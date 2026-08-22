#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BODY = ROOT / "원고" / "본문"
REPORT_PATH = ROOT / "원고" / "본문 전수 개고 감사 보고서.md"

body_files = sorted(BODY.glob("*.md"))
assert len(body_files) == 23, f"expected 23 body files, found {len(body_files)}"
texts = {p.name: p.read_text(encoding="utf-8") for p in body_files}
all_body = "\n".join(texts.values())

checks: list[tuple[str, bool, str]] = []

def check(name: str, condition: bool, detail: str) -> None:
    checks.append((name, condition, detail))
    if not condition:
        raise AssertionError(f"{name}: {detail}")

# 보호항목
check("10화 현재 테오도어 반응", "그래서 저 군인들이 아까 그 아가씨를 계속 살폈군." in texts["10 사천 리브라.md"], "현재 반응 유지")
check("10화 제1강대국 정보", "벡실리아를 제1의 강대국으로 세계에 군림하게 하는 핵심 기반이에요." in texts["10 사천 리브라.md"], "필수 세계질서 명제 유지")
check("15화 외부·내부 관계 대조", "종국적으로는 그렇지 않아. 현실적으로는 그렇지." in texts["15 정정 소견.md"], "연대채무와 구상 관계 유지")
check("15화 담보 또는 이행 선택지", "24,000리브라 상당의 적격 담보 제공 또는 채무 이행" in texts["15 정정 소견.md"], "선이행 의무로 왜곡하지 않음")
check("19화 관계 오판", all(x in texts["19 뒷문.md"] for x in ("가출 한번 해 봐", "사춘기가 조금 늦었지만", "네 침대는 안 치울 테니까")), "가출·사춘기·침대 유지")
check("19화 베르나르 결정 동작", "손잡이 위의 손가락이 아주 조금 멎었다." in texts["19 뒷문.md"], "고유 기능 정지 보존")
check("20화 무손실 압승", all(x in texts["20 반환 목록.md"] for x in ("도적단 따위가.", "칼끝이 단단한 피부에서 옆으로 미끄러졌다")), "전력 차 유지")
check("20화 아멜리 주체성", all(x in texts["20 반환 목록.md"] for x in ("내 짐 챙겨 올게.", "자기 가방을 멘 채 큰 문으로 걸어 나갔다", "네가 필요해.")), "자기 짐·큰 문·능력 기반 영입 유지")
check("23화 단일 공방", all(x in texts["23 손바닥 위의 항로.md"] for x in ("탄중 사뭇. 내일도 여기로 가는 척할 거야.", "이 계획은 거기에 걸어.", "돌아간 게 아니군.", "아쿠아 알타야.")), "기만·실행·오판·재계산 유지")

# 옛 문장과 적용 전 문장 잔존 금지
forbidden = {
    "테오도어 옛 촬영 농담": "담보물 번호부터 틀리지 않는 게 좋겠군",
    "2화 부정형 경계": "렌즈가 흐려진 것도 아닌데 넬라는 망원경을 내렸다가 다시 들었다",
    "5화 펜 정지": "안개에 가렸던 상부 몸체를 그리려던 펜끝은 종이 위에서 멈췄고",
    "9화 포장 손 정지": "테오도어는 포장지를 접던 손을 멈추고",
    "13화 다음 선편 손 정지": "`다음 선편`이라는 말을 적는 순간 손이 멈췄다",
    "15화 이중 정지": "파비아가 손을 허공에서 멈추고",
    "16화 마개 정지": "테오도어가 마개를 쥔 손을 멈췄다",
    "16화 검집 정지": "마르톤의 손이 검집 고리에서 멎었다",
    "18화 상자보다 아멜리 쪽 정지": "손은 상자보다 아멜리 쪽에서 더 자주 멈췄다",
    "19화 상자 손가락 굳음": "상자 손잡이를 쥔 손가락이 그대로 굳었다",
    "20화 반복 군중 웃음 1": "도적들이 다시 웃었고 아멜리도 코로 짧게 웃었다",
    "20화 반복 군중 웃음 2": "뒤의 도적들 사이에서 웃음이 터졌다. 코르베르는 한 걸음 가까이",
}
for name, phrase in forbidden.items():
    check(name, phrase not in all_body, "적용 전 문장이 본문에 남지 않음")

# 설정 동기화
EP = ROOT / "부유해파리도감의 설정과 전개" / "이야기" / "에피소드"
ep05 = (EP / "05 용 사진과 오르텔라행.md").read_text(encoding="utf-8")
ep07 = (EP / "07 실해파리와 도주.md").read_text(encoding="utf-8")
ep08 = (EP / "08 셀라리온과 아멜리.md").read_text(encoding="utf-8")
check("에피소드 5 옛 대사 제거", "담보물 번호부터 틀리지 않는 게 좋겠군" not in ep05, "현재 본문 반응으로 교체")
check("에피소드 5 제1강대국", "벡실리아를 제1의 강대국" in ep05, "필수 정보 명시")
check("에피소드 7 연도", "1478년" not in ep07 and "1490년" in ep07, "1410+80 계산 동기화")
check("에피소드 8 자기 짐", "마르톤은 아멜리의 짐을 먼저 가져온다" not in ep08 and "아멜리는 위층 자기 방에서 여행 가방을 직접 챙겨" in ep08, "아멜리 주체성 동기화")

# 화별 문자 수
lengths = []
for p in body_files:
    text = texts[p.name]
    lengths.append((p.stem, len(text.replace("\n", "").replace("\r", ""))))

# 남은 정지 동작 후보. 고유 기능인지 수동 판정할 수 있도록 줄 단위로 전부 보존한다.
stop_pattern = re.compile(r"(?:손|손가락|엄지|펜끝|시선|발).{0,50}(?:멈|멎|굳)")
stop_candidates: list[tuple[str, int, str]] = []
for p in body_files:
    for i, line in enumerate(texts[p.name].splitlines(), 1):
        if stop_pattern.search(line):
            stop_candidates.append((p.stem, i, line.strip()))

# 9화 이후 기존 방법론 재설명 후보. 새 학술 개념은 자동 위반으로 판정하지 않는다.
method_terms = ("직접 관찰", "구술", "원인 칸", "반응 원인", "물음표", "비워 두", "따로 시험", "조건을 따로", "확인해야")
method_candidates: list[tuple[str, int, str]] = []
for p in body_files[8:]:
    for i, line in enumerate(texts[p.name].splitlines(), 1):
        if any(term in line for term in method_terms):
            method_candidates.append((p.stem, i, line.strip()))

# 18~20화 웃음 표지
laugh_candidates: list[tuple[str, int, str]] = []
for name in ("18 공모 혐의.md", "19 뒷문.md", "20 반환 목록.md"):
    for i, line in enumerate(texts[name].splitlines(), 1):
        if "웃" in line or "입꼬리" in line:
            laugh_candidates.append((Path(name).stem, i, line.strip()))

report: list[str] = [
    "# 『부유해파리도감』 본문 전수 개고 감사 보고서",
    "",
    "> 이 보고서는 체크리스트 적용 뒤 1~23화와 관련 에피소드 문서를 다시 읽기 위한 임시 검증 문서다. 최종 통과와 함께 체크리스트·일회성 도구·이 보고서를 삭제하되 커밋 이력은 보존한다.",
    "",
    "## 자동 보호·정본 검사",
    "",
]
for name, ok, detail in checks:
    report.append(f"- [{'x' if ok else ' '}] **{name}:** {detail}")

report.extend(["", "## 화별 문자 수", "", "공백과 문장부호를 포함하고 줄바꿈만 제외했다.", "", "| 화 | 문자 수 |", "|---|---:|"])
for stem, n in lengths:
    report.append(f"| {stem} | {n:,} |")

report.extend(["", "## 남은 정지 동작 후보", ""])
if stop_candidates:
    for stem, line_no, line in stop_candidates:
        report.append(f"- **{stem}:{line_no}** — {line}")
else:
    report.append("- 없음")

report.extend(["", "## 9화 이후 방법론 표지 후보", "", "아래 항목은 자동 위반 목록이 아니다. 새 개념·새 증거·실제 위험 기능을 문맥에서 구분한다.", ""])
if method_candidates:
    for stem, line_no, line in method_candidates:
        report.append(f"- **{stem}:{line_no}** — {line}")
else:
    report.append("- 없음")

report.extend(["", "## 18~20화 웃음·입꼬리 표지", ""])
if laugh_candidates:
    for stem, line_no, line in laugh_candidates:
        report.append(f"- **{stem}:{line_no}** — {line}")
else:
    report.append("- 없음")

report.extend([
    "",
    "## 수동 기능 판정",
    "",
    "- [x] 1~8화는 방법론 확립 구간으로 보존했다.",
    "- [x] 10화의 설명은 추심관 업무·모렌타·전략급 전력·제1강대국이라는 서로 다른 필수 층위를 유지했다.",
    "- [x] 15화는 법률관계의 외부·내부 층위와 적격 담보 또는 이행 선택지를 유지했다.",
    "- [x] 16화의 법률 반복은 화자·입장 변화와 역콜백 기능 때문에 유지했다.",
    "- [x] 18화의 첫 용서 재연과 집단 웃음은 아멜리의 오해와 도적단 공연성을 보여 주므로 유지했다.",
    "- [x] 19화의 가출·사춘기는 코르베르의 관계 오판이므로 유지했다.",
    "- [x] 20화는 기능이 겹치는 군중 웃음만 줄이고 실제 은혜·소유욕·목표·무손실 압승을 유지했다.",
    "- [x] 21화는 새 학술 개념과 인위선택 우선순위를 삭제하지 않고 표본·항해도에 결속했다.",
    "- [x] 22화는 티투스와 루케타의 출처를 보존하고 고래 관찰 중 일화 밀도만 줄였다.",
    "- [x] 23화는 한 화 구조를 유지하고 첫 질문 사다리와 반복 행정 문장만 압축했다.",
    "",
    "## 완료 전 남은 절차",
    "",
    "- [ ] 위 후보들을 문맥에서 한 번 더 확인한다.",
    "- [ ] 변경 커밋의 전체 diff를 확인한다.",
    "- [ ] 보호항목·정본·문체·전역 패턴이 모두 통과하면 체크리스트와 임시 도구·보고서를 삭제한다.",
])
REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")
print(REPORT_PATH)
