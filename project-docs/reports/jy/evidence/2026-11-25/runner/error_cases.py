"""오류안내-01~05 사례 정의와 판정 함수. tui_runner.py 가 가져다 쓴다(훅 켬 전용).

판정에 쓰는 자료
- Ghost-ALICE 훅 실행기 기록: ~/.ghost-alice/session-logs/claude/<세션>/strict-hook-output.jsonl
- 모니터 5번 카드: 모니터의 /api/timeline 응답에서 known 이 false 인 항목이 '해설 미등록'으로 표시된다.
- 메시지가 "쉬운 말"인지: 계획서 기준(무엇이·왜 막혔는지, 사용자가 다음에 할 일)을 기계로 판정할 수 없으므로
  막힘 메시지 원문에 한글이 한 글자도 없으면 걸림으로 본다. 원문은 기록에 남긴다.
"""
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from collections import Counter
from datetime import datetime
from pathlib import Path

import cli_runner as R

PASS, FAIL, REVIEW = R.PASS, R.FAIL, R.REVIEW
GA_HOME = Path.home() / ".ghost-alice"
VIS_CLI = GA_HOME / "runtime" / "current" / "_shared" / "agent_visibility_cli.py"
KOREAN = re.compile("[가-힣]")
GATE_CODE = re.compile(r"\[completion-gate\]\s*(?:[A-Z][^:]*: )?([a-z]+(?:-[a-z0-9]+)+):")
NOT_WINDOWS = re.compile(r"(?:^|[\s`;&|(])(?:env\s+[A-Za-z_][A-Za-z0-9_]*=|export\s+[A-Za-z_][A-Za-z0-9_]*=|[A-Z_][A-Z0-9_]*=\S+\s+python)")
LEAK = re.compile(r"completion-gate|route-unavailable|repair-target|delivery-route|session-intent|response[-_]route|"
                  r"completion_recording|[a-z]+-[a-z]+-(?:invalid|unavailable|unbound|incompatible)", re.I)
README_Q = "test-fixture/README.md 파일 맨 위 제목 한 줄만 알려줘."
ANY_Q = ["파이썬에서 리스트와 튜플의 차이를 한 줄로 알려줘.", "파이썬에서 딕셔너리와 집합의 차이를 한 줄로 알려줘."]


def moment(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None


def raw_hooks(session):
    """훅 실행기 기록 전체(잘라내지 않음). out 은 훅이 낸 JSON."""
    path = GA_HOME / "session-logs" / "claude" / str(session) / "strict-hook-output.jsonl"
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            try:
                out = json.loads(row.get("stdout") or "")
            except ValueError:
                out = {}
            out = out if isinstance(out, dict) else {}
            specific = out.get("hookSpecificOutput") if isinstance(out.get("hookSpecificOutput"), dict) else {}
            rows.append({"event": row.get("event"), "hook": row.get("hook_id"), "ts": row.get("ts"), "at": moment(row.get("ts")),
                         "seconds": float(row.get("observed_duration_s") or 0), "visible": row.get("visible_decision"),
                         "decision": str(out.get("decision") or "").lower(), "reason": str(out.get("reason") or ""),
                         "system": str(out.get("systemMessage") or ""), "context": str(specific.get("additionalContext") or ""),
                         "stdout": str(row.get("stdout") or ""), "surface": str(row.get("user_surface_output") or "")})
    return rows


def within(rows, run, index):
    """index 번째 입력을 보낸 뒤부터 다음 입력 전까지의 훅 기록."""
    start = moment(run["turns"][index]["sent_at"])
    end = moment(run["turns"][index + 1]["sent_at"]) if index + 1 < len(run["turns"]) else None
    return [r for r in rows if r["at"] and start and r["at"] >= start and (end is None or r["at"] < end)]


def stop_blocks(rows):
    return [r for r in rows if r["event"] == "Stop" and r["decision"] == "block"]


def code_of(text):
    hit = GATE_CODE.search(text or "")
    return hit.group(1) if hit else None


def codes(blocks):
    return Counter(code_of(b["reason"]) or "(코드 없음)" for b in blocks)


def has_korean(blocks):
    return any(KOREAN.search(b["reason"]) for b in blocks)


def context_length(rows):
    return sum(len(r["context"]) for r in rows)


def monitor_unknown(session):
    """모니터 5번 카드에서 '해설 미등록'으로 표시되는 항목(known == false)."""
    R.http("GET", "/api", timeout=120)
    data = R.http("GET", "/api/timeline?session=" + urllib.parse.quote(str(session)), timeout=120)
    found = []
    for turn in data.get("turns") or []:
        for item in turn.get("findings") or []:
            if isinstance(item, dict) and item.get("known") is False:
                found.append(f"{item.get('name')}: {item.get('title')}")
    return found


def block_text(blocks):
    if not blocks:
        return "Stop 막힘 0회"
    first = blocks[0]["reason"].replace("\n", " ")[:260]
    return (f"Stop 막힘 {len(blocks)}회(코드 {', '.join(f'{k} {v}회' for k, v in codes(blocks).items())}), "
            f"막힘 메시지에 한글 {'있음' if has_korean(blocks) else '없음'}, 첫 메시지 원문: {first}")


def answer(run, index=-1):
    return R.last_text(run, index).strip()[:200]


def judge_e01(run):
    rows = raw_hooks(run["session"])
    blocks = stop_blocks(rows)
    unknown = monitor_unknown(run["session"])
    run["err"] = {"blocks": [b["reason"] for b in blocks], "unknown": unknown, "context_length": context_length(rows),
                  "stop_seconds": [r["seconds"] for r in rows if r["event"] == "Stop"]}
    verdict = [FAIL if blocks else PASS, FAIL if blocks and not has_korean(blocks) else PASS, FAIL if unknown else PASS]
    return verdict, (f"{block_text(blocks)} / 모니터 해설 미등록 {len(unknown)}건{('(' + '; '.join(unknown[:3]) + ')') if unknown else ''} / "
                     f"훅 additionalContext 길이 합계 {context_length(rows)}자 / 답변: {answer(run)}")


def judge_e02(run):
    rows = within(raw_hooks(run["session"]), run, 1)
    blocks = stop_blocks(rows)
    stale = any('"route_binding": "stale"' in r["stdout"] for r in rows)
    most = max(codes(blocks).values()) if blocks else 0
    text = R.last_text(run)
    run["err"] = {"blocks": [b["reason"] for b in blocks], "stale_seen": stale, "same_request_max": most,
                  "first_turn_blocks": len(stop_blocks(within(raw_hooks(run["session"]), run, 0)))}
    verdict = [(FAIL if stale else REVIEW) if blocks else PASS, FAIL if blocks and not has_korean(blocks) else PASS,
               FAIL if most > 2 else PASS]
    return verdict, (f"둘째 입력 뒤 {block_text(blocks)} / 둘째 입력 뒤 훅 출력에 route_binding stale {'있음' if stale else '없음'} / "
                     f"같은 코드의 막힘 최다 {most}회 / 첫 입력의 Stop 막힘 {run['err']['first_turn_blocks']}회 / "
                     f"답에 3 {'있음' if re.search(r'(?<![0-9])3(?![0-9])|세 개|셋', text) else '없음'} / 답변: {answer(run)}")


def judge_e03(run):
    rows = raw_hooks(run["session"])
    stopped = moment(run["turns"][0]["ended_at"])
    after = [r for r in rows if r["at"] and stopped and r["at"] >= stopped]
    blocks = stop_blocks(rows)
    prompt_blocks = [r for r in after if r["event"] == "UserPromptSubmit" and r["decision"] == "block"]
    route_calls = [c for t in run["turns"][1:] for c in t["calls"]
                   if "response_route.py" in json.dumps(c["input"], ensure_ascii=False) and "--help" not in json.dumps(c["input"])]
    rejected = [c for c in route_calls if c["is_error"] or re.search(r'"status":\s*"(?!ready)', str(c["result"]))]
    unclear = [c for c in route_calls if c not in rejected and '"status": "ready"' not in str(c["result"])]
    most = max(codes(blocks).values()) if blocks else 0
    run["err"] = {"blocks": [b["reason"] for b in blocks], "prompt_blocks": [r["reason"] for r in prompt_blocks],
                  "route_calls": len(route_calls), "route_rejected": [str(c["result"])[:600] for c in rejected],
                  "route_unclear": [str(c["result"])[:300] for c in unclear], "same_request_max": most,
                  "turn_stop_blocks": [len(stop_blocks(within(rows, run, i))) for i in range(len(run["turns"]))]}
    verdict = [FAIL if prompt_blocks or rejected else PASS, FAIL if most > 3 else PASS,
               FAIL if blocks and not has_korean(blocks) else PASS]
    return verdict, (f"중단 전 내용이 돌아온 py 파일 {run['py_returned']}개. 중단 뒤 UserPromptSubmit 막힘 {len(prompt_blocks)}회, "
                     f"경로 등록 호출 {len(route_calls)}회 중 거부 {len(rejected)}회(결과 확인 불가 {len(unclear)}회) / {block_text(blocks)} / "
                     f"같은 코드의 Stop 막힘 최다 {most}회, 입력별 Stop 막힘 {run['err']['turn_stop_blocks']} / "
                     f"'아무 질문 2번'은 \"{ANY_Q[0]}\" \"{ANY_Q[1]}\"로 넣음 / 마지막 답변: {answer(run)}")


def judge_e04(run):
    rows = raw_hooks(run["session"])
    stops = [r for r in rows if r["event"] == "Stop"]
    blocks = stop_blocks(rows)
    notices = [r for r in stops if r["hook"] == "completion" and (r["reason"] or r["system"])]
    coded = [r["reason"] or r["system"] for r in notices if code_of(r["reason"] or r["system"])]
    twice = [r for r in stops if r["reason"].strip() and r["system"].strip()
             and (code_of(r["reason"]) == code_of(r["system"]) or r["system"].strip()[:80] in r["reason"] or r["reason"].strip()[:80] in r["system"])]
    guidance = "\n".join(r["reason"] + "\n" + r["system"] + "\n" + r["context"] for r in rows)
    bad = sorted({m.group(0).strip(" `;&|(\n") for m in NOT_WINDOWS.finditer(guidance)})
    content = run.get("sandbox")
    seen = Counter(code_of(text) for text in coded)
    run["err"] = {"blocks": [b["reason"] for b in blocks], "codes": dict(seen), "notices": coded[:6], "twice": len(twice),
                  "not_windows": bad, "stop_seconds": [[r["hook"], r["seconds"]] for r in stops], "hello": content}
    verdict = [FAIL if coded and not any(KOREAN.search(text) for text in coded) else PASS, FAIL if twice else PASS, FAIL if bad else PASS]
    longest = max([r["seconds"] for r in stops] or [0])
    return verdict, (f"Stop 훅이 낸 사유 코드 {', '.join(f'{k} {v}회' for k, v in seen.items()) or '없음'}, 그 메시지에 한글 "
                     f"{'있음' if any(KOREAN.search(text) for text in coded) else '없음'} / systemMessage와 reason에 같은 안내가 함께 나온 Stop 훅 {len(twice)}회 / "
                     f"Windows에서 그대로 안 되는 명령 형태 {bad or '없음'} / {block_text(blocks)} / "
                     f"Stop 훅 {len(stops)}회, 한 번에 최장 {longest:.2f}초, 합계 {sum(r['seconds'] for r in stops):.2f}초 / "
                     f"test-sandbox/hello.txt 내용 {content!r} / 답변: {answer(run)}")


def judge_e05(run):
    rows = within(raw_hooks(run["session"]), run, 1)
    blocks = stop_blocks(rows)
    shown = [r for r in rows if r["visible"] != "hide" and LEAK.search(r["surface"])]
    text = R.last_text(run)
    in_answer = sorted(set(m.group(0) for m in LEAK.finditer(text)))
    switched = run.get("visibility_after") == "minimal" and run["turns"][0]["result"] == "success"
    run["err"] = {"visibility_after": run.get("visibility_after"), "blocks": [b["reason"] for b in blocks],
                  "surface_leaks": [[r["event"], r["hook"], r["visible"], r["surface"][:400]] for r in shown],
                  "answer_leaks": in_answer, "context_length": context_length(rows),
                  "visible_counts": dict(Counter(f"{r['event']}·{r['hook']}·{r['visible']}" for r in rows))}
    verdict = [PASS if switched else FAIL, FAIL if shown or in_answer else PASS]
    return verdict, (f"/visibility 뒤 설정 값 {run.get('visibility_after')} / 둘째 입력에서 숨기지 않은 훅 출력에 내부 사유 코드·원장 경로·훅 진단이 있는 것 {len(shown)}건"
                     f"({', '.join(sorted({r['hook'] + ' ' + str(r['visible']) for r in shown})) or '없음'}), 답변 글에 나온 내부 용어 {in_answer or '없음'} / "
                     f"둘째 입력 {block_text(blocks)} / 둘째 입력의 훅 additionalContext 길이 합계 {context_length(rows)}자(관찰값) / 답변: {answer(run)}")


def profile():
    try:
        return json.loads((GA_HOME / "config.json").read_text(encoding="utf-8"))["agent_visibility"]["profile"]
    except (OSError, ValueError, KeyError):
        return None


def set_profile(name):
    subprocess.run([sys.executable, str(VIS_CLI), name], capture_output=True, text=True, timeout=60)
    return profile()


def clear_sandbox(cwd):
    target = (cwd / "test-sandbox").resolve()
    if target.parent != cwd.resolve() or target.name != "test-sandbox":
        raise SystemExit(f"지우려는 곳이 test-sandbox가 아닙니다: {target}")
    if target.exists():
        shutil.rmtree(target)


def sandbox_hello(cwd):
    path = cwd / "test-sandbox" / "hello.txt"
    return path.read_bytes().decode("utf-8", errors="replace") if path.exists() else None


def case(cid, prompts, conditions, judge, expected, **extra):
    spec = R.case(cid, prompts, conditions, judge, expected)
    spec["shown"] = " → ".join(prompts)
    spec.update(extra)
    return spec


CASES = {c["id"]: c for c in [
    case("오류안내-01", [README_Q],
         ["Stop 훅이 답을 막았다.", "막힘 메시지에 사유 코드만 있고 할 일이 쉬운 말로 없다.", "모니터 5번 카드가 '해설 미등록'이다."],
         judge_e01, "제목 \"테스트용 문서\"를 답하고 Stop 훅에 막히지 않고 끝난다."),
    case("오류안내-02", [README_Q, "그 파일에 '## '로 시작하는 제목이 몇 개 있는지 세어줘."],
         ["새 입력 뒤 경로가 stale이 되어 Stop이 막았다.", "메시지만 보고 경로를 다시 등록해야 한다는 원인을 알 수 없다.", "같은 요구가 2번 넘게 반복됐다."],
         judge_e02, "둘째 입력에 3이라고 답하고 Stop 훅에 막히지 않고 끝난다."),
    case("오류안내-03", ["test-fixture/py 폴더의 .py 파일을 하나씩 열어서 각 파일 역할을 한 줄씩 정리해줘.", "아니, alpha.py 하나만 해줘."] + ANY_Q,
         ["멈춘 뒤 입력이 계속 막히거나 경로 등록이 거부됐다.", "Stop 훅이 같은 요구를 3번 넘게 반복했다.", "메시지만 보고 원인(처리되지 않은 입력 대기열)을 알 수 없다."],
         judge_e03, "멈춘 뒤의 입력이 막히지 않고 차례로 처리된다.", interrupt=3),
    case("오류안내-04", ["test-sandbox 폴더에 hello.txt를 만들고 내용을 hello 한 단어로 써줘. 완료 조건은 파일이 있고 내용이 정확히 hello인 것이다."],
         ["사유 코드(예: core-assessment-incompatible, criterion-unbound)에 원인과 할 일이 쉬운 말로 없다.", "같은 안내가 두 번 나왔다(systemMessage와 reason).",
          "안내 명령이 Windows에서 그대로 실행되지 않는다(예: env KEY=… python3)."],
         judge_e04, "test-sandbox/hello.txt를 만들고 내용이 hello인 것을 확인한 뒤 끝난다.", clear="test-sandbox"),
    case("오류안내-05", ["/visibility minimal", README_Q],
         ["/visibility 전환이 실패했다.", "minimal 설정인데 사용자 화면에 내부 사유 코드·원장 경로·훅 진단 정보가 노출됐다."],
         judge_e05, "minimal로 바뀌고, 제목을 답하는 동안 내부 사유 코드·원장 경로·훅 진단이 화면에 나오지 않는다.", visibility=True),
]}
