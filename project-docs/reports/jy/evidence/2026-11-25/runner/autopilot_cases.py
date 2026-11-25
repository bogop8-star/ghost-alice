"""Autopilot 연속 실행 사례. 작업 A와 B를 Autopilot 후속 계획에 등록하고, A가 끝난 뒤 Autopilot이 B를 넘겨주는지 본다.

훅 켬 전용이다. 출력은 test-output/autopilot/ 아래다.
규약: ghost-alice-autopilot/addons/autopilot-mode/skill/references/continuation.md
"""
import json
import os
import re

import cli_runner as R

PASS, FAIL = R.PASS, R.FAIL
OUT = "test-output/autopilot"
HOOK_LOGS = os.path.expanduser("~/.ghost-alice/session-logs/claude")

PROMPT = (
    "작업 A: test-output/autopilot/note.txt에 done을 쓰고, 파일 생성 완료를 기록한다. "
    "작업 B: A의 완료 기록이 적용된 뒤 note.txt를 다시 읽는다. 내용이 done이면 test-output/autopilot/verified.txt에 PASS를 쓴다. "
    "작업 A와 B를 모두 승인합니다. 실행 전에 두 작업을 Autopilot 후속 계획에 등록하고, B는 A가 완료되어야 실행할 수 있도록 설정해 주세요. "
    "계획이 등록되면 A만 시작하세요. B는 Autopilot이 다음 작업으로 넘겨준 뒤에 실행하세요."
)

CONDITIONS = [
    "계획 등록 단계에서 실패했다(Autopilot 후속 계획이 admitted로 등록되지 않았다).",
    "후속 작업 선택에 실패했다(A가 끝났는데 Autopilot이 B를 dispatched로 기록하지 않았다).",
    "전달 또는 실행에 실패했다(B를 넘겼는데 verified.txt가 PASS로 만들어지지 않았다).",
    "B를 넘긴 기록 없이 verified.txt가 만들어졌다(모델이 두 작업을 스스로 처리했다).",
]

ADMITTED = re.compile(r'"status"\s*:\s*"admitted"')
WROTE_RESULT = re.compile(r"verified=\[PASS\]|wrote PASS")


def _json(text):
    try:
        value = json.loads(text or "")
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def stop_hooks(run):
    """Stop adapter-autopilot-mode-continue 훅의 출력 원문.

    cli_runner 의 ga_hooks 는 stdout 을 3000자에서 자른다. 이 훅의 출력은 4000자를 넘고 continuation 이 뒤쪽에 있어서,
    잘리지 않은 훅 기록 파일에서 직접 읽는다.
    """
    path = os.path.join(HOOK_LOGS, str(run.get("session")), "strict-hook-output.jsonl")
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                row = _json(line)
                if row.get("event") == "Stop" and row.get("hook_id") == "adapter-autopilot-mode-continue":
                    rows.append({"ts": row.get("ts"), "stdout": row.get("stdout")})
    return rows


def dispatches(run):
    """Stop 훅이 남긴 continuation 기록."""
    found = []
    for hook in stop_hooks(run):
        continuation = _json(hook.get("stdout")).get("continuation")
        if isinstance(continuation, dict):
            found.append({"at": hook.get("ts"), "status": continuation.get("status"), "task_id": continuation.get("task_id"),
                          "plan_id": continuation.get("plan_id")})
    return found


def recordings(run):
    states = []
    for hook in stop_hooks(run):
        recording = _json(hook.get("stdout")).get("completion_recording") or {}
        units = ",".join(str(u.get("work_unit_id")) + "=" + str(u.get("status")) for u in recording.get("units") or [])
        states.append(str(recording.get("status")) + (f"({recording.get('reason')})" if recording.get("reason") else "")
                      + (f"[{units}]" if units else ""))
    return states


def written_at(run, filename):
    """그 파일을 실제로 쓴 첫 도구 호출의 시각. 계획 글 안에 파일 이름이 나오는 것만으로는 세지 않는다."""
    redirect = re.compile(r">\s*[\"']?\S*" + re.escape(filename))
    for call in R.all_calls(run):
        data = call["input"] if isinstance(call["input"], dict) else {}
        target = str(data.get("file_path") or "").replace("\\", "/")
        command = str(data.get("command") or "")
        result = str(call.get("result") or "")
        if call["name"] in R.WRITE_TOOLS and target.endswith("/" + filename):
            return call.get("at")
        if redirect.search(command) or (filename in command and WROTE_RESULT.search(result)):
            return call.get("at")
    return None


def judge_a01(run):
    note = run["final_files"].get("test-output\\autopilot\\note.txt")
    verified = run["final_files"].get("test-output\\autopilot\\verified.txt")
    sent = dispatches(run)
    dispatched = [d for d in sent if d["status"] == "dispatched"]
    # 넘김 기록에 plan_id 가 있으면 그 계획은 등록된 것이다. 등록 스크립트를 파일로 써서 돌린 회차도 이것으로 잡는다.
    admitted = any(d.get("plan_id") for d in sent) or any(ADMITTED.search(str(c.get("result") or "")) for c in R.all_calls(run))
    a_done = (note or "").strip() == "done"
    b_done = (verified or "").strip() == "PASS"
    first_dispatch = min((d["at"] for d in dispatched if d["at"]), default=None)
    verified_at = written_at(run, "verified.txt")
    before_dispatch = b_done and (not dispatched or bool(verified_at and first_dispatch and verified_at[:19] < first_dispatch[:19]))
    verdict = [PASS if admitted else FAIL,
               PASS if dispatched else FAIL,
               PASS if (b_done and dispatched) else FAIL,
               FAIL if before_dispatch else PASS]
    if not admitted:
        stage = "등록 단계에서 멈춤"
    elif not a_done:
        stage = "계획은 등록됐지만 A가 끝나지 않음"
    elif not dispatched:
        stage = "A는 끝났지만 Autopilot이 B를 넘기지 않음(후속 작업 선택)"
    elif not b_done:
        stage = "B를 넘겼지만 verified.txt가 PASS가 아님(전달 또는 실행)"
    elif before_dispatch:
        stage = "B를 넘기기 전에 verified.txt가 만들어짐"
    else:
        stage = "등록 → A 완료 기록 적용 → B 넘김 → B 실행까지 감"
    run["err"] = {"stage": stage, "admitted": admitted, "dispatches": sent, "recordings": recordings(run), "note": note,
                  "verified": verified, "verified_written_at": verified_at, "first_dispatch_at": first_dispatch}
    return verdict, (f"{stage} / 계획 등록 {'admitted' if admitted else '안 됨'} / note.txt {note!r} / "
                     f"Autopilot continuation 기록 {[(d['status'], d['task_id']) for d in sent] or '없음'} / "
                     f"B를 넘긴 시각 {first_dispatch}, verified.txt를 쓴 시각 {verified_at}, verified.txt {verified!r} / "
                     f"완료 기록 상태 {recordings(run)} / 답변: {R.last_text(run).strip()[-200:]}")


def case(cid, prompts, judge, expected, **extra):
    spec = R.case(cid, prompts, CONDITIONS, judge, expected, clear=OUT)
    spec["shown"] = " → ".join(prompts)
    spec.update(extra)
    return spec


CASES = {c["id"]: c for c in [
    case("연속실행-01", [PROMPT], judge_a01,
         "계획 등록 → A 완료 기록 적용 → Autopilot이 B를 dispatched로 기록 → B가 note.txt를 읽고 verified.txt에 PASS를 쓴다."),
]}
