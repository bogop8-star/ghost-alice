"""Local fix 2026-11-26: ask for the work route before the first file-changing tool call.

When the route was registered only at Stop, after the work was done and checked, Ghost-ALICE
Autopilot rejected the proof as verified before its origin capture and recorded no completion.
This gate denies a file-changing tool call while the current input has no ready route, so the
assistant records the criterion and route first and the capture precedes the work.

Read-only calls and Ghost-ALICE's own record scripts pass (native_transcript decides), so the
route can always be registered. Sessions whose input is not canonically bound, other platforms,
and any lookup failure are left to the Stop gate. Set GHOST_ALICE_ROUTE_GATE=0 to disable.
Dependencies: Python 3.11+ standard library and this Core's ledger module.
"""
from __future__ import annotations

from pathlib import Path

# Tools that change files. Other tools (web, todo, agents) are not this gate's concern.
_CHANGING_TOOLS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Bash', 'PowerShell'}

_MESSAGE = ('route-before-work: This tool call would change files, but the current input has no Core '
    'response-route yet. Before this call, record the user\'s completion condition through '
    'session-intent-analyzer as an admitted criterion owned by an execution work unit (work_unit_id and '
    'contract_revision), register the route selecting that execution work unit and criterion through '
    'task-router, then retry this same tool call. When the input states no completion condition, register '
    'the route through task-router and retry. Ghost-ALICE Autopilot records completion only for proof '
    'checked after the route exists.')


def route_gate_denial(env, hook_payload):
    """Return the denial reason for this PreToolUse call, or None to let it run."""
    if env.get('GHOST_ALICE_ROUTE_GATE', '1') != '1' or env.get('GHOST_ALICE_PLATFORM') != 'claude':
        return None
    name, data = hook_payload.get('tool_name'), hook_payload.get('tool_input')
    session, root = hook_payload.get('session_id'), env.get('GHOST_ALICE_SESSION_INTENT_ROOT')
    if name not in _CHANGING_TOOLS or not isinstance(session, str) or not session or not root:
        return None
    from native_transcript import _read_only_call
    if _read_only_call(dict(name=name, input=data if isinstance(data, dict) else {})):
        return None
    from native_completion import _ledger, _LEDGER_SCOPE_NOTE
    ledger = _ledger(dict(env, GHOST_ALICE_SESSION_ID=session))
    root = Path(root)
    with ledger._read_connection(root, None) as connection:
        state = ledger._stored_state(connection, 'claude', session)
        if state is None or not ledger._canonical_input_bound(connection, root, state):
            return None
        try:
            route = ledger.read_response_route(root=root, platform='claude', session_id=session,
                                               transaction=connection)
        except ValueError:
            route = None
    if (isinstance(route, dict) and route.get('status') == 'ready'
            and route.get('input_event_id') == state.get('latest_input_event_id')):
        return None
    return _MESSAGE + ' ' + _LEDGER_SCOPE_NOTE
