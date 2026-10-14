"""Contract tests for checkpoint persistence, source pins and publication."""
import copy
import json
import unittest

from novel_workflow import STATE, LEDGER, STAGES, WorkflowError, blob_sha, encode, prepare, status


def snapshot():
    contents = {
        STATE: encode({"schema_version": 1, "revision": 0, "active_job": None, "jobs": {}, "last_event": {}}),
        LEDGER: encode({"schema_version": 1, "characters": {}, "threads": {}}),
        "AGENTS.md": "작업 지침을 적용한다.\n",
        "원고/집필 원칙.md": "현재 자료를 읽고 집필한다.\n",
        "원고/본문/24 준비.md": "인물은 항구에 도착했다.\n",
    }
    return {"repository": "glutfeste/buyu-haepari-dogam", "branch": "main", "head": "a" * 40,
            "tree": "b" * 40, "verified_new_paths": ["원고/본문/25 새 항로.md"], "files": {p: {"content": t, "sha": blob_sha(t)} for p, t in contents.items()}}


def publish(snap, result):
    result = copy.deepcopy(result)
    for item in result["tree_elements"]:
        snap["files"][item["path"]] = {"content": item["content"], "sha": blob_sha(item["content"])}
    snap["head"] = blob_sha(encode(result))
    snap["tree"] = blob_sha("tree:" + snap["head"])


def current(snap):
    return json.loads(snap["files"][STATE]["content"])


def event(snap, op, **values):
    revision = current(snap)["revision"]
    return {"event_id": "event-" + str(revision + 1), "expected_revision": revision, "op": op, **values}


def start(snap, name="c0025"):
    ev = event(snap, "start", job_id=name, chapter=25, request="25화 집필해",
               source_paths=["AGENTS.md", "원고/집필 원칙.md", "원고/본문/24 준비.md"])
    publish(snap, prepare(snap, ev))


def advance(snap, text="인물은 항구에 도착했다.\n"):
    state = current(snap)
    job = state["jobs"][state["active_job"]]
    ev = event(snap, "advance", stage=job["stage"], content=text)
    if job["stage"] == "context":
        ev["read_attestation"] = {"reader": "ChatGPT", "complete_paths": list(job["sources"])}
    if job["stage"] == "revision":
        ev["review_decision"] = {"instruction": "검토 결과를 반영해 수정해", "review_sha": job["artifacts"]["review"]["sha"]}
    publish(snap, prepare(snap, ev))


def finish_ready(snap):
    start(snap)
    for _ in STAGES[:5]:
        advance(snap)


def final_event(snap, **overrides):
    job = current(snap)["jobs"]["c0025"]
    values = {"target": "원고/본문/25 새 항로.md", "target_expected_sha": None,
              "approval": {"actor": "user", "instruction": "이 수정본으로 확정해",
                           "revision_sha": job["artifacts"]["revision"]["sha"]}}
    values.update(overrides)
    return event(snap, "finalize", **values)


class WorkflowTests(unittest.TestCase):
    def test_initial_state_is_ready(self):
        self.assertEqual(status(snapshot())["revision"], 0)

    def test_stage_sequence_and_atomic_state(self):
        s = snapshot(); start(s)
        for stage in STAGES[:5]:
            self.assertEqual(current(s)["jobs"]["c0025"]["stage"], stage)
            advance(s)
        result = prepare(s, final_event(s))
        paths = [item["path"] for item in result["tree_elements"]]
        self.assertIn(STATE, paths); self.assertIn("원고/본문/25 새 항로.md", paths)
        publish(s, result)
        self.assertEqual(current(s)["jobs"]["c0025"]["stage"], "complete")
        self.assertIsNone(current(s)["active_job"])

    def test_partial_survives_serialization(self):
        s = snapshot(); start(s); advance(s); advance(s)
        publish(s, prepare(s, event(s, "partial", stage="draft", content="첫 장면을 기록했다.\n")))
        restored = json.loads(json.dumps(s, ensure_ascii=False))
        result = status(restored)
        self.assertEqual(result["next_action"], "본문 집필")
        self.assertEqual(result["partial"]["stage"], "draft")
        advance(restored)
        self.assertEqual(status(restored)["next_action"], "원고 검토")

    def test_latest_revision_gate(self):
        s = snapshot(); start(s)
        with self.assertRaisesRegex(WorkflowError, "LATEST_REVISION_REQUIRED"):
            prepare(s, {"event_id": "stale", "expected_revision": 0, "op": "pause"})

    def test_retry_returns_saved_receipt(self):
        s = snapshot(); start(s)
        ev = event(s, "partial", stage="context", content="자료를 확인 중이다.\n")
        publish(s, prepare(s, ev))
        self.assertEqual(prepare(s, ev)["status"], "already_saved")

    def test_reused_id_requires_same_content(self):
        s = snapshot(); start(s)
        ev = event(s, "pause"); publish(s, prepare(s, ev)); ev["op"] = "annotate"
        with self.assertRaisesRegex(WorkflowError, "EVENT_ID_CONTENT_CHECK"):
            prepare(s, ev)

    def test_stage_order_gate(self):
        s = snapshot(); start(s)
        with self.assertRaisesRegex(WorkflowError, "EXPECTED_STAGE:context"):
            prepare(s, event(s, "advance", stage="draft", content="본문"))

    def test_complete_read_scope_gate(self):
        s = snapshot(); start(s)
        with self.assertRaisesRegex(WorkflowError, "COMPLETE_SCOPE_REQUIRED"):
            prepare(s, event(s, "advance", stage="context", content="자료 기록",
                             read_attestation={"reader": "ChatGPT", "complete_paths": ["AGENTS.md"]}))

    def test_full_text_gate(self):
        s = snapshot(); start(s)
        sources = list(current(s)["jobs"]["c0025"]["sources"])
        del s["files"]["AGENTS.md"]["content"]
        with self.assertRaisesRegex(WorkflowError, "FULL_TEXT_REQUIRED"):
            prepare(s, event(s, "advance", stage="context", content="자료 기록",
                             read_attestation={"reader": "ChatGPT", "complete_paths": sources}))

    def test_changed_source_requests_refresh(self):
        s = snapshot(); start(s)
        s["files"]["AGENTS.md"] = {"content": "새 기준", "sha": blob_sha("새 기준")}
        with self.assertRaisesRegex(WorkflowError, "REFRESH_REQUIRED"):
            status(s)
        publish(s, prepare(s, event(s, "refresh")))
        self.assertEqual(status(s)["next_action"], "자료 확인")

    def test_changed_artifact_requests_refresh(self):
        s = snapshot(); start(s); advance(s)
        p = current(s)["jobs"]["c0025"]["artifacts"]["context"]["path"]
        s["files"][p] = {"content": "편집", "sha": blob_sha("편집")}
        with self.assertRaisesRegex(WorkflowError, "REFRESH_REQUIRED"):
            status(s)

    def test_content_hash_gate(self):
        s = snapshot(); s["files"][STATE]["content"] += " "
        with self.assertRaisesRegex(WorkflowError, "CONTENT_SHA_CHECK"):
            status(s)

    def test_pause_and_activate(self):
        s = snapshot(); start(s)
        publish(s, prepare(s, event(s, "pause")))
        self.assertIsNone(status(s)["active_job"])
        self.assertEqual(status(s)["resume_job"], "c0025")
        publish(s, prepare(s, event(s, "activate", job_id="c0025")))
        self.assertEqual(status(s)["active_job"], "c0025")

    def test_author_approval_gate(self):
        s = snapshot(); finish_ready(s)
        with self.assertRaisesRegex(WorkflowError, "AUTHOR_APPROVAL_REQUIRED"):
            prepare(s, final_event(s, approval={}))

    def test_approved_revision_gate(self):
        s = snapshot(); finish_ready(s)
        ev = final_event(s); ev["approval"]["revision_sha"] = "0" * 40
        with self.assertRaisesRegex(WorkflowError, "APPROVED_REVISION_CHECK"):
            prepare(s, ev)

    def test_manuscript_path_gate(self):
        s = snapshot(); finish_ready(s)
        with self.assertRaisesRegex(WorkflowError, "PROJECT_PATH_REQUIRED"):
            prepare(s, final_event(s, target="원고/본문/../../AGENTS.md"))

    def test_overwrite_requires_target_sha(self):
        s = snapshot(); finish_ready(s)
        s["files"]["원고/본문/25 새 항로.md"] = {"content": "작가 원고", "sha": blob_sha("작가 원고")}
        with self.assertRaisesRegex(WorkflowError, "TARGET_VERSION_CHECK"):
            prepare(s, final_event(s))

    def test_target_chapter_gate(self):
        s = snapshot(); finish_ready(s)
        with self.assertRaisesRegex(WorkflowError, "TARGET_CHAPTER_CHECK"):
            prepare(s, final_event(s, target="원고/본문/26 새 항로.md"))

    def test_evidence_bound_ledger(self):
        s = snapshot(); p = "원고/본문/24 준비.md"
        row = {"id": "character-1-location", "value": "항구", "kind": "observed",
               "evidence": {"path": p, "sha": s["files"][p]["sha"], "quote": "인물은 항구에 도착했다."}}
        publish(s, prepare(s, event(s, "annotate", ledger={"characters": [row]})))
        ledger = json.loads(s["files"][LEDGER]["content"])
        self.assertEqual(ledger["characters"][row["id"]]["authority"], "derived_with_citation")

    def test_evidence_quote_gate(self):
        s = snapshot(); p = "원고/본문/24 준비.md"
        row = {"id": "thread-1", "value": "회수", "kind": "observed",
               "evidence": {"path": p, "sha": s["files"][p]["sha"], "quote": "배는 도착했다."}}
        with self.assertRaisesRegex(WorkflowError, "EVIDENCE_QUOTE_CHECK"):
            prepare(s, event(s, "annotate", ledger={"threads": [row]}))

    def test_branch_gate(self):
        s = snapshot(); s["branch"] = "other"
        with self.assertRaisesRegex(WorkflowError, "MAIN_BRANCH_REQUIRED"):
            status(s)

    def test_active_job_gate(self):
        s = snapshot(); start(s)
        with self.assertRaisesRegex(WorkflowError, "FINISH_OR_PAUSE_ACTIVE_JOB"):
            start(s, "second")

    def test_explicit_target_version(self):
        s = snapshot(); finish_ready(s); ev = final_event(s); del ev["target_expected_sha"]
        with self.assertRaisesRegex(WorkflowError, "EXPLICIT_TARGET_VERSION_REQUIRED"):
            prepare(s, ev)

    def test_new_target_inventory_gate(self):
        s = snapshot(); finish_ready(s); s["verified_new_paths"] = []
        with self.assertRaisesRegex(WorkflowError, "TARGET_INVENTORY_CHECK"):
            prepare(s, final_event(s))

    def test_commit_bundle_uses_snapshot_parent(self):
        s = snapshot(); start(s)
        result = prepare(s, event(s, "pause"))
        self.assertEqual(result["expected_head"], s["head"])
        self.assertEqual(result["base_tree_sha"], s["tree"])
        self.assertEqual(result["branch"], "main")

    def test_early_finalization_gate(self):
        s = snapshot(); start(s)
        with self.assertRaisesRegex(WorkflowError, "REVISION_COMPLETION_REQUIRED"):
            prepare(s, event(s, "finalize"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
