"""터미널에서 대화형 claude 를 띄워 Ghost-ALICE 테스트 사례를 돌리고, 판정해서 모니터에 저장한다.

claude -p 로 넣은 입력은 출처가 sdk 로 찍혀 Ghost-ALICE 가 사람 입력으로 확정하지 않는다.
그래서 claude 를 대화형으로 띄우고, 둘째 입력과 Esc 는 이 콘솔의 입력 버퍼에 키 이벤트로 써 넣는다.
사례 정의와 판정 함수는 cli_runner.py 것을 그대로 쓴다. 반드시 진짜 터미널 창에서 실행한다.

    python tui_runner.py --env off --group all --runs 5 --wait
    python tui_runner.py --env on --cases 시간비용-01 --runs 1 --dry     # 판정을 저장하지 않는다
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_runner as R  # noqa: E402
import error_cases as E  # noqa: E402
import trap_cases as TR  # noqa: E402
import autopilot_cases as AP  # noqa: E402

CLAUDE = R.CLAUDE   # PATH의 claude. 다른 것을 쓰려면 GA_CLAUDE에 경로를 넣는다
VERSION = (subprocess.run([CLAUDE, "--version"], capture_output=True, text=True).stdout.split() or ["unknown"])[0]   # JY 시험은 2.1.310
ENVS = {"off": R.BASE / "ghost-alice-nohook" / "off-test", "on": R.BASE / "ghost-alice-agent" / "ghost-alice"}
SUFFIX = "-터미널"
PHASE = "before"          # --phase after 로 바꾸면 수정 후 구간으로 저장한다
PY_NAMES = ("alpha.py", "beta.py", "gamma.py", "delta.py", "epsilon.py")
DENIED = re.compile(r"permission|denied|not allowed|haven't granted|requires approval", re.I)

CASES = {cid: dict(spec) for cid, spec in R.CASES.items()}
# 원래 문장으로는 터미널에서 다섯 파일을 한꺼번에 읽어 중단 시점이 생기지 않는다.
CASES["행동확인-03-지시변경"]["prompts"] = [
    "test-fixture/py 폴더의 py 파일 5개를 하나씩 열어서 역할을 각각 한 줄로 정리해 줘. 파일은 수정하지 마.",
    "아니, alpha.py만 해 줘."]
CASES.update(E.CASES)   # 오류안내-01~05 (훅 켬 전용)
CASES.update(TR.CASES)  # 검증-01~03
CASES.update(AP.CASES)  # 연속실행-01 (훅 켬 전용)
CHANGED_INPUT = {"행동확인-03-지시변경": "터미널에서는 첫 입력을 '하나씩 열어서' 문장으로 바꿔 넣음"}


# ---------- 키 입력 ----------
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateFileW.restype = wintypes.HANDLE
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
k32.WriteConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
k32.FlushConsoleInputBuffer.argtypes = [wintypes.HANDLE]
k32.CloseHandle.argtypes = [wintypes.HANDLE]


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD), ("wVirtualKeyCode", wintypes.WORD),
                ("wVirtualScanCode", wintypes.WORD), ("UnicodeChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]


class INPUT_RECORD(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("pad", ctypes.c_byte * 16)]
    _fields_ = [("EventType", wintypes.WORD), ("Event", _U)]


def console_input():
    handle = k32.CreateFileW("CONIN$", 0xC0000000, 3, None, 3, 0, None)
    if not handle or handle == wintypes.HANDLE(-1).value:
        raise SystemExit("콘솔 입력을 열 수 없습니다. 터미널 창에서 실행해야 합니다.")
    return handle


def send_keys(text):
    """이 콘솔에서 도는 claude 창에 글자를 키 입력으로 넣는다. Enter 는 '\\r', Esc 는 '\\x1b'."""
    handle = console_input()
    for ch in text:
        vk = {"\r": 0x0D, "\x1b": 0x1B}.get(ch, 0)
        for down in (True, False):
            rec = INPUT_RECORD()
            rec.EventType = 1
            rec.Event.KeyEvent = KEY_EVENT_RECORD(down, 1, vk, 0, ch, 0)
            written = wintypes.DWORD()
            if not k32.WriteConsoleInputW(handle, ctypes.byref(rec), 1, ctypes.byref(written)):
                raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.02)
    k32.CloseHandle(handle)


def flush_input():
    handle = console_input()
    k32.FlushConsoleInputBuffer(handle)
    k32.CloseHandle(handle)


# ---------- 대화 기록 읽기 ----------
def read_rows(path):
    rows = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def parse(rows):
    """대화 기록을 사람 입력 단위의 턴으로 나눈다. 턴 끝은 turn_duration 행, 중단은 interrupted 행으로 안다."""
    turns, by_id = [], {}
    meta = {"session": None, "model": None, "permission": None, "versions": set()}
    for row in rows:
        kind = row.get("type")
        msg = row.get("message") if isinstance(row.get("message"), dict) else {}
        content, stamp = msg.get("content"), row.get("timestamp")
        meta["session"] = meta["session"] or row.get("sessionId")
        if row.get("version"):
            meta["versions"].add(row["version"])
        if kind == "user" and isinstance(content, str):
            if row.get("promptSource") == "typed" or row.get("turnOrigin") == "human":
                meta["permission"] = row.get("permissionMode") or meta["permission"]
                turns.append({"prompt": content, "sent_at": stamp, "calls": [], "texts": [], "result": None, "ended_at": None,
                              "stop_feedback": 0, "py_names": [], "py_asked": [],
                              "origin": [row.get("promptSource"), row.get("turnOrigin")]})
            elif turns and content.startswith("Stop hook feedback"):
                turns[-1]["stop_feedback"] += 1
            continue
        ending = (row.get("promptSubmitEnding") or {}).get("ending") or {} if kind == "system" else {}
        if ending.get("kind") == "blocked_by_hook":
            # UserPromptSubmit 훅이 입력을 받아 처리하고 끝낸 경우(/visibility 등). user 행도 turn_duration 행도 남지 않는다.
            original = str(row.get("content") or "").rsplit("Original prompt: ", 1)[-1].strip()
            turns.append({"prompt": original, "sent_at": stamp, "calls": [], "texts": [], "result": "success", "ended_at": stamp,
                          "stop_feedback": 0, "py_names": [], "py_asked": [], "origin": ["blocked_by_hook", None],
                          "hook_reason": ending.get("reason")})
            continue
        if not turns:
            continue
        turn = turns[-1]
        if kind == "assistant":
            meta["model"] = msg.get("model") or meta["model"]
            for part in content if isinstance(content, list) else []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    call = {"name": part.get("name"), "input": part.get("input"), "id": part.get("id"), "at": stamp,
                            "result": None, "is_error": None}
                    turn["calls"].append(call)
                    by_id[part.get("id")] = call
                    if turn["result"] is None:
                        asked = json.dumps(call["input"], ensure_ascii=False)
                        turn["py_asked"] += [n for n in PY_NAMES if n in asked and n not in turn["py_asked"]]
                elif part.get("type") == "text" and str(part.get("text") or "").strip():
                    turn["texts"].append(part["text"])
        elif kind == "user" and isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_result":
                    call = by_id.get(part.get("tool_use_id"))
                    if not call:
                        continue
                    body = part.get("content")
                    call["result"] = (R.text_blocks(body) or str(body))[:4000]
                    call["is_error"] = bool(part.get("is_error"))
                    if not call["is_error"] and turn["result"] is None:
                        asked = json.dumps(call["input"], ensure_ascii=False)
                        turn["py_names"] += [n for n in PY_NAMES if n in asked and n not in turn["py_names"]]
                elif part.get("type") == "text" and str(part.get("text") or "").startswith("[Request interrupted by user"):
                    turn["result"], turn["ended_at"] = "interrupted", stamp
        elif kind == "system" and row.get("subtype") == "turn_duration" and turn["result"] is None:
            turn["result"], turn["ended_at"] = "success", stamp
    return turns, meta


# ---------- 실행 ----------
def say(text=""):
    print(text, flush=True)


def clear_output(cwd, relative):
    """출력 폴더를 비운다. 다른 프로세스가 잡고 있어 안 지워지는 빈 폴더는 그대로 둔다(파일은 모두 지운다)."""
    if relative == "test-sandbox":
        E.clear_sandbox(cwd)
        return
    try:
        R.clear_output(cwd, relative)
        return
    except PermissionError:
        pass
    target = (cwd / relative).resolve()
    for path in sorted(target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            path.rmdir() if path.is_dir() else path.unlink()
        except OSError:
            if path.is_file():
                raise


def same_input(recorded, typed):
    """대화 기록의 입력이 넣은 입력과 같은지. /명령은 기록에 <command-name> 형태로 남는다."""
    if typed.startswith("/"):
        return recorded == typed or f"<command-name>{typed.split()[0]}</command-name>" in recorded
    return recorded == typed


def execute(spec, env, cwd, permission):
    """한 회차를 돌린다. 첫 입력은 인수로, 둘째 입력과 Esc 는 키 입력으로 넣는다."""
    prompts, need = list(spec["prompts"]), spec["interrupt"]
    inherited = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_PREVIEW", "GHOST_ALICE_")
    clean_env = {k: v for k, v in os.environ.items() if not k.upper().startswith(inherited)}
    clean_env["DISABLE_AUTOUPDATER"] = "1"
    project = R.PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    flush_input()
    began = time.time()
    proc = subprocess.Popen(executable=CLAUDE, args=["claude", "--model", R.MODEL, "--permission-mode", permission, prompts[0]],
                            cwd=str(cwd), env=clean_env)

    def current():
        best = None
        for path in project.glob("*.jsonl"):
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_ctime < began - 2:
                continue
            turns, meta = parse(read_rows(path))
            if turns and same_input(turns[0]["prompt"], prompts[0]) and (best is None or stat.st_mtime > best[0]):
                best = (stat.st_mtime, path, turns, meta)
        return best

    index, interrupted_at, files_by_turn, waiting_since = 0, None, {}, time.time()
    run_between = {}
    turns, meta, path = [], {"session": None, "model": None, "permission": None, "versions": set()}, None
    deadline = began + 900
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.1)
        got = current()
        if not got:
            if time.time() - waiting_since > 90:
                break
            continue
        _, path, turns, meta = got
        if len(turns) <= index:                      # 넣은 입력이 기록에 나타나기를 기다린다
            if time.time() - waiting_since > 90:
                break
            continue
        turn = turns[index]
        # 훅 끔에서는 읽기가 빨라 결과를 기다리면 다섯 개가 다 돌아온다. 그래서 py 파일 읽기 요청이 보이면 바로 넣는다.
        # 훅 켬에서는 도구마다 훅이 돌아 느리므로 첫 결과가 돌아온 뒤에 넣는다.
        ready = turn["py_asked"] if env == "off" else turn["py_names"]
        if need and index == 0 and interrupted_at is None and turn["result"] is None and ready:
            send_keys("\x1b")
            interrupted_at = datetime.now().isoformat()
            continue
        if turn["result"] is None:
            continue
        time.sleep(2)
        files_by_turn[index] = (R.snapshot(cwd), bool(spec["clear"] != "test-output" and (cwd / spec["clear"]).exists()))
        if index + 1 >= len(prompts):
            break
        if index in (spec.get("between") or {}):          # 입력 사이에 파일을 바꾸는 사례
            run_between[index] = spec["between"][index](cwd)
        time.sleep(4)
        send_keys(prompts[index + 1])
        time.sleep(0.6)
        send_keys("\r")
        index, waiting_since = index + 1, time.time()

    if proc.poll() is None:
        send_keys("/exit")
        time.sleep(1)
        send_keys("\r")
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    flush_input()
    if path:
        turns, meta = parse(read_rows(path))

    run = {"env": env, "cwd": cwd, "session": meta["session"] or (path.stem if path else None), "turns": [],
           "py_returned": 0, "py_names": [], "interrupted_at": interrupted_at, "hooks": [], "hook_counts": {},
           "model": meta["model"], "permission": meta["permission"], "versions": sorted(meta["versions"]),
           "exit_code": proc.returncode, "transcript": str(path) if path else None, "between": run_between}
    for number, turn in enumerate(turns[:len(prompts)]):
        files, out_dir = files_by_turn.get(number, ({}, False))
        denials = [{"tool": c["name"], "text": str(c["result"])[:300]} for c in turn["calls"]
                   if c["is_error"] and DENIED.search(str(c["result"]))]
        # Ghost-ALICE 가 답을 막았다 풀면 마지막 글은 "경로를 등록했다"는 말뿐이고 답은 앞 글에 있다.
        # 그래서 판정에는 그 턴의 글 전체를 하나로 이어서 넘긴다. 나뉜 원문은 texts_raw 에 둔다.
        joined = ["\n\n".join(turn["texts"])] if turn["texts"] else []
        run["turns"].append({"prompt": turn["prompt"], "sent_at": turn["sent_at"], "calls": turn["calls"], "texts": joined,
                             "texts_raw": turn["texts"],
                             "result": turn["result"], "files": files, "out_dir_exists": out_dir, "denials": denials,
                             "ended_at": turn["ended_at"], "stop_feedback": turn["stop_feedback"], "origin": turn["origin"]})
    if need and turns:
        run["py_names"] = list(turns[0]["py_names"])
        run["py_returned"] = len(run["py_names"])
    return run


def one_attempt(spec, env, number, attempt, args):
    cwd = ENVS[env]
    case_id = spec["id"] + SUFFIX
    clear_output(cwd, spec["clear"])
    if spec["id"] in TR.CASES:
        TR.setup(cwd)
    before = R.tree_hash(cwd / "test-fixture")
    if spec.get("visibility"):
        E.set_profile("dynamic")
    try:
        run = execute(spec, env, cwd, args.permission)
        run["visibility_after"] = E.profile()
    finally:
        if spec.get("visibility"):
            E.set_profile("dynamic")
    run["sandbox"] = E.sandbox_hello(cwd)
    run["fixture_before"], run["fixture_after"] = before, R.tree_hash(cwd / "test-fixture")
    run["final_files"] = R.snapshot(cwd)
    run["ga"] = R.ga_hooks(run["session"]) if run["session"] else []

    invalid = None
    if not run["session"] or not run["turns"] or run["turns"][-1]["result"] is None:
        invalid = "실행이 끝까지 가지 못함"
    elif len(run["turns"]) < len(spec["prompts"]):
        invalid = "입력을 모두 넣지 못함"
    elif any(t["origin"] != ["typed", "human"] and not (t["origin"][1] == "human" and t["prompt"].startswith("<command-"))
             and not (t["origin"][0] == "blocked_by_hook" and t["prompt"].startswith("/"))
             for t in run["turns"]):
        invalid = f"입력이 사람 입력으로 찍히지 않음: {[t['origin'] for t in run['turns']]}"
    elif run["versions"] != [VERSION]:
        invalid = f"claude 버전이 {VERSION}이 아님: {run['versions']}"
    elif env == "on" and not run["ga"]:
        invalid = "훅 켠 폴더인데 Ghost-ALICE 훅 기록이 없음"
    elif env == "off" and run["ga"]:
        invalid = "훅 끈 폴더인데 Ghost-ALICE 훅 기록이 있음"
    elif spec["interrupt"] and not (run["turns"][0]["result"] == "interrupted" and 1 <= run["py_returned"] <= 4):
        invalid = (f"중단 조건 불성립: 첫 턴 결과 {run['turns'][0]['result']}, "
                   f"중단 전 내용이 돌아온 py 파일 {run['py_returned']}개")

    metrics = R.monitor_metrics(run["session"], len(run["turns"])) if run["session"] else None
    total = R.totals(metrics)
    run["seconds"] = total["seconds"]
    if env == "off":
        run["ga"] = []
    verdict_list, note = ([], invalid) if invalid else spec["judge"](run)
    if not invalid and env == "on" and "Ghost-ALICE 훅" not in note:
        note += " / " + R.ga_text(run)
    if spec["id"] in CHANGED_INPUT:
        note += " / " + CHANGED_INPUT[spec["id"]]
    status = "판정 불가" if invalid else ("검토 필요" if R.REVIEW in verdict_list else ("실패" if R.FAIL in verdict_list else "통과"))
    denials = [d for t in run["turns"] for d in t["denials"]]
    note_full = (f"[터미널 대화형 실행 · {R.ENV_LABEL[env]} · {phase_label()} · {number}회차 · claude {VERSION}] {note}"
                 + (f" / 권한 거부로 보이는 도구 오류 {len(denials)}건" if denials else ""))

    saved = None
    if status in ("통과", "실패") and not args.dry:
        verdict = {c: v for c, v in zip(spec["conditions"], verdict_list)}
        if env == "on":
            R.http("GET", "/api", timeout=120)   # 모니터가 이 세션의 훅 기록을 읽어 들이게 한다
        R.http("POST", "/api/case", {"id": case_id, "context": "없음", "prompt": spec.get("shown", spec["prompts"][0]),
                                     "expected": spec["expected"], "conditions": "\n".join(spec["conditions"])})
        reply = R.http("POST", "/api/verdict", {"session": run["session"], "phase": PHASE, "verdict": verdict, "note": note_full,
                                                "messages": R.transcript_messages(run["session"]), "monitor_start": "",
                                                "run_saved_at": "live"})
        saved = datetime.now().isoformat() if reply.get("ok") else None
    clear_output(cwd, spec["clear"])

    record = {"case": case_id, "mode": "tui", "phase": PHASE, "dry": bool(args.dry), "env": env, "cwd": str(cwd), "run": number,
              "attempt": attempt, "status": status,
              "saved_at": saved, "session": run["session"], "model": run["model"], "permission_mode": run["permission"],
              "cli_versions": run["versions"], "conditions": spec["conditions"], "verdict": verdict_list, "note": note_full,
              "turns": run["turns"], "py_returned": run["py_returned"], "py_names": run["py_names"],
              "interrupted_at": run["interrupted_at"], "ga_hooks": run["ga"],
              "fixture_same": run["fixture_before"] == run["fixture_after"], "final_files": run["final_files"],
              "err": run.get("err"), "visibility_after": run.get("visibility_after"), "between": run.get("between"),
              "metrics": metrics, "totals": total, "denials": denials, "transcript": run["transcript"], "exit_code": run["exit_code"]}
    with (R.OUT / "results.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    for number_, turn in enumerate(run["turns"], 1):
        say(f"  [입력 {number_}] {turn['prompt']}")
        say(f"  [도구] {', '.join(c['name'] for c in turn['calls']) or '없음'} · 결과 {turn['result']}")
    for condition, value in zip(spec["conditions"], verdict_list):
        say(f"  [조건] {'걸리지 않음' if value == R.PASS else ('걸림' if value == R.FAIL else '검토 필요')} · {condition}")
    say(f"  [근거] {note}")
    say(f"  [수치] 세션 {run['session']} · 턴 {total['turns']} · {total['seconds']}초 · 토큰 {total['tokens']:,} · "
        f"${total['cost_usd']:.3f} · 도구 {total['tool_calls']} · Ghost-ALICE 훅 {len(run['ga'])} · "
        f"Stop 막힘 {sum(1 for row in run['ga'] if row['block'])}")
    say(f"  [판정] {status}" + (" · 모니터에 저장됨" if saved else (" · 저장 안 함(시험)" if args.dry else " · 저장 안 함")))
    return status


def phase_label():
    return "수정 후" if PHASE == "after" else "수정 전"


def main():
    global PHASE
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["off", "on"], required=True)
    ap.add_argument("--cases", help="쉼표로 구분한 사례 ID. 앞부분만 적어도 된다(예: 행동확인-01)")
    ap.add_argument("--group", choices=["basic", "seq", "all", "err", "trap", "auto"],
                    help="basic=행동확인·시간비용, seq=연속작업, all=둘 다, err=오류안내(훅 켬 전용)")
    ap.add_argument("--wait", type=int, nargs="?", const=60, default=0, help="이 초만큼 센 뒤 시작한다(값 없으면 60초)")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--first", type=int, default=1, help="시작 회차 번호")
    ap.add_argument("--permission", default="auto")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--model", help="모델 ID. 주지 않으면 기본 모델")
    ap.add_argument("--phase", choices=["before", "after"], default="before", help="after=수정 후 구간")
    args = ap.parse_args()
    PHASE = args.phase
    if args.model:
        R.MODEL = args.model
    (R.OUT / "logs").mkdir(parents=True, exist_ok=True)
    groups = {"basic": ("행동확인", "시간비용"), "seq": ("연속작업",), "all": ("행동확인", "시간비용", "연속작업"),
              "err": ("오류안내",), "trap": ("검증",), "auto": ("연속실행",)}
    chosen = [c for cid, c in CASES.items() if args.group and cid.startswith(groups[args.group])]
    for name in (args.cases or "").split(","):
        if not name.strip():
            continue
        name = re.sub(r"^err(\d+)$", r"오류안내-\1", name.strip())
        name = re.sub(r"^trap(\d+)$", r"검증-\1", name)
        name = re.sub(r"^auto(\d+)$", r"연속실행-\1", name)
        name = re.sub(r"^cost(\d+)$", r"시간비용-\1", name)
        name = name     # 터미널에는 한글을 못 넣어 err05 처럼 적는다
        hits = [c for cid, c in CASES.items() if cid.startswith(name.strip())]
        if len(hits) != 1:
            raise SystemExit(f"사례를 {len(hits)}개 찾았습니다: {name}")
        chosen.append(hits[0])
    if not chosen:
        raise SystemExit("--cases 나 --group 이 필요합니다")
    if args.env == "off" and any(c["id"].startswith(("오류안내", "연속실행")) for c in chosen):
        raise SystemExit("오류안내·연속실행 사례는 훅 켬 전용입니다")
    label = R.ENV_LABEL[args.env]
    say(f"Ghost-ALICE 터미널 대화형 테스트 · {label} · {phase_label()} · 사례 {len(chosen)}개 × {args.runs}회 · 폴더 {ENVS[args.env]}")
    for spec in chosen:
        say(f"  {spec['id']}{SUFFIX}")
    if args.wait:
        say()
        for left in range(args.wait, 0, -1):
            print(f"\r{left}초 뒤 시작합니다. 지금 녹화를 누르세요.   ", end="", flush=True)
            time.sleep(1)
        say()
    summary = []
    for spec in chosen:
        for number in range(args.first, args.first + args.runs):
            for attempt in range(1, 4):
                say()
                say("=" * 78)
                say(f"{spec['id']}{SUFFIX} · {label} · {phase_label()} · {number}회차" + (f" (재실행 {attempt})" if attempt > 1 else "")
                    + f" · {datetime.now().strftime('%H:%M:%S')}")
                say("=" * 78)
                status = one_attempt(spec, args.env, number, attempt, args)
                if status != "판정 불가":
                    break
            summary.append((spec["id"], number, status))
    say()
    say("=" * 78)
    say(f"끝 · {label}. 회차별 결과")
    for cid, number, status in summary:
        say(f"  {cid}{SUFFIX} {number}회차: {status}")


if __name__ == "__main__":
    main()
