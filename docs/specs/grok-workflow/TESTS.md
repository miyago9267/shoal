# TESTS — grok-workflow

> Acceptance cases for `SPEC.md`。G1 至 G4 全部離線，測試用 temp 目錄，
> 不讀寫真實的 `~/.grok`。

## orchestration rules（G1）

- **AC-GW-001:** The grok host shall render
  `rules/pilotfish-grok.md` into `hosts/grok/dist/`, with the version marker
  taken from `hosts/grok/VERSION` and not hard-coded in the renderer.
- **AC-GW-002:** When `hosts/grok/VERSION` changes and dist is not
  rewritten, `render --host grok --check` shall exit 1 naming the rules
  file; after `--write` the marker shall be
  `<!-- pilotfish-grok v<VERSION> -->`.
- **AC-GW-003:** The rendered rules file shall equal the upstream v1.0.6
  fixture line for line, except the single marker line.
- **AC-GW-004:** The rendered grok output, including the rules file and the
  hooks, shall be byte-identical to `tests/golden/grok/`.
- **AC-GW-005:** When `hosts/grok/VERSION` is missing or malformed, or the
  rules source does not have exactly one marker line, render shall exit 2.

## SubagentStop 格式 gate（G3）

- **AC-GW-010:** The hook config shall register three `SubagentStop`
  entries with matchers `^verifier$`, `^plan-verifier$` and
  `^security-reviewer$`; each entry shall pass its role through
  `PILOTFISH_ROLE`, and the command shall be a path relative to the JSON file.
- **AC-GW-011:** When the verifier's last message contains `CONFIRMED`,
  `REFUTED`, `INCONCLUSIVE`, `CONTINUE`, `PIVOT` or `ROLLBACK` at any
  position, the gate shall allow the stop.
- **AC-GW-012:** When the verifier's last message contains none of those
  tokens, the gate shall block with a reason that lists them.
- **AC-GW-013:** The plan-verifier gate shall allow a message with a bare
  `READY` line, and a `REVISE` message whose every block has `Blocker:`,
  `Evidence:`, `Minimum revision:` and `Acceptance check:`; it shall block
  prose, a `REVISE` without blocks, and a block missing a field, naming the
  missing fields.
- **AC-GW-014:** The security-reviewer gate shall allow findings that each
  have a severity and either `file:line` or an explicit evidence gap, and an
  explicit statement of no findings; it shall block a finding without
  severity, a finding without evidence, and a message with neither.
- **AC-GW-015:** When `stopHookActive` is true, every gate shall allow the
  stop, even for a malformed message.
- **AC-GW-016:** When stdin is not valid JSON, is not an object, has no
  `lastAssistantMessage`, or the role is unknown, every gate shall exit 0
  without output (fail-open).
- **AC-GW-017:** Every token the gates require shall still appear in the
  corresponding `hosts/grok/dist/agents/<role>.md`.

## plan mode 防護（G3）

- **AC-GW-020:** When `permissionMode` is not `plan`, the guard shall allow
  every `spawn_subagent` call.
- **AC-GW-021:** While `permissionMode` is `plan`, an explicit
  `capability_mode` shall decide: `read-only` and `execute` allow,
  `read-write` and `all` deny.
- **AC-GW-022:** While in plan mode with no `capability_mode`, the guard
  shall read `default_capability_mode` from
  `<grok-home>/roles/<subagent_type>.toml`: the installed read-only roles
  and `verifier` allow, `executor`, `mech-executor` and `security-executor`
  deny.
- **AC-GW-023:** Without a role file, built-in `explore` and `plan` allow,
  `general-purpose` and an omitted `subagent_type` deny.
- **AC-GW-024:** The guard shall fail open on invalid JSON, a non-object
  `toolInput`, an unknown type without a role file, a malformed role TOML,
  and a `subagent_type` that is not a plain name.
- **AC-GW-025:** The grok home shall be selectable by `--grok-home`, then
  `PILOTFISH_GROK_HOME`, then `GROK_HOME`, then `~/.grok`.
- **AC-GW-026:** The deny reason shall tell the model to leave plan mode
  first.
- **AC-GW-027:** The hook scripts shall import only the Python standard
  library, and the PreToolUse entry shall use the anchored matcher
  `^spawn_subagent$`.

## installer（G2）

- **AC-GW-030:** Without `--apply`, the installer shall write nothing under
  the grok home, including no backup directory.
- **AC-GW-031:** After `--apply`, every installed file shall have the same
  SHA-256 as the committed dist, and the rules marker shall equal
  `hosts/grok/VERSION`.
- **AC-GW-032:** Before replacing a file, the installer shall copy the
  files it will replace and `config.toml` to
  `<grok-home>/backups/shoal-<timestamp>/`.
- **AC-GW-033:** When `[subagents.toggle]` sets a shoal role to `false`,
  the dry-run shall flag it; `--apply` without `--fix-toggles` shall leave
  `config.toml` byte-identical.
- **AC-GW-034:** `--fix-toggles` shall delete only the lines that set a
  shoal role to `false` in `[subagents.toggle]`; every other byte of
  `config.toml` shall be preserved, and it shall abort when the minimal edit
  cannot be applied.
- **AC-GW-035:** After `--apply --fix-toggles`, `--restore <backup-dir>
  --apply` shall bring `config.toml` back byte for byte and remove the files
  the install created.
- **AC-GW-036:** `--uninstall --apply` shall remove only shoal's files and
  shall not modify `config.toml` or other files in the shared directories.
- **AC-GW-037:** The installer shall not open, read or modify credential,
  session, history or auth files placed in the grok home.
- **AC-GW-038:** The installer shall install what is committed at `HEAD`,
  not the working tree.
- **AC-GW-039:** When the existing rules file has more than one begin
  marker or an unmatched marker, the installer shall stop before writing.
- **AC-GW-040:** Running `--apply` twice shall skip every file the second
  time and create no second backup.

## 文件與版本（G4）

- **AC-GW-050:** The root `VERSION` shall be `1.1.0`, and `CHANGELOG.md`
  shall have a `## v1.1.0` section and no `## Unreleased`.
- **AC-GW-051:** `upstream.lock` shall record the grok host version
  `1.0.6-shoal.1`, with upstream `Nanako0129/pilotfish-grok`.
- **AC-GW-052:** `README.md` shall link to `Nanako0129/pilotfish-grok`, list
  `tools/install_grok.py` as the grok install path, and `INSTALL.md` shall
  have a grok section.
