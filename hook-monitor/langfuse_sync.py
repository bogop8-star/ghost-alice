"""Send hook-monitor results to Langfuse.

For each judged session (an `assessment` row in captures/runs.jsonl) `sync` sends:
- the case as a Langfuse dataset item (dataset `ghost-alice-benchmark`),
- the human verdict as session scores (one per failure condition plus an overall result),
- the session's explained hook flow (see below).
`sync_session` sends only the explained hook flow of one session, judged or not.

The hook flow is the timeline that the monitor shows (timeline.py + explain.py): one trace per user turn
and one observation per step, carrying the same Korean explanation (what happened, why, how to resume).
Sent: hook judgments and their original messages, ledger event kinds, refused ledger commands.
Not sent: conversation text, user input previews and the intent summaries stored in the ledger.

Claude Code's own conversation is sent separately by the Langfuse Claude Code plugin;
both use the Claude session ID as the Langfuse session ID, so they appear together.
Hook records carry the same user id as the plugin's records (see `user_id`).

Langfuse keeps traces and observations immutable: a record sent again with the same id is stored as a duplicate,
not as an update, and duplicates inflate metrics (https://langfuse.com/faq/all/tracing-data-updates).
A turn is therefore sent exactly once, after it has ended. captures/langfuse-sent/<session>.json remembers
which turns were sent to which Langfuse project. Scores and dataset items may be sent again: Langfuse
overwrites those by id.
Dependencies: Python 3.11+ standard library only.
"""
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import explain

DATASET = 'ghost-alice-benchmark'
SERVICE = 'ghost-alice-hook-monitor'
MAX_TEXT = 4000
KEYS = ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_BASE_URL')
PLUGIN_ID = 'langfuse-observability@langfuse-observability'
# Where Claude Code keeps the options of the Langfuse plugin, including the User ID it attaches to conversations.
PLUGIN_SETTINGS = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'settings.json'
SENT_DIR = Path(__file__).resolve().parent / 'captures' / 'langfuse-sent'
OTEL_PATH = '/api/public/otel/v1/traces'


class SyncError(Exception):
    pass


def _env_file(workspace):
    """KEY=VALUE pairs of <workspace>/.env (the first value of a repeated key); {} when the file is missing."""
    path = Path(workspace) / '.env'
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            if sep:
                values.setdefault(key.strip().removeprefix('export ').strip(), value.strip().strip('"').strip("'"))
    return values


def load_config(workspace):
    """Read Langfuse keys from the environment, then from <workspace>/.env."""
    values = {k: os.environ.get(k, '') for k in KEYS}
    if not all(values[k] for k in KEYS[:2]):
        saved = _env_file(workspace)
        for key in KEYS:
            values[key] = values[key] or saved.get(key, '')
    values['LANGFUSE_BASE_URL'] = (values['LANGFUSE_BASE_URL'] or 'https://cloud.langfuse.com').rstrip('/')
    return values


def user_id(workspace):
    """User id attached to every hook trace, so hook records are labelled like the conversation records.

    LANGFUSE_USER_ID from the environment, then from <workspace>/.env, then the User ID configured for the
    Langfuse Claude Code plugin (PLUGIN_SETTINGS). '' when none is set.
    """
    own = os.environ.get('LANGFUSE_USER_ID') or _env_file(workspace).get('LANGFUSE_USER_ID')
    if own:
        return own.strip()
    try:
        settings = json.loads(PLUGIN_SETTINGS.read_text(encoding='utf-8-sig'))
        value = settings['pluginConfigs'][PLUGIN_ID]['options']['LANGFUSE_USER_ID']
    except (OSError, ValueError, KeyError, TypeError):
        return ''
    return value.strip() if isinstance(value, str) else ''


def configured(workspace):
    cfg = load_config(workspace)
    return bool(cfg['LANGFUSE_PUBLIC_KEY'] and cfg['LANGFUSE_SECRET_KEY'])


def _id(*parts, length=32):
    return hashlib.sha256('|'.join(str(p) for p in parts).encode('utf-8')).hexdigest()[:length]


def _text(value):
    value = '' if value is None else str(value)
    return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + ' …(truncated)'


def _time(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.astimezone()


class Client:
    def __init__(self, cfg):
        token = base64.b64encode(f"{cfg['LANGFUSE_PUBLIC_KEY']}:{cfg['LANGFUSE_SECRET_KEY']}".encode()).decode()
        self.base = cfg['LANGFUSE_BASE_URL']
        self.headers = {'Authorization': 'Basic ' + token, 'Content-Type': 'application/json'}

    def post(self, path, body, extra_headers=None):
        request = urllib.request.Request(self.base + path, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                         headers={**self.headers, **(extra_headers or {})}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode('utf-8', 'replace')[:300]
            raise SyncError(f'{path} → HTTP {err.code}: {detail}') from err
        except urllib.error.URLError as err:
            raise SyncError(f'{path} → {err.reason}') from err
        return json.loads(raw) if raw.strip() else {}


# ---- explained hook flow -> OTel spans -----------------------------------------------------

OUTCOME_LABEL = {'ok': '정상', 'warn': '주의', 'resumed': '막혔다가 다시 진행', 'unresolved': '막힘 · 미해결', 'error': '훅 오류'}
LANGFUSE_LEVEL = {'warn': 'WARNING', 'block': 'WARNING', 'error': 'ERROR'}


def _attr(key, value):
    if isinstance(value, bool):
        return {'key': key, 'value': {'boolValue': value}}
    if isinstance(value, list):
        return {'key': key, 'value': {'arrayValue': {'values': [{'stringValue': str(v)} for v in value]}}}
    return {'key': key, 'value': {'stringValue': str(value)}}


def _nanos(moment):
    return str(int(moment.timestamp() * 1_000_000_000))


def _step_span(session, turn, number, step, trace_id, root_id, stage_labels, level_labels, trace_attrs):
    first_end = _time(step.get('ts'))
    last_end = _time(step.get('ts_end')) or first_end
    count = int(step.get('count') or 1)
    # One run: the hook's own duration. A collapsed group: from its first run to its last.
    start = first_end - timedelta(seconds=float(step.get('duration_s') or 0)) if count == 1 else first_end
    level = step.get('level', 'ok')
    stage = stage_labels.get(step.get('stage'), '')
    result = level_labels.get(level, level)
    output = {'결과': result, '요약': step.get('title', '')}
    if level != 'ok':
        for key, label in (('why', '왜'), ('resume', '다시 진행하려면'), ('improve', '개선 힌트')):
            if step.get(key):
                output[label] = step[key]
    # Ledger steps carry no original text here: the agent's intent summaries stay on this computer.
    if step.get('raw') and step.get('source') != 'ledger':
        output['원문'] = _text(step['raw'])
    name = f'{stage} · {step.get("name", "")}' + (f' ×{count}' if count > 1 else '') + (f' → {result}' if level != 'ok' else '')
    attrs = trace_attrs + [
        _attr('langfuse.observation.type', 'event' if start == last_end else 'span'),
        _attr('langfuse.observation.input', json.dumps({'단계': stage, '실행': step.get('name', ''), '횟수': count}, ensure_ascii=False)),
        _attr('langfuse.observation.output', json.dumps(output, ensure_ascii=False)),
        _attr('langfuse.observation.metadata.result', level),
        _attr('langfuse.observation.metadata.source', step.get('source', '')),
        _attr('langfuse.observation.metadata.count', str(count)),
    ]
    if step.get('code'):
        attrs.append(_attr('langfuse.observation.metadata.code', step['code']))
    if level in LANGFUSE_LEVEL:
        attrs += [_attr('langfuse.observation.level', LANGFUSE_LEVEL[level]),
                  _attr('langfuse.observation.status_message', step.get('title', ''))]
    return {'traceId': trace_id, 'parentSpanId': root_id,
            'spanId': _id('flow-step', ID_VERSION, session, turn['index'], number, step.get('name'), step.get('code'),
                          step.get('ts'), length=16),
            'name': name, 'kind': 1, 'startTimeUnixNano': _nanos(start), 'endTimeUnixNano': _nanos(max(start, last_end)),
            'attributes': attrs, 'status': {'code': 2 if level == 'error' else 0}}


# Part of every trace and span id. Langfuse cannot replace a stored record, so records that had to be deleted and
# uploaded again get new ids: a deletion of the old ids that Langfuse finishes late then cannot remove the new
# upload. v2 (2026-11-16): the first automatic sender had stored whole sessions several times.
ID_VERSION = 'v2'


def _trace_id(session, turn_index):
    return _id('ghost-alice-flow', ID_VERSION, session, turn_index)


def timeline_spans(data, user=''):
    """Turn an explained timeline (timeline.build) into OTel spans: one trace per turn, one observation per step.

    `user` is the Langfuse user id put on every span; '' sends none.
    """
    session = data['session']
    stage_labels = {stage['key']: stage['label'] for stage in data.get('stages') or explain.STAGES}
    level_labels = data.get('level_labels') or explain.LEVEL_LABEL
    spans = []
    for turn in data.get('turns', []):
        trace_id = _trace_id(session, turn['index'])
        root_id = _id('flow-root', ID_VERSION, session, turn['index'], length=16)
        label = 'session start' if turn['index'] == 0 else f'turn {turn["index"]}'
        outcome = turn.get('outcome', 'ok')
        codes = list(dict.fromkeys(f['code'] for f in turn.get('findings', []) if f.get('code')))
        tags = ['ghost-alice', f'ghost-alice:{outcome}'] + (['ghost-alice:block'] if turn.get('blocks') else []) \
            + [f'ghost-alice:{code}' for code in codes[:6]]
        # Langfuse v4 filters by session, user, trace name and tags only when every span of the trace repeats them.
        trace_attrs = [_attr('langfuse.session.id', session), _attr('langfuse.trace.name', f'Ghost-ALICE · {label}'),
                       _attr('langfuse.trace.tags', tags)] + ([_attr('langfuse.user.id', user)] if user else [])
        children = [_step_span(session, turn, number, step, trace_id, root_id, stage_labels, level_labels, trace_attrs)
                    for number, step in enumerate(turn.get('steps', [])) if _time(step.get('ts'))]
        if not children:
            continue
        summary = {
            '결과': OUTCOME_LABEL.get(outcome, outcome), '요약': turn.get('headline', ''),
            '단계별': {stage_labels.get(key, key): level_labels.get(value.get('level'), value.get('level'))
                     for key, value in (turn.get('stages') or {}).items()},
            '참고': [note['text'] for note in turn.get('notes', [])],
            '막힘·주의': [f'{f["title"]}' + (f' ×{f["count"]}' if f.get('count', 1) > 1 else '') for f in turn.get('findings', [])],
        }
        asked = json.dumps({'턴': turn.get('label', label), '입력 종류': turn.get('input_kind_label') or '확인 안 됨',
                            '도구 호출': turn.get('tool_calls', 0)}, ensure_ascii=False)
        answered = json.dumps(summary, ensure_ascii=False)
        spans.append({'traceId': trace_id, 'spanId': root_id, 'name': f'Ghost-ALICE · {label}', 'kind': 1,
                      'startTimeUnixNano': min(c['startTimeUnixNano'] for c in children),
                      'endTimeUnixNano': max(c['endTimeUnixNano'] for c in children),
                      # The root observation's input and output are what Langfuse v4 shows for the whole trace.
                      'attributes': trace_attrs + [
                                     _attr('langfuse.observation.input', asked), _attr('langfuse.observation.output', answered),
                                     _attr('langfuse.trace.metadata.outcome', outcome),
                                     _attr('langfuse.trace.metadata.blocks', str(turn.get('blocks', 0))),
                                     _attr('langfuse.trace.metadata.pending_inputs', str(turn.get('pending_at_end', 0))),
                                     _attr('langfuse.trace.metadata.route_registered', bool(turn.get('route_registered')))]
                      + ([_attr('langfuse.observation.level', 'WARNING'),
                          _attr('langfuse.observation.status_message', turn.get('headline', ''))] if outcome != 'ok' else []),
                      'status': {'code': 0}})
        spans.extend(children)
    return spans


def _otel_body(spans):
    return {'resourceSpans': [{'resource': {'attributes': [_attr('service.name', SERVICE)]},
                               'scopeSpans': [{'scope': {'name': SERVICE}, 'spans': spans}]}]}


# ---- cases and verdicts --------------------------------------------------------------------

def _conditions(case):
    raw = case.get('conditions') or ''
    return [c.strip() for c in (raw if isinstance(raw, list) else str(raw).splitlines()) if c and c.strip()]


def case_item(case):
    return {'datasetName': DATASET, 'id': 'case-' + _id('case', case.get('id'), length=24),
            'input': {'case_id': case.get('id'), 'context': case.get('context'), 'prompt': case.get('prompt')},
            'expectedOutput': {'expected': case.get('expected'), 'failure_conditions': _conditions(case)},
            'metadata': {'case_id': case.get('id'), 'source': SERVICE}}


def verdict_scores(run):
    case = run.get('case') or {}
    session, saved = run.get('session'), run.get('saved_at')
    order = {c: i for i, c in enumerate(_conditions(case), 1)}
    common = {'case_id': case.get('id'), 'phase': run.get('phase'), 'saved_at': saved}
    scores = []
    for n, (condition, value) in enumerate((run.get('verdict') or {}).items(), 1):
        index = order.get(condition, n)
        scores.append({'id': _id('score', session, saved, condition), 'sessionId': session,
                       'name': f"{case.get('id') or 'case'} · 조건 {index}", 'value': str(value),
                       'dataType': 'CATEGORICAL', 'comment': condition, 'metadata': {**common, 'condition': condition}})
    failed = any(v == 'fail' for v in (run.get('verdict') or {}).values())
    scores.append({'id': _id('score', session, saved, 'overall'), 'sessionId': session, 'name': 'case-result',
                   'value': 'fail' if failed else 'pass', 'dataType': 'CATEGORICAL',
                   'comment': _text(run.get('note')), 'metadata': common})
    return scores


# ---- entry point ---------------------------------------------------------------------------

def _read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _connect(workspace):
    cfg = load_config(workspace)
    if not (cfg['LANGFUSE_PUBLIC_KEY'] and cfg['LANGFUSE_SECRET_KEY']):
        raise SyncError(f'Langfuse 키가 없습니다. 환경 변수나 {Path(workspace) / ".env"}에 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY를 넣으세요.')
    return cfg, Client(cfg)


# ---- each turn is sent once ------------------------------------------------------------------

def finished_traces(data, final=False):
    """Trace ids of the turns that will not change any more, so they may be sent.

    A turn is finished when a later turn exists, or when its answer ended without an unresolved block.
    `final` (the session is over) finishes every turn.
    """
    turns = data.get('turns', [])
    return {_trace_id(data['session'], turn['index']) for position, turn in enumerate(turns)
            if final or position < len(turns) - 1 or (turn.get('ended') and turn.get('outcome') != 'unresolved')}


def target_of(cfg):
    """Names the Langfuse project that records go to, so a different project still receives every turn once."""
    return cfg['LANGFUSE_BASE_URL'] + '|' + _id('public-key', cfg['LANGFUSE_PUBLIC_KEY'], length=12)


def sent_file(session, sent_dir=None):
    return Path(sent_dir or SENT_DIR) / f'{session}.json'


def load_sent(path):
    """Return {target: [trace ids already sent]} of one session; {} when nothing was sent yet."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))['sent']
        return {str(target): list(traces) for target, traces in saved.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
        # Sending everything again would duplicate records in Langfuse for good, so stop instead of guessing.
        raise SyncError(f'전송 기록 파일을 읽지 못해 보내지 않았습니다: {path} ({type(err).__name__})') from err


def save_sent(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'sent': records}, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


class _SendLock:
    """Lets one send per session run at a time, across the monitor and the automatic sender."""

    def __init__(self, path, wait=30, stale=600):
        self.path, self.wait, self.stale = Path(path), wait, stale

    def __enter__(self):
        deadline = time.monotonic() + self.wait
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:  # left behind by a process that died
                        self.path.unlink()
                        continue
                except OSError:
                    continue
                if time.monotonic() >= deadline:
                    raise SyncError('같은 세션의 다른 전송이 아직 끝나지 않아 보내지 않았습니다.') from None
                time.sleep(0.2)

    def __exit__(self, *_):
        try:
            self.path.unlink()
        except OSError:
            pass


def _send_finished(client, cfg, data, spans, sent_dir, final):
    """Send the finished turns that this Langfuse project has not received yet. Returns counts."""
    path = sent_file(data['session'], sent_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    target, finished = target_of(cfg), finished_traces(data, final)
    traces = {}
    for span in spans:
        traces.setdefault(span['traceId'], []).append(span)
    with _SendLock(path.with_suffix('.lock')):
        records = load_sent(path)
        already = set(records.get(target, []))
        pending = [trace for trace in traces if trace in finished and trace not in already]
        batches = []
        for trace in pending:  # a trace is never split, so a turn arrives whole or not at all
            if batches and sum(len(traces[t]) for t in batches[-1]) + len(traces[trace]) <= 200:
                batches[-1].append(trace)
            else:
                batches.append([trace])
        sent = set(already)
        for batch in batches:
            # Without this header Langfuse Cloud may show the data up to 10 minutes late
            # (https://langfuse.com/integrations/native/opentelemetry).
            client.post(OTEL_PATH, _otel_body([span for trace in batch for span in traces[trace]]),
                        {'x-langfuse-ingestion-version': '4'})
            sent.update(batch)
            records[target] = sorted(sent)
            save_sent(path, records)  # after every request, so a later failure cannot cause a resend of this batch
    return {'traces': len(pending), 'observations': sum(len(traces[trace]) - 1 for trace in pending),
            'skipped': sum(1 for trace in traces if trace in already),
            'waiting': sum(1 for trace in traces if trace not in finished and trace not in already),
            'trace_ids': pending}


def sync_session(workspace, data, sent_dir=None, final=False):
    """Send the finished, not yet sent turns of one session's explained hook flow (timeline.build) to Langfuse.

    `final` marks the last send of a session: it also sends a turn that never ended.
    Returns counts: `traces`/`observations` sent now, `skipped` turns sent earlier, `waiting` turns not finished.
    """
    spans = timeline_spans(data, user_id(workspace)) if data.get('turns') else []
    if not spans:
        raise SyncError('이 세션에는 보낼 훅 기록이 없습니다.')
    cfg, client = _connect(workspace)
    return {'session': data['session'], **_send_finished(client, cfg, data, spans, sent_dir, final),
            'host': cfg['LANGFUSE_BASE_URL'], 'synced_at': datetime.now(timezone.utc).isoformat()}


def sync(workspace, runs_file, case_file, build_timeline, sent_dir=None):
    """Send every judged session to Langfuse. Returns counts; raises SyncError on the first failed request.

    `build_timeline(session)` returns that session's explained hook flow (timeline.build).
    Cases and verdicts are sent every time; of the hook flow only the finished turns not sent before.
    """
    cfg, client = _connect(workspace)
    user = user_id(workspace)
    runs = [r for r in _read_jsonl(Path(runs_file)) if r.get('kind') == 'assessment' and r.get('session')]
    cases = {}
    if Path(case_file).exists():
        current = json.loads(Path(case_file).read_text(encoding='utf-8'))
        if current.get('id'):
            cases[current['id']] = current
    for run in runs:
        # Older assessment rows carry no case snapshot; the monitor shows them with the current case, so do the same.
        if not (run.get('case') or {}).get('id') and cases:
            run['case'] = next(iter(cases.values()))
        if (run.get('case') or {}).get('id'):
            cases.setdefault(run['case']['id'], run['case'])

    result = {'cases': 0, 'scores': 0, 'sessions': 0, 'hook_runs': 0, 'traces': 0, 'missing_hook_logs': []}
    if cases:
        client.post('/api/public/datasets', {'name': DATASET, 'description': 'Ghost-ALICE hook-monitor benchmark cases'})
    for case in cases.values():
        client.post('/api/public/dataset-items', case_item(case))
        result['cases'] += 1
    for run in runs:
        for score in verdict_scores(run):
            client.post('/api/public/scores', score)
            result['scores'] += 1
    for session in sorted({r['session'] for r in runs}):
        data = build_timeline(session)
        spans = timeline_spans(data, user) if data.get('turns') else []
        if not spans:
            result['missing_hook_logs'].append(session)
            continue
        sent = _send_finished(client, cfg, data, spans, sent_dir, False)
        result['sessions'] += 1
        result['traces'] += sent['traces']
        result['hook_runs'] += sent['observations']
    result['host'] = cfg['LANGFUSE_BASE_URL']
    result['synced_at'] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == '__main__':
    # `python hook-monitor/langfuse_sync.py` sends every judged session; add a session ID to send only that session's
    # hook flow, and `--final` after it when the session is over and its unfinished turn should be sent too.
    import sys

    import server
    import timeline

    def build(session):
        return timeline.build(session, server.TIMELINE_CONFIG)

    if len(sys.argv) > 1:
        outcome = sync_session(server.WORKSPACE, build(sys.argv[1]), final='--final' in sys.argv[2:])
    else:
        outcome = sync(server.WORKSPACE, server.RUNS_FILE, server.CASE_FILE, build)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
