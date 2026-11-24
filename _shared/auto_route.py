"""IMP item 2': Core registers the response-route at Stop instead of blocking for it.

Condition (the same one under which the original Stop guard reports
`route-unavailable`): the current human input is canonically bound, native tool
calls happened after it, and there is no ready route for that input. Sessions
with open admitted acceptance criteria are left to the original guard, because
their route must carry execution work units for Ghost-ALICE Autopilot.

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


FILE_CHANGING_TOOLS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}
# Same met statuses as Ghost-ALICE Autopilot (autopilot_intent_recovery.MET_CRITERION_STATUSES).
MET_STATUSES = frozenset({'met', 'done', 'satisfied', 'pass', 'passed', 'complete', 'completed', 'resolved', 'closed'})


def has_open_criteria(state) -> bool:
    """True when the session holds an admitted acceptance criterion that is not met yet."""
    criteria = state.get('acceptance_criteria') if isinstance(state, dict) else None
    return any(isinstance(c, dict) and c.get('admitted', True) is not False
               and str(c.get('status') or 'unmet').strip().lower() not in MET_STATUSES
               for c in criteria or [])


def _turn_blocks(transcript_path):
    """Assistant content blocks after the current human input (empty when unreadable)."""
    import json
    from native_transcript import is_actual_user_prompt
    try:
        rows = [json.loads(line) for line in Path(transcript_path).read_text(encoding='utf-8').splitlines()
                if line.strip()]
    except (OSError, TypeError, ValueError):
        return []
    start = max((i for i, row in enumerate(rows) if isinstance(row, dict) and is_actual_user_prompt(row)
                 and not row.get('isSidechain')), default=-1)
    blocks = []
    for row in rows[start + 1:]:
        if isinstance(row, dict) and row.get('type') == 'assistant' and not row.get('isSidechain'):
            blocks += [b for b in (row.get('message') or {}).get('content') or [] if isinstance(b, dict)]
    return blocks


def turn_purpose(final_text: str, transcript_path) -> str:
    """Purpose for this turn's automatic route.

    Marker: the final answer's first line, else the first marker in this turn's
    assistant text blocks (models often state it before tool calls).

    IMP v2 review rule: `execution` is accepted only when this turn changed files
    (a file-changing tool ran). An answer that only read and reported is an
    explanation and keeps response review, whatever the marker says.
    """
    blocks = _turn_blocks(transcript_path)
    declared = None
    if PURPOSE_LINE.match(final_text or ''):
        declared = declared_purpose(final_text)
    else:
        for block in blocks:
            if block.get('type') == 'text' and PURPOSE_LINE.match(block.get('text') or ''):
                declared = declared_purpose(block['text'])
                break
    changed_files = any(b.get('type') == 'tool_use' and b.get('name') in FILE_CHANGING_TOOLS for b in blocks)
    return 'execution' if declared == 'execution' and changed_files else 'explanation'


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
        if has_open_criteria(state):
            # Admitted completion conditions mean execution work units and
            # Ghost-ALICE Autopilot recording; keep the original guard so the
            # assistant registers that route itself.
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
    purpose = turn_purpose(text, native_input.get('transcript_path') or native_input.get('transcriptPath'))
    response_route.record_response_route(Path(root), platform, session, event, _candidate(purpose), None)
    return purpose
