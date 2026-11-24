"""An input that only read files answers without a registered route; work still needs one.

The Stop hook blocks an unrouted input that used a native tool. These tests fix the boundary:
read-only tools and read-only shell commands do not trigger that block, anything that can change
a file still does, and a block tells the user in Korean what was held, why, and what to do.
"""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_response_route as fixtures


def call(name, **data):
    return dict(type='tool_use', name=name, input=data)


def shell(command, name='Bash'):
    return call(name, command=command)


class ReadOnlyCallTests(unittest.TestCase):
    def setUp(self):
        self.native = importlib.import_module('native_transcript')

    def read_only(self, item):
        return self.native._read_only_call(item)

    def test_reading_tools_are_read_only(self):
        for name in ('Read', 'Glob', 'Grep', 'LS', 'NotebookRead', 'Skill', 'ToolSearch'):
            with self.subTest(name=name):
                self.assertTrue(self.read_only(call(name, file_path='/isolated/a.md')))

    def test_writing_and_unknown_tools_are_work(self):
        for name in ('Write', 'Edit', 'NotebookEdit', 'WebFetch', 'Agent', 'mcp__server__tool'):
            with self.subTest(name=name):
                self.assertFalse(self.read_only(call(name, file_path='/isolated/a.md')))

    def test_malformed_shell_input_is_work(self):
        self.assertFalse(self.read_only(dict(type='tool_use', name='Bash', input=None)))
        self.assertFalse(self.read_only(dict(type='tool_use', name='Bash', input=dict(command=7))))

    def test_read_commands_are_read_only(self):
        commands = [
            'head -n 5 "a b/README.md"',
            'cd "x" && wc -l f && tail -c 1 f | od -c | head -1 && awk \'END{print NR}\' f',
            'grep -n -E "a|b" f | head',
            'for f in *.py; do echo "== $f"; head -n 1 "$f"; done',
            "cd test-fixture/py && for f in *.py; do printf '%s: ' \"$f\"; head -n 1 \"$f\"; echo; done; ls -la",
            'd=$(git rev-parse --show-toplevel)/test-fixture/py; ls -la "$d"; for f in "$d"/*.py; do echo "== $(basename "$f")"; done',
            'ls x 2>/dev/null',
            'wc -l f 2>&1',
            'sed -n 1,5p f',
            'find . -name "*.py"',
            'git status',
            'G=C:/x; grep -n -A70 "Core" $G/a.md | head -100',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(self.read_only(shell(command)))

    def test_powershell_read_commands_are_read_only(self):
        commands = [
            'Get-Content test-fixture/README.md | Measure-Object -Line',
            '$p = "f"; (Get-Content $p | Measure-Object -Line).Lines',
            'Get-ChildItem test-fixture | Select-Object Name',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(self.read_only(shell(command, 'PowerShell')))

    def test_commands_that_can_change_files_are_work(self):
        commands = [
            'rm -rf x', 'echo hi > a.txt', 'echo "a" >> f', 'printf x > f', 'echo "x" > "$f"', 'cat a | tee b',
            'python x.py', 'mkdir test-output', 'cp a b', 'mv a b', 'touch b', 'cat a; touch b',
            'sed -i s/a/b/ f', 'sed s/a/b/ f', 'git commit -m "x"', 'git push', 'git',
            'X=1; rm f', 'for f in *; do rm $f; done', 'awk \'{system("rm x")}\' f', 'find . -delete',
            'find . -exec rm {} ;', 'head f && python -c "open(1)"', 'd=$(rm -rf x); ls', 'echo "$(touch a)"',
            'ls $(mkdir z)', 'echo `touch a`',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(self.read_only(shell(command)))

    def test_powershell_commands_that_can_change_files_are_work(self):
        for command in ('Set-Content a.txt hi', 'New-Item x', 'Remove-Item x', 'Get-Content a | Out-File b'):
            with self.subTest(command=command):
                self.assertFalse(self.read_only(shell(command, 'PowerShell')))

    def test_own_record_scripts_are_read_only(self):
        for script in ('session_intent_ledger.py', 'response_route.py', 'completion_assessment.py'):
            with self.subTest(script=script):
                self.assertTrue(self.read_only(shell(f'python /core/_shared/{script} --record x > out.json')))


class ReadOnlyActivityTests(unittest.TestCase):
    def setUp(self):
        self.native = importlib.import_module('native_transcript')
        self.fixture = fixtures.ResponseRouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.transcript = Path(self.fixture.tmp.name) / 'native.jsonl'

    def activity(self, *items):
        rows = [dict(type='user', sessionId='current', message=dict(role='user', content='Tell me the title.'))]
        rows += [dict(type='assistant', sessionId='current', message=dict(role='assistant', content=[item])) for item in items]
        self.transcript.write_text('\n'.join(json.dumps(row) for row in rows))
        return self.native.native_tool_activity('claude', 'current',
            dict(session_id='current', transcript_path=str(self.transcript)))

    def test_tool_free_input_reports_no_activity(self):
        self.assertEqual(self.activity()['status'], 'absent')

    def test_reading_input_is_observed_and_read_only(self):
        result = self.activity(call('Read', file_path='/isolated/README.md'), shell('head -n 1 README.md'))
        self.assertEqual(result['status'], 'observed')
        self.assertTrue(result['read_only'])

    def test_one_writing_call_makes_the_input_work(self):
        result = self.activity(call('Read', file_path='/isolated/README.md'), shell('echo done > note.txt'))
        self.assertEqual(result['status'], 'observed')
        self.assertFalse(result['read_only'])


class ReadOnlyStopTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ResponseRouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.coords['platform'] = 'claude'
        self.fixture.event = self.fixture.intake('Tell me the title of the README.')
        self.source = dict(GHOST_ALICE_CORE_ROOT=str(fixtures.ROOT),
            GHOST_ALICE_SESSION_INTENT_ROOT=str(self.fixture.root),
            GHOST_ALICE_PLATFORM='claude', GHOST_ALICE_SESSION_ID='current')
        self.transcript = Path(self.fixture.tmp.name) / 'native.jsonl'
        self.hook = Path(os.environ.get('GHOST_ALICE_TEST_SHARED_ROOT', Path(__file__).parent)) / 'claude_stop_verification_hook.py'

    def stop(self, body, *items):
        rows = [dict(type='user', sessionId='current', message=dict(role='user', content='Tell me the title of the README.'))]
        rows += [dict(type='assistant', sessionId='current', message=dict(role='assistant', content=[item])) for item in items]
        self.transcript.write_text('\n'.join(json.dumps(row) for row in rows))
        result = subprocess.run([sys.executable, '-B', str(self.hook)],
            input=json.dumps(dict(session_id='current', transcript_path=str(self.transcript), last_assistant_message=body)),
            text=True, capture_output=True, check=True, encoding='utf-8',
            env=dict(os.environ, **self.source, CLAUDE_CODE_ENTRYPOINT='claude-desktop', PYTHONDONTWRITEBYTECODE='1',
                PYTHONIOENCODING='utf-8'))
        return json.loads(result.stdout)

    def test_unrouted_reading_input_is_not_blocked(self):
        answer = 'The title is "Test document".'
        self.assertNotEqual(self.stop(answer, call('Read', file_path='/isolated/README.md')).get('decision'), 'block')
        self.assertNotEqual(self.stop(answer, shell('head -n 1 /isolated/README.md')).get('decision'), 'block')

    def test_unrouted_writing_input_is_still_blocked_with_user_guidance(self):
        blocked = self.stop('I wrote the title to title.txt.', call('Read', file_path='/isolated/README.md'),
            shell('head -n 1 /isolated/README.md > title.txt'))
        self.assertEqual(blocked.get('decision'), 'block')
        self.assertIn('route-unavailable', blocked['reason'])
        self.assertIn('repair-target: response_route', blocked['reason'])
        for part in ('[사용자 안내]', '무엇이 막혔나:', '왜:', '다음에 할 일:'):
            with self.subTest(part=part):
                self.assertIn(part, blocked['reason'])


class KoreanGuideTests(unittest.TestCase):
    def setUp(self):
        self.hook = importlib.import_module('claude_stop_verification_hook')

    def test_block_guide_names_what_why_and_next_step(self):
        guide = self.hook._korean_guide('route-unavailable: This input contains native tool calls', True)
        for part in ('무엇이 막혔나:', '왜:', '다음에 할 일:', 'response-route'):
            with self.subTest(part=part):
                self.assertIn(part, guide)

    def test_notice_guide_says_the_answer_went_out(self):
        guide = self.hook._korean_guide('criterion-unbound: The current-session assistant follows', False)
        for part in ('무엇이 남았나:', '왜:', '다음에 할 일:'):
            with self.subTest(part=part):
                self.assertIn(part, guide)

    def test_each_known_code_has_its_own_reason(self):
        codes = ('route-unavailable', 'native-activity-unavailable', 'criterion-unbound', 'response-assessment-required',
                 'claim-evidence-unbound', 'assessment-unsupported')
        reasons = {self.hook._korean_guide(code + ': x', True) for code in codes}
        self.assertEqual(len(reasons), len(codes))
        self.assertNotIn(self.hook._korean_guide('unknown-code: x', True), reasons)


if __name__ == '__main__':
    unittest.main()
