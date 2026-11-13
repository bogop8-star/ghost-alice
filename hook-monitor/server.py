"""Local Ghost-ALICE hook and benchmark case monitor."""
import json
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import langfuse_sync

ROOT = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get('GHOST_ALICE_WORKSPACE', str(ROOT.parent))).resolve()
HOME = Path.home()
LOG_ROOT = HOME / '.ghost-alice' / 'session-logs' / 'claude'
TRACE = HOME / '.ghost-alice' / 'io-trace.jsonl'
DEFAULT_LEDGER_ROOT = (WORKSPACE if (WORKSPACE / 'install.sh').exists() else WORKSPACE / 'ghost-alice') / '.tmp' / 'session-intent'
LEDGER_ROOT = Path(os.environ.get('GHOST_ALICE_LEDGER_ROOT', str(DEFAULT_LEDGER_ROOT)))
INTENT = LEDGER_ROOT / 'claude'
OUTPUT = ROOT / 'captures'
OUTPUT.mkdir(exist_ok=True)
CAPTURE = OUTPUT / ('hook-monitor-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.jsonl')
SETTINGS = HOME / '.claude' / 'settings.json'
CASE_FILE = OUTPUT / 'case.json'
RUNS_FILE = OUTPUT / 'runs.jsonl'
LIVE_FILE = OUTPUT / 'live-transcripts.jsonl'
LANGFUSE_PROJECTS = OUTPUT / 'langfuse-projects.json'
LANGFUSE_SENT = OUTPUT / 'langfuse-sent.json'
PROJECTS = HOME / '.claude' / 'projects'
PROJECT_TRANSCRIPTS = PROJECTS / str(WORKSPACE).replace(':', '-').replace('\\', '-').replace('/', '-')
seen = {}
events = []
transcript_seen = {}
live_sessions = {}
lock = threading.Lock()
langfuse_lock = threading.Lock()

def text_blocks(content):
    if isinstance(content, str): return content
    if not isinstance(content, list): return ''
    return '\n'.join(str(x.get('text','')) for x in content if isinstance(x,dict) and x.get('type') == 'text')

def parse_transcript(raw):
    messages = []
    session = None
    for line in raw.splitlines():
        try: row = json.loads(line)
        except ValueError: continue
        session = session or row.get('sessionId') or row.get('session_id')
        msg = row.get('message',{})
        if not isinstance(msg,dict): continue
        role = msg.get('role') or row.get('type')
        if role not in ('user','assistant'): continue
        content = msg.get('content')
        body = text_blocks(content)
        if body.strip() and not body.lstrip().startswith('<system-reminder>'):
            messages.append({'role':role,'ts':row.get('timestamp'), 'text':body[:20000]})
        if isinstance(content,list):
            for item in content:
                if isinstance(item,dict) and item.get('type') == 'tool_use':
                    messages.append({'role':'tool','ts':row.get('timestamp'),
                                     'text':str(item.get('name','unknown'))})
    return session, messages[-300:]

def scan_transcripts():
    if not PROJECT_TRANSCRIPTS.exists(): return
    files = sorted(PROJECT_TRANSCRIPTS.glob('*.jsonl'), key=lambda p:p.stat().st_mtime, reverse=True)[:20]
    for path in files:
        key = str(path)
        size = path.stat().st_size
        offset = transcript_seen.get(key, 0)
        if size < offset: offset = 0
        with path.open('rb') as f:
            f.seek(offset)
            chunk = f.read()
            lines = chunk.split(b'\n')
            transcript_seen[key] = size-len(lines[-1])
        for line in lines[:-1]:
            try: row = json.loads(line.decode('utf-8'))
            except (ValueError, UnicodeError): continue
            session = row.get('sessionId') or row.get('session_id') or path.stem
            _,messages = parse_transcript(json.dumps(row,ensure_ascii=False))
            if not messages: continue
            current = live_sessions.setdefault(session,{'updated':0,'messages':[]})
            current['updated'] = path.stat().st_mtime
            current['messages'].extend(messages)
            del current['messages'][:-300]
            with LIVE_FILE.open('a',encoding='utf-8') as out:
                for message in messages:
                    out.write(json.dumps({'session':session,**message},ensure_ascii=False)+'\n')
    for session in list(live_sessions):
        if len(live_sessions)>20:
            oldest=min(live_sessions,key=lambda x:live_sessions[x]['updated'])
            del live_sessions[oldest]

def paths():
    result = []
    if LOG_ROOT.exists():
        result += list(LOG_ROOT.glob('*/strict-hook-output.jsonl'))
    if INTENT.exists():
        result += list(INTENT.glob('*/intent-events.jsonl'))
    if TRACE.exists():
        result.append(TRACE)
    return result

def sanitize(path, row):
    if path.name == 'strict-hook-output.jsonl':
        return {'source':'hook', 'ts':row.get('ts'), 'session':row.get('session_id'),
                'stage':row.get('event'), 'hook':row.get('hook_id'),
                'exit_code':row.get('exit_code'), 'visibility':row.get('visible_decision'),
                'duration_s':row.get('observed_duration_s'),
                'error':str(row.get('stderr') or '')[:300]}
    if path.name == 'intent-events.jsonl':
        return {'source':'ledger', 'ts':row.get('ts') or row.get('timestamp'),
                'session':row.get('session_id') or path.parent.name,
                'stage':row.get('event'), 'event_id':row.get('event_id')}
    return {'source':'tool trace', 'ts':row.get('ts'), 'session':row.get('session_id'),
            'stage':row.get('event') or row.get('hook_event_name'),
            'tool':row.get('tool_name') or row.get('tool')}

def scan():
    with lock:
        for path in paths():
            key = str(path)
            size = path.stat().st_size
            offset = seen.get(key, size if key not in seen else 0)
            if size < offset: offset = 0
            with path.open('rb') as f:
                f.seek(offset)
                chunk = f.read()
                lines = chunk.split(b'\n')
                seen[key] = size - len(lines[-1])
            for line in lines[:-1]:
                try: row = json.loads(line.decode('utf-8'))
                except (UnicodeError, ValueError): continue
                item = sanitize(path, row)
                events.append(item)
                with CAPTURE.open('a', encoding='utf-8') as out:
                    out.write(json.dumps(item, ensure_ascii=False) + '\n')
        del events[:-1000]

def settings_status():
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8-sig'))
        return {'disabled': bool(data.get('disableAllHooks')),
                'registered': {k:len(v) for k,v in data.get('hooks',{}).items()}}
    except (OSError, ValueError):
        return {'disabled':None, 'registered':{}}

def read_jsonl(path):
    if not path.exists(): return []
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try: rows.append(json.loads(line))
        except ValueError: continue
    return rows

def at_or_before(timestamp, saved_at):
    if not timestamp or not saved_at: return True
    try:
        observed = datetime.fromisoformat(str(timestamp).replace('Z','+00:00'))
        saved = datetime.fromisoformat(str(saved_at).replace('Z','+00:00'))
        return observed.astimezone() <= saved.astimezone()
    except ValueError:
        return True

def after_start(timestamp, start):
    if not start: return True
    if not timestamp: return False
    try:
        observed = datetime.fromisoformat(str(timestamp).replace('Z','+00:00'))
        boundary = datetime.fromisoformat(str(start).replace('Z','+00:00'))
        return observed.astimezone() > boundary.astimezone()
    except ValueError:
        return False

def saved_results():
    case = json.loads(CASE_FILE.read_text(encoding='utf-8')) if CASE_FILE.exists() else {}
    history = read_jsonl(LIVE_FILE)
    hook_history = [row for path in OUTPUT.glob('hook-monitor-*.jsonl') for row in read_jsonl(path)]
    results = []
    for row in read_jsonl(RUNS_FILE):
        if row.get('kind') != 'assessment': continue
        sid = row.get('session')
        start = row.get('monitor_start')
        results.append({**row, 'case':row.get('case',case),
                        'messages':row['messages'] if 'messages' in row else [{k:v for k,v in m.items() if k!='session'} for m in history if m.get('session')==sid and at_or_before(m.get('ts'),row.get('saved_at')) and after_start(m.get('ts'),start)],
                        'events':row['events'] if 'events' in row else [e for e in hook_history if e.get('session')==sid and at_or_before(e.get('ts'),row.get('saved_at')) and after_start(e.get('ts'),start)]})
    return results

class Handler(BaseHTTPRequestHandler):
    def reply(self, data, code=200):
        body = json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        route = urlparse(self.path).path
        length = int(self.headers.get('Content-Length','0'))
        if length > 12_000_000:
            self.reply({'error':'파일이 너무 큽니다 (12 MB 제한)'},413); return
        try: data = json.loads(self.rfile.read(length))
        except ValueError:
            self.reply({'error':'JSON 형식 오류'},400); return
        if route == '/api/langfuse-projects':
            try:
                project = langfuse_sync.register_project(LANGFUSE_PROJECTS, data.get('host',''), data.get('public_key',''), data.get('secret_key',''))
            except langfuse_sync.SyncError as err:
                self.reply({'error':str(err)},400); return
            self.reply({'ok':True,'project':project}); return
        if route == '/api/langfuse-sync':
            try:
                with langfuse_lock:
                    cfg, name = langfuse_sync.select_project(WORKSPACE, LANGFUSE_PROJECTS, str(data.get('project_id','')))
                    result = langfuse_sync.sync(WORKSPACE, RUNS_FILE, CASE_FILE, LOG_ROOT, cfg, LANGFUSE_SENT)
            except langfuse_sync.SyncError as err:
                self.reply({'error':str(err)},502); return
            self.reply({'ok':True,'project':name,**result}); return
        if route == '/api/case':
            case = {k:str(data.get(k,''))[:20000] for k in ('id','context','prompt','expected','conditions')}
            CASE_FILE.write_text(json.dumps(case,ensure_ascii=False,indent=2),encoding='utf-8')
            self.reply({'ok':True,'path':str(CASE_FILE)})
        elif route == '/api/transcript':
            session,messages = parse_transcript(str(data.get('raw','')))
            if not messages:
                self.reply({'error':'Claude Code JSONL에서 대화 메시지를 찾지 못했습니다'},400); return
            run = {'saved_at':datetime.now().isoformat(), 'session':session or str(data.get('session','')),
                   'phase':str(data.get('phase','before')), 'messages':messages,
                   'verdict':{}, 'note':''}
            with RUNS_FILE.open('a',encoding='utf-8') as out:
                out.write(json.dumps(run,ensure_ascii=False)+'\n')
            self.reply({'ok':True,'run':run,'path':str(RUNS_FILE)})
        elif route == '/api/verdict':
            sid = str(data.get('session',''))
            monitor_start = str(data.get('monitor_start',''))
            run = {'saved_at':datetime.now().isoformat(), 'session':str(data.get('session','')),
                   'phase':str(data.get('phase','before')), 'verdict':data.get('verdict',{}),
                   'note':str(data.get('note',''))[:5000], 'kind':'assessment',
                   'monitor_start':monitor_start,
                   'case':json.loads(CASE_FILE.read_text(encoding='utf-8')) if CASE_FILE.exists() else {},
                   'messages':data.get('messages',[])[:300] if isinstance(data.get('messages'),list) else [],
                   'events':[e for e in events if e.get('session')==sid and after_start(e.get('ts'),monitor_start)]}
            with RUNS_FILE.open('a',encoding='utf-8') as out:
                out.write(json.dumps(run,ensure_ascii=False)+'\n')
            self.reply({'ok':True,'path':str(RUNS_FILE)})
        else: self.reply({'error':'찾을 수 없음'},404)

    def do_GET(self):
        route = urlparse(self.path).path
        if route == '/api/langfuse-projects':
            self.reply({'projects':langfuse_sync.project_choices(WORKSPACE, LANGFUSE_PROJECTS)}); return
        if route == '/api':
            scan()
            with lock: scan_transcripts()
            with lock: body = json.dumps({'events':events, 'settings':settings_status(),
                                          'monitor_reset_supported':True,
                                          'capture':str(CAPTURE), 'runs_path':str(RUNS_FILE),
                                          'live_path':str(LIVE_FILE), 'live_sessions':live_sessions,
                                          'case':json.loads(CASE_FILE.read_text(encoding='utf-8')) if CASE_FILE.exists() else {},
                                          'runs':read_jsonl(RUNS_FILE), 'saved_results':saved_results(),
                                          'langfuse':langfuse_sync.configured(WORKSPACE)}, ensure_ascii=False).encode('utf-8')
            mime = 'application/json; charset=utf-8'
        elif route == '/':
            body = (ROOT / 'index.html').read_bytes()
            mime = 'text/html; charset=utf-8'
        else:
            self.send_error(404); return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *_): pass

if __name__ == '__main__':
    if PROJECT_TRANSCRIPTS.exists():
        transcript_seen.update({str(p): p.stat().st_size for p in PROJECT_TRANSCRIPTS.glob('*.jsonl')})
    port = int(os.environ.get('GHOST_ALICE_MONITOR_PORT', '8765'))
    print(f'http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
