# dispatch guard

## Dispatch guard

Since host 1.8.3 the installer also registers the dispatch guard
(`hooks/shoal_guard.py --host codex`,
[`docs/specs/dispatch-enforcement`](./specs/dispatch-enforcement/SPEC.md))
next to the autoroute gate. It is a separate script with its own projection ID
(`shoal-dispatch-guard-v2`; `shoal-dispatch-guard-v1` and the older
`shoal-guard-v1` to `v5` are upgraded in place, and Codex asks for one
`/hooks` re-approval of the changed `PostToolUse` and new `SessionEnd`
groups) and its own
state entry (`guard_registration`), so the gate
is unchanged. It adds a `UserPromptSubmit` group that records the turn and
reads `#direct`, a `PreToolUse` group with matcher
`^(apply_patch|spawn_agent|collaborationspawn_agent|Bash)$`, and, since 3.4.0,
a `Stop` group for the completion check (below), since the legacy
`shoal-guard-v4` a
`SubagentStart` group without a matcher that tells the guard a dispatched role
has really started (below), and since the legacy `shoal-guard-v5` a
`PostToolUse` group
with matcher `^Bash$` that lets the completion check count a shell call that
really ran (below). The guard is in
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
selectable. R2 still only reminds. Shell-write detection is a literal
reading of the command text (redirects, `tee`, `sed -i`, `perl -i`): writes
through an interpreter such as `python -c` or `node -e`, or through `cp`, `mv`,
`patch` and `dd`, are not caught. The background-shell rule G4 does not exist
on Codex (its shell calls carry no `run_in_background`). The rule is built on
a recorded payload of Codex CLI 0.160.1: the shell tool is `Bash` with
`tool_input.command`, the same `turn_id` is on the prompt and tool events, and
main-session calls have no `agent_id` (keys and types:
`tests/fixtures/codex_payload_shapes.json`;
[`docs/specs/guard-declared-direct/PROGRESS.md`](./specs/guard-declared-direct/PROGRESS.md)).
A foreground `Bash` call that neither declares nor writes a file gets no
opinion and writes no log line (after a change in the turn it records that a
check ran, see the completion check below). An existing home that predates the
guard gains the script and all three groups on the next install; a home
registered by an earlier release is upgraded in place: `shoal-guard-v1` (3.2.0 or
earlier, matcher without `Bash`) has its `PreToolUse` group replaced at the same
position, `v1` and `v2` (3.2.1 to 3.3.1) gain the guard's own `Stop`
group, appended after the existing `Stop` entries, and `v1` to `v3` gain the
`SubagentStart` group (`v3` changes nothing else), and `v1` to `v4` gain the
`PostToolUse` group (an earlier, unreleased `v4` install is upgraded in
place). Every other entry (your own
`Bash` matcher, your own `Stop` hook, the autoroute gate's own `Stop` group) is
left untouched. Re-runs change nothing. The installer does not write hook
trust: after installing **or upgrading to 3.4.0**, approve the new `Stop` hook
once in an interactive Codex session with `/hooks`, as for the autoroute gate.
Without that approval Codex does not run it and the completion check never
fires (nothing else changes). A `PreToolUse` group that is not re-approved
after an upgrade from `v1` leaves the guard blind to `Bash` (declarations then
have no way in, so keep `#direct` and dispatch in mind until you approve).
**Approve the new `SubagentStart` hook once with `/hooks` after upgrading to
`shoal-guard-v4`, and the new `PostToolUse` hook after upgrading to
`shoal-guard-v5`.** The groups you approved before keep their bytes and stay approved.
A dispatched write role unlocks the main session's edit once the role has
started, not at the `spawn_agent` call (docs/specs/guard-every-gate, E3; the
payloads are in `tests/fixtures/codex_subagent_tool_shapes.json`, Codex CLI
0.160.1): the dispatch call is always allowed and only records a pending
dispatch (log `dispatch_pending`); `SubagentStart` (`agent_id`, `agent_type`,
and the main session's `session_id`) releases one pending dispatch per
`agent_id` when its `agent_type` is a write-level role (log `dispatch_started`).
A spawn of an unknown `agent_type` fires no `SubagentStart`, so it never
unlocks. Until you approve the hook the start event never arrives, so the
guard also accepts the first `apply_patch` or `Bash` call that carries an
`agent_id` and a write-level `agent_type` as proof that the role started (that
call is covered by the `PreToolUse` group you already approved); a write role
that makes neither call leaves the main session locked, and `#direct` or
`SHOAL_GUARD_DIRECT=1` still work. The guard cannot read Codex's approval state
(`hooks.state`), so it does not try to detect an old or unapproved
registration. A launch probe
(must exit 0, prints nothing):

```bash
echo '{}' | /usr/bin/env python3 "$SHOAL_TARGET_HOME/hooks/shoal_guard.py" --host codex
```

### Completion check

Since 3.4.0 the guard records, per turn, whether the main session changed files
and whether anything checked the change afterwards (docs/specs/shared-rules,
B2 to B4). A change is a non-exempt `apply_patch` or `Bash` file write that the
guard allowed, or a dispatched write-level role (`executor`, `applier`,
`security-executor`, `sol-executor`; on Codex the dispatch call counts). A check
is a dispatched `verifier` or `watcher`, or a foreground `Bash` call that is
neither a file write nor a `: shoal-direct` declaration, made after the latest
change; a later change clears it. On Claude and Codex (3.6.0 and the guard
projection that was `shoal-guard-v5`)
that shell call counts at its `PostToolUse`, i.e. when it actually ran: a call the
user rejects or that never runs fires no `PostToolUse` and does not count; on
Claude a call that fails (a test run exiting non-zero) fires `PostToolUseFailure`,
which counts the same way, since it did run. The
guard cannot tell whether the new hook is registered or approved, so until a
session has seen its first `PostToolUse` of a main-session `Bash` call, the
`PreToolUse` of that call still counts (the old behaviour; a home that has not
re-approved hooks is not blocked at every `Stop`); after the first one, only
`PostToolUse` counts. Other hosts keep the `PreToolUse` rule. A `PostToolUse`
from a subagent, a background `Bash`, a file write or a declaration is not a
check. When the main session ends the turn with a
change and no check, the `Stop` hook answers
`{"decision":"block","reason":"..."}` once per turn: run a verification, or say
in the report that the change is unverified. The block is skipped when Codex
reports `stop_hook_active` (the retry after a block), for a `Stop` of another
turn, for unreadable state or an unexpected payload, in `SHOAL_GUARD=shadow`
(the log gets `would_block`), with `SHOAL_GUARD=off`, and with
`SHOAL_GUARD_STOP=off`. The switch defaults to `on`, exists on Claude, Codex and
Grok and agy (both default to logging `would_block` only until
SHOAL_GUARD_STOP=enforce), and has no effect elsewhere: OpenCode never blocks
because no end-of-turn payload of its is recorded. On Grok the check is
attached to its
`stop` event (only `reason == end_turn`; a second `stop` fires at session end)
but its `{"decision":"block"}` answer has not been exercised on a real Grok yet,
so by default it only logs `would_block`; set `SHOAL_GUARD_STOP=enforce` (with
the guard in `enforce`) to let it block once the live check shows Grok honours
it. The autoroute gate's `Stop`
group (Plan review and model escalation) is a separate script and is not
changed.

### Guard only, without running the installer

When `install/install.py` cannot be reconciled with the Codex home (for
example a locally modified `shoal_autoroute_gate.py` that the installer
would replace), `tools/install_hooks.py --host codex` manages only the guard.
It writes the same `shoal-dispatch-guard-v2` groups (including `commandWindows`;
a
legacy `shoal-guard-v1` to `v4` group is replaced in place) into
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

## Claude Code 與 Gemini/agy 的 dispatch guard

Claude Code 與 Gemini/agy 沒有自己的 shoal installer，dispatch guard 由
`tools/install_hooks.py` 安裝（Python 3.9 以上，需要 `git`）。和 `install_grok.py`
一樣，沒有 `--apply` 一律是 dry-run。

- 腳本取自 committed `HEAD` 的 `hooks/shoal_guard.py`（`git show`，不吃工作樹；HEAD
  沒有就中止），安裝到 `${XDG_DATA_HOME:-~/.local/share}/shoal/guard/shoal_guard.py`
  （0755）。

- 只有 command 含 `shoal_guard.py --host` 的 handler 算 shoal 的；其他 hook、其他 key、
  key 順序與 2 空格縮排都原樣保留。重複執行不會改變結果，也不會產生新備份。

- 寫入前把原檔備份到 `${XDG_STATE_HOME:-~/.local/state}/shoal/install-hooks/backups/`
  （目錄 0700、檔案 0600），寫入後重新讀檔驗證：shoal handler 數量、其餘內容未被改動、
  腳本與 `HEAD` 相同；不符 exit 1。設定檔不是合法 JSON 或結構不符預期時 exit 2，不寫入。

## Claude 上 guard 的行為（3.0.0 起）

[`docs/specs/delegation-default`](./specs/delegation-default/SPEC.md)
讓 Claude 上的 main session 規則回到 deny；Grok、agy、OpenCode 的 R1 現在也預設 deny（見下表與各自的段落）。
3.2.1 起 Codex 的 R1 與 G5 和 Claude 一樣（見下）。
3.2.0 起 R1 與 G5 不再等分類來源（宣告）；3.3.0 起預設改成 `strict`：main 沒派 write role、
使用者也沒有 `#direct` 就不能改檔，宣告不再是出口
（[`docs/specs/guard-declared-direct`](./specs/guard-declared-direct/SPEC.md)）。

### main 改檔規則的模式：`SHOAL_GUARD_R1`

| 值 | 預設於 | R1（改檔工具）與 G5（寫檔的 `Bash`） |
| --- | --- | --- |
| `strict` | Claude、Codex（3.3.0 起）、Grok、agy、OpenCode（3.6.0 起） | enforce 時 deny，除非本輪有：已派出的 write role，或使用者的 `#direct`（或 `SHOAL_GUARD_DIRECT=1`），或目標在豁免路徑。`: shoal-direct ...` 只是普通的空指令（不寫 state、不寫 log、不放行），分類檔（包含 `parent_local`）沒有作用。訊息只列兩個出口：派 `executor`／`applier`，或請使用者加 `#direct`。shadow 記 `would_deny` |
| `declare` | 無（3.2.x 的預設，可選） | enforce 時 deny，除非本輪有：已派出的 write role、使用者的 `#direct` 或 `SHOAL_GUARD_DIRECT=1`、main 的宣告（下一節），或分類檔的 `role` 是 `parent_local`。沒有分類檔、或其他 `role`，都不影響結果。shadow 記 `would_deny` |
| `classified` | 無（可選；3.6.0 前的 OpenCode 預設） | 3.1.0 的規則：只有分類檔把本輪標成 `judgment` 或 `mechanical` 時才擋（Claude：deny；其他 host 只提醒） |
| `off` | 無 | 關掉 R1 與 G5。硬規則（LEAF、VERIFY_EDIT）、G4、R2 不受影響 |

未設定、空字串、無法辨識的值，或在不能閘控的 host 上設 `strict`／`declare`，都用該 host 的預設
（所有 host 都是 `strict`；3.6.0 前 OpenCode 是 `classified`）。
`declare`、`classified`、`off` 的行為與 3.2.1 相同。
被 deny 的改檔與 shell 寫檔不計入 R2 的檔案數，也不會在同一次呼叫送出 R2 提醒。

### subagent 改檔規則：`SHOAL_GUARD_SUBAGENT_WRITE`

E1（見
[`docs/specs/guard-every-gate`](./specs/guard-every-gate/SPEC.md)）：
不是 shoal 可寫 role 的
subagent（含沒有 agent type 的）用編輯工具或 shell 字面寫檔，且目標不在豁免路徑時，enforce 下 deny、
shadow 記 `would_deny`（規則 id `E1`）。verify 等級的 role 的編輯仍是 `VERIFY_EDIT`。

| 值 | 效果 |
| --- | --- |
| `on`（所有 host 的預設） | 啟用 E1 |
| `off` | 沒有 E1，行為與以前完全相同 |

未設定時所有 host 都是 `on`（Codex 從 legacy 的 `shoal-guard-v4` 起）；
明確設 `on` 或 `off` 在任何 host 都優先。Codex 的內建 `worker`、`default`、
`explorer` 與其他不是 shoal 可寫 role 的 agent type 都適用同一條規則。

出口：派 shoal 可寫的 role；把 agent type 加進 `SHOAL_GUARD_WRITE_AGENTS`（逗號分隔，去掉空白，
比對原始 type 或去掉 `shoal:` 前綴的 type，例如 Workflow 預設的 `workflow-subagent`）；設
`SHOAL_GUARD_DIRECT=1`；或在 Claude、Codex、Grok、OpenCode 上，啟動這項工作的那一回合
prompt 帶 `#direct`（agy 的 payload 沒有 prompt 文字，不支援）。
最後一項靠 subagent 事件帶的 `session_id` 與 `prompt_id` 對到主 session 的 state 檔，其中
`direct_turns` 保存最近 16 個帶 `#direct` 的回合 id，所以背景 Workflow 的子 agent 在主 session 已進入
下一回合後才改檔，仍以啟動它的那一回合為準。state 檔讀不到或內容壞掉一律視為未放行。
Codex 的 subagent 有自己的 `turn_id`（和主 session 不同，同一個 subagent 內不變），所以改用
`agent_id`：`SubagentStart`（帶主 session 的 `session_id`）發生時，若主 session 當下這一回合帶 `#direct`，
就把該 `agent_id` 記進 state 檔的 `direct_agents`（最近 32 個），之後這個 agent 的改檔以此放行；
之後的非 `#direct` 回合才啟動的 agent、其他 session 的 agent 都不放行，state 讀不到或壞掉一律視為未放行。
Grok 在 `subagent_start` 時記下當下 main 那一回合有沒有 `#direct`（`state/grok.agents.json`）；
OpenCode 以 child session 建立當下 main 的那一回合為準。agy 沒有 `#direct`，所以不放行 subagent。
派出非 shoal 的 agent type 仍然允許，也不會解鎖 main 的改檔。
Claude 上 `watcher`、`verifier` 把輸出導到 `/tmp`、`/private/tmp`、`$TMPDIR`（含 Claude 的 scratchpad）
屬豁免路徑；導到 repo 內的路徑會被 E1 擋下。

**已知限制：可寫權限以 host 回報的 agent type 名稱為準。** 專案裡自訂、但取了 shoal 可寫 role 名稱
的 agent（例如叫 `executor` 的專案 agent）會被當成那個 role，E1 不擋它，它也能解鎖 main。Grok 還會把
通用 subagent 型別改寫成 `shoal:executor`（live 觀察），所以通用 subagent 的 `subagent_start`
可能就帶著可寫 role 的名稱。guard 看不到實際載入的 agent 內容。這個前提是否成立尚未驗證（見
[PROGRESS.md](./specs/guard-every-gate/PROGRESS.md)）。

### 宣告

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

### 分類檔（公開的選用介面）

任何工具都可以寫分類檔；shoal 不依賴也不安裝任何寫入者（dotfile 的 Jev 只是其中一個）。

- 路徑：`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/turns/<session_id>.json`
  （`session_id` 是 hook payload 的 `session_id`；目錄 `0700`，檔案屬於同一個 uid，guard 會把
  檔案權限收到 `0600`；symlink 與他人擁有的檔案一律忽略）。
- 內容：`{"turn_id": "<這一輪的 id>", "role": "judgment" | "mechanical" | "parent_local"}`。
  `turn_id` 是 Claude 的 `prompt_id`，要等於 guard 目前記錄的那一輪，不同就當成過期而忽略
  （舊鍵名 `prompt_id` 也接受）。其他欄位忽略，檔案上限 64 KiB。
- `strict` 模式下分類檔沒有作用（`parent_local` 也不放行）。`declare` 模式下它只能放寬：`parent_local` 視同已宣告；`judgment`、`mechanical`、其他值、
  或沒有檔案，結果與「沒有檔案」相同。`classified` 模式下行為與 3.1.0 相同（見下表）。

### 規則總表

| 規則 | 條件 | Claude／Codex（enforce） | Claude／Codex（shadow） | Grok、agy、OpenCode（預設 enforce，與 Claude 相同；OpenCode 見下一節） |
| --- | --- | --- | --- | --- |
| R1 | `strict`：本輪沒有派工或 `#direct`；`declare`：本輪沒有派工、`#direct`、宣告或 `parent_local`；`classified`：分類檔把本輪標成 `judgment` 或 `mechanical` 且沒派工。路徑不在豁免範圍 | deny main 的 `Edit`、`Write`、`MultiEdit`、`NotebookEdit` | 記 `would_deny` | deny（`strict`；選 `classified` 時只提醒） |
| R2 | 本輪 main 直接改到第 3 個不同的檔案 | 只提醒 | 只提醒 | 只提醒 |
| G4 | main（payload 沒有 `agent_id`）呼叫 `Bash` 且 `run_in_background: true`（只有 Claude；Codex 沒有這個欄位） | deny，訊息要求改派背景的 `watcher` | 記 `would_deny` | 無此規則 |
| G5（3.0.1 起） | R1 的條件成立，且 main 前景呼叫的 `Bash` 指令字面上寫檔（見下） | 以 R1 的規則 id 與訊息 deny | 記 `would_deny`（規則 `R1`） | 同左（Grok `run_terminal_command`、agy `run_command`、OpenCode `bash`） |

- 派出 `watcher`、`researcher`、`scout` 等非 write role 不會解除 R1（任何模式）；G4 不因任何派工解除。
  派出 `executor`、`applier`、`security-executor` 之後，本輪的改檔與 shell 寫檔放行。
- 放行：使用者 prompt 內獨立的 `#direct`（區分大小寫的字面比對；`#directory`、
  `x#direct`、`#direct-ly` 不算）只放行那一輪，下一輪失效，同時關掉那一輪的 R1、R2 與 G4；
  `SHOAL_GUARD_DIRECT=1` 對整個 session 放行 R1、R2、G4。guard 只記「這輪有 `#direct`」的旗標，
  不記錄 prompt 內容。
- 快速模式：prompt 內獨立的 `#fast`（偵測規則同 `#direct`）讓這個 session 之後的每一回合都當成帶 `#direct`，記在
  state 的 `fast`，跨回合保留，直到獨立的 `#strict`（同一個 prompt 兩者都有時以 `#strict` 為準）；
  `SHOAL_GUARD_FAST=1` 對每個 session 生效，給沒有 prompt 文字的 agy。放行的範圍與 `#direct`
  完全相同（main 的 R1、R2、G4、G5，以及 E1 的 subagent 放行，Codex、Grok 把 `#fast` 當成 `#direct`
  回合）；LEAF、VERIFY_EDIT 與完成檢查不變。log 在開啟時多一個 `fast: true`，R1、E1 的 deny 訊息在有
  prompt 文字的 host 多提示 `#fast`。
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
- **派工要真的啟動（M11）：Claude 從 3.3.1 起實作，Codex 從 `shoal-guard-v4` 起實作。**
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
  - Codex（`shoal-guard-v4` 起）：同樣只記待啟動的派工，`SubagentStart` 的
    `agent_type` 是 write 等級
    才釋放，每個 `agent_id` 只釋放一筆（log：`skip`／`agent_already_started` 表示重複）。事件的 `turn_id`
    是 subagent 自己的回合，不拿來和主 session 比對。啟動失敗（未知的 `agent_type`）沒有 `SubagentStart`，
    所以不放行。舊註冊或尚未在 `/hooks` 核准新 hook 時收不到啟動事件：guard 也接受該 role 的第一個帶
    `agent_id` 與 write 等級 `agent_type` 的 `apply_patch`／`Bash` 呼叫當作啟動證據；兩者都沒有就保持鎖住，
    出口只剩 `#direct` 與 `SHOAL_GUARD_DIRECT=1`。guard 讀不到 Codex 的核准狀態，不做舊註冊偵測。
  - OpenCode：`task` 呼叫只記待啟動；帶 `parentID`（就是 main session）與 write role 的
    `agent` 的 `session.created` 才放行（`client.session.get` 看到未知的子 session 時等同啟動）。
    role 名稱不存在或權限被擋的派工沒有 `session.created`，所以不放行。
  - Grok：`spawn_subagent` 只記待啟動；`subagent_start` 事件（以 main 的 session id 送出，帶 `subagentId`
    與 `subagentType`）才釋放。
  - agy：`invoke_subagent` 只記待啟動；新 conversation 的 `SessionStart` 認領後，write 類別才釋放。
  - 沒有任何 host 還在派工呼叫當下解鎖：五個 host 都以啟動事件為準（`START_UNLOCK_HOSTS`）。
- **OpenCode（TypeScript 移植）：shell 與 `apply_patch` 也在 guard 內，預設 enforce。**
  依據是 `tests/fixtures/opencode_guard_event_shapes.json`（opencode 1.18.31，
  2026-10-13 實測）。
  - main 與 subagent：`session.created` 事件帶 `parentID`（main session）與 `agent`（role），沒收到事件時
    用 `client.session.get` 補查；有 `parentID` 的是 subagent，role 就是 `agent`。查不到的未知 session
    是 fail-open（不擋，log 一筆 `skip`／`exception`）。
  - main 的 `write`／`edit`／`multiedit`／`apply_patch` 與寫檔的 `bash` 走 `strict`（沒設
    `SHOAL_GUARD_R1` 時 adapter 自動用 `strict`；明確設 `classified` 或 `off` 照辦）：本輪沒有已啟動的
    write role、也沒有 `#direct` 就 deny。讀取類 `bash` 不受影響。
  - subagent 的改檔與 shell 寫檔：role 不是 shoal write role（含內建的 `general`、`explore`）就 deny（E1），
    預設開（`SHOAL_GUARD_SUBAGENT_WRITE=off` 可關）。出口：`SHOAL_GUARD_WRITE_AGENTS`、
    `SHOAL_GUARD_DIRECT=1`、豁免路徑，以及 `#direct`。
  - `#direct`：main 的 `chat.message` 文字有獨立的 `#direct` 就放行那一輪 main 自己的改檔；
    subagent 則看子 session 建立當下 main 的那一輪，若有 `#direct` 也放行（以 child sessionID 記錄那一輪）。
  - 完成檢查（Stop）在 OpenCode 不可用，見下表。

OpenCode 事件與 guard 的對照（`docs/DESIGN-INVARIANTS.md` 第 3 條要求的清單）：

| 事件 | 掛上？ | 規則 | 原因或證據 |
| --- | --- | --- | --- |
| `tool.execute.before`（`write`、`edit`、`multiedit`、`apply_patch`） | 是 | R1（main）、E1、VERIFY_EDIT | throw 即 deny；`apply_patch` 的路徑取自 `patchText` 標頭 |
| `tool.execute.before`（`bash`） | 是 | G5（main，以 R1 訊息）、E1 | subagent 的 `bash` 也帶完整 `args.command`（fixture `q2`） |
| `tool.execute.before`（`task`） | 是 | LEAF、派工待啟動 | `subagent_type` 不會先驗證，失敗的派工只留下這個事件 |
| `event` `session.created` | 是 | 啟動（M11／E3）、main 與 subagent 的辨識 | 帶 `parentID` 與 `agent`；失敗的派工沒有此事件 |
| `chat.message` | 是 | 回合邊界、`#direct` | `output.message.id` 是回合 id，`output.parts[].text` 是 prompt |
| `command.execute.before` | 否 | 無 | 外掛 API 有此 hook，fixture 只列名稱，未實測是否觸發與 payload；沒有規則需要 slash command 事件，改檔與 shell 閘門都在 `tool.execute.before` |
| `shell.env` | 否 | 無 | fixture 記錄有觸發，但沒有記 payload 形狀，能否擋未實測；沒有規則需要 |
| `chat.params`、`chat.headers`、`experimental.chat.system.transform`、`experimental.chat.messages.transform`、`experimental.text.complete`、`experimental.provider.small_model`、`experimental.session.compacting`、`experimental.compaction.autocontinue`、`tool.definition`、`config`、`tool`、`auth`、`provider`、`dispose` | 否 | 無 | fixture 只列名稱（`chat.params`、`system.transform`、`text.complete` 有觸發）；沒有規則與 model 參數、system prompt、compaction、provider 設定相關，payload 未實測 |
| `tool.execute.after` | 否 | 無需 | 失敗的派工不觸發，啟動已由 `session.created` 判斷 |
| `event` `session.idle`／`session.status` | 否 | 完成檢查（B2、B3） | `event` hook 的型別是 `(input) => Promise<void>`，沒有回傳值也沒有 output，無法擋；`session.idle` 在 turn 結束後才發。以 `session.promptAsync` 重新提示的行為沒有實測，不實作 |
| `permission.ask` | 否 | 無 | 尚未量測，沒有證據顯示它能區分 main 與 subagent |

- **完成檢查（3.4.0 起，Claude 與 Codex；Grok、agy 預設只記錄；
  docs/specs/shared-rules B2 到 B4）。** guard 逐回合記兩件事：
  - `changed`：main 的改檔工具或 shell 寫檔被放行且目標不是豁免路徑；或可寫的 role 算「已派工」
    （各 host 都在啟動事件釋放待啟動派工的那一刻；沒有 host 在派工呼叫當下算）。
  - `checked`：在最近一次 `changed` 之後，派出或啟動了 verify 等級的 role（`verifier`、`watcher`），
    或 main 執行了前景 `Bash`、而且那個指令既不寫檔也不是 `: shoal-direct` 宣告。
    Claude 與 Codex 在 `PostToolUse`（指令真的跑了）才算，使用者拒絕或沒跑的呼叫
    不算；guard 看不出新事件有沒有註冊或核准，所以同一個 session 第一次看到
    `PostToolUse` 之前，`PreToolUse` 的前景 `Bash` 仍算（後備，舊註冊不會每次
    Stop 都被擋），看過之後只認 `PostToolUse`；其他 host 維持 `PreToolUse`。
    之後再發生一次
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
  - 開關：`SHOAL_GUARD_STOP=on|off`（預設 `on`；其他值視為 `on`），對 Claude、Codex、Grok、agy 有效
    （Grok、agy 預設 shadow，`SHOAL_GUARD_STOP=enforce` 才擋）。agy 的 `Stop` 已掛上
    （只看讓整個 session 閒置的那一次，`fullyIdle: true`）；OpenCode 沒有已記錄的結束事件 payload，不啟用，永遠不擋。
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

## Guard chain：外部 guard 以設定掛上

shoal 只開一個擴充點：guard chain。外部 guard 不改 shoal 的程式碼，只在 installed manifest
（`${XDG_DATA_HOME:-~/.local/share}/shoal/modules.json`，測試時可用 `SHOAL_GUARD_CHAIN_FILE`
指定別的路徑）的 `chain` 陣列登記一筆：

```json
{"chain": [
  {"name": "my-guard", "command": ["/usr/local/bin/my-guard", "check"],
   "hosts": ["claude", "codex"], "order": 10, "events": ["PreToolUse", "PostToolUse"]}
]}
```

- `command` 是 argv 清單，直接 exec（不經 shell），cwd 與環境變數沿用 hook 的。`hosts` 含目前 host 的
  項目才會跑，依 `order` 由小到大。欄位不合格的項目會被略過。env 除了繼承的之外，另注入
  `SHOAL_GUARD_HOST`（host 名稱）與 `SHOAL_GUARD_EVENT`（事件的標準名稱，例如 `PreToolUse`）。
- `events` 是成員要收的事件，預設 `["PreToolUse"]`；可填 `PreToolUse`、`PostToolUse`、
  `UserPromptSubmit`、`SessionEnd`、`Stop`，沒登記的事件不會轉給該成員，不認得的名字會被忽略。
  Claude 的 guard plugin 與 Codex 的 hook 註冊會把改檔工具的 `PostToolUse`、`SessionEnd`
  也送進 guard（Claude 的 `PostToolUse` matcher 是 `Edit|Write|MultiEdit|NotebookEdit`，
  Codex 是 `^(Bash|apply_patch)$`）；
  沒有任何規則、任何成員需要的事件，guard 在讀完 manifest 後立刻結束，不寫 state、不啟動成員。
  OpenCode、Grok、agy 目前仍只轉發既有的事件（OpenCode 只有 PreToolUse），其餘等 shoal-guard M3 再補。
- 成員在 stdin 收到 host 傳給 shoal guard 的原始 payload（同一份 JSON）。OpenCode 沒有 stdin payload，
  收到的是 `tool.execute.before` 的 input 加 `args`，且只涵蓋 guard 會判斷的 edit、bash、task 呼叫。
- 成員要擋時，在 stdout 印 `{"decision": "deny", "reason": "..."}`。
  `{"decision": "allow"}` 或沒有輸出
  都是放行。任一成員 deny 就整體 deny，host 收到的是 guard 自己 deny 用的原生輸出，理由前面加
  name 與冒號（`<name>:`）。只有 `PreToolUse` 的 deny 會擋；`Stop` 維持原本的 block；
  其他事件（`PostToolUse`、`UserPromptSubmit`、`SessionEnd`）的 deny 只記 log、不擋，
  但同樣是第一個 deny 贏：之後的成員不會再跑（前面成員已收集的 `context` 保留）。
- shoal 自己已經 deny 或 block 時不會呼叫成員；任何事件的第一個 deny 之後，後面的成員也不會跑。
  `SHOAL_GUARD=off` 時整條 chain 不跑，`shadow` 時 deny 只記成 `would_deny`。
- 輸出可以多帶 `context`（字串，建議性、不會擋）：Claude 在 `PreToolUse`、`PostToolUse`、
  `UserPromptSubmit` 轉成 `hookSpecificOutput.additionalContext`，多個成員的 context 以換行串起來；
  其他 host 與事件只寫 log（`chain_context`，不含內文），不送給模型。`member`、`version` 只寫進
  log（`chain_report`），其他不認得的欄位一律忽略。`version` 可以是字串或數字
  （如 `1`），數字會轉成字串寫進 log；其他型別忽略。
- fail-open：非零 exit、逾時、輸出不是 JSON 或 decision 不認得，一律當作放行，log 記
  `chain_error` 或 `chain_timeout`。成員 stdout 最多讀 64 KiB，超過就終止該成員並記
  `chain_error`（stderr 丟棄），不會把輸出整個緩衝在 guard 裡。每個成員逾時預設 5 秒
  （`SHOAL_GUARD_CHAIN_TIMEOUT_MS` 可調，上限 8000）。整條 chain 另有總時限：host 的 hook 逾時
  （10 秒）減 2 秒，從 guard 開始判斷算起（`SHOAL_GUARD_CHAIN_BUDGET_MS` 只能再縮短）；剩餘時間用完時，
  後面的成員被略過並記 `chain_budget`（fail-open）。
  每個成員一筆 log，欄位有 `member` 與 `ms`。
- 每個成員多一次 process 呼叫，延遲會加在每次 tool call 上；OpenCode 以 await 執行，同樣如此。
