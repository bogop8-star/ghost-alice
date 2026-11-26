"""A new session can take over the unfinished part of an earlier session's approved plan.

2026-11-25 comparison, case 12: the first session registered tasks A and B, finished A,
and stopped. The next session was asked to continue the same plan, but the plan lived
only in the first session's run, so task B was never dispatched.
"""
import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/autopilot-mode/skill/adapters'))


def ref(unit, criterion, revision=1):
    return dict(work_unit_id=unit, contract_revision=revision, criterion_id=criterion)


def row(unit, criterion, summary, revision=1, source='user-explicit', status='unmet'):
    return dict(work_unit_id=unit, contract_revision=revision, id=criterion, summary=summary,
        source=source, admitted=True, status=status)


def item(identity, refs, *, status='ready', depends=()):
    return dict(id=identity, status=status, depends_on=list(depends), acceptance_criteria=[],
        allowed_surface=['C:/work/out'], focus_layer='meso', prompt='Execute ' + identity, criterion_refs=refs)


A_SUMMARY = 'note.txt contains done'
B_SUMMARY = 'verified.txt contains PASS after note.txt is reread'


def earlier_plan(a_status='completed'):
    contracts = [dict(work_unit_id=u, contract_revision=1, criteria=[row(u, c, s)])
                 for u, c, s in (('task-a', 'A1', A_SUMMARY), ('task-b', 'B1', B_SUMMARY))]
    for contract in contracts:
        for criterion in contract['criteria']:
            criterion.pop('status')
    return dict(plan_id='sha256:earlier', allowed_surfaces=['C:/work/out'], contracts=contracts,
        items=[item('task-a', [ref('task-a', 'A1')], status=a_status),
               item('task-b', [ref('task-b', 'B1')], status='ready', depends=['task-a'])])


class AdoptionItemsTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('autopilot_continuation')
        self.met = {('task-a', 1, 'A1'): 'met', ('task-b', 1, 'B1'): 'unmet'}
        # The new session admitted task B's criterion under its own work unit.
        self.current = [row('resume-b', 'B1', B_SUMMARY)]

    def adopt(self, plan=None, statuses=None, current=None):
        return self.module._adoption_items(plan or earlier_plan(), self.met if statuses is None else statuses,
                                           self.current if current is None else current)

    def test_only_unfinished_tasks_are_taken_over(self):
        result = self.adopt()
        self.assertEqual([t['id'] for t in result['items']], ['task-b'])
        self.assertEqual(result['completed'], ['task-a'])
        self.assertEqual(result['allowed_surfaces'], ['C:/work/out'])

    def test_finished_dependency_is_satisfied_and_task_is_ready(self):
        task = self.adopt()['items'][0]
        self.assertEqual(task['depends_on'], [])
        self.assertEqual(task['status'], 'ready')

    def test_criterion_refs_point_to_this_sessions_contract(self):
        self.assertEqual(self.adopt()['items'][0]['criterion_refs'], [ref('resume-b', 'B1')])

    def test_unrecorded_criterion_in_this_session_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'B1'):
            self.adopt(current=[])

    def test_changed_criterion_definition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'B1'):
            self.adopt(current=[row('resume-b', 'B1', 'something else')])

    def test_completed_task_without_met_proof_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'task-a'):
            self.adopt(statuses={('task-a', 1, 'A1'): 'unmet'})

    def test_unfinished_dependency_keeps_waiting(self):
        result = self.adopt(plan=earlier_plan(a_status='running'),
                            current=[row('resume-a', 'A1', A_SUMMARY), row('resume-b', 'B1', B_SUMMARY)])
        self.assertEqual([t['id'] for t in result['items']], ['task-a', 'task-b'])
        self.assertEqual(result['items'][0]['status'], 'ready')
        self.assertEqual(result['items'][1]['depends_on'], ['task-a'])

    def test_finished_plan_has_nothing_to_take_over(self):
        plan = earlier_plan()
        plan['items'][1]['status'] = 'completed'
        with self.assertRaisesRegex(ValueError, 'nothing'):
            self.adopt(plan=plan, statuses={('task-a', 1, 'A1'): 'met', ('task-b', 1, 'B1'): 'met'})


class AdoptionSourceTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('autopilot_continuation')

    def test_same_session_cannot_adopt_itself(self):
        run = Path('C:/home/.ghost-alice/autopilot/sessions/claude/new')
        with self.assertRaisesRegex(ValueError, 'another session'):
            self.module._earlier_run_dir(run, 'new', 'new')

    def test_only_a_sibling_session_run_is_used(self):
        run = Path('C:/home/.ghost-alice/autopilot/sessions/claude/new')
        self.assertEqual(self.module._earlier_run_dir(run, 'new', 'old'), run.parent / 'old')
        for bad in ('../old', 'a/b', ''):
            with self.assertRaises(ValueError):
                self.module._earlier_run_dir(run, 'new', bad)

    def test_non_session_run_cannot_adopt(self):
        with self.assertRaisesRegex(ValueError, 'session'):
            self.module._earlier_run_dir(Path('C:/runs/explicit'), 'new', 'old')


if __name__ == '__main__':
    unittest.main()
