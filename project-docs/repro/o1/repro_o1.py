"""Reproduce observation O1: `claude -p` input stays pending in the Ghost-ALICE ledger.

Runs one non-interactive `claude -p` question (or checks an existing session),
then reads the session-intent ledger read-only and prints a redacted verdict.

Usage:
  python repro_o1.py                          # run claude -p once and check
  python repro_o1.py --runs 3                 # repeat
  python repro_o1.py --check-session-id <id>  # only check a session (e.g. interactive control)

Dependencies: Python 3.11+ standard library, Claude Code CLI logged in,
Ghost-ALICE Core + Autopilot installed with hooks enabled.
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

QUESTION = "오늘 저녁 메뉴로 간단한 것 하나만 추천해줘."
HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or HOME / ".claude")


def redact(text: str) -> str:
    user = getpass.getuser()
    for needle in {str(HOME), str(HOME).replace("\\", "/"), str(HOME).replace("\\", "\\\\")}:
        text = text.replace(needle, "<home>")
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


def hook_binding() -> dict:
    """Decode the Ghost-ALICE hook binding the installer wrote into settings.json."""
    settings = CONFIG_DIR / "settings.json"
    if not settings.exists():
        return {}
    for match in re.finditer(r'--binding-b64\\?"?\s*\\?"?([A-Za-z0-9+/=]{40,})', settings.read_text(encoding="utf-8")):
        try:
            return json.loads(base64.b64decode(match.group(1)))
        except (ValueError, json.JSONDecodeError):
            continue
    return {}


def read_ledger(ledger_root: Path, session_id: str) -> dict:
    db = ledger_root / "ghost-state.sqlite3"
    if not db.exists():
        return {"error": "ledger-db-missing"}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    row = con.execute("SELECT revision, input_event_id, state_json FROM sessions "
                      "WHERE platform='claude' AND session_id=?", (session_id,)).fetchone()
    events = [json.loads(e)["event"] if "event" in json.loads(e) else "?" for (e,) in con.execute(
        "SELECT event_json FROM intent_events WHERE platform='claude' AND session_id=? ORDER BY sequence",
        (session_id,))]
    con.close()
    if not row:
        return {"error": "no-session-row", "events": events}
    state = json.loads(row[2])
    return {
        "ledger_revision": row[0],
        "intake_status": state.get("intake_status"),
        "latest_input_event_id_set": bool(state.get("latest_input_event_id")),
        "pending_native_inputs": len(state.get("pending_native_inputs") or []),
        "current_goal_set": bool(state.get("current_goal")),
        "response_route_set": state.get("response_route") is not None,
        "events": events,
    }


def verdict(ledger: dict) -> str:
    if "error" in ledger:
        return "NO_LEDGER_ROW (hooks may not have run)"
    if (ledger["intake_status"] == "pending-native-origin" and not ledger["latest_input_event_id_set"]
            and not ledger["current_goal_set"] and not ledger["response_route_set"]):
        return "REPRODUCED"
    return "NOT_REPRODUCED"


def run_once(claude: str, model: str) -> dict:
    workdir = tempfile.mkdtemp(prefix="ga-o1-")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    proc = subprocess.run([claude, "-p", "--output-format", "json", "--model", model],
                          input=QUESTION, capture_output=True, text=True, encoding="utf-8",
                          cwd=workdir, timeout=600)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"started_at": started, "error": redact((proc.stderr or proc.stdout)[:500])}
    return {"started_at": started, "session_id": out.get("session_id"),
            "claude_is_error": out.get("is_error"), "answer_chars": len(out.get("result") or "")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--ledger-root", help="override; default comes from the installed hook binding")
    ap.add_argument("--check-session-id", help="skip claude -p and check this session only")
    ap.add_argument("--out", default="o1-result.json")
    args = ap.parse_args()

    binding = hook_binding().get("destination", {})
    ledger_root = Path(args.ledger_root or binding.get("ledger_root") or "")
    if not str(ledger_root) or not ledger_root.exists():
        sys.exit("ledger root not found; pass --ledger-root (is Ghost-ALICE installed with hooks?)")
    claude = find_claude()
    version = subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()

    cases = []
    if args.check_session_id:
        cases.append({"mode": "check-only", "session_id": args.check_session_id})
    else:
        for _ in range(args.runs):
            cases.append({"mode": "claude -p", **run_once(claude, args.model)})
    time.sleep(1)
    for case in cases:
        if case.get("session_id"):
            case["ledger"] = read_ledger(ledger_root, case["session_id"])
            case["verdict"] = verdict(case["ledger"])
        else:
            case["verdict"] = "RUN_FAILED"

    report = {
        "observation": "O1",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {"os": f"{platform.system()} {platform.release()} ({platform.version()})",
                        "python": platform.python_version(), "claude_cli": version,
                        "hook_mode": binding.get("mode"), "ledger_root": redact(str(ledger_root))},
        "question_chars": len(QUESTION),
        "cases": cases,
    }
    text = redact(json.dumps(report, ensure_ascii=False, indent=2))
    Path(args.out).write_text(text, encoding="utf-8")
    for case in cases:
        print(f"{case['verdict']:<16} session={str(case.get('session_id'))[:8]} "
              f"status={case.get('ledger', {}).get('intake_status')} events={case.get('ledger', {}).get('events')}")
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
