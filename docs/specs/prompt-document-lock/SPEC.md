---
title: Prompt and document lock
status: complete
created: 2026-09-14
updated: 2026-10-05
---

<!-- markdownlint-disable MD025 -->

# Prompt and document lock

## Goal

Keep future changes to agent prompts, role descriptions, and orchestration
policy text small, reviewable, and semantically anchored.

## Scope

- Protect the runtime prompt surfaces under `templates/`, `plugin/`, and the
  install prompt (Codex, 16 surfaces), and the Claude host runtime prompts
  under `hosts/claude/dist/` (11 surfaces). 27 surfaces in total.
- Enforce per-surface change budgets against the Git base revision.
- Require stable behavior anchors and exact synchronization of duplicated
  policy files.
- Run the lock in local validation and the Python CI workflow.

General README and historical report prose remains outside the lock.

## Decisions

- The lock is a repository contract, not a runtime permission switch.
- A first lock introduction may establish the baseline while the manifest is
  absent from the base revision; later changes use the declared budgets.
- The lock manifest is immutable during normal changes. Intentional policy
  renewal requires the explicit `--allow-lock-update` validator mode and human
  review.
- The manifest is schema v2. Every surface declares a required `version_file`
  (`hosts/<host>/VERSION`) naming the version file of the host that owns it.
  The validator rejects a surface whose `version_file` is missing or is not of
  that form.
- The version gate is per host. A change to a protected surface requires a
  change of that surface's own `version_file` against the Git base; the
  repository-root `VERSION` is no longer consulted. Codex surfaces map to
  `hosts/codex/VERSION` and Claude surfaces to `hosts/claude/VERSION`. The
  failure message names the version file and the changed surfaces. The manifest's
  `version_gate` keeps only `require_change_for_protected_surfaces`.
- Lock renewal (adding surfaces or editing `LOCK.json`) needs
  `--allow-lock-update` and human review. CI turns the flag on through exactly
  two paths: a pull request carrying the label `lock-renewal`, or a push to
  `main` whose head commit message has a line `Lock-Renewal: approved`. Neither
  relaxes the budgets or the version gate of existing surfaces; without the
  label or trailer a `LOCK.json` change stays red.
- The Claude host `hosts/claude/dist/agents/*.md` (8 files, 7 core-rendered plus
  `Explore`) and `skills/pilotfish-orchestration/` (`SKILL.md` plus 2
  references) are protected. `hosts/claude/dist/claude-md.bootstrap.md` and
  `settings.snippet.json` are not installed and stay outside the lock. Three
  surfaces (`executor`, `mech-executor`, `security-executor`) use
  `max_change_ratio` 0.35, the validator's hard ceiling, see
  `docs/specs/claude-eval-parity/SPEC.md` Decision 2.
- Budgets measure both changed lines and changed characters. Absolute file-size
  limits and required fragments provide a second boundary when a Git base is
  unavailable.
- `templates/agents-md.orchestration.md` and the packaged policy reference must
  remain byte-identical.

## Contract

The validator must fail when any protected surface is missing, exceeds its
absolute size limit, loses a required fragment, exceeds its base diff budget,
or diverges from its declared mirror. It must report the surface and metric
that caused the failure without printing prompt contents.

## Tasks

- [x] Add the lock manifest and validator.
- [x] Add regression tests for pass, budget failure, manifest drift, and mirror
  drift.
- [x] Add the validator to the Python CI workflow and documentation.
- [x] Verify the complete suite and record the milestone.

## Files

- `docs/specs/prompt-document-lock/LOCK.json`
- `install/validate_prompt_lock.py`
- `tests/test_prompt_document_lock.py`
- `.github/workflows/python-tests.yml`
- `hosts/codex/VERSION`, `hosts/claude/VERSION`

## Stop condition

The lock is complete when the validator passes for the current rc.4 sources,
rejects an oversized protected-surface diff in tests, and runs in CI for pull
requests and pushes.

## Local verification

```text
python install/validate_prompt_lock.py --base-ref HEAD
python -m unittest tests.test_prompt_document_lock -v
```

The rc.4 sources passed the lock with 15 protected surfaces; the full offline
suite then passed with 424 tests and 1 skipped; Markdown lint, Python syntax,
native agent validation, hook self-test, mirror comparison, and `git diff
--check` also passed.

After Phase B0 of `claude-eval-parity` (2026-10-05) the lock has 27 protected
surfaces: 16 Codex and 11 Claude. The offline suite passes with 865 tests and
1 skipped.
