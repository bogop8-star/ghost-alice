"""Tests for governance_metrics.py using a synthetic transcript; no real logs are read."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import governance_metrics as gm  # noqa: E402


def user(content, **extra):
    return dict(type='user', message=dict(role='user', content=content), **extra)


def assistant(msg_id, blocks, output_tokens=10):
    return dict(type='assistant', message=dict(id=msg_id, role='assistant', content=blocks,
                                               usage=dict(output_tokens=output_tokens)))


def tool(name, **args):
    return dict(type='tool_use', name=name, input=args)


def stop_block(code):
    return dict(type='attachment', attachment=dict(type='hook_blocking_error', hookEvent='Stop',
                blockingError=dict(blockingError=f'[completion-gate] {code}: detail')))


class GovernanceMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name) / 'C--Users-x-ghost-alice'
        folder.mkdir()
        rows = [
            user([dict(type='text', text='<system-reminder>context</system-reminder>'), dict(type='text', text='첫 질문')]),
            dict(type='attachment', attachment=dict(type='queued_command', prompt='작업 중 보낸 질문')),
            assistant('m1', [tool('Bash', command='cat history.md')]),
            user([dict(type='tool_result', tool_use_id='t', content='out')]),
            assistant('m1', [dict(type='text', text='답')]),  # same message id: tokens counted once
            stop_block('route-unavailable'),
            user('Stop hook feedback:\n[completion-gate] route-unavailable', isMeta=True),
            user('Stop hook feedback: again'),
            assistant('m2', [tool('Skill', skill='task-router'),
                             tool('Bash', command='python response_route.py --read'),
                             tool('Bash', command='python _shared/completion_assessment.py prepare-response')], 20),
            stop_block('criterion-unbound'),
            user('<task-notification>done</task-notification>'),
            user([dict(type='text', text='두 번째 질문')]),
            assistant('m3', [tool('Edit', file_path='a.py'), tool('Skill', skill='anthropic-skills:docx')], 5),
            dict(type='assistant', isSidechain=True, message=dict(id='s', content=[tool('Bash', command='x')])),
            'not json',
        ]
        (folder / 'abcdef12-0000.jsonl').write_text(
            '\n'.join(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
        self.projects = Path(self.tmp.name)

    def test_session_metrics_counts_turns_tools_blocks_and_tokens(self):
        [row] = gm.collect(self.projects)
        self.assertEqual(row['session'], 'abcdef12')
        self.assertEqual(row['group'], 'ghost-alice')
        self.assertEqual(row['user_turns'], 3)
        self.assertEqual(row['tool_calls'], 6)
        self.assertEqual(row['gov_tool_calls'], 3)
        self.assertEqual(row['stop_blocks'], 2)
        self.assertEqual(row['stop_reasons'], {'route-unavailable': 1, 'criterion-unbound': 1})
        self.assertEqual(row['output_tokens'], 35)

    def test_single_project_folder_is_accepted(self):
        [row] = gm.collect(self.projects / 'C--Users-x-ghost-alice')
        self.assertEqual((row['session'], row['group'], row['stop_blocks']), ('abcdef12', 'ghost-alice', 2))

    def test_summary_ratios_per_group(self):
        summary = gm.summarize(gm.collect(self.projects))['ghost-alice']
        self.assertEqual(summary['sessions_blocked'], 1)
        self.assertEqual(summary['blocks_per_turn'], 0.67)
        self.assertEqual(summary['gov_calls_per_turn'], 1.0)
        self.assertEqual(summary['gov_share_of_tool_calls'], 0.5)

    def test_group_labels_hide_paths(self):
        self.assertEqual(gm.group_of('C--Users-x-AppData-Local-Temp-daily-off-abc'), 'daily-off')
        self.assertEqual(gm.group_of('C--Users-x-AppData-Local-Temp-daily-on-abc'), 'daily-on')
        self.assertEqual(gm.group_of('C--Users-x-AppData-Local-Temp-ghost-chat-grader-abc'), 'ghost-chat-grader')
        self.assertEqual(gm.group_of('C--Users-x-AppData-Local-Temp-ga-o1-abc'), 'ga-o1')
        self.assertEqual(gm.group_of('C--Users-x-scratch-2026-11-16-a4f2f2'), 'scratch')
        self.assertEqual(gm.group_of('C--Users-x-Desktop-other'), 'other')


if __name__ == '__main__':
    unittest.main()
