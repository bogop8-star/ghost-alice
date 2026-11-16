"""Per-session governance cost metrics from local Claude Code transcripts.

Reads ~/.claude/projects/<project>/<session>.jsonl (or the folder given by --projects) and counts, per session:
user turns, tool calls, governance tool calls, Stop hook blocks by reason, and output tokens.
Reads local files only, sends nothing anywhere, and prints no prompt, answer or tool text.

Usage:
  python governance_metrics.py [--projects DIR] [--json OUT] [--min-turns N]

Definitions (see project-docs/metrics/README.md):
  user_turns       messages typed by a person, including ones queued mid-turn (not tool results, hook feedback or
                   notifications)
  tool_calls       assistant tool_use blocks
  gov_tool_calls   tool calls that only serve Ghost-ALICE governance (see GOV_* below)
  stop_blocks      Stop hook_blocking_error attachments, with reason codes parsed from "[completion-gate] <code>:"
  output_tokens    sum of usage.output_tokens over distinct assistant message ids
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

GOV_SKILLS = {'task-router', 'boundary-contract', 'verification-before-completion', 'using-coding-convention',
              'session-intent-analyzer', 'merge-companion', 'autopilot-mode'}
GOV_COMMAND = re.compile(r'session_intent_ledger|response_route|completion_assessment|autopilot|merge-companion|pending-merges')
REASON = re.compile(r'\[completion-gate\]\s*([a-z0-9-]+)')
NOT_TYPED = ('Stop hook feedback', '<task-notification', '<system-reminder', '[SYSTEM NOTIFICATION', '<command-name>',
             '<local-command', 'Caveat:')


def group_of(project_dir: str) -> str:
    """Coarse, path-free label for the folder a session ran in."""
    name = project_dir.lower()
    for label in ('daily-off', 'daily-on', 'ghost-chat-grader', 'ghost-chat-bench', 'life-check', 'life-grader', 'ga-o1'):
        if label in name:
            return label
    if name.endswith('ghost-alice'):
        return 'ghost-alice'
    if 'scratch' in name:
        return 'scratch'
    return 'other'


def typed_text(entry: dict) -> str | None:
    if entry.get('type') != 'user' or entry.get('isMeta') or entry.get('isSidechain'):
        return None
    content = (entry.get('message') or {}).get('content')
    if isinstance(content, str):
        content = [dict(type='text', text=content)]
    if not isinstance(content, list) or any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
        return None
    # A typed prompt can follow injected context blocks (for example a leading <system-reminder>) in the same entry.
    typed = [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text'
             and b.get('text', '').strip() and not b['text'].lstrip().startswith(NOT_TYPED)]
    return '\n'.join(typed) if typed else None


def is_governance(block: dict) -> bool:
    name, args = block.get('name', ''), block.get('input') or {}
    if name == 'Skill':
        return str(args.get('skill', '')).split(':')[-1] in GOV_SKILLS
    if name in ('Bash', 'PowerShell'):
        return bool(GOV_COMMAND.search(str(args.get('command', ''))))
    return False


def session_metrics(path: Path) -> dict:
    turns = tool_calls = gov_calls = 0
    reasons: Counter = Counter()
    tokens: dict = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get('isSidechain'):
            continue
        if typed_text(entry) is not None:
            turns += 1
        message = entry.get('message') or {}
        if entry.get('type') == 'assistant':
            for block in message.get('content') or []:
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    tool_calls += 1
                    gov_calls += is_governance(block)
            usage = message.get('usage') or {}
            if message.get('id') and isinstance(usage.get('output_tokens'), int):
                tokens[message['id']] = usage['output_tokens']
        attachment = entry.get('attachment') or {}
        if attachment.get('type') == 'queued_command' and str(attachment.get('prompt', '')).strip():
            turns += 1  # a message the person typed while the assistant was still working
        if attachment.get('type') == 'hook_blocking_error' and attachment.get('hookEvent') == 'Stop':
            text = json.dumps(attachment.get('blockingError'), ensure_ascii=False)
            reasons[(REASON.search(text) or [None, 'other'])[1]] += 1
    return dict(session=path.stem[:8], group=group_of(path.parent.name), user_turns=turns, tool_calls=tool_calls,
                gov_tool_calls=gov_calls, stop_blocks=sum(reasons.values()), stop_reasons=dict(reasons),
                output_tokens=sum(tokens.values()))


def collect(projects: Path, min_turns: int = 1) -> list[dict]:
    # Accept either the projects root (one folder per project) or a single project folder.
    paths = sorted(projects.glob('*/*.jsonl')) or sorted(projects.glob('*.jsonl'))
    rows = [session_metrics(p) for p in paths]
    return [r for r in rows if r['user_turns'] >= min_turns]


def summarize(rows: list[dict]) -> dict:
    groups: dict = {}
    for row in rows:
        g = groups.setdefault(row['group'], Counter())
        g['sessions'] += 1
        g['sessions_blocked'] += row['stop_blocks'] > 0
        for key in ('user_turns', 'tool_calls', 'gov_tool_calls', 'stop_blocks', 'output_tokens'):
            g[key] += row[key]
        for reason, n in row['stop_reasons'].items():
            g['reason:' + reason] += n
    out = {}
    for name, g in sorted(groups.items()):
        turns = g['user_turns'] or 1
        out[name] = dict(g, blocks_per_turn=round(g['stop_blocks'] / turns, 2),
                         gov_calls_per_turn=round(g['gov_tool_calls'] / turns, 2),
                         gov_share_of_tool_calls=round(g['gov_tool_calls'] / (g['tool_calls'] or 1), 2),
                         output_tokens_per_turn=round(g['output_tokens'] / turns))
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--projects', type=Path, default=Path.home() / '.claude' / 'projects')
    parser.add_argument('--json', type=Path, help='write per-session rows and group summary as JSON')
    parser.add_argument('--min-turns', type=int, default=1)
    args = parser.parse_args(argv)
    rows = collect(args.projects, args.min_turns)
    summary = summarize(rows)
    if args.json:
        args.json.write_text(json.dumps(dict(sessions=rows, groups=summary), ensure_ascii=False, indent=1),
                             encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
