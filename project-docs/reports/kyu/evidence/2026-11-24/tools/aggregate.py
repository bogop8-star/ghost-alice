"""Aggregate measured runs into per-case and per-arm tables.

Usage: python aggregate.py [--arms off base imp] [--out C:/Users/N-/hook-monitor/perf/results.md]

Reads runs/<arm>/<case>/<repeat>/check.json (numeric repeats only; trial runs
such as "0" or "0b" are excluded) and the copied transcript for governance tool
calls, Stop blocks and hook wait time (perf_baseline.build). Cost is Claude
Code's own total_cost_usd per run.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\N-\ga-test")
PERF = Path(r"C:\Users\N-\hook-monitor\perf")
sys.path.insert(0, str(PERF))
import perf_baseline as pb  # noqa: E402


def load_runs(arms):
    sys.path.insert(0, str(ROOT / "tools"))
    import run_case
    cases = {c["id"]: c for c in json.loads(run_case.CASES.read_text(encoding="utf-8"))["cases"]}
    runs = []
    for arm in arms:
        for check in sorted((ROOT / "runs" / arm).glob("*/*/check.json")):
            # Only measured repeats 1..n; trial runs ("0", "0b") are excluded.
            if not check.parent.name.isdigit() or int(check.parent.name) < 1:
                continue
            data = json.loads(check.read_text(encoding="utf-8"))
            run_case.use_suite(data.get("suite", "testbed"))
            cases = {c["id"]: c for c in json.loads(run_case.CASES.read_text(encoding="utf-8"))["cases"]}
            # Re-apply the current case checks to the saved answers and work folder,
            # so a corrected check never requires re-running the model.
            answers = [json.loads(p.read_text(encoding="utf-8")).get("result") or ""
                       for p in sorted(check.parent.glob("result-*.json"))]
            data["checks"] = run_case.check(cases[data["case"]], answers, check.parent / "work", data.get("task_tools", 0))
            data["pass"] = all(c["ok"] for c in data["checks"])
            transcript = check.parent / "transcript.jsonl"
            if transcript.exists():
                _, s = pb.build(pb.load(transcript), {})
                data.update(gov_tools=s["tools"]["tools_governance"], all_tools=s["tools"]["tools_total"],
                            blocks=s["stop_blocks"], hook_wait_s=round(s["hook_wait_min"] * 60, 1))
                raw = transcript.read_text(encoding="utf-8")
                # Stop let an answer through with only a notice: the delivered text was not the reviewed one.
                data["unresolved_review"] = "Internal response review remains unresolved" in raw
            data["reviews"] = recorded_reviews(data.get("session_id"))
            runs.append(data)
    return runs


EVIDENCE_CASES = {"K2", "K3", "K4", "K6"}
LEDGER_DB = ROOT / "src" / "core" / ".tmp" / "session-intent" / "ghost-state.sqlite3"


def recorded_reviews(session_id):
    """Count Core response reviews recorded for one test session (both arms share this ledger DB)."""
    import sqlite3
    if not session_id:
        return 0
    total = 0
    for ledger in sorted((ROOT / "src").glob("*/.tmp/session-intent/ghost-state.sqlite3")):
        with sqlite3.connect(ledger) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='core_completion_responses'").fetchone():
                continue
            total += db.execute(
            "SELECT count(*) FROM core_completion_responses r JOIN core_completion_candidates c "
            "ON json_extract(r.payload_json,'$.candidate_reference')=c.reference "
            "WHERE json_extract(c.payload_json,'$.owner.session_id')=?", (session_id,)).fetchone()[0]
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["off", "base"])
    ap.add_argument("--out", type=Path, default=PERF / "results.md")
    args = ap.parse_args()
    runs = load_runs(args.arms)
    by = defaultdict(list)
    for r in runs:
        by[(r["case"], r["arm"])].append(r)
    cases = sorted({r["case"] for r in runs})

    lines = ["# 측정 결과", "", f"조건: {', '.join(args.arms)} · 실행 {len(runs)}회 · 금액은 Claude Code가 보고한 total_cost_usd", "",
             "## 케이스별 평균 금액 (최소~최대, 정답 수/실행 수)", "",
             "| 케이스 | " + " | ".join(args.arms) + " |", "| --- |" + " --- |" * len(args.arms)]
    for case in cases:
        cells = []
        for arm in args.arms:
            rs = by.get((case, arm), [])
            if not rs:
                cells.append("-")
                continue
            costs = [r["cost_usd"] for r in rs]
            cells.append(f"${statistics.mean(costs):.3f} ({min(costs):.3f}~{max(costs):.3f}, {sum(r['pass'] for r in rs)}/{len(rs)})")
        lines.append(f"| {case} | " + " | ".join(cells) + " |")

    lines += ["", "## 조건별 합계", "", "| 지표 | " + " | ".join(args.arms) + " |", "| --- |" + " --- |" * len(args.arms)]

    def arm_rows(arm):
        return [r for r in runs if r["arm"] == arm]

    metrics = [
        ("실행 수", lambda rs: len(rs)),
        ("총 금액", lambda rs: f"${sum(r['cost_usd'] for r in rs):.2f}"),
        ("실행당 평균 금액", lambda rs: f"${statistics.mean(r['cost_usd'] for r in rs):.3f}" if rs else "-"),
        ("실행당 평균 시간(초)", lambda rs: f"{statistics.mean(r['wall_s'] for r in rs):.0f}" if rs else "-"),
        ("정답", lambda rs: f"{sum(r['pass'] for r in rs)}/{len(rs)}"),
        ("오류 실행", lambda rs: sum(bool(r.get('is_error')) for r in rs)),
        ("도구 호출 (관리/전체)", lambda rs: f"{sum(r.get('gov_tools', 0) for r in rs)}/{sum(r.get('all_tools', 0) for r in rs)}"),
        ("Stop 차단", lambda rs: sum(r.get('blocks', 0) for r in rs)),
        ("훅 대기(초)", lambda rs: f"{sum(r.get('hook_wait_s', 0) for r in rs):.0f}"),
        ("검토된 답 그대로 전달 (근거 케이스, 미해결 알림 없음)", lambda rs: (lambda ev: f"{sum(1 for r in ev if r.get('reviews', 0) > 0 and not r.get('unresolved_review'))}/{len(ev)}")([r for r in rs if r["case"] in EVIDENCE_CASES])),
        ("미해결 알림으로 통과한 실행 (전체)", lambda rs: sum(bool(r.get('unresolved_review')) for r in rs)),
        ("응답 검토 실행 (근거 케이스 K2·K3·K4·K6)", lambda rs: (lambda ev: f"{sum(1 for r in ev if r.get('reviews', 0) > 0)}/{len(ev)}")([r for r in rs if r["case"] in EVIDENCE_CASES])),
    ]
    for name, fn in metrics:
        lines.append(f"| {name} | " + " | ".join(str(fn(arm_rows(a))) for a in args.arms) + " |")

    failed = [r for r in runs if not r["pass"]]
    if failed:
        lines += ["", "## 오답·실패 실행", ""]
        for r in failed:
            bad = [c for c in r["checks"] if not c["ok"]]
            lines.append(f"- {r['arm']} {r['case']} #{r['repeat']}: {json.dumps(bad, ensure_ascii=False)[:200]}")
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out.with_suffix(".json")).write_text(json.dumps(runs, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
