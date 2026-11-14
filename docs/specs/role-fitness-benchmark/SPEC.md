---
id: spec-role-fitness-benchmark
title: Role Fitness Benchmark
status: proposed
created: 2026-08-04
updated: 2026-08-06
author: Miyago
approved_by: Miyago (execution approval, all benchmark actions, 2026-08-05)
tags: [benchmark, routing, evaluation]
priority: high
---

> 實作已搬到私有 repo `miyago9267/shoal-bench`（text-first P4，2026-10-23）；
> 本 spec 保留決策紀錄。

## Requirements

- Measure why Sol/high is reserved for risk-triggered Plan review while
  Luna/low-medium remains the mechanical default.
- Measure role-relevant capability, not generic model intelligence. The
  existing exact artifact contract remains a transport and usage metric only.
- Publish separate planning-quality, mechanical-reliability, usage, and time
  values; no aggregate score may hide a failed quality gate.
- Keep Miyago's priority order: usage first, time second, quality sufficient
  for the role. Sol must demonstrate a material planning benefit before its
  added usage or latency is accepted.
- Reuse only the existing native receipt and rollout-ledger semantics. The new
  runner must replace the current broad environment, auth-copy, raw-session,
  and report-publication paths with the security gates below.

## Architecture / Plan

### Decisions

- **Decision:** Create a new `role-fitness-v1` cohort rather than extend the
  existing `usage-routing-v1` acceptance metric.
  - **Reason:** The current fixture accepts only byte-equivalent artifacts;
    it does not contain a plan, risk ledger, ownership decision, or downstream
    execution result to score.
  - **By:** Miyago (2026-08-04)

- **Decision:** Compare the installed roles in their actual jobs.
  - **Reason:** Planning cases compare Luna/xhigh and Sol/high through the
    `plan-verifier` contract. Mechanical cases compare Luna/medium and
    Sol/high through `mech-executor`. Terra is out of scope because it has no
    active binding.
  - **By:** Miyago (2026-08-04)

- **Decision:** The benchmark has three matched cohorts, capped at 60 scenario
  arms and 108 paid Codex process calls.
  - **Reason:** It yields role-specific evidence without treating a cheap
    routing decision as an open-ended model study.
  - **By:** Miyago (2026-08-04)

- **Decision:** No live role-fitness run may use the current benchmark auth and
  session-retention flow unchanged.
  - **Reason:** Security review found broad host-environment inheritance,
    readable auth placement, unbounded raw-session retention, and no enforced
    public-report projection.
  - **By:** Miyago (2026-08-04)

- **Decision:** Keep the installed role architecture and Luna-first routing as
  the working default while further experiments continue.
  - **Evidence:** A live smoke cohort completed 10 distinct daily-development
    scenarios and exercised all seven installed roles. The observed bindings
    were `scout=Luna/low`, `mech-executor=Luna/medium`,
    `executor=Luna/max`, `verifier=Luna/xhigh`, and the three security or
    planning roles on `Sol/high`.
  - **Evidence:** A sequential `plan-verifier -> mech-executor` handoff
    completed with two typed children, no untyped fallback, and no third child.
  - **Decision:** Luna remains the practical default for reconnaissance and
    mechanical work. Sol remains restricted to risk-triggered planning and
    security boundaries; its live quality benefit is not yet proven to justify
    its additional usage and latency.
  - **Caveat:** The installed CLI reports `multi_agent_v2` disabled by default;
    the verifier now treats `--enable multi_agent_v2` as part of its fixed
    native command contract rather than an ad-hoc benchmark override. Two
    content-bearing high-effort trials exceeded the bounded wait and were
    inconclusive.
  - **By:** Miyago (2026-08-05)

- **Routing improvement:** Apply a bounded selective Sol trigger: any
  security category or at least two independent material-risk categories may
  require `plan-verifier` on Sol/high; a single non-security category stays on
  the Luna-first path. This reduces unproven high-reasoning switches while
  preserving the security boundary. The formal paired cohort remains required
  before claiming a cost-performance score above `5/10`.

- **Decision:** Use `Luna verifier -> host disagreement gate -> one Sol
  adjudicator` as the next switching protocol.
  - **Reason:** A Luna verifier is an economical standard for ordinary
    acceptance checks, but it must not be the sole judge of semantic conflicts
    involving Sol. The adjudicator receives an anonymous, fingerprinted
    disagreement and may not repair missing evidence or trigger a second vote.
  - **Boundary:** Deterministic probes and the frozen hidden-ledger scorer
    remain authoritative. Adjudication may improve a claim only when the final
    adjudicated output enters the unchanged source-rubric scorer.
  - **By:** Miyago (2026-08-06)

- **Evidence update:** Regrade the completed 12-case adjudicator cohort with
  the existing risk-coverage premium exception. The full 12-case protocol cost
  remains in the denominator; only the risk-coverage numerator excludes the
  four clean controls as already required by the scoring contract.
  - **Result:** Risk coverage improved from `50.00%` to `68.75%` (`+18.75`
    points), quality delta was `+10.00` with a positive paired CI, and the
    deterministic score is `8/10`.
  - **Boundary:** This regrades the direct-model switching diagnostic. The
    native typed child-role claim remains separate and unpromoted.
  - **By:** Miyago (2026-08-06)

- **Decision:** Treat Miyago's explicit approval as the benchmark execution
  approval; do not use a global `UserPromptSubmit` context injection as an
  authorization mechanism.
  - **Reason:** Codex permission policy and the benchmark's quota/evidence gate
    are separate layers. The active Codex config already has
    `approval_policy = "never"`, trusted workspace scope, and native agents
    enabled. Hook `additionalContext` can inform the model but cannot grant
    runtime permission or prove a paid run was authorized.
  - **Evidence:** Miyago approved all benchmark actions on 2026-08-05.
  - **By:** Miyago (2026-08-05)

- **Decision:** Do not hard-pin Codex to `0.146.0` or any later release.
  Version output is parsed and recorded only; native compatibility is proven
  by the observed schema, typed spawn, role binding, receipt, and rollout
  evidence. A compatibility failure is diagnostic input for the user's AI
  agent, not a release-lock reason to prevent all newer versions.
  - **By:** Miyago (2026-08-05)

- **Decision:** Do not hard-pin a Codex release in the installer, verifier, or
  benchmark runner. Parse and record the observed version, then let native
  schema, typed-child evidence, receipt validation, and role binding determine
  whether that runtime is usable. A malformed version is a diagnostic
  failure; a valid newer or older version is allowed to run and report its
  actual contract failure for the user's AI agent to resolve.
  - **By:** Miyago (2026-08-05)

- **Evidence:** A bounded live smoke using the available Codex
  a staged home reached post-spawn inspection but returned
  `SKIPPED / native_spawn_evidence_missing`. Direct trace inspection found one
  parent session, zero `spawn_agent` calls, and zero `sub_agent_activity`
  events. The active app binary is `0.147.0-alpha.1.2`; it is accepted for
  probing because version numbers are diagnostic rather than a hard gate.
  - **Disposition:** Do not count this as availability success: the missing
    spawn evidence is a native-surface/runtime issue, not a version result.
  - **Follow-up evidence:** The active runtime emits typed dispatch through
    `custom_tool_call(name="exec")` with
    `tools.multi_agent_v1__spawn_agent` / `wait_agent`, plus a
    `subagent_notification` child marker. The verifier now normalizes this
    schema while retaining fail-closed argument, wait, parent-child, model,
    and effort checks. Three subsequent probes included one strict
    `NATIVE_OK`, one incomplete spawn-without-wait failure, and one missing
    evidence skip; the resulting runtime diagnostic remains `1/5` and is not
    promoted to the three-repeat availability claim.
  - **Resolution evidence:** The fixed verifier command now activates
      `multi_agent_v2`; three fresh-home probes produced `NATIVE_OK` with one
      typed child and two session rollouts each. This is command-contract
      activation, not a release pin, and the formal 30-stage cohort remains
      open.

- **Evidence:** The bounded live dispatch repeat harness completed three
  all-role repeats (seven roles per repeat) plus nine additional scout stages:
  `30/30` admitted stages reached `NATIVE_OK`, with identical manifest and
  scorecard hashes and no failure-taxonomy entries. The Wilson 95% lower bound
  is `0.886482909`, proving the conservative 0.80 dispatch availability gate
  and supporting a confidence-adjusted `8/10` dispatch-layer score, but not
  the stricter 0.90 target. This remains dispatch evidence only; it does not
  prove content-bearing plan quality, mechanical correctness, or Sol switching
  value.
  - **By:** Codex execution under Miyago's 2026-08-05 approval

- **Evidence:** The existing usage-routing proxy remains a negative diagnostic
  for unconditional high-reasoning switching: Sol accepted `5/12` artifacts
  at `$2.931608` per 12 cases versus Luna's `12/12` at `$0.743874`. Because
  those are not matched risk-bearing P0/P1 cases, this evidence cannot prove a
  quality delta; high-reasoning cost-performance therefore remains fail-closed
  at `5/10`, with selective risk-triggered switching retained as the next
  experiment.

- **Directional evidence:** A single anonymous content-bearing migration probe
  produced valid `REVISE` JSON from both Luna/xhigh and Sol/high, with five
  findings each. Sol took `14.22s` versus Luna's `13.64s`; quality delta was
  zero, so this probe cannot lift switching above `5/10` and is not included in
  the formal paired cohort.

- **Directional evidence:** The first three-case content pilot (one clean
  control, two risk cases) produced valid reviews for both candidates. Luna and
  Sol each reached `0.5` risk coverage on the risk cases; Sol had zero clean
  false escalations versus Luna's one, but used `10.18%` more input tokens and
  `42.54%` more wall time. There was no positive incremental risk yield, so the
  cost-performance score remains `5/10` and the pilot is not promoted.

- **Method correction:** The content probe prompt previously called every
  fixture a “production Plan”, including the non-production clean control.
  The runner now says to respect the Plan's stated scope. All prior
  content-probe scores remain diagnostic and are superseded for clean-control
  false-escalation comparisons; a fresh matched run is required before any
  cost-performance promotion.

- **Scoring correction:** The content runner now uses the registered Planning
  Quality Score weights exactly (`0.50 coverage + 0.25 critical precision +
  0.25 actionable revision`). Content artifacts produced before this correction
  remain diagnostic and must not be mixed into a new paired aggregate.

- **Directional evidence:** The complete 12-case direct-model plan proxy
  produced valid JSON for all 24 candidate stages. Luna/xhigh averaged `53.19`
  quality points versus Sol/high `52.33`; risk coverage was `0.6875` versus
  `0.50`, clean false escalations `3` versus `4`, and Sol wall premium was
  `45.53%`. This is strong negative evidence against unconditional switching,
  but remains outside the formal claim because native child role stages,
  confidence intervals, mechanical execution, and split workflows are still
  pending.

- **Decision:** Freeze the first synthetic fixture bundle for bounded content
  probes. The private answer key is stored at the explicitly supplied
  user-owned path; the repository records only case hashes and HMAC
  commitments. This bundle is a benchmark input, not evidence of model
  quality until its live outputs pass the source-rubric scorer.
  - **Evidence:** `12` plan-review, `12` mechanical, and `6` split fixtures;
    exactly `4` plan clean controls; manifest hash
    `7ef0ac3299c5be0a016cf240cc428f95339d9adadedaad8e23d311deb309b3e2`.
  - **By:** Codex execution under Miyago's 2026-08-05 approval

| Cohort | Cases × arms | Scenario arms | Paid stages | Purpose |
| --- | ---: | ---: | --- | --- |
| Plan review | 12 × Luna/xhigh, Sol/high | 24 | reviewer | Planning Quality Score |
| Mechanical execution | 12 × Luna/medium, Sol/high | 24 | executor → verifier | Execution Reliability Score |
| Split workflow | 6 × Luna/xhigh, Sol/high review | 12 | reviewer → executor → verifier | Sol escalation value |

### Security findings and dispositions

The following security-review findings are accepted as implementation gates.
None is accepted as a live-run exception. Their acceptance checks must pass
before the execution-approval request.

| Finding | Disposition | Required before live execution |
| --- | --- | --- |
| Auth file and inherited host secrets can reach a workspace-write trial | Fix | minimal environment allowlist, auth isolation proof, and outbound boundary test |
| Private ledgers and raw session material lack retention controls | Fix | `0700` encrypted private root, TTL audit, crash cleanup, and deletion-error failure |
| Public benchmark artifact has no allowlist-only projection | Fix | separate raw/public schemas, unknown-field rejection, and secret/path scanner |
| Hidden ledger has no tamper-evident precommitment | Fix | salted commitment, timestamped freeze record, and mutation rejection |
| Split handoff and stage attribution are underspecified | Fix | fresh homes, identity-free handoff schema, per-stage receipts, and reconciliation |

### Scorecards

Each plan fixture contains a hidden, frozen risk ledger. It assigns P0/P1/P2
weights of `5 / 3 / 1`, source evidence, minimum revision, and acceptance
check. The ledger is not shown to the model. The scorer runs before candidate
identity is joined to the result. It only accepts a source-anchored rubric
match; an ambiguous match is `inconclusive`, never a pass.

| Score | Formula | What it answers |
| --- | --- | --- |
| Risk coverage | caught ledger weight / total ledger weight | Did the review find the important problems? |
| Critical precision | supported P0/P1 findings / all claimed P0/P1 findings | Does it cry wolf? |
| Actionable revision rate | true findings with evidence, minimum revision, and acceptance check / true findings | Can the review be acted on? |
| Planning Quality Score | `100 × (0.50 × coverage + 0.25 × precision + 0.25 × actionable revision)` | Is this reviewer better for high-risk Plans? |
| Verified first-pass rate | mechanical cases accepted by the independent verifier on first submission / cases | Does the worker finish the job? |
| Rework-free rate | accepted cases requiring no repair pass / cases | How often is a result immediately usable? |
| Execution Reliability Score | `100 × (0.70 × first-pass + 0.30 × rework-free)` | Is this worker dependable for mechanical work? |

Usage fields remain raw input/output/cache tokens, weighted tokens, equivalent
cost, median wall time, and p95 wall time. They are displayed beside quality;
they are not mixed into either quality score.

### Operational fitness scorecard

The benchmark also reports four operational scores on a 0–10 scale. These are
not model-intelligence claims; they measure whether the installed routing
architecture is usable in repeated operation. The score is computed from the
raw gates below and rounded only for display:

| Dimension | Baseline | Target | Measurement |
| --- | ---: | ---: | --- |
| Architecture | 8 | ≥ 8 | invariant and ownership checks passed / required checks |
| Stability | 7 | ≥ 8 | successful repeat runs with no drift, orphan, or unreconciled stage / eligible runs |
| Availability | 8 | ≥ 8 | admitted stages that reach a valid native receipt / admitted stages |
| High-reasoning cost-performance | 5 | ≥ 8 | quality-adjusted incremental value per switching premium, with latency and usage caps |

The displayed score is `floor(10 × gate_rate)`, capped at 10, with a score of
8 requiring a gate rate of at least 0.80. A dimension cannot be promoted by an
aggregate average: any failed hard gate keeps that dimension at its baseline
or lower.
Reports must include numerator, denominator, raw rate, score, and failed case
IDs so that score changes are auditable across runs.
The runner also reports a confidence-adjusted display score derived from the
Wilson lower bound; this is useful for deciding whether a raw 10/10 result has
enough samples to support an 8/10 operational claim.

Architecture checks are static and deterministic: role binding is resolved at
one seam, stage ownership is explicit, handoff validation is performed before
execution, receipt correlation is one-to-one, and public projection rejects
unknown or secret-like fields. Stability checks run the same frozen fixtures
at least three times with fresh homes and compare fixture, prompt, scorecard,
binding, and schema hashes. Availability excludes intentionally rejected
admissions from the denominator, but counts timeout, auth, receipt, cleanup,
and metric-correlation failures once an admission was accepted. Stability is a
deterministic repeat gate rather than a probabilistic rate: it requires three
fresh-home repeats, matching hashes, no drift, orphan, cleanup, or
unreconciled stage, and zero inconclusive repeats.

### Repeated-run protocol

One benchmark result is a single run, not proof of availability. The minimum
evidence set is three independent runs (`R1`–`R3`) over the same frozen
manifest, with fresh private roots and fresh stage homes. The fixed native
command contract may activate `multi_agent_v2`; ad-hoc model, tool, or
service-tier overrides remain ineligible. A run is eligible only after startup
preflight, security sentinel,
fixture commitment, and resource admission all pass. Each run writes a
sanitized aggregate containing its run ID, manifest hash, scorecard hash,
stage counts, failure taxonomy, and metric values; raw sessions remain private
and are not evidence artifacts.

After each eligible run, update the aggregate instead of overwriting the prior
result. Availability and stability are reported both per run and pooled across
runs. The pooled availability gate requires at least 30 admitted stages and a
Wilson 95% lower bound of `≥ 0.80` for score 8; the target operational claim
requires the stricter lower bound of `≥ 0.90`. If fewer than 30 stages are
available, the result is directional only and cannot claim proven availability.
Stability is proven when all three eligible repeats pass the deterministic
repeat gate above; it does not apply a Wilson bound to the three-run integrity
denominator. Any inconclusive stage remains in the availability denominator
and is listed by failure class; an inconclusive repeat prevents stability
promotion.

### High-reasoning switching cost-performance

The current 5/10 score is treated as a routing problem, not a reason to remove
high reasoning from risk work. Every matched split case records a baseline
`Luna/xhigh` path and a switched `Sol/high` path, including the review quality
delta, weighted-token delta, equivalent-cost delta, p95 wall-time delta, and
switch overhead (dispatch, fresh-home, handoff, and verifier time). The primary
metric is:

```text
switch value = additional supported P0/P1 findings
               / (extra weighted tokens / 100,000)
```

The cost-performance score is 8 only when all of these gates pass across the
matched cohort: switch value is positive with a paired bootstrap 95% interval
excluding zero; the switched path adds no more than 25% p95 wall time or 20%
weighted tokens unless its risk coverage improves by at least 10 points; and
the switched path has no additional false escalation or inconclusive result.
A score of 9 additionally requires the median switch premium to be ≤10% on
both weighted tokens and wall time. If the quality delta is zero or the
confidence interval crosses zero, the score is capped at 5 regardless of
absolute quality. This prevents an expensive high-reasoning path from looking
efficient merely because it is individually capable.

The preferred improvement path is: keep Luna/medium as the default, perform a
cheap local risk gate, switch only when the risk trigger is positive, reuse a
credential-free handoff, and avoid a second high-reasoning verifier when the
first receipt and acceptance evidence are already sufficient. The benchmark
must compare this selective path with an always-Sol control so that fewer
switches are credited only when quality and availability remain intact.
If a switched path is quality-positive and uses fewer weighted tokens than its
matched baseline, the scorer records a cost saving instead of rejecting the
cohort as invalid; the same quality, confidence, availability, and premium
gates still apply.

### Scoring edge cases and aggregation

- The plan-review decision cohort must include at least four P0/P1 ledger
  entries and exactly four matched clean-control cases. It otherwise fails
  before a live run.
- Risk coverage and actionable revision aggregate micro-style across all
  ledger weights. Clean controls contribute no coverage denominator.
- Critical precision aggregates all claimed P0/P1 findings. A zero denominator
  is `1.0` only when the corresponding ledger contains no P0/P1 entry;
  otherwise it is `0.0`.
- Missing output, invalid structured verdict, missing source evidence, failed
  receipt, or unresolved scorer match yields `inconclusive`. Inconclusive
  outputs receive no quality credit and block automatic routing claims.
- Paired model deltas use case-level scores and a fixed-seed 10,000-resample
  percentile bootstrap. Risk-coverage inference resamples only the matched
  risk-bearing cases; every resample recomputes the micro weighted ratio.
  Clean controls are excluded from this denominator and reported separately as
  false escalations. Reports include the delta and 95% interval; no result is
  rounded before the gate is evaluated.
- A clean-control false escalation is any `REVISE`, invalid verdict, or
  inconclusive score on a fixture with an empty ledger. The fixed-seed paired
  bootstrap resamples all four clean controls and reports
  `false_escalation(Sol) - false_escalation(Luna)`. Invalid or inconclusive
  controls count as false escalations and cannot improve either candidate.

### Routing decision rule

Sol remains an automatic risk-triggered Plan-review tier only when all gates
pass against Luna/xhigh on the matched plan-review cohort:

1. Risk coverage improves by at least 10 points and the paired bootstrap 95%
   interval excludes zero.
2. Critical precision is not more than 10 points lower than Luna.
3. The split workflow's verifier-confirmed completion rate is no lower than
   Luna-review → Luna-executor by more than one of six matched cases.
4. Sol's clean-control false-escalation rate is at most 25% and no higher than
   Luna's; any additional Sol-only false escalation fails the automatic route.
5. The added Sol cost and p95 time are published as a premium, not hidden.

Luna remains the mechanical default only if its verified first-pass rate is at
least 90% and is not more than one of 12 matched cases below Sol. Once that
quality gate passes, lower weighted-token usage decides first and lower p95
wall time breaks a usage tie within 5%.

The README also reports the human-readable marginal result:

```text
critical-risk yield = additional supported P0/P1 findings per 100k extra weighted tokens
```

The 1.6.0 scorecard also reports the author's primary efficiency metric:

```text
quality-adjusted cost efficiency = quality points / equivalent cost
```

This metric is eligible only when the candidate meets the matched baseline
quality floor and the paired quality confidence lower bound is non-negative.
If the quality floor fails, its candidate efficiency is reported as zero; a
cheaper but lower-quality route cannot win by cost alone. Equivalent cost is
preferred when receipt-backed pricing is available, otherwise the report uses
the weighted-token proxy and labels that basis explicitly. This descriptive
metric never bypasses the existing score-8/9 promotion gates.

If any quality result is inconclusive, the automatic route fails closed. Sol
may still be manually requested, but the benchmark cannot claim it is justified
as a default escalation.

### Data and scoring boundary

- Plan-review fixtures are realistic Plan documents with predeclared source
  context, risks, dependencies, acceptance evidence, and stop conditions.
- Mechanical fixtures are isolated worktrees with allowed paths and an
  acceptance script. They must test a useful change, not exact prose.
- The split cohort sends the reviewed Plan to the same Luna/medium executor;
  only the reviewer model differs.
- Every split fixture provides an original Plan plus pre-frozen, ledger-bound
  revision fragments. The runner applies fragments mechanically; no reviewer
  or executor authors a Plan revision.
- A valid `READY` hands off the original Plan only for a clean-control fixture.
  A valid `REVISE` creates an execution-approved Plan by applying exactly the
  matched revision fragments in stable order. Executor admission after
  `REVISE` requires one or more unambiguous supported ledger matches, nonempty
  `revision_ids`, a derived Plan hash distinct from the original, and a passed
  Plan validator. Any unsupported or ambiguous finding, including P2, makes a
  mixed `REVISE` terminal. A risky fixture with `READY`, an invalid or
  inconclusive verdict, or a failed Plan validation is terminal and never
  starts execution.
- The execution-approved handoff has exactly `scenario_id`, `fixture_hash`,
  `original_plan_hash`, `approved_plan_hash`, `ledger_commitment`,
  `revision_ids`, and `review_score_hash`. The runner owns creation; the
  validator owns schema and hash checks before executor admission.
- Fixture hashes, model binding, prompts, receipt correlation, usage ledgers,
  and scorecard versions are retained in the sanitized report.
- The private risk ledger and raw trial material live in a Miyago-owned,
  explicit, mode-`0700`, non-symlink root on an encrypted local volume. The
  runner never creates a default persistent location. Miyago retains the ledger
  and audit index through result approval; their hashes, not contents, enter
  the sanitized report.
- Raw stdout and session JSONL exist only in a per-stage private directory long
  enough to derive native metrics. The runner must then remove them, check every
  deletion result, and turn cleanup failure into a failed scenario.
- The private root has a 30-day TTL. Startup runs a permission and expiry audit;
  stale material is reported and blocks a run until Miyago explicitly resolves
  it. The benchmark never silently ignores a cleanup failure.
- Before a dry run, the scorer writes a timestamped commitment for each fixture:
  `HMAC-SHA256(salt, fixture_hash || ledger_bytes || rubric_bytes)`. The private
  salt, ledger, and rubric are immutable for the run; any later mismatch
  invalidates all affected scores.
- The public report is an allowlist-only `role-fitness-public-v1` projection.
  It may contain cohort aggregates, rubric and commitment hashes, metric
  versions, and limits. It rejects free text, prompts, fixture contents,
  source snippets, absolute paths, identities, unknown fields, and secret-like
  values before writing under `docs/benchmarks`.

### Ownership and freeze points

| Surface | Exclusive owner | Freeze point |
| --- | --- | --- |
| Fixture and hidden ledger | Miyago | signed manifest before any dry run |
| Runner, validator, and receipt accounting | main-session implementer | offline suite before execution approval |
| Deterministic source-rubric scorer | main-session implementer | scorecard hash before any live call |
| Ambiguous score disposition | Miyago | before aggregate approval; unresolved is inconclusive |
| Sanitized aggregate and README publication | Miyago | after reviewed report approval |

No model sees a ledger or candidate identity. The scorer receives an anonymous
output packet and source-rubric IDs only. A local audit index maps anonymized
packet hashes to candidate bindings and remains in Miyago's private root.

The runner uses a minimal environment allowlist and rejects inherited cloud,
SSH, API-key, token, password, proxy, and credential-path variables. Runtime
authentication and inference traffic may originate only from the parent Codex
client, via TLS on port 443 to an operator-pinned official Codex endpoint
allowlist. Model-accessible tool subprocesses have no outbound egress and no
read path to `auth.json` or the private root. A sentinel fixture before any
paid call proves that auth, sentinel environment values, and private-root files
are unreadable from tools and absent from stdout, session material, reports,
and permitted parent requests. If the native runtime cannot enforce either the
parent allowlist or zero tool egress, the live benchmark is blocked.

### Stage accounting, budgets, and stops

Each stage executes as one fresh parent plus exactly one named child in an
isolated home. A scenario arm receives a stable ID; every stage receipt and
native parent/child ledger binds to that ID. The scenario's usage and wall time
are the deduplicated sum of all of its stages. Credential-free, hash-bound
handoff artifacts are the only data copied between stages. The handoff has an
allowlisted, identity-free schema, rejects model names and extra fields, and is
validated and hashed before the next fresh stage starts. Each stage reports its
usage separately; the scenario report reconciles the exact parent and child
rollout IDs before summing them.

The split-workflow branch is deterministic: `READY` on a clean control starts
the executor with the original Plan; a valid `REVISE` starts it only with the
validated derived Plan; every other verdict terminates before execution. The
fresh outcome verifier runs only after an executor stage and records whether
the approved Plan produced a verified completion. Offline tests cover every
branch and prove no executor starts from an unapproved handoff.

| Fixture | Review result | Transition |
| --- | --- | --- |
| Clean control | exact `READY` | execute original Plan |
| Clean control | `REVISE`, invalid, or inconclusive | terminal false escalation |
| Risk-bearing | supported-only `REVISE` with nonempty fragment set | validate and execute derived Plan |
| Risk-bearing | `READY`, zero-match, unsupported, ambiguous, or mixed `REVISE` | terminal; no executor |

| Cohort | Scenario arms | Stages per arm | Maximum paid processes |
| --- | ---: | ---: | ---: |
| Plan review | 24 | 1 | 24 |
| Mechanical execution | 24 | 2 | 48 |
| Split workflow | 12 | 3 | 36 |
| Total | 60 | — | 108 |

The hard live limits are 60 scenario arms, 108 paid processes, and six hours of
cumulative wall time. Admission closes at five hours and 50 minutes, leaving a
single 10-minute stage timeout as the only permitted time overshoot. There are
no automatic retries. Equivalent cost `$30` and `8,000,000` weighted tokens are
settled stop points, not claimed hard maxima: the Codex CLI does not currently
expose a proven per-call token or cost kill switch. Before a paid run, the
implementation must either prove a per-stage upstream limit and reserve it at
admission, or keep the benchmark dry-run only. A failed binding receipt,
fixture or ledger hash mismatch, private-root violation, session redaction
failure, metric correlation failure, or invalid handoff aborts the cohort
immediately. Any additional replicate is a new, separately approved run with
its own cap.

### Reporting and chart contract

The README replaces the ambiguous contract pass-rate headline with two panels:

1. **Planning quality:** risk coverage, critical precision, actionable revision
   rate, Planning Quality Score, Sol premium, and critical-risk yield.
2. **Mechanical delivery:** verified first-pass rate, rework-free rate,
   Execution Reliability Score, weighted tokens, equivalent cost, and p95
   wall time.

The chart calls the values `planning quality` and `execution reliability`, not
`intelligence`. It labels every cohort size and states that its result is
specific to this repository's versioned fixtures.

## Tasks

- [x] Freeze 12 plan-review, 12 mechanical, and 6 split-workflow fixtures;
      write their hidden risk ledgers, source-rubric IDs, and acceptance scripts
      before any run. The first bundle is synthetic and HMAC-committed in the
      user-owned private fixture root.
- [x] Implement an isolated `benchmark_role_fitness.py` runner that reuses the
      native-ledger semantics without changing `usage-routing-v1`. It must use
      the new auth, environment, retention, publication, commitment, and
      handoff gates.
- [x] Implement the offline preflight shell for `benchmark_role_fitness.py`:
      validate all seven role bindings, derive a manifest hash, exercise the
      scorecard path, and guarantee zero live calls in dry-run mode.
- [x] Add validators and offline tests for fixture hashes, ledger schema,
      anonymous scoring, model bindings, report redaction, stage accounting,
      review-to-execution branches, resource admission, security sentinel
      behavior, cleanup recovery, bootstrap edge cases, and all decision gates.
- [x] Run an offline dry run that proves every role binding and scorecard path;
      three independent dry-runs produced the same manifest hash and zero live
      calls.
- [x] Repeat the offline preflight three times with ten stages per repeat and
      publish the sanitized `30 / 30` preflight availability evidence.
- [x] Add an offline operational scorecard evaluator covering the four
      dimensions, Wilson lower bounds, failure denominators, and score caps.
- [x] Add a repeated-run aggregate that appends `R1`–`R3` evidence by manifest
      and scorecard hash without replacing prior runs.
- [x] Add a receipt-driven live-evidence adapter that validates stage boundaries,
      keeps admitted failures in the denominator, and emits a sanitized summary.
- [x] Add an explicitly gated fresh-home repeat harness with checkpointed
      per-repeat aggregates and no raw-session publication.
- [x] Accept both legacy native rollout events and the current
      `custom_tool_call` / `subagent_notification` transport without weakening
      typed argument or child-binding validation.
- [x] Add an explicitly opted-in bounded live dispatch repeat harness with a
      fresh staged home per stage, sanitized receipt retention, and pooled
      Wilson-gated availability output.
- [x] Add deterministic matched switch-cost accounting with fail-closed
      quality, premium, false-escalation, and inconclusive caps.
- [x] Add matched switch-cost accounting for dispatch, handoff, usage, and
      p95 time; prove that inconclusive and false-escalation cases cannot
      improve cost-performance.
- [x] Run a first live role-dispatch smoke with at least 10 daily-development
      scenarios, including a sequential thinking-to-mechanical handoff.
- [x] Repeat the native dispatch smoke three times across all seven roles with
      fresh homes; retain incomplete and missing-evidence attempts in the
      denominator. The content-bearing role-fitness cohort remains separate.
- [x] Run a bounded anonymous direct-model content pilot and a 12-case plan
      proxy with strict JSON scoring, weighted-token accounting, and cleanup;
      keep both explicitly directional because they do not yet exercise the
      native child role contract.
- [ ] Run paired, content-bearing Luna/Sol cases with bounded stage timeouts
      to measure quality delta separately from dispatch and latency overhead.
- [x] Run one bounded live Luna/Sol content probe to validate the matched data
      path; keep it directional and separate from the formal cohort.
- [x] Run the bounded v2 routing matrix: Luna by default, Sol for security or
      compound material risk, with uncertainty represented as a separate
      policy variant.
- [x] Run a six-case live quality slice against the v2 routing matrix and retain
      the sanitized policy-projection artifact.
- [x] Run the remaining six risk-bearing cases and combine them into the
      twelve-case matched quality aggregate before any switching regrade.
- [x] Compare Sol/high against Luna/xhigh on matched risk-bearing plans before
      changing the automatic escalation rule.
- [x] Define the Luna-verifier disagreement contract and one-shot Sol
      adjudicator boundary without changing the frozen rubric or denominator.
- [x] Add an offline adjudicator policy Matrix covering Luna-only,
      risk-gated adjudication, and semantic-adjudication variants.
- [x] Run the bounded adjudicator Matrix with matched plan and split-workflow
      cases before changing the automatic escalation rule.
- [x] Prove the native typed Sol adjudicator seam on a bounded 2-case smoke;
      retain child binding, receipt, and source-rubric evidence.
- [x] Run the bounded 12-case live plan-review adjudicator cohort with the
      frozen rubric, complete disagreement receipts, and full protocol cost.
- [x] Obtain explicit execution approval from Miyago for all benchmark actions;
      run at most 60 scenario arms
      and 108 paid processes within the declared resource caps.
- [x] Review the sanitized aggregate, fail closed on an inconclusive score, and
      decide whether the Sol escalation remains automatic.
- [ ] Generate the two-panel README SVG and update benchmark documentation only
      after Miyago approves the reviewed aggregate.

### Operational acceptance gates

- [x] Architecture remains ≥8/10 after any runner or handoff change; the
      deterministic offline score is 5/5 = 10/10, with receipt correlation
      tested against a synthetic receipt (not counted as runtime availability).
- [x] Stability reaches ≥8/10 over three eligible repeats with no unreconciled
      stage or cleanup failure.
- [x] Availability reaches ≥8/10 and has at least 30 admitted-stage samples;
      the public claim uses the Wilson 95% lower bound.
- [ ] High-reasoning switching reaches ≥8/10 only with a positive,
      statistically supported risk yield and within the premium caps, or with
      the existing ≥10-point risk-coverage exception.
- [x] No score is promoted when a quality gate is inconclusive; the report
      records the dimension as `unproven` and schedules another bounded repeat.

## Files

- `docs/specs/role-fitness-benchmark/SPEC.md` - approved experiment contract.
- `install/role_fitness_scorecard.py` - deterministic offline operational
  scorecard and repeated-run aggregation.
- `tests/test_role_fitness_scorecard.py` - scorecard contract tests.
- `install/benchmark_role_fitness.py` - isolated dry-run and receipt-driven
  live-evidence harness; it never starts Codex implicitly.
- `install/run_role_fitness_live.py` - explicitly gated fresh-home repeat
  runner for sanitized native receipts, checkpointed repeats, and bounded
  aggregates.
- `install/run_role_fitness_content.py` - explicitly gated content probe with
  native usage metrics, matched-arm projection, resumable checkpointed rows,
  and an atomically written sanitized final report.
- `tests/test_benchmark_role_fitness.py` - offline contract and gate coverage.
- `tests/test_run_role_fitness_content.py` - content probe parsing and usage
  contract tests.
- `docs/benchmarks/role-fitness-v1/` - sanitized manifest, aggregate, and
  metric definitions.
- `docs/benchmarks/role-fitness-v1-preflight.json` - sanitized 3 × 10 offline
  preflight evidence plus the deterministic architecture invariant score;
  explicitly not a runtime availability claim.
- `docs/benchmarks/role-fitness-v1-runtime-diagnostic.json` - two sanitized
  baseline probes plus three fixed-activation live dispatch probes; it records
  the activation-path result but cannot promote runtime availability.
- `docs/benchmarks/role-fitness-v1-live-dispatch-smoke.json` - verified 3 × 1
  fixed-activation smoke evidence; explicitly directional until 30 stages.
- `docs/benchmarks/role-fitness-v1-live-dispatch-r1-r3.json` - verified 30
  admitted stages across three fresh-home repeats.
- `docs/benchmarks/role-fitness-v1-live-dispatch-r1-r4.json` - verified 40
  admitted stages across four fresh-home repeat slices; Wilson-gated dispatch
  availability reaches the stricter 0.90 lower-bound target.
- `docs/benchmarks/role-fitness-v1-runtime-repeat.json` - sanitized 30-stage,
  three-repeat all-role dispatch evidence with conservative Wilson scoring.
- `docs/benchmarks/role-fitness-v1-fixtures-manifest-v2.json` - public hashes
  and HMAC commitments for the frozen synthetic fixture bundle; no answer
  keys.
- `docs/benchmarks/role-fitness-v1-switch-diagnostic.json` - unmatched usage
  proxy diagnostic; it keeps high-reasoning switching at 5/10 until paired
  risk-bearing quality evidence exists.
- `docs/benchmarks/role-fitness-v1-content-probe.json` - one matched live
  content probe; it is directional only and records a fail-closed score of 5.
- `docs/benchmarks/role-fitness-v1-content-probe-r2.json` - two-case matched
  replicate; it remains directional and records a fail-closed score of 5.
- `docs/benchmarks/role-fitness-v1-content-probe-v2-clean.json` - post-prompt
  correction clean-control validation; both arms still false-escalated and it
  remains a negative control, not a promotion result.
- `docs/benchmarks/role-fitness-v1-content-probe-v3-risk.json` - post-scoring
  correction risk-case validation; Sol found no additional risk and remains
  fail-closed at 5/10.
- `docs/benchmarks/role-fitness-v1-content-pilot.json` - anonymous three-case
  content pilot; directional only and not a formal cohort claim.
- `docs/benchmarks/role-fitness-v1-content-plan-cohort.json` - anonymous
  12-case direct-model plan proxy; directional only, cost-performance remains
  fail-closed at 5/10.
- `docs/benchmarks/role-fitness-v1-native-content-probe.json` - one native
  `plan-verifier` child probe with verified Sol/high binding but an
  inconclusive machine-readable review output; not a quality pass.
- `docs/benchmarks/role-fitness-v1-native-content-plan-r1.json` - three
  repeatable native Sol/high plan-verifier cases with hidden-ledger scores;
  single-arm evidence only, not a paired switching claim.
- `docs/benchmarks/role-fitness-v1-native-content-paired-r1.json` - three
  Luna proxy versus native Sol/high matched cases; directional and explicitly
  fail-closed at `5/10`.
- `docs/benchmarks/role-fitness-v1-native-mechanical-r1.json` - three native
  Luna/medium `mech-executor` cases with exact acceptance artifacts; verifier
  and rework stages are still pending.
- `docs/benchmarks/role-fitness-v1-native-mechanical-verifier-r1.json` - one
  native verifier stage with verified binding but an inconclusive outcome;
  no rework-free credit is granted.
- `docs/benchmarks/role-fitness-v1-native-mechanical-verifier-r2.json` - three
  final verifier confirmations with one retry; bounded Execution Reliability
  is `7/10`, not yet proven at the full cohort gate.
- `docs/benchmarks/role-fitness-v1-native-split-r1.json` - split review
  binding evidence with an inconclusive verdict; executor admission correctly
  remained `false`.
- `docs/benchmarks/role-fitness-v1-fixtures-v4-summary.json` - corrected
  future-run fixture contract with both ledger-bound split fragments; prior v2
  evidence remains immutable and hash-scoped.
- `docs/benchmarks/role-fitness-v1-native-split-v2.json` - corrected split
  fixture with native review-to-handoff admission; executor artifact remained
  inconclusive, so no completion credit is claimed.
- `docs/benchmarks/role-fitness-v1-native-split-v3.json` - one complete native
  split scenario through review, handoff, executor, and verifier; bounded only.
- `docs/benchmarks/role-fitness-v1-fixtures-v5-summary.json` - hash-scoped v5
  split fixture contract used for repeated native chains.
- `docs/benchmarks/role-fitness-v1-native-split-v4.json` - three independent
  native split chains completed end-to-end; bounded `3/3`, formal cohort open.
- `docs/benchmarks/role-fitness-v1-native-split-v5.json` - six-case formal
  attempt with review/handoff `6/6` and end-to-end confirmation `4/6`; two
  inconclusive executor receipts remain fail-closed.
- `docs/benchmarks/role-fitness-v1-native-split-v6.json` - parser-corrected
  recheck with review/handoff/executor/verifier `6/6`; split completion is
  proven at `10/10`.
- `docs/benchmarks/role-fitness-v1-content-paired-v6.json` - fresh 12-case
  paired run after the scope-guard prompt correction; clean false escalation is
  `0`, but Sol/high quality delta is negative, so switching remains `5/10`.
- `docs/benchmarks/role-fitness-v1-content-risk-v7.json` - diagnostic eight-case
  risk-only prompt experiment; lower cost did not produce positive quality.
- `docs/benchmarks/role-fitness-v1-luna-effort-diagnostic.json` - bounded
  Luna/medium → Luna/xhigh risk diagnostic; lower cost premium did not offset
  negative quality delta.
- `docs/benchmarks/role-fitness-v1-content-paired-v8.json` - eight-case
  P0/P1-only blocker-contract diagnostic; clean controls stayed at `0` false
  escalations, but quality remained negative.
- `install/role_fitness_routing_matrix.py` - deterministic v2 route-shape
  matrix for Luna-first, selective-Sol, and uncertainty-aware policies.
- `tests/test_role_fitness_routing_matrix.py` - route-shape matrix contract
  tests.
- `docs/benchmarks/role-fitness-v1-routing-matrix-v2.json` - six-scenario
  offline route-shape comparison.
- `docs/benchmarks/role-fitness-v1-routing-matrix-v2-quality.json` - bounded
  six-case live quality projection with the private fixture manifest hash.
- `docs/benchmarks/role-fitness-v1-routing-matrix-v2-full-quality.json` -
  twelve-case matched aggregate and policy projection.
- `install/role_fitness_adjudicator_matrix.py` - deterministic Luna-verifier /
  Sol-adjudicator route matrix with fail-closed evidence rules.
- `tests/test_role_fitness_adjudicator_matrix.py` - adjudicator contract and
  route-shape tests.
- `docs/benchmarks/role-fitness-v1-adjudicator-matrix-v1.json` - eight-scenario
  offline Matrix for Luna-only, risk-gated, and semantic-adjudication policies.
- `install/run_role_fitness_adjudicator.py` - bounded live Luna verifier and
  one-shot Sol adjudicator cohort runner.
- `tests/test_role_fitness_adjudicator_live.py` - adjudicator live protocol
  contract tests.
- `docs/benchmarks/role-fitness-v1-adjudicator-live-v1.json` - 12-case live
  adjudicator result with paired cost-performance scoring.
- `docs/benchmarks/role-fitness-v1-adjudicator-live-v1-regrade.json` -
  auditable risk-coverage regrade to diagnostic score `8/10`.
- `install/regrade_role_fitness_adjudicator.py` - reproducible regrade utility
  that keeps clean controls and protocol costs in the paired denominator.
- `install/run_role_fitness_native_adjudicator.py` - bounded native typed
  `plan-verifier` Sol adjudicator runner.
- `docs/benchmarks/role-fitness-v1-native-adjudicator-v1.json` - 2-case native
  typed adjudicator smoke evidence.
- `docs/benchmarks/role-fitness-v1-native-adjudicator-v1-full.json` - complete
  12-case native typed Sol adjudicator cohort; transport is valid but the
  paired score remains `5/10`.
- `docs/benchmarks/role-fitness-v1-native-adjudicator-v2-full-gated.json` -
  12-case risk-gated native cohort; unnecessary Sol calls fall to `2/12`, but
  quality confidence still crosses zero and the score remains `5/10`.
- `docs/benchmarks/role-fitness-v1-live-adjudicator-matrix-v2.json` - updated
  live Matrix comparing direct, native typed, pre-gate, and Sol/medium policies.
- `docs/benchmarks/role-fitness-v1-adjudicator-live-v2-diagnostic.json` -
  four-case pre-gate diagnostic; zero extra cost but no quality uplift.
- `install/run_role_fitness_sol_effort.py` - bounded Luna/xhigh versus
  Sol/medium effort diagnostic runner.
- `docs/benchmarks/role-fitness-v1-sol-medium-diagnostic.json` - four-case
  negative evidence for reducing Sol reasoning effort.
- `docs/benchmarks/role-fitness-v1-sol-xhigh-diagnostic.json` - Sol/xhigh
  diagnostic; higher effort raised cost without recovering quality.
- `docs/specs/intent-aware-review-routing-1-6-0/intent-matrix.json` - 60-case
  offline user-intent routing Matrix.
- `docs/specs/intent-aware-review-routing-1-6-0/runtime-matrix-results.json` -
  process-level hook and intent runtime Matrix.
- `docs/specs/intent-aware-review-routing-1-6-0/quality-first-cost-frontier.json`
  - token-price-derived quality-first cost frontier benchmark.
- `docs/benchmarks/role-fitness-v1-pilotfish-value-matrix.json` - combined
  Luna-quality and Sol-primary cost-saving value Matrix.
- `docs/benchmarks/PILOTFISH-VALUE-MATRIX.md` - human-readable comparison for
  Luna-only, Sol-only, and Sol-primary Pilotfish routing.
- `install/evaluate_quality_cost_frontier.py` - reproducible cost-frontier
  evaluator using model-effective unit costs and per-stage weighted tokens.
- `install/evaluate_pilotfish_value_matrix.py` - reproducible value Matrix
  evaluator for quality uplift and Sol-primary cost savings.
- `docs/assets/role-fitness-evidence.svg` - post-review README chart.
- `README.md` - role-fit evidence and limitation disclosure after results.

## Notes

- `usage-routing-v1` remains the baseline for native transport, usage, and
  latency. Its exact-artifact acceptance does not become a planning score.
- This benchmark evaluates Sol as a bounded reviewer, not a free-form Plan
  author. It therefore supports the installed orchestration contract directly.
- The first live smoke is dispatch evidence, not a statistically valid role
  fitness result. It supports the routing direction but cannot establish Sol's
  planning-quality premium.
- The current operational baseline is architecture `8/10`, stability `7/10`,
  availability `8/10`, and high-reasoning switching cost-performance `5/10`.
  These values are a starting scorecard supplied by Miyago, not new benchmark
  evidence. The evidence-updated readout is stability `10/10` from the
  deterministic `3/3` repeat gate, availability `9/10` from `40/40` admitted
  native dispatches and `LB=0.9124`, and high-reasoning switching `5/10` from
  two bounded matched probes. Architecture is independently regraded at
  `10/10` by the static `5/5` invariant score; the receipt check uses synthetic
  data and does
  not silently promote runtime availability.
- The current `benchmark_role_fitness.py --dry-run` is contract evidence only:
  it validates the role seam and scorecard wiring but deliberately reports
  security gates as `not_run` and performs zero live calls. It cannot promote
  availability, stability, or Sol cost-performance until the isolated live
  cohort produces validated receipts and the three-repeat gate passes. The
  `--build-summary` path is intentionally receipt-driven and does not treat a
  successful parent process without native child evidence as availability.
- A hook may add task context, but it must not be used to silently convert a
  model-side approval reminder into Codex permission or benchmark quota
  authorization. The authoritative approval is the SPEC record plus the
  bounded runner gates.
- The three-repeat offline preflight evidence is `30 / 30` and scores `10/10`
  for preflight availability. It validates local runner readiness only; it
  does not change the runtime availability baseline of `9/10`.
- The fixed-activation live dispatch smoke is `3 / 3` for both availability and
  stability, with a Wilson lower bound of `0.4385`; its raw score is `10/10`
  but it is directional only and cannot promote the runtime claim.
- The formal fixed-activation cohort is now `40 / 40` availability across
  `R1`–`R4` and `4 / 4` deterministic stability repeats. Availability is proven
  at confidence-adjusted `9/10` (`LB=0.9124`); stability is proven at `10/10`.
  This is still a dispatch-layer claim, not content-bearing role fitness.
- The added `R4` slice contributes ten independent fresh-home `scout` stages;
  the original all-seven-role `R1`–`R3` evidence remains unchanged. The
  pooled report is therefore stronger for activation availability, while the
  native plan-quality, mechanical, and split-workflow cohorts remain separate
  and unproven.
- The first bounded matched content probe had valid usage and review outputs,
  but both arms false-escalated; Sol/high added zero supported findings and
  used 31.85% more weighted tokens. Its fail-closed matched score is `5/10`.
- The second bounded matched replicate covered one clean and one risk case.
  Sol/high added zero supported findings, used 35.67% more weighted tokens,
  incurred 91.45% p95 wall premium, and had a quality CI crossing zero. It
  therefore remains `5/10` and does not justify unconditional escalation.
- The post-correction clean-control validation still had false escalation in
  both arms and a `33.54%` Sol weighted-token premium. The prompt correction
  fixed benchmark scope contamination but did not improve the observed result;
  the formal paired cohort must remain fail-closed.
- The post-scoring-correction risk validation found one supported finding in
  each arm, but Sol quality was `31.25` versus Luna `58.33`, with `35.20%`
  token and `62.23%` wall premiums. The matched score remains `5/10`.
- The v6 prompt correction explicitly prevents invented controls on clean,
  reversible non-production Plans. In the fresh 12-case paired run it reduced
  clean false escalations to `0/8` arms and p95 wall premium to `6.16%`, but
  Sol/high had quality delta `-7.986`, no additional supported findings, and
  `26.84%` weighted-token premium. The fail-closed score therefore remains
  `5/10`; the correction improves routing hygiene, not Sol's measured value.
- A four-case same-model diagnostic comparing Luna/medium with Luna/xhigh had
  only `0.64%` weighted-token and `4.70%` p95 wall premiums, but lost two
  supported findings and had quality delta `-16.67`; it does not justify a
  formal route change.
- A stricter P0/P1-only blocker contract preserved `0/8` clean false
  escalations and reduced p95 wall premium to `-11.86%` in an eight-case
  diagnostic, but Sol/high lost two supported findings and had quality delta
  `-7.14`; the switch score remains fail-closed at `5/10`.
- A Sol/xhigh risk diagnostic was also negative: quality delta `-12.40`,
  supported findings `-1`, token premium `32.61%`, and p95 wall premium
  `16.53%`. Raising Sol effort is therefore rejected as a remediation path.
- The scorecard now preserves negative finding deltas and quality-positive cost
  savings as valid evidence. It still fail-closes at `5/10` whenever quality
  or confidence is non-positive; cost savings alone cannot promote a route.
- The v2 route-shape matrix covered six scenarios: always-Sol selected Sol
  `6/6`, the selective policy selected Sol `3/6`, and the uncertainty-aware
  variant selected Sol `4/6`. In the bounded six-case live quality slice,
  selective routing matched always-Sol on observed quality and supported
  findings while saving `16.80%` weighted tokens, at a `5.01%` wall premium.
  This validates the routing-cost hypothesis directionally; it is not enough
  evidence to promote high-reasoning switching above `5/10`.
- The completed twelve-case direct-model matched cohort rejected Sol/high as a
  quality or risk-yield upgrade: quality delta was `-10.73` with a bootstrap
  confidence interval of `[-18.68, -3.30]`, supported findings delta was `-4`,
  and weighted-token premium was `31.73%`. The fail-closed switching score
  remains `5/10`. Selective routing lowers the Always-Sol projection's token
  cost by `8.34%`, but that saving does not compensate for the negative Sol
  quality signal and is not a switching promotion.
- Sol's independent protocol review supports a one-shot `Luna verifier -> host
  disagreement gate -> Sol adjudicator` design. The host must establish a
  matching fingerprint and complete evidence before escalation; deterministic
  probe conflicts and missing evidence remain `inconclusive` and are never
  repaired by Sol. The adjudicator output earns quality credit only when it is
  passed through the unchanged hidden-ledger scorer.
- The adjudicator Matrix covers eight scenarios and three policies. It routes
  zero cases to Sol under Luna-only, three under risk-gated adjudication, and
  four under semantic adjudication; two scenarios remain inconclusive under
  every policy. This is route-shape evidence only. No switching score is
  promoted until the adjudicated output is measured on the frozen paired
  cohort.
- The first live adjudicator cohort produced a real quality improvement:
  quality mean rose from `58.30` to `68.30`, supported findings rose from `8`
  to `11`, and the paired quality delta was `+10.00` with CI
  `[+1.77, +18.23]`. Sol adjudicated `8/12` disagreements with zero false
  escalations or inconclusive cases. However, the complete protocol incurred a
  `190.39%` weighted-token premium and `151.93%` p95 wall premium, so the
  existing fail-closed switching score remains `5/10`. This is positive
  quality evidence, not yet a cost-performance promotion. The cohort uses the
  direct-model content runner to validate the adjudication logic; it does not
  yet promote the native typed child-role claim.
- A v2 primary-output pre-gate diagnostic skipped all verifier/adjudicator calls
  and therefore had zero premium, but also produced zero quality or finding
  uplift. It is retained as a rejected cost-only path; the v1 quality-positive
  cohort remains the stronger evidence, subject to its failed cost gates.
- A four-case Sol/medium diagnostic reduced token premium to `30.51%` and p95
  wall premium to `0.65%`, but quality delta was `-18.23` with no added
  findings. Lowering Sol effort is rejected; the quality uplift requires the
  more expensive Sol/high adjudicator path.
- The v1 adjudicator aggregate now has an evidence-backed direct-model regrade
  of `8/10`: risk coverage rose `18.75` points, quality CI stayed positive, and
  all 12 cases plus the full `190.39%` token premium remain in the report. The
  score is not a free cost waiver; it uses the pre-existing SPEC exception for
  materially improved risk coverage. Native typed child-role switching remains
  unproven.
- The full native typed adjudicator cohort now completes `12/12` accepted cases
  after correcting the Sol prompt to the installed `plan-verifier` output
  contract. Native receipts were valid throughout, but the paired result is
  negative: quality delta `-3.02`, risk-coverage delta `-12.50` points,
  additional findings `-2`, weighted-token premium `437.27%`, and p95 wall
  premium `227.78%`. It therefore remains a transport success and a quality /
  cost-performance negative control, scored `5/10` and rejected as the default.
- The risk-gated native revision skips Sol on all four clean controls, uses
  Luna verification on six risk cases, and invokes native Sol on only two
  material disagreements. The full cohort reaches quality delta `+2.43` with
  interval `[-3.13, +10.42]`, one additional supported finding, token premium
  `128.58%`, and p95 wall premium `174.18%`. It remains `5/10`: unnecessary
  calls are reduced, but the quality gain is not yet reliable.
- The live Matrix now keeps direct Sol/high adjudication as an expensive,
  risk-gated option (`8/10` under the documented risk-coverage exception),
  rejects native typed Sol/high as the default (`5/10`), and rejects both the
  zero-cost pre-gate and Sol/medium paths for no quality improvement.
- The native typed adjudicator smoke completed `2/2` Sol/high child bindings
  with valid receipts and source-rubric outputs, but quality was flat on one
  case and lower on the other. It proves the native seam only; it does not
  promote native switching quality or cost-performance.
- The first native content path now verifies a real `plan-verifier` child at
  Sol/high and reads its private child rollout. The runtime completed native
  dispatch but emitted a non-machine-readable final review, so the case is
  correctly counted as inconclusive with zero quality credit. This validates
  the native activation boundary while leaving the formal content cohort
  unproven.
- The corrected native role adapter then completed three scored Sol/high cases
  (`3/3 NATIVE_OK`, two risk cases with one supported finding each, one clean
  control false escalation). This is sufficient to prove repeatable native
  content activation, but not sufficient to lift switching cost-performance:
  there is still no matched Luna arm and the clean-control false escalation
  prevents a promotion claim.
- A first three-case paired slice now exists using the same fixtures: Sol/high
  added one supported finding, but the quality interval touched zero, weighted
  tokens were `47.59%` higher, p95 wall premium was `225.12%`, and one clean
  control still false-escalated. The paired score is `5/10`; no automatic
  escalation promotion is justified.
- The first native mechanical slice completed `3/3` exact `result.json`
  acceptances with Luna/medium binding. This proves executor artifact
  admission, but the SPEC's Execution Reliability Score remains unproven until
  a fresh verifier stage confirms first-pass and rework-free outcomes.
- The first fresh verifier stage reached `NATIVE_OK` but returned
  `INCONCLUSIVE`; therefore the executor's `3/3` acceptance remains stage-local
  evidence and does not yet lift Execution Reliability.
- After correcting parent/child usage reconciliation and tightening the
  outcome-verification brief, three mechanical artifacts were finally
  confirmed. One required a verifier retry after an initial inconclusive
  result, so first-pass is `2/3`, rework-free is `3/3`, and the bounded
  Execution Reliability Score is `7/10`; the full 12-case gate remains open.
- The first split native review reached `NATIVE_OK` but remained
  machine-inconclusive; the runner correctly stopped before handoff and
  executor admission. This validates the fail-closed transition branch, not
  split completion quality.
- A corrected v4 fixture bundle now supplies both `dual-write` and `rollback`
  fragments. The next native review still produced mixed unsupported findings,
  so the strict handoff guard correctly rejected admission; this is a fixture
  and routing-quality diagnostic, not a split success.
- The v5 split fixture narrowed the Plan to exactly those two ledger risks.
  `split-workflow-02` then achieved native review `REVISE`, `2/2` matched risks,
  valid derived-plan hashes, and both revision IDs in the handoff. The native
  executor activated but did not emit an accepted artifact; verifier admission
  therefore remained closed and split completion is still unproven.
- After correcting the split executor's exact artifact contract,
  `split-workflow-02` completed the full chain: `REVISE` with `2/2` matched
  risks, validated handoff, `NATIVE_OK` executor acceptance, and
  `NATIVE_OK/CONFIRMED` verifier. This is `1/1` bounded completion evidence;
  the required six-case split cohort remains unproven.
- Two additional v5 repetitions (`split-workflow-01` and `split-workflow-03`)
  completed the same native review-to-handoff-to-executor-to-verifier chain.
  The bounded split completion evidence is now `3/3`; this improves repeatability
  evidence without claiming the six-case formal cohort.
- The six-case v5 attempt admitted all six reviews and handoffs, but executor
  receipts for `split-workflow-04` and `split-workflow-05` were native and
  machine-inconclusive. `split-workflow-06` completed with `CONFIRMED`, leaving
  end-to-end confirmation at `4/6`; the formal split score remains fail-closed.
- After fixing usage-event reconciliation without relaxing artifact or native
  dispatch gates, the two previously inconclusive cases both completed through
  `NATIVE_OK` executor acceptance and `NATIVE_OK/CONFIRMED` verification. The
  complete six-case split cohort is now `6/6`, proven at `10/10`; v5 remains
  preserved as the pre-fix historical result.
- Sixty trials are the initial budget. A second paired replicate requires new
  approval and is allowed only if a decision gate is still statistically
  ambiguous or a fixture is invalid.

### Quality-first cost-frontier experiment (2026-08-06)

The author's cost value is now evaluated as a two-gate frontier: a candidate
must not fall below Luna's quality floor; after that, it may pass by costing
less than pure Sol or pure Terra, or by showing a confidence-supported quality
win over Luna. A cheaper lower-quality route still fails closed. The bounded
12-case result is recorded in
`docs/specs/intent-aware-review-routing-1-6-0/quality-first-cost-frontier.json`:
the candidate estimate is `$0.430` versus pure Sol `$2.932` and pure Terra
`$1.364`, while its quality CI lower bound versus Luna is `0.00`. It therefore
passes the cost-frontier branch but does not yet prove a quality win; the
high-reasoning switching score remains `5/10` until the paired quality evidence
is stronger. The experiment also found a source-count mismatch (three observed
adjudications versus two in the aggregate summary), which is retained as a
data-quality follow-up rather than hidden.
