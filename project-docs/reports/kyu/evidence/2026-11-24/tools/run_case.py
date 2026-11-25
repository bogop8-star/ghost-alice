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

# Paths: GA_TEST_ROOT (runs, test homes, test Cores; default ~/ga-test) and
# GA_PERF_DIR (folder holding testbed/ and testbed2/). When these tools sit in
# the team repository's evidence folder, GA_PERF_DIR defaults to that folder.
_HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("GA_TEST_ROOT") or (Path.home() / "ga-test"))
PERF = Path(os.environ.get("GA_PERF_DIR") or (
    _HERE.parent if (_HERE.parent / "testbed" / "cases.json").exists()
    else Path(r"C:\Users\N-\hook-monitor\perf")))
CASES = PERF / "testbed" / "cases.json"
FIXTURE = PERF / "testbed" / "fixture"


def use_suite(name: str) -> None:
    """Point CASES/FIXTURE at perf/<name>/ (default suite: testbed)."""
    global CASES, FIXTURE
    CASES, FIXTURE = PERF / name / "cases.json", PERF / name / "fixture"
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
    # Hooks find Python on PATH: put the interpreter running this script first.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def work_name(rel: Path) -> Path:
    """A fixture file kept as <name>.md.txt (outside the docs checks) is used as <name>.md."""
    return rel.with_name(rel.name[:-4]) if rel.name.endswith(".md.txt") else rel


def copy_fixture(work: Path) -> None:
    shutil.copytree(FIXTURE, work)
    for p in list(work.rglob("*.md.txt")):
        p.rename(work / work_name(p.relative_to(work)))


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
            ok = all((work / work_name(p.relative_to(FIXTURE))).is_file()
                     and (work / work_name(p.relative_to(FIXTURE))).read_bytes() == p.read_bytes()
                     for p in FIXTURE.rglob("*") if p.is_file())
            out.append({"check": t, "ok": ok})
        elif t == "max_tool_calls":
            out.append({"check": t, "ok": task_tools <= c["value"], "task_tools": task_tools})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arm", help="result label, e.g. off, base, imp, imp2")
    ap.add_argument("--home", help="test home name, i.e. ~/ga-test/home-<name> made by install_arm.ps1 -Arm <name> "
                                   "(default: same as arm)")
    ap.add_argument("case")
    ap.add_argument("repeat")
    ap.add_argument("--budget", type=float, default=2.0)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--suite", default="testbed")
    args = ap.parse_args()
    use_suite(args.suite)
    # Any installed home name works (TESTING.md uses a and b). Stop before creating a run
    # folder when the home is missing, so a typo does not leave a half-made run behind.
    home_dir = ROOT / f"home-{args.home or args.arm}"
    if not home_dir.is_dir():
        sys.exit(f"test home not found: {home_dir} (install it with install_arm.ps1 -Arm {args.home or args.arm})")

    case = next(c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"] if c["id"] == args.case)
    run_dir = ROOT / "runs" / args.arm / args.case / str(args.repeat)
    if run_dir.exists():
        sys.exit(f"already exists: {run_dir}")
    work = run_dir / "work"
    copy_fixture(work)
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
        sys.path[:0] = [str(_HERE), str(PERF)]
        import perf_baseline as pb
        for row in pb.load(transcript):
            if row.get("type") == "assistant":
                for b in (row.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and pb.classify_tool(b) == "task":
                        task_tools += 1

    checks = check(case, answers, work, task_tools)
    # Answer drafts that a Stop block held back: shows whether a review changed the answer.
    drafts = []
    if transcript:
        last_text = None
        for row in pb.load(transcript):
            message = row.get("message") or {}
            if row.get("type") == "assistant":
                for b in message.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip():
                        last_text = b["text"]
            elif row.get("type") == "user" and isinstance(message.get("content"), str) \
                    and "Stop hook feedback" in message["content"]:
                drafts.append(last_text)
    summary = {
        "arm": args.arm, "home": home_arm, "suite": args.suite, "case": args.case, "repeat": args.repeat, "model": args.model,
        "session_id": session_id, "wall_s": round(time.time() - started, 1),
        "cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in results), 4),
        "num_turns": sum(r.get("num_turns") or 0 for r in results),
        "duration_ms": sum(r.get("duration_ms") or 0 for r in results),
        "is_error": any(r.get("is_error") or r.get("parse_error") for r in results),
        "task_tools": task_tools,
        "pass": all(c["ok"] for c in checks), "checks": checks,
        "blocked_drafts": drafts, "answers": answers,
    }
    (run_dir / "check.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    # run_batch.py reads this line as UTF-8. ASCII escapes keep it readable even when this
    # process's stdout uses the Windows ANSI code page (cp949 on Korean Windows).
    print(json.dumps(summary, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
