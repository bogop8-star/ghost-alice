"""Run the automatable everyday test questions with Ghost-ALICE on and off.

For each question marked "auto": true in questions.json, the runner sends the
question once through `claude -p` with the normal setup (Ghost-ALICE on) and
once with `--safe-mode` (CLAUDE.md, skills and hooks off), each in a fresh
empty temporary folder. It records the answer, cost, turns, tool denials and,
for the "on" run, the session-intent ledger state (read-only).

Every run appends redacted JSON lines to results/<run_id>.jsonl and a line to
results/run-log.md. Nothing is graded automatically; grading is a separate step.

Usage:
  python run_daily_test.py                 # all auto questions, both modes
  python run_daily_test.py --ids D01 D08   # selected questions
  python run_daily_test.py --modes on      # one mode only
  python run_daily_test.py --model sonnet  # pin a model (default: CLI default)

Dependencies: Python 3.11+ standard library, logged-in Claude Code CLI.
"""
import argparse
import base64
import getpass
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or HOME / ".claude")


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def redact(text: str) -> str:
    for needle in {str(HOME), str(HOME).replace("\\", "/"), str(HOME).replace("\\", "\\\\")}:
        text = text.replace(needle, "<home>")
    user = getpass.getuser()
    return re.sub(re.escape(user), "<user>", text, flags=re.IGNORECASE) if user else text


def find_claude() -> str:
    explicit = os.environ.get("CLAUDE_EXE")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    hits = sorted(Path(os.environ.get("LOCALAPPDATA", "")).glob("Claude-Data/*/claude-code/*/*/claude.exe"),
                  key=lambda p: p.stat().st_mtime)
    if hits:
        return str(hits[-1])
    sys.exit("claude CLI not found; set CLAUDE_EXE")


def ledger_root() -> Path | None:
    settings = CONFIG_DIR / "settings.json"
    if not settings.exists():
        return None
    for match in re.finditer(r'--binding-b64\\?"?\s*\\?"?([A-Za-z0-9+/=]{40,})', settings.read_text(encoding="utf-8")):
        try:
            root = json.loads(base64.b64decode(match.group(1)))["destination"]["ledger_root"]
            return Path(root)
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    return None


def read_ledger(root: Path | None, session_id: str) -> dict:
    db = root / "ghost-state.sqlite3" if root else None
    if not db or not db.exists():
        return {"error": "ledger-db-missing"}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    row = con.execute("SELECT state_json FROM sessions WHERE platform='claude' AND session_id=?",
                      (session_id,)).fetchone()
    events = [json.loads(e).get("event", "?") for (e,) in con.execute(
        "SELECT event_json FROM intent_events WHERE platform='claude' AND session_id=? ORDER BY sequence",
        (session_id,))]
    con.close()
    if not row:
        return {"error": "no-session-row", "events": events}
    state = json.loads(row[0])
    return {"intake_status": state.get("intake_status"),
            "input_confirmed": bool(state.get("latest_input_event_id")),
            "current_goal_set": bool(state.get("current_goal")),
            "response_route_set": state.get("response_route") is not None,
            "events": events}


def run_one(claude: str, question: str, mode: str, model: str | None) -> dict:
    cmd = [claude, "-p", "--output-format", "json"]
    if mode == "off":
        cmd.append("--safe-mode")
    if model:
        cmd += ["--model", model]
    workdir = tempfile.mkdtemp(prefix=f"daily-{mode}-")
    started = now()
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, input=question, capture_output=True, text=True,
                              encoding="utf-8", cwd=workdir, timeout=600)
    except subprocess.TimeoutExpired:
        return {"started_at": started, "error": "timeout-600s"}
    elapsed = round(time.time() - t0, 1)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"started_at": started, "elapsed_s": elapsed,
                "error": redact((proc.stderr or proc.stdout or "no output")[:800])}
    return {"started_at": started, "elapsed_s": elapsed,
            "session_id": out.get("session_id"),
            "model": next(iter(out.get("modelUsage") or {}), None),
            "is_error": out.get("is_error"), "subtype": out.get("subtype"),
            "num_turns": out.get("num_turns"), "cost_usd": out.get("total_cost_usd"),
            "permission_denials": [d.get("tool_name") for d in out.get("permission_denials") or []],
            "answer": redact(out.get("result") or ""),
            "answer_chars": len(out.get("result") or "")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--modes", nargs="*", default=["on", "off"], choices=["on", "off"])
    ap.add_argument("--model")
    args = ap.parse_args()

    spec = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    questions = [q for q in spec["questions"] if q["auto"] and (not args.ids or q["id"] in args.ids)]
    claude = find_claude()
    root = ledger_root()
    version = subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{run_id}.jsonl"
    env = {"os": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
           "claude_cli": version, "model_arg": args.model or "cli-default"}
    print(f"run {run_id}: {len(questions)} questions x {args.modes} -> {out_file.name}")

    totals = {"runs": 0, "errors": 0, "cost_usd": 0.0}
    for q in questions:
        for mode in args.modes:
            rec = {"run_id": run_id, "id": q["id"], "type": q["type"], "mode": mode,
                   "question": q["turns"][0], "observe": q["observe"], "fail_if": q["fail_if"],
                   "environment": env, **run_one(claude, q["turns"][0], mode, args.model)}
            if mode == "on" and rec.get("session_id"):
                time.sleep(1)
                rec["ledger"] = read_ledger(root, rec["session_id"])
            rec["recorded_at"] = now()
            with out_file.open("a", encoding="utf-8") as fh:
                fh.write(redact(json.dumps(rec, ensure_ascii=False)) + "\n")
            totals["runs"] += 1
            totals["errors"] += 1 if rec.get("error") or rec.get("is_error") else 0
            totals["cost_usd"] += rec.get("cost_usd") or 0
            ledger = rec.get("ledger", {})
            print(f"{q['id']} {mode:<3} {rec.get('elapsed_s', '-')}s turns={rec.get('num_turns')} "
                  f"chars={rec.get('answer_chars')} denied={rec.get('permission_denials')} "
                  f"intake={ledger.get('intake_status', '-')} err={rec.get('error', '')}")

    with (out_dir / "run-log.md").open("a", encoding="utf-8") as fh:
        fh.write(f"| {run_id} | {now()} | {','.join(q['id'] for q in questions)} | {','.join(args.modes)} | "
                 f"{env['model_arg']} | {totals['runs']} | {totals['errors']} | ${totals['cost_usd']:.4f} | "
                 f"results/{out_file.name} |\n")
    print(f"done: runs={totals['runs']} errors={totals['errors']} cost=${totals['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
