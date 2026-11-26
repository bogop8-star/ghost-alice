# Approved task continuation

Load this reference when the current-conversation model has identified necessary authorized follow-up work or must register an already authorized conditional dependency plan. The model makes that necessity and authority judgment; the Ghost-ALICE Autopilot API records the supplied plan. Admission checks the current selected criteria and boundary without requiring a completed response review or Stop application. Execution eligibility remains conditional on the recorded dependencies and applied criteria.

Core verification-before-completion owns claim/source and whole-answer review. Resolve its installed references/autopilot-publication.md when preparing a response with new claims. Use this reference for the Ghost-ALICE Autopilot plan handoff.

## Register the approved plan

An unmet criterion or successful publication is not an executable plan. The current-session assistant registers only executable steps already authorized by the human. Resolve `AUTOPILOT_SKILL_ROOT` from the trusted installed Ghost-ALICE Autopilot binding; its `adapters/autopilot_continuation.py` imports sibling modules, so add the `adapters` directory itself to Python's module path.

The assistant prepares a JSON object in permitted runtime scratch at absolute `PLAN_INPUT`. Its `expected_input_event_id` is the current canonical receipt/state event, not an old event attached to a new decision. Its `approval_evidence` is `{"decision":"approved","source":"<compressed actual human authorization and locator>"}`; `approve` and `go` are also accepted decision values, but the assistant cannot invent approval. Its `allowed_surfaces` is a nonempty string list of the actual approved boundaries. Each `items` element contains:

- `id`, `status`, `focus_layer` and `prompt`: a stable nonempty task ID, its actual current task state, the selected focus and a self-contained executable instruction for the receiving assistant. Do not admit an item as `completed` or `not_applicable`; use `blocked` for a missing required decision and `stopped` for an explicit stop.
- `allowed_surface`: nonempty strings within the approved `allowed_surfaces`; `depends_on`: known task IDs forming an acyclic dependency graph; `acceptance_criteria`: criterion descriptions. The latter two may be empty lists.
- `criterion_refs`: nonempty qualified references `{work_unit_id, contract_revision, criterion_id}` copied from the exact current selected, admitted, owned contract. No reference may occur twice within or across items. Omit `attempt` for its initial zero default; do not manufacture completion metadata.

The native host execution tool must retain the current trusted managed runtime environment, including its Core/runtime/owned roots, platform/project context, native v2 capability and any exact existing `GHOST_ALICE_AUTOPILOT_RUN_DIR` or `GHOST_ALICE_AUTOPILOT_CWD` overrides. CORE_ROOT is the trusted runtime GHOST_ALICE_CORE_ROOT (or supplied GHOST_ALICE_SKILLS_DIR fallback); LEDGER_ROOT, PLATFORM, SESSION_ID and the current event come from the exact hook receipt and canonical state. Those receipt bindings must match the runtime context. A missing compatible context leaves admission unavailable; creating a foreign run or inventing overrides is not recovery.

After binding those paths and receipt coordinates, use the exposed shell tool:

```bash
GHOST_ALICE_CORE_ROOT="$CORE_ROOT" \
GHOST_ALICE_SESSION_INTENT_ROOT="$LEDGER_ROOT" \
GHOST_ALICE_PLATFORM="$PLATFORM" \
GHOST_ALICE_SESSION_ID="$SESSION_ID" \
python3 - "$AUTOPILOT_SKILL_ROOT" "$PLAN_INPUT" <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'adapters'))
from autopilot_continuation import register_continuation_plan
plan = json.loads(Path(sys.argv[2]).read_text())
result = register_continuation_plan(dict(os.environ),
    expected_input_event_id=plan['expected_input_event_id'],
    items=plan['items'], approval_evidence=plan['approval_evidence'],
    allowed_surfaces=plan['allowed_surfaces'],
    hold_until_next_input=plan.get('hold_until_next_input', False))
print(json.dumps(result))
PY
```

Set `hold_until_next_input` to `true` in `PLAN_INPUT` when the user's current request says not to run the plan now: "register only", "do not create the files yet", "stop after task A", "do not run task B". The plan is then recorded, but `advance_continuation` dispatches nothing in this session until a later user input; at this input's Stop it reports `continuation: {status: "held"}`. A task the current-session assistant runs itself in this turn (for example task A in "run A, then stop") is still recorded as completed when its proof applies. Use the hold instead of registering a later task as `blocked`: a `blocked` task never becomes dependency-ready without a revised plan. Leave it `false` when the user wants the next task handed over in this session after the current one.

Register the plan with one work unit per task, each owning only that task's criteria, and select all planned work units in the route that admits the plan. After the plan is admitted, do not register a different route for the same input before the response review is recorded: a route change after the review makes the prepared receipt stale and the completion is not recorded.

The API validates current selection, item references, surfaces and dependencies, persists the admitted queue in the resolved Ghost-ALICE Autopilot runtime target, and returns `{"status":"admitted","plan_id":"sha256:..."}`. The assistant retains that returned ID. An identical plan preserves its dispatch state; an invalid binding or shape raises an error and admits no plan. Read the exit status/error rather than claiming admission from the proposed JSON. If scratch files are prohibited, the exposed Python tool may pass the same constructed object directly to this API; it does not waive any origin or schema requirement.

After privileged v2 application, `advance_continuation` maps accepted proof to completed tasks, selects dependency-ready work from the recorded approved queue and records dispatch. Its payload contains `continuation: {status: "dispatched", task_id, criterion_refs, plan_id}` and a `systemMessage` containing the task's prompt, allowed surfaces and criterion references. At Stop, `_format_payload_for_hook` transports that message in stdout JSON as `decision: "block"` with `reason` equal to `systemMessage`. The native host receives this continuation request; if it delivers the request to the conversation that triggered the hook, the model generating that conversation's next response executes the assigned step. The Stop input's session ID identifies the destination; it does not establish reuse of a model process or create a delegated assistant. An already approved plan can consume existing accepted proof during a non-closing partial or explanation response without creating a new publication obligation. Recording-only parked errors do not request this continuation block.

A dispatch record does not prove that the host executed the next action. The current-session assistant receiving that feedback executes and verifies the requested action under host permissions and the selected skill instructions. Actual proof invalidation reopens only affected completed tasks and dependency checks, including a running descendant. A blocked branch does not cancel independent work.

The same unchanged task/criterion state dispatches once, then waits for relevant progress or an explicitly revised plan. A new input alone does not reset that condition. Keep `continuation` distinct from `completion_recording`.

## Continue an earlier session's plan

A plan belongs to the session that admitted it, so a new session cannot advance it. When the user asks the current session to continue an earlier Autopilot plan, the current-session assistant takes over the unfinished tasks as its own plan. The user's request in the current session is the approval evidence; the earlier approval does not authorize the current session by itself. Do not execute the earlier tasks before adoption, and do not report that a task is unknown before listing the earlier plans.

1. List the earlier plans with the same environment bindings as plan registration. `resumable_plans` reads only; it returns, newest first, each earlier session's `session_id`, `plan_id`, `allowed_surfaces`, `completed` task IDs and `unfinished` tasks with their `prompt`, `depends_on` and `criteria_to_admit`.

```bash
GHOST_ALICE_CORE_ROOT="$CORE_ROOT" \
GHOST_ALICE_SESSION_INTENT_ROOT="$LEDGER_ROOT" \
GHOST_ALICE_PLATFORM="$PLATFORM" \
GHOST_ALICE_SESSION_ID="$SESSION_ID" \
python3 - "$AUTOPILOT_SKILL_ROOT" <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'adapters'))
from autopilot_continuation import resumable_plans
print(json.dumps(resumable_plans(dict(os.environ)), ensure_ascii=False, indent=1))
PY
```

2. Choose the plan that matches the user's request. When several earlier plans hold the same unfinished tasks (the same prompts and criteria), continue the newest one without asking. Ask the user only when the matching plans hold different unfinished work.
3. Admit every `criteria_to_admit` entry of the unfinished tasks in the current session's ledger with the exact `id`, `summary` and `source`, under a work unit and contract revision owned by the current session (session-intent-analyzer owns the ledger write). Then register the current response route selecting those work units and criteria (task-router owns route registration).
4. Adopt the plan with the current event, the earlier `session_id` and `plan_id`, and approval evidence that quotes the user's current request:

```bash
GHOST_ALICE_CORE_ROOT="$CORE_ROOT" \
GHOST_ALICE_SESSION_INTENT_ROOT="$LEDGER_ROOT" \
GHOST_ALICE_PLATFORM="$PLATFORM" \
GHOST_ALICE_SESSION_ID="$SESSION_ID" \
python3 - "$AUTOPILOT_SKILL_ROOT" "$EVENT_ID" "$EARLIER_SESSION_ID" "$PLAN_ID" "$APPROVAL_SOURCE" <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'adapters'))
from autopilot_continuation import adopt_continuation_plan
print(json.dumps(adopt_continuation_plan(dict(os.environ), expected_input_event_id=sys.argv[2],
    earlier_session_id=sys.argv[3], plan_id=sys.argv[4],
    approval_evidence={'decision': 'approved', 'source': sys.argv[5]})))
PY
```

The API reads the earlier plan only from the same ledger and platform. It accepts a completed earlier task only when that task's criteria are met in the earlier session's ledger, removes completed tasks from the dependencies of the remaining ones, and maps each remaining criterion reference to the current session's criterion with the same `id`, `summary` and `source`. It then registers the remaining tasks through `register_continuation_plan`, so the same surface, reference and dependency checks apply. It returns `{"status":"admitted","plan_id":...,"adopted_from":{...},"tasks":[...]}`. An error names the missing or changed criterion; admit it as listed and retry instead of editing the earlier session.

5. End the response after adoption. At Stop, `advance_continuation` dispatches the first dependency-ready adopted task to this conversation, and the assistant executes it when that request arrives.
