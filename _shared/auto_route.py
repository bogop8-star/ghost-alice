"""IMP item 2': Core registers the response-route at Stop instead of blocking for it.

Condition (the same one under which the original Stop guard reports
`route-unavailable`): the current human input is canonically bound, native tool
calls happened after it, and there is no ready route for that input.

Purpose comes from the answer's first line, `[purpose: execution]` or
`[purpose: explanation]`. A missing or unreadable marker defaults to
`explanation`, so the Stop guard keeps requiring a response review exactly where
a model-declared explanation would. The route selects no work units, like the
routes models registered by hand in the baseline sessions.

Set GHOST_ALICE_IMP_AUTO_ROUTE=0 to disable.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

PURPOSE_LINE = re.compile(r'^\s*\[purpose:\s*(execution|explanation)\s*\]\s*(?:\r?\n|$)', re.IGNORECASE)


def declared_purpose(text: str) -> str:
    match = PURPOSE_LINE.match(text or '')
    return match.group(1).lower() if match else 'explanation'


def strip_purpose_line(text: str) -> str:
    return PURPOSE_LINE.sub('', text or '', count=1)


def _candidate(purpose: str) -> dict:
    order = ('causal-answer-first-after-necessary-evidence' if purpose == 'explanation'
             else 'imperative-result-first-after-necessary-work')
    return {
        'schema_version': 'response-route.v1',
        'response_purpose': purpose,
        'routing_surface': {
            'intent_relation': 'new', 'response_mode': 'normal', 'response_order': order,
            'change_depth': 'minimal', 'focus_layer': 'micro', 'verification_complexity': 'level-1',
            'boundary_contract': 'n/a', 'forced_visibility': 'no',
            'primary_request': 'current input (route registered by Core at Stop)',
            'causal_axis': 'n/a',
            'reason': f'automatic route registration; purpose={purpose} from the answer marker or default',
        },
        'work_units': [], 'selected_work_unit_ids': [], 'selected_criteria': [],
    }


def auto_register_route(source: dict, text: str, native_input: dict) -> str | None:
    """Register the current input's route when the original guard would block; return the purpose."""
    if os.environ.get('GHOST_ALICE_IMP_AUTO_ROUTE', '1') != '1':
        return None
    platform, session = source.get('GHOST_ALICE_PLATFORM'), source.get('GHOST_ALICE_SESSION_ID')
    root = source.get('GHOST_ALICE_SESSION_INTENT_ROOT')
    if platform != 'claude' or not session or not isinstance(root, str) or not Path(root).is_absolute():
        return None
    from native_completion import _ledger
    from native_transcript import native_tool_activity
    import response_route
    ledger = _ledger(source)
    with ledger._read_connection(Path(root), None) as connection:
        state = ledger._stored_state(connection, platform, session)
        if state is None or not ledger._canonical_input_bound(connection, Path(root), state):
            return None
        event = state.get('latest_input_event_id')
        observation = dict(input_digest=state.get('latest_input_digest'),
                           input_char_count=state.get('latest_input_char_count'))
        try:
            route = ledger.read_response_route(root=Path(root), platform=platform, session_id=session,
                                               transaction=connection)
        except ValueError:
            route = None
    if isinstance(route, dict) and route.get('status') == 'ready' and route.get('input_event_id') == event:
        return None
    activity = native_tool_activity(platform, session, native_input, input_observation=observation)
    if activity.get('status') != 'observed':
        return None
    purpose = declared_purpose(text)
    response_route.record_response_route(Path(root), platform, session, event, _candidate(purpose), None)
    return purpose
