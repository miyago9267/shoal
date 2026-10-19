---
id: spec-policy-install-isolation
title: Isolate Pilotfish policy installation from user-owned Agent Rules
status: superseded
created: 2026-08-10
updated: 2026-08-10
author: Miyago
priority: critical
tags: [installer, policy, agents-md, persona, compatibility, migration, safety]
---

> Superseded by [`hybrid-pilotfish-runtime/SPEC.md`](../hybrid-pilotfish-runtime/SPEC.md).
> Retained as historical evidence for policy ownership and migration constraints.

## Decision summary

Pilotfish 不應把 orchestration policy 直接寫入既有的使用者 `AGENTS.md` 或
`AGENTS.override.md`。目前 installer 雖然只替換自己的 marker 區塊，但仍會
修改使用者檔案；若該檔案是 symlink，還會直接修改 symlink target。這個行為
可能改變 Persona、Agent Rule 的有效優先順序，也可能覆寫 marker 內的使用者
自訂內容。

本 spec 的安全預設是：Pilotfish 自動管理自己的 roles、hooks 與 config；對
既有 instruction policy 只做偵測、報告與明確 opt-in，不做 silent merge。

## Goal

建立清楚的 ownership boundary，使 Pilotfish 更新、重裝、降版或 migration 時：

1. 不刪除、不替換、不重排使用者的 Persona、語言、Recap 或 Agent Rule。
2. 不透過 symlink、hard link 或其他路徑別名繞過 ownership 判斷。
3. 不讓 Pilotfish 的 policy 以未明示的優先順序蓋過使用者規則。
4. 仍能可靠安裝與驗證 Pilotfish 的 roles、hooks、config 與核心 runtime。
5. 讓使用者知道 orchestration policy 是否已套用、如何套用與如何回復。

## Non-goals

- 不重新設計 Codex 的 instruction precedence。
- 不保證 arbitrary `~/.codex/pilotfish/*.md` 會被 Codex 自動載入；除非 Codex
  提供正式 include／instruction-file 入口，否則專用檔案只作為人工整合來源。
- 不自動搬移、重寫或整理使用者既有 Persona／Agent Rule。
- 不以 `AGENTS.override.md` 作為繞過使用者同意的寫入位置。
- 不因隔離 policy 而弱化 mandatory review、permission、security 或外部操作
  gate。

## Current behavior and root cause

目前 `install/install.py`：

- 透過 `active_instruction_file()` 選擇 `AGENTS.override.md` 或 `AGENTS.md`。
- 以 `merge_instruction_text()` 在該檔案追加或替換
  `pilotfish-codex:begin/end` marker。
- 以一般檔案寫入流程處理該 path，未將 symlink target 視為不同 ownership。

這使 installer 能保留 marker 外的 bytes，卻仍然直接修改使用者 policy。若
使用者把 `~/.codex/AGENTS.md` symlink 到 dotfiles repository，更新 Pilotfish
會修改 dotfiles 的 tracked source。即使沒有資料遺失，較後插入的 Pilotfish
規則仍可能在語意衝突時影響 Persona、語言與回覆格式。

## Ownership model

| Path / object | Owner | Default installer action |
|---|---|---|
| `agents/*.toml` | Pilotfish, subject to drift approval | install / update |
| `hooks/pilotfish_*` | Pilotfish | install / update |
| Pilotfish-owned config keys | Pilotfish | merge only owned projection |
| existing `AGENTS.md` | User | read / fingerprint / report only |
| existing `AGENTS.override.md` | User | read / fingerprint / report only |
| symlink or hard-link policy target | User / external owner | never write by default |
| active root policy marker block | Pilotfish | install / update only in the selected active policy file |
| new policy file on an empty home | Pilotfish, with explicit mode | may create |

"User-owned" means any pre-existing instruction file, regardless of whether its
contents currently contain a Pilotfish marker. A marker alone is not sufficient
proof that the whole file is Pilotfish-owned.

## Required behavior

### R1 — Existing policy preserves user bytes outside the managed block

If an active `AGENTS.md` or `AGENTS.override.md` exists and is non-empty, the
installer may append or replace only the bounded Pilotfish marker block. It must
preserve every byte outside that block, even when:

- it contains an old or current Pilotfish marker;
- the file is byte-identical to a previously installed Pilotfish policy;
- the installer is invoked with `--replace-drifted-roles`;
- the file is a symlink to a repository-managed file.

The installer may read it, compute a fingerprint, detect a Pilotfish marker, and
report a migration or integration action. Role replacement approval must never
implicitly approve instruction-file replacement.

### R2 — Empty-home bootstrap is automatic and bounded

On a Codex home with no non-empty `AGENTS.md` or `AGENTS.override.md`, the
installer creates the active root `AGENTS.md` with a managed marker. The state
sidecar records the Pilotfish integration and the empty original bytes.

The default runtime mode installs native runtime components and integrates the
Pilotfish policy into the selected active root policy file. Bytes outside the
managed marker block remain user-owned and unchanged. Symlink, hard-link, or
ambiguous policy targets stop before any write.

### R3 — Symlink and alias safety

Before any policy write, reject:

- `AGENTS.md` or `AGENTS.override.md` symlinks;
- hard-linked policy files when link identity can be determined;
- a policy path whose parent or target resolves outside the intended Codex home;
- both non-empty policy files being present.

The error must identify the safe reason and the read-only alternatives. It must
not silently follow the link, unlink it, or replace it.

### R4 — Policy integration is automatic and bounded

When an existing policy is found, dry-run output must report one of:

- `policy=integrated` — the bounded Pilotfish marker is active in the selected
  root policy file;
- `policy=requires-explicit-integration` — ownership or path safety prevents
  automatic integration;
- `policy=blocked-symlink` — policy path is an alias and cannot be written.

Symlinks, hard links, ambiguous policy targets, stale state, and concurrent edits
must stop before writing and state the exact target, backup behavior, ownership
effect, and rollback path. Role or hook approval does not authorize bypassing
these policy safety checks.

### R5 — Managed policy must not outrank user identity accidentally

If an explicit integration mode remains supported, the generated integration must
place Pilotfish policy in a clearly delimited section and document precedence.
User Persona, language, naming, recap, safety and project-local rules must remain
the authoritative user-facing layer unless the user explicitly chooses otherwise.

The installer must never claim that marker preservation alone guarantees semantic
preservation; acceptance must include conflicting-rule tests.

### R6 — Dedicated files require a real loader

Pilotfish may store its policy at a dedicated path such as
`<CODEX_HOME>/pilotfish/AGENTS.md`, but it must not claim the policy is active unless
Codex's supported instruction-loading mechanism actually loads that file. If no
loader exists, the installer must label it `source-only` and provide a manual
integration snippet rather than silently relying on an unsupported convention.

### R7 — Upgrade, downgrade and uninstall safety

Every transition must preserve user bytes outside an explicitly Pilotfish-owned
file. A failed migration must leave the original policy unchanged. Rollback must
restore the exact prior Pilotfish-owned artifact and must not restore a backup over
an independently changed user file.

Existing installations that already contain a Pilotfish marker require a migration
report. Migration must not assume that marker contents are the only user changes;
it must compare recorded original bytes, current bytes and ownership evidence before
offering any repair.

## Proposed install modes

| Mode | Roles / hooks / config | Existing policy | New empty policy | Intended use |
|---|---|---|---|---|
| `runtime` (default) | install | read-only, preserve | do not create | safest normal install/update |
| `runtime-with-policy` | install | stop for explicit integration | create managed policy | deliberate opt-in |
| `policy-source-only` | install | preserve | write under `pilotfish/` only | manual integration / inspection |
| `repair-policy` | no unrelated replacement | only after ownership proof | explicit confirmation required | recovery of known Pilotfish-owned file |

The final CLI names may differ, but the ownership semantics must remain unchanged.

## Migration plan for current v1.6.x installs

1. Detect the active policy path, symlink status, marker pair, install sidecar and
   recorded original bytes.
2. Produce a dry-run report without writing the policy.
3. Keep roles, hooks and owned config migration independent from policy migration.
4. If ownership is unproven, mark policy migration `requires-explicit-integration`
   and leave the file untouched.
5. If ownership is proven for a fully Pilotfish-created file, move or retain it
   as a dedicated managed artifact only with explicit migration approval.
6. Preserve a checksum and timestamped backup for every Pilotfish-owned artifact.
7. Never auto-revert a user policy merely because it differs from the installed
   marker or from a prior Pilotfish version.

## Security and failure model

The installer must fail closed for ambiguous ownership, path aliasing, concurrent
changes, malformed marker pairs, stale state, missing backup evidence and both
policy files being active. It must not use `realpath()` as permission to write the
resolved target; realpath is evidence for rejection and diagnostics.

Sensitive prompt content, Persona text and full policy contents must not be copied
into logs or telemetry. Reports may include paths, byte counts, hashes and bounded
reason codes.

## Acceptance criteria

- Installing or updating Pilotfish against a pre-existing regular `AGENTS.md`
  preserves every byte outside the managed Pilotfish marker block.
- The same holds for `AGENTS.override.md`.
- A symlinked `AGENTS.md` causes a clear `blocked-symlink` result and no target
  write.
- A hard-linked policy path is rejected when detectable.
- Existing Persona, `Miyago` naming, Traditional Chinese and Recap rules remain
  byte-identical and behaviorally effective after roles/hooks/config update.
- A marker inside a user-owned file is not treated as proof of full-file ownership.
- Valid user-owned roles outside Pilotfish's role names are preserved and do not
  block installation.
- A customized same-name Pilotfish role remains unchanged unless its exact role
  is explicitly approved for replacement.
- An empty home can install a managed policy only in explicit policy mode.
- A policy block in the active root `AGENTS.md` is reported as active only after
  a fresh-session probe confirms root `AGENTS.md` loading.
- Role drift approval cannot modify any policy file.
- Interrupted install, concurrent policy edit and stale state leave user policy
  unchanged.
- Upgrade, downgrade and rollback tests cover regular files, symlinks, hard links,
  CRLF files, UTF-8 content and dotfiles-style symlink targets.
- macOS, Linux/WSL and native Windows run the same ownership and dry-run tests.
- Documentation explains policy status, explicit integration, backup, rollback and
  how to keep custom Persona／Agent Rule authoritative.

## Version classification rubric

The following rubric is part of the release decision, not an implementation detail.

### Patch candidate

Only a patch if the change is a fail-safe correction that does not change the
successful install contract for existing users, for example:

- reject symlink policy writes;
- stop before a dangerous write and require operator resolution;
- fix backup, fingerprint or rollback validation;
- add tests and diagnostics while preserving explicit existing policy behavior.

### Minor candidate

Use a minor release if the default changes from automatic policy merge to safe
runtime-only installation, but roles/hooks/config remain compatible and users can
explicitly opt in to policy integration. This adds install modes and a migration
report without requiring a breaking runtime API change.

### Major candidate

Use a major release if any of these are true:

- existing installations lose an active Pilotfish policy without an explicit
  migration action;
- the supported instruction-loading contract changes incompatibly;
- users must manually reorganize existing AGENTS files to retain behavior;
- the installer no longer supports a previously documented install path or CLI
  contract;
- rollback cannot preserve the previous effective policy on all supported platforms.

The recommended target is **minor**, provided `runtime` remains compatible for
roles/hooks/config and existing policy is preserved with an explicit migration
notice. It becomes **major** only if the migration removes or silently changes the
effective policy of existing installations.

## Tasks

- [x] T1 — Define the ownership/state schema for managed policy versus user policy.
- [x] T2 — Add runtime-only default install mode with an active managed policy block.
- [ ] T3 — Reject symlink, hard-link and ambiguous policy targets before any write.
- [x] T4 — Decouple role/hook/config installation from instruction policy migration.
- [ ] T5 — Add migration and dry-run reason codes without logging policy contents.
- [ ] T6 — Add upgrade, downgrade, rollback and concurrent-edit coverage.
- [ ] T7 — Add macOS, Linux/WSL and Windows path/line-ending integration tests.
- [ ] T8 — Update install docs, release notes and operator recovery instructions.
- [ ] T9 — Decide release class using the rubric above after migration behavior
  is implemented and tested.

## Files likely affected

- `install/install.py` — policy ownership, modes, symlink rejection and migration.
- `install/stage_smoke_home.py` — staged-home allowlist and policy state.
- `install/AGENT-INSTALL.md` and `INSTALL.md` — user-facing install contract.
- `tests/test_install.py` — install ownership and migration tests.
- `tests/test_stage_smoke_home.py` — staged policy safety tests.
- `tests/test_verify_dispatch.py` — policy discovery and parity tests.
- `templates/agents-md.orchestration.md` — only if policy is retained as an
  explicit source artifact; do not move user Persona content into this template.
- `CHANGELOG.md` — migration and compatibility notes.

## Rollback

Until the new ownership model has passed cross-platform migration tests, do not
change the default installer behavior in a release branch. A failed implementation
must be reverted to the last verified installer commit while preserving current
user policy bytes. Never use a broad restore over a symlink or an independently
modified policy file.

## Related

- `docs/specs/review-block-deduplication/SPEC.md`
- `INSTALL.md`
- `install/install.py`

## Notes

The current v1.6.2 installation is evidence for this spec:
`~/.codex/AGENTS.md` is a symlink to a dotfiles-managed file, and the Pilotfish
marker update modified the
target file. The custom content was retained in this instance, but the write
boundary remains unsafe and must be treated as a compatibility issue.
