"""Run a batch of test cases sequentially, interleaving arms and cases.

Usage: python run_batch.py --arms off base --repeats 3 [--cases K1 K2 ...] [--budget 2.0]
       arm labels may name their test home: --arms jy:base kyu13:imp

Order: for each repeat, for each case, every arm in turn (arm order rotates per
repeat) so time-of-day effects spread across arms. Existing run folders are
skipped, so an interrupted batch can be restarted. Progress goes to
runs/batch-<arms>.log; each run writes its own check.json via run_case.py.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\N-\ga-test")
PERF = Path(r"C:\Users\N-\hook-monitor\perf")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", required=True)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--cases", nargs="*")
    ap.add_argument("--budget", type=float, default=2.0)
    ap.add_argument("--home", help="test home for every arm label (default: arm name)")
    ap.add_argument("--suite", default="testbed")
    args = ap.parse_args()
    cases = args.cases or [c["id"] for c in json.loads((PERF / args.suite / "cases.json").read_text(encoding="utf-8"))["cases"]]
    homes = {a.split(':')[0]: (a.split(':')[1] if ':' in a else args.home) for a in args.arms}
    args.arms = list(homes)
    log = ROOT / "runs" / f"batch-{'-'.join(args.arms)}.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    plan = []
    for rep in range(1, args.repeats + 1):
        arms = args.arms[rep % len(args.arms):] + args.arms[:rep % len(args.arms)]
        for case in cases:
            for arm in arms:
                plan.append((arm, case, str(rep)))
    total = len(plan)
    spent = 0.0
    with log.open("a", encoding="utf-8") as out:
        out.write(f"=== start {time.strftime('%H:%M:%S')} runs={total}\n")
        for i, (arm, case, rep) in enumerate(plan, 1):
            run_dir = ROOT / "runs" / arm / case / rep
            if (run_dir / "check.json").exists():
                out.write(f"[{i}/{total}] skip {arm} {case} {rep}\n")
                continue
            t = time.time()
            proc = subprocess.run([sys.executable, str(ROOT / "tools" / "run_case.py"), arm, case, rep,
                                   "--budget", str(args.budget), "--suite", args.suite] + (["--home", homes[arm]] if homes[arm] else []), capture_output=True, text=True, encoding="utf-8")
            try:
                res = json.loads(proc.stdout.strip().splitlines()[-1])
                spent += res.get("cost_usd") or 0
                line = (f"[{i}/{total}] {arm} {case} {rep} cost=${res.get('cost_usd')} pass={res.get('pass')} "
                        f"err={res.get('is_error')} {time.time() - t:.0f}s total=${spent:.2f}")
            except (ValueError, IndexError):
                line = f"[{i}/{total}] {arm} {case} {rep} FAILED rc={proc.returncode} {proc.stderr[-300:]!r}"
            out.write(line + "\n")
            out.flush()
        out.write(f"=== end {time.strftime('%H:%M:%S')} spent=${spent:.2f}\n")
    print(f"done, spent ${spent:.2f}, log {log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
