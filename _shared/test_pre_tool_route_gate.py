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
        # The original behaviour ("always") is kept for the tests below; the default mode is
        # tested separately in DefaultModeTests.
        self.env = dict(GHOST_ALICE_CORE_ROOT=str(fixtures.ROOT), GHOST_ALICE_PLATFORM='claude',
            GHOST_ALICE_SESSION_INTENT_ROOT=str(self.fixture.root), GHOST_ALICE_ROUTE_GATE='always')

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
                # The script locations are named so the assistant does not search the disk for them.
                self.assertIn('response_route.py', reason)
                self.assertIn('session_intent_ledger.py', reason)

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


class DefaultModeTests(PreToolRouteGateTests):
    """Review on #39: gating every write turn cost 68 s -> 363 s for a one-file task.

    By default the gate applies only while the session owns an admitted criterion that is
    not met, which is where Ghost-ALICE Autopilot records completion.
    """
    def setUp(self):
        super().setUp()
        del self.env['GHOST_ALICE_ROUTE_GATE']

    def admit_criterion(self, status=None):
        row = dict(self.fixture.criterion('first'), **({'status': status} if status else {}))
        fixtures.ledger.record_turn(root=self.fixture.root, platform='claude', session_id='current',
            expected_input_event_id=self.event, intent_delta={'acceptance_criteria': [row]})

    def test_plain_work_without_a_criterion_is_not_gated(self):
        self.assertIsNone(self.deny('Write', file_path='a.txt', content='x'))

    def test_work_with_an_open_criterion_is_gated(self):
        self.admit_criterion()
        self.assertIn('route-before-work', self.deny('Write', file_path='a.txt', content='x'))

    # The inherited tests assume the gate applies; run them with an open criterion.
    def deny(self, name, **data):
        return super().deny(name, **data)

    test_file_change_without_route_is_denied_with_guidance = None


class HookRunTests(unittest.TestCase):
    """The gate is exercised through hook_profile_gate._run, the real PreToolUse entry."""
    def run_hook(self, gate_effect):
        import base64, io, json, os, shlex, subprocess, sys, tempfile
        from unittest import mock
        import install_destination
        hook_profile_gate = importlib.import_module('hook_profile_gate')
        directory = tempfile.mkdtemp()
        root = Path(directory)
        destination = install_destination.InstallDestination(mode='normal', owned_root=str(root),
            platform_dir=str(root / '.claude'), skills_dir=str(root / 'skills'),
            ghost_root=str(root / '.ghost-alice'), ledger_root=str(root / 'intent'),
            project_root=str(root), core_source_root=str(Path(__file__).resolve().parents[1]))
        command = base64.urlsafe_b64encode(shlex.join([sys.executable, '-c', 'print(1)']).encode()).decode()
        children, audit, out = [], [], io.StringIO()
        def child(*args, **kwargs):
            children.append(args)
            return subprocess.CompletedProcess(args[0], 0, '{}\n', '')
        stdin = json.dumps(dict(session_id='s', hook_event_name='PreToolUse', tool_name='Write',
                                tool_input=dict(file_path='a.txt', content='x')))
        with (mock.patch.dict(os.environ, {'HOME': directory}, clear=True),
              mock.patch.object(hook_profile_gate, '_read_stdin', return_value=stdin),
              mock.patch.object(hook_profile_gate.subprocess, 'run', side_effect=child),
              mock.patch('pre_tool_route_gate.route_gate_denial', **gate_effect),
              mock.patch.object(hook_profile_gate.strict_session_log, 'append_event',
                                side_effect=lambda **kw: audit.append(kw['event'])),
              mock.patch.object(sys, 'stdout', out)):
            hook_profile_gate._run('tool-checkpoint', command, platform='claude', binding=destination.binding())
        return children, audit, out.getvalue()

    def test_denial_is_returned_to_the_host_without_running_the_checkpoint(self):
        children, audit, out = self.run_hook(dict(return_value='route-before-work: test'))
        self.assertEqual(children, [])
        self.assertIn('route-before-work: test', audit[0]['stdout'])
        self.assertIn('"deny"', audit[0]['stdout'])

    def test_gate_error_runs_the_checkpoint_and_is_kept_in_the_audit(self):
        children, audit, out = self.run_hook(dict(side_effect=RuntimeError('boom')))
        self.assertEqual(len(children), 1)
        self.assertEqual(audit[0]['route_gate_error'], 'RuntimeError: boom')

if __name__ == '__main__':
    unittest.main()
