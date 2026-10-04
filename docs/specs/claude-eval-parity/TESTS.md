# TESTS — claude-eval-parity

> Acceptance cases for `SPEC.md`. B0–B3 are offline; B4–B5 need approved
> paid runs. AC-CE-018 needs one approved minimal live call.

## Prompt surface protection（B0）

- **AC-CE-001:** When a Claude agent file under `hosts/claude/dist/agents/`
  changes beyond its budget, `validate_prompt_lock.py` shall fail and name
  the surface.
- **AC-CE-002:** When a Claude surface loses one of its
  `required_fragments`, the lock check shall fail.
- **AC-CE-003:** When any Claude surface changes and the Claude host version
  is unchanged from the base, the lock check shall fail.
- **AC-CE-004:** The commit that adds Claude surfaces to `LOCK.json` shall
  not change any prompt content; its file list shall contain only the lock,
  validator, version files and tests, and all render `--check` commands
  shall pass on that commit.
- **AC-CE-005:** When only a Claude surface changes and the Claude host
  version changes, the lock check shall pass without a change to the root
  `VERSION`.
- **AC-CE-006:** The workflow `paths` for both `pull_request` and `push`
  shall include `hosts/claude/**`; a PR that changes only
  `hosts/claude/dist/agents/*.md` shall trigger the workflow and shall be
  blocked by the lock check.
- **AC-CE-007:** The renewal shall have a reproducible green path: with the
  `lock-renewal` label (PR) or the `Lock-Renewal: approved` trailer (main
  push) the workflow passes `--allow-lock-update`, and without them a
  `LOCK.json` change stays red. Offline, the validator is run in a temp git
  repo with and without the flag, and the workflow file is checked
  statically for both switches and the `labeled`/`unlabeled` types; the
  first real renewal PR confirms the CI behaviour.

## Host adapter（B1–B2）

- **AC-CE-010:** When the Codex path runs through the extracted adapter
  interface, its stage outputs shall be field-for-field identical to the
  pre-refactor runner on the same recorded inputs.
- **AC-CE-011:** When the Claude adapter processes a recorded stream that
  contains an `Agent` tool call, it shall report the `subagent_type` as
  dispatch evidence; when no such call exists, the stage shall be marked as
  a dispatch failure.
- **AC-CE-012:** The Claude adapter shall stage `.claude/agents/` from the
  committed `hosts/claude/dist/agents/`, and the argv and env it builds
  shall satisfy all of the following (asserted on the built command, not
  only on the copied agents):
  - argv contains `-p`, `--output-format stream-json`, `--verbose`,
    `--setting-sources project` and `--max-budget-usd <amount>`.
  - env `CLAUDE_CONFIG_DIR` is a fresh temp directory, distinct per stage,
    and neither equal to nor under `~/.claude`.
  - no argv element or recorded log line contains the subscription token.
- **AC-CE-013:** The Claude prompt shall not contain `spawn_agent` or
  `wait_agent`.
- **AC-CE-014:** When a stage finishes, its raw stream and its temp config
  directory (transcripts, session data) shall be deleted; a failed deletion
  shall mark the stage as failed.
- **AC-CE-015:** The Claude run shall load the same frozen manifest v2 and
  shall reject a manifest with a different hash.
- **AC-CE-016:** The Claude adapter shall read the subscription token from
  the environment only; the token shall not appear in files, command
  arguments, logs, or recorded streams.
- **AC-CE-017:** When the cumulative `total_cost_usd` plus the next stage's
  reserved per-stage cap would exceed $30, the runner shall not admit the
  stage; tested offline with recorded costs.
- **AC-CE-018:** (needs approval) One minimal live call shall confirm the
  repo-external facts in R4 and R6: the token env var name works under a
  fresh `CLAUDE_CONFIG_DIR`; `--verbose` works with `-p --output-format
  stream-json`; `~/.claude` has the same file list and mtimes before and
  after; user-level hooks, skills and agents are not loaded; and
  `--max-budget-usd` aborts the call when exceeded. If the last point
  cannot be shown, paid runs stay dry-run only.

## Failure taxonomy（B3）

Result files below live in `docs/benchmarks/`; names omit the
`role-fitness-v1-` prefix. The classifier input is a recorded runner-format
stage dict (Decision 4), never the benchmark JSON itself. The benchmark
files are the source of expected values only; each fixture is built from
the file fields as mapped below. Stage fields not listed come from the
runner's normal accepted or inconclusive return.

| File and case | File fields | Recorded runner stage | Expected |
|---|---|---|---|
| `native-content-plan-r1`, plan-review-01 (:9) | `status: accepted`, `false_escalation: true`, `supported_findings: 0` | `status: accepted`, `dispatch_status: NATIVE_OK`, `false_escalation: true`, `risk_coverage: 1.0`, `score.expected_decision: READY` | `false_escalation` |
| `native-content-plan-r1`, plan-review-06 (:11); plan-review-05 (:10) is identical | `status: accepted`, `supported_findings: 1`, `quality_score: 42.5`, `false_escalation: false` | `status: accepted`, `false_escalation: false`, `risk_coverage: 0.5` (inferred from aggregate :17, confirm by re-scoring), `score.expected_decision: REVISE` | `missed_risk` |
| `native-content-probe` (:8-12) | `dispatch_status: NATIVE_OK`, `review_json_valid: false`, `status: inconclusive` | `status: inconclusive`, `reason: invalid_native_review_output`, `dispatch_status: NATIVE_OK` | `unparseable_output` |
| `native-split-v2` executor (:9) | `status: inconclusive`, `accepted_artifact: false`, `dispatch_status: NATIVE_OK` | `status: inconclusive`, `reason: invalid_split_executor_acceptance`, `dispatch_status: NATIVE_OK` | `executor_no_artifact` |
| `native-split-v5`, split-workflow-04 and 05 (:11-12) | `executor: "INCONCLUSIVE"`, `verifier: "not_run"` | same executor stage as the row above; no verifier stage | `executor_no_artifact` |
| `native-split-v5`, split-workflow-01 to 03 and 06 (:8-10, :13) | `executor: "accepted"`, `verifier: "CONFIRMED"` | accepted executor stage and accepted verifier stage, no `rerun_of` | no class |
| `native-mechanical-verifier-r2`, mechanical-execution-02 (:10) | `verification: CONFIRMED`, `retry_after_initial_inconclusive: true` | `status: accepted`, `native_role: verifier`, `verification: CONFIRMED`, `attempt: 2`, `rerun_of: mechanical-execution-02#1` | `verifier_retry` |
| `native-mechanical-verifier-r2`, mechanical-execution-01 and 03 (:9, :11) | `verification: CONFIRMED`, no retry field | accepted verifier stage, `attempt: 1`, no `rerun_of` | no class |
| `native-mechanical-verifier-r1` (:9-12) | `verification: INCONCLUSIVE`, `status: inconclusive`, `dispatch_status: NATIVE_OK` | `status: inconclusive`, `reason: verifier_did_not_confirm`, `verification: INCONCLUSIVE`, `dispatch_status: NATIVE_OK` | `verifier_inconclusive` |

`content-plan-cohort.json` is a direct_model_proxy aggregate with no
per-case data (:13, :20 `clean_false_escalations` 3 and 4; :12, :19
`risk_coverage` 0.6875 and 0.5), so it is not replayed; it is only a
sanity reference for expected totals.

- **AC-CE-020:** When the classifier is fed the recorded plan-review-01
  stage, it shall return `false_escalation`; when fed the recorded
  plan-review-05 and plan-review-06 stages, it shall return `missed_risk`
  for both (risk case with per-case `risk_coverage < 1.0`), and a clean
  control stage with `risk_coverage` 1.0 and no escalation shall get no
  class.
- **AC-CE-021:** When the classifier is fed the recorded
  `native-content-probe` stage, it shall return `unparseable_output`.
- **AC-CE-022:** When the classifier is fed the recorded executor stages
  for `native-split-v2` and `native-split-v5` (split-workflow-04 and 05),
  it shall return `executor_no_artifact`, and the stages with accepted
  artifacts shall get no class.
- **AC-CE-023:** When the classifier is fed the recorded
  mechanical-execution-02 stage with `rerun_of`, it shall return
  `verifier_retry`; the same stage without `rerun_of` shall not be
  classified `verifier_retry`.
- **AC-CE-024:** When a failed stage matches no category (for example a
  `timeout` stage), it shall be classified `unclassified`, never left
  empty.
- **AC-CE-025:** The run summary's `failure_taxonomy` shall contain both the
  existing dispatch-layer keys and the new `content.*` keys.
- **AC-CE-026:** The report shall list per-arm category counts and shares
  next to the scores, with R1–R3 shown separately.
- **AC-CE-027:** The public projection shall accept the new category keys
  and shall still reject free text, prompts, fixture content, and paths.
- **AC-CE-028:** When the classifier is fed the recorded
  `native-mechanical-verifier-r1` stage (verifier `inconclusive`, no stage
  with a matching `rerun_of`), it shall return `verifier_inconclusive`;
  when a rerun stage with that `rerun_of` exists, the initial stage shall
  not be counted again.
- **AC-CE-029:** The runner shall emit `attempt` and `rerun_of` only when
  the operator explicitly requests a rerun of an INCONCLUSIVE stage; a
  first run shall not emit `rerun_of`, and the runner shall never retry on
  its own.

## Paid runs（B4–B5）

- **AC-CE-030:** The smoke run shall start only after Miyago's approval and
  shall execute at most (processes per arm × number of arms) processes,
  summed over the cohorts (plan review 1, mechanical 2, split 3 per arm);
  the cap is not a fixed 6 (6 with one arm per case, 12 with two).
- **AC-CE-031:** When a run reaches $30 API-equivalent cost or 8,000,000
  weighted tokens, it shall stop and keep completed stages.
- **AC-CE-032:** When the run receives a usage-limit response, it shall stop
  immediately and report the completed stages.
- **AC-CE-033:** R2 and R3 shall start only after the previous run's result
  has been reviewed and the next run approved.
- **AC-CE-034:** The B4 approval sheet shall list the per-stage cap
  (`--max-budget-usd` amount) and the process total computed from the
  arm count; a run without both shall not start.
