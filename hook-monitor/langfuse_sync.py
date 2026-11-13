"""Send hook-monitor results to Langfuse.

For each judged session (an `assessment` row in captures/runs.jsonl) this module sends:
- the case as a Langfuse dataset item (dataset `ghost-alice-benchmark`),
- the human verdict as session scores (one per failure condition plus an overall result),
- every Ghost-ALICE hook run of that session, including its decision and reason,
  as OpenTelemetry spans grouped into one trace per user turn.

Claude Code's own conversation is sent separately by the Langfuse Claude Code plugin;
both use the Claude session ID as the Langfuse session ID, so they appear together.
Sent item IDs are recorded separately for each destination project to avoid duplicate ingestion.
Dependencies: Python 3.11+ standard library only.
"""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATASET = 'ghost-alice-benchmark'
SERVICE = 'ghost-alice-hook-monitor'
MAX_TEXT = 4000
KEYS = ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_BASE_URL')


class SyncError(Exception):
    pass


def load_config(workspace):
    """Read Langfuse keys from the environment, then from <workspace>/.env."""
    values = {k: os.environ.get(k, '') for k in KEYS}
    env_file = Path(workspace) / '.env'
    if env_file.exists() and not all(values[k] for k in KEYS[:2]):
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            key = key.strip().removeprefix('export ').strip()
            if sep and key in KEYS and not values[key]:
                values[key] = value.strip().strip('"').strip("'")
    values['LANGFUSE_BASE_URL'] = (values['LANGFUSE_BASE_URL'] or 'https://cloud.langfuse.com').rstrip('/')
    return values


def configured(workspace):
    cfg = load_config(workspace)
    return bool(cfg['LANGFUSE_PUBLIC_KEY'] and cfg['LANGFUSE_SECRET_KEY'])


def load_member(workspace):
    """Read the uploader label independently of the selected project's API keys."""
    member = os.environ.get('LANGFUSE_MEMBER', '').strip()
    env_file = Path(workspace) / '.env'
    if not member and env_file.exists():
        for line in env_file.read_text(encoding='utf-8-sig').splitlines():
            key, sep, value = line.partition('=')
            if sep and key.strip().removeprefix('export ').strip() == 'LANGFUSE_MEMBER':
                member = value.strip().strip('"').strip("'").strip()
                break
    return member[:200]


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

    def post(self, path, body):
        request = urllib.request.Request(self.base + path, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                         headers=self.headers, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode('utf-8', 'replace')[:300]
            raise SyncError(f'{path} → HTTP {err.code}: {detail}') from err
        except urllib.error.URLError as err:
            raise SyncError(f'{path} → {err.reason}') from err
        return json.loads(raw) if raw.strip() else {}

    def get(self, path):
        request = urllib.request.Request(self.base + path, headers=self.headers, method='GET')
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as err:
            raise SyncError(f'Langfuse 인증 오류 (HTTP {err.code})') from err
        except (urllib.error.URLError, ValueError) as err:
            raise SyncError(f'Langfuse 프로젝트 확인 실패: {err}') from err


def _read_store(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_store(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def _valid_url(base):
    parsed = urlparse(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise SyncError('Langfuse 주소는 https://로 시작하는 서버 주소를 입력하세요.')
    return base.rstrip('/')


def project_info(cfg):
    projects = Client(cfg).get('/api/public/projects')
    if isinstance(projects, dict):
        projects = projects.get('data') or projects.get('projects') or []
    if not isinstance(projects, list) or len(projects) != 1 or not isinstance(projects[0], dict):
        raise SyncError('이 키에 연결된 Langfuse 프로젝트를 확인하지 못했습니다.')
    item = projects[0]
    if not item.get('id') or not item.get('name'):
        raise SyncError('Langfuse 프로젝트 이름을 확인하지 못했습니다.')
    return {'project_id': str(item['id']), 'name': str(item['name'])}


def project_choices(workspace, store_path):
    saved = _read_store(store_path)
    choices = []
    if configured(workspace):
        cfg = load_config(workspace)
        try:
            name = project_info(cfg)['name'] + ' (기본 설정)'
        except SyncError:
            name = '기본 프로젝트 (.env)'
        choices.append({'id': 'default', 'name': name, 'host': cfg['LANGFUSE_BASE_URL']})
    for key, item in saved.items():
        if isinstance(item, dict):
            choices.append({'id': key, 'name': item.get('name', key), 'host': item.get('LANGFUSE_BASE_URL', '')})
    return choices


def register_project(store_path, base, public, secret):
    cfg = {'LANGFUSE_BASE_URL': _valid_url(str(base).strip()),
           'LANGFUSE_PUBLIC_KEY': str(public).strip(), 'LANGFUSE_SECRET_KEY': str(secret).strip()}
    if not cfg['LANGFUSE_PUBLIC_KEY'] or not cfg['LANGFUSE_SECRET_KEY']:
        raise SyncError('새 프로젝트의 Public Key와 Secret Key를 모두 입력하세요.')
    info = project_info(cfg)
    key = 'project-' + _id(cfg['LANGFUSE_BASE_URL'], info['project_id'], length=20)
    saved = _read_store(store_path)
    saved[key] = {**cfg, **info}
    _write_store(store_path, saved)
    return {'id': key, 'name': info['name'], 'host': cfg['LANGFUSE_BASE_URL']}


def select_project(workspace, store_path, project_id):
    if project_id == 'default':
        cfg = load_config(workspace)
        if not cfg['LANGFUSE_PUBLIC_KEY'] or not cfg['LANGFUSE_SECRET_KEY']:
            raise SyncError('기본 Langfuse 키가 없습니다.')
        try:
            name = project_info(cfg)['name']
        except SyncError:
            name = '기본 프로젝트 (.env)'
        return cfg, name
    item = _read_store(store_path).get(project_id)
    if not isinstance(item, dict):
        raise SyncError('선택한 Langfuse 프로젝트를 찾을 수 없습니다.')
    return item, item['name']


# ---- Ghost-ALICE hook runs -> OTel spans ---------------------------------------------------

def _decision(row):
    """Pull the hook's judgment (decision and reason) out of its JSON stdout, if any."""
    try:
        out = json.loads(row.get('stdout') or '')
    except ValueError:
        return '', _text(row.get('stdout'))
    if not isinstance(out, dict):
        return '', _text(row.get('stdout'))
    specific = out.get('hookSpecificOutput') if isinstance(out.get('hookSpecificOutput'), dict) else {}
    decision = out.get('decision') or specific.get('permissionDecision') or ''
    reason = (out.get('reason') or specific.get('permissionDecisionReason') or specific.get('additionalContext')
              or out.get('systemMessage') or '')
    return str(decision), _text(reason)


def _attr(key, value):
    if isinstance(value, bool):
        return {'key': key, 'value': {'boolValue': value}}
    if isinstance(value, list):
        return {'key': key, 'value': {'arrayValue': {'values': [{'stringValue': str(v)} for v in value]}}}
    return {'key': key, 'value': {'stringValue': str(value)}}


def _nanos(moment):
    return str(int(moment.timestamp() * 1_000_000_000))


def hook_spans(session, rows, member=''):
    """Group one session's hook rows into turns (a turn starts at UserPromptSubmit) and build spans."""
    turns, current = [], []
    for row in sorted(rows, key=lambda r: str(r.get('ts'))):
        if row.get('event') == 'UserPromptSubmit' and current:
            turns.append(current)
            current = []
        current.append(row)
    if current:
        turns.append(current)

    spans = []
    for number, turn in enumerate(turns):
        trace_id = _id('ghost-alice-turn', session, number)
        root_id = _id('root', session, number, length=16)
        children, blocked = [], 0
        for row in turn:
            end = _time(row.get('ts'))
            if end is None:
                continue
            try:
                duration = float(row.get('observed_duration_s') or 0)
            except ValueError:
                duration = 0.0
            start = end - timedelta(seconds=duration)
            decision, reason = _decision(row)
            failed = str(row.get('exit_code', '0')) not in ('0', '')
            blocking = decision.lower() in ('block', 'deny')
            blocked += blocking
            level = 'ERROR' if failed else 'WARNING' if blocking else 'DEFAULT'
            name = f"{row.get('event')} · {row.get('hook_id')}" + (f' → {decision}' if decision else '')
            attrs = [
                _attr('langfuse.session.id', session),
                _attr('langfuse.observation.type', 'event' if duration == 0 else 'span'),
                _attr('langfuse.observation.level', level),
                _attr('langfuse.observation.input', json.dumps({'event': row.get('event'), 'hook': row.get('hook_id')})),
                _attr('langfuse.observation.output', json.dumps({'decision': decision, 'reason': reason}, ensure_ascii=False)),
                _attr('langfuse.observation.metadata.exit_code', row.get('exit_code', '')),
                _attr('langfuse.observation.metadata.visibility', row.get('visible_decision', '')),
                _attr('langfuse.observation.metadata.payload_digest', row.get('payload_digest', '')),
            ]
            if member:
                attrs.append(_attr('langfuse.observation.metadata.member', member))
            if row.get('stderr'):
                attrs.append(_attr('langfuse.observation.status_message', _text(row.get('stderr'))))
            children.append({'traceId': trace_id, 'parentSpanId': root_id,
                             'spanId': _id('hook', session, row.get('ts'), row.get('hook_id'), row.get('payload_digest'), length=16),
                             'name': name, 'kind': 1, 'startTimeUnixNano': _nanos(start), 'endTimeUnixNano': _nanos(end),
                             'attributes': attrs, 'status': {'code': 2 if failed else 0}})
        if not children:
            continue
        label = 'session start' if turn[0].get('event') != 'UserPromptSubmit' else f'turn {number}'
        tags = ['ghost-alice'] + (['ghost-alice:block'] if blocked else [])
        root_attrs = [_attr('langfuse.trace.name', f'Ghost-ALICE · {label}'),
                      _attr('langfuse.session.id', session),
                      _attr('langfuse.trace.tags', tags),
                      _attr('langfuse.trace.metadata.hook_runs', len(children)),
                      _attr('langfuse.trace.metadata.blocking_decisions', blocked)]
        if member:
            root_attrs.append(_attr('langfuse.trace.metadata.member', member))
        spans.append({'traceId': trace_id, 'spanId': root_id, 'name': f'Ghost-ALICE · {label}', 'kind': 1,
                      'startTimeUnixNano': min(c['startTimeUnixNano'] for c in children),
                      'endTimeUnixNano': max(c['endTimeUnixNano'] for c in children),
                      'attributes': root_attrs,
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


def case_item(case, member=''):
    return {'datasetName': DATASET, 'id': 'case-' + _id('case', case.get('id'), length=24),
            'input': {'case_id': case.get('id'), 'context': case.get('context'), 'prompt': case.get('prompt')},
            'expectedOutput': {'expected': case.get('expected'), 'failure_conditions': _conditions(case)},
            'metadata': {'case_id': case.get('id'), 'source': SERVICE, **({'member': member} if member else {})}}


def verdict_scores(run, member=''):
    case = run.get('case') or {}
    session, saved = run.get('session'), run.get('saved_at')
    order = {c: i for i, c in enumerate(_conditions(case), 1)}
    common = {'case_id': case.get('id'), 'phase': run.get('phase'), 'saved_at': saved,
              **({'member': member} if member else {})}
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


def pending_items(runs_file, case_file, hook_log_root, member=''):
    """Build the current saved case, score and hook items without sending them."""
    runs = [r for r in _read_jsonl(Path(runs_file)) if r.get('kind') == 'assessment' and r.get('session')]
    cases = {}
    if Path(case_file).exists():
        current = json.loads(Path(case_file).read_text(encoding='utf-8'))
        if current.get('id'):
            cases[current['id']] = current
    for run in runs:
        if not (run.get('case') or {}).get('id') and cases:
            run['case'] = next(iter(cases.values()))
        if (run.get('case') or {}).get('id'):
            cases.setdefault(run['case']['id'], run['case'])
    items = [('dataset', DATASET, {'name': DATASET, 'description': 'Ghost-ALICE hook-monitor benchmark cases'})] if cases else []
    items += [('case', case_item(case, member)['id'], case_item(case, member)) for case in cases.values()]
    items += [('score', score['id'], score) for run in runs for score in verdict_scores(run, member)]
    missing = []
    for session in sorted({r['session'] for r in runs}):
        log = Path(hook_log_root) / session / 'strict-hook-output.jsonl'
        if not log.exists():
            missing.append(session)
            continue
        items += [('span', span['traceId'] + ':' + span['spanId'], span) for span in hook_spans(session, _read_jsonl(log), member)]
    return items, missing


def _ledger_key(cfg):
    return _id(cfg['LANGFUSE_BASE_URL'], cfg['LANGFUSE_PUBLIC_KEY'])


def seed_sent(state_path, cfg, runs_file, case_file, hook_log_root):
    """Mark previously uploaded local items for this one destination (migration only)."""
    state = _read_store(state_path)
    key = _ledger_key(cfg)
    if key not in state:
        items, _ = pending_items(runs_file, case_file, hook_log_root)
        state[key] = [kind + ':' + item_id for kind, item_id, _ in items]
        _write_store(state_path, state)
    return len(state[key])


def sync(workspace, runs_file, case_file, hook_log_root, cfg=None, state_path=None):
    """Send unsent items to one Langfuse project and remember each successful request."""
    cfg = cfg or load_config(workspace)
    if not (cfg['LANGFUSE_PUBLIC_KEY'] and cfg['LANGFUSE_SECRET_KEY']):
        raise SyncError(f'Langfuse 키가 없습니다. 환경 변수나 {Path(workspace) / ".env"}에 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY를 넣으세요.')
    client = Client(cfg)
    items, missing = pending_items(runs_file, case_file, hook_log_root, load_member(workspace))
    state = _read_store(state_path) if state_path else {}
    key = _ledger_key(cfg)
    sent = set(state.get(key, []))
    def mark(kind, item_ids):
        sent.update(kind + ':' + item_id for item_id in item_ids)
        if state_path:
            state[key] = sorted(sent)
            _write_store(state_path, state)
    result = {'cases': 0, 'scores': 0, 'sessions': 0, 'hook_runs': 0, 'traces': 0, 'missing_hook_logs': []}
    result['missing_hook_logs'] = missing
    spans = []
    for kind, item_id, body in items:
        if kind + ':' + item_id in sent:
            continue
        if kind == 'span':
            spans.append((item_id, body))
            continue
        path = {'dataset': '/api/public/datasets', 'case': '/api/public/dataset-items', 'score': '/api/public/scores'}[kind]
        client.post(path, body)
        mark(kind, [item_id])
        if kind == 'case': result['cases'] += 1
        if kind == 'score': result['scores'] += 1
    for i in range(0, len(spans), 200):
        batch = spans[i:i + 200]
        client.post('/api/public/otel/v1/traces', _otel_body([span for _, span in batch]))
        mark('span', [item_id for item_id, _ in batch])
        result['traces'] += sum(1 for _, s in batch if 'parentSpanId' not in s)
        result['hook_runs'] += sum(1 for _, s in batch if 'parentSpanId' in s)
    result['sessions'] = len({s['traceId'] for _, s in spans})
    result['host'] = cfg['LANGFUSE_BASE_URL']
    result['synced_at'] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == '__main__':
    here = Path(__file__).resolve().parent
    workspace = Path(os.environ.get('GHOST_ALICE_WORKSPACE', str(here.parent))).resolve()
    print(json.dumps(sync(workspace, here / 'captures' / 'runs.jsonl', here / 'captures' / 'case.json',
                          Path.home() / '.ghost-alice' / 'session-logs' / 'claude',
                          state_path=here / 'captures' / 'langfuse-sent.json'), ensure_ascii=False, indent=2))
