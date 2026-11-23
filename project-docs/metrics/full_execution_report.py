"""Full Ghost-ALICE execution aggregate from local transcripts and hook logs. Read-only; writes one JSON file."""
import collections
import hashlib
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# langfuse_transcript_send.py (turn parser and price table) lives in the hook-monitor folder; override with HOOK_MONITOR_DIR.
sys.path.insert(0, os.environ.get('HOOK_MONITOR_DIR') or str(Path.home() / 'hook-monitor'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import langfuse_transcript_send as lt
import governance_metrics as gm

KST = timezone(timedelta(hours=9))
SWITCH = '2026-11-16T05:58'  # UTC, install moved to the main line at 14:58 KST
TOPIC = re.compile(r'ghost[-_ ]?alice|고스트|앨리스|langfuse|거버넌스|skproject|autopilot|오토파일럿', re.I)
AUTO = {'ghost-chat-bench', 'ghost-chat-grader', 'life-check', 'life-grader', 'daily-on', 'daily-off', 'ga-o1'}
IDLE = 300


def ns(ts):
    return lt.to_ns(ts)


def day(ts):
    try:
        return datetime.fromisoformat(str(ts).replace('Z', '+00:00')).astimezone(KST).strftime('%m-%d')
    except ValueError:
        return '?'


def pct(sorted_values, q):
    return sorted_values[min(int(len(sorted_values) * q), len(sorted_values) - 1)] if sorted_values else 0


def category(path, turns):
    name = path.parent.name
    group = gm.group_of(name)
    if group in AUTO or 'ghost-chat' in name.lower():
        return 'auto-test', group if group in AUTO else 'ghost-chat-bench'
    if re.search(r'ghost[-_]alice', name, re.I):
        return 'ga-work', 'ghost-alice folder'
    if any(TOPIC.search(t['prompt']) for t in turns):
        return 'ga-work', 'other folder, Ghost-ALICE topic'
    return 'excluded', group


seen_msg, seen_turn = set(), set()
cats = collections.defaultdict(lambda: collections.Counter())
sub = collections.defaultdict(lambda: collections.Counter())
by_day = collections.defaultdict(lambda: collections.Counter())
by_model = collections.defaultdict(lambda: collections.Counter())
kinds = collections.Counter()
tools = collections.defaultdict(collections.Counter)
skills = collections.Counter()
blocks = collections.defaultdict(collections.Counter)
block_era = collections.defaultdict(collections.Counter)
turn_secs = collections.defaultdict(list)
turn_cost = collections.defaultdict(list)
turn_tools = collections.defaultdict(list)
sessions_out = []
dup_turns = 0
ga_session_ids = set()

for path in sorted((Path.home() / '.claude' / 'projects').glob('*/*.jsonl')):
    sid = path.stem
    turns = lt.parse_turns(path)
    if not turns:
        continue
    cat, subcat = category(path, turns)
    cats[cat]['sessions'] += 1
    sub[(cat, subcat)]['sessions'] += 1
    if cat == 'excluded':
        cats[cat]['turns'] += len(turns)
        continue
    ga_session_ids.add(sid)
    # active seconds: gaps of at most IDLE seconds between consecutive transcript rows
    stamps = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            t = json.loads(line).get('timestamp')
        except (ValueError, AttributeError):
            continue
        v = ns(t)
        if v:
            stamps.append(v)
    stamps.sort()
    active = sum(min((b - a) / 1e9, IDLE) for a, b in zip(stamps, stamps[1:]) if (b - a) / 1e9 <= IDLE)
    s = collections.Counter()
    for t in turns:
        key = hashlib.sha256((t['prompt'] + '|' + str(t['ts'])).encode('utf-8')).hexdigest()
        if key in seen_turn:
            dup_turns += 1
            continue
        seen_turn.add(key)
        d = day(t['ts'])
        era = 'new' if str(t['ts']) >= SWITCH else 'old'
        cost = 0.0
        for m in t['messages']:
            if m['id'] and m['id'] in seen_msg:
                continue
            seen_msg.add(m['id'])
            tokens, c = lt.usage_and_cost(m['model'], m['usage'])
            if not c:
                continue
            cost += c['total']
            by_model[m['model']]['cost'] += c['total']
            by_model[m['model']]['messages'] += 1
            by_model[m['model']]['out'] += tokens.get('output', 0)
            by_model[m['model']]['cache_read'] += tokens.get('cache_read_input_tokens', 0)
            by_model[m['model']]['cache_write'] += tokens.get('cache_write_1h_input_tokens', 0) + tokens.get('cache_write_5m_input_tokens', 0)
            for k, v in c.items():
                if k != 'total':
                    kinds[k] += v
        gov = 0
        for call in t['tools']:
            name = call['name']
            tools[cat][name] += 1
            block = dict(name=name, input=call['input'] if isinstance(call['input'], dict) else {})
            g = gm.is_governance(block)
            gov += g
            if name == 'Skill':
                skills[str((call['input'] or {}).get('skill', '?'))] += 1
        for b in t['blocks']:
            m = gm.REASON.search(b['reason'])
            reason = m.group(1) if m else 'other'
            blocks[cat][reason] += 1
            block_era[era][reason] += 1
        dur = None
        a, b_ = ns(t['ts']), ns(t['end'])
        if a and b_ and b_ >= a:
            dur = (b_ - a) / 1e9
        for target in (cats[cat], sub[(cat, subcat)], by_day[d], s, by_day[d + '|' + cat]):
            target['turns'] += 1
            target['tools'] += len(t['tools'])
            target['gov_tools'] += gov
            target['blocks'] += len(t['blocks'])
            target['cost'] += cost
        if dur is not None and dur <= 3600:
            turn_secs[cat].append(dur)
        turn_cost[cat].append(cost)
        turn_tools[cat].append(len(t['tools']))
    cats[cat]['active_secs'] += active
    sub[(cat, subcat)]['active_secs'] += active
    if stamps:
        by_day[day(datetime.fromtimestamp(stamps[0] / 1e9, timezone.utc).isoformat())]['active_secs'] += active
    sessions_out.append(dict(session=sid[:8], cat=cat, sub=subcat, turns=s['turns'], tools=s['tools'], gov=s['gov_tools'],
                             blocks=s['blocks'], cost=round(s['cost'], 2), active_min=round(active / 60, 1)))

# hooks, only for Ghost-ALICE sessions
hook = {'old': collections.defaultdict(list), 'new': collections.defaultdict(list)}
hook_tot = {'old': collections.Counter(), 'new': collections.Counter()}
gate = collections.Counter()
for f in (Path.home() / '.ghost-alice' / 'session-logs' / 'claude').glob('*/strict-hook-output.jsonl'):
    if f.parent.name not in ga_session_ids:
        continue
    for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        era = 'new' if str(r.get('ts', '')) >= SWITCH else 'old'
        d = r.get('observed_duration_s')
        name = f"{r.get('event')}:{r.get('hook_id')}"
        hook_tot[era]['runs'] += 1
        hook_tot[era]['nonzero_exit'] += str(r.get('exit_code', 0)) not in ('0', '')
        if isinstance(d, (int, float)):
            hook[era][name].append(d)
            hook_tot[era]['secs'] += d
        hook_tot[era]['tool_calls'] += name == 'PreToolUse:tool-checkpoint'
        out = str(r.get('stdout') or '')
        if '"decision": "block"' in out or '"decision":"block"' in out:
            m = gm.REASON.search(out)
            gate[(era, r.get('event'), m.group(1) if m else 'other')] += 1


def dist(values):
    v = sorted(values)
    return dict(n=len(v), median=round(statistics.median(v), 2) if v else 0, p90=round(pct(v, .9), 2), max=round(v[-1], 2) if v else 0,
                mean=round(statistics.mean(v), 2) if v else 0)


result = dict(
    generated=datetime.now(KST).isoformat(timespec='seconds'),
    categories={k: dict(v) for k, v in cats.items()},
    subcategories={f'{a} / {b}': dict(v) for (a, b), v in sorted(sub.items())},
    duplicate_turns_skipped=dup_turns,
    by_day={k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in sorted(by_day.items())},
    by_model={k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in by_model.items()},
    cost_kinds={k: round(v, 2) for k, v in kinds.items()},
    tools={c: t.most_common(25) for c, t in tools.items()},
    skills=skills.most_common(30),
    blocks={c: dict(v) for c, v in blocks.items()},
    blocks_by_era={e: dict(v) for e, v in block_era.items()},
    turn_seconds={c: dist(v) for c, v in turn_secs.items()},
    turn_cost={c: dist(v) for c, v in turn_cost.items()},
    turn_tools={c: dist(v) for c, v in turn_tools.items()},
    top_sessions=sorted(sessions_out, key=lambda r: -r['cost'])[:12],
    hooks={era: dict(total=dict(hook_tot[era]), per_hook={k: dict(dist(v), total_s=round(sum(v))) for k, v in
                                                           sorted(hook[era].items(), key=lambda kv: -sum(kv[1]))}) for era in hook},
    gate_blocks_in_hook_log={f'{a} {b} {c}': n for (a, b, c), n in gate.most_common()},
)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('full-execution.json')
out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps({k: result[k] for k in ('categories', 'subcategories', 'duplicate_turns_skipped', 'by_model', 'cost_kinds',
                                         'blocks', 'blocks_by_era', 'turn_seconds', 'turn_cost', 'turn_tools')}, ensure_ascii=False, indent=1))
