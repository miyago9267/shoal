# Shoal-Codex installation playbook（shoal 的 Codex host 安裝說明）

This playbook is for an AI agent installing the native Shoal-Codex target.
Read it completely before running an installation command. The detailed
ownership and migration rules are in
[`install/AGENT-INSTALL.md`](install/AGENT-INSTALL.md); this playbook does not
replace that runbook.

## Scope and prerequisites

The installer changes one Codex home. The default is `~/.codex`; set the
`CODEX_HOME` environment variable or pass `--codex-home` to select another
home. It installs the
native shoal roles, the active bootstrap block in the selected root
`AGENTS.md`, the `shoal-codex` Plugin/Skill through Codex's local
marketplace contract, native config, and the shoal hook registration and
script. It does not install an
adapter, change shell startup files, manage credentials, or use `sudo`.

Before any run, confirm all of the following:

- Codex CLI is `>=0.147.0` (one bare version token; a suffix or an ambiguous
  `--version` result is not accepted; the installer enforces this floor, newer
  releases are expected to work).
- Python is `3.11` or newer.
- A local POSIX checkout has Bash and Python; a native Windows checkout has
  PowerShell and Python. No network tools are needed for the local path.
- A remote POSIX path additionally needs `curl`, `tar`, `mktemp`, and network
  access to `github.com`; a remote PowerShell path uses
  `Invoke-WebRequest` and `tar`. The remote archive is selected by a visible
  ref.
- The POSIX entrypoint is `install/install.sh`; the native Windows entrypoint is
  `install/install.ps1`; the actual installer remains `install/install.py`.
  `--ref` belongs to either wrapper and must not be passed to `install.py`.

Do not print or copy `auth.json`, tokens, API keys, or other credentials while
inspecting the home.

## Optional Astra main-session mode

The installer keeps the default root Luna/Plan and Sol review policy. The
automatic route may use the installed strong `executor`/`verifier` bindings.
To opt into Astra for the root session itself, start Codex with launch-time
overrides instead of editing `config.toml`. `<strong-model>` is the model your
Codex binding resolves for the strong tier; see
`python3 tools/render.py --host codex --explain`.

```bash
codex --model <strong-model> \
  -c model_reasoning_effort="high" \
  -c plan_mode_reasoning_effort="high" \
  -c agents.max_concurrent_threads_per_session=1
```

This activation is zero-write and session-only. The prompt keeps Astra on
synthesis, planning, and difficult judgment; delegates mechanical work to
Luna; and preserves `plan-critic` on Sol/high plus all approval and security
gates. `max_tool_calls=12` and `max_wall_seconds=300` are advisory limits, not
a provider-enforced quota. An invalid override or unavailable Astra model must
fail closed before task work; start a new session without the flags to return
to the normal policy. No installer option enables this mode by default.

## Confirmation boundary

The agent may fetch this playbook, inspect source, check versions, read the
documented configuration files, and run `--help` or `--dry-run` without
approval. A remote dry-run downloads a pinned archive into the installer's
private temporary directory; it does not write the Codex home.

Stop immediately after the dry-run and before any real install command that
targets the selected home. Show the user:

- the absolute Codex home path;
- the selected source and ref;
- every `would change primary:` path;
- the policy and hook changes;
- existing files that will receive a timestamped
  `*.shoal-codex-<timestamp>` backup; and
- any role drift, extra role, pending transaction, or unresolved hook
  registration ownership that caused an abort.

Ask for explicit approval to back up and write that home. Approval must name
the path and does not authorize replacing customized same-name roles,
deleting residual roles, changing credentials, or using elevated privileges.
If the user does not approve, stop with no install command.

## Inspect before execution

From a checkout, inspect both the thin shell wrapper and the detailed runbook
before invoking the wrapper:

```bash
sed -n '1,220p' install/install.sh
sed -n '1,260p' install/AGENT-INSTALL.md
bash install/install.sh --help
```

For a remote-only run, fetch `INSTALL.md` and the shell entrypoint from the
same pinned ref, then inspect the unpacked `install/AGENT-INSTALL.md` and
`install/install.sh` before proceeding. Do not silently substitute `main` for a
requested pinned ref.

Check the prerequisites and select the target home without changing it:

```bash
python3 --version
codex --version
SHOAL_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
printf 'target home=%s\n' "$SHOAL_TARGET_HOME"
```

Inspect only the managed inputs. Preserve unrelated config and custom role
files; do not read credentials:

```bash
if [ -f "$SHOAL_TARGET_HOME/config.toml" ]; then
  sed -n '1,240p' "$SHOAL_TARGET_HOME/config.toml"
fi
for policy in "$SHOAL_TARGET_HOME/AGENTS.md" "$SHOAL_TARGET_HOME/AGENTS.override.md"; do
  if [ -s "$policy" ]; then
    printf '\n--- %s ---\n' "$policy"
    sed -n '1,260p' "$policy"
  fi
done
if [ -d "$SHOAL_TARGET_HOME/agents" ]; then
  find "$SHOAL_TARGET_HOME/agents" -maxdepth 1 -type f -name '*.toml' -print
fi
```

If both policy files are non-empty, or if a pending state sidecar exists, stop
for operator resolution before a dry-run. The detailed runbook defines the
legacy migration and ownership evidence that must remain intact.

## Dry-run

Use one of these entrypoints. Local checkout is always the first source choice
when the shell script is executed from a valid checkout.

Local checkout:

```bash
SHOAL_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
bash install/install.sh --dry-run --codex-home "$SHOAL_TARGET_HOME"
```

Native Windows PowerShell:

```powershell
$shoalHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
.\install\install.ps1 --dry-run --codex-home $shoalHome
```

Pinned remote source (replace the placeholder with an exact published tag or
full commit SHA; do not run the placeholder itself):

```bash
SHOAL_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
SHOAL_REF='<release-tag-or-commit-sha>'
curl -fsSL \
  "https://raw.githubusercontent.com/miyago9267/shoal/${SHOAL_REF}/install/install.sh" \
  | bash -s -- --ref "$SHOAL_REF" --dry-run \
    --codex-home "$SHOAL_TARGET_HOME"
```

Note: pinned refs before v1.0.0 (v1.8.1 and earlier) exist only in
`miyago9267/pilotfish-codex`; use that repository name in the URL for them.

If the active home has a dotfiles-managed `AGENTS.md` or `hooks` symlink that
points outside the home, use the isolated role path instead of integrating the
full target:

```bash
bash install/install.sh --dry-run --roles-only \
  --codex-home "$SHOAL_TARGET_HOME"
bash install/install.sh --roles-only \
  --codex-home "$SHOAL_TARGET_HOME"
```

`--roles-only` writes only the `agents/*.toml` role files. It leaves policy,
config, hooks, Plugin, and installer state untouched; existing same-name role
customizations still require an explicit replacement option.

`--ref=<release-tag-or-commit-sha>` is equivalent to the two-argument form.
Keep the raw script URL ref and the archive ref identical. `SHOAL_REF` is
only the wrapper fallback when `--ref` is omitted. The wrapper prints
`selected source:` and `selected ref:` before a remote fetch.

A successful dry-run prints `would change primary:` lines and allowed state,
backup, and pending-artifact names, or says that the target is already up to
date. It must not create those artifacts. A failed dry-run is a stop signal;
resolve its ownership or state error rather than weakening the installer.
When the host Plugin registry is unavailable, the native runtime still installs
but the committed state records Plugin status as `unavailable`; this is a
fallback, not proof that the Skill is active.

## Install after approval

After the user approves the exact home and planned writes, rerun the same
source and ref without `--dry-run`.

Local checkout:

```bash
SHOAL_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
bash install/install.sh --codex-home "$SHOAL_TARGET_HOME"
```

Native Windows PowerShell:

```powershell
$shoalHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
.\install\install.ps1 --codex-home $shoalHome
```

Pinned remote source:

```bash
SHOAL_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
SHOAL_REF='<release-tag-or-commit-sha>'
curl -fsSL \
  "https://raw.githubusercontent.com/miyago9267/shoal/${SHOAL_REF}/install/install.sh" \
  | bash -s -- --ref "$SHOAL_REF" \
    --codex-home "$SHOAL_TARGET_HOME"
```

The wrapper forwards only installer arguments such as `--dry-run`,
`--roles-only`, and `--codex-home`; it consumes `--help` and `--ref`. It
validates a remote ref before constructing the codeload URL, uses no `eval` or
`sudo`, and removes only its own temporary directory.

If the active policy path is a symlink managed by the user's dotfiles, the
installer stops by default. After verifying the target, explicitly authorize
integration with `--follow-policy-symlink --policy-root <contained-root>`; this
preserves the symlink and writes only its regular-file target. A stale committed
policy fingerprint likewise stops by default. Use
`--reconcile-current` only after the dry-run confirms the current policy/config
are the intended source of truth; the resulting state version 4 records the
accepted preimages, target identity, previous sidecar digest, post-merge
fingerprints, and rollback paths. Plugin installation may update only its own
`plugins`/`marketplaces` entries; a foreign config mutation aborts.

## Validate and trust the hook

When a checkout is available, validate the installed config and role manifest:

```bash
python3 install/validate_agents.py \
  --config "$SHOAL_TARGET_HOME/config.toml" "$SHOAL_TARGET_HOME/agents"
```

The expected result is:
`all native shoal config and agent TOMLs valid`.
Also confirm that these managed hook files exist, without printing secrets:

```bash
test -f "$SHOAL_TARGET_HOME/hooks.json"
test -f "$SHOAL_TARGET_HOME/hooks/shoal_autoroute_gate.py"
test -f "$SHOAL_TARGET_HOME/hooks/shoal_guard.py"
grep -F 'Shoal automatic typed Plan-review gate.' \
  "$SHOAL_TARGET_HOME/hooks.json"
```

### Dispatch guard

Since host 1.8.3 the installer also registers the dispatch guard
(`hooks/shoal_guard.py --host codex`,
[`docs/specs/dispatch-enforcement`](./docs/specs/dispatch-enforcement/SPEC.md))
next to the autoroute gate. It is a separate script with its own projection ID
(`shoal-guard-v3`) and its own state entry (`guard_registration`), so the gate
is unchanged. It adds a `UserPromptSubmit` group that records the turn and
reads `#direct`, a `PreToolUse` group with matcher
`^(apply_patch|spawn_agent|collaborationspawn_agent|Bash)$`, and, since 3.4.0,
a `Stop` group for the completion check (below). The guard is in
enforce mode by default (`SHOAL_GUARD=shadow` logs `would_deny` and `advise`
records under `${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`;
`SHOAL_GUARD=off` disables it). The subagent rules (LEAF, VERIFY_EDIT) deny.
Since 3.3.0 the main-session edit rule is the same `strict` rule as on Claude
(`SHOAL_GUARD_R1=strict`, the default; 3.2.1 and 3.2.x defaulted to
`declare`): `apply_patch` and a `Bash` call that literally writes a file are
denied unless the turn has a dispatched write role or a standalone `#direct`
in the prompt (or `SHOAL_GUARD_DIRECT=1`). A declaration is no exit in
`strict`. The earlier `declare` rule (exit: a `Bash` call that is exactly `:
shoal-direct "<reason>"`; see the Claude guard section below), the
reminder-only `SHOAL_GUARD_R1=classified` and `SHOAL_GUARD_R1=off` stay
selectable. R2 still only reminds. The background-shell rule G4 does not exist
on Codex (its shell calls carry no `run_in_background`). The rule is built on
a recorded payload of Codex CLI 0.160.1: the shell tool is `Bash` with
`tool_input.command`, the same `turn_id` is on the prompt and tool events, and
main-session calls have no `agent_id` (keys and types:
`tests/fixtures/codex_payload_shapes.json`;
[`docs/specs/guard-declared-direct/PROGRESS.md`](./docs/specs/guard-declared-direct/PROGRESS.md)).
A foreground `Bash` call that neither declares nor writes a file gets no
opinion and writes no log line (after a change in the turn it records that a
check ran, see the completion check below). An existing home that predates the
guard gains the script and all three groups on the next install; a home
registered by 3.3.x or earlier is upgraded in place: `shoal-guard-v1` (3.2.0 or
earlier, matcher without `Bash`) has its `PreToolUse` group replaced at the same
position, and both `v1` and `v2` (3.2.1 to 3.3.1) gain the guard's own `Stop`
group, appended after the existing `Stop` entries. Every other entry (your own
`Bash` matcher, your own `Stop` hook, the autoroute gate's own `Stop` group) is
left untouched. Re-runs change nothing. The installer does not write hook
trust: after installing **or upgrading to 3.4.0**, approve the new `Stop` hook
once in an interactive Codex session with `/hooks`, as for the autoroute gate.
Without that approval Codex does not run it and the completion check never
fires (nothing else changes). A `PreToolUse` group that is not re-approved
after an upgrade from `v1` leaves the guard blind to `Bash` (declarations then
have no way in, so keep `#direct` and dispatch in mind until you approve).
Dispatch unlocks at the `spawn_agent` call itself: Codex has no
recorded event that proves the role started, so a role that fails to start
still unlocks the turn (docs/specs/guard-declared-direct, M11). A launch probe
(must exit 0, prints nothing):

```bash
echo '{}' | /usr/bin/env python3 "$SHOAL_TARGET_HOME/hooks/shoal_guard.py" --host codex
```

#### Completion check

Since 3.4.0 the guard records, per turn, whether the main session changed files
and whether anything checked the change afterwards (docs/specs/shared-rules,
B2 to B4). A change is a non-exempt `apply_patch` or `Bash` file write that the
guard allowed, or a dispatched write-level role (`executor`, `applier`,
`security-executor`, `sol-executor`; on Codex the dispatch call counts). A check
is a dispatched `verifier` or `watcher`, or a foreground `Bash` call that is
neither a file write nor a `: shoal-direct` declaration, made after the latest
change; a later change clears it. When the main session ends the turn with a
change and no check, the `Stop` hook answers
`{"decision":"block","reason":"..."}` once per turn: run a verification, or say
in the report that the change is unverified. The block is skipped when Codex
reports `stop_hook_active` (the retry after a block), for a `Stop` of another
turn, for unreadable state or an unexpected payload, in `SHOAL_GUARD=shadow`
(the log gets `would_block`), with `SHOAL_GUARD=off`, and with
`SHOAL_GUARD_STOP=off`. The switch defaults to `on`, exists on Claude and Codex
only, and has no effect elsewhere: Grok, agy and OpenCode never block because
no end-of-turn payload of theirs is recorded. The autoroute gate's `Stop`
group (Plan review and model escalation) is a separate script and is not
changed.

#### Guard only, without running the installer

When `install/install.py` cannot be reconciled with the Codex home (for
example a locally modified `shoal_autoroute_gate.py` that the installer
would replace), `tools/install_hooks.py --host codex` manages only the guard.
It writes the same `shoal-guard-v3` groups (including `commandWindows`; a
`shoal-guard-v1` or `v2` group is replaced in place) into
`<codex-home>/hooks.json` and the committed-`HEAD` script to
`<codex-home>/hooks/shoal_guard.py` (0600). The codex home is `--home`, then
`CODEX_HOME`, then `~/.codex`. Dry-run is the default:

```bash
python3 tools/install_hooks.py --host codex           # dry-run
python3 tools/install_hooks.py --host codex --apply   # back up, then install
python3 tools/install_hooks.py --host codex --uninstall --apply
```

Only handlers whose command references `shoal_guard.py` are owned. The
autoroute gate, other hooks, `config.toml`, `AGENTS.md` and hook trust
(`hooks.state`) are never touched. Writes are idempotent and backed up under
`${XDG_STATE_HOME:-~/.local/state}/shoal/install-hooks/backups/`.
`--uninstall` removes only the owned entries and the script. Approve the new
hooks once with `/hooks` in an interactive Codex session. A later
`install/install.py` run adopts these exact entries instead of duplicating
them; once its state records the guard, `--uninstall` here refuses and the
installer must be used.

### Prove the hook can launch

Registration and trust do not prove that the registered command runs. A hook
whose interpreter is missing fails silently and open: no enforcement, and no
signal that enforcement is gone. Run the registered command's own launch probe
before trusting the result of any later gate check.

On macOS and Linux:

```bash
/usr/bin/env python3 \
  "$SHOAL_TARGET_HOME/hooks/shoal_autoroute_gate.py" --selftest
```

On native Windows, `python` is frequently the Microsoft Store alias stub, which
opens the Store instead of running the script. Run the probe through the same
command the `commandWindows` entry uses and require real output:

```powershell
uv run --no-project python -c "import os,runpy; from pathlib import Path; runpy.run_path(str(Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))/'hooks'/'shoal_autoroute_gate.py'), run_name='__main__')" --selftest
```

Both must print `shoal-autoroute-gate schema=<n> launchable`. Any other
result — no output, a Store window, `ModuleNotFoundError` — means the gate is
not enforcing anything on this machine. Fix the interpreter or record the gate
as unenforced; do not report the install as gated.

Trust the shoal registration once in an interactive Codex session. Inspect
the groups that run `hooks/shoal_autoroute_gate.py` and `hooks/shoal_guard.py`,
start Codex, and use
`/hooks` to review and trust it. A pre-existing user-level `hooks.json` can
have its own top-level description, so do not rely on one global description as
the registration identity. Codex records trust against the hook definition
hash; repeat this only when that definition changes. Do not use a bypass flag
for normal active-runtime work.

If the UI exposes trust only as a prompt while a session is starting, close
that session and start a fresh one. Approve the exact hook at session start,
then run `/hooks` in that session (or the next fresh session) to confirm the
trusted state. The resulting `[hooks.state]` entry is expected and does not
require reinstalling shoal.

For a remote-only install with no checkout, validate the same files from a
checkout or source archive at the exact installed ref. Do not fetch an
un-pinned validator or claim validation from a different ref.

## Safe rerun and update

Rerunning the same command at the same ref is intended to be idempotent. It
preserves unrelated config, custom same-name role bytes, user files, and
complete unrelated native hook groups. Shoal only owns its exact,
event-bound hook groups and its script. A sidecar-proven shoal script can
upgrade to the selected source; a changed, missing, duplicated, or unproven
shoal group or script stops the update. Run a new dry-run and obtain
approval again before changing to another visible tag or commit. Review every
changed role, policy, hook, and backup path before the real update.

The installer fails closed for customized role drift, malformed or ambiguous
hook registration, an unproven current or historical shoal group, extra
roles, malformed config, or stale transaction evidence. Do not force those
cases by deleting state or passing an unsupported option to `install.py`.

## Recovery and rollback

If an install aborts, stop. Preserve the error output, the pending or aborted
state sidecar, and every `*.shoal-codex-<timestamp>` backup. Do not rerun
over a pending transaction, delete unknown roles, or restore the whole home
blindly. After separate operator approval, copy the affected managed files and
state evidence to an explicitly chosen recovery directory; exclude credentials
unless the operator deliberately handles them.

The installer stages writes, creates backups before replacement, verifies
post-write fingerprints, and records committed ownership in a mode-`0600`
sidecar. Its isolated smoke candidate uses the clean shoal registration,
not any unrelated active-home hook group. If a concurrent edit is detected, the
installer preserves that content and leaves an aborted sidecar for operator
resolution. Use those records and
[`install/AGENT-INSTALL.md`](install/AGENT-INSTALL.md) to decide a targeted
restoration. A customized same-name role or an unproven shoal hook group
requires an explicit operator decision; this playbook does not authorize
deletion or an uninstall shortcut.

## Final report

Report all of the following in the agent's completion message:

- selected source, exact ref, and absolute target home;
- dry-run result and real install result, including whether it was already
  up to date;
- validation command and its output;
- changed primary paths and exact backup/state paths, if any;
- hook trust result, including whether a fresh session-start prompt was used;
- preserved or unresolved custom roles, extra files, and pending state; and
- confirmation that no credentials, shell startup files, or elevated
  privileges were used.

## Grok Build

The Grok Build host is installed by `tools/install_grok.py`, not by the Codex
installer above. It installs what is committed at `HEAD` of a shoal checkout:
`agents/`, `roles/`, `rules/shoal-grok.md`, and the native hooks
(`hooks/shoal-grok.json` plus `hooks/shoal-grok/`) under the Grok home.
The default home is `$GROK_HOME`, else `~/.grok`; pass `--grok-home DIR` to
select another. The installer is Python 3.11 or newer and needs `git`.

Every command that writes (install, `--restore`, `--uninstall`) is a dry-run
until `--apply` is given. The installer opens only the paths it manages and
`config.toml`; it does not read credentials, sessions or history, and does not
touch `~/.claude`.

```bash
# 1. Dry-run: lists files to add, replace or skip, and flags config problems.
python3 tools/install_grok.py

# 2. Install after the user approves the dry-run output.
python3 tools/install_grok.py --apply

# Roll back one install from its backup directory.
python3 tools/install_grok.py --restore ~/.grok/backups/shoal-<timestamp> --apply

# Remove only the files shoal installed (config.toml is not modified).
python3 tools/install_grok.py --uninstall --apply
```

Before the first write it copies every file it will replace, plus
`config.toml`, to `<grok-home>/backups/shoal-<timestamp>/`. After installing it
checks that each file has the same SHA-256 as the committed dist and that the
rules marker matches `hosts/grok/VERSION`; a mismatch exits 1.

If `[subagents.toggle]` in `config.toml` sets a shoal role (`scout`,
`plan-critic`, `security-reviewer`, `applier`, `executor`, `verifier`,
`security-executor`) to `false`, the dry-run flags it and nothing is changed.
`--fix-toggles` deletes exactly those lines and keeps every other byte; it
aborts without writing if the table cannot be edited that way (for example
inline or dotted keys). Other `config.toml` keys, including the Claude
compatibility cells in `config.snippet.toml`, are not managed by this
installer; merge them by hand.

The hooks add a `SubagentStop` format gate for `verifier`, `plan-critic` and
`security-reviewer`, and a `PreToolUse` guard that denies write-capable
`spawn_subagent` calls while Grok is in plan mode. They also install the shoal
dispatch guard (`hooks/shoal-grok/shoal_guard.py`) with a `UserPromptSubmit`
entry and a `PreToolUse` entry (matcher `^(search_replace|spawn_subagent)$`), shadow
mode by default; the existing plan-mode guard entry is kept. The copy in
`hosts/grok/dist` is generated from `hooks/shoal_guard.py` by
`python3 tools/render.py --host grok --write`, and the installer aborts if the
dist copy
differs from the same commit's `hooks/shoal_guard.py`. Grok runs the hook path directly,
so the host comes from the hook's `env` (`SHOAL_GUARD_HOST=grok`) instead of `--host`.
Start a new Grok session after installing: agents, rules and hooks are read at session
start.

## Claude Code 與 Gemini/agy 的 dispatch guard

Claude Code 與 Gemini/agy 沒有自己的 shoal installer，dispatch guard 由
`tools/install_hooks.py` 安裝（Python 3.9 以上，需要 `git`）。和 `install_grok.py`
一樣，沒有 `--apply` 一律是 dry-run。

```bash
# 1. Dry-run：列出腳本與 settings 的變更，不寫入。
python3 tools/install_hooks.py --host claude

# 2. 使用者核准 dry-run 後安裝。
python3 tools/install_hooks.py --host claude --apply
python3 tools/install_hooks.py --host agy --apply

# 只移除 shoal 的 entry（腳本留著，claude 與 agy 共用）。
python3 tools/install_hooks.py --host claude --uninstall --apply
```

- 腳本取自 committed `HEAD` 的 `hooks/shoal_guard.py`（`git show`，不吃工作樹；HEAD
  沒有就中止），安裝到 `${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py`
  （0755）。
- `--host claude` 改 `settings.json`（`--home`，其次 `CLAUDE_CONFIG_DIR`，預設
  `~/.claude`）：`UserPromptSubmit`，以及 matcher 為
  `Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow|Bash` 的 `PreToolUse`（`Bash`
  是 3.0.0 起為 G4 加的，舊安裝重跑一次就會換成這個 matcher），以及沒有 matcher 的
  `SubagentStart`（3.3.1 起，M11），以及沒有 matcher 的 `Stop`（3.4.0 起，完成檢查）；舊的
  settings 重跑 `--apply` 會原地補上，你自己的 `Stop` 與其他 entry 不動。
  `settings.json` 若是 symlink（dotfile 管理）
  就寫進它指向的檔案，權限不變。Claude 預設 enforce。
- `--host agy` 改 `~/.gemini/config/hooks.json`（`--home` 指 `~/.gemini`）：新增具名
  群組 `shoal-guard`，含 `PreToolUse`（matcher `*`）與 `PreInvocation`。agy 無法分辨
  main 與 subagent，guard 固定 shadow。
- 只有 command 含 `shoal_guard.py --host` 的 handler 算 shoal 的；其他 hook、其他 key、
  key 順序與 2 空格縮排都原樣保留。重複執行不會改變結果，也不會產生新備份。
- 寫入前把原檔備份到 `${XDG_STATE_HOME:-~/.local/state}/shoal/install-hooks/backups/`
  （目錄 0700、檔案 0600），寫入後重新讀檔驗證：shoal handler 數量、其餘內容未被改動、
  腳本與 `HEAD` 相同；不符 exit 1。設定檔不是合法 JSON 或結構不符預期時 exit 2，不寫入。
- `~/.grok` 會讀 `~/.claude/settings.json` 的 hooks（Claude 相容掃描），所以 Claude 的
  entry 也會在 grok session 觸發；guard 的 Claude adapter 看到 grok 的 camelCase payload
  就放行，由 grok 自己的註冊處理。

### Claude 上 guard 的行為（3.0.0 起）

[`docs/specs/delegation-default`](./docs/specs/delegation-default/SPEC.md)
讓 Claude 上的 main session 規則回到 deny；Grok、agy、OpenCode 的行為不變（R1、R2 只提醒）。
3.2.1 起 Codex 的 R1 與 G5 和 Claude 一樣（見下）。
3.2.0 起 R1 與 G5 不再等分類來源（宣告）；3.3.0 起預設改成 `strict`：main 沒派 write role、
使用者也沒有 `#direct` 就不能改檔，宣告不再是出口
（[`docs/specs/guard-declared-direct`](./docs/specs/guard-declared-direct/SPEC.md)）。

#### main 改檔規則的模式：`SHOAL_GUARD_R1`

| 值 | 預設於 | R1（改檔工具）與 G5（寫檔的 `Bash`） |
| --- | --- | --- |
| `strict` | Claude、Codex（3.3.0 起） | enforce 時 deny，除非本輪有：已派出的 write role，或使用者的 `#direct`（或 `SHOAL_GUARD_DIRECT=1`），或目標在豁免路徑。`: shoal-direct ...` 只是普通的空指令（不寫 state、不寫 log、不放行），分類檔（包含 `parent_local`）沒有作用。訊息只列兩個出口：派 `executor`／`applier`，或請使用者加 `#direct`。shadow 記 `would_deny` |
| `declare` | 無（3.2.x 的預設，可選） | enforce 時 deny，除非本輪有：已派出的 write role、使用者的 `#direct` 或 `SHOAL_GUARD_DIRECT=1`、main 的宣告（下一節），或分類檔的 `role` 是 `parent_local`。沒有分類檔、或其他 `role`，都不影響結果。shadow 記 `would_deny` |
| `classified` | 其他 host（Grok、agy、OpenCode） | 3.1.0 的規則：只有分類檔把本輪標成 `judgment` 或 `mechanical` 時才擋（Claude：deny；其他 host 只提醒） |
| `off` | 無 | 關掉 R1 與 G5。硬規則（LEAF、VERIFY_EDIT）、G4、R2 不受影響 |

未設定、空字串、無法辨識的值，或在不能閘控的 host 上設 `strict`／`declare`，都用該 host 的預設
（Claude、Codex 是 `strict`，其他是 `classified`）。
`declare`、`classified`、`off` 的行為與 3.2.1 相同。
被 deny 的改檔與 shell 寫檔不計入 R2 的檔案數，也不會在同一次呼叫送出 R2 提醒。

#### 宣告

`declare` 模式（`SHOAL_GUARD_R1=declare`）下，要自己改檔時 main 先單獨執行一次 shell 指令
（`strict` 下這個指令是普通的空指令，不放行）：

```bash
: shoal-direct "改一個錯字，寫 brief 比直接改貴"
```

`:` 是 shell 的空指令，所以這次呼叫什麼都不做，guard 只讀它。整個指令（去掉前後空白後）必須
是 `: shoal-direct <理由>`：

- 理由可以是雙引號、單引號，或不加引號；去掉空白後不得為空。不加引號時只能是純文字單字：
  不含 `;`、`&`、`|`、`<`、`>`、括號、`$`、反引號、`\`、引號、`*`、`?`、`[`、`]`、`{`、`}`、`~`、
  `^`、`!`、`#`，單字也不以 `=` 開頭。雙引號內只有 `\"`、`\\`、`\$` 與反斜線加反引號是跳脫，
  沒有跳脫的 `$` 與反引號（會展開）不接受。
- 不得有其他指令：`;`、`&&`、`||`、`|`、換行後的第二個指令、subshell、導向、結尾註解、
  前置文字、放在較長 script 裡，都不算宣告，也沒有任何特殊處理（照一般 `Bash` 判斷）。
- 宣告成功時，guard 把「本輪已宣告」記在 state（與 `#direct` 的旗標同一個生命週期，下一輪失效），
  並寫一筆 log（`decision: state`、`rule: declare`、`tool: Bash`）；理由去掉控制字元、截成 200
  字元後放在 log 的 `reason` 欄位，state 不存理由。guard 不判斷理由的內容。
- subagent 的宣告無效；宣告不解除 G4，也不影響硬規則。

deny 訊息（英文；`SHOAL_GUARD_LANG=zh-TW` 為繁中）自帶三個出口：派出 write role（`executor`
或 `applier`）、執行上述宣告，或請使用者在 prompt 加 `#direct`。Claude 的 bootstrap 另有一句
要求只在符合「直接做的條件」時才宣告。

#### 分類檔（公開的選用介面）

任何工具都可以寫分類檔；shoal 不依賴也不安裝任何寫入者（dotfile 的 Jev 只是其中一個）。

- 路徑：`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/turns/<session_id>.json`
  （`session_id` 是 hook payload 的 `session_id`；目錄 `0700`，檔案屬於同一個 uid，guard 會把
  檔案權限收到 `0600`；symlink 與他人擁有的檔案一律忽略）。
- 內容：`{"turn_id": "<這一輪的 id>", "role": "judgment" | "mechanical" | "parent_local"}`。
  `turn_id` 是 Claude 的 `prompt_id`，要等於 guard 目前記錄的那一輪，不同就當成過期而忽略
  （舊鍵名 `prompt_id` 也接受）。其他欄位忽略，檔案上限 64 KiB。
- `strict` 模式下分類檔沒有作用（`parent_local` 也不放行）。`declare` 模式下它只能放寬：`parent_local` 視同已宣告；`judgment`、`mechanical`、其他值、
  或沒有檔案，結果與「沒有檔案」相同。`classified` 模式下行為與 3.1.0 相同（見下表）。

#### 規則總表

| 規則 | 條件 | Claude／Codex（enforce） | Claude／Codex（shadow） | Grok、agy、OpenCode |
| --- | --- | --- | --- | --- |
| R1 | `strict`：本輪沒有派工或 `#direct`；`declare`：本輪沒有派工、`#direct`、宣告或 `parent_local`；`classified`：分類檔把本輪標成 `judgment` 或 `mechanical` 且沒派工。路徑不在豁免範圍 | deny main 的 `Edit`、`Write`、`MultiEdit`、`NotebookEdit` | 記 `would_deny` | 只提醒（`advise`） |
| R2 | 本輪 main 直接改到第 3 個不同的檔案 | 只提醒 | 只提醒 | 只提醒 |
| G4 | main（payload 沒有 `agent_id`）呼叫 `Bash` 且 `run_in_background: true`（只有 Claude；Codex 沒有這個欄位） | deny，訊息要求改派背景的 `watcher` | 記 `would_deny` | 無此規則 |
| G5（3.0.1 起） | R1 的條件成立，且 main 前景呼叫的 `Bash` 指令字面上寫檔（見下） | 以 R1 的規則 id 與訊息 deny | 記 `would_deny`（規則 `R1`） | 無此規則 |

- 派出 `watcher`、`researcher`、`scout` 等非 write role 不會解除 R1（任何模式）；G4 不因任何派工解除。
  派出 `executor`、`applier`、`security-executor` 之後，本輪的改檔與 shell 寫檔放行。
- 放行：使用者 prompt 內獨立的 `#direct`（區分大小寫的字面比對；`#directory`、
  `x#direct`、`#direct-ly` 不算）只放行那一輪，下一輪失效，同時關掉那一輪的 R1、R2 與 G4；
  `SHOAL_GUARD_DIRECT=1` 對整個 session 放行 R1、R2、G4。guard 只記「這輪有 `#direct`」的旗標，
  不記錄 prompt 內容。
- subagent 不受 R1、G4、G5 影響（它們是 main session 規則）；既不是宣告也沒有寫檔的前景 `Bash`
  與其他工具不會被 guard 計入或寫 log；3.4.0 起，本回合已有改檔且尚未檢查時，前景 `Bash` 會把
  state 的 `checked` 設為真（見下面的完成檢查），其他情況不碰 state。
- `Bash` 是 3.0.0 起加進 `PreToolUse` matcher 的工具名稱，所以 3.0.0 之前裝的全域 guard
  要重跑 `tools/install_hooks.py --host claude --apply` 才有 G4（宣告同樣走 `Bash`，沒有 `Bash`
  就沒有宣告出口，這時 `declare` 只能靠 `#direct` 與派工放行）。plugin 的 `--plugin` 判斷看的是
  全域 `settings.json` 的 matcher 有沒有涵蓋該工具：舊 matcher 不含 `Bash` 時，`Bash` 事件由 plugin
  那份處理，每個事件仍只判一次。
- 訊息預設英文，`SHOAL_GUARD_LANG=zh-TW` 切繁中；`SHOAL_GUARD=shadow|off` 照常有效。
- Codex（3.2.1 起）：`apply_patch` 與 `Bash` 的寫檔被擋（3.3.0 起預設 `strict`），`Bash` 工具是
  `tool_input.command`，`UserPromptSubmit` 的 `prompt` 讀 `#direct`；沒有 G4。
  hook 註冊在 3.2.1
  升到 `shoal-guard-v2`（matcher 加 `Bash`）；3.3.0 沒有改任何 hook 註冊，不需要再核准。
- **派工要真的啟動（M11）：Claude 從 3.3.1 起實作，Codex 沒有。**
  - Claude：派工呼叫（`Agent`）本身永遠放行，但只記一筆「待啟動的 write 派工」（log：`allow`／
    `dispatch_pending`）。`SubagentStart` 事件的 `agent_type`（去掉 `shoal:` 前綴後）是
    write 等級的
    role、且同一個 session 有待啟動的派工時，guard 放行這一輪（log：`state`／`dispatch_started`），
    一次事件只釋放一筆。read-only 或 verify 等級的啟動、沒有待啟動派工的啟動，都不改變任何東西。
    對應規則：以 `session_id` 為準（實測與 main 相同）；事件的 `prompt_id` 若與 guard 記錄的本輪不同，
    仍然釋放並在 log 的 `skip_reason` 寫 `prompt_id_mismatch`（兩者是否相等沒有量過）。待啟動的派工
    不跨輪。啟動失敗時是否仍會發出事件沒有量過；沒有發出事件就不放行。deny 訊息沿用各模式原本的
    訊息（`strict` 就是 strict 訊息），不新增出口。
  - **guard 腳本與 hook 註冊必須一起更新**：plugin 的 `hooks.json` 與全域的
    `tools/install_hooks.py --host claude --apply` 都在 3.3.1 加了 `SubagentStart`。只更新腳本、沒有
    註冊該事件的 Claude 安裝，收不到啟動事件，派工後會一直被擋（只剩 `#direct`），沒有時間啟發式
    補救；plugin 與全域 guard 並存時 `--plugin` 的讓出判斷對 `SubagentStart` 同樣看全域 settings 有沒有
    註冊。
  - Codex：沒有已記錄的啟動事件，維持在 `spawn_agent` 呼叫時放行；role 沒能啟動時放行仍然有效。
  - 其他 host 不變（派工呼叫放行）。
- **完成檢查（3.4.0 起，Claude 與 Codex；docs/specs/shared-rules B2 到 B4）。** guard 逐回合記兩件事：
  - `changed`：main 的改檔工具或 shell 寫檔被放行且目標不是豁免路徑；或可寫的 role 算「已派工」
    （Claude 在 `SubagentStart` 釋放待啟動派工的那一刻，Codex 在派工呼叫）。
  - `checked`：在最近一次 `changed` 之後，派出或啟動了 verify 等級的 role（`verifier`、`watcher`），
    或 main 執行了前景 `Bash`、而且那個指令既不寫檔也不是 `: shoal-direct` 宣告。之後再發生一次
    `changed` 會清掉 `checked`；改檔之前的前景指令不算。判斷只看有沒有跑，不判斷指令是不是測試
    （spec D3）。沒有改檔的回合，前景 `Bash` 不碰 state，也不寫 log。
  - `Stop` 事件：同一回合的 state、`changed` 且沒有 `checked`、`stop_hook_active` 恰為 `false`、模式為
    enforce、這一回合還沒擋過，guard 在 stdout 輸出一次 `{"decision":"block","reason":"..."}`
    （先把「已擋」存進 state，寫入失敗就不擋）。訊息：「Shoal completion check: this turn
    changed files and no check ran afterwards. Run a verification now (tests, a
    verifier or watcher role), or say explicitly in your report that the change
    is unverified.」
    （`SHOAL_GUARD_LANG=zh-TW` 為繁中）。
    其他情況一律不表態（失敗開放）：別的回合的 `Stop`、state 讀不到或超過上限、id 缺漏、
    `stop_hook_active` 不是 `false`、subagent 的 `Stop`、shadow（log 記 `would_block`）、
    `SHOAL_GUARD=off`。
  - 開關：`SHOAL_GUARD_STOP=on|off`（預設 `on`；其他值視為 `on`），只對 Claude 與 Codex
    有效。其他 host（Grok、agy、OpenCode）沒有已記錄的結束事件 payload，不啟用，永遠不擋。
  - 註冊：plugin 的 `hooks.json` 與全域 `install_hooks.py --host claude` 都加了沒有
    matcher 的 `Stop`；
    plugin 與全域並存時，`--plugin` 的讓出判斷對 `Stop` 同樣看全域 settings 有沒有註冊。guard 腳本與
    註冊必須一起更新，只更新腳本的安裝只是沒有完成檢查，其他規則不受影響。
  - **未量到：Claude 對 Stop block 輸出的處理。** 輸出用 Claude Code 文件的 Stop hook 格式
    （JSON `decision: "block"` 加 `reason`，exit 0）；repo 內沒有實測紀錄。格式不被接受時 Claude 只是
    照常結束，檢查失效但不會卡住。payload 形狀已實測（`tests/fixtures/stop_payload_shapes.json`）。

G5 補的是 R1 看不到的缺口：main 用 `cat > 檔案 <<EOF` 之類的 shell 指令寫檔，沒走任何改檔工具
（2026-10-10 實測）。它只看 `Bash` 的指令字串，是字面判斷，不是 shell parser：

- 算寫檔：`>`、`>>`、`>|`、`&>` 導向一般檔案（含 `cat > f <<'EOF'` 這類 heredoc）、`tee [-a] 檔案`、
  `sed -i` 與 `sed --in-place`。這些要在指令位置（`;`、`|`、`&&`、換行、`(`、`then`、`do` 之後，
  或接在 `sudo`、`env`、`xargs`、`find -exec` 後面）。
- 不算：導向 `/dev/` 底下（`/dev/null`、`/dev/stdout`、`/dev/stderr`）、檔案描述符複製（`2>&1`、`>&2`）、
  輸入導向 `<`、沒有輸出導向的 heredoc 本文、引號內的 `>`（`grep "a > b" f`）、`[[ ]]`、`(( ))`、
  `$(( ))` 內的比較、註解，以及 R1 豁免路徑（`/tmp`、`$TMPDIR`、`.ai`、Claude 的 projects 目錄；
  相對路徑依事件的 cwd 解析；開頭的 `~`、`$HOME`、`$TMPDIR` 會展開）。
- 目標看不出來時（`> "$f"`、`> $(mktemp)`）：只要它明確是導向非 `/dev/` 的目標就算寫檔；`sed -i`
  沒有檔案參數（檔名來自 `xargs` 或 `find -exec`）也算。這會有誤擋（例如變數其實指向 `/tmp`），
  出口是宣告或 `#direct`。
- 擋不到：用 interpreter 寫檔（`python`、`node`、`perl` 腳本）、`cp`、`mv`、`git apply`、`patch`、
  `dd of=`、`install`、`awk` 程式內的 `print > file`，以及 `$(...)` 或 backtick 內的導向。這是刻意的取捨，
  不嘗試偵測。
- 被 deny 的指令不會記成 edit；放行的 shell 寫檔（豁免路徑、`#direct`、已派 write role、已宣告，
  或 `classified` 模式下沒有分類）也不計入 R2 的檔案數。放行且確實有寫檔的呼叫會留一筆 `allow` log
  （規則 `direct`、`dispatched`、`declared` 或 `uncounted`）。

## Claude Code plugin

Claude Code 的第二條安裝路徑，給沒有 dotfile 的使用者。內容（10 個 role，含 `watcher`、`researcher`、
`shoal-orchestration` skill、dispatch guard、policy bootstrap）全部由
`python3 tools/render.py --host claude-plugin --write` 從 `hosts/claude/dist`、
`hooks/shoal_guard.py` 與根目錄 `VERSION` 產生，輸出在 `claude-plugin/` 與
`.claude-plugin/marketplace.json`；`--check` 與 golden 擋住手改。Codex 的
`plugin/` 目錄與這條路徑無關。需要 Claude Code 2.1 以上與 `python3`。

```bash
# 1. 釘在 tag 上安裝（不追預設 branch）。
claude plugin marketplace add miyago9267/shoal#v3.5.0
claude plugin install shoal@shoal

# 升級：marketplace 的 source 不同會被拒絕，所以先移除再用新 tag 加回。
claude plugin marketplace remove shoal
claude plugin marketplace add miyago9267/shoal#v3.5.0
claude plugin update shoal@shoal

# 解除安裝。
claude plugin uninstall shoal@shoal
claude plugin marketplace remove shoal

# 只在單一 session 試用（不寫任何 config）。
claude --plugin-dir ./claude-plugin
```

- `owner/repo#<ref>` 的 `<ref>` 是 branch 或 tag，由 `git clone --branch` 解析（在
  Claude Code 2.1.291 實測：ref 不存在時回報 `Remote branch ... not found`）。不寫
  `#<ref>` 會跟預設 branch，不建議。tag 沿用 repo 的 `v<VERSION>`，必須包含
  `claude-plugin/` 與 `.claude-plugin/marketplace.json`；第一個含 plugin 的 tag 發佈前，
  上面的 `#v3.5.0` 指令會失敗。`claude plugin tag claude-plugin` 也可以建
  `shoal--v<VERSION>` 形式的 tag，兩種擇一，marketplace 用哪個就 `#` 哪個。
- plugin 與 marketplace 的版本都等於根目錄 `VERSION`。
- guard hook 的 command 一律是
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/shoal_guard.py" --host claude --plugin`，
  路徑加引號，安裝路徑含空白也能跑；SessionStart 的 `emit-sessionstart.sh` 自己固定
  `PATH=/usr/bin:/bin`，把 `claude-plugin/policy/claude-md.bootstrap.md` 注入 session。
  如果全域 `CLAUDE.md` 已經有 shoal bootstrap，就不再注入。
- namespace：plugin 的 agent 名稱是 `shoal:<role>`（例如 `shoal:executor`），skill 是
  `shoal:shoal-orchestration`。實測 hook payload 的 `agent_type` 與 Agent 工具的
  `subagent_type` 都是 `shoal:executor`；guard 只認裸名稱與 `shoal:` 前綴。
- 與全域安裝共存：已經用 `tools/install_hooks.py --host claude` 裝過全域 guard 時，
  plugin 的 hook 帶 `--plugin`，只在 user `settings.json`（`CLAUDE_CONFIG_DIR` 或
  `~/.claude`，symlink 會解開）確實有指向
  `${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py` 的對應 event entry，
  而且那支腳本存在時才什麼都不做；其他情況（沒有全域安裝、腳本不見、settings 讀不
  懂）plugin 那份照常執行，不會變成零次。兩邊同時存在時每個事件只會有一筆 log。
  SessionStart 偵測到全域 guard 會印一行提示，僅供參考。
- 預設模式與全域安裝相同（Claude 是 enforce）；`SHOAL_GUARD=shadow|off` 照常有效。

資料與保留（K6）：plugin 與全域安裝共用同一個 state 與 log 目錄
`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`（`state/`、`turns/` 與
`guard.jsonl`）。`guard.jsonl` 超過 1 MiB 就停止寫入，不輪替。
`claude plugin uninstall` 與 `marketplace remove` 不會刪這個目錄；要清除時手動執行：

```bash
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/shoal/guard"
```

目錄會在下次事件重建。這個目錄與全域安裝共用，清除前先確認沒有進行中的 session
要保留 guard 的 turn 狀態。

## OpenCode

OpenCode host 的 installer 是 `hosts/opencode/plugin/install/install.sh`，有兩種
範圍。兩者都需要 `bun`，動作語意相同：`--enable` 安裝、`--disable` 移除、
`--rollback` 還原。

```bash
# 專案：寫進 <project>/.opencode/
sh hosts/opencode/plugin/install/install.sh --target DIR --enable

# 全域：寫進 OpenCode 的 config dir
sh hosts/opencode/plugin/install/install.sh --global --enable
sh hosts/opencode/plugin/install/install.sh --global --config-dir DIR --enable
sh hosts/opencode/plugin/install/install.sh --global --disable
sh hosts/opencode/plugin/install/install.sh --global --rollback
```

`--global` 安裝 shoal committed `HEAD` 的內容：五個 role 到 `<config-dir>/agents/`，
plugin 到 `<config-dir>/plugins/shoal-opencode.js`，`catalog.json` 與
`routing.json` 到 `<config-dir>/shoal/`。plugin 是在暫存目錄用
`git archive HEAD hosts/opencode`、`bun install --frozen-lockfile` 與 `bun build`
產生，不吃未 commit 的修改。`<config-dir>` 依序取 `--config-dir`、
`OPENCODE_CONFIG_DIR`、`~/.config/opencode`，必須已存在。

- manifest 與備份放在 `${XDG_STATE_HOME:-$HOME/.local/state}/shoal/opencode-global`，
  不寫進 config dir（config dir 可能被 dotfile 追蹤）。
- 目標路徑已有不是本 installer 安裝的檔案（內容與來源不同，且 manifest 沒有記錄或
  hash 不符）時中止並列出衝突，完全不寫入。
- `--disable`、`--rollback` 只在每個檔案的 hash 都與 manifest 相符時動作，否則整批
  不動；config dir 以 manifest 記錄的為準。`--rollback` 之後 installer 新增的檔案與
  它建立的 `agents/`、`plugins/`、`shoal/` 目錄都會消失。
- 安裝後檢查 `routing.json` 的候選 provider 是否出現在
  `<config-dir>/opencode.json` 的 `provider` keys 或 `enabled_providers`，沒有就
  警告（不中止）；只比對 key 名稱，auth 或環境變數型 provider 無法在這裡驗證。
- 目前目錄（或其 git root）已有專案的 `.opencode/plugins/shoal-opencode.js`
  時警告：全域與專案兩份 plugin 會同時載入。新版 plugin 以 `globalThis` 登記表避免
  重複註冊 `shoal_route`，舊版專案 plugin 沒有這個保護。

plugin 查找設定時，專案的 `.opencode/shoal/catalog.json` 存在就只用專案層，
否則改用全域 `<config-dir>/shoal/`（同一層內 `routing.json` 可省略，缺少時回退
native routing）。從 shoal 以外的目錄執行時，installer 需要在 shoal checkout 內
（它用 `git` 讀取 HEAD）。安裝後重新啟動 OpenCode。

## 每日同步

`tools/sync_global.py` 把 committed HEAD 同步到 Codex、Grok、agy、OpenCode 的全域
安裝。dotfile 的 SessionStart hook（`agent-stack-auto-update.sh`，每個日曆日一次）
在 Claude 的步驟之後以 `--apply` 呼叫它。只用 Python stdlib；沒有差異時不寫檔、不建
備份，重複執行結果相同。

```bash
python3 tools/sync_global.py                      # dry-run，四個 host 各印一行
python3 tools/sync_global.py --apply              # 實際更新
python3 tools/sync_global.py --apply --host codex grok --strict
```

每個 host 一行：`<host>: up-to-date | updated (<內容>) | skipped (<原因>) | failed (<原因>)`；
dry-run 的 `updated` 行尾有 `[dry-run]`。exit 0，只有 `--strict` 且有 `failed` 才是 1。

| Host | 做什麼 |
| --- | --- |
| codex | `install_hooks.py --host codex`（guard 與 hook entry）。`templates/agents/*.toml` 對 `<CODEX_HOME 或 ~/.codex>/agents/`：相同就略過；與 HEAD 不同但位元組等於該 template 的歷史版本才取代（temp file 加 rename，保留 mode）；其他情況（自己改過、來源不明、symlink）不動並回報 `drift`。平常不跑 `install/install.py`；偵測到 2.0.0 之前的舊名安裝才跑（見下方「從舊名升級」）。 |
| grok | `install_grok.py` dry-run 有差異才 `--apply`；不帶 `--fix-toggles`，不動 `config.toml`。舊名的 rules、hooks 檔案（確認是 shoal 安裝的）會一起移除。 |
| agy | `install_hooks.py --host agy`；`~/.gemini/config/agents`、`skills` 是指向 `hosts/agy/dist` 的 symlink，只檢查沒有斷掉或改指（回報，不修）；唯一例外是指向本 repo 的舊名 skill symlink，會移除並改指新名。 |
| opencode | 需要 `bun`（沒有就 `skipped`）。照 `install_global.sh` 的步驟建出 HEAD 的 bundle，與全域 config dir 的 plugin、roles、`shoal/*.json` 逐位元組比對，有差異才 `install.sh --global --disable` 再 `--enable`。全域安裝尚未啟用或已停用就 `skipped`，不替使用者重新啟用。dotfile 的 harness copy（`OPENCODE_HARNESS_PLUGIN`，預設 `~/dotfile/config/opencode-harness/plugins/shoal-opencode.js`）只回報 `matches` 或 `differs`，不寫入。 |

`install_hooks.py` 與 `install_grok.py` 的 `--json` 會多印一行 `{"changes": ...}`
（寫入前是否有差異），這是 `sync_global.py` 判斷是否需要 `--apply` 的依據。

## 從舊名升級

2.0.0 把安裝出去的名稱全部換新（對照表：`docs/specs/shoal-rebrand/RENAME.md`）。installer
與 `sync_global.py` 會辨識自己以舊名安裝的檔案，移除後以新名安裝；不是 shoal 安裝的
舊名檔案不動，只回報。dry-run 的計畫只會有「移除舊名」與「安裝新名」兩類。

| Host | 辨識與移除 | 保留 |
| --- | --- | --- |
| codex | 與舊 projection 逐位元組相同的 hooks.json 群組、舊 gate 腳本（hash 等於舊 install state 的紀錄）、`AGENTS.md` 的舊 marker 區塊（換成新 marker）、舊 install state（封存成 `.pre-shoal-<時間>`）、`config.toml` 中指向本 repo `plugin/` 的舊 marketplace 與 plugin table（改名）、同一條件下的 plugin cache 與 jev 資料目錄（cache 移除，jev 目錄改名） | 你自己改過的舊 gate 腳本改名為 `.pre-shoal-<時間>` 備份並取消註冊；不指向本 repo 的 table、有 pending 的舊交易（要先處理，installer 會中止） |
| grok | `rules/`、`hooks/` 底下舊名檔案，且 rules marker 帶 `-shoal.N` 或有 shoal 專屬的 guard 腳本 | 舊名目錄裡其他檔案、沒有 shoal 記號的舊名檔案 |
| agy | 指向本 repo `hosts/agy/dist` 的舊 skill symlink（改指新名） | 指向別處或不是 symlink 的 |
| opencode | 舊 manifest 記錄的 plugin 與舊名控制目錄裡的檔案，用舊 manifest `--disable` 後再 `--enable`；專案層的 `.opencode/` 同理 | 被改過的檔案（整批不動） |

Codex 遷移後，新的 hook 路徑要在互動式 Codex 用 `/hooks` 再核准一次；plugin cache 由
`install/install.py` 的 `codex plugin add` 重建。Claude Code 的 plugin 更新到 2.0.0 後 skill
名稱自動換成 `shoal-orchestration`。
