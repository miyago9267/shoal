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

`--roles-only` writes only the seven `agents/*.toml` files. It leaves policy,
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
(`hooks/shoal_guard.py --host codex`, [`docs/specs/dispatch-enforcement`](./docs/specs/dispatch-enforcement/SPEC.md))
next to the autoroute gate. It is a separate script with its own projection ID
(`shoal-guard-v1`) and its own state entry (`guard_registration`), so the gate is
unchanged. It adds a `UserPromptSubmit` group that only records the turn, and a
`PreToolUse` group with matcher `^(apply_patch|spawn_agent|collaborationspawn_agent)$`.
It runs in shadow mode (`would_deny` and `advise` log records under
`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`) until the enforce switch in
the spec
(E6); `SHOAL_GUARD=off` disables it for a session. Only the subagent rules
(LEAF, VERIFY_EDIT) ever deny; the main-session rules R1 and R2 only remind
(once per turn, as `additionalContext` on Claude and Codex;
`SHOAL_GUARD_DIRECT=1` silences it). An existing home that
predates the
guard gains the script and both groups on the next install; other hook groups are
preserved. The installer does not write hook trust: after installing, approve
the new
hook once in an interactive Codex session with `/hooks`, as for the autoroute gate.
Without that approval Codex does not run it. A launch probe (must exit 0, prints
nothing):

```bash
echo '{}' | /usr/bin/env python3 "$SHOAL_TARGET_HOME/hooks/shoal_guard.py" --host codex
```

#### Guard only, without running the installer

When `install/install.py` cannot be reconciled with the Codex home (for
example a locally modified `shoal_autoroute_gate.py` that the installer
would replace), `tools/install_hooks.py --host codex` manages only the guard.
It writes the same `shoal-guard-v1` groups (including `commandWindows`) into
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

## Claude Code plugin

Claude Code 的第二條安裝路徑，給沒有 dotfile 的使用者。內容（8 個 role、
`shoal-orchestration` skill、dispatch guard、policy bootstrap）全部由
`python3 tools/render.py --host claude-plugin --write` 從 `hosts/claude/dist`、
`hooks/shoal_guard.py` 與根目錄 `VERSION` 產生，輸出在 `claude-plugin/` 與
`.claude-plugin/marketplace.json`；`--check` 與 golden 擋住手改。Codex 的
`plugin/` 目錄與這條路徑無關。需要 Claude Code 2.1 以上與 `python3`。

```bash
# 1. 釘在 tag 上安裝（不追預設 branch）。
claude plugin marketplace add miyago9267/shoal#v2.0.0
claude plugin install shoal@shoal

# 升級：marketplace 的 source 不同會被拒絕，所以先移除再用新 tag 加回。
claude plugin marketplace remove shoal
claude plugin marketplace add miyago9267/shoal#v2.0.0
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
  上面的 `#v2.0.0` 指令會失敗。`claude plugin tag claude-plugin` 也可以建
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
