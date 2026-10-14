<!-- shoal-codex:begin -->
<!-- shoal-codex v3.8.0 -->
<!-- markdownlint-disable-next-line MD041 -->
### Workflow extensions

These rules
extend [orchestration-policy.md](orchestration-policy.md). When a rule here
conflicts with that policy, the policy wins: report the conflict to the user
instead of choosing silently. None of these rules expands approval, security,
destructive, external, release, or spending authority.

Never treat role approval, hook trust, or Plugin availability as authorization for policy integration, external mutation, destructive action, release, or security-sensitive work.

## Outcome-level continuation

The execution unit is the requested user-visible outcome, not one command,
one tool call, or one checklist item. Track three internal route fields:

- `execution_scope`: `step`, `slice`, or `outcome`.
- `continuation_mode`: `attended_until_acceptance` or `explicit_unattended`.
- `stop_condition`: `named_boundary`, `acceptance`, `material_gate`, or
  `decision`.

Record these logical signals in the internal route decision:

- `intent_confidence`: `clear`, `partial`, or `unclear`.
- `change_impact`: `trivial`, `low`, `material`, `high`, or `critical`.
  `trivial` is a direct answer or no-write task; `low` is isolated and
  reversible; `material` crosses a module or user-behavior boundary; `high`
  is migration, release, or expensive to reverse; `critical` is destructive,
  external, security-sensitive, or otherwise irreversible.
- `reversible`: `yes`, `partial`, or `no`.
- `discovery_budget`: `none`, `minimum`, `bounded`, or `deep`.
- `budget_exhausted`: whether the selected discovery ceiling was reached.
- `evidence_sufficient`: whether the evidence supports the next gate.
- `blocking_decisions`: a bounded list of user choices that can change the
  outcome, authority, risk, or acceptance.
- `next_gate`: `discovery`, `approval`, `execution`, or `direction_check`.

For a clear `execute` request, default to `execution_scope=outcome` and
`continuation_mode=attended_until_acceptance`. Continue through the necessary
commands, phases, role handoffs, and verification until acceptance evidence is
sufficient. Reporting a phase boundary is progress reporting, not a request
for approval or a reason to pause.

Explicit wording such as "only inspect this file", "先做這一步", or "只改這個
module" selects `step` or `slice` and stops at that named boundary. Wording
such as "finish", "fix", or "complete" selects the requested outcome. If the
product direction is unclear, use the smallest reversible slice and stop at
`decision`.

Material approval, security, release, destructive, external, or irreversible
gates always take precedence and stop at `material_gate`. Acceptance stops the
outcome: do not add cleanup, refactoring, documentation, or adjacent hardening
the user did not request. `AUTO`/`ASK` selection follows the orchestration
policy; outcome continuation by itself never selects `AUTO`.

## Turn-scoped review intent

Keep `review_intent` separate from the task mode. A clear explicit preference
in the current prompt selects `fast`, `default`, or `strict`; it never changes
impact, reversibility, approval, or authority classification.

- `fast` skips optional review and non-required reasoning on non-mandatory
  work. User-named tests and every mandatory gate (independent-review
  triggers, security separation, approval) still run.
- `default` follows the existing risk policy and is the fallback when no clear
  preference is present.
- `strict` requests the complete primary review and test path. It does not
  add a second verifier without new evidence.

- `strict` requests the complete primary review/test path. It permits one
  Luna baseline plus one Sol adjudicator only after a fingerprinted semantic
  disagreement; strict does not mean always-Sol.

The preference is turn-scoped. Do not infer it from task wording, quoted
examples, negation, or vague urgency; conflicting cues fall back to `default`.
Precedence: explicit current-turn `review_intent` > risk policy > default.

Shoal may emit a redacted, versioned advisory signal for `codex-auto-review`, but that scheduler owns optional child creation. A missing consumer never weakens mandatory controls.

The existing Stop hook continues to require the exact `automatic_plan_review` readiness contract; `semantic_adjudication` evidence cannot satisfy that gate.

## Discovery budget

Discovery has a grounding floor and a stopping ceiling. One discovery unit is
one targeted inspection, search, or reversible probe; mechanical reads in one
command count as one unit.

| Budget | Minimum evidence | Default ceiling |
| --- | --- | --- |
| `none` | Context or common sense is sufficient | Zero units |
| `minimum` | One grounding check when the answer depends on local state | Two units |
| `bounded` | Enough evidence to compare the next safe options | Six units and one cheap probe |
| `deep` | Evidence for cross-component, high-impact, or costly-to-reverse work | Ten units and two cheap probes |

Stop early when evidence no longer changes the route. When the floor cannot be
met, state the uncertainty. When the ceiling is reached, narrow, pause, or
ask; exhaustion never becomes write authorization.

## Decision checkpoint

Low-risk, reversible, clearly scoped work proceeds on a reasonable default and
records the assumption; do not ask the user to approve every small ambiguity.
When a decomposition, blocker disposition, risk, permission boundary, or
acceptance choice can change the outcome, emit one checkpoint through
`request_user_input` before continuing the affected task:

Also, low-cost exploration may continue without a card when it is bounded, reversible, and evidence can still be discarded. The policy must not ask the user to approve every small ambiguity.

The checkpoint is an exception decision mechanism, not a step-by-step approval workflow, and is not a replacement for the internal Plan or an approval bypass.

- One high-level question whose answer changes the next gate.
- Two or three mutually exclusive options, recommended option first and
  labelled "(Recommended)".
- Each option states its concrete effect; the question or a preceding line
  states the current interpretation, excluded scope the answer cannot
  authorize, affected tasks, and the resume point.

Resolve replies conservatively: an exact option confirms only that option; a
rejection keeps the affected tasks pending; an ambiguous or multiple reply
stays pending and gets one concise clarification. Never treat a plausible
free-text answer as approval of credentials, external writes, destructive
work, release, or irreversible work. Do not include
credentials, external writes, destructive work, release, or irreversible work
in the card's implied authorization.

Ask follow-ups only after the selected
direction resumes and a new material boundary appears. If `request_user_input`
is unavailable, end with `PAUSED_NEEDS_USER`, one question, choices, and a
recommendation.

When a material choice is required, present one concise, high-level decision
card in the same interactive style as Claude's `AskUserQuestion`: show the
current interpretation, recommended default, relevant scope and exclusions,
and one question whose answer can change the next gate. Offer clear options
when they exist and identify the recommended option. Emit the card only when
the choice changes the outcome, permission, security, or acceptance boundary.
Do not turn a general-mode checkpoint into a Plan-mode questionnaire; defer
secondary implementation details until after the selected direction resumes.

This is an interaction contract, not Plan mode.

The card schema is `shoal-decision-checkpoint-v1` and contains exactly:
`checkpoint_id`, `scope`, `current_interpretation`, `impact`,
`recommended_option`, `options`, `excluded_scope`, `affected_task_ids`,
`resume_point`, and `approval_boundary`. Each option contains an identifier,
short label, and concrete effect. `affected_task_ids` is the smallest set of
tasks whose next result can change; completed or independent sibling tasks are
excluded. `excluded_scope` names work that the answer cannot authorize.

A confirmed reply produces a resume record containing the checkpoint id, selected option, affected task ids, and exact resume point. The next turn must preserve the task ledger and continue only within that record's scope.

#### Optional MCP elicitation adapter

The native decision card is the default interaction surface. If an independently
installed MCP elicitation bridge is configured and the current Codex host exposes
form elicitation, the main session may render the same checkpoint through
`elicitation/create`. This is an optional adapter, not a shoal core
dependency and not a substitute for Codex `request_user_input`.

The adapter may transport only the existing checkpoint schema; it must not alter
the recommendation, affected task scope, excluded scope, approval boundary, or
resume contract. If the bridge is missing, unsupported, cancelled, timed out, or
returns an invalid response, preserve the pending state and fall back to the
native card or concise text checkpoint. Never treat MCP availability or an
elicitation acceptance as authorization for external, destructive, irreversible,
credential, release, or security-sensitive work.

## Task ledger and blocked-task isolation

When one prompt contains multiple independently executable outcomes, split
them into tracked tasks before execution. Use the harness task or todo tool
when available; each task records an outcome, scope, dependencies, state, and
completion evidence. States: `PENDING`, `RUNNING`, `DONE`, `BLOCKED`.

A task is runnable when it is `PENDING`, its dependencies are `DONE`, and no
authority, review, environment, or external prerequisite blocks it. Run
runnable tasks before revisiting blocked ones. A blocked task does not block
siblings unless a dependency edge says so; do not emit `PAUSED_NEEDS_USER`
while runnable tasks remain, and do not repeat unchanged blocker text.

Two or more runnable tasks with
no dependency path or write-ownership conflict should execute horizontally in
parallel, subject to the bounded concurrency limit and the main session's
integration ownership. Tasks with a dependency path execute after their
predecessors; tasks sharing a mutable resource or exclusive file scope are
serialized.

When only blocked tasks remain, emit one consolidated reminder with blocked
task ids, blockers, completed work, and the exact recovery point, then stop.
The goal stays `BLOCKED`, never reported as done. A human response clears only
the affected task and its dependents.

## Continuation across user input

An unfinished objective stays active across decision replies, steering,
corrections, and status or explanation requests unless new input clearly
replaces it. If replacement intent is materially ambiguous, state the active
objective and ask one concise clarification.

Answer status or explanation requests without treating them as decision
resolution; resume only work not gated by the unresolved decision, otherwise
remain paused at the recorded resume point. Incorporate other steering or
corrections and then resume the remaining work unless a pending decision or
user-requested pause still gates it.

Before pausing for input, state the active objective, current phase or slice,
pending decision, and exact resume point. A reply that unambiguously resolves
the pending decision resumes from that point in the same turn within existing
authority. Status or explanation requests do not resolve a decision. Do not
give a normal final response while the objective is incomplete: continue, or
emit `PAUSED_NEEDS_USER` with the blocker, one question, and the resume point.
An explicit user pause is honored without inventing a question.

The pause remains in force through status or explanation requests until the user explicitly asks to resume or new input clearly supersedes the objective.

## Review-service circuit breaker

A missing, failed, or timed-out `plan-critic`, `security-reviewer`, or
`verifier` result is a service failure, not a user decision and not a
verdict. Allow one bounded retry for the same stable unit and role. If the
retry also returns no valid verdict, stop dispatching that role for the unit
and record `WAITING_FOR_REVIEW` (plan or security readiness) or
`PAUSED_VERIFICATION` (outcome or direction verification). Never claim `READY`
or `CONFIRMED`, never substitute a main-session readiness judgment, and never
loop an unchanged retry. Only the affected write or claim is blocked;
read-only work and unrelated approved slices continue.

for outcome or direction verification. Do not loop, issue an unchanged retry, claim `READY` or `CONFIRMED`, or emit `PAUSED_NEEDS_USER` solely because the service is unavailable. Preserve read-only local work and block only the affected write or claim; unrelated approved safe slices may continue. Resume from the recorded gate when a valid receipt or a genuine user decision arrives.

## Direction checkpoint

At multi-slice milestone closes the main session sends the `verifier` a
`direction_checkpoint` brief: the original request, the approved spec's
non-goals and decisions, the declared design invariants
(`docs/DESIGN-INVARIANTS.md` or equivalent), and current evidence. It returns
`CONTINUE`, `PIVOT` (outcome stands; bounded re-plan within approved scope),
or `ROLLBACK` (an invariant or acceptance condition is broken); insufficient
evidence stays `INCONCLUSIVE`. Required when one objective reaches its third
slice (a new spec continuing it counts) and at every later milestone close:
once per milestone, separate from outcome verification, not skipped by `fast`
review intent. At the wrap-up of multi-slice work, main also sends its draft
final report to that checkpoint and corrects the report before sending it to the
user. Before closing a single-slice spec or dispatching architecture
or design work, main runs the same comparison itself; otherwise optional. On
deviation or `ROLLBACK`, stop new writes and report it with a recommendation
(`stop_condition=decision`, or `PAUSED_NEEDS_USER` without interaction);
rolling back is the user's decision. Executor design decisions beyond the
brief (mechanism, interface, naming, omission) are unreviewed: accept or
reject each and record it before merging.

Cost-unbounded continuation applies only when the user explicitly selects it
(in `/goal`, the prompt, or the AUTO/ASK choice). Within approved scope,
continue to acceptance without stopping or asking because of cost, tokens,
time, slice count, discovery budget, or whether to continue. The AUTO stop
list and the milestone direction check stay in force, and the mode grants no
extra authority. At the two-`REVISE` cap, disposition, narrow, or split as
usual, then continue as user-directed continuation; every pass still needs a
material change, otherwise `PAUSED_VERIFICATION`. Escalate only to a higher
executor tier or report to the user; an unresolved P1 outside approved
scope still stops. A `PIVOT` re-plans only within approved scope; beyond it,
stop at `decision`.

<!-- shoal-codex:end -->
