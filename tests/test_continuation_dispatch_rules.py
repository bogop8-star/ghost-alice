"""advance_continuation dispatch rules found in the 2026-11-26 interactive retest.

- A finished task outside the current route was dispatched again because its criterion
  was read from the selected projection only.
- "Register only" and "stop after task A" were not respected because the plan was
  dispatched at the same input's Stop.
- An earlier plan whose task was held as `blocked` could not be continued.

The storage and Core material calls are replaced with small fakes so these rules run
without the v2 fixture tree.
"""
import contextlib
import copy
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/autopilot-mode/skill/adapters'))

INPUT = 'sha256:input-1'


def ref(unit, criterion):
    return dict(work_unit_id=unit, contract_revision=1, criterion_id=criterion)


def snapshot(unit, criterion):
    return dict(work_unit_id=unit, contract_revision=1, owner=dict(platform='claude', session_id='s'),
                criteria=[dict(id=criterion, summary=criterion, source='user-explicit')],
                relevant_context=dict(constraints=[], non_goals=[], decisions=[], latest_scope={}))


def task(identity, unit, criterion, status, depends_on=()):
    return dict(id=identity, status=status, focus_layer='micro', prompt='do ' + identity,
                allowed_surface=['test-output/...'], depends_on=list(depends_on), acceptance_criteria=[],
                criterion_refs=[ref(unit, criterion)])


class FakeStore:
    def __init__(self, plan):
        self.plan = plan
        self.connection = object()

    def continuation_plan(self):
        return copy.deepcopy(self.plan)

    def set_continuation_plan(self, value):
        self.plan = copy.deepcopy(value)


class DispatchRulesTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('autopilot_continuation')
        self.root = Path(tempfile.mkdtemp())
        (self.root / self.module.storage.AUTHORITY_FILE).write_text('{}')

    def run_stop(self, plan, *, selected_units, ledger, recordings, input_event_id=INPUT):
        store = FakeStore(plan)
        contracts = [snapshot(u, c) for u, c in selected_units]
        material = dict(selected_work_units=[u for u, _ in selected_units], state_path='x',
                        intent_state=dict(acceptance_criteria=[
                            dict(work_unit_id=u, contract_revision=1, id=c, status=ledger.get((u, 1, c)))
                            for u, c in selected_units]))
        selection = dict(status='selected')
        service = self.module.service

        @contextlib.contextmanager
        def transaction(*_):
            yield store

        patches = [
            mock.patch.object(service, '_v2_run_is_paused', return_value=False),
            mock.patch.object(service, '_v2_claim_scope', return_value=None),
            mock.patch.object(service, '_v2_authority', return_value={}),
            mock.patch.object(service, '_v2_material',
                              return_value=(dict(GHOST_ALICE_SESSION_ID='s'), self.root, {}, material, selection)),
            mock.patch.object(service, '_v2_recording_transaction', side_effect=transaction),
            mock.patch.object(service, '_v2_contracts',
                              return_value=(dict(input_event_id=input_event_id), 'target', contracts)),
            mock.patch.object(self.module.storage, 'read_continuation_plan', return_value=plan),
            mock.patch.object(self.module, '_ledger_statuses', return_value=dict(ledger)),
        ]
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            payload = dict(completion_recording=dict(units=recordings))
            result = self.module.advance_continuation({}, payload)
        return result['continuation'], store.plan

    def plan(self, items, **extra):
        return dict(dict(plan_id='p', target='target',
                         contracts=[snapshot('wu-a', 'A1'), snapshot('wu-b', 'B1')],
                         items=items, dispatches={'task-a': 'old'}, events=[]), **extra)

    def test_finished_task_outside_the_route_is_not_dispatched_again(self):
        # Retest "register only" run 2 (fixed A): A was applied, B ran with a route that
        # selected only B, and at B's Stop task-a was reopened and dispatched again.
        plan = self.plan([task('task-a', 'wu-a', 'A1', 'completed'),
                          task('task-b', 'wu-b', 'B1', 'running', ['task-a'])])
        ledger = {('wu-a', 1, 'A1'): 'met', ('wu-b', 1, 'B1'): 'met'}
        continuation, stored = self.run_stop(plan, selected_units=[('wu-b', 'B1')], ledger=ledger,
            recordings=[dict(work_unit_id='wu-b', status='applied', application_reference='r')])
        self.assertEqual(continuation['status'], 'complete')
        self.assertNotIn('task-proof-invalidated', [e['event'] for e in stored['events']])

    def test_a_criterion_that_really_became_unmet_still_reopens(self):
        plan = self.plan([task('task-a', 'wu-a', 'A1', 'completed'),
                          task('task-b', 'wu-b', 'B1', 'ready', ['task-a'])])
        ledger = {('wu-a', 1, 'A1'): 'unmet', ('wu-b', 1, 'B1'): 'unmet'}
        continuation, stored = self.run_stop(plan, selected_units=[('wu-a', 'A1'), ('wu-b', 'B1')],
                                             ledger=ledger, recordings=[])
        self.assertIn('task-proof-invalidated', [e['event'] for e in stored['events']])

    def test_held_plan_dispatches_nothing_at_the_same_input(self):
        # "지금은 Autopilot 후속 계획만 등록하고 파일은 만들지 마."
        plan = self.plan([task('task-a', 'wu-a', 'A1', 'ready'),
                          task('task-b', 'wu-b', 'B1', 'ready', ['task-a'])], hold_input_event_id=INPUT)
        plan['dispatches'] = {}
        ledger = {('wu-a', 1, 'A1'): 'unmet', ('wu-b', 1, 'B1'): 'unmet'}
        continuation, stored = self.run_stop(plan, selected_units=[('wu-a', 'A1'), ('wu-b', 'B1')],
                                             ledger=ledger, recordings=[])
        self.assertEqual(continuation['status'], 'held')
        self.assertEqual(stored['dispatches'], {})

    def test_held_plan_records_the_task_run_now_but_does_not_hand_over_the_next(self):
        # "계획에 등록한 뒤 A만 실행하고, A가 끝나면 멈추고 B는 실행하지 마."
        plan = self.plan([task('task-a', 'wu-a', 'A1', 'ready'),
                          task('task-b', 'wu-b', 'B1', 'ready', ['task-a'])], hold_input_event_id=INPUT)
        plan['dispatches'] = {}
        ledger = {('wu-a', 1, 'A1'): 'met', ('wu-b', 1, 'B1'): 'unmet'}
        continuation, stored = self.run_stop(plan, selected_units=[('wu-a', 'A1'), ('wu-b', 'B1')], ledger=ledger,
            recordings=[dict(work_unit_id='wu-a', status='applied', application_reference='r')])
        self.assertEqual(continuation['status'], 'held')
        self.assertEqual({t['id']: t['status'] for t in stored['items']}['task-a'], 'completed')
        self.assertNotIn('task-b', stored['dispatches'])

    def test_held_plan_dispatches_after_a_later_input(self):
        plan = self.plan([task('task-a', 'wu-a', 'A1', 'ready')], hold_input_event_id=INPUT)
        plan['dispatches'] = {}
        continuation, _ = self.run_stop(plan, selected_units=[('wu-a', 'A1')],
                                        ledger={('wu-a', 1, 'A1'): 'unmet'}, recordings=[],
                                        input_event_id='sha256:input-2')
        self.assertEqual(continuation['status'], 'dispatched')
        self.assertEqual(continuation['task_id'], 'task-a')

    def test_plan_without_hold_still_dispatches_at_the_same_input(self):
        plan = self.plan([task('task-a', 'wu-a', 'A1', 'ready')])
        plan['dispatches'] = {}
        continuation, _ = self.run_stop(plan, selected_units=[('wu-a', 'A1')],
                                        ledger={('wu-a', 1, 'A1'): 'unmet'}, recordings=[])
        self.assertEqual(continuation['status'], 'dispatched')

    def test_blocked_earlier_task_can_be_continued(self):
        # Retest next-session run 3: task B was registered as blocked in the first session.
        contracts = [dict(work_unit_id=u, contract_revision=1,
                          criteria=[dict(work_unit_id=u, contract_revision=1, id=c, summary=c, source='user-explicit')])
                     for u, c in (('wu-a', 'A1'), ('wu-b', 'B1'))]
        plan = dict(contracts=contracts,
                    items=[task('task-a', 'wu-a', 'A1', 'completed'),
                           task('task-b', 'wu-b', 'B1', 'blocked', ['task-a'])],
                    allowed_surfaces=['test-output/...'])
        rows = [dict(admitted=True, id='B1', summary='B1', source='user-explicit',
                     work_unit_id='wu-b2', contract_revision=1)]
        adopted = self.module._adoption_items(plan, {('wu-a', 1, 'A1'): 'met'}, rows)
        self.assertEqual([(t['id'], t['status'], t['depends_on']) for t in adopted['items']],
                         [('task-b', 'ready', [])])


if __name__ == '__main__':
    unittest.main()
