<!-- addendum: pending-shared-route-decision-signals at=after:route-fields join=paragraph -->
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

<!-- addendum: pending-shared-low-cost-exploration at=after:checkpoint-default join=paragraph -->
Also, low-cost exploration may continue without a card when it is bounded, reversible, and evidence can still be discarded. The policy must not ask the user to approve every small ambiguity.

<!-- addendum: pending-shared-checkpoint-not-approval at=after:checkpoint-default join=paragraph -->
The checkpoint is an exception decision mechanism, not a step-by-step approval workflow, and is not a replacement for the internal Plan or an approval bypass.

<!-- addendum: pending-shared-review-outage-no-pause at=after:review-circuit-breaker join=paragraph -->
for outcome or direction verification. Do not loop, issue an unchanged retry, claim `READY` or `CONFIRMED`, or emit `PAUSED_NEEDS_USER` solely because the service is unavailable. Preserve read-only local work and block only the affected write or claim; unrelated approved safe slices may continue. Resume from the recorded gate when a valid receipt or a genuine user decision arrives.

<!-- addendum: pending-shared-task-parallelism at=after:ledger-runnable join=paragraph -->
Two or more runnable tasks with
no dependency path or write-ownership conflict should execute horizontally in
parallel, subject to the bounded concurrency limit and the main session's
integration ownership. Tasks with a dependency path execute after their
predecessors; tasks sharing a mutable resource or exclusive file scope are
serialized.

<!-- addendum: pending-shared-status-requests-and-steering at=after:objective-persists join=paragraph -->
Answer status or explanation requests without treating them as decision
resolution; resume only work not gated by the unresolved decision, otherwise
remain paused at the recorded resume point. Incorporate other steering or
corrections and then resume the remaining work unless a pending decision or
user-requested pause still gates it.

<!-- addendum: pending-shared-pause-persists at=after:pause-statement join=paragraph -->
The pause remains in force through status or explanation requests until the user explicitly asks to resume or new input clearly supersedes the objective.

<!-- addendum: codex-strict-adjudication at=after:review-intent-strict join=paragraph -->
- `strict` requests the complete primary review/test path. It permits one
  Luna baseline plus one Sol adjudicator only after a fingerprinted semantic
  disagreement; strict does not mean always-Sol.

<!-- addendum: codex-auto-review-signal at=after:review-intent-turn-scoped join=paragraph -->
Shoal may emit a redacted, versioned advisory signal for `codex-auto-review`, but that scheduler owns optional child creation. A missing consumer never weakens mandatory controls.

<!-- addendum: codex-stop-hook-contract at=after:review-intent-turn-scoped join=paragraph -->
The existing Stop hook continues to require the exact `automatic_plan_review` readiness contract; `semantic_adjudication` evidence cannot satisfy that gate.

<!-- addendum: codex-decision-card at=after:checkpoint-unavailable join=paragraph -->
When a material choice is required, present one concise, high-level decision
card in the same interactive style as Claude's `AskUserQuestion`: show the
current interpretation, recommended default, relevant scope and exclusions,
and one question whose answer can change the next gate. Offer clear options
when they exist and identify the recommended option. Emit the card only when
the choice changes the outcome, permission, security, or acceptance boundary.
Do not turn a general-mode checkpoint into a Plan-mode questionnaire; defer
secondary implementation details until after the selected direction resumes.

<!-- addendum: codex-checkpoint-interaction at=after:checkpoint-unavailable join=paragraph -->
This is an interaction contract, not Plan mode.

<!-- addendum: codex-checkpoint-schema at=after:checkpoint-unavailable join=paragraph -->
The card schema is `shoal-decision-checkpoint-v1` and contains exactly:
`checkpoint_id`, `scope`, `current_interpretation`, `impact`,
`recommended_option`, `options`, `excluded_scope`, `affected_task_ids`,
`resume_point`, and `approval_boundary`. Each option contains an identifier,
short label, and concrete effect. `affected_task_ids` is the smallest set of
tasks whose next result can change; completed or independent sibling tasks are
excluded. `excluded_scope` names work that the answer cannot authorize.

<!-- addendum: codex-checkpoint-resume at=after:checkpoint-unavailable join=paragraph -->
A confirmed reply produces a resume record containing the checkpoint id, selected option, affected task ids, and exact resume point. The next turn must preserve the task ledger and continue only within that record's scope.

<!-- addendum: codex-mcp-elicitation-adapter at=after:checkpoint-unavailable join=paragraph -->
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

<!-- addendum: codex-no-authority-hook-trust at=after:ext-no-authority join=paragraph -->
Never treat role approval, hook trust, or Plugin availability as authorization for policy integration, external mutation, destructive action, release, or security-sensitive work.

<!-- addendum: pending-shared-card-no-implied-authorization at=after:explicit-approval-only join=space -->
Do not include
credentials, external writes, destructive work, release, or irreversible work
in the card's implied authorization.
