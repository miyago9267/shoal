# Grok Build 安裝

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
dispatch guard (`hooks/shoal-grok/shoal_guard.py`) with `UserPromptSubmit`,
`SubagentStart` and `Stop` entries and a `PreToolUse` entry (matcher
`^(search_replace|write|write_file|edit|multi_edit|create_file|run_terminal_command|spawn_subagent)$`);
the existing plan-mode guard entry is kept.

Since the guard-every-gate S4 slice (docs/specs/guard-every-gate; payloads in
`tests/fixtures/grok_guard_event_shapes.json`, Grok CLI 1.0.46) the Grok guard
defaults to `enforce` (it was `shadow`; `SHOAL_GUARD=shadow` or `off` still
works) because a `{"decision":"deny"}` answer was observed to stop the main
session's `write`, a subagent's `write` and `spawn_subagent`. The main session's
edit rule is `strict` like Claude and Codex: `write`, `search_replace` and a
`run_terminal_command` that writes a file literally (`>`, `>>`, `tee`,
`sed -i`, `perl -i`) are denied unless a write-level role has started this
turn, the prompt carries `#direct`, `SHOAL_GUARD_DIRECT=1` is set, or the
path is exempt. A write role
counts as started at its `subagent_start` event, not at the `spawn_subagent`
call. A subagent's own events carry its own session id (equal to the
`subagentId` of `subagent_start`, which is sent under the main session id), so
`subagent_start` records `subagentId -> {main session, role, whether the main
turn carried #direct}` in `state/grok.agents.json` (the last 64) and the
subagent's calls are judged through it: a subagent that is not a shoal
write-capable role (including a generic one) is denied file writes (E1), a
`#direct` turn releases the subagents started in it, `SHOAL_GUARD_WRITE_AGENTS`
and `SHOAL_GUARD_DIRECT=1` release as on the other hosts, and a subagent that
calls `spawn_subagent` is denied (LEAF). A subagent event that names a
`subagentType` but has no record is judged by that role and is never released by
`#direct`. Reinstall (`install_grok.py --apply`) to get the new hook entries and
start a new Grok session; the Stop answer is the only part not yet confirmed
live (see above). The copy in
`hosts/grok/dist` is generated from `hooks/shoal_guard.py` by
`python3 tools/render.py --host grok --write`, and the installer aborts if the
dist copy
differs from the same commit's `hooks/shoal_guard.py`. Grok runs the hook path directly,
so the host comes from the hook's `env` (`SHOAL_GUARD_HOST=grok`) instead of `--host`.
Start a new Grok session after installing: agents, rules and hooks are read at session
start.
