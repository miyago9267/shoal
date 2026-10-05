---
title: Dispatch 強制與權限補強 - 進度
status: in-progress
created: 2026-10-05
updated: 2026-10-05
---

<!-- markdownlint-disable MD025 -->

# 進度

規格見 [SPEC.md](./SPEC.md)，live 實測結果見 [E0-RESULTS.md](./E0-RESULTS.md)。

## E0 實測（完成）

五個 host 的 deny 能力、id 欄位、subagent 與 role 辨識、派工與編輯工具都已實測，
結果在 [E0-RESULTS.md](./E0-RESULTS.md)。對設計的影響（`#direct` 改環境變數、agy 固定
shadow、Codex 用 `turn_id` 與 patch 標頭、grok 相容掃描、OpenCode id 含底線）已納入 E1/E2。

## E1 核心與 Claude adapter、E2 Codex/grok/agy adapter（程式與測試完成，Jev provider 另案）

新增：

- `hooks/shoal_guard.py`：單檔、標準函式庫、Python 3.9 語法；`--host claude|codex|grok|agy`。
- `tests/fixtures/guard_vectors.json`：95 組 normalized-event 層級的共用向量（TypeScript 移植沿用）。
- `tests/guard_vectors_helper.py`：向量 replay；`tests/test_shoal_guard.py`：43 個測試
  （向量 replay、role 表對照 `core/roles.toml` 與各 `hosts/*/binding.toml` 的 `[extra_roles.*]`、
  四個 host 的真實 payload 欄位、deny 輸出格式、CLI 失效安全、log 欄位白名單）。
- `tools/guard_parity.py`：一次性對照腳本，不進 CI。

測試：`python3 -m unittest discover -s tests` 全綠（含既有測試）。

決策與偏差：

- 分類 provider 的 turn 檔讀 `turn_id`，相容舊的 `prompt_id` key（dotfile Jev 改寫前不必同步）。
- `SHOAL_GUARD` 設成無法辨識的值時視為 shadow（沿用舊 guard）；未設定或空字串才用 host 預設。
- `SHOAL_GUARD_MAX_FILES` 不是整數時 fail-open 並記
  `skip_reason=invalid_config`（舊 guard 同樣在該分支丟例外而放行）。
- agy 固定 shadow 只壓過 `enforce`；`off` 仍然關閉，保留 rollback。
- Workflow 沒有 role，不解鎖本輪（屬於「只有 write 等級 role 才解鎖」）。
- agy（live probe，agy 1.2.16）：`PreInvocation` 每次模型呼叫都會觸發，
  `invocationNum` 只在 turn 開頭是 0，所以只有 `invocationNum == 0` 算 turn
  boundary，turn id 為 `conversationId:initialNumSteps`；`invocationNum > 0`
  不重設 state，tool payload 不帶 turn id，沿用目前 state。
  `invoke_subagent` 的 role 取 `args.Subagents[].TypeName`（退而用 `Role`），
  列出的每個 subagent 都是 write 等級才解鎖，有一個不是就不解鎖。

### 與 dotfile guard 的對照

`python3 tools/guard_parity.py`（Claude 向量 52 組加 1 組 `#direct` prompt
情境；排除 subagent 規則、state 路徑與檔案安全、`SHOAL_GUARD=""` 這幾類
舊 guard 沒有對應行為的向量）：

```text
vectors replayed: 52 (+1 extra #direct scenario)
steps compared: 208  identical: 191  different: 17  unmapped: 0
  R2 #direct replaced by SHOAL_GUARD_DIRECT     6
  R2 read-only dispatch no longer unlocks       4
  R2 realpath                                   7
  - direct_env_allows_unlimited (3 steps): old=deny new=allow [R2 #direct replaced by SHOAL_GUARD_DIRECT]
  - extra_prompt_direct_marker (2 steps): old=allow new=deny [R2 #direct replaced by SHOAL_GUARD_DIRECT]
  - path_dotdot_dedupes_with_plain_path (1 step): old=deny new=allow [R2 realpath]
  - path_dotdot_out_of_tmp_is_not_exempt (1 step): old=allow new=deny [R2 realpath]
  - path_relative_uses_cwd (2 steps): old=deny new=allow [R2 realpath]
  - path_symlink_alias_counts_once (1 step): old=deny new=allow [R2 realpath]
  - path_symlink_into_tmp_is_not_exempt (1 step): old=allow new=deny [R2 realpath]
  - path_symlinked_ai_dir_is_not_exempt (1 step): old=allow new=deny [R2 realpath]
  - r1_direct_env_allows (1 step): old=deny new=allow [R2 #direct replaced by SHOAL_GUARD_DIRECT]
  - r1_dispatch_scout_does_not_unlock (1 step): old=allow new=deny [R2 read-only dispatch no longer unlocks]
  - r2_dispatch_readonly_roles_do_not_unlock (1 step): old=allow new=deny [R2 read-only dispatch no longer unlocks]
  - r2_dispatch_scout_does_not_unlock (1 step): old=allow new=deny [R2 read-only dispatch no longer unlocks]
  - r2_dispatch_workflow_without_role_does_not_unlock (1 step): old=allow new=deny [R2 read-only dispatch no longer unlocks]
```

所有差異都對應到 SPEC R2 的三項變更，沒有未標註的差異。

## E5 程式（installer，2026-10-05，未 commit，live 安裝待 commit 後）

任務拆解與驗收見 [TASKS.md](./TASKS.md)、[TESTS.md](./TESTS.md)。

- Codex：guard 是獨立的 projection ID `shoal-guard-v1`（`install/hook_registration.py`），
  script 裝到 `<codex-home>/hooks/shoal_guard.py`，`hooks.json` 加
  `UserPromptSubmit` 與
  `PreToolUse`（matcher
  `^(apply_patch|spawn_agent|collaborationspawn_agent)$`，Codex 以 regex
  比對 tool 名稱），state 新增 `guard_registration` 與 target `hooks/shoal_guard.py`
  （兩者必須同時存在，舊 state 沒有也合法）。reinstall 已安裝的 home 會補上 script 與
  groups，不觸發 `installed_hook_drift`。不寫 hook trust，INSTALL.md 寫明用 `/hooks` 核准一次。
- 偏差一：群組定義放在 `hook_registration.py`，不改 `templates/hooks.json`。LOCK.json 對該檔的
  預算是 36 行、1500 bytes、最多改 4 行與 500 字元，加兩個群組（含 commandWindows）放不下，
  而 `--allow-lock-update` 需要使用者核准。代價是新安裝的 `hooks.json` 不再逐位元組等於
  template（template 加上 guard 群組）。`hosts/codex/VERSION` 仍依 Decision 5 bump 到 1.8.3
  （marker、`plugin.json`、`PILOTFISH_PLUGIN_VERSION`、golden、changelog），prompt 文字不變。
- 偏差二：Codex 沒有 uninstall 指令，disable 靠 `SHOAL_GUARD=off`，rollback 靠既有的 transaction
  與備份機制（寫入失敗時會移除新增的 script）。
- `install/stage_smoke_home.py`：layout 與 state 驗證容許 guard script 與 `guard_registration`。
- Grok：`tools/render.py` 從 `hooks/shoal_guard.py` 產生 dist 內的副本（`render --check`
  擋手改），
  `hosts/grok/src` 不放副本。hook 以 `env`（`SHOAL_GUARD_HOST=grok`）傳 host，因為 grok 直接
  exec 路徑、帶參數時是否解析相對路徑未記載（同 grok-workflow G3）；`shoal_guard.py` 因此多了
  `--host` 缺席時讀 `SHOAL_GUARD_HOST` 的 fallback。`install_grok.py` 增加 dist 副本與同 commit
  來源的一致檢查。`hosts/grok/VERSION` 沒有 bump（見下）。
- Claude、agy：新增 `tools/install_hooks.py`；腳本取自 committed HEAD，entry 以
  `shoal_guard.py --host` 為擁有標記，備份在 `${XDG_STATE_HOME}/shoal/install-hooks/backups/`。
  `--uninstall` 不刪腳本（兩個 host 共用）。`hosts/claude/dist` 不放 settings snippet。

未決：grok host 的 VERSION 未 bump（Decision 5 要求受影響 host 各自 bump；會牽動 rules
marker、golden、`upstream.lock`、README 與數個固定版本字串的測試，建議 commit 前一次處理）。
SPEC 的 v1.3.0 CHANGELOG 段與根目錄 `VERSION` 未動。

## E3 OpenCode TypeScript 移植（完成；agy adapter 已在 E2 完成）

新增與變更（`hosts/opencode/plugin/`，版本 0.1.0 到 0.2.0，沒有測試釘住舊版本）：

- 修正 live 載入失敗：OpenCode 把入口 module 的每個 export 都當 plugin function，
  bundle 原本還 export 了 symbol 與 `createPilotfishRouteTool`。原入口內容搬到
  `src/plugin/pilotfish-plugin.ts`（helper 與 registration key 留在這裡，測試從這裡 import），
  `src/plugin/pilotfish-opencode.ts` 變成只有
  `export default PilotfishOpenCodePlugin` 的薄入口。
  入口路徑與 bundle 檔名都沒變，所以 `install.sh`、`install_global.sh`、
  dotfile `install-pilotfish.sh` 的 `bun build` 入口（同一路徑）都不用改。
- `src/guard/core.ts`：`hooks/shoal_guard.py` 的 TypeScript 移植（同一組
  normalized-event 語意、訊息、mode、`SHOAL_GUARD_*` 環境變數）。state 檔防護用
  node fs 實作：目錄 0700、檔案 0600、
  `O_NOFOLLOW`、uid 檢查、上層不得是 symlink、XDG 後備、log 欄位白名單、1 MiB 上限，
  state 目錄同為 `${XDG_STATE_HOME or ~/.local/state}/shoal/guard`，與分類器的 turn 檔共用。
  `realpath` 以自寫的 lenient 版本處理不存在的路徑與 dangling symlink（對齊 Python 非 strict 行為）。
- `src/guard/opencode.ts`：adapter。`chat.message` 是 turn 邊界（turn id 為 messageID），
  `tool.execute.before` 丟 `Error` 擋下；session id 用 `input.sessionID`；
  `client.session.get` 的 `parentID` 不為 null 即 subagent，role 取 session 的 `agent`
  （退而用該 session 第一則 `chat.message` 的 agent），每個 session 快取，查詢有 3 秒 timeout，
  失敗一律 fail-open 並記 `skip_reason=exception`。編輯工具：`apply_patch`（`patchText` 標頭，
  與 Python codex adapter 同一個規則）、`write`、`edit`、`multiedit`（`filePath`）；派工工具 `task`
  （`subagent_type`）。其他工具不查 session。OpenCode 預設 shadow（E6 才切 enforce）。
- 與 `pilotfish_route` 的去重共用同一個 `globalThis` 登記表，guard 用 `guard:<dir>` key，
  舊版 bundle 先載入時不會擋掉 guard。

測試：`bun test` 143 pass、2 skip（既有 live 測試）、0 fail；`bun run typecheck` 乾淨；
`tests/guard-vectors.test.ts` 重播同一份 `tests/fixtures/guard_vectors.json` 的 95 組向量，
全部適用、沒有略過（檔案 owner 不同的向量用 `setOwnerResolverForTests` 模擬另一個 uid），
並比對 `ROLE_ACCESS` 與 Python 表一致；`tests/guard-opencode.test.ts` 測 adapter；
`tests/entry-exports.test.ts` 驗證入口原始檔與實際 bundle 的每個 export 都是 function。

Live（OpenCode 1.18.31，temp 專案，bundle 放 `.opencode/plugins/`）：

- `say hi`：該 bundle 沒有出現 `failed to load plugin`；state 檔與 `event=prompt, decision=state`
  的 log 出現，證明 `chat.message` 與 `client.session.get` 都在 live 運作。
- `SHOAL_GUARD=enforce` 要求連寫三個檔：模型實際使用的是 `apply_patch`，前兩個 `allow/count`，
  第三個 `deny/R2`，被擋後改派 `task`；派 `general` 不解鎖（非 write 等級 role），
  log 欄位皆在白名單內。
- 全域 `~/.config/opencode/plugins/pilotfish-opencode.js` 仍是舊的壞 bundle，會繼續報錯，
  重新安裝屬於 E5。

偏差與限制：

- OpenCode 的 `tool.execute.before` 沒有 turn id，tool 事件沿用 `chat.message` 寫下的 state
  （與 agy 相同的「tool 事件 turn id 可省略」規則，`opencode` 加入該 host 集合）。
- `/loop`、goal continuation 等 model 排程的 prompt 也會觸發 `chat.message`，無法分辨，
  所以 OpenCode 不接受 prompt 內 `#direct`，只用 `SHOAL_GUARD_DIRECT=1`。

## E4 與其餘

binding/render/golden/lock（E4）由另一位 executor 進行，工作樹已有變更，本文件不記錄其狀態。
dotfile 切換與非 Claude host 切 enforce 尚未開始。
