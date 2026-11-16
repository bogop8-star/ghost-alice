"""Classify the tools used in each turn that a Stop route-unavailable block ended.

For every route-unavailable Stop block in local Claude Code transcripts, look at the tool calls made since the
last typed input (or since the previous block in the same input) and label the turn: read-only, read-only plus a
shared-history log append, other shell commands, file edits, or MCP/other tools. Governance-only calls are ignored.
Reads local files only and prints counts per group; no prompt, answer or command text is printed.

Usage: python route_block_tools.py [PROJECTS_DIR]   (default ~/.claude/projects)

The read-only shell test is a heuristic: a command-prefix allow-list plus a write-hint deny-list (README.md).
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import governance_metrics as gm  # noqa: E402

READ_TOOLS = {'Read', 'Grep', 'Glob', 'LS', 'WebSearch', 'WebFetch', 'ToolSearch', 'NotebookRead', 'TodoWrite',
              'Skill', 'mcp__ccd_turn__update_plan', 'mcp__ccd_turn__wrap_up'}
READ_CMD = re.compile(r'^\s*(cd\s+\S+\s*(&&|;)\s*)?(cat|ls|dir|grep|rg|head|tail|wc|find|pwd|echo|type|sed\s+-n|'
                      r'git\s+(status|log|diff|show|branch|rev-parse|ls-remote|worktree\s+list)|Get-Content|Get-ChildItem)\b')
WRITE_HINT = re.compile(r'(^|[^2])>\s*[^&]|\btee\b|\brm\b|\bmv\b|\bcp\b|\bmkdir\b|git\s+(commit|push|add|checkout|reset)'
                        r'|Set-Content|Out-File|-i\b')
HISTORY_READ = re.compile(r'history_tool\.py"?\s+read')
HISTORY_ADD = re.compile(r'history_tool\.py"?\s+add')
FOR_LOOP = re.compile(r'\s*for\s+\w+\s+in\b')


def kind(block: dict) -> str:
    name, args = block.get('name', ''), block.get('input') or {}
    if name in READ_TOOLS:
        return 'read'
    if name in ('Bash', 'PowerShell'):
        cmd = str(args.get('command', ''))
        if gm.GOV_COMMAND.search(cmd):
            return 'governance'
        if HISTORY_READ.search(cmd):
            return 'read'
        if HISTORY_ADD.search(cmd):
            return 'log'
        if (READ_CMD.search(cmd) or FOR_LOOP.match(cmd)) and not WRITE_HINT.search(cmd):
            return 'read'
        return 'shell-other'
    if name in ('Edit', 'Write', 'NotebookEdit', 'MultiEdit'):
        return 'write'
    return 'mcp-other' if name.startswith('mcp__') else 'other'


def label(kinds: set[str]) -> str:
    kinds = kinds - {'governance'}
    if not kinds:
        return 'governance-only'
    if kinds <= {'read'}:
        return 'read-only'
    if kinds <= {'read', 'log'}:
        return 'read-only+log'
    if 'write' in kinds:
        return 'writes'
    if 'shell-other' in kinds:
        return 'shell-other'
    return 'mcp/other'


def classify(projects: Path) -> dict[str, Counter]:
    groups: dict[str, Counter] = defaultdict(Counter)
    paths = sorted(projects.glob('*/*.jsonl')) or sorted(projects.glob('*.jsonl'))
    for path in paths:
        group, kinds = gm.group_of(path.parent.name), []
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get('isSidechain'):
                continue
            attachment = entry.get('attachment') or {}
            if gm.typed_text(entry) is not None or attachment.get('type') == 'queued_command':
                kinds = []
            if entry.get('type') == 'assistant':
                kinds += [kind(b) for b in (entry.get('message') or {}).get('content') or []
                          if isinstance(b, dict) and b.get('type') == 'tool_use']
            if (attachment.get('type') == 'hook_blocking_error' and attachment.get('hookEvent') == 'Stop'
                    and 'route-unavailable' in json.dumps(attachment.get('blockingError'))):
                groups[group][label(set(kinds))] += 1
                kinds = []  # a later block in the same input counts only the repair turn's tools
    return groups


def main(argv=None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:] if argv is None else argv
    groups = classify(Path(args[0]) if args else Path.home() / '.claude' / 'projects')
    total = Counter()
    for counts in groups.values():
        total.update(counts)
    print('ALL', dict(total), 'total', sum(total.values()))
    for group, counts in sorted(groups.items()):
        print(group, dict(counts), 'total', sum(counts.values()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
