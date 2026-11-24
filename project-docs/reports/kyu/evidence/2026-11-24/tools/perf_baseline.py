"""Per-turn cost and governance-overhead baseline for one Claude Code session.

Reads (read-only):
  ~/.claude/projects/<project>/<session>.jsonl   Claude Code transcript
  --costs <file>                                 optional message_id -> USD map
                                                 written by lf_costs.py (Langfuse)

Writes to --out (default: ./out/<session>/):
  turns.csv      one row per turn
  summary.json   session totals
  summary.md     short human-readable summary

A turn starts at each user-side message that the model must answer: a human
prompt, a Stop-hook feedback message, a background task notification, or a
compaction summary. Mid-turn human messages (queued_command) are counted but
do not start a turn.

Definitions
  hook_sum_s     sum of every hook's own duration (durationMs)
  hook_wait_s    per (tool call, hook event) the slowest hook only; Claude Code
                 runs matching hooks in parallel, so this approximates the time
                 the session actually waited
  hook_text      characters hooks returned to the host as context, system
                 messages or blocking errors (what can reach the model)
  tool classes   governance = Ghost-ALICE bookkeeping (ledger, route, response
                 review, skill loading, governance files); ui = desktop-app
                 bookkeeping tools; task = everything else
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

GOV_BASH = re.compile(
    r"session_intent_ledger\.py|response_route\.py|completion_assessment\.py|"
    r"review\d+\.py|route\d+\.json|hook_profile_gate\.py|autopilot_completion\.py|"
    r"pending-merges[\\/].*manifest\.json")
GOV_PATH = re.compile(r"[\\/]\.claude[\\/]skills[\\/]|[\\/]\.ghost-alice[\\/](runtime|skills)[\\/]|"
                      r"scratchpad[\\/](review|route\d+)", re.I)
UI_TOOLS = re.compile(r"^(mcp__ccd_|ToolSearch$)")
ACTIVITY_TYPES = {"assistant", "user", "attachment"}
IDLE_GAP_S = 300  # a silence longer than this (waiting for CI, the user, a background job) is not active time
BLOCK_CODE = re.compile(r"\b(route-unavailable|criterion-unbound|response-unbound|recording-unavailable|"
                        r"route-binding|core-assessment-incompatible|authority-missing)\b")


def ts(value: str | None) -> float | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def find_transcript(session: str) -> Path:
    hits = list((Path.home() / ".claude" / "projects").glob(f"*/{session}.jsonl"))
    if len(hits) != 1:
        raise SystemExit(f"expected one transcript for {session}, found {len(hits)}")
    return hits[0]


def turn_kind(row: dict) -> str | None:
    if row.get("type") != "user" or row.get("isSidechain"):
        return None
    content = (row.get("message") or {}).get("content")
    if isinstance(content, list):
        types = {b.get("type") for b in content if isinstance(b, dict)}
        if "tool_result" in types or "text" not in types:
            return None
        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    elif isinstance(content, str):
        text = content
    else:
        return None
    head = text.lstrip()[:200]
    if head.startswith("Stop hook feedback"):
        return "stop-feedback"
    if head.startswith("<task-notification") or "<task-notification>" in head:
        return "task-notification"
    if head.startswith("This session is being continued"):
        return "compaction"
    if row.get("isMeta"):
        return None
    return "human"


def classify_tool(block: dict) -> str:
    name = block.get("name") or ""
    # json.dumps escapes Windows backslashes ("\\"); fold them to "/" so path rules match.
    data = json.dumps(block.get("input") or {}, ensure_ascii=False).replace("\\\\", "/")
    if UI_TOOLS.match(name):
        return "ui"
    if name == "Skill":
        return "governance"
    if name == "Bash" and GOV_BASH.search(data):
        return "governance"
    if name in {"Read", "Write", "Edit", "Grep", "Glob"} and GOV_PATH.search(data):
        return "governance"
    return "task"


def load(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def build(rows: list[dict], costs: dict[str, float]) -> tuple[list[dict], dict]:
    turns: list[dict] = []
    usage_by_msg: dict[str, tuple[int, dict, str]] = {}
    current = None
    for row in rows:
        when = ts(row.get("timestamp"))
        kind = turn_kind(row)
        if kind and when is not None:
            current = {"turn": len(turns) + 1, "kind": kind, "start": when, "end": when,
                       "tools": Counter(), "msgs": set(), "hooks": [], "hook_text": 0,
                       "blocks": 0, "codes": Counter(), "queued": 0, "active": 0.0}
            turns.append(current)
            continue
        if current is None or when is None:
            continue
        rtype = row.get("type")
        if rtype in ACTIVITY_TYPES:
            # Bookkeeping rows (titles, snapshots, queue markers) can be written much
            # later; only model, tool and hook activity defines how long a turn ran.
            if when - current["end"] <= IDLE_GAP_S:
                current["active"] += when - current["end"]
            current["end"] = max(current["end"], when)
        if rtype == "assistant" and not row.get("isSidechain"):
            msg = row.get("message") or {}
            if msg.get("id"):
                current["msgs"].add(msg["id"])
                usage_by_msg[msg["id"]] = (current["turn"], msg.get("usage") or {}, msg.get("model") or "")
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    current["tools"][classify_tool(block)] += 1
        elif rtype == "attachment":
            att = row.get("attachment") or {}
            atype = att.get("type")
            if atype == "hook_success":
                try:
                    dur = float(att.get("durationMs") or 0) / 1000
                except ValueError:
                    dur = 0.0
                current["hooks"].append((att.get("hookEvent"), att.get("hookName"), att.get("toolUseID"), dur))
                current["hook_text"] += len(att.get("content") or "")
            elif atype in {"hook_additional_context", "hook_system_message"}:
                content = att.get("content")
                current["hook_text"] += len(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
            elif atype == "hook_blocking_error":
                err = att.get("blockingError")
                text = err if isinstance(err, str) else json.dumps(err, ensure_ascii=False)
                current["hook_text"] += len(text)
                current["blocks"] += 1
                current["codes"].update(set(BLOCK_CODE.findall(text)))
            elif atype == "queued_command":
                current["queued"] += 1

    out = []
    for t in turns:
        tok = Counter()
        cost, priced = 0.0, 0
        for mid in t["msgs"]:
            _, usage, _ = usage_by_msg[mid]
            tok["input"] += usage.get("input_tokens") or 0
            tok["output"] += usage.get("output_tokens") or 0
            tok["cache_read"] += usage.get("cache_read_input_tokens") or 0
            tok["cache_write"] += usage.get("cache_creation_input_tokens") or 0
            if mid in costs:
                cost += costs[mid]
                priced += 1
        wait = defaultdict(float)
        for event, _name, tool_id, dur in t["hooks"]:
            key = (event, tool_id or f"{event}-{t['turn']}")
            wait[key] = max(wait[key], dur)
        tools = t["tools"]
        total_tools = sum(tools.values())
        out.append({
            "turn": t["turn"], "kind": t["kind"],
            "start": datetime.fromtimestamp(t["start"]).isoformat(timespec="seconds"),
            "wall_s": round(t["end"] - t["start"], 1),
            "active_s": round(t["active"], 1),
            "llm_calls": len(t["msgs"]),
            "input_tok": tok["input"], "output_tok": tok["output"],
            "cache_read_tok": tok["cache_read"], "cache_write_tok": tok["cache_write"],
            "cost_usd": round(cost, 4) if priced else "",
            "tools_total": total_tools, "tools_task": tools["task"],
            "tools_governance": tools["governance"], "tools_ui": tools["ui"],
            "gov_share": round(tools["governance"] / total_tools, 3) if total_tools else "",
            "hook_runs": len(t["hooks"]),
            "hook_sum_s": round(sum(h[3] for h in t["hooks"]), 1),
            "hook_wait_s": round(sum(wait.values()), 1),
            "hook_text_chars": t["hook_text"],
            "stop_blocks": t["blocks"], "block_codes": ";".join(sorted(t["codes"])),
            "queued_msgs": t["queued"],
        })

    def total(key):
        return sum(r[key] for r in out if isinstance(r[key], (int, float)))

    summary = {
        "turns": len(out),
        "turns_by_kind": dict(Counter(r["kind"] for r in out)),
        "wall_hours": round(total("wall_s") / 3600, 2),
        "active_hours": round(total("active_s") / 3600, 2),
        "llm_calls": total("llm_calls"),
        "tokens": {k: total(k) for k in ("input_tok", "output_tok", "cache_read_tok", "cache_write_tok")},
        "cost_usd": round(total("cost_usd"), 2) if any(r["cost_usd"] != "" for r in out) else None,
        "tools": {k: total(k) for k in ("tools_total", "tools_task", "tools_governance", "tools_ui")},
        "hook_runs": total("hook_runs"),
        "hook_sum_min": round(total("hook_sum_s") / 60, 1),
        "hook_wait_min": round(total("hook_wait_s") / 60, 1),
        "hook_text_chars": total("hook_text_chars"),
        "stop_blocks": total("stop_blocks"),
        "block_codes": dict(sum((Counter(r["block_codes"].split(";")) for r in out if r["block_codes"]), Counter())),
        "queued_msgs": total("queued_msgs"),
    }
    t_all = summary["tools"]["tools_total"] or 1
    summary["governance_share_of_tools"] = round(summary["tools"]["tools_governance"] / t_all, 3)
    summary["hook_wait_share_of_active"] = round(total("hook_wait_s") / (total("active_s") or 1), 3)
    repair = [r for r in out if r["kind"] == "stop-feedback"]
    summary["stop_feedback_turns"] = {
        "count": len(repair),
        "active_min": round(sum(r["active_s"] for r in repair) / 60, 1),
        "llm_calls": sum(r["llm_calls"] for r in repair),
        "cost_usd": round(sum(r["cost_usd"] for r in repair if r["cost_usd"] != ""), 2) if summary["cost_usd"] is not None else None,
    }
    return out, summary


def write_md(path: Path, session: str, s: dict) -> None:
    cost = f"${s['cost_usd']}" if s["cost_usd"] is not None else "(no cost file)"
    rf = s["stop_feedback_turns"]
    lines = [
        f"# Baseline: session `{session}`", "",
        "| Metric | Value |", "| --- | --- |",
        f"| Turns | {s['turns']} ({', '.join(f'{k} {v}' for k, v in s['turns_by_kind'].items())}) |",
        f"| Active time (sum of turns, silences over {IDLE_GAP_S // 60} min excluded) | {s['active_hours']} h |",
        f"| Wall time (sum of turns, incl. waits) | {s['wall_hours']} h |",
        f"| Model calls | {s['llm_calls']} |",
        f"| Cost | {cost} |",
        f"| Tool calls | {s['tools']['tools_total']} (task {s['tools']['tools_task']}, governance {s['tools']['tools_governance']}, ui {s['tools']['tools_ui']}) |",
        f"| Governance share of tool calls | {s['governance_share_of_tools']:.1%} |",
        f"| Hook runs | {s['hook_runs']} |",
        f"| Hook time: sum / waited | {s['hook_sum_min']} min / {s['hook_wait_min']} min |",
        f"| Waited hook time share of active time | {s['hook_wait_share_of_active']:.1%} |",
        f"| Hook text returned to the host | {s['hook_text_chars']:,} chars |",
        f"| Stop-hook blocks | {s['stop_blocks']} ({', '.join(f'{k} {v}' for k, v in s['block_codes'].items())}) |",
        f"| Stop-feedback repair turns | {rf['count']} turns, {rf['active_min']} active min, {rf['llm_calls']} model calls, cost {rf['cost_usd']} |",
        f"| Mid-turn messages | {s['queued_msgs']} |",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session")
    ap.add_argument("--transcript", type=Path)
    ap.add_argument("--costs", type=Path, help="JSON map message_id -> USD from lf_costs.py")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    transcript = args.transcript or find_transcript(args.session)
    costs = json.loads(args.costs.read_text(encoding="utf-8")) if args.costs else {}
    out_dir = args.out or Path(__file__).resolve().parent / "out" / args.session
    out_dir.mkdir(parents=True, exist_ok=True)
    turns, summary = build(load(transcript), costs)
    with (out_dir / "turns.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(turns[0].keys()))
        writer.writeheader()
        writer.writerows(turns)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_md(out_dir / "summary.md", args.session, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
