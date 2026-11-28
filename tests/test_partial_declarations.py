"""A partial answer may name another planned task's criterion only as unverified.

2026-11-26 interactive retest ("A만 시작하세요. B는 Autopilot이 다음 작업으로 넘겨준 뒤에
실행하세요.", run 3): task A's answer listed B-AC1 under acceptance-criteria and unverified,
and A's completion was rejected as "Partial proof declares criteria outside original capture".
"""
import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/autopilot-mode/skill/adapters'))


class PartialDeclarationsTest(unittest.TestCase):
    def setUp(self):
        self.ok = importlib.import_module('autopilot_completion_contract')._partial_declarations_ok

    def test_other_task_criterion_left_unverified_is_accepted(self):
        parsed = dict(acceptance_ids=['A-AC1', 'B-AC1'], unverified_ids=['B-AC1'], criterion_ids=['A-AC1'])
        self.assertTrue(self.ok(parsed, {'A-AC1'}))

    def test_outside_criterion_that_is_not_unverified_is_rejected(self):
        parsed = dict(acceptance_ids=['A-AC1', 'B-AC1'], unverified_ids=[], criterion_ids=['A-AC1'])
        self.assertFalse(self.ok(parsed, {'A-AC1'}))

    def test_criteria_inside_the_capture_are_accepted(self):
        parsed = dict(acceptance_ids=['A-AC1'], unverified_ids=[], criterion_ids=['A-AC1'])
        self.assertTrue(self.ok(parsed, {'A-AC1'}))


if __name__ == '__main__':
    unittest.main()
