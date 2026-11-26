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

# The PowerShell read command given in case 3 of the 2026-11-25 hook-off/A/B comparison.
CASE3_COMMAND = ('if (Test-Path -LiteralPath .\\README.md) { $p = Resolve-Path -LiteralPath .\\README.md; '
                 '@(Get-Content -LiteralPath $p | Where-Object { $_ -ne $null }).Count }')


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
            "sed -n '3p' f", 'git log --oneline -3', 'sort f | uniq -c', 'uniq f', 'FOO=1 ls', 'X=hostname',
            "awk '{print $1}' f",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(self.read_only(shell(command)))

    def test_powershell_read_commands_are_read_only(self):
        commands = [
            'Get-Content test-fixture/README.md | Measure-Object -Line',
            '$p = "f"; (Get-Content $p | Measure-Object -Line).Lines',
            'Get-ChildItem test-fixture | Select-Object Name',
            '$r = Get-Content x', "$env:FOO = 'x'; Get-Content x",
            # The 2026-11-25 comparison, case 3: A blocked this exact read command in all three runs.
            CASE3_COMMAND,
            # .NET readers, pipeline filters and expressions over what was read.
            "[IO.File]::ReadAllBytes('README.md').Length",
            '$b = [IO.File]::ReadAllBytes((Resolve-Path README.md)); ($b | Where-Object { $_ -eq 10 }).Count',
            '$t = [IO.File]::ReadAllText("$PWD/README.md"); $t.Split("`n").Count',
            "[System.IO.File]::ReadAllLines((Resolve-Path 'README.md')).Count",
            "[Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes('a.txt'))",
            '$c = [IO.File]::ReadAllText("$PWD/hello.txt"); "len=$($c.Length) exact=$($c -ceq 1)"',
            'Get-ChildItem py -Filter *.py | ForEach-Object { $_.Name; Get-Content $_.FullName -TotalCount 1 }',
            "Get-ChildItem py | Where-Object { $_.Extension -eq '.py' } | Select-Object Name, Length | Format-Table",
            'foreach ($f in Get-ChildItem py -Filter *.py) { Write-Output $f.Name; Get-Content $f.FullName | Select-Object -First 1 }',
            '$lines = Get-Content README.md; $lines.Count; $lines[0]',
            '(Get-Content README.md -Raw) -split "`n" | Measure-Object | Select-Object -ExpandProperty Count',
            '$n = 0; Get-Content f | ForEach-Object { $n += 1 }; $n',
            "if (Test-Path out.txt) { Get-Content out.txt } else { 'missing' }",
            'Get-Content a.txt 2>$null | Sort-Object | Get-Unique', 'Get-FileHash README.md | Format-List',
            '$x=Get-Content a; $x.Length',
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
            # A leading assignment does not hide the command after it.
            'FOO=1 rm -rf build', 'A=1 B=2 touch f', 'env FOO=1 rm x',
            # Options and scripts that write a file or run a program.
            'sort -o out.txt in.txt', 'sort --output=out.txt in.txt', 'sort --compress-program=sh f',
            'sed -n w out.txt in.txt', "sed -n 'w out.txt' in.txt", 'sed -n 1,5p f -i', 'sed -n -e w f',
            "awk '{print > \"out.txt\"}' in.txt", "awk 'BEGIN{print \"x\" | \"sh\"}'",
            'uniq in.txt out.txt', 'git diff --output=out.txt', 'git log --output=f', 'git -C x commit',
            'find . -fprint out.txt', 'rg --pre ./x.sh pat', 'file -C -m magic',
            # Shell forms that run a second command.
            'ls & rm x', 'cat <(rm x)', 'ls | xargs rm',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(self.read_only(shell(command)))

    def test_powershell_commands_that_can_change_files_are_work(self):
        for command in ('Set-Content a.txt hi', 'New-Item x', 'Remove-Item x', 'Get-Content a | Out-File b',
                '$r = Remove-Item x', '$x = hostname', '(Get-Item x).Delete()', '[IO.File]::WriteAllText("a","b")',
                'Get-ChildItem | ForEach-Object { Remove-Item $_ }', '& rm x',
                # Writing cmdlets and redirection, wherever they sit in the command.
                'Get-Content a > b', "'x' | Add-Content b", 'Get-Content a | Tee-Object b', 'Copy-Item a b',
                'Get-Content a | ForEach-Object { $_ > b }', "[IO.File]::ReadAllText('a') | Set-Content b",
                "(Get-Content a).Replace('a','b') | Set-Content a", 'Get-Content a; del b',
                # A script block, a parenthesised part or a string can hold a command.
                'Get-ChildItem | Where-Object { Remove-Item $_.FullName }', 'if (Test-Path a) { Remove-Item a }',
                'foreach ($f in Get-ChildItem) { Remove-Item $f }', 'foreach ($f in (Remove-Item x)) { $f }',
                'Get-Content (Remove-Item x)', 'Write-Output (New-Item y)', '$n += (New-Item z).Length',
                '"$(Remove-Item x)"', '$(Remove-Item x).Count',
                CASE3_COMMAND.replace('@(Get-Content', '@(Remove-Item'),
                # Members that change a file, and calls whose target is not known.
                'Get-ChildItem | ForEach-Object Delete', 'Get-ChildItem | % { $_.Delete() }', '$x.Save("a")',
                '$a = @(1,2); $a.Clear()', '(Get-Item x).IsReadOnly = $true', "$f = Get-Item x; $f.Attributes = 'Hidden'",
                "[IO.File]::Delete('a')", '[IO.Path]::GetTempFileName()', "New-Object IO.StreamWriter('a')",
                '$e = { Remove-Item x }; $e.Invoke()',
                # Running another program or script.
                '$x=hostname', '& $cmd', "$cmd = 'rm'; & $cmd x", "Invoke-Expression 'rm x'", 'iex $s', '. ./run.ps1',
                './run.ps1', 'Start-Process notepad', 'python x.py'):
            with self.subTest(command=command):
                self.assertFalse(self.read_only(shell(command, 'PowerShell')))

    def test_record_reads_seen_on_2026_11_26_are_read_only(self):
        # The pre-tool route gate denied these read-only record commands in a real run.
        script = 'C:/home/.claude/skills/session-intent-analyzer/scripts/session_intent_ledger.py'
        for command in (
                f'S="{script}"; ls x 2>&1; python "$S" --root "C:/l" --platform claude --session-id s --read-state',
                f'python "{script}" --read-state | python -c "import json,sys; d=json.load(sys.stdin); '
                "print(json.dumps({k:d.get(k) for k in ['ledger_revision']},ensure_ascii=False,indent=1))\"; ls output 2>&1",
                'cat state.json | python3 -c "import json,sys; print(len(json.load(sys.stdin)))"'):
            with self.subTest(command=command):
                self.assertTrue(self.read_only(shell(command)))

    def test_python_inline_code_that_can_change_files_is_work(self):
        for command in ('python -c "open(\'x\',\'w\').write(\'a\')"', 'python -c "import os; os.remove(\'x\')"',
                        'python -c "import shutil; shutil.rmtree(\'x\')"', 'python -c "exec(input())"',
                        'python -c "__import__(\'os\').system(\'rm x\')"', "python -c 'from pathlib import Path; Path(\"x\").touch()'",
                        'S="x.py"; python "$S"', 'S="session_intent_ledger.py"; python "$S"; rm -rf y',
                        # Review on #39: writes the earlier deny list missed.
                        """python -c "import io; io.FileIO('x','w')" """.strip(),
                        """python -c "import tempfile; tempfile.mkstemp(dir='.')" """.strip(),
                        """python -c "f=getattr(__builtins__,'op'+'en'); print(1, file=f('x','w'))" """.strip(),
                        """python -c "import zipfile; zipfile.ZipFile('x.zip','w').close()" """.strip(),
                        """python -c "import sys; sys.modules['os'].remove('x')" """.strip()):
            with self.subTest(command=command):
                self.assertFalse(self.read_only(shell(command)))

    def test_own_record_scripts_are_read_only(self):
        for script in ('session_intent_ledger.py', 'response_route.py', 'completion_assessment.py'):
            with self.subTest(script=script):
                self.assertTrue(self.read_only(shell(f'python /core/_shared/{script} --record x > out.json')))
                self.assertTrue(self.read_only(shell(f'cd x && python3 {script} --read-state | head')))
                self.assertTrue(self.read_only(shell(f'"C:/Python/python.exe" C:/core/_shared/{script} --read')))

    def test_a_record_script_name_does_not_cover_other_commands(self):
        for command in ('python response_route.py; rm -rf x', 'rm response_route.py', 'cat response_route.py > copy.py',
                'python other.py response_route.py && touch a'):
            with self.subTest(command=command):
                self.assertFalse(self.read_only(shell(command)))


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
        self.assertNotEqual(self.stop('17', shell(CASE3_COMMAND, 'PowerShell')).get('decision'), 'block')

    def test_unrouted_writing_input_is_still_blocked_with_user_guidance(self):
        blocked = self.stop('I wrote the title to title.txt.', call('Read', file_path='/isolated/README.md'),
            shell('head -n 1 /isolated/README.md > title.txt'))
        self.assertEqual(blocked.get('decision'), 'block')
        self.assertIn('route-unavailable', blocked['reason'])
        self.assertIn('repair-target: response_route', blocked['reason'])
        for part in ('[사용자 안내]', '무엇이 막혔나:', '왜:', '다음에 할 일:'):
            with self.subTest(part=part):
                self.assertIn(part, blocked['reason'])

    def test_route_block_says_the_ledger_is_not_a_user_file(self):
        # 2026-11-25 comparison: after "다른 파일은 건드리지 마", A's assistant refused in all six
        # blocked runs to register the route because it took the Ghost-ALICE ledger for a user file.
        blocked = self.stop('I wrote the title to title.txt.', shell('head -n 1 /isolated/README.md > title.txt'))
        self.assertEqual(blocked.get('decision'), 'block')
        self.assertIn('not a user project file', blocked['reason'])
        self.assertIn('does not forbid', blocked['reason'])

    def test_route_block_says_how_a_completion_condition_is_recorded(self):
        # With the ledger note alone, the assistant registered a route with no work unit and no
        # criterion, so Ghost-ALICE Autopilot still had nothing to record.
        blocked = self.stop('I wrote the title to title.txt.', shell('head -n 1 /isolated/README.md > title.txt'))
        self.assertIn('admitted criterion', blocked['reason'])
        self.assertIn('execution work unit', blocked['reason'])
        # With the route alone, the assistant answered without the response review, so there
        # was still no authenticated proof for Ghost-ALICE Autopilot to apply.
        self.assertIn('verification-before-completion', blocked['reason'])
        self.assertIn('response review', blocked['reason'])


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
