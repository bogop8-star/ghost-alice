"""A later route may select fewer planned units; it may not add or change one."""
import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/autopilot-mode/skill/adapters'))


def contract(unit, revision=1, summary='done'):
    return dict(work_unit_id=unit, contract_revision=revision, owner=dict(platform='claude', session_id='s'),
        criteria=[dict(id=unit + '-1', summary=summary, source='user-explicit')],
        relevant_context=dict(constraints=[], non_goals=[], decisions=[], latest_scope={}))


class PlanContractsTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('autopilot_continuation')
        self.planned = [contract('task-a'), contract('task-b')]

    def holds(self, current):
        return self.module._plan_contracts_hold(current, self.planned)

    def test_same_selection_holds(self):
        self.assertTrue(self.holds([contract('task-a'), contract('task-b')]))

    def test_narrowed_selection_holds(self):
        # 2026-11-25 comparison, case 11 run 3: the route was registered again with
        # only task-a selected after the plan admitted task-a and task-b.
        self.assertTrue(self.holds([contract('task-a')]))
        self.assertTrue(self.holds([contract('task-b')]))

    def test_unplanned_unit_does_not_hold(self):
        self.assertFalse(self.holds([contract('task-a'), contract('task-c')]))

    def test_changed_contract_does_not_hold(self):
        self.assertFalse(self.holds([contract('task-a', revision=2)]))
        self.assertFalse(self.holds([contract('task-a', summary='changed')]))

    def test_empty_selection_does_not_hold(self):
        self.assertFalse(self.holds([]))


if __name__ == '__main__':
    unittest.main()
