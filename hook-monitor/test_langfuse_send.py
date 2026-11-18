"""Tests for what the hook-flow sender transmits to Langfuse, and how often.

Two outside contracts set the expected results:
- Langfuse treats traces and observations as immutable. A record sent again with the same id is stored as a
  duplicate, not as an update, and duplicates inflate metrics (https://langfuse.com/faq/all/tracing-data-updates).
  So a turn is sent exactly once, and only after it has ended.
- The user id is a trace-level property that Langfuse reads from the `langfuse.user.id` attribute of each span
  (https://langfuse.com/integrations/native/opentelemetry, "Property mapping"). Hook records carry the same
  user id as the conversation records sent by the Langfuse Claude Code plugin.

Run: python -X utf8 -m unittest discover -s hook-monitor -p "test_*.py"
"""
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import explain  # noqa: E402
import langfuse_sync  # noqa: E402
import timeline  # noqa: E402
from test_explain import BLOCK, PASS, one_input  # noqa: E402

SESSION = '11111111-2222-3333-4444-555555555555'
CONFIG = {'LANGFUSE_PUBLIC_KEY': 'pk-lf-test', 'LANGFUSE_SECRET_KEY': 'sk-lf-test',
          'LANGFUSE_BASE_URL': 'https://langfuse.invalid'}


def session_data(*turn_stops):
    """An explained timeline with one turn per argument; each argument lists that turn's Stop hook results."""
    rows = []
    for number, stops in enumerate(turn_stops):
        rows += one_input(f'2026-11-13T03:{10 + number * 2}', stops=list(stops))
    data = timeline.assemble(SESSION, rows)
    data.update(stages=explain.STAGES, level_labels=explain.LEVEL_LABEL)
    return data


def attributes(span):
    return {a['key']: a['value'].get('stringValue') for a in span['attributes']}


class FakeLangfuse:
    """Stands in for the Langfuse client: keeps every span it is asked to store."""

    def __init__(self):
        self.spans = []
        self.fail = False

    def post(self, path, body, extra_headers=None):
        if self.fail:
            raise langfuse_sync.SyncError(f'{path} → HTTP 500')
        for resource in body['resourceSpans']:
            for scope in resource['scopeSpans']:
                self.spans += scope['spans']
        return {}

    def trace_names(self):
        return sorted({attributes(span)['langfuse.trace.name'] for span in self.spans})


class UserIdTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Path(folder.name)
        self.plugin_settings = self.workspace / 'claude-settings.json'
        patches = [mock.patch.object(langfuse_sync, 'PLUGIN_SETTINGS', self.plugin_settings),
                   mock.patch.dict(os.environ)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        os.environ.pop('LANGFUSE_USER_ID', None)

    def set_plugin_user(self, value):
        self.plugin_settings.write_text(json.dumps({'pluginConfigs': {
            'langfuse-observability@langfuse-observability': {'options': {'LANGFUSE_USER_ID': value}}}}), encoding='utf-8')

    def test_every_span_carries_the_user_id(self):
        spans = langfuse_sync.timeline_spans(session_data([PASS], [PASS]), 'jy')
        self.assertTrue(spans)
        for span in spans:
            self.assertEqual(attributes(span).get('langfuse.user.id'), 'jy', span['name'])

    def test_no_user_id_attribute_is_sent_when_none_is_set(self):
        for span in langfuse_sync.timeline_spans(session_data([PASS])):
            self.assertNotIn('langfuse.user.id', attributes(span))

    def test_user_id_is_the_one_set_for_the_langfuse_plugin(self):
        self.set_plugin_user('jy')
        self.assertEqual(langfuse_sync.user_id(self.workspace), 'jy')

    def test_user_id_in_the_workspace_env_file_wins_over_the_plugin_setting(self):
        self.set_plugin_user('jy')
        (self.workspace / '.env').write_text('LANGFUSE_PUBLIC_KEY=pk\nLANGFUSE_USER_ID="alice"\n', encoding='utf-8')
        self.assertEqual(langfuse_sync.user_id(self.workspace), 'alice')

    def test_user_id_in_the_environment_wins_over_everything(self):
        self.set_plugin_user('jy')
        (self.workspace / '.env').write_text('LANGFUSE_USER_ID=alice\n', encoding='utf-8')
        os.environ['LANGFUSE_USER_ID'] = 'bob'
        self.assertEqual(langfuse_sync.user_id(self.workspace), 'bob')

    def test_user_id_is_empty_when_nothing_is_set(self):
        self.assertEqual(langfuse_sync.user_id(self.workspace), '')


class SendOnceTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.workspace = Path(folder.name)
        self.sent_dir = self.workspace / 'langfuse-sent'
        self.langfuse = FakeLangfuse()
        self.config = dict(CONFIG)
        patches = [mock.patch.object(langfuse_sync, '_connect', lambda workspace: (self.config, self.langfuse)),
                   mock.patch.object(langfuse_sync, 'user_id', lambda workspace: 'jy')]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def send(self, data, **options):
        return langfuse_sync.sync_session(self.workspace, data, sent_dir=self.sent_dir, **options)

    def test_ended_turns_are_sent_and_the_turn_in_progress_is_held(self):
        result = self.send(session_data([PASS], [PASS], []))
        self.assertEqual(self.langfuse.trace_names(), ['Ghost-ALICE · turn 1', 'Ghost-ALICE · turn 2'])
        self.assertEqual((result['traces'], result['waiting']), (2, 1))

    def test_sending_again_without_changes_sends_nothing(self):
        self.send(session_data([PASS], [PASS], []))
        stored = len(self.langfuse.spans)
        result = self.send(session_data([PASS], [PASS], []))
        self.assertEqual(len(self.langfuse.spans), stored)
        self.assertEqual((result['traces'], result['observations'], result['skipped']), (0, 0, 2))

    def test_a_turn_is_sent_when_it_ends_and_no_record_is_ever_sent_twice(self):
        self.send(session_data([PASS], [PASS], []))
        result = self.send(session_data([PASS], [PASS], [PASS], []))
        self.assertEqual(result['traces'], 1)
        self.send(session_data([PASS], [PASS], [PASS], [PASS]))
        self.assertEqual(self.langfuse.trace_names(),
                         ['Ghost-ALICE · turn 1', 'Ghost-ALICE · turn 2', 'Ghost-ALICE · turn 3', 'Ghost-ALICE · turn 4'])
        copies = Counter((span['traceId'], span['spanId']) for span in self.langfuse.spans)
        self.assertEqual(max(copies.values()), 1)

    def test_a_blocked_turn_waits_until_claude_gets_past_the_block(self):
        result = self.send(session_data([PASS], [BLOCK]))
        self.assertEqual((self.langfuse.trace_names(), result['waiting']), (['Ghost-ALICE · turn 1'], 1))
        self.send(session_data([PASS], [BLOCK, PASS]))
        self.assertEqual(self.langfuse.trace_names(), ['Ghost-ALICE · turn 1', 'Ghost-ALICE · turn 2'])

    def test_an_unfinished_turn_is_sent_once_the_next_turn_has_started(self):
        self.send(session_data([PASS], [BLOCK]))
        self.send(session_data([PASS], [BLOCK], []))
        self.assertEqual(self.langfuse.trace_names(), ['Ghost-ALICE · turn 1', 'Ghost-ALICE · turn 2'])

    def test_the_final_send_of_a_session_includes_the_unfinished_turn(self):
        result = self.send(session_data([PASS], []), final=True)
        self.assertEqual(self.langfuse.trace_names(), ['Ghost-ALICE · turn 1', 'Ghost-ALICE · turn 2'])
        self.assertEqual((result['traces'], result['waiting']), (2, 0))

    def test_sent_records_carry_the_user_id(self):
        self.send(session_data([PASS]))
        self.assertEqual({attributes(span).get('langfuse.user.id') for span in self.langfuse.spans}, {'jy'})

    def test_a_refused_request_is_not_remembered_as_sent(self):
        self.langfuse.fail = True
        with self.assertRaises(langfuse_sync.SyncError):
            self.send(session_data([PASS], [PASS]))
        self.langfuse.fail = False
        result = self.send(session_data([PASS], [PASS]))
        self.assertEqual(result['traces'], 2)

    def test_another_langfuse_project_receives_each_ended_turn_once(self):
        self.send(session_data([PASS], [PASS]))
        self.config['LANGFUSE_PUBLIC_KEY'] = 'pk-lf-other-project'
        result = self.send(session_data([PASS], [PASS]))
        self.assertEqual(result['traces'], 2)
        self.assertEqual(self.send(session_data([PASS], [PASS]))['traces'], 0)

    def test_a_session_without_hook_records_is_refused(self):
        with self.assertRaises(langfuse_sync.SyncError):
            self.send({'session': SESSION, 'turns': []})


class BuildWithoutSavingTest(unittest.TestCase):
    """The automatic sender reads a session while the monitor may be writing the same snapshot file."""

    def build(self, **options):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = {'log_root': root / 'logs', 'ledger_root': root / 'ledger', 'trace': root / 'io-trace.jsonl',
                      'transcripts': root / 'projects' / 'watched-folder', 'snapshots': root / 'timelines'}
            log = config['log_root'] / SESSION / 'strict-hook-output.jsonl'
            log.parent.mkdir(parents=True)
            log.write_text('\n'.join(json.dumps(row) for row in one_input('2026-11-13T03:10', stops=[PASS])), encoding='utf-8')
            built = timeline.build(SESSION, config, **options)
            return built, (config['snapshots'] / f'{SESSION}.json').exists()

    def test_the_snapshot_is_written_by_default(self):
        built, saved = self.build()
        self.assertTrue(built['turns'])
        self.assertTrue(saved)

    def test_no_snapshot_is_written_when_saving_is_turned_off(self):
        built, saved = self.build(save=False)
        self.assertTrue(built['turns'])
        self.assertFalse(saved)


if __name__ == '__main__':
    unittest.main()
