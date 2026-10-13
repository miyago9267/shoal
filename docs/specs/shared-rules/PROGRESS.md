# shared-rules 進度

## S1（完成，v3.4.0）

- `docs/DESIGN-INVARIANTS.md` 第 4 條改為 D1 的字句，
  `tests/test_delegation_default.py` 的釘住文字同步。
- `docs/specs/core-policy/SPEC.md` 末尾加「修訂：規則共用（2026-10-13）」，
  `docs/specs/milestone-direction-check/SPEC.md` 加註記（「同質化」指抹平
  role 形狀與工具綁定）。`core/README.md` 改指向 shared-rules；渲染器只允許
  Claude 用 core 條款的限制保留到 S4，文字已寫明。

## S2（B1、B5、B6 完成；bootstrap 上限未達）

- B1：`core/policy/bootstrap.toml` 新增 `bootstrap-verify-report`（非
  required，排在 `bootstrap-collect` 之後）。
- B5、B6：`core/contracts/verifier.toml` 新增 `checkpoint-draft-report` 與
  `checkpoint-premise`；`core/policy/extensions.toml` 的
  `direction-checkpoint` 加一句收尾時 main 把回報草稿交給檢查、修正後才回報。
  Claude 的 legacy 對照來源（`hosts/claude/src/...`）與 Codex 的
  `hosts/codex/src/agents/verifier.md` 同步，逐字拼回的測試維持通過。
  `tests/test_direction_milestone.py` 的 M2 逐字測試改為：Claude 的 core 輸出
  含新句，Codex 的 legacy 模板維持原文。
- 這句是 core 文字：五個 host 的 `verifier` 都會帶到，已重新渲染。
- 位元組（渲染後的 Claude bootstrap）：3046（v3.3.1）→ 3103。**沒有達到
  2900。** B1 約 +170，縮短其他條款約 -113，差 203。縮短的條款（前 → 後）：
  - delegate-default：「diagnosing a bug, integrating, and judging stay with
    the main session」→「diagnosing, integrating, and judging stay with
    main」；「including the same change across several files」→「also one
    change across several files」；「test suite」→「tests」。
  - routing：「Route by shape first」→「Route by shape」。
  - outcome：「stops at that boundary」→「stops there」。
  - dispatch-brake：冒號句改為括號句（「the role default, lower for trivial
    ... work」→「(role default; lower if trivial ...」）、「of every call to a
    write-capable role」→「of every write-capable call」。
  - load-skill：刪「for the full policy」、兩句併成一句。
  - 沒有動 required 條款，也沒有刪規則。再縮需要刪掉有意義的內容（剩下的都是
    被測試釘住的句子或 required 條款），選項：把 routing／outcome 兩條移到
    skill、縮減 named roles 清單的寫法，或讓 Codex 的 frame 吃掉差額。
- Prompt lock：`LOCK.json` 沒有變動；`verifier` 與 workflow-extensions 的
  大小仍在上限內（Claude verifier 90 行／6792 bytes，上限 104／7700；
  workflow-extensions 172／9457，上限 180／9600；Codex verifier 90／5702，
  上限 95／6000）。commit 不需要 `Lock-Renewal: approved`。

## S3（實作完成；live 驗收已完成）

- `hooks/shoal_guard.py` 與 `hosts/opencode/plugin/src/guard/core.ts`：state
  新增 `changed`、`checked`、`stop_blocked`；`Stop` adapter（Claude：
  `prompt_id`；Codex：`turn_id`）；`STOP_HOSTS`、`SHOAL_GUARD_STOP`。向量
  `tests/fixtures/guard_vectors.json` 新增 64 筆（Python 與 TypeScript 共用）。
- 閘門條件：同一回合的 state、`changed`、非 `checked`、`stop_hook_active`
  恰為 `false`、enforce、這回合沒擋過、`SHOAL_GUARD_STOP` 不是 `off`。先把
  `stop_blocked` 寫入再輸出 block，寫入失敗就不擋。
- 前景 `Bash`（非寫檔、非宣告）只在 `changed` 已為真且未 `checked` 時才取鎖
  寫 state，其餘只讀一次 state；不寫 log。
- 註冊：`tools/render.py` 的 plugin `hooks.json`、
  `tools/install_hooks.py`（Claude `Stop`）、`install/hook_registration.py`
  （`shoal-guard-v3`；v1、v2 原地升級）。Codex 升級後要用 `/hooks` 核准一次。
- Payload 證據：`tests/fixtures/stop_payload_shapes.json`（2026-10-13 的兩次
  真實執行，只記 key 與型別）。
- Claude 對 `{"decision":"block","reason":...}` 的處理已實測確認（見下方
  「S3 的 live 驗收」）。Codex 的格式與 `shoal_autoroute_gate.py` 相同。
- Live 驗收已執行（改檔後直接結束被擋一次、有檢查時不擋；Claude 與 Codex
  各一次），結果見下方「S3 的 live 驗收」。另外也以暫存 HOME 與
  XDG_STATE_HOME 對真實形狀的 payload 手動餵給腳本。
- 未驗證：Claude 的 `Stop` 的 `prompt_id` 是否等於同一回合
  `UserPromptSubmit` 的 `prompt_id`（假設相等，不相等時完全不擋）。

## S3 的 live 驗收（2026-10-13，v3.4.0，`941c90b`）

紀錄在 `docs/benchmarks/shared-rules-gate/`。Claude 2 次（USD 0.97）、Codex 2 次，四題都符合預期。

- **改完沒檢查就結束**：Claude 與 Codex 各 1 次，prompt 含 `#direct`。guard 放行改檔後，在結束時
  擋下一次（真實的 guard log 各有一筆 `STOP`／`block`）；兩邊的 session 都繼續了一輪，並在回報中
  寫明變更未驗證。同一回合第二次結束沒有再被擋。
- **有檢查就不擋**：Claude 與 Codex 各 1 次。main 派出可寫的 role，之後自己跑了測試指令，沒有任何
  `STOP` 紀錄。
- **輸出格式**：Claude 接受 `{"decision":"block","reason":...}`，stream 裡看得到「Stop hook
  feedback」與完整訊息。Codex 的 `exec --json` 不會印出 hook 的回饋，依據是 session 在被擋後繼續，
  而且後續回覆引用了訊息內容。
- 限制：每題 1 次；Codex 以 `--dangerously-bypass-hook-trust` 執行（變更後的 hook 尚未由使用者
  核准）；Codex 那次同時還有另一個 Stop hook（model 升級的 gate）也回了訊息，所以「繼續」不能只歸因
  於這條規則；沒有測到只改文件、以 `verifier` 或 `watcher` 當檢查、以及被擋後仍直接結束的情況。

## 前置：條款拆分與派工單位（v3.4.1，2026-10-13）

只改共用條款文字；Claude 的 legacy 對照來源（`hosts/claude/src/...`）同步，其他 host 只換 marker。

- `core/policy/bootstrap.toml`：`bootstrap-dispatch-brake` 拆成 `bootstrap-effort`、
  `bootstrap-dispatch-brake`、`bootstrap-kind-label`（皆非 required），host 可單獨省略。
  brake 加「brief 寫時間預算；到預算的 role 回報手上已有的結果」。
- `core/policy/orchestration.toml`：`one-shot-spec` 加 file ownership 與時間預算，兩次失敗後
  改為「升 tier 或回報給使用者」；新增 `small-parallel-units`（排在 `parallel-launch` 之後，
  `parallel-launch` 的 sep 改為 newline 讓它獨立成條）。
  並行 worker 只跑自己檔案的檢查，完整測試整合時跑一次。
- `core/policy/extensions.toml`：`cost-unbounded-continuation` 的「main-session takeover」改為
  「report to the user」。
- 測試：bootstrap 三條獨立、`small-parallel-units` 位置與渲染、Claude 渲染結果不含 take over／
  takeover。
- 其他 host 的 legacy 文字（Codex、agy、Grok）仍是合併的舊 bullet，待 S4 起改由 core 產生。

## S4（Codex）與 S5（agy）（2026-10-13）

### S5 agy

- 條款改由 core 產生（commits `aac0a5a`、`6243852`）；常駐文字不再有
  「role 不可用就忽略整節」。
- live 實測（agy 1.3.3，共 4 次付費執行）：
  - 長指令派 `watcher`：符合。
  - main 全程沒有自己改檔：符合。
  - 兩個小檔的偵察，main 直接讀、沒派 `scout`：不符合，僅記錄未修改。
- 實測發現的缺陷：可寫 role（`applier`、`executor`、`security-executor`）
  在 binding 沒寫 `tools`，agy 上實際沒有寫檔與 shell 工具，main 以
  `define_subagent` 自造 role 才完成。修正 `e15a443`：`[access.write]`
  明列 9 個工具；重測時 `executor` 自己完成修改，main 沒有自造 role。
- 本機安裝：skill 目錄是 symlink 到 `hosts/agy/dist`；常駐文字由 dotfile
  的 `setup_gemini.sh` 重新產生。

### S4 Codex

- 條款改由 core 產生，v3.5.0。Codex 專屬內容在
  `hosts/codex/policy-addenda/`；通用但 core 沒有的規則以 `pending-shared-*`
  保留，含這次補上的 `pending-shared-low-risk-targeted-check`。
- 常駐文字 48 行／2991 bytes（上限 48／3000，沒有餘裕）。
- prompt lock：三個 policy surface 以 migration `shared-rules-codex-core`
  更新必要片段；新增兩個 surface（`extensions-template`、
  `packaged-workflow-extensions`），上限 270 行／15600 bytes（Miyago
  2026-10-13 核准）；共 33 個 surface。
- 產生的 Codex 條款檔（templates 三份、plugin references 兩份）加入
  markdownlint 忽略清單，比照其他 host 的 render 輸出；原因是在來源換行會
  超過上限，且部分過長的行來自 core 條款本身。core 條款的換行與 `sep`
  問題尚未處理。
- 缺陷與修正 `3d772d4`：extensions 文件有出貨但沒有任何地方指向它；plugin
  `SKILL.md` 補上參考行，並加測試要求 `references/` 的每份文件都被列出。
- live 實測（codex-cli 0.160.x，預設 model，3 次有效執行）：小功能與小修正
  都派 `sol-executor`，role 正常啟動並改檔，main 沒有自己改；長指令派
  `watcher`，main 沒有自己執行。未觸發、因此未驗證：role 啟動失敗時回報而不
  接手；Stop 的完成檢查。
- 本機安裝：`install/install.py` 在這台不適用（`~/.codex/AGENTS.md` 是
  dotfile 的 symlink，`~/.codex.shoal-install-state.json` 過期）；實際由
  dotfile 的 `setup_codex.sh` 產生常駐文字、`codex plugin add` 更新 plugin。
  過期的安裝狀態檔未處理。
- 整合檢查（`3d772d4`）：unittest 1568 個通過（skipped 2）、六個 render
  檢查、lock、lint、OpenCode plugin 的 bun test 671 通過。

### 未完成

S6 OpenCode、S7 Grok、S8 收尾（`verifier` 方向檢查與逐句核對）；host 專屬的
通用規則去重後升到 core。
