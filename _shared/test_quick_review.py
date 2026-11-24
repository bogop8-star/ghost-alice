"""IMP v3: one-command response review."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import quick_review


def _rows():
    return [
        dict(type='user', message=dict(role='user', content='old question')),
        dict(type='assistant', message=dict(content=[dict(type='tool_use', id='old', name='Bash', input={'command': 'ls'})])),
        dict(type='user', message=dict(role='user', content=[dict(type='tool_result', tool_use_id='old', content='OLD')])),
        dict(type='user', message=dict(role='user', content='How many lines in README.md?')),
        dict(type='assistant', message=dict(content=[dict(type='tool_use', id='t1', name='Bash',
                                                          input={'command': 'wc -l README.md'})])),
        dict(type='user', message=dict(role='user', content=[dict(type='tool_result', tool_use_id='t1',
                                                                  content='17 README.md')])),
        dict(type='assistant', message=dict(content=[dict(type='text', text='README.md has 17 lines.')])),
    ]


class QuickReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.transcript = self.root / 't.jsonl'
        self.transcript.write_text('\n'.join(json.dumps(r) for r in _rows()), encoding='utf-8')
        self.source = dict(GHOST_ALICE_SESSION_INTENT_ROOT=str(self.root), GHOST_ALICE_SESSION_ID='s1',
                           GHOST_ALICE_PLATFORM='claude')

    def tearDown(self):
        self.tmp.cleanup()

    def test_sources_are_only_this_turns_calls_with_input_and_result(self):
        sources = quick_review.turn_sources(self.transcript)
        self.assertEqual([tid for tid, _ in sources], ['t1'])
        self.assertIn('wc -l README.md', sources[0][1])
        self.assertIn('17 README.md', sources[0][1])

    def test_locate_tolerates_whitespace_only(self):
        self.assertEqual(quick_review._locate('has  17\nlines', 'README.md has 17 lines.'), 'has 17 lines')
        self.assertIsNone(quick_review._locate('has 18 lines', 'README.md has 17 lines.'))

    def _run(self, review):
        quick_review.save_pending(self.source, 'README.md has 17 lines.', self.transcript)
        calls = {}

        def prepare(source, *, response_text, source_paths, claim_statements):
            calls['prepare'] = (response_text, source_paths, claim_statements)
            return dict(candidate_reference='c1', response_binding=dict(binding_id='r1'),
                        bindings=[dict(binding_id=f'b{i}') for i, _ in enumerate(claim_statements)],
                        sources=[dict(locator=p, source_id=f'id-{i}') for i, p in enumerate(source_paths)])

        def record(source, reference, review):
            calls['record'] = (reference, review)
            return dict(status='reviewed')

        with mock.patch('completion_assessment.prepare_response_review', prepare), \
                mock.patch('completion_assessment.record_response_review', record):
            result = quick_review.review_once(self.source, review)
        return result, calls

    def test_supported_claim_with_real_evidence_records_both_judgments(self):
        result, calls = self._run(dict(
            claims=[dict(claim='README.md has 17 lines.', evidence='17 README.md', verdict='supported',
                         rationale='wc -l printed 17')],
            response=dict(verdict='supported', rationale='answers the question exactly')))
        self.assertEqual(result['status'], 'reviewed')
        text, paths, statements = calls['prepare']
        self.assertEqual(text, 'README.md has 17 lines.')
        self.assertEqual(statements, ['README.md has 17 lines.'])
        self.assertEqual(len(paths), 1)
        self.assertIn('17 README.md', Path(paths[0]).read_text(encoding='utf-8'))
        _, review = calls['record']
        self.assertEqual(review['claims'][0]['source_ids'], ['id-0'])
        self.assertEqual(review['response']['binding_id'], 'r1')
        self.assertFalse((self.root / 'quick-review' / 's1' / 'pending.json').exists())

    def test_invented_evidence_is_rejected(self):
        with self.assertRaisesRegex(quick_review.QuickReviewError, 'verbatim excerpt'):
            self._run(dict(
                claims=[dict(claim='README.md has 17 lines.', evidence='18 README.md', verdict='supported',
                             rationale='x')],
                response=dict(verdict='supported', rationale='x')))

    def test_evidence_from_an_earlier_turn_is_rejected(self):
        with self.assertRaisesRegex(quick_review.QuickReviewError, 'verbatim excerpt'):
            self._run(dict(
                claims=[dict(claim='README.md has 17 lines.', evidence='OLD', verdict='supported', rationale='x')],
                response=dict(verdict='supported', rationale='x')))

    def test_claim_missing_from_answer_is_rejected(self):
        with self.assertRaisesRegex(quick_review.QuickReviewError, 'not found in the answer'):
            self._run(dict(
                claims=[dict(claim='README.md has 18 lines.', evidence='17 README.md', verdict='supported',
                             rationale='x')],
                response=dict(verdict='supported', rationale='x')))

    def test_without_pending_answer_nothing_is_recorded(self):
        with self.assertRaisesRegex(quick_review.QuickReviewError, 'no blocked answer'):
            quick_review.review_once(self.source, dict(
                claims=[dict(claim='a', evidence='b', verdict='supported', rationale='c')],
                response=dict(verdict='supported', rationale='d')))

    def test_block_reason_is_self_contained(self):
        text = quick_review.block_reason(self.source)
        self.assertIn('quick_review.py', text)
        self.assertIn("--session s1", text)
        self.assertNotIn('references/', text)


if __name__ == '__main__':
    unittest.main()
