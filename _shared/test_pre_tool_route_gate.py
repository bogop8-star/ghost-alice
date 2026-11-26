"""The work route is asked for before the first file-changing tool call, not after the answer.

2026-11-26: when the route was registered only at Stop, after the work was done and checked,
Ghost-ALICE Autopilot rejected the proof as verified before its origin capture, so no
completion was recorded. Asking before the first file-changing call puts the capture first.
"""
import importlib
import unittest
from pathlib import Path

import test_response_route as fixtures


def payload(name, **data):
    return dict(session_id='current', hook_event_name='PreToolUse', tool_name=name, tool_input=data)


class PreToolRouteGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = importlib.import_module('pre_tool_route_gate')
        self.fixture = fixtures.ResponseRouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.coords['platform'] = 'claude'
        self.event = self.fixture.intake('Make output/report.txt with three lines. Do not touch other files.')
        self.env = dict(GHOST_ALICE_CORE_ROOT=str(fixtures.ROOT), GHOST_ALICE_PLATFORM='claude',
            GHOST_ALICE_SESSION_INTENT_ROOT=str(self.fixture.root))

    def deny(self, name, **data):
        return self.gate.route_gate_denial(self.env, payload(name, **data))

    def register_route(self):
        candidate = self.fixture.candidate(units=())
        fixtures.ledger.record_response_route(root=self.fixture.root, platform='claude', session_id='current',
            expected_input_event_id=self.event, candidate=candidate, boundary_ref='test-boundary')

    def test_file_change_without_route_is_denied_with_guidance(self):
        for name, data in (('Write', dict(file_path='output/report.txt', content='alpha')),
                           ('Edit', dict(file_path='a.txt', old_string='a', new_string='b')),
                           ('Bash', dict(command='printf alpha > output/report.txt')),
                           ('PowerShell', dict(command="Set-Content output/report.txt 'alpha'"))):
            with self.subTest(tool=name):
                reason = self.deny(name, **data)
                self.assertIsNotNone(reason)
                self.assertIn('route-before-work', reason)
                self.assertIn('admitted criterion', reason)
                self.assertIn('not a user project file', reason)

    def test_reading_and_record_scripts_are_not_denied(self):
        self.assertIsNone(self.deny('Read', file_path='README.md'))
        self.assertIsNone(self.deny('Bash', command='head -n 1 README.md'))
        self.assertIsNone(self.deny('PowerShell', command='Get-Content README.md | Measure-Object -Line'))
        # Registering the route itself must never be blocked by this gate.
        self.assertIsNone(self.deny('Bash', command='python C:/core/_shared/response_route.py --candidate-json x'))
        self.assertIsNone(self.deny('Bash', command='python session_intent_ledger.py --record x'))

    def test_tools_that_do_not_change_files_are_not_denied(self):
        self.assertIsNone(self.deny('WebFetch', url='https://example.com'))
        self.assertIsNone(self.deny('TodoWrite', todos=[]))

    def test_ready_route_for_the_current_input_lets_the_change_run(self):
        self.register_route()
        self.assertIsNone(self.deny('Write', file_path='output/report.txt', content='alpha'))

    def test_other_platforms_and_unbound_sessions_are_left_to_the_stop_gate(self):
        self.env['GHOST_ALICE_PLATFORM'] = 'codex'
        self.assertIsNone(self.deny('Write', file_path='a.txt', content='x'))
        self.env['GHOST_ALICE_PLATFORM'] = 'claude'
        self.assertIsNone(self.gate.route_gate_denial(self.env, dict(payload('Write', file_path='a', content='x'),
                                                                     session_id='unknown-session')))

    def test_gate_can_be_turned_off(self):
        self.env['GHOST_ALICE_ROUTE_GATE'] = '0'
        self.assertIsNone(self.deny('Write', file_path='a.txt', content='x'))


if __name__ == '__main__':
    unittest.main()
