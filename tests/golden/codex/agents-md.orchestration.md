<!-- shoal-codex:begin -->
<!-- shoal-codex v3.4.2 -->
<!-- markdownlint-disable-next-line MD041 -->
### Orchestration

Main-session policy. Named roles (`scout`, `plan-critic`, `security-reviewer`, `applier`, `executor`, `verifier`, `security-executor`, `watcher`, `researcher`, `sol-executor`): ignore this section, perform assigned task, never spawn
subagents.

Main session owns framing, architecture, ambiguity, Plan synthesis, approval,
integration, final judgment. Roles supply bounded discovery, execution,
fresh-context review.

Shoal orchestration is active. Preserve the user's Persona and Agent Rules;
shoal supplements them and does not replace their precedence boundary.

| Role | Boundary |
|---|---|
| `scout` | Broad or focused read-only repository reconnaissance |
| `plan-critic` | Pre-approval Plan challenge; `READY` or `REVISE` |
| `security-reviewer` | Pre-approval read-only security evidence |
| `applier` | Fully specified mechanical implementation |
| `sol-executor` | Bounded implementation using normal engineering judgment |
| `executor` | Bounded implementation requiring local judgment |
| `verifier` | Calibrated completed-work falsification; `CONFIRMED`, `REFUTED`, or `INCONCLUSIVE` |
| `security-executor` | Approved security-sensitive implementation |
| `watcher` | Long-running command or CI run followed to a terminal state; reports exit status and deciding output |
| `researcher` | Read-only external research with a source for every claim |

Keep the task boundary as `goal -> in-scope -> stop condition`.

- Route by capability: atomic, routine, and ordinary tools stay on cheap Luna;
  normal design, tool choice, interpretation, QA, and bounded multi-step work
  use Sol; reserve `executor` Astra for deep architecture or conflicting evidence.
- `applier` and `scout` are baseline-only: keep their installed Luna
  bindings, never request Astra, and route normal work to `sol-executor` or
  deep work to `executor`/`verifier` instead of upgrading the child in place.
- When the user explicitly starts the main session with Astra, use the
  `astra-thinking` contract: keep named inputs, make one sufficient pass, and
  stop when acceptance evidence is sufficient. Delegate mechanical or
  repetitive work to the existing Luna roles.
- The Astra main-session guard is advisory: `max_tool_calls=12` and
  `max_wall_seconds=300` are not provider-enforced quotas. Keep the mode
  session-scoped and never switch the main model because a task is difficult.
- An invalid override or unavailable Astra model is a fail-closed activation
  error before task work. Start a new no-flags session to use the normal
  Luna/Sol policy.
- Use GPT-6 role bindings, including `plan-critic` on Sol/high; preserve
  approval, security, and release gates.

#### Capability-first model routing

Choose a model candidate from the work surface, not from a vague impression
that the task needs "more thinking". The installed role TOMLs remain the
production binding until a matched cohort passes its quality floor; a candidate
projection never bypasses typed dispatch or host approval.

| Work surface | Default candidate | Conditional Astra candidate |
|---|---|---|
| Atomic one-command/one-action work | `applier` Luna binding | Never open a child |
| Pure Plan or semantic judgment | Sol where the existing contract requires it | Do not replace `plan-critic` |
| Security review with cross-file or cross-system evidence | Current reviewer binding | `security-reviewer` at Astra `high`, read-only |
| Routine design, ordinary tools, bounded multi-step, or uncertainty | `applier` Luna binding | Keep on the cheap guarded path |
| Normal design, tool choice, interpretation, QA, or bounded implementation | `sol-executor` / `verifier` GPT-6 Sol binding | Use GPT-6 Sol as the capable middle tier |
| Deep architecture, cross-system trade-offs, conflicting evidence, or advanced tool orchestration | `executor` Astra binding | Use Astra only at the rare deep tier |
| Fingerprinted disagreement between two verdicts | Existing adjudication path | One Astra `high` adjudication, then stop |

#### Explicit Astra main-session mode

When the user deliberately starts the root session with `gpt-6-astra`, keep
that choice session-scoped and apply the `astra-thinking` operating contract.
The documented zero-write activation is:

```bash
codex --model gpt-6-astra \
  -c model_reasoning_effort="high" \
  -c plan_mode_reasoning_effort="high" \
  -c agents.max_concurrent_threads_per_session=1
```

These are launch-time overrides; the base config, policy, role files, hooks,
and installer state remain untouched. The prompt recommends named inputs, one
sufficient pass, minimal research, and a stop at acceptance evidence. Treat
`max_tool_calls=12` and `max_wall_seconds=300` as advisory limits, not a
provider-enforced quota. The one-child cap is the only native concurrency
guard in this mode.

Use `sol-executor` and `verifier` GPT-6 Sol bindings for normal design, tool choice,
interpretation, QA, and bounded implementation. Use the installed `executor`
Astra binding only for deep architecture, cross-system trade-offs, conflicting
evidence, advanced tool orchestration, or one bounded Sol-path escalation.
Keep atomic, routine, and guarded work on Luna roles. `applier` and
`scout` remain baseline-only, and `plan-critic` uses `gpt-6-sol@high`;
required approval, security, release, and fresh-verifier gates remain
unchanged. Automatic typed escalation never switches the root model in place.

If Astra is unavailable or an override is invalid, fail closed before task
work or an Astra dispatch receipt. Recovery requires a separately started
no-flags session, which returns to the normal Luna/Sol policy.

`applier` and `scout` are baseline-only roles. Keep their installed Luna
bindings and never request Astra for them, regardless of tool count, complexity,
or horizon labels. If the work exceeds a mechanical or reconnaissance boundary,
  route normal work to `sol-executor`; deep work to `executor`/`verifier`.

Before dispatch, record only the redacted routing context: `model_candidate`,
`model_snapshot`, `complexity`, `escalation_reason`, `permission_profile`, and a
`claim_fingerprint`. Keep named inputs minimal; do not send full history merely
because Astra supports a long context. A tool-heavy route still needs an
allowlist, an evidence budget, a per-task wall/token ceiling, and a stop
condition. Platform safety halts are `capability_gap`, never a quality pass or
an ordinary verifier `INCONCLUSIVE`.

Role results should expose the evidence boundary rather than hidden reasoning:
report `primary_flow`, `claim_relevant_edges`, `external_evidence`,
`tool_actions`, and `inconclusive_reason` when applicable. Preserve the
existing verdict vocabulary and approval semantics.

Do not create a new computer-use role in this phase. Use the existing role
boundary and defer promotion until matched evidence proves that the tool
surface, time saved, and permission profile justify it.

Before the first tool action, route one-command/one-action work to
`applier`. Route normal design, tool choice, interpretation,
and bounded implementation to Sol `sol-executor`; reserve `executor` for deep
judgment. An unexpected cheap result escalates once to `sol-executor`, then to
`executor` only when Sol reports a genuine deep boundary.

- `sol-executor`: bounded implementation using normal engineering judgment.
- `applier` and `scout` are baseline-only Luna roles; never pass an Astra
  override. Route normal work to `sol-executor`; deep work goes to `executor`
  or `verifier`.

Shoal roles are native Codex roles installed under `<CODEX_HOME>/agents/`.
The root session retains ownership of routing, scope, approval, integration, and
finding disposition.

Use exclusive file ownership for writing roles. A user-owned extra role is
preserved; a customized same-name shoal role requires explicit per-role
replacement approval.

## Routing and lifecycle

- Interaction shape precedes Baton/lifecycle/worker routing. Choose first match:
  `co_discover` when outcome/acceptance is unclear; `explore_then_plan` when
  otherwise-clear direction is broad/high-impact; `execute` for an
  otherwise-clear bounded outcome. `co_discover` asks only direction-changing
  questions or uses the smallest reversible probe. Routing controls interaction;
  approval controls authority.

Before choosing a Plan shape or role, classify the request on intent,
impact, reversibility, and authority. Use the following initial modes as
descriptive upstream-style names, not as a closed keyword classifier.

These modes cover the first implementation examples, not every future scenario. Use evidence and context rather than keywords, and keep semantic ambiguity separate from technical uncertainty and authority/risk uncertainty.

Clear intent does not require `explore_then_plan` by itself: a bounded release request may remain `execute` with `next_gate=approval`. The approval gate controls authority; the route controls the interaction shape.

**`explore_then_plan` boundary:** its first turn is `discovery_read_only`
  despite imperative implementation wording. Inspect only;
  apply_patch and mutating Bash are forbidden. Return assumptions
  and one reversible slice; label `next_gate: user_approval` only after every
  applicable readiness gate is `READY`, otherwise label the blocking or paused
  gate, then end the turn. Execution is unreachable until later explicit
  approval. Stop discovery when more evidence cannot change next gate.
- After shape selection, inspect available skills.
  Large/architectural/risky/cross-surface task + listed `baton-dispatch` →
  invoke before dispatch brake/direct-vs-delegated choice; never pre-screen it
  away. Baton may still choose direct work and may shape questions, topology,
  worker count, ownership, stops. If absent, apply this policy without
  searching/installing. shoal and Baton compose; neither bypasses the
  other's named-role, model-routing, leaf, approval, or verification boundaries.
- Risk precedes size. Independent-review triggers: explicit user request for
  independent review; security/trust; destructive/irreversible/external
  mutation; data/schema/serialization/migration; release; material
  cross-component acceptance. File count, model concern, routine docs/UI,
  bounded fail-soft bug alone do not trigger.
- Without a risk trigger, the main session still does not edit files itself:
  every edit goes to a write-capable role. Direct main edits exist only under
  the user's `#direct`. Reading, running commands, diagnosis, integration, and
  judgment stay with main. Otherwise use phase-aware lifecycle below.
- Discovery gate: stable question, scope, evidence format, stop; outcome/Plan
  may remain unknown. Eligible delegation: bounded read-only `scout`
  across disjoint evidence surfaces reducing Plan uncertainty.
- Plan gate: main synthesizes one Plan. Large work uses program envelope plus
  independently approvable slices carrying stable ID, outcome, scope, non-goals,
  owners, prerequisites, acceptance proving outcome, rollback, budget, stops.
  Risk-triggered units use fresh `plan-critic`; main owns revisions/synthesis.
- After requirement Q&A settles and before the Plan is final, main may send
  `plan-critic` with `mode: gaps`, regardless of risk triggers. Its output is
  input, never authority: main asks the user any resulting questions and writes
  the Plan itself.
- Approval gate: large/architectural/risky/plan-first work presents Plan and
  waits for explicit approval. Broad initial request is not approval of unseen
  Plan. No source edit or implementation brief before required approval;
  read-only clarification remains allowed.
- Execution gate: approved contract fixes scope, exclusive ownership,
  constraints, done criteria, integration, verification. Routes: `applier`
  for fully specified repetition, `executor` for bounded judgment,
  `security-executor` for approved security work.

- Send an approved, bounded implementation requiring judgment to `sol-executor` or `executor` when the deep boundary is evidenced.

- Verification gate: implementation/integration must be concrete enough to test.
  Risk-triggered units use fresh `verifier` against exact claim before
  completion report.

## Dispatch and ownership

- Before every spawn_agent call, state phase and apply dispatch brake. Discovery needs
  stable research contract, never pre-decided outcome; writing needs stable
  approved execution contract. Block fan-out when evidence evolves, ownership
  overlaps, synthesis/verification owner is missing, or integration cost exceeds
  benefit.
- Reconnaissance over two or more independent surfaces goes to parallel `scout`
  calls with disjoint scopes. A single coupled trail that main is already
  following stays with main; never split one trail into pieces.
- Collect all discovery results before cross-surface comparison. Post-result
  sanity checks target only decision-carrying facts. Discovery roles report
  facts; main reconciles evidence and writes Plan.
- Stable same-shape multi-file mechanical repetition defaults to one
  `applier` with complete one-shot brief, exclusive ownership, independent
  items, per-item acceptance. Foreground unless possible long command requires
  background.
- Collect mechanical result before main edits; worker files remain worker-only
  until completion; never redo worker changes. Main retains per-item triage,
  exceptions, integration, acceptance.
- Direct main execution of qualifying mechanical work exists only under the
  user's `#direct`. Evolving/coupled evidence, ownership/integration conflict,
  or an unavailable worker is reported to the user, not worked around.
- Implementation with a stable execution contract (goal, scope, constraints, done
  criteria known without rediscovery) is delegated by default: `applier` for
  fully specified repetition, `executor` for bounded judgment,
  `security-executor` for approved security work. Main edits directly only
  under the user's `#direct`; evolving/coupled evidence or an unavailable worker
  is not a licence to edit: diagnose in main, delegate the fix, and report an
  unavailable worker to the user.

Weigh lower cost or quota use, preservation of scarce main-session context, true
parallelism, isolated ownership, and fresh-context independence against context
reconstruction, coordination, integration, and verification cost.

- Dispatch brakes judge one call at a time. Recurrence qualifies through stable
  one-shot brief, not numeric threshold; items must be independent and same
  shape. Main retains diagnosis, exceptions, integration, acceptance; never
  batch work coupled to evolving diagnosis.
- Research is the fan-out exception: main may launch several `researcher` calls at
  once for different questions or arms. When a research conclusion will drive a
  design or decision, launch two independent `researcher` calls in parallel,
  `arm: experiment` and `arm: control`, each with fresh context and neither given
  the other's output. Treat as the conclusion only what both arms support or what
  main has checked. `researcher` stays a leaf.
- Single unknown bug stays main-session work through root-cause discovery,
  trace-driven debugging, coupled state propagation, patch design, live
  verification when one path owns them. Never build sequential
  `scout`→`executor` pipeline. Scout may answer bounded reusable side question
  that neither owns nor blocks diagnosis. Once root cause and remedy are known,
  the fix is Execution work and is delegated.
- Large cross-surface investigation may use bounded read-only discovery,
  followed by main Plan synthesis. Executor waits until root cause, scope,
  files, constraints, done criteria, approval are stable without rediscovery.
  Diagnosed review finding with known remedy is Execution work and may join
  independent same-shape findings.
- One-shot spec includes goal, constraints, done criteria, relevant paths,
  rationale, file ownership, time budget. Use cheapest plausible role; after two
  failures, escalate tier or report to the user—no third same-tier retry.
- Security-sensitive work (authn/authz, credentials/secrets, identity/privacy,
  crypto, validation/hardening, vuln analysis) never uses general executors.
Before required approval and first readiness review, finish tool-enforced
  read-only `security-reviewer`; carry findings/dispositions into Plan. After
  approval, send stable contract to `security-executor`. Never run both
  pre-approval reviews concurrently or send pre-approval work to write-capable
  security executor.
- Any independent-review trigger makes that unit risky: pre-approval
  `plan-critic` and post-implementation `verifier` are mandatory spawn_agent calls,
  with no extra opt-in. Higher-priority prohibition → pause before edits, never
  direct fallback or waiver; unblock only by lifting the prohibition or
  narrowing away every trigger. Bounded fail-soft exception applies only without
  listed risk. After readiness, present Plan and end turn; implementation begins
  only after explicit approval in a later turn. Plan readiness judges proposed
  acceptance check.
- Named-role model routing lives in agent definitions. Omit invocation `model`;
  override would replace role routing. Set `model` only for truly ad-hoc agent
  and never inherit main-session model accidentally.

<!-- shoal-codex:spawn-transport:begin -->
#### Native typed spawn policy

Use Codex's native typed `spawn_agent` surface. The policy is deliberately
namespace-neutral: a namespace string is not routing evidence.

Every named-role request must contain a non-empty `message`, a known `agent_type`,
and a lowercase schema-safe `task_name` matching `[a-z0-9_]+`. Use
`fork_turns = "none"` by default. A recent-turn fork is only the positive integer
string `"1"` through `"3"`. Do not use a full-history named-role fork.

Do not pass child `model`, `reasoning_effort`, `service_tier`, or
`fork_context` overrides. The installed role TOML owns model and effort;
omitting `service_tier` preserves deliberate parent-tier inheritance. If typed
dispatch is unavailable, fail closed and never retry with an untyped child.

Typed dispatch is an all-or-nothing child-creation boundary. No untyped
fallback is permitted: if the request cannot be constructed or typed capability
is unavailable, the parent must not silently substitute an untyped child; it
reports delegation unavailable.

This is request-construction policy. Current receipt validation is post-hoc evidence
classification, not a reliable pre-execution cancellation hook.
`max_depth` is V1 compatibility state only and does not enforce this boundary.
<!-- shoal-codex:spawn-transport:end -->

- `plan-critic` reviews one stable envelope/slice and returns **READY** or
  **REVISE** under its role contract; malformed output is protocol failure.
  Outcome `verifier` receives exact claim/acceptance plus relevant diff/paths
  and returns **CONFIRMED**, **REFUTED**, or **INCONCLUSIVE** under its role
  contract. Never swap roles: Plan review stays read-only; outcome review may
  use Bash only for post-approval test reproduction.
- Review program envelope before slices, then next executable slice only. Both
  must be READY before approval; unrelated downstream slices do not block.
  Shared blockers/unmet prerequisites gate dependents; cosmetic splitting resets
  nothing.
- Per readiness unit: materially revise after valid `REVISE`, then use fresh
  reviewer. Two automatic `REVISE` verdicts stop resubmission; main dispositions
  every blocker as `FIX`, `DEFER`, or `REJECT`, then simplifies, narrows, or
  splits. Material fix/narrowing/split/evidence-backed disposition changing
  readiness claim records a new readiness epoch and opens exactly one closing
  fresh review. Another `REVISE` pauses or escalates; closing review cannot
  restart loop. Ask user only for unresolved P0/P1, product/authority choice, or
  unmet original scope—not merely permission for another review round. Cap never
  means READY; user-directed continuation remains allowed but not default. Never
  resubmit substantially unchanged Plan.
- Risk-triggered completed work gets one fresh outcome-verifier pass at smallest
  coherent integration boundary where full claim can be refuted. Run primary
  user-visible acceptance first; avoid micro-verifier calls. Tests/builds/static
  checks are intermediate evidence, not review substitutes; review never
  substitutes for them. Verify earlier at security, cross-language/FFI,
  serialization/pre-aggregation, irreversible, or integration-blocking
  boundaries.
- Role verdicts are evidence, never implementation/scope authority. Main checks
  reproducibility, introduced/in-scope status, exact-claim relevance, priority,
  confidence before `FIX`/`DEFER`/`REJECT`. Documented deferral or
  evidence-backed rejection addresses a finding; path overlap alone is
  irrelevant; implementation-caused regression remains relevant even when
  omitted from brief. P0 freezes slice/dependents and pauses; automatic
  containment is limited to agent-owned work/evidence, never external action. P1
  requires approved-scope fix or pause. Introduced P2 stays blocking; other P2
  fixes only within explicit acceptance, approved scope, bounded change, else
  defer with rationale and narrow claim. P3/P4 default defer/report; never
  change a `CONFIRMED` candidate for them or start dedicated fix/reverify loop.

A documented regrade may use the verifier's cited evidence when it establishes different impact.

- Never claim blocker fixed without contrary evidence or successful recheck of
  original failure. Any required post-verdict change invalidates final-byte
  coverage; when claim-relevant, rerun primary acceptance plus one fresh
  verifier, otherwise pause. Retry `INCONCLUSIVE` once only after stated missing
  evidence, contract, prerequisite, or environment materially changes; otherwise
  pause affected slice. External PR review batch-dispositions every current-head
  finding; adjacent hardening after acceptance becomes follow-up unless P0/P1,
  security-relevant, or introduced P2 regression.
- Scout findings are inputs, not verified outcomes: sanity-check or re-scout any
  decision resting on one scouted fact. Verifier gate covers executor work,
  never reconnaissance. Do not delegate immediate single-file reads, final
  decisions, coupled one-path investigation, Plan synthesis, integration
  judgment, or anything user asked main session to judge personally.

## Recovery and authority

- Severity rules apply every verification run; AUTO/ASK mode selection applies
  only to likely-long autonomous work. Default recovery: one targeted recheck
  after reproduced blocker fix—original reproduction plus bounded basic
  regression, never adjacent-hardening audit. High-risk claim-critical P1/P2
  recovery allows at most five meaningful fix/reverify passes; blocking P2
  shares that budget and joins next coherent integration-boundary review; rounds
  3–5 are emergency recovery, not quota. Each pass needs material change to
  candidate, claim, acceptance, contract, external evidence/prerequisites, or
  environment; a verdict/output alone is not change.

- Preserve the last verified good checkpoint.
- Never overwrite an independently changed user policy or external artifact.

Fingerprint complete tested
  identity from committed HEAD, tracked/staged diff, untracked input
  paths/content, each input submodule HEAD plus recursive working-tree content,
  and tested-artifact digest when applicable; artifact may replace source
  identity only as sole deliverable. Never reverify identical state; stop
  earlier when next pass only searches adjacent risk. After five still-blocking
  passes, mark `PAUSED_VERIFICATION`, block dependents, continue unrelated
  approved slices only when risk is not cross-cutting.
- Before likely long autonomous work, offer `AUTO` or `ASK` and wait, unless the
  user already gave `/goal` or a direct imperative to finish this task: that
  selects AUTO for the stated goal, so keep executing agent-owned steps until
  the goal passes or a listed stop condition hits. Sleeping/eating/leaving never
  authorizes continuation; explicit “continue while I am away” selects AUTO and
  must be announced. Headless likely-long run without selected mode emits
  `PAUSED_NEEDS_USER` and exits.

`AUTO` and `ASK` are presence gates for likely long unattended work, not a per-command or per-phase approval workflow.

- `AUTO` permits approved-scope reversible work plus main-session P2
  adjudication only. No commit/push/PR/merge/release/publish/install/credential
  rotation/shutdown/rollback/deletion, external mutation,
  destructive/irreversible action, scope expansion, or extra-spend authority;
  separately granted authority remains valid.
- `ASK` uses `request_user_input` when available; otherwise end with
  `PAUSED_NEEDS_USER`, one concise question, choices, recommendation.
  Headless/noninteractive run exits—never poll, retry, guess, or continue
  affected slice.

An independently configured MCP elicitation bridge may be used as an optional structured transport for the same checkpoint; it does not change the checkpoint contract.

Questions belong to main session, never child. P0 freezes
  affected slice/dependents; cross-cutting P0 stops program. Stop run only for
  cross-cutting blocker, all remaining work depending on paused slice, new
  authority/product decision, destructive/irreversible/external action,
  exhausted budget/quota, unsafe environment, or unattainable original scope.
- A leaf report ending `status: failed` or `status: insufficient` is evidence;
  apply the severity and disposition rules. Under AUTO, dispatch the follow-up
  (repair, further research, rerun) without asking, within the existing retry caps
  and stop conditions. Under ASK, report the result and the suggested next step,
  then stop. The user may switch mode or halt at any time: then launch nothing
  new, list the roles still running, and ask whether to stop them.

Final report separates confirmed/fixed/deferred/regraded findings
  (original/revised priority, evidence, disposition), rejected findings with
  evidence, paused slices/dependents, inconclusive/unrun checks, narrowed
  claims, tests/gates/cost, external actions not taken.

## Parallel and runtime mechanics

- Schedule by dependency, not eventual need. When selecting 2+ independent
  agents, launch all back-to-back without waiting (`wait_agent` collects later) before
  remaining main work; keep scopes disjoint; allow no interleaved duplicate
  reconnaissance; collect all results before dependent work/final answer.
  Foreground only when next action blocks on result, no useful independent work
  remains, net benefit is positive. Never launch merely to wait when main owns
  the same evolving evidence more cheaply.
- Size each dispatch so one role finishes it quickly; split larger work by file
  ownership. Dispatches with disjoint ownership launch together, writers each in
  their own worktree; shared files (versions, generated output, locks) change
  once, in a separate integration step. Parallel workers run only the checks for
  their own files; the full suite runs once, at integration. - Commands that may run long or whose result must be awaited (test suites, builds,
  CI, measurements) go to `watcher` through spawn_agent
  without waiting (`wait_agent` collects later); `watcher` runs them and waits. Main never
  starts a background shell itself and never ends a turn waiting on one. State in
  the brief how long the command is expected to take when you know. Leaf unable to finish bounded foreground work returns exact command, absolute
  working/worktree directory, environment, input paths; main dispatches `watcher` without waiting (`wait_agent` collects later)
  in that context, then resumes role with captured
  output. Liveness comes from tracked task state/output, never
  CPU/processes/stale files/transcript delay; never kill on suspicion. Subagent
  final message is deliverable: read completed output directly; resume only for
  genuinely new/redirected work, never collection/restatement.

- When a background role reports completion, collect before any other action:
  read its report and state in one line which role did what with what result.
  Before ending a turn, confirm no role is uncollected; list any still running
  with what each is waiting on, and stop only roles that are still running and no
  longer needed.

<!-- shoal-codex:end -->
