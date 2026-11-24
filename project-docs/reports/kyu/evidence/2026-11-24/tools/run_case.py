"""Run one test case in one arm with headless Claude Code and keep everything it produced.

Usage: python run_case.py <arm: off|base|imp> <case id> <repeat> [--budget 2.0] [--model opus]

For each run:
  - copies perf/testbed/fixture into a fresh work folder
  - runs `claude -p --output-format json` once per prompt (later prompts use --resume)
    with HOME / USERPROFILE / CLAUDE_CONFIG_DIR / GHOST_ALICE_GHOST_ROOT pointing at
    C:/Users/N-/ga-test/home-<arm>, and all inherited CLAUDE_*/ANTHROPIC_*/GHOST_ALICE_*
    variables removed so the run cannot reach the desktop session that launched it
  - allows only Bash, Read, Write, Edit, Glob, Grep, Skill (other tools are denied in -p)
  - applies the case checks from cases.json
  - writes runs/<arm>/<case>/<repeat>/: result-<n>.json (Claude Code output), check.json,
    transcript.jsonl (copied), work/ (the work folder after the run)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\N-\ga-test")
PERF = Path(r"C:\Users\N-\hook-monitor\perf")
CASES = PERF / "testbed" / "cases.json"
FIXTURE = PERF / "testbed" / "fixture"
TOOLS = "Bash Read Write Edit Glob Grep Skill"


def clean_env(arm: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("CLAUDE", "ANTHROPIC", "GHOST_ALICE", "LANGFUSE"))}
    home = ROOT / f"home-{arm}"
    env.update(HOME=str(home), USERPROFILE=str(home), CLAUDE_CONFIG_DIR=str(home / ".claude"),
               GHOST_ALICE_GHOST_ROOT=str(home / ".ghost-alice"), PYTHONUTF8="1",
               # Test-only Core patch (branch test/sdk-origin): treat headless prompts as human
               # input so governance follows its normal path. Set for every arm.
               GHOST_ALICE_TEST_ACCEPT_SDK_ORIGIN="1")
    env["PATH"] = r"C:\Users\N-\AppData\Local\Programs\Python\Python314;" + env.get("PATH", "")
    return env


def tree_digest(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(path)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def check(case: dict, answers: list[str], work: Path, task_tools: int) -> list[dict]:
    out = []
    for c in case["checks"]:
        t = c["type"]
        if t in ("answer_any", "answer_all"):
            text = answers[c.get("turn", len(answers)) - 1].lower() if answers else ""
            hits = [v for v in c["values"] if v.lower() in text]
            ok = bool(hits) if t == "answer_any" else len(hits) == len(c["values"])
            out.append({"check": t, "turn": c.get("turn"), "ok": ok, "hits": hits})
        elif t == "file_equals":
            p = work / c["path"]
            got = p.read_text(encoding="utf-8") if p.is_file() else None
            ok = got is not None and (got.strip() if c.get("strip") else got) == c["value"]
            out.append({"check": t, "ok": ok, "got": got})
        elif t == "unchanged_fixture":
            ok = all((work / p.relative_to(FIXTURE)).is_file()
                     and (work / p.relative_to(FIXTURE)).read_bytes() == p.read_bytes()
                     for p in FIXTURE.rglob("*") if p.is_file())
            out.append({"check": t, "ok": ok})
        elif t == "max_tool_calls":
            out.append({"check": t, "ok": task_tools <= c["value"], "task_tools": task_tools})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", help="result label, e.g. off, base, imp, imp2")
    ap.add_argument("--home", choices=["off", "base", "imp"], help="test home to run in (default: same as arm)")
    ap.add_argument("case")
    ap.add_argument("repeat")
    ap.add_argument("--budget", type=float, default=2.0)
    ap.add_argument("--model", default="opus")
    args = ap.parse_args()

    case = next(c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"] if c["id"] == args.case)
    run_dir = ROOT / "runs" / args.arm / args.case / str(args.repeat)
    if run_dir.exists():
        sys.exit(f"already exists: {run_dir}")
    work = run_dir / "work"
    shutil.copytree(FIXTURE, work)
    (work / "output").mkdir(exist_ok=True)
    home_arm = args.home or args.arm
    env = clean_env(home_arm)

    session_id, answers, results = None, [], []
    started = time.time()
    for n, prompt in enumerate(case["prompts"], 1):
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", args.model,
               "--max-budget-usd", str(args.budget), "--allowedTools", *TOOLS.split()]
        if session_id:
            cmd += ["--resume", session_id]
        proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=900, shell=False)
        (run_dir / f"stdout-{n}.txt").write_text(proc.stdout, encoding="utf-8")
        (run_dir / f"stderr-{n}.txt").write_text(proc.stderr, encoding="utf-8")
        try:
            res = json.loads(proc.stdout)
        except json.JSONDecodeError:
            res = {"parse_error": True, "returncode": proc.returncode}
        (run_dir / f"result-{n}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append(res)
        session_id = res.get("session_id") or session_id
        answers.append(res.get("result") or "")

    transcript = None
    if session_id:
        hits = list((ROOT / f"home-{home_arm}" / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
        if hits:
            transcript = run_dir / "transcript.jsonl"
            shutil.copy2(hits[0], transcript)

    task_tools = 0
    if transcript:
        sys.path.insert(0, str(PERF))
        import perf_baseline as pb
        for row in pb.load(transcript):
            if row.get("type") == "assistant":
                for b in (row.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and pb.classify_tool(b) == "task":
                        task_tools += 1

    checks = check(case, answers, work, task_tools)
    summary = {
        "arm": args.arm, "home": home_arm, "case": args.case, "repeat": args.repeat, "model": args.model,
        "session_id": session_id, "wall_s": round(time.time() - started, 1),
        "cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in results), 4),
        "num_turns": sum(r.get("num_turns") or 0 for r in results),
        "duration_ms": sum(r.get("duration_ms") or 0 for r in results),
        "is_error": any(r.get("is_error") or r.get("parse_error") for r in results),
        "task_tools": task_tools,
        "pass": all(c["ok"] for c in checks), "checks": checks,
    }
    (run_dir / "check.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
