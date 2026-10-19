# Usage-first routing pilot

- Slug: `usage-first-routing`
- Status: Done
- Owner: Miyago
- Created: 2026-08-03

## Goal

Measure whether Luna, Terra, and Sol routing lowers real Codex usage without
accepting a quality regression. Use quality as a manual fail-closed gate, then
rank accepted routing chains by usage and, within a 5% usage band, by p95
settled time.

## Decisions

- Run 12 versioned representative cases, each with Luna, Terra, and Sol, for
  exactly 36 independently reproducible trials.
- Keep the parent fixed at Luna/medium. Routine cases use mech-executor;
  judgment cases use executor. Candidate bindings change only the named role
  in an isolated temporary Codex home.
- Model chains are post-hoc clean-rerun simulations: `L→T→S`, `L→S`, `T→S`,
  and `S only`. They do not claim to measure context or artifact handoff.
- Quality verdicts are blinded, human-provided `accept`, `reject`, or
  `inconclusive`; missing or inconclusive verdicts fail closed.
- A deterministic artifact failure is retained as a safe rejected trial with
  its measured usage and latency; it is not treated as runner infrastructure
  failure or silently excluded from chain simulation.
- Use a cohort-wide upstream quota delta only with an explicit exclusive-account
  attestation and stable snapshots. Otherwise price the exact native parent and
  child rollout ledgers consistently for the whole cohort; never mix sources.
- Keep security review and execution on Sol/high. For non-security work, keep
  Luna as the default; no Terra binding is retained. Sol/high runs at the
  existing risk-triggered Plan-review boundary; only the model binding changes.

## Pilot result

The successful v6 cohort contained all 36 trials. The recommendation settled
on `L→S`, retaining no Terra tier: Luna passed every artifact contract, so the
conditional Sol tier was not selected in this cohort. Aggregated by candidate:

| Candidate | Artifact acceptance | Equivalent cost / 12 | Median wall time |
| --- | ---: | ---: | ---: |
| Luna | `12 / 12` | `$0.743874` | `28.55s` |
| Terra | `10 / 12` | `$1.363531` | `41.09s` |
| Sol | `5 / 12` | `$2.931608` | `40.76s` |

The acceptance check is a deterministic artifact contract, not a human
intelligence benchmark. It establishes that Terra is not justified for this
usage-first route and that Sol needs a narrow, evidence-backed role rather than
unconditional task execution.

## Metrics

The audited native-rollout proxy records the final cumulative parent and child
`In`, `Out`, cache-read (`CR`), and cache-write (`CW`) totals. It prices each
participant at its own pinned model rate; the parent is Luna/medium and the
child is the candidate binding. Its versioned equivalent cost is:

```text
USD = (In × Pin + CR × Pin × 0.1 + CW × Pin × 1.25 + Out × Pout) / 1,000,000
```

Native `output_tokens` already includes reasoning output, so reasoning is
validated for schema stability but never charged a second time.
The report retains raw tokens, reasoning-token visibility, and the parent
process wall time alongside currency. Wall time is a latency signal, not a
claim of pure model-reasoning time. The report identifies the selected metric
source and confidence for each cohort.

## Credential boundary

- The live runner accepts a user-owned `auth.json` only through an explicit
  absolute path. It rejects symlinks and opens the source with no-follow file
  descriptors; owner, file type, mode, and fingerprint must remain valid while
  copying.
- Codex runs in a private temporary home with both `CODEX_HOME` and
  `CODEX_SQLITE_HOME` isolated. The copied credential is mode `0600`, is removed
  immediately after the Codex process group exits, and is never provided to
  CodexBar.
- CodexBar analyses a second, credential-free directory containing only the
  required session material as an optional cross-check. Reports retain the
  native primary metrics, cross-check availability, and receipts; raw stdout,
  stderr, and session JSONL are not saved.
- The runner sanitizes inherited credential-source environment variables and
  snapshots the permanent home before and after a trial. A mismatch fails the
  trial. It cleans known inactive stale run directories on startup; a host
  `SIGKILL` can leave a private stale directory until that next safe cleanup.

## Verification

- Validate corpus, temporary-home projection, named role binding, receipt
  correlation, native-ledger accounting, CodexBar schema, quota invalidation,
  verdict gate, chain simulation, and the 36-trial cap with targeted unit
  tests.
- Require a dry run that produces three isolated binding receipts without a
  persistent config change.
- Live mode requires explicit opt-in flags, refuses CI, receives authentication
  through a temporary protected copy, and cleans it in all recoverable paths.
- Update README benefit metrics only after a decoded pilot report is reviewed
  and approved by Miyago.
