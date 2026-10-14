"""ChatGPT/GitHub writing checkpoints. Python 3.10+, standard library.

The caller supplies GitHub snapshots and authoring results. The engine validates
stage transitions and produces one Git-tree change set. GitHub publishes that
change set using create_tree, create_commit and update_ref with expected_sha.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import PurePosixPath, Path
from typing import Any

ROOT = "집필시스템/"
STATE = ROOT + "진행상태.json"
LEDGER = ROOT + "인물·복선.json"
STAGES = ("context", "blueprint", "draft", "review", "revision", "finalize", "complete")
LABELS = dict(zip(STAGES, ("자료 확인", "장면 설계", "본문 집필", "원고 검토", "원고 수정", "작가 확정", "완료")))
REQUIRED_RULES = ("AGENTS.md", "원고/집필 원칙.md")
SHA = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")


class WorkflowError(ValueError):
    """Structured validation result for the calling assistant."""


def require(condition: Any, code: str) -> None:
    if condition:
        return
    raise WorkflowError(code)


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def blob_sha(text: str) -> str:
    raw = text.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def path_ok(path: str) -> str:
    require(isinstance(path, str) and bool(path), "PATH_REQUIRED")
    p = PurePosixPath(path)
    require(p.as_posix() == path and p.is_absolute() is False, "RELATIVE_PATH_REQUIRED")
    require(all(part not in (".", "..", ".git") for part in p.parts), "PROJECT_PATH_REQUIRED")
    require(all(c not in path for c in ("\\", "\x00", "\n", "\r", ":")), "PORTABLE_PATH_REQUIRED")
    return path


def entry(snapshot: dict, path: str, text: bool = False) -> dict:
    path_ok(path)
    value = snapshot["files"].get(path)
    require(isinstance(value, dict), "FETCH_REQUIRED:" + path)
    require(bool(SHA.fullmatch(value.get("sha", ""))), "BLOB_SHA_REQUIRED:" + path)
    if "content" in value:
        require(isinstance(value["content"], str), "UTF8_REQUIRED:" + path)
        require(blob_sha(value["content"]) == value["sha"], "CONTENT_SHA_CHECK:" + path)
    if text:
        require("content" in value, "FULL_TEXT_REQUIRED:" + path)
    return value


def document(snapshot: dict, path: str) -> dict:
    result = json.loads(entry(snapshot, path, True)["content"])
    require(isinstance(result, dict), "OBJECT_REQUIRED:" + path)
    return result


def source_pins(snapshot: dict, paths: list[str]) -> dict:
    require(isinstance(paths, list) and len(paths) > 0, "SOURCE_SCOPE_REQUIRED")
    return {path_ok(p): entry(snapshot, p)["sha"] for p in sorted(set(paths))}


def freshness(snapshot: dict, job: dict) -> None:
    pins = dict(job["sources"])
    pins.update({a["path"]: a["sha"] for a in job["artifacts"].values()})
    if job.get("partial"):
        pins[job["partial"]["path"]] = job["partial"]["sha"]
    for path, sha in pins.items():
        require(entry(snapshot, path)["sha"] == sha, "REFRESH_REQUIRED:" + path)


def checked(snapshot: dict) -> dict:
    require(snapshot.get("repository") == "glutfeste/buyu-haepari-dogam", "REPOSITORY_CHECK")
    require(snapshot.get("branch") == "main", "MAIN_BRANCH_REQUIRED")
    for key in ("head", "tree"):
        require(bool(SHA.fullmatch(snapshot.get(key, ""))), key.upper() + "_SHA_REQUIRED")
    state = document(snapshot, STATE)
    require(state.get("schema_version") == 1, "SCHEMA_VERSION_CHECK")
    require(type(state.get("revision")) is int and state["revision"] >= 0, "REVISION_CHECK")
    return state


def status(snapshot: dict) -> dict:
    state = checked(snapshot)
    active = state.get("active_job")
    result = {"revision": state["revision"], "active_job": active, "resume_job": state.get("resume_job"), "jobs": state["jobs"]}
    if active:
        job = state["jobs"][active]
        freshness(snapshot, job)
        result.update(next_action=LABELS[job["stage"]], sources=job["sources"], partial=job.get("partial"))
    else:
        result["next_action"] = "작가가 지정한 집필·개고·검토 작업 시작"
    return result


def merge_ledger(snapshot: dict, additions: dict, writes: dict[str, str]) -> None:
    ledger = document(snapshot, LEDGER)
    for group in ("characters", "threads"):
        rows = additions.get(group, [])
        require(isinstance(rows, list), "LEDGER_LIST_REQUIRED")
        for row in rows:
            require(isinstance(row, dict) and bool(ID.fullmatch(row.get("id", ""))), "LEDGER_ID_REQUIRED")
            require(bool(str(row.get("value", "")).strip()), "LEDGER_VALUE_REQUIRED")
            evidence = row.get("evidence", {})
            path = path_ok(evidence.get("path", ""))
            require(path.startswith(("원고/본문/", "부유해파리도감의 설정과 전개/")), "CANON_SOURCE_REQUIRED")
            if path in writes:
                text = writes[path]
                sha = blob_sha(text)
            else:
                src = entry(snapshot, path, True)
                text, sha = src["content"], src["sha"]
            quote = evidence.get("quote", "")
            require(isinstance(quote, str) and bool(quote.strip()) and quote in text, "EVIDENCE_QUOTE_CHECK")
            require(evidence.get("sha") == sha, "EVIDENCE_SHA_CHECK")
            require(row.get("kind") in ("observed", "planned"), "EVIDENCE_KIND_REQUIRED")
            item = copy.deepcopy(row)
            item["authority"] = "derived_with_citation"
            ledger[group][row["id"]] = item
    writes[LEDGER] = encode(ledger)


def prepare(snapshot: dict, event: dict) -> dict:
    """Validate an authoring event and produce an atomic Git change set."""
    state = checked(snapshot)
    require(isinstance(event, dict), "EVENT_OBJECT_REQUIRED")
    event_id = event.get("event_id", "")
    require(bool(ID.fullmatch(event_id)), "EVENT_ID_REQUIRED")
    fingerprint = hashlib.sha256(encode(event).encode()).hexdigest()
    if state.get("last_event", {}).get("id") == event_id:
        require(state["last_event"]["fingerprint"] == fingerprint, "EVENT_ID_CONTENT_CHECK")
        return {"status": "already_saved", "tree_elements": [], "revision": state["revision"]}
    require(event.get("expected_revision") == state["revision"], "LATEST_REVISION_REQUIRED")
    op = event.get("op")
    writes: dict[str, str] = {}
    active = state.get("active_job")
    job = state["jobs"].get(active) if active else None

    if op == "start":
        require(active is None, "FINISH_OR_PAUSE_ACTIVE_JOB")
        job_id = event.get("job_id", "")
        require(bool(ID.fullmatch(job_id)), "JOB_ID_REQUIRED")
        require(job_id not in state["jobs"], "FRESH_JOB_ID_REQUIRED")
        require(type(event.get("chapter")) is int and event["chapter"] > 0, "CHAPTER_REQUIRED")
        require(bool(str(event.get("request", "")).strip()), "AUTHOR_REQUEST_REQUIRED")
        paths = event.get("source_paths", [])
        require(all(p in paths for p in REQUIRED_RULES), "RULE_SOURCE_REQUIRED")
        job = {"chapter": event["chapter"], "request": event["request"], "stage": "context",
               "sources": source_pins(snapshot, paths), "artifacts": {}, "partial": None,
               "read_attestation": {}, "review_decision": {}}
        state["jobs"][job_id] = job
        state["active_job"] = job_id
        state["resume_job"] = job_id
    elif op == "annotate":
        merge_ledger(snapshot, event.get("ledger", {}), writes)
    elif op == "activate":
        require(active is None, "FINISH_OR_PAUSE_ACTIVE_JOB")
        job_id = event.get("job_id")
        require(job_id in state["jobs"], "KNOWN_JOB_REQUIRED")
        target = state["jobs"][job_id]
        require(target["stage"] in STAGES[:-1], "ACTIVE_STAGE_REQUIRED")
        freshness(snapshot, target)
        state["active_job"] = job_id
        state["resume_job"] = job_id
    else:
        require(isinstance(job, dict), "START_JOB_REQUIRED")
        if op == "refresh":
            paths = event.get("source_paths", list(job["sources"]))
            require(all(p in paths for p in REQUIRED_RULES), "RULE_SOURCE_REQUIRED")
            job.update(sources=source_pins(snapshot, paths), stage="context", artifacts={},
                       partial=None, read_attestation={}, review_decision={})
        else:
            freshness(snapshot, job)
            if op == "pause":
                state["resume_job"] = active
                state["active_job"] = None
            elif op in ("partial", "advance"):
                stage = job["stage"]
                require(stage in STAGES[:5], "AUTHOR_FINALIZATION_REQUIRED")
                require(event.get("stage") == stage, "EXPECTED_STAGE:" + stage)
                text = event.get("content", "")
                require(isinstance(text, str) and bool(text.strip()), "STAGE_CONTENT_REQUIRED")
                if stage == "context" and op == "advance":
                    attestation = event.get("read_attestation", {})
                    require(attestation.get("reader") == "ChatGPT", "READER_ATTESTATION_REQUIRED")
                    require(set(attestation.get("complete_paths", [])) == set(job["sources"]), "COMPLETE_SCOPE_REQUIRED")
                    for path in job["sources"]:
                        entry(snapshot, path, True)
                    job["read_attestation"] = attestation
                if stage == "revision" and op == "advance":
                    decision = event.get("review_decision", {})
                    require(bool(str(decision.get("instruction", "")).strip()), "REVISION_INSTRUCTION_REQUIRED")
                    require(decision.get("review_sha") == job["artifacts"]["review"]["sha"], "CURRENT_REVIEW_REQUIRED")
                    job["review_decision"] = decision
                path = ROOT + "작업/" + active + "/" + stage + ".md"
                writes[path] = text
                record = {"path": path, "sha": blob_sha(text), "stage": stage}
                if op == "partial":
                    job["partial"] = record
                else:
                    job["artifacts"][stage] = record
                    job["partial"] = None
                    job["stage"] = STAGES[STAGES.index(stage) + 1]
            elif op == "finalize":
                require(job["stage"] == "finalize", "REVISION_COMPLETION_REQUIRED")
                approval = event.get("approval", {})
                require(approval.get("actor") == "user" and bool(str(approval.get("instruction", "")).strip()), "AUTHOR_APPROVAL_REQUIRED")
                revised = job["artifacts"]["revision"]
                require(approval.get("revision_sha") == revised["sha"], "APPROVED_REVISION_CHECK")
                text = entry(snapshot, revised["path"], True)["content"]
                target = path_ok(event.get("target", ""))
                require(bool(re.fullmatch(r"원고/본문/[0-9]{2,} [^/]+\.md", target)), "MANUSCRIPT_TARGET_REQUIRED")
                require(int(PurePosixPath(target).name.split(" ", 1)[0]) == job["chapter"], "TARGET_CHAPTER_CHECK")
                current = snapshot["files"].get(target)
                old_sha = entry(snapshot, target)["sha"] if current else None
                if current is None:
                    require(target in snapshot.get("verified_new_paths", []), "TARGET_INVENTORY_CHECK")
                require(event.get("target_expected_sha") == old_sha, "TARGET_VERSION_CHECK")
                require(event.get("target_expected_sha", "omitted") != "omitted", "EXPLICIT_TARGET_VERSION_REQUIRED")
                writes[target] = text
                job.update(stage="complete", approval=approval, final={"path": target, "sha": blob_sha(text)})
                if event.get("ledger"):
                    merge_ledger(snapshot, event["ledger"], writes)
                state["active_job"] = None
                state["resume_job"] = None
            else:
                raise WorkflowError("SUPPORTED_OPERATION_REQUIRED")
    state["revision"] += 1
    state["last_event"] = {"id": event_id, "fingerprint": fingerprint}
    writes[STATE] = encode(state)
    return {"status": "prepared", "repository": snapshot["repository"], "branch": "main",
            "expected_head": snapshot["head"], "base_tree_sha": snapshot["tree"],
            "revision": state["revision"],
            "tree_elements": [{"path": p, "mode": "100644", "type": "blob", "content": text}
                              for p, text in sorted(writes.items())]}


def main() -> int:
    parser = argparse.ArgumentParser(description="집필 단계 검사와 GitHub 저장 묶음 생성")
    parser.add_argument("command", choices=("status", "prepare"))
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if args.command == "status":
            result = status(snapshot)
        else:
            require(isinstance(args.event, Path), "EVENT_FILE_REQUIRED")
            result = prepare(snapshot, json.loads(args.event.read_text(encoding="utf-8")))
        text = encode(result)
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    except (WorkflowError, OSError, ValueError, TypeError, KeyError) as exc:
        print(encode({"status": "action_required", "detail": str(exc)}), file=sys.stderr, end="")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
