# delegation-default live behaviour gate

日期 2026-10-10。問題：工作樹的 plugin（`claude-plugin/`，delegation-default 條款）
載入後，真實的 Claude Code main session 會不會照新 policy 派工。這不是 benchmark，
是 10 次 headless run 的行為抽查。

## 方法

- Claude Code 2.1.296，每個 case 一次 `claude -p`，cwd 是全新的 throwaway git repo
  （小型 Python fixture，`scripts/run_tests.sh` 內含 `sleep 20`），原始 stream 放在
  repo 外，這裡只留衍生欄位。
- 旗標：`--model opus --plugin-dir <repo>/claude-plugin --setting-sources project
  --strict-mcp-config --dangerously-skip-permissions --output-format stream-json
  --verbose --max-budget-usd 2`。
- 驗證載入：init 事件列出 `shoal:*` 的 10 個 role，plugin 只有 `shoal`；SessionStart
  hook 注入了 bootstrap policy（完整 policy 在 `shoal-orchestration` skill，需 main 自己載入）。
- `run_gate.py run <CASE> --work DIR` 執行並計數（上限 10，失敗也算），`classify` 與
  `export` 離線分類並產生 `results.json`。判定嚴格：未達期望一律 fail。
- 10 個 prompt 在 `prompts/`。

## 結果

| case | 期望 | 結果 | 觀察 |
|---|---|---|---|
| A 小修 | 無 Agent，main 直接改 | pass | 直接 Edit，無 Agent |
| B 機械批次 | 一個 `applier` | fail | 無 Agent；main 用 Bash 迴圈自己改 10 檔 |
| C 判斷型功能 | `executor` + 標籤 + effort | fail | 無 Agent；main 自己寫 3 檔 |
| D1 兩處偵察 | 兩個並行 `scout` | fail | 無 Agent；main 直接讀兩個目錄 |
| D2 兩處偵察 | 兩個並行 `scout` | fail | 同上 |
| E1 長指令 | `watcher` 背景 | fail | main 前景自己跑 20 秒測試 |
| E2 長指令 | `watcher` 背景 | fail | 同上 |
| F 研究定案 | 並行 `researcher` 實驗/對照 | fail | 派了兩個（arm 正確、Opus）但無 effort，且分兩個 turn 發出 |
| G 需求不明 | 問方向或 `plan-critic` gaps | pass | 用文字提問，未實作（未派 critic） |
| H 單一 bug | main 先診斷 | pass | main 自己診斷並修好，無 Agent |

合計 pass 3 / fail 7。總成本 USD 1.82，10 次 run 全部用完，沒有 run
啟動失敗。每個 case 的 Agent 呼叫、turns、cost、token 與 model usage 在 `results.json`。

## 觀察到的 subagent model

只有 F 派了 subagent：兩個 `shoal:researcher` 的 child message 都是 `claude-opus-5-5`。
`scout`、`watcher` 一次都沒被派，haiku 的 pin 沒有被驗證。F 的 `modelUsage` 另有
`claude-haiku-5-5`（約 26 萬 input token），推測是 WebFetch 的內部摘要，未確認。

## 限制

- 每個 case 只有 1 次（D、E 兩種措辭），一個 fixture，沒有重複，無法估變異。
- 這次 runtime 的 `shoal_guard.py` 實際上沒有作用：plugin guard 偵測到
  `~/.claude/settings.json` 登記了全域 guard 就退讓，而該 settings 在
  `--setting-sources project` 下沒有載入。所以結果量到的是 policy 文字，不含 G1/G4 的 deny。
- fixture 很小（偵察目錄約 40 行、測試 20 秒），main 可能因此合理判斷「自己做更便宜」；
  D2 原本想用較大的目錄，但補丁沒套用成功，實際沿用小 fixture，且已計入 10 次。
- 第一次 B/C 結果出來後沒有改 prompt 重跑（預算已定），所以沒有調整措辭的對照。
- F 的「並行」判定是 tool_use 都早於任一 result；實際上兩個 researcher 都是 background
  task 且時間重疊，只是不在同一個 turn 發出。
- 使用 subscription，CLI 回報的 cost 是估算值。

## 第二輪（2026-10-10，bootstrap 改寫之後）

派工規則寫進常駐 bootstrap 後重跑。差異：plugin guard 自己判斷事件（每次 run 的
`XDG_DATA_HOME` 指向空目錄、`XDG_STATE_HOME` 指向私有目錄）；fixture 換成 `fixture2/`
（四個套件 240 至 380 行、12 個同形模組、測試仍 `sleep 20`）；B 的 prompt 改成 12 檔
（`prompts/B.pass2.txt`）。旗標、其餘 prompt 與判定同第一輪；D、F 的「並行」改為兩個
Agent tool_use 在同一則 message，或都早於任一 result。結果在 `results-pass2.json`。

| case | 第一輪 | 第二輪 | 第二輪觀察 |
|---|---|---|---|
| A 小修 | pass | 未量 | 見下方「run 用量」 |
| B 機械批次 | fail | pass | 一個 `applier`（`feat:`、effort low），12 檔完成 |
| C 判斷型功能 | fail | fail | 無 Agent；main 先 `cat` 三個檔，再 Edit、Write 自己寫 |
| D1 兩處偵察 | fail | pass | 兩個 `scout` 在同一則 message，effort medium |
| D2 兩處偵察 | fail | pass | 同上，effort low |
| E1 長指令 | fail | pass | 一個背景 `watcher`，main 沒跑測試也沒開背景 shell |
| E2 長指令 | fail | pass | 同上 |
| F 研究定案 | fail | pass | 兩個 `researcher`（實驗與對照）同一則 message，effort medium |
| G 需求不明 | pass | pass | 載入 skill 後用文字提問，未實作 |
| H 單一 bug | pass | pass | main 用 Bash 診斷並修好，無 Agent |

合計 8 pass、1 fail、1 未量（第一輪 3/10）。

- run 用量：10 次用完。第一次 A 忘了帶 `--pass 2`（小 fixture、guard 退讓），算入上限但不列入
  表格（直接改、無 Agent，USD 0.10）；最後一次留給 E2 而非重跑 A。總成本 USD 2.43。
- subagent model：`scout`、`watcher` 為 `claude-haiku-5-5`，`researcher` 為 `claude-opus-5-5`，
  `applier` 為 `claude-sonnet-5-5`；haiku 與 opus 的 pin 已驗證。
- guard：有評估（guard.jsonl 有 prompt 與 Agent 事件），沒有任何 deny。fixture 在系統暫存目錄，
  guard 對該路徑的改檔一律豁免（C 的 Edit、Write 記為 `exempt`），R1 不可能觸發；
  R1 與 G4 的 deny 仍未被量到。watcher 的測試在前景預設時限內跑完，沒用到背景 shell 條款。
- bootstrap、fixture、guard 三件事同時改，每個 case 只有 1 次，不能把改善歸給單一因素。
  C 沒有 Agent 呼叫也沒載入 skill；原因只能從 tool 序列推論，沒有直接證據。
