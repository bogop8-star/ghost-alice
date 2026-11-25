"""훅 끔, 훅 켬(A), 훅 켬(B) 세 조건에서 같은 사례를 터미널 대화형으로 돌리고 판정 자료를 남긴다.

어제의 tui_runner.py 와 같은 방식이다. claude 를 대화형으로 띄우고 입력을 실제 키 입력으로 넣는다.
달라진 것은 조건뿐이다: 훅 끔 / 훅 켬(A, 450e4b3) / 훅 켬(B, 15b6e2b).
A와 B는 앞선 창에서 따로 설치해 둔 폴더(~/ga-test/home-a, home-b)를 쓰고, 실제 설치본은 건드리지 않는다.
코드는 고치지 않는다. 반드시 진짜 터미널 창에서 실행한다.

    python ab_runner.py --cases c01 --wait 30                     # 사례 하나
    python ab_runner.py --list                                    # 사례 목록만 보기(실행 안 함)

결과: ~/ga-test/테스트결과/ab/results.jsonl (한 회차 한 줄), ~/ga-test/테스트결과/ab/runs/<조건>/<사례>/<회차>/ (대화 기록·훅 기록 사본)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tui_runner as T  # noqa: E402  키 입력(send_keys), 대화 기록 읽기(read_rows, parse)를 그대로 쓴다

CLAUDE = T.CLAUDE                      # JY 시험은 CLI 2.1.310
VERSION = T.VERSION
MODEL = "claude-opus-5-5"
EFFORT = "medium"                      # 어제 대화 기록에 찍힌 값과 같다
GA = Path.home() / "ga-test"
KIT = GA / "src" / "team" / "project-docs" / "reports" / "kyu" / "evidence" / "2026-11-24"
WORK = Path("C:/ga-work")            # 윗폴더에 .claude 가 없는 곳. 사용자 폴더 아래에 두면 실제 설정이 딸려 들어온다
OUT = GA / "테스트결과" / "ab"
PY = sys.executable

ARMS = {
    "off": {"label": "훅 끔", "home": GA / "home-off", "core": None},   # 고스트엘리스가 하나도 없는 빈 설정 폴더
    "a": {"label": "훅 켬(A)", "home": GA / "home-a", "core": GA / "src" / "core-a"},
    "b": {"label": "훅 켬(B)", "home": GA / "home-b", "core": GA / "src" / "core-b"},
}
KOREAN = re.compile("[가-힣]")
GATE_CODE = re.compile(r"\[completion-gate\]\s*(?:[A-Z][^:]*: )?([a-z]+(?:-[a-z0-9]+)+):")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
RECORD_SCRIPTS = re.compile(r"session_intent_ledger\.py|response_route\.py|completion_assessment\.py|quick_review\.py")

REPORT_PROMPT = ("output/report.txt를 새로 만들어 줘. 내용은 정확히 세 줄이고 첫째 줄은 alpha, 둘째 줄은 beta, 셋째 줄은 gamma야. "
                 "완료 조건: output/report.txt 에 3줄이 있어야 함. 만든 뒤 다시 읽어서 줄 수를 확인하고 완료를 보고해. 다른 파일은 건드리지 마.")
PS_COMMAND = ("if (Test-Path -LiteralPath .\\README.md) { $p = Resolve-Path -LiteralPath .\\README.md; "
              "@(Get-Content -LiteralPath $p | Where-Object { $_ -ne $null }).Count }")
PLAN_FIRST = ("작업 A: test-output/autopilot/note.txt에 done을 쓰고, 파일 생성 완료를 기록한다. "
              "작업 B: A의 완료 기록이 적용된 뒤 note.txt를 다시 읽어, 내용이 done이면 test-output/autopilot/verified.txt에 PASS를 쓴다. "
              "B는 A가 끝나야 실행된다. 두 작업을 승인한다. 계획에 등록한 뒤 A만 실행하고, A가 끝나면 멈추고 B는 실행하지 마.")

# sessions: 세션마다 입력 목록. 세션이 둘이면 첫 세션을 닫고 같은 폴더에서 새 세션을 연다.
CASES = [
    {"id": "probe", "name": "환경 확인용 질문", "runs": 1, "probe": True,
     "sessions": [["도구는 쓰지 말고 답해. 지금 네 컨텍스트에 들어와 있는 지시문 파일(CLAUDE.md 등)의 경로를 전부 적고, "
                   "쓸 수 있는 스킬 이름을 전부 적어. 없으면 없다고 적어."]]},
    {"id": "c01", "name": "도구 없이 답하는 질문", "runs": 1,
     "sessions": [["파이썬에서 리스트와 튜플의 차이를 한 줄로 알려줘."]]},
    {"id": "c02", "name": "README 제목 한 줄 읽기",
     "sessions": [["README.md를 Read 도구로 열어 맨 위 제목 한 줄만 알려줘. 다른 파일은 열지 말고 파일은 수정하지 마."]]},
    {"id": "c03", "name": "파워셸 명령으로 README 줄 수 세기",
     "sessions": [["아래 명령을 PowerShell 도구로 그대로 한 번 실행하고, 출력된 숫자만 알려줘. 파일은 수정하지 마.\n" + PS_COMMAND]]},
    {"id": "c04", "name": "hello 파일 만들고 다시 읽어 확인",
     "sessions": [["output/hello.txt를 새로 만들고 내용은 hello 한 단어로 해 줘. 완료 조건은 파일이 있고 내용이 정확히 hello인 것이다. "
                   "만든 뒤 다시 읽어서 확인하고 끝났다고 해. 다른 파일은 건드리지 마."]]},
    {"id": "c05", "name": "파일 만들 때 나오는 막힘 문구",
     "sessions": [["test-sandbox/hello.txt를 만들고 내용을 hello 한 단어로 써 줘. 완료 조건은 파일이 있고 내용이 정확히 hello인 것이다."]]},
    {"id": "c06", "name": "완료 조건이 있는 세 줄 파일 만들기", "sessions": [[REPORT_PROMPT]]},
    {"id": "c07", "name": "같은 작업, 장부에 완료 조건을 미리 넣고", "sessions": [[REPORT_PROMPT]], "preinsert": True},
    {"id": "c08", "name": "함정이 있는 매출 합계",
     "sessions": [["data/sales.csv에서 region이 정확히 East인 거래의 amount_usd 합계를 소수점 둘째 자리까지 알려줘. "
                   "괄호로 감싼 금액은 환불(음수)이고, TOTAL 줄은 거래가 아니야. 파일은 수정하지 마."]]},
    {"id": "c09", "name": "함정이 있는 행사 날짜",
     "sessions": [["data/events.csv에서 launch 행사 날짜를 2026-MM-DD 형식으로 알려줘. 파일은 수정하지 마."]]},
    {"id": "c10", "name": "작업 두 개를 후속 계획에 등록만 하기",
     "sessions": [["작업 A: test-output/autopilot/note.txt에 done을 쓴다. 작업 B: A의 완료 기록이 적용된 뒤 note.txt를 다시 읽어, "
                   "내용이 done이면 test-output/autopilot/verified.txt에 PASS를 쓴다. B는 A가 끝나야 실행된다. 두 작업을 승인한다. "
                   "지금은 Autopilot 후속 계획만 등록하고 파일은 만들지 마."]]},
    {"id": "c11", "name": "첫 작업이 끝난 뒤 둘째 작업을 넘겨받아 실행",
     "sessions": [["작업 A: test-output/autopilot/note.txt에 done을 쓰고, 파일 생성 완료를 기록한다. "
                   "작업 B: A의 완료 기록이 적용된 뒤 note.txt를 다시 읽는다. 내용이 done이면 test-output/autopilot/verified.txt에 PASS를 쓴다. "
                   "작업 A와 B를 모두 승인합니다. 실행 전에 두 작업을 Autopilot 후속 계획에 등록하고, B는 A가 완료되어야 실행할 수 있도록 설정해 주세요. "
                   "계획이 등록되면 A만 시작하세요. B는 Autopilot이 다음 작업으로 넘겨준 뒤에 실행하세요."]]},
    {"id": "c12", "name": "첫 작업만 하고 멈춘 뒤, 다음 세션에서 둘째 작업만 실행",
     "sessions": [[PLAN_FIRST], ["같은 Autopilot 계획을 이어서, 넘겨받은 작업 B만 실행해."]]},
]
BY_ID = {c["id"]: c for c in CASES}


def say(text=""):
    print(text, flush=True)


# ---------- 작업 폴더 ----------
def fixture_files():
    """시험 자료: kyu 시험 키트의 testbed/fixture 전체와 testbed2 의 함정 자료 두 개."""
    files = {}
    base = KIT / "testbed" / "fixture"
    for path in sorted(base.rglob("*")):
        if path.is_file():
            rel = path.relative_to(base).as_posix()
            files[rel[:-4] if rel.endswith(".md.txt") else rel] = path.read_bytes()
    for name in ("sales.csv", "events.csv"):
        files["data/" + name] = (KIT / "testbed2" / "fixture" / "data" / name).read_bytes()
    return files


def reset_work(arm):
    """회차마다 작업 폴더를 비우고 시험 자료를 새로 넣는다. ~/ga-test/work/<조건> 밖은 건드리지 않는다."""
    cwd = (WORK / arm).resolve()
    if cwd.parent != WORK.resolve() or cwd.name not in ARMS:
        raise SystemExit(f"작업 폴더가 예상한 곳이 아닙니다: {cwd}")
    cwd.mkdir(parents=True, exist_ok=True)
    for child in cwd.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    for rel, data in fixture_files().items():
        target = cwd / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (cwd / "output").mkdir(exist_ok=True)
    return cwd


def fixture_same(cwd):
    return all((cwd / rel).is_file() and (cwd / rel).read_bytes() == data for rel, data in fixture_files().items())


def snapshot(cwd):
    """시험 자료가 아닌 파일(모델이 만든 것)의 내용과 수정 시각."""
    known, files = set(fixture_files()), {}
    for path in sorted(cwd.rglob("*")):
        if path.is_file():
            rel = path.relative_to(cwd).as_posix()
            if rel not in known:
                files[rel] = {"text": path.read_bytes().decode("utf-8", errors="replace")[:4000], "mtime": path.stat().st_mtime}
    return files


# ---------- 조건별 환경 ----------
def arm_env(arm):
    """claude 에 넘길 환경. 이 스크립트를 띄운 세션의 Claude·Ghost-ALICE 변수는 물려주지 않는다."""
    inherited = ("CLAUDE", "ANTHROPIC", "GHOST_ALICE", "LANGFUSE")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(inherited)}
    env["DISABLE_AUTOUPDATER"] = "1"
    home = ARMS[arm]["home"]
    if home:      # 따로 설치해 둔 폴더를 설정 폴더로 가리킨다. 시험 전용 패치의 스위치는 켜지 않는다.
        env.update(HOME=str(home), USERPROFILE=str(home), CLAUDE_CONFIG_DIR=str(home / ".claude"),
                   GHOST_ALICE_GHOST_ROOT=str(home / ".ghost-alice"))
        env["PATH"] = str(Path(PY).parent) + os.pathsep + env.get("PATH", "")
    return env


def check_environment(arm):
    """돌리기 전에 그 조건의 환경이 맞는지 본다. 문제가 있으면 그 내용을 돌려준다(없으면 빈 목록)."""
    home, problems = ARMS[arm]["home"], []
    config = home / ".claude"
    if not (config / ".credentials.json").exists():
        problems.append(f"로그인이 안 돼 있음: {config}")
    settings = {}
    if (config / "settings.json").exists():
        settings = json.loads((config / "settings.json").read_text(encoding="utf-8"))
    skills = [p.name for p in (config / "skills").iterdir() if p.name != "synced"] if (config / "skills").is_dir() else []   # synced 는 Claude Code가 계정에서 받아 오는 폴더로 고스트엘리스 것이 아니다
    if arm == "off":      # 훅 끔은 고스트엘리스가 하나도 없어야 한다: 지시문, 절차 문서, 훅, 설치 폴더
        if (config / "CLAUDE.md").exists():
            problems.append("지시문 파일 CLAUDE.md가 있음")
        if skills:
            problems.append(f"절차 문서(스킬)가 있음: {skills[:5]}")
        if settings.get("hooks"):
            problems.append("훅이 등록돼 있음")
        if (home / ".ghost-alice").exists():
            problems.append("고스트엘리스 설치 폴더(.ghost-alice)가 있음")
    else:                 # A·B는 그 커밋의 고스트엘리스가 설치돼 있어야 한다
        state = home / ".ghost-alice" / "install-state" / "claude.json"
        head = json.loads(state.read_text(encoding="utf-8")).get("source_head", "") if state.exists() else ""
        want = {"a": "450e4b3", "b": "15b6e2b"}[arm]
        if not head.startswith(want):
            problems.append(f"설치된 커밋이 {want}가 아님: {head[:12] or '설치 기록 없음'}")
        if not settings.get("hooks"):
            problems.append("훅이 등록돼 있지 않음")
    for parent in [WORK / arm, *(WORK / arm).parents]:      # 작업 폴더와 윗폴더에 설정이 있으면 그 내용이 딸려 들어온다
        for name in (".claude", "CLAUDE.md", "CLAUDE.local.md", ".mcp.json"):
            if (parent / name).exists():
                problems.append(f"작업 폴더 윗쪽에 설정이 있음: {parent / name}")
    trusted = False
    if (config / ".claude.json").exists():
        projects = json.loads((config / ".claude.json").read_text(encoding="utf-8")).get("projects", {})
        trusted = bool(projects.get((WORK / arm).as_posix(), {}).get("hasTrustDialogAccepted"))
    if not trusted:
        problems.append(f"작업 폴더 신뢰 표시가 없음: {(WORK / arm).as_posix()}")
    return problems


def projects_dir(arm):
    home = ARMS[arm]["home"]
    return (home / ".claude" / "projects") if home else (Path.home() / ".claude" / "projects")


def hook_log(arm, session):
    home = ARMS[arm]["home"]
    return (home / ".ghost-alice" / "session-logs" / "claude" / str(session) / "strict-hook-output.jsonl") if home else None


def ledger_root(arm):
    core = ARMS[arm]["core"]
    return (core / ".tmp" / "session-intent") if core else None


def core_tool(arm, script, *args):
    """그 조건의 Core 스크립트를 읽기·기록용으로 실행한다. (stdout, stderr, returncode)"""
    core = ARMS[arm]["core"]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CLAUDE", "ANTHROPIC", "GHOST_ALICE", "CODEX"))}
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run([PY, str(core / script), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=120)
    return proc.stdout, proc.stderr, proc.returncode


def read_state(arm, session):
    if not ARMS[arm]["core"] or not session:
        return None
    out, err, code = core_tool(arm, "session-intent-analyzer/scripts/session_intent_ledger.py", "--read-state",
                               "--root", str(ledger_root(arm)), "--platform", "claude", "--session-id", session)
    try:
        return json.loads(out)
    except ValueError:
        return {"_error": (err or out)[:500], "_code": code}


def read_route(arm, session):
    if not ARMS[arm]["core"] or not session:
        return None
    out, err, code = core_tool(arm, "_shared/response_route.py", "--read", "--root", str(ledger_root(arm)),
                               "--platform", "claude", "--session-id", session)
    try:
        return json.loads(out)
    except ValueError:
        return {"_error": (err or out)[:500], "_code": code}


def preinsert_criterion(arm, session):
    """입력을 보내기 전에 그 세션 장부에 완료 조건 1건을 넣고, 들어갔는지 장부에서 다시 읽어 확인한다."""
    delta = {"acceptance_criteria": [{"id": "AC1", "summary": "output/report.txt가 3줄", "source": "user-explicit",
                                      "status": "unmet", "admitted": True}]}
    out, err, code = core_tool(arm, "session-intent-analyzer/scripts/session_intent_ledger.py", "--root", str(ledger_root(arm)),
                               "--platform", "claude", "--session-id", session, "--delta-json", json.dumps(delta, ensure_ascii=False))
    state = read_state(arm, session) or {}
    found = [c for c in state.get("acceptance_criteria") or [] if isinstance(c, dict)]
    ok = any(c.get("admitted") is True and str(c.get("status")) == "unmet" and "3줄" in str(c.get("summary")) for c in found)
    return {"ok": ok, "returncode": code, "stderr": err[:500], "criteria_before_prompt": found}


# ---------- 실행 ----------
def turn_rows(path):
    """대화 기록에서 막힘 직전 초안, Stop 훅이 돌려보낸 글, 토큰 합계를 뽑는다."""
    drafts, feedback, last_text = [], [], None
    tokens = {"input": 0, "cache_create": 0, "cache_read": 0, "output": 0}
    seen = set()
    for row in T.read_rows(path):
        msg = row.get("message") if isinstance(row.get("message"), dict) else {}
        content = msg.get("content")
        if row.get("type") == "assistant":
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "text" and str(part.get("text") or "").strip():
                    last_text = part["text"]
            usage, mid = msg.get("usage"), msg.get("id") or row.get("requestId")
            if usage and mid not in seen:
                seen.add(mid)
                tokens["input"] += usage.get("input_tokens", 0) or 0
                tokens["cache_create"] += usage.get("cache_creation_input_tokens", 0) or 0
                tokens["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                tokens["output"] += usage.get("output_tokens", 0) or 0
        elif row.get("type") == "user" and isinstance(content, str) and content.startswith("Stop hook feedback"):
            drafts.append(last_text)
            feedback.append(content)
    return drafts, feedback, tokens


def run_session(arm, cwd, prompts, session_id=None):
    """세션 하나를 돌린다. 첫 입력은 인수로, 다음 입력은 키 입력으로 넣고, 끝나면 /exit 로 닫는다."""
    args = ["claude", "--model", MODEL, "--effort", EFFORT, "--permission-mode", "auto"]
    if session_id:
        args += ["--session-id", session_id]
    if ARMS[arm]["core"]:      # 고스트엘리스 절차 문서가 실제로 있는 폴더를 작업 폴더에 포함한다(어제는 작업 폴더가 저장소 자체였다)
        args += ["--add-dir", str(ARMS[arm]["core"]), "--add-dir", str(GA / "src" / "autopilot"),
                 "--add-dir", str(ARMS[arm]["home"])]   # 설치 폴더 전체: 절차 문서 연결 경로(.claude/skills)와 .ghost-alice
    project = projects_dir(arm) / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    T.flush_input()
    began = time.time()
    proc = subprocess.Popen(executable=CLAUDE, args=args[:1] + [prompts[0]] + args[1:], cwd=str(cwd), env=arm_env(arm))   # 입력을 맨 앞에 둔다. 뒤에 두면 --add-dir 가 폴더로 삼켜 버린다

    def current():
        best = None
        for path in project.glob("*.jsonl"):
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_ctime < began - 2:
                continue
            turns, meta = T.parse(T.read_rows(path))
            if turns and T.same_input(turns[0]["prompt"], prompts[0]) and (best is None or stat.st_mtime > best[0]):
                best = (stat.st_mtime, path, turns, meta)
        return best

    index, waiting_since, path, turns, meta = 0, time.time(), None, [], {"session": None, "model": None, "versions": set()}
    deadline = began + 1200
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.2)
        got = current()
        if not got or len(got[2]) <= index:
            if time.time() - waiting_since > 120:
                break
            continue
        _, path, turns, meta = got
        if turns[index]["result"] is None:
            continue
        # Autopilot이 다음 작업을 넘기면 턴이 이어질 수 있다. 대화 기록이 6초 동안 그대로일 때 끝난 것으로 본다.
        settled = time.time()
        while time.time() - settled < 6 and time.time() < deadline:
            time.sleep(1)
            if path.stat().st_mtime > settled:
                settled = time.time()
        if index + 1 >= len(prompts):
            break
        T.send_keys(prompts[index + 1])
        time.sleep(0.6)
        T.send_keys("\r")
        index, waiting_since = index + 1, time.time()

    if proc.poll() is None:
        T.send_keys("/exit")
        time.sleep(1)
        T.send_keys("\r")
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    T.flush_input()
    if path:
        turns, meta = T.parse(T.read_rows(path))
    drafts, feedback, tokens = turn_rows(path) if path else ([], [], {})
    session = meta["session"] or (path.stem if path else session_id)
    seconds = None
    if turns and turns[0]["sent_at"] and turns[-1]["ended_at"]:
        seconds = round((datetime.fromisoformat(turns[-1]["ended_at"].replace("Z", "+00:00"))
                         - datetime.fromisoformat(turns[0]["sent_at"].replace("Z", "+00:00"))).total_seconds(), 1)
    return {"session": session, "transcript": str(path) if path else None, "model": meta["model"],
            "versions": sorted(meta["versions"]), "exit_code": proc.returncode, "seconds": seconds, "tokens": tokens,
            "turns": [{"prompt": t["prompt"], "origin": t["origin"], "result": t["result"], "sent_at": t["sent_at"],
                       "ended_at": t["ended_at"], "texts": t["texts"], "calls": t["calls"], "stop_feedback": t["stop_feedback"]}
                      for t in turns],
            "blocked_drafts": drafts, "stop_feedback_texts": feedback,
            "prompts_sent": index + 1, "prompts_expected": len(prompts), "files_after": snapshot(cwd)}


def hook_rows(arm, session):
    """Ghost-ALICE 훅 기록 전체. 3,000자에서 자르지 않고 원문 그대로 읽는다."""
    path = hook_log(arm, session)
    rows = []
    if path and path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            try:
                out = json.loads(row.get("stdout") or "")
            except ValueError:
                out = {}
            rows.append({"event": row.get("event"), "hook": row.get("hook_id"), "ts": row.get("ts"),
                         "seconds": float(row.get("observed_duration_s") or 0), "visible": row.get("visible_decision"),
                         "out": out if isinstance(out, dict) else {}, "stdout": str(row.get("stdout") or ""),
                         "surface": str(row.get("user_surface_output") or "")})
    return rows


def gate_code(text):
    hit = GATE_CODE.search(text or "")
    return hit.group(1) if hit else None


def digest(rows):
    """훅 기록에서 판정에 쓰는 것만 추린다."""
    stops = [r for r in rows if r["event"] == "Stop" and r["hook"] == "completion"]
    blocks = [r for r in stops if str(r["out"].get("decision") or "").lower() == "block"]
    notices = [r for r in stops if str(r["out"].get("decision") or "").lower() != "block" and r["out"].get("systemMessage")]
    auto = [r for r in rows if r["event"] == "Stop" and r["hook"] == "adapter-autopilot-mode-continue"]
    recordings, continuations = [], []
    for r in auto:
        rec = r["out"].get("completion_recording") or {}
        units = [{"work_unit_id": u.get("work_unit_id"), "status": u.get("status"), "unit_status": u.get("unit_status"),
                  "reason": u.get("reason")} for u in rec.get("units") or [] if isinstance(u, dict)]
        recordings.append({"ts": r["ts"], "status": rec.get("status"), "reason": rec.get("reason"), "units": units})
        cont = r["out"].get("continuation")
        if isinstance(cont, dict):
            continuations.append({"ts": r["ts"], "status": cont.get("status"), "task_id": cont.get("task_id"), "plan_id": cont.get("plan_id")})
    counts = {}
    for r in rows:
        counts[f"{r['event']}·{r['hook']}"] = counts.get(f"{r['event']}·{r['hook']}", 0) + 1
    return {"hook_counts": counts, "hook_seconds": round(sum(r["seconds"] for r in rows), 2),
            "stop_block_codes": [gate_code(str(r["out"].get("reason"))) or "(코드 없음)" for r in blocks],
            "stop_block_texts": [str(r["out"].get("reason")) for r in blocks],
            "stop_notice_codes": [gate_code(str(r["out"].get("systemMessage"))) or "(코드 없음)" for r in notices],
            "stop_notice_texts": [str(r["out"].get("systemMessage")) for r in notices],
            "autopilot_recordings": recordings, "autopilot_continuations": continuations,
            "autopilot_stdout": [r["stdout"] for r in auto],
            "shown_to_user": [{"event": r["event"], "hook": r["hook"], "visible": r["visible"], "text": r["surface"]}
                              for r in rows if r["visible"] != "hide" and r["surface"].strip()]}


# ---------- 판정 ----------
def all_calls(sessions):
    return [c for s in sessions for t in s["turns"] for c in t["calls"]]


def final_answer(session):
    texts = [x for t in session["turns"] for x in t["texts"] if str(x).strip()]
    return "\n\n".join(texts)


def call_text(call):
    return json.dumps(call.get("input"), ensure_ascii=False)


def record_calls(calls):
    """Ghost-ALICE 기록용 호출(경로 등록, 장부, 검토, 절차 문서 읽기)."""
    return [c for c in calls if (c["name"] in SHELL_TOOLS and RECORD_SCRIPTS.search(call_text(c))) or c["name"] == "Skill"]


def wrote_at(calls, filename):
    redirect = re.compile(r">\s*[\"']?\S*" + re.escape(filename))
    for call in calls:
        data = call["input"] if isinstance(call["input"], dict) else {}
        target = str(data.get("file_path") or "").replace("\\", "/")
        command = str(data.get("command") or "")
        if (call["name"] in WRITE_TOOLS and target.endswith("/" + filename)) or (
                call["name"] in SHELL_TOOLS and (redirect.search(command)
                                                 or (filename in command and re.search(r"Set-Content|Out-File|WriteAllText", command)))):
            return call.get("at")
    return None


def file_text(rec, rel):
    item = rec["sessions"][-1]["files_after"].get(rel)
    return item["text"] if item else None


def judge(case, arm, rec):
    """사례별로 붙여 받은 기준의 각 칸을 따로 적는다. 값: True 충족 / False 불충족 / None 사람이 확인."""
    on = arm != "off"
    ses, last = rec["sessions"], rec["sessions"][-1]
    d = rec["hooks"][-1] if rec["hooks"] else {}
    calls, answer = all_calls(ses), final_answer(last)
    codes = [c for h in rec["hooks"] for c in h.get("stop_block_codes", [])]
    route_block = "route-unavailable" in codes
    cid, items = case["id"], []

    def add(name, value, basis):
        items.append({"check": name, "value": value, "basis": str(basis)[:600]})

    add("실제 모델이 claude-opus-5-5", all(str(s["model"] or "").startswith(MODEL) for s in ses), [s["model"] for s in ses])
    add("입력이 사람 입력으로 찍힘", all(t["origin"] == ["typed", "human"] for s in ses for t in s["turns"]),
        [t["origin"] for s in ses for t in s["turns"]])
    add("시험 자료가 그대로", rec["fixture_same"], "")
    add("Stop 막힘 사유(전체)", None, codes or "없음")

    if cid == "probe":
        add("답 전체(사람이 확인)", None, answer[:600])
    elif cid == "c01":
        add("도구 호출 0회", not calls, [c["name"] for c in calls])
        add("답에 변경 가능 여부가 있음", bool(re.search(r"변경|수정|바꿀|바뀌|mutable|immutable", answer, re.I)), answer[:200])
        add("막힘 0회", not codes, codes)
    elif cid == "c02":
        add("답이 테스트용 문서", "테스트용 문서" in answer, answer[:200])
        add("route-unavailable 막힘 없음", not route_block, codes)
    elif cid == "c03":
        used = [c for c in calls if "Resolve-Path -LiteralPath" in call_text(c)]
        add("받은 명령을 그대로 실행", bool(used), [c["name"] for c in used] or "명령을 바꿔 실행했거나 실행하지 않음")
        add("답이 17", bool(re.search(r"(?<!\d)17(?!\d)", answer)), answer[:200])
        if arm == "a":
            add("A는 route-unavailable로 막힘", route_block, codes)
        elif arm == "b":
            add("B는 route-unavailable로 막히지 않음", not route_block, codes)
    elif cid == "c04":
        text = file_text(rec, "output/hello.txt")
        add("output/hello.txt 내용이 hello", text is not None and text.strip() == "hello", repr(text))
        add("route-unavailable 막힘 여부(기록)", None, "막힘" if route_block else "막히지 않음")
        add("기록용 호출 수(기록)", None, len(record_calls(calls)))
    elif cid == "c05":
        text = file_text(rec, "test-sandbox/hello.txt")
        add("test-sandbox/hello.txt 내용이 hello", text is not None and text.strip() == "hello", repr(text))
        blocks = [t for h in rec["hooks"] for t in h.get("stop_block_texts", [])]
        add("막힘 문구에 한국어가 있음", (any(KOREAN.search(t) for t in blocks) if blocks else None), f"막힘 {len(blocks)}회")
        add("막힘 문구에 무엇·왜·다음 할 일이 있음",
            (all(("무엇이" in t and "왜:" in t and "다음에 할 일" in t) for t in blocks) if blocks else None),
            (blocks[0][-400:] if blocks else "막힘 없음"))
    elif cid in ("c06", "c07"):
        text = file_text(rec, "output/report.txt")
        add("output/report.txt가 alpha·beta·gamma 세 줄", text is not None and text.strip().splitlines() == ["alpha", "beta", "gamma"], repr(text))
        if on:
            add("장부의 완료 조건 수(기록)", None, len((rec["ledger"][-1] or {}).get("acceptance_criteria") or []))
            route = rec["route"][-1] or {}
            add("경로의 작업 단위 수와 목적(기록)", None, f"{len(route.get('work_units') or [])}개, 목적 {route.get('response_purpose')}, 상태 {route.get('status')}")
            add("Autopilot 완료 기록 상태(기록)", None, [(r["status"], r["reason"], r["units"]) for r in d.get("autopilot_recordings", [])])
        if cid == "c07" and on:
            add("입력 전에 장부에 조건이 들어감", bool((rec.get("preinsert") or {}).get("ok")), rec.get("preinsert"))
            add("route-unavailable로 막힘(자동 등록을 건너뜀)", route_block, codes)
    elif cid == "c08":
        right, trap = r"9,?815\.10?(?!\d)", r"10,?815\.10?(?!\d)"
        add("최종 답이 9815.10", bool(re.search(right, answer)) and not re.search(trap, answer.split("\n")[-1]), answer[-300:])
        add("막히기 전 초안에 함정 값 10815.10이 있음(기록)", None,
            [bool(re.search(trap, str(x))) for x in last["blocked_drafts"]] or "막힘 없음")
        add("검토 명령 실행(기록)", None, sum(1 for c in calls if "quick_review" in call_text(c) or "record-response" in call_text(c)))
    elif cid == "c09":
        add("최종 답이 2026-03-02", "2026-03-02" in answer and "2026-02-03" not in answer.split("\n")[-1], answer[-300:])
        reviews = [c for c in calls if "quick_review" in call_text(c) or "record-response" in call_text(c)]
        add("검토 통과 여부(기록, 정답 수에 더하지 않음)", None, [str(c.get("result"))[:120] for c in reviews] or "검토 명령 없음")
    elif cid in ("c10", "c11", "c12"):
        note, verified = file_text(rec, "test-output/autopilot/note.txt"), file_text(rec, "test-output/autopilot/verified.txt")
        conts = [c for h in rec["hooks"] for c in h.get("autopilot_continuations", [])]
        admitted = any(c.get("plan_id") for c in conts) or any(re.search(r'"status"\s*:\s*"admitted"', str(c.get("result") or "")) for c in calls)
        dispatched = [c for c in conts if c["status"] == "dispatched"]
        add("후속 계획이 admitted로 등록됨", (admitted if on else None), [c.get("plan_id") for c in conts][:3] or "넘김 기록에 계획 없음")
        if cid == "c10":
            add("note.txt와 verified.txt가 없음", note is None and verified is None, f"note {note!r}, verified {verified!r}")
            add("경로의 작업 단위 수(기록)", None, len(((rec["route"][-1] or {}) if on else {}).get("work_units") or []))
        else:
            applied = [(r["ts"], u["work_unit_id"]) for h in rec["hooks"] for r in h.get("autopilot_recordings", [])
                       for u in r["units"] if u["status"] == "applied"]
            add("첫 작업의 완료 기록이 applied", (bool(applied) if on else None), applied[:3] or "없음")
            add("note.txt 내용이 done", note is not None and note.strip() == "done", repr(note))
        if cid == "c11":
            first = min((c["ts"] for c in dispatched if c["ts"]), default=None)
            at = wrote_at(calls, "verified.txt")
            add("둘째 작업이 dispatched로 넘겨짐", (bool(dispatched) if on else None), dispatched[:2] or "없음")
            add("verified.txt 내용이 PASS", verified is not None and verified.strip() == "PASS", repr(verified))
            add("verified.txt를 넘긴 뒤에 씀", (bool(first and at and at[:19] >= first[:19]) if on else None), f"넘김 {first}, 씀 {at}")
        if cid == "c12":
            first_ses, second_ses = ses[0], ses[-1]
            add("첫 세션 뒤 verified.txt가 없음", "test-output/autopilot/verified.txt" not in first_ses["files_after"], "")
            second_conts = rec["hooks"][-1].get("autopilot_continuations", []) if len(rec["hooks"]) > 1 else []
            second_disp = [c for c in second_conts if c["status"] == "dispatched"]
            add("둘째 세션에서 둘째 작업이 dispatched", (bool(second_disp) if on else None), second_disp[:2] or "없음")
            add("verified.txt 내용이 PASS", verified is not None and verified.strip() == "PASS", repr(verified))
            before = first_ses["files_after"].get("test-output/autopilot/note.txt")
            after = second_ses["files_after"].get("test-output/autopilot/note.txt")
            add("둘째 세션에서 note.txt를 다시 쓰지 않음",
                bool(before and after and before["mtime"] == after["mtime"]) and not wrote_at(all_calls([second_ses]), "note.txt"),
                f"수정 시각 {before and before['mtime']} → {after and after['mtime']}")
    return items


def verdict_of(items):
    values = [i["value"] for i in items]
    return "실패" if False in values else "통과(기록 칸은 사람이 확인)"


# ---------- 한 회차 ----------
def one_run(case, arm, number):
    cwd = reset_work(arm)
    rec = {"case": case["id"], "name": case["name"], "arm": arm, "arm_label": ARMS[arm]["label"], "run": number,
           "started_at": datetime.now().isoformat(), "cwd": str(cwd), "model_requested": MODEL, "effort": EFFORT,
           "cli": VERSION, "sessions": [], "hooks": [], "ledger": [], "route": [], "preinsert": None}
    for position, prompts in enumerate(case["sessions"]):
        session_id = None
        if position == 0 and case.get("preinsert") and arm != "off":
            session_id = str(uuid.uuid4())
            rec["preinsert"] = preinsert_criterion(arm, session_id)
            say(f"  [장부] 입력 전 완료 조건 넣기: {'들어감' if rec['preinsert']['ok'] else '안 들어감'}")
        ses = run_session(arm, cwd, prompts, session_id)
        rec["sessions"].append(ses)
        rows = hook_rows(arm, ses["session"]) if ses["session"] else []
        rec["hooks"].append(digest(rows) if arm != "off" else {})
        rec["ledger"].append(read_state(arm, ses["session"]))
        rec["route"].append(read_route(arm, ses["session"]))
        if position + 1 < len(case["sessions"]):
            time.sleep(5)
    rec["fixture_same"] = fixture_same(cwd)
    ok = all(s["session"] and s["turns"] and s["turns"][-1]["result"] and s["prompts_sent"] == s["prompts_expected"] for s in rec["sessions"])
    rec["judgement"] = judge(case, arm, rec) if ok else []
    rec["status"] = verdict_of(rec["judgement"]) if ok else "판정 불가(실행이 끝까지 가지 못함)"
    if ok and arm != "off" and not any(rec["hooks"]):
        rec["status"] = "판정 불가(훅 켠 조건인데 훅 기록이 없음)"
    if ok and arm == "off" and check_environment("off"):
        rec["status"] = "판정 불가(훅 끈 조건인데 훅 기록이 있음)"

    folder = OUT / "runs" / arm / case["id"] / str(number)
    folder.mkdir(parents=True, exist_ok=True)
    for n, ses in enumerate(rec["sessions"], 1):
        if ses["transcript"] and Path(ses["transcript"]).exists():
            shutil.copy2(ses["transcript"], folder / f"transcript-{n}.jsonl")
        log = hook_log(arm, ses["session"])
        if log and log.exists():
            shutil.copy2(log, folder / f"strict-hook-output-{n}.jsonl")
    (folder / "record.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with (OUT / "results.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    for n, ses in enumerate(rec["sessions"], 1):
        say(f"  [세션 {n}] {ses['session']} · 모델 {ses['model']} · {ses['seconds']}초 · 도구 {sum(len(t['calls']) for t in ses['turns'])}회")
    for item in rec["judgement"]:
        mark = {True: "충족", False: "불충족", None: "기록"}[item["value"]]
        say(f"  [{mark}] {item['check']} · {item['basis'][:600 if case.get('probe') else 160]}")
    say(f"  [판정] {rec['status']}")
    return rec["status"]


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["off", "a", "b"], choices=list(ARMS))
    ap.add_argument("--cases", default="all", help="all 또는 쉼표로 구분한 번호(c01,c03)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--first", type=int, default=1)
    ap.add_argument("--wait", type=int, default=0, help="이 초만큼 센 뒤 시작한다")
    ap.add_argument("--list", action="store_true", help="사례 목록만 보여 주고 끝낸다")
    args = ap.parse_args()
    chosen = [c for c in CASES if not c.get("probe")] if args.cases == "all" else [BY_ID[c.strip()] for c in args.cases.split(",") if c.strip()]
    say(f"Ghost-ALICE 훅 끔·A·B 비교 · 대화형 · claude {VERSION} · {MODEL} · effort {EFFORT}")
    for case in chosen:
        say(f"  {case['id']} {case['name']} · 조건 {', '.join(ARMS[a]['label'] for a in args.arms)} · {case.get('runs', args.runs)}회")
    if args.list:
        return
    for arm in args.arms:              # 환경이 맞지 않으면 한 번도 돌리지 않고 끝낸다
        problems = check_environment(arm)
        say(f"환경 확인 · {ARMS[arm]['label']} · {'정상' if not problems else '문제 있음'}")
        for problem in problems:
            say(f"  - {problem}")
        if problems:
            raise SystemExit("환경이 맞지 않아 시작하지 않습니다.")
    OUT.mkdir(parents=True, exist_ok=True)
    if args.wait:
        say()
        for left in range(args.wait, 0, -1):
            print(f"\r{left}초 뒤 시작합니다. 지금 녹화를 누르세요.   ", end="", flush=True)
            time.sleep(1)
        say()
    summary = []
    for arm in args.arms:              # 어제처럼 한 조건에서 모든 사례를 다 돌린 뒤 다음 조건으로 넘어간다
        for case in chosen:
            for number in range(args.first, args.first + case.get("runs", args.runs)):
                say()
                say("=" * 78)
                say(f"{ARMS[arm]['label']} · {case['name']} · {number}회차 · {datetime.now().strftime('%H:%M:%S')}")
                say("=" * 78)
                status = one_run(case, arm, number)
                summary.append((case["id"], arm, number, status))
    say()
    say("=" * 78)
    say("끝. 회차별 결과")
    for cid, arm, number, status in summary:
        say(f"  {cid} {BY_ID[cid]['name']} · {ARMS[arm]['label']} · {number}회차: {status}")


if __name__ == "__main__":
    main()
