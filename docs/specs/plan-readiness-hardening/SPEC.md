# SPEC — Plan Readiness Hardening: Upgrade Path & Brake Durability

- Slug: `plan-readiness-hardening`
- Status: Proposed
- Owner: Miyago
- Created: 2026-07-27
- Source PR:
  [#6 — fix(plan): bound readiness by executable slices](https://github.com/miyago9267/pilotfish-codex/pull/6)
  (author @Nanako0129, branch `codex/plan-verifier-convergence`)
- Related spec:
  `codex-native-multi-agent-migration` (archived, see git history)
  — this spec extends its installer transactional boundary rather than
  redefining it.

## Context

PR #6 replaces the unbounded plan-verifier loop with a program envelope plus
independently approvable execution slices, requires bare `READY` or structured
`REVISE`, applies a two-verdict brake per readiness unit, and orders
`security-reviewer` ahead of the first readiness review for affected units. It
also adds an installer upgrade path so release-pinned prior canonical role
bytes can be replaced without operator intervention.

The policy design, slice model, role prompts, and the upgrade allowlist
mechanism are accepted as-is. This spec records only the review findings that
remain open after PR #6, so they are tracked instead of lost in PR comments.

## Review evidence (PR head `0d3f859`, verified locally)

Checked in a detached worktree of the PR head, not assumed:

- Offline suite: **79 tests pass** (`python3 -m unittest discover -s tests`).
- The v1.3.0 fixture bytes in `install/previous/v1.3.0/agents/` hash to
  `c552938705065c826da9a3cbaf09c2fbbaa9fde4adb1f691a59b694d8468f541`
  (`plan-verifier`) and
  `94d7de12d1cb197c98e83c2f78d402cf3fb393e860feee1e146f5b6294075d27`
  (`security-reviewer`), byte-identical to the same templates on `main`. The
  upgrade path therefore fires for real v1.3.0 installs, not only for
  reconstructed fixtures.
- A one-byte customization of an installed role still aborts with
  `installed_role_drift`.
- `install/install.sh` fetches the full repository tarball, so
  `install/previous/` is present on the execution host at install time.
- Driving `install(dry_run=True)` against a synthetic v1.3.0 home prints only
  `would change`; the `upgraded canonical role …` notes are unreachable in the
  dry-run path.

Both bot findings on PR #6 are genuinely resolved: the readiness retry loop now
names a fresh `plan-verifier` (`c5e4986`, pinned by `test_policy.py`), and the
canonical-role upgrade allowlist unblocks v1.3.0 → v1.3.1 installs
(`0d3f859`). Neither is restated as work here.

## Findings

### G1 — Dry run hides planned canonical role replacement (resolved)

`install/install.py` returned from the `dry_run` branch before the `notes` loop
executed, so a dry run never reported that two installed role files were about
to be overwritten. Fixed on branch `fix/install-dry-run-upgrade-notes`: dry-run
now emits the same `note:` lines (including
`upgraded canonical role <role>`) before the early return, without writing.
Regression:
`test_dry_run_names_canonical_role_upgrades_without_writes`.

#### Dry-run boundary (as implemented on PR head `0d3f859`)

Planning runs fully whether or not `dry_run` is set. The dry-run flag only
suppresses the commit path and, today, also suppresses note emission.

| Step | dry-run | real install |
|---|---|---|
| Version pin / home inventory / config+policy merge plan | yes | yes |
| Role byte compare; upgrade allowlist match | yes | yes |
| Custom same-name bytes → `installed_role_drift` abort (no write) | yes | yes |
| Build `writes[]` (config / policy / new roles / upgraded roles) | yes | yes |
| Validate planned native config + role manifest extras | yes | yes |
| Print `would change` / `already up to date` | yes | no (prints `changed…` after commit) |
| Print `note: upgraded canonical role <role>` and other merge notes | **no** (gap) | yes, after successful commit |
| Create pending sidecar / atomic write / post-write fingerprint | no | yes |
| Mutate any file under `CODEX_HOME` | no | only listed `writes[]` |

Invariants that already hold and must not regress:

1. **Plan-before-write**: every target is decided before any mutation.
2. **Fail closed before dry-run return**: drift, extra roles, and invalid planned
   config abort with exit 2 and leave the home untouched even under `--dry-run`.
3. **Dry-run is read-only**: no config, policy, role TOML, or install-state
   sidecar is created, modified, or removed.
4. **Upgrade is exact-bytes only**: only digests in
   `CANONICAL_ROLE_UPGRADE_DIGESTS` (today: release-pinned v1.3.0
   `plan-verifier` + `security-reviewer`) may enter `writes[]` as replacements.

What G1 still requires: when dry-run builds a non-empty `writes[]` that includes
a role upgrade, stdout must name each role (same note text as the real path, or
an equivalent planned-write line) so operators can approve automatic
replacement without guessing.

### G2 — Upgrade digests are hand-maintained and omit the current release

`CANONICAL_ROLE_UPGRADE_DIGESTS` is a literal in `install/install.py`, while
the same bytes are also stored under `install/previous/v1.3.0/agents/`. The
allowlist carries v1.3.0 digests only. When a later release changes a role
payload again, every v1.3.1 install reproduces the exact abort PR #6 fixed
unless a maintainer remembers to extend the literal.

Decision: derive the allowlist at load time from
`install/previous/<version>/agents/<role>.toml`, keeping exact-bytes matching
and fail-closed behavior for every other difference. Release procedure reduces
to copying the outgoing templates into a new `install/previous/<version>/`
directory.

### G3 — Policy negative assertions are line-wrap fragile

`tests/test_policy.py` matches required phrases against whitespace-normalized
policy text, but asserts the removal of `Plan epoch` and `format-recovery`
against the raw string. A reintroduced term split across a line break would
pass. The removal assertions are the ones guarding against silent regression of
retired machinery, so they should be at least as strict as the positive ones.

Decision: normalize both directions.

### G4 — The two-verdict brake has no durable carrier

The `REVISE` and `REFUTED` caps are counted per readiness unit in main-session
context only. No artifact records the count, so context compaction silently
resets the brake, and the accompanying guarantees — the cap is not `READY`, and
cosmetic splitting cannot reset it — become unenforceable at exactly the point
where a long Plan is most likely to need them.

Decision: record the count against the stable unit ID in the Plan artifact, or
document the compaction reset as a known limitation in `docs/design.md`. The
documentation-only option is acceptable for this release; overstating the
brake's strength is not.

## Non-goals

- Re-litigating the envelope/slice model, the structured `REVISE` field set, or
  the security-review ordering introduced by PR #6.
- Changing the MultiAgentV2 transport, named-role model bindings, or live
  dispatch evidence.
- Retroactively tagging historical releases.

## Open decision — release number

PR #6 proposes `1.3.1` and notes the maintainer may renumber to `1.4.0`. Either
choice keeps installed copies correct because the policy stamp advances, so
this is a labeling preference, not a defect. `1.4.0` reads as the more honest
number: the release adds new policy semantics and a new installer capability.

Separately, repository tags stop at `v1.2.1` while `VERSION` reads `1.3.1`. If
`install/previous/<version>/` is to be auditable against a release, the missing
tags need to be created or the directory documented as the sole source of prior
canonical bytes.
