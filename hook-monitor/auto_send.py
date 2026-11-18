"""Send a session's Ghost-ALICE hook flow to Langfuse each time Claude finishes an answer.

Register this file as a Claude Code `Stop` and `SessionEnd` hook (README, "훅 기록 자동 전송").
Claude Code passes the hook input as JSON on stdin. This script reads `session_id` and `hook_event_name` from
it, starts a separate worker process and returns at once with exit status 0, so an answer is never delayed
or blocked.

The worker waits a few seconds so the other Stop hooks can finish writing their records of the turn, builds the
session's explained hook flow without touching the monitor's saved files, and hands it to
langfuse_sync.sync_session. That function sends only the turns that have ended and were not sent before:
Langfuse stores a record that is sent twice as a duplicate (https://langfuse.com/faq/all/tracing-data-updates).
The send after `SessionEnd` is the final one and also includes a turn that never ended.
Langfuse keys and the user id are read by langfuse_sync. Each attempt appends one JSON line to
captures/auto-send.log.
Dependencies: Python 3.11+ standard library only.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / 'captures' / 'auto-send.log'
# Ghost-ALICE's own Stop hooks run at the same moment as this one; the wait lets their records be included.
DELAY_SECONDS = 5
SESSION_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{7,127}')


def hook_request(raw):
    """Return (session ID, final) from a Claude Code hook input; ('', False) when it carries no usable session ID.

    `final` is True for the SessionEnd event: the chat is over, so its last turn will not change any more.
    """
    try:
        payload = json.loads(raw)
    except ValueError:
        return '', False
    session = payload.get('session_id') if isinstance(payload, dict) else None
    if not isinstance(session, str) or not SESSION_PATTERN.fullmatch(session):
        return '', False
    return session, payload.get('hook_event_name') == 'SessionEnd'


def _log(row, log_path):
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    except OSError:
        pass  # a full disk or locked file must not turn into a hook failure


def _row(session, result):
    return {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'session': session, **result}


def send_session(session, final):
    """Build the session's hook flow in this process (read-only) and send its finished, unsent turns."""
    import langfuse_sync
    import server
    import timeline
    data = timeline.build(session, server.TIMELINE_CONFIG, save=False)
    return langfuse_sync.sync_session(server.WORKSPACE, data, final=final)


def run_worker(session, final=False, delay=DELAY_SECONDS, log_path=LOG, send=send_session, sleep=time.sleep):
    """Wait, send the session's new hook records, append the outcome to the log and return it. Never raises."""
    sleep(delay)
    try:
        reply = send(session, final)
        result = {'ok': True, 'final': final, **{key: reply.get(key, 0) for key in ('traces', 'observations', 'skipped', 'waiting')},
                  'host': reply.get('host', '')}
    except Exception as err:  # noqa: BLE001 - this runs unattended after an answer; report every failure, raise none
        result = {'ok': False, 'final': final, 'error': f'{type(err).__name__}: {err}'}
    row = _row(session, result)
    _log(row, log_path)
    return row


def spawn_worker(session, final):
    """Start the worker as a process that outlives this hook and shares none of its pipes."""
    command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--send', session] + (['--final'] if final else [])
    options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL,
               'close_fds': True, 'cwd': str(ROOT)}
    if os.name != 'nt':
        subprocess.Popen(command, start_new_session=True, **options)
        return
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        # Leave the hook's job object when Windows allows it, so the worker is not ended together with the hook.
        subprocess.Popen(command, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options)
    except OSError:
        subprocess.Popen(command, creationflags=flags, **options)


def run_hook(raw, spawn=spawn_worker, log_path=LOG):
    """Hook entry: start the worker for the chat named in the hook input. Always returns 0."""
    session, final = hook_request(raw)
    if session:
        try:
            spawn(session, final)
        except Exception as err:  # noqa: BLE001 - a hook that fails here would disturb Claude's answer
            _log(_row(session, {'ok': False, 'final': final,
                                'error': f'전송 작업을 시작하지 못했습니다: {type(err).__name__}: {err}'}), log_path)
    return 0


def main(argv, read_input):
    if len(argv) >= 3 and argv[1] == '--send':
        if SESSION_PATTERN.fullmatch(argv[2]):
            run_worker(argv[2], final='--final' in argv[3:])
        return 0
    return run_hook(read_input())


if __name__ == '__main__':
    try:
        # Read bytes: the console's default encoding on Korean Windows (cp949) cannot decode the UTF-8 hook input.
        main(sys.argv, lambda: sys.stdin.buffer.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001 - exit status stays 0 so the answer is never blocked
        pass
    raise SystemExit(0)
