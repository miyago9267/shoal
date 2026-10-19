---
id: spec-hybrid-pilotfish-runtime
title: Hybrid Pilotfish runtime with always-on policy bootstrap and Plugin Skill
status: completed
created: 2026-08-10
updated: 2026-08-10
author: Miyago
priority: critical
tags: [installer, plugin, skill, policy, agents-md, roles, compatibility]
---

## Decision summary

Pilotfish 採用 Hybrid runtime：

1. active root `AGENTS.md` 或 `AGENTS.override.md` 放置短小的 Pilotfish
   always-on bootstrap block，確保安裝後核心 policy 立即生效。
2. Plugin 封裝並安裝 `pilotfish-orchestration` Skill，提供完整、可維護、可
   更新的 orchestration workflow。
3. native roles、hooks 與 config 繼續安裝到 Codex 已確認的 loader 路徑。
4. root bootstrap 與 Skill 必須語意一致；Skill 不可成為唯一的安全或 approval
   gate 來源。

目前沒有已確認的 `@file` instruction include contract，因此不把
`@pilotfish/AGENTS.md` 當成 loader。Plugin 保證 Skill 的安裝與可發現性；root
bootstrap 保證核心規則在 Skill 未載入、Plugin disabled 或版本不相容時仍存在。

## Goal

讓使用者安裝 Pilotfish 後立即得到可驗證的 orchestration 行為，同時：

- 保留 user Persona、語言、命名、Recap、安全與 project-local rules。
- 讓完整 workflow 以 Plugin／Skill 形式版本化與維護。
- 保留 user-owned extra roles。
- 只有同名 role、policy alias、ambiguous target、stale state 或 concurrent edit
  等嚴重 conflict 才停止並要求人工介入。
- 能在 fresh Codex session 中證明 bootstrap 與 Plugin／Skill 的 active 狀態。

## Non-goals

- 不重新設計 Codex instruction precedence。
- 不宣稱 Plugin／Skill 具有 host 未提供的 global instruction 優先權。
- 不把 user Persona 搬移到 Plugin 或 Skill。
- 不刪除 user-owned roles、hooks、config 或 policy bytes。
- 不以 role／hook approval 取代 policy integration 或安全 gate。

## Architecture

### Always-on bootstrap

Installer 在 active root instruction file 內維護唯一的
`pilotfish-codex:begin/end` block。此 block 應保持短小，只包含：

- Pilotfish 已啟用與核心 identity。
- 必須遵守的 approval、security、blocked-task 與 parent-accountability invariants。
- Plugin Skill 的 canonical name、版本檢查與使用條件。
- Skill 不可用時的 bounded fallback。
- 不得覆蓋 user Persona／Agent Rule 的 precedence boundary。

完整 routing vocabulary、decision tables、role briefs、verification contract
與 recovery workflow 移入 Skill，不在 root block 重複維護。

### Plugin package

Plugin 使用 Codex 支援的 manifest／installation mechanism，預期結構如下：

```text
plugin/
├── .agents/plugins/marketplace.json
└── plugins/pilotfish-codex/
    ├── .codex-plugin/
    │   └── plugin.json
    ├── skills/
    │   └── pilotfish-orchestration/
    │       ├── SKILL.md
    │       └── references/
    │           ├── role-contract.md
    │           ├── verification-contract.md
    │           └── recovery-contract.md
```

Plugin ownership 屬 Pilotfish；installer 必須使用 host 支援的 Plugin install
path，不得自行猜測一個會被 Codex 自動載入的 arbitrary directory。若 host
Plugin registry 不可用，installer 仍可安裝 native runtime 與 root bootstrap，
並將 Plugin 狀態標為 `unavailable`，不得宣稱 Skill active。

### Native runtime paths

| Artifact | Path | Ownership |
| --- | --- | --- |
| Pilotfish roles | `<CODEX_HOME>/agents/*.toml` | Pilotfish, same-name drift requires approval |
| Native config projection | `<CODEX_HOME>/config.toml` | Pilotfish-owned keys only |
| Hook registration | `<CODEX_HOME>/hooks.json` | structural co-ownership |
| Hook script | `<CODEX_HOME>/hooks/pilotfish_autoroute_gate.py` | Pilotfish |
| Always-on bootstrap | active root `AGENTS*.md` marker block | bounded shared file |
| Plugin | host-supported Plugin install path | Pilotfish |

### Cross-OS installer contract

| OS family | Public entrypoint | Backend | Plugin command resolution |
| --- | --- | --- | --- |
| macOS/Linux/WSL | `install/install.sh` | `install/install.py` | `codex` |
| Native Windows | `install/install.ps1` | `install/install.py` | `codex`, `codex.exe`, or `codex.cmd` |

Both wrappers support local checkout and pinned remote source selection, forward
the same installer options, and preserve the same dry-run/approval boundary.
Windows uses the native `commandWindows` hook form where available; policy,
roles, state, Plugin marketplace, and Skill semantics remain shared.

## Policy ownership and integration

Default install integrates the bootstrap block into the selected active root policy
file. It preserves every byte outside the block and records the original policy
SHA-256, installed block SHA-256, Plugin status/version and rollback backup path.

The installer rejects symlink, hard-link, both non-empty policy files, path escape,
malformed marker pairs, stale state and concurrent edits before writing. Empty homes
receive a newly created active root `AGENTS.md`.

## Role coexistence

- Valid extra user roles remain in `agents/` and do not block installation.
- Missing Pilotfish roles are created.
- Canonical Pilotfish role upgrades are allowed only with recorded provenance.
- Customized same-name roles remain unchanged and require explicit per-role
  replacement approval.
- Invalid TOML, duplicate names, symlink roles or filename/name mismatch are severe
  conflicts and stop before writes.

## Install states

| State | Meaning | Installer action |
| --- | --- | --- |
| `integrated` | root bootstrap active and Plugin installed/verified | normal update |
| `integrated-plugin-unavailable` | root bootstrap active, Plugin unavailable | report fallback |
| `requires-explicit-integration` | policy target cannot be safely changed | stop |
| `blocked-symlink` | policy alias detected | stop |
| `role-collision` | same-name or duplicate role conflict | stop |
| `stale` | previous state or target changed | stop |

## Verification contract

### Installer tests

- Existing Persona policy preserves every byte outside the managed block.
- Fresh home receives active root `AGENTS.md` and no arbitrary source-only claim.
- Plugin manifest and Skill files are installed at the host-supported path.
- Plugin unavailable produces `integrated-plugin-unavailable` without disabling
  the root bootstrap.
- Extra valid roles survive install and update byte-for-byte.
- Same-name customized roles require explicit replacement.
- Symlink, hard-link, ambiguous policy, stale state and concurrent edits leave all
  user policy bytes unchanged.
- Upgrade, downgrade, rollback, CRLF, UTF-8 and Windows path cases are covered.

### Fresh-session probe

Use a new `codex exec` process, never `resume`, in an isolated temporary home:

1. Verify the root bootstrap marker produces deterministic probe behavior.
2. Verify the Plugin is discoverable and the Skill name/version is available.
3. Verify a routing task follows the Pilotfish contract without requiring the user
   to paste or mention the Skill.
4. Verify user Persona and Recap rules remain effective.

Report separately: `bootstrap=active`, `plugin=installed|unavailable`,
`skill=available|unavailable`, and `pilotfish_behavior=verified|unverified`.

## Migration and rollback

1. Detect current policy path, managed marker, sidecar, Plugin version and role
   provenance.
2. Dry-run all policy, Plugin and native runtime changes before writes.
3. Keep user policy backup and Pilotfish-owned Plugin/runtime backups separate.
4. Restore only exact Pilotfish-owned artifacts whose current bytes still match
   the transaction output; never overwrite an independently changed user policy.
5. Downgrade must retain a compatible bootstrap contract or stop with a recovery
   report.

## Tasks

- [x] T1 — Split the full orchestration template into minimal always-on bootstrap
  and Skill-owned workflow content.
- [x] T2 — Create Plugin manifest and `pilotfish-orchestration` Skill package.
- [x] T3 — Define host-supported Plugin installation and discovery probe via the
  Codex local marketplace plus `codex plugin add` contract.
- [x] T4 — Extend installer state schema with bootstrap ownership and Plugin
  name/version/source digest/status; Skill availability is represented by the
  host Plugin result and never inferred from source presence alone.
- [x] T5 — Install/update bootstrap, Plugin and native runtime transactionally;
  Plugin installation is attempted after native target commit and its verified
  outcome is published as an explicit fallback or integrated state.
- [x] T6 — Preserve extra roles and require explicit same-name role replacement.
- [x] T7 — Add migration, upgrade, downgrade, rollback and concurrent-edit tests;
  committed state now includes exact Pilotfish-owned rollback backup names.
- [x] T8 — Add fresh-session activation and Persona/Recap regression probes via
  `install/probe_hybrid_runtime.py`; Plugin/Skill availability remains separate.
- [x] T9 — Update INSTALL, runbook, CHANGELOG and recovery documentation.

## Files likely affected

- `install/install.py`
- `install/install.ps1`
- `install/stage_smoke_home.py`
- `templates/agents-md.bootstrap.md`
- `templates/agents-md.orchestration.md`
- `plugin/.agents/plugins/marketplace.json`
- `plugin/plugins/pilotfish-codex/.codex-plugin/plugin.json`
- `plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/SKILL.md`
- `plugin/plugins/pilotfish-codex/skills/pilotfish-orchestration/references/*`
- `tests/test_install.py`
- `tests/test_plugin.py`
- `tests/test_live_policy_activation.py`
- `INSTALL.md`
- `install/AGENT-INSTALL.md`
- `CHANGELOG.md`

## Release classification

Minor if policy bytes outside the managed block remain preserved, Plugin is additive,
and rollback is exact. Major if users must reorganize policy files, lose active
behavior, or the supported Codex loader contract changes incompatibly.

## Related

- `docs/specs/policy-install-isolation/SPEC.md`
- `docs/WORK-STATUS.md`
