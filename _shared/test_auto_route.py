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


if __name__ == '__main__':
    unittest.main()
