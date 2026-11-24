"""IMP item 2': purpose marker parsing and its default."""
import unittest

import auto_route


class PurposeMarkerTests(unittest.TestCase):
    def test_marker_on_first_line_sets_purpose(self):
        self.assertEqual(auto_route.declared_purpose('[purpose: execution]\nDone.'), 'execution')
        self.assertEqual(auto_route.declared_purpose('  [Purpose: Explanation]\r\nBecause...'), 'explanation')

    def test_missing_or_misplaced_marker_defaults_to_explanation(self):
        self.assertEqual(auto_route.declared_purpose('Done.'), 'explanation')
        self.assertEqual(auto_route.declared_purpose('Done.\n[purpose: execution]'), 'explanation')
        self.assertEqual(auto_route.declared_purpose('[purpose: delete-everything]\nx'), 'explanation')
        self.assertEqual(auto_route.declared_purpose(''), 'explanation')

    def test_strip_removes_only_the_leading_marker(self):
        self.assertEqual(auto_route.strip_purpose_line('[purpose: execution]\nDone.'), 'Done.')
        self.assertEqual(auto_route.strip_purpose_line('Done.'), 'Done.')

    def test_candidate_selects_no_work_and_keeps_purpose(self):
        candidate = auto_route._candidate('explanation')
        self.assertEqual(candidate['response_purpose'], 'explanation')
        self.assertEqual(candidate['work_units'], [])
        self.assertEqual(candidate['selected_criteria'], [])

    def test_turn_purpose_reads_marker_from_first_message_of_the_turn(self):
        import json
        import tempfile
        from pathlib import Path
        def user(text):
            return dict(type='user', message=dict(role='user', content=text))
        def assistant(text):
            return dict(type='assistant', message=dict(content=[dict(type='text', text=text)]))
        def tool(name):
            return dict(type='assistant', message=dict(content=[dict(type='tool_use', name=name, input={})]))
        head = [user('old question'), assistant('[purpose: explanation]\nold'), user('make hello.txt')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 't.jsonl'
            def write(rows):
                path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
            # execution marker in the first message + a file-changing tool -> execution
            write(head + [assistant('[purpose: execution]'), tool('Write'), assistant('Created.')])
            self.assertEqual(auto_route.turn_purpose('Created.', str(path)), 'execution')
            # no marker -> explanation
            write(head + [tool('Write'), assistant('Created.')])
            self.assertEqual(auto_route.turn_purpose('Created.', str(path)), 'explanation')

    def test_v2_rule_read_only_turn_stays_explanation_despite_execution_marker(self):
        import json
        import tempfile
        from pathlib import Path
        rows = [dict(type='user', message=dict(role='user', content='count lines')),
                dict(type='assistant', message=dict(content=[dict(type='text', text='[purpose: execution]')])),
                dict(type='assistant', message=dict(content=[dict(type='tool_use', name='Bash', input={})])),
                dict(type='assistant', message=dict(content=[dict(type='tool_use', name='Read', input={})]))]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 't.jsonl'
            path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
            self.assertEqual(auto_route.turn_purpose('It has 17 lines.', str(path)), 'explanation')
            self.assertEqual(auto_route.turn_purpose('[purpose: execution]\nIt has 17 lines.', str(path)), 'explanation')
        self.assertEqual(auto_route.turn_purpose('x', None), 'explanation')


    def test_open_admitted_criteria_keep_the_original_route_guard(self):
        open_ = dict(acceptance_criteria=[dict(id='AC1', work_unit_id='w', admitted=True, status='unmet')])
        default_unmet = dict(acceptance_criteria=[dict(id='AC1', work_unit_id='w')])
        met = dict(acceptance_criteria=[dict(id='AC1', work_unit_id='w', status='met')])
        not_admitted = dict(acceptance_criteria=[dict(id='AC1', work_unit_id='w', admitted=False)])
        self.assertTrue(auto_route.has_open_criteria(open_))
        self.assertTrue(auto_route.has_open_criteria(default_unmet))
        self.assertFalse(auto_route.has_open_criteria(met))
        self.assertFalse(auto_route.has_open_criteria(not_admitted))
        self.assertFalse(auto_route.has_open_criteria({}))

if __name__ == '__main__':
    unittest.main()
