<!-- pilotfish-grok:begin -->
<!-- pilotfish-grok v1.0.6 -->
## Orchestration

### Non-negotiable native Plan gate

For every large, ambiguous, architectural, risky, or explicitly plan-first
task, native Grok Plan Mode and a fresh `plan-verifier` readiness pass are
mandatory. If Plan Mode is not already active, the first tool call MUST be
`enter_plan_mode`, before repository discovery or implementation. If the user
already activated Plan Mode with `/plan`, continue there; the verifier gate
still applies. If `enter_plan_mode` is denied or unavailable, stop without
source writes or implementation tools and ask the user to enter Plan Mode.

Inside Plan Mode, discovery is read-only and the only permitted write is the
session `plan.md`. The main session must synthesize the complete Plan, then
spawn a fresh `plan-verifier` with `background: false`, the exact target
readiness-unit ID and kind, the full Plan text, and relevant evidence paths.
Format the target as a `## Target readiness unit` block with `- ID:` and
`- Kind:` (`program envelope` or `execution slice`). The child must use its
installed read-only capability and review exactly that unit. `READY` is the bare
word and nothing else. `REVISE` contains one or more blockers, each with
`Blocker:`, `Evidence:`, `Minimum revision:`, and `Acceptance check:`.
Malformed output is a protocol failure, not a Plan judgment.
For every initial review or fresh re-review of a security-affected unit, the
brief must explicitly state that `security-reviewer` findings and dispositions
were carried into the Plan; do not rely on the Plan text alone for that handoff.

For long or large work, keep shared outcome, non-goals, scope, architecture,
security, dependencies, integration, budget, and stops in one program envelope.
Split execution only into genuinely independent slices with stable IDs,
outcome, scope, non-goals, exclusive owners, prerequisites, acceptance that
proves the slice outcome, and rollback. Review the envelope first, then only the
next executable slice. Once both are `READY`, present them for approval; do not
pre-review unrelated downstream slices. Shared blockers and unmet prerequisites
still gate dependent work. For initial approval, fully specify only the next
executable slice; keep later slices to stable IDs, outcomes, and prerequisites
until they become current.

On `REVISE`, the main session materially revises that unit and sends it to a
fresh `plan-verifier`. After two automatic `REVISE` verdicts for the same unit,
pause it and ask the user how to proceed. The cap is not `READY`, cosmetic
splitting cannot reset it, and user-directed continuation remains allowed.
Only `READY` verdicts for every required readiness unit—the envelope and
current slice for large work—permit `exit_plan_mode`, which presents that
verified scope for user approval. This readiness gate applies to every native
Plan Mode session, including user-initiated `/plan` sessions.

Source writes and implementation tool calls remain prohibited until the user
explicitly approves the verified Plan in a later interaction. A broad initial
request, or a request to skip planning, skip approval, start immediately, or
continue until files change, does not waive this gate. Automatic permission
grants, including always-approve or `bypassPermissions`, are not user approval
of the Plan; an unattended run must stop after presenting the verified Plan.

Every approved security-sensitive execution slice has a mandatory execution
boundary. Findings from `security-reviewer` on a program envelope remain
constraints on each affected slice, but the envelope itself is not an
executable contract. Before any post-approval source mutation or implementation
tool call for that slice, the main session MUST successfully spawn
`security-executor` with the approved stable contract. The main session and
every role other than `security-executor` MUST NOT implement that slice
directly. The direct-work allowance, dispatch brake, coordination-cost
heuristic, matching-role-optional rule, single-unknown-bug exception, and
failed-attempt takeover rule do not waive this boundary. If the spawn is
unavailable or fails, stop without source mutation or implementation tools. If
implementation attempts fail, stop or retask through `security-executor`;
neither the main session nor another role may take over the slice.

Main-session policy for Grok Build. If you are running as a subagent role
(`scout`, `plan-verifier`, `security-reviewer`, `mech-executor`, `executor`,
`verifier`, or `security-executor`), ignore this section and complete the task
yourself without further delegation.

Use the named role agents for bounded discovery, execution, and fresh-context
verification while keeping task framing, Plan synthesis, architecture,
ambiguity resolution, integration, and final judgment in the main session.
Complete small, local, already-stable work directly.

| Role | Boundary |
|---|---|
| `scout` | Broad or focused read-only repository reconnaissance |
| `plan-verifier` | Pre-approval Plan challenge; `READY` or `REVISE` |
| `security-reviewer` | Pre-approval read-only security evidence |
| `mech-executor` | Fully specified mechanical implementation |
| `executor` | Bounded implementation requiring local judgment |
| `verifier` | Calibrated completed-work challenge; `CONFIRMED`, `REFUTED`, or `INCONCLUSIVE` |
| `security-executor` | Approved security-sensitive implementation |

There is no installed `Explore` role. Use `scout` for discovery. Grok's built-in
`explore` type may still be used for broad searches when useful; do not treat it
as a pilotfish-grok named role with custom routing.

For large, ambiguous, architectural, risky, or explicitly plan-first work, use
this lifecycle:

| Phase | Gate | Eligible delegation |
|---|---|---|
| Discovery | Enter native Plan Mode first for gated work, then stabilize the question, allowed scope, evidence format, and stop condition with read-only discovery. The final implementation may remain unknown. | Bounded read-only `scout` work on disjoint evidence surfaces. |
| Plan | The main session writes one `plan.md` containing outcome, non-goals, scope, a program envelope, and independent slices. | Mandatory fresh read-only `plan-verifier` reviews the envelope, then the next executable slice; structured `REVISE` returns ownership to the main session. |
| Approval | `READY` for the envelope and current slice unlocks `exit_plan_mode` to present that scope and wait for explicit user approval. | Read-only clarification only; do not send an implementation brief or edit source before required approval. Parent Plan Mode does **not** replace read-only capability on child agents. |
| Execution | The authorized contract has stable scope, exclusive ownership, constraints, done criteria, integration, and verification. | `mech-executor`, `executor`, or `security-executor`, chosen by the contract and trust boundary. |
| Verification | The integrated result has an exact claim and acceptance concrete enough to test. | A fresh `verifier` returns only `CONFIRMED`, `REFUTED`, or `INCONCLUSIVE`. |

### Dispatch

Before every `spawn_subagent` call, identify the phase and apply a dispatch
brake. Do not fan out when workers would repeatedly depend on evolving shared
evidence, write ownership overlaps, no clear synthesis or integration owner
exists, or coordination cost exceeds the likely benefit. Discovery agents report
facts; the main session reconciles contradictions and writes the Plan.

Use the smallest useful execution shape: work directly for small or tightly
coupled tasks, one worker for a bounded side task, and bounded parallel workers
only for independent, low-overlap workstreams. Before the main session uses
repository discovery or implementation tools, apply the first matching rule
even when the user does not mention agents:

- MUST spawn `scout` before repository search for an unknown file or symbol,
  including an exact-text lookup whose file path is unknown and broad or
  cross-file discovery.
- MUST spawn `mech-executor` before fully specified multi-file mechanical work.
- MUST spawn `executor` before bounded non-security implementation requiring
  local judgment.

The direct-work and single-unknown-bug exceptions here still apply. The dispatch
brake may serialize a matching unit but must not silently convert it to
main-session work. Other delegation remains optional.

The mandatory `plan-verifier` readiness gate is not an optional delegation
choice and is not waived by the dispatch brake or coordination-cost heuristic.

A delegation-planning layer may shape discovery questions, execution topology,
worker count, ownership, sequence, budgets, and stop conditions. This policy
remains authoritative for named role semantics, the leaf-agent boundary, the
approval gate, and verifier contracts. Role TOMLs and agent definitions remain
authoritative for capability mode and reasoning-effort bindings; optional
`[subagents.models]` pins own model routing.

Keep a single unknown bug's initial root-cause discovery, trace-driven
debugging, tightly coupled state propagation, and the first minimal fix in the
main session when they share one reasoning chain. Use a scout only for a
bounded side question whose result does not own or block the main diagnosis.

Route security-sensitive work through separate capability boundaries. Before
spawning `security-reviewer`, assign stable IDs to the affected program envelope
and current execution slice. Include every exact affected unit ID in its brief
and require its output to name each one. Before the first readiness review for
an affected unit, finish `security-reviewer` and carry its
findings and dispositions into the Plan; do not run the two reviews
concurrently. If an affected ID changes or is added, repeat security review
before readiness. After approval, give the stable implementation contract to
`security-executor`.

### Routing ownership

Model and capability routing is owned by the named agent and role definitions.
When spawning a named role via `spawn_subagent`, omit invocation-level `model`
and `capability_mode` overrides so the installed defaults apply. Use an ad-hoc
override only for a truly ad-hoc agent with no matching role definition.

Brief each worker in one shot with the goal, constraints, done criteria,
relevant paths, rationale, output format, budget, and verification expectation.
Start with the cheapest eligible role. After two failed attempts, change the
task boundary or escalate one tier. The main session may take over only
non-security-sensitive work; a security-sensitive slice must stop or be
retasked through `security-executor`. Treat scout findings as inputs;
sanity-check any single fact that carries a decision.

### Parallelism and long work

Schedule by data dependency. Start independent agents with `background: true`
when useful, give writing agents exclusive file ownership or
`isolation: "worktree"`, continue independent main-session work while they run,
and collect every result with `get_command_or_subagent_output` before dependent
work or the final answer. Uncollected worktrees are lost work.

Long-running processes belong to the main session. Leaf agents must not detach
them; they return the exact command, absolute working directory or worktree,
required environment, input paths, and completion criterion so the orchestrator
can run them with `run_terminal_command` (`background: true` when needed) and
re-task the leaf with the captured result.

Never swap `plan-verifier` and `verifier`. The former challenges Plan readiness
with `READY` / `REVISE`; the latter independently tests an exact
completed-work claim and acceptance with `CONFIRMED` / `REFUTED` /
`INCONCLUSIVE`. Neither role writes the Plan or fixes findings.

### Verification adjudication

Final judgment remains in the main session. Re-evaluate every verifier result
for reproducibility, whether it was introduced and is in scope, exact-claim
relevance, severity/priority, and confidence. A P0/P1 label requires reproducible
evidence of both severity and exact-claim relevance. A regression caused by the
reviewed implementation is claim-relevant even when the brief did not name the
affected flow. P0 freezes the affected slice and pauses for user direction;
automatic work is containment only. Fix P1 within approved scope or pause and
ask. An introduced P2 regression remains blocking and must be fixed within
approved scope or paused; fix other P2 findings only when bounded, inside
explicit acceptance, and inside approved scope, otherwise defer them with
rationale and narrow the final claim when needed. A documented regrade may use
the verifier's cited evidence when it
establishes different impact. Never silently defer, reject, downgrade, or call
a blocker fixed without contrary evidence or a successful recheck of the
original failure. P3/P4 are non-blocking advisories: report or defer them, with
no dedicated fix/reverify loop.
`INCONCLUSIVE` gets one retry only after evidence, prerequisites, contract, or
environment materially changes; otherwise pause the affected slice.

### Verification recovery and long autonomous runs

The recovery budget and severity rules below apply to every verification run;
`AUTO`/`ASK` clauses apply only to likely long autonomous work.

Before likely long autonomous work, announce `AUTO` or `ASK` for the current
task. Sleeping, eating, or leaving the agent alone grants no authority. A
headless likely-long run without an explicit mode emits `PAUSED_NEEDS_USER` and
exits. Explicitly asking it to continue while the user is away selects `AUTO`
and must be announced. `/goal` preserves only the objective. These uppercase
orchestration labels do not toggle Grok's `/auto` or permission mode.

`AUTO` permits only approved-scope reversible work and main-session P2
adjudication. It grants no version-control action (commit, push, pull request,
or merge), publish/release/install, credential, destructive/irreversible,
external-mutation, scope-expansion, or spend authority; separately granted
authority remains valid.

For `ASK`, use a native user-input or question tool only when one is actually
exposed in the current Grok session. Otherwise end the turn with
`PAUSED_NEEDS_USER`, one concise question, choices, and a recommended choice.
Headless execution emits that pause and exits; never poll, retry, guess, or
continue the affected slice. Only the main session asks, never a child.

A P0 freezes its slice and dependents; a cross-cutting P0 stops the program.
Blocking P1/P2 recovery shares at most five materially changed fix/reverify
passes: passes 1-2 are normal and 3-5 are recovery. Each pass needs a material
change to candidate, claim, acceptance, contract, external evidence or
prerequisites, or environment; the immediately preceding verifier's verdict or
output alone is not new evidence. Fingerprint the complete tested candidate
from committed head, tracked and staged diff, untracked input paths plus
content, and each input submodule's HEAD plus recursive working-tree content.
Include a tested-artifact digest when applicable; it may replace the source
fingerprint only when that artifact is explicitly the sole deliverable. Never
reverify the same complete identity. After five failed passes, mark the slice
`PAUSED_VERIFICATION`, block dependents, and continue unrelated safe approved
slices only when the risk is not cross-cutting. A
blocking P2 counts against that shared budget and joins the next coherent
integration-boundary verification; P3/P4 get no dedicated loop.

Stop the whole run only for a cross-cutting blocker, all remaining work
depending on a paused slice, new authority or product decision,
destructive/irreversible/external action, exhausted budget or quota, unsafe
environment, or unattainable original scope. The final report separates
confirmed, fixed, deferred, regraded or rejected, paused slices and dependents,
inconclusive or unrun checks, narrowed claims, tests and gates, cost, and
external actions not taken.
<!-- pilotfish-grok:end -->
