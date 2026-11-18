"""Tests for the automatic hook-flow sender (auto_send.py).

Expected values come from existing contracts, not from the sender itself:
- Claude Code passes the Stop / SessionEnd hook input as JSON on stdin with the chat's `session_id` and the
  `hook_event_name`.
- A hook must not delay or block Claude's answer, so the entry returns 0 at once whatever happens.
- Langfuse stores a re-sent record as a duplicate, so two sends of one session must never run at the same time
  and the last send of a session (SessionEnd) is the one that may include a turn that never ended.

Run: python -X utf8 -m unittest discover -s hook-monitor -p "test_*.py"
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import auto_send  # noqa: E402
import langfuse_sync  # noqa: E402

SESSION = '65343343-2f2f-4c5c-b837-11ca9ef98cb2'


def hook_input(event='Stop', session=SESSION):
    return json.dumps({'session_id': session, 'hook_event_name': event, 'stop_hook_active': False,
                       'transcript_path': 'C:/Users/someone/.claude/projects/p/' + SESSION + '.jsonl'})


class HookInputTest(unittest.TestCase):
    def test_reads_the_session_id_from_the_stop_hook_input(self):
        self.assertEqual(auto_send.hook_request(hook_input('Stop')), (SESSION, False))

    def test_the_end_of_a_session_asks_for_the_final_send(self):
        self.assertEqual(auto_send.hook_request(hook_input('SessionEnd')), (SESSION, True))

    def test_input_without_a_usable_session_id_gives_no_session(self):
        for raw in ('', 'not json', '[]', '{}', json.dumps({'session_id': 5}),
                    json.dumps({'session_id': '../../etc'}), json.dumps({'session_id': 'a b; rm'})):
            with self.subTest(raw=raw):
                self.assertEqual(auto_send.hook_request(raw)[0], '')


class HookNeverBlocksTest(unittest.TestCase):
    """The hook must return 0 at once whatever happens, so Claude's answer is never delayed or blocked."""

    def test_starts_one_worker_for_the_session_and_returns_zero(self):
        started = []
        self.assertEqual(auto_send.run_hook(hook_input('Stop'), lambda session, final: started.append((session, final))), 0)
        self.assertEqual(started, [(SESSION, False)])

    def test_the_worker_of_a_session_end_is_told_it_is_the_final_send(self):
        started = []
        auto_send.run_hook(hook_input('SessionEnd'), lambda session, final: started.append((session, final)))
        self.assertEqual(started, [(SESSION, True)])

    def test_returns_zero_without_a_worker_when_the_input_is_unusable(self):
        started = []
        self.assertEqual(auto_send.run_hook('not json', lambda session, final: started.append(session)), 0)
        self.assertEqual(started, [])

    def test_returns_zero_and_logs_the_reason_when_the_worker_cannot_start(self):
        def broken(session, final):
            raise OSError('cannot start a process')
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'auto-send.log'
            self.assertEqual(auto_send.run_hook(hook_input('Stop'), broken, log), 0)
            row = json.loads(log.read_text(encoding='utf-8').splitlines()[0])
        self.assertEqual((row['session'], row['ok']), (SESSION, False))
        self.assertIn('cannot start a process', row['error'])


class WorkerTest(unittest.TestCase):
    def run_worker(self, send, final=False, delay=5):
        order = []
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'auto-send.log'
            auto_send.run_worker(SESSION, final, delay, log, send=lambda session, last: order.append('send') or send(session, last),
                                 sleep=lambda seconds: order.append(('sleep', seconds)))
            rows = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
        return order, rows

    def test_waits_for_the_other_stop_hooks_then_sends_and_logs_one_line(self):
        asked = []

        def send(session, final):
            asked.append((session, final))
            return {'session': session, 'traces': 1, 'observations': 9, 'skipped': 4, 'waiting': 0,
                    'host': 'https://langfuse.invalid'}
        order, rows = self.run_worker(send)
        self.assertEqual(order, [('sleep', 5), 'send'])  # waited before sending
        self.assertEqual(asked, [(SESSION, False)])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['session'], rows[0]['ok'], rows[0]['traces'], rows[0]['observations'],
                          rows[0]['skipped'], rows[0]['waiting'], rows[0]['final']), (SESSION, True, 1, 9, 4, 0, False))
        self.assertIn('ts', rows[0])

    def test_the_final_send_is_passed_on_and_logged(self):
        asked = []

        def send(session, final):
            asked.append(final)
            return {'traces': 1, 'observations': 3, 'skipped': 0, 'waiting': 0, 'host': 'https://langfuse.invalid'}
        _, rows = self.run_worker(send, final=True)
        self.assertEqual((asked, rows[0]['final']), ([True], True))

    def test_a_refused_send_is_logged_and_never_raised(self):
        def send(session, final):
            raise langfuse_sync.SyncError('Langfuse 키가 없습니다.')
        _, rows = self.run_worker(send, delay=0)
        self.assertEqual((rows[0]['session'], rows[0]['ok']), (SESSION, False))
        self.assertIn('Langfuse 키가 없습니다', rows[0]['error'])

    def test_an_unexpected_failure_is_logged_and_never_raised(self):
        def send(session, final):
            raise RuntimeError('unexpected')
        _, rows = self.run_worker(send, delay=0)
        self.assertEqual(rows[0]['ok'], False)
        self.assertIn('unexpected', rows[0]['error'])


if __name__ == '__main__':
    unittest.main()
