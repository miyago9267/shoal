# Pilotfish-Codex installation playbook（shoal 的 Codex host 安裝說明）

This playbook is for an AI agent installing the native Pilotfish-Codex target.
Read it completely before running an installation command. The detailed
ownership and migration rules are in
[`install/AGENT-INSTALL.md`](install/AGENT-INSTALL.md); this playbook does not
replace that runbook.

## Scope and prerequisites

The installer changes one Codex home. The default is `~/.codex`; set the
`CODEX_HOME` environment variable or pass `--codex-home` to select another
home. It installs the
native Pilotfish roles, the active bootstrap block in the selected root
`AGENTS.md`, the `pilotfish-codex` Plugin/Skill through Codex's local
marketplace contract, native config, and the Pilotfish hook registration and
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
Luna; and preserves `plan-verifier` on Sol/high plus all approval and security
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
  `*.pilotfish-codex-<timestamp>` backup; and
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
PILOTFISH_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
printf 'target home=%s\n' "$PILOTFISH_TARGET_HOME"
```

Inspect only the managed inputs. Preserve unrelated config and custom role
files; do not read credentials:

```bash
if [ -f "$PILOTFISH_TARGET_HOME/config.toml" ]; then
  sed -n '1,240p' "$PILOTFISH_TARGET_HOME/config.toml"
fi
for policy in "$PILOTFISH_TARGET_HOME/AGENTS.md" "$PILOTFISH_TARGET_HOME/AGENTS.override.md"; do
  if [ -s "$policy" ]; then
    printf '\n--- %s ---\n' "$policy"
    sed -n '1,260p' "$policy"
  fi
done
if [ -d "$PILOTFISH_TARGET_HOME/agents" ]; then
  find "$PILOTFISH_TARGET_HOME/agents" -maxdepth 1 -type f -name '*.toml' -print
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
PILOTFISH_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
bash install/install.sh --dry-run --codex-home "$PILOTFISH_TARGET_HOME"
```

Native Windows PowerShell:

```powershell
$pilotfishHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
.\install\install.ps1 --dry-run --codex-home $pilotfishHome
```

Pinned remote source (replace the placeholder with an exact published tag or
full commit SHA; do not run the placeholder itself):

```bash
PILOTFISH_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
PILOTFISH_REF='<release-tag-or-commit-sha>'
curl -fsSL \
  "https://raw.githubusercontent.com/miyago9267/shoal/${PILOTFISH_REF}/install/install.sh" \
  | bash -s -- --ref "$PILOTFISH_REF" --dry-run \
    --codex-home "$PILOTFISH_TARGET_HOME"
```

Note: pinned refs before v1.0.0 (v1.8.1 and earlier) exist only in
`miyago9267/pilotfish-codex`; use that repository name in the URL for them.

If the active home has a dotfiles-managed `AGENTS.md` or `hooks` symlink that
points outside the home, use the isolated role path instead of integrating the
full target:

```bash
bash install/install.sh --dry-run --roles-only \
  --codex-home "$PILOTFISH_TARGET_HOME"
bash install/install.sh --roles-only \
  --codex-home "$PILOTFISH_TARGET_HOME"
```

`--roles-only` writes only the seven `agents/*.toml` files. It leaves policy,
config, hooks, Plugin, and installer state untouched; existing same-name role
customizations still require an explicit replacement option.

`--ref=<release-tag-or-commit-sha>` is equivalent to the two-argument form.
Keep the raw script URL ref and the archive ref identical. `PILOTFISH_REF` is
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
PILOTFISH_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
bash install/install.sh --codex-home "$PILOTFISH_TARGET_HOME"
```

Native Windows PowerShell:

```powershell
$pilotfishHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
.\install\install.ps1 --codex-home $pilotfishHome
```

Pinned remote source:

```bash
PILOTFISH_TARGET_HOME="${CODEX_HOME:-$HOME/.codex}"
PILOTFISH_REF='<release-tag-or-commit-sha>'
curl -fsSL \
  "https://raw.githubusercontent.com/miyago9267/shoal/${PILOTFISH_REF}/install/install.sh" \
  | bash -s -- --ref "$PILOTFISH_REF" \
    --codex-home "$PILOTFISH_TARGET_HOME"
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
  --config "$PILOTFISH_TARGET_HOME/config.toml" "$PILOTFISH_TARGET_HOME/agents"
```

The expected result is:
`all native Pilotfish config and agent TOMLs valid`.
Also confirm that these managed hook files exist, without printing secrets:

```bash
test -f "$PILOTFISH_TARGET_HOME/hooks.json"
test -f "$PILOTFISH_TARGET_HOME/hooks/pilotfish_autoroute_gate.py"
test -f "$PILOTFISH_TARGET_HOME/hooks/shoal_guard.py"
grep -F 'Pilotfish automatic typed Plan-review gate.' \
  "$PILOTFISH_TARGET_HOME/hooks.json"
```

### Dispatch guard

Since host 1.8.3 the installer also registers the dispatch guard
(`hooks/shoal_guard.py --host codex`, [`docs/specs/dispatch-enforcement`](./docs/specs/dispatch-enforcement/SPEC.md))
next to the autoroute gate. It is a separate script with its own projection ID
(`shoal-guard-v1`) and its own state entry (`guard_registration`), so the gate is
unchanged. It adds a `UserPromptSubmit` group that only records the turn, and a
`PreToolUse` group with matcher `^(apply_patch|spawn_agent|collaborationspawn_agent)$`.
It runs in shadow mode (`would_deny` log records under
`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`) until the enforce switch in
the spec
(E6); `SHOAL_GUARD=off` disables it for a session. An existing home that
predates the
guard gains the script and both groups on the next install; other hook groups are
preserved. The installer does not write hook trust: after installing, approve
the new
hook once in an interactive Codex session with `/hooks`, as for the autoroute gate.
Without that approval Codex does not run it. A launch probe (must exit 0, prints
nothing):

```bash
echo '{}' | /usr/bin/env python3 "$PILOTFISH_TARGET_HOME/hooks/shoal_guard.py" --host codex
```

### Prove the hook can launch

Registration and trust do not prove that the registered command runs. A hook
whose interpreter is missing fails silently and open: no enforcement, and no
signal that enforcement is gone. Run the registered command's own launch probe
before trusting the result of any later gate check.

On macOS and Linux:

```bash
/usr/bin/env python3 \
  "$PILOTFISH_TARGET_HOME/hooks/pilotfish_autoroute_gate.py" --selftest
```

On native Windows, `python` is frequently the Microsoft Store alias stub, which
opens the Store instead of running the script. Run the probe through the same
command the `commandWindows` entry uses and require real output:

```powershell
uv run --no-project python -c "import os,runpy; from pathlib import Path; runpy.run_path(str(Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))/'hooks'/'pilotfish_autoroute_gate.py'), run_name='__main__')" --selftest
```

Both must print `pilotfish-autoroute-gate schema=<n> launchable`. Any other
result — no output, a Store window, `ModuleNotFoundError` — means the gate is
not enforcing anything on this machine. Fix the interpreter or record the gate
as unenforced; do not report the install as gated.

Trust the Pilotfish registration once in an interactive Codex session. Inspect
the groups that run `hooks/pilotfish_autoroute_gate.py` and `hooks/shoal_guard.py`,
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
require reinstalling Pilotfish.

For a remote-only install with no checkout, validate the same files from a
checkout or source archive at the exact installed ref. Do not fetch an
un-pinned validator or claim validation from a different ref.

## Safe rerun and update

Rerunning the same command at the same ref is intended to be idempotent. It
preserves unrelated config, custom same-name role bytes, user files, and
complete unrelated native hook groups. Pilotfish only owns its exact,
event-bound hook groups and its script. A sidecar-proven Pilotfish script can
upgrade to the selected source; a changed, missing, duplicated, or unproven
Pilotfish group or script stops the update. Run a new dry-run and obtain
approval again before changing to another visible tag or commit. Review every
changed role, policy, hook, and backup path before the real update.

The installer fails closed for customized role drift, malformed or ambiguous
hook registration, an unproven current or historical Pilotfish group, extra
roles, malformed config, or stale transaction evidence. Do not force those
cases by deleting state or passing an unsupported option to `install.py`.

## Recovery and rollback

If an install aborts, stop. Preserve the error output, the pending or aborted
state sidecar, and every `*.pilotfish-codex-<timestamp>` backup. Do not rerun
over a pending transaction, delete unknown roles, or restore the whole home
blindly. After separate operator approval, copy the affected managed files and
state evidence to an explicitly chosen recovery directory; exclude credentials
unless the operator deliberately handles them.

The installer stages writes, creates backups before replacement, verifies
post-write fingerprints, and records committed ownership in a mode-`0600`
sidecar. Its isolated smoke candidate uses the clean Pilotfish registration,
not any unrelated active-home hook group. If a concurrent edit is detected, the
installer preserves that content and leaves an aborted sidecar for operator
resolution. Use those records and
[`install/AGENT-INSTALL.md`](install/AGENT-INSTALL.md) to decide a targeted
restoration. A customized same-name role or an unproven Pilotfish hook group
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
`agents/`, `roles/`, `rules/pilotfish-grok.md`, and the native hooks
(`hooks/pilotfish-grok.json` plus `hooks/pilotfish-grok/`) under the Grok home.
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
`plan-verifier`, `security-reviewer`, `mech-executor`, `executor`, `verifier`,
`security-executor`) to `false`, the dry-run flags it and nothing is changed.
`--fix-toggles` deletes exactly those lines and keeps every other byte; it
aborts without writing if the table cannot be edited that way (for example
inline or dotted keys). Other `config.toml` keys, including the Claude
compatibility cells in `config.snippet.toml`, are not managed by this
installer; merge them by hand.

The hooks add a `SubagentStop` format gate for `verifier`, `plan-verifier` and
`security-reviewer`, and a `PreToolUse` guard that denies write-capable
`spawn_subagent` calls while Grok is in plan mode. They also install the shoal
dispatch guard (`hooks/pilotfish-grok/shoal_guard.py`) with a `UserPromptSubmit`
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
  `Edit|Write|NotebookEdit|MultiEdit|Agent|Workflow` 的 `PreToolUse`。`settings.json`
  若是 symlink（dotfile 管理）就寫進它指向的檔案，權限不變。Claude 預設 enforce。
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
plugin 到 `<config-dir>/plugins/pilotfish-opencode.js`，`catalog.json` 與
`routing.json` 到 `<config-dir>/pilotfish/`。plugin 是在暫存目錄用
`git archive HEAD hosts/opencode`、`bun install --frozen-lockfile` 與 `bun build`
產生，不吃未 commit 的修改。`<config-dir>` 依序取 `--config-dir`、
`OPENCODE_CONFIG_DIR`、`~/.config/opencode`，必須已存在。

- manifest 與備份放在 `${XDG_STATE_HOME:-$HOME/.local/state}/shoal/opencode-global`，
  不寫進 config dir（config dir 可能被 dotfile 追蹤）。
- 目標路徑已有不是本 installer 安裝的檔案（內容與來源不同，且 manifest 沒有記錄或
  hash 不符）時中止並列出衝突，完全不寫入。
- `--disable`、`--rollback` 只在每個檔案的 hash 都與 manifest 相符時動作，否則整批
  不動；config dir 以 manifest 記錄的為準。`--rollback` 之後 installer 新增的檔案與
  它建立的 `agents/`、`plugins/`、`pilotfish/` 目錄都會消失。
- 安裝後檢查 `routing.json` 的候選 provider 是否出現在
  `<config-dir>/opencode.json` 的 `provider` keys 或 `enabled_providers`，沒有就
  警告（不中止）；只比對 key 名稱，auth 或環境變數型 provider 無法在這裡驗證。
- 目前目錄（或其 git root）已有專案的 `.opencode/plugins/pilotfish-opencode.js`
  時警告：全域與專案兩份 plugin 會同時載入。新版 plugin 以 `globalThis` 登記表避免
  重複註冊 `pilotfish_route`，舊版專案 plugin 沒有這個保護。

plugin 查找設定時，專案的 `.opencode/pilotfish/catalog.json` 存在就只用專案層，
否則改用全域 `<config-dir>/pilotfish/`（同一層內 `routing.json` 可省略，缺少時回退
native routing）。從 shoal 以外的目錄執行時，installer 需要在 shoal checkout 內
（它用 `git` 讀取 HEAD）。安裝後重新啟動 OpenCode。
