# delegation-default live behaviour gate

日期 2026-10-10。問題：工作樹的 plugin（`plugins/claude/`，delegation-default 條款）
載入後，真實的 Claude Code main session 會不會照新 policy 派工。這不是 benchmark，
是 10 次 headless run 的行為抽查。

## 方法

- Claude Code 2.1.296，每個 case 一次 `claude -p`，cwd 是全新的 throwaway git repo
  （小型 Python fixture，`scripts/run_tests.sh` 內含 `sleep 20`），原始 stream 放在
  repo 外，這裡只留衍生欄位。
- 旗標：`--model opus --plugin-dir <repo>/plugins/claude --setting-sources project
  --strict-mcp-config --dangerously-skip-permissions --output-format stream-json
  --verbose --max-budget-usd 2`。
- 驗證載入：init 事件列出 `shoal:*` 的 10 個 role，使用者安裝的 plugin 只有 `shoal`（init 另列出三個內建的 `cc-plugin-*`）；SessionStart
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

## 第三輪：真實設定下的 guard（v3.0.1）

前兩輪都在隔離設定下跑，沒有 Jev 分類，fixture 又在暫存目錄，所以 R1 從未觸發。
這一輪改用本機的真實設定（Plugin `shoal@shoal` 3.0.1、Jev active），在家目錄下的
拋棄式 repo 跑 case C 的同型題目（三個檔案的小功能加測試），共 2 次，USD 1.13。

| run | Jev 分類 | main 的行為 | guard | 結果 |
|---|---|---|---|---|
| 1（v3.0.0） | 無（prompt 含風險字被 Jev 跳過） | 用 `cat > 檔 <<EOF` 寫三個檔，無 Agent | 無評估 | fail |
| 2（v3.0.1） | `judgment` | `cat > 檔 <<EOF` 被擋後派 `shoal:applier`（`feat:`、effort low） | R1 `deny` 一次、Agent `allow` | pass |

- run 1 找到兩個缺口：main 用 shell 寫檔繞過改檔工具（已由 G5 補上，v3.0.1）；Jev 的
  風險字篩選會讓整個回合沒有分類，這類回合 R1 不會觸發（未處理，屬 Jev 的設計）。
- run 2 的 child model 是 `claude-sonnet-5-5`。main 選的是 `applier` 而不是 `executor`；
  兩者都是可寫 role，符合「有穩定契約的實作要派工」。
- 只有 1 次通過，題目是同一型；G4（main 開背景 shell）仍只有單元測試與手動實測的證據。

## 第四輪：真實設定下補 live 證據（v3.0.1）

同第三輪的真實設定（Jev active，家目錄下的拋棄式 repo，fixture2，
`--permission-mode acceptEdits`），6 次 run（上限 7），USD 3.21。
結果在 `results-pass4.json`，prompt 為 `prompts/pass4-*.txt`。

| case | Jev | main 的行為 | guard | 結果 |
|---|---|---|---|---|
| C-edit | judgment | Edit、Edit、Write 全被擋後派 `applier`（`feat:`、effort low） | R1 deny 3 次 | pass |
| C-repeat1 | judgment | 同上 | R1 deny 3 次 | pass |
| C-repeat2 | 無 | main 自己 Edit、Write 三個檔，無 Agent | 無 deny（R2 advise） | fail |
| G4 背景測試 | 無 | 直接派背景 `watcher`，沒試背景 shell | 無 deny | pass（未觸發 G4） |
| reviewer 下限 | judgment | heredoc 寫檔被擋，派 `applier` 後派 `verifier`（effort medium） | R1 deny（Bash） | pass |
| watcher 長指令 | 無 | 派背景 `watcher`；watcher 用單一前景 Bash（timeout 600000） | 無 deny | fail |

現在有 live 證據的項目：

- R1 對 Edit、Write 的 deny 在真實 session 觀察到（C-edit、C-repeat1 各 3 次），
  deny 後 main 改派可寫 role；effort 與 kind 標籤都有帶。
- reviewer 下限：明確要求獨立檢查時，main 派 `shoal:verifier` 且 effort 為 medium（1 次）。
- 背景 `watcher` 會被主動派工（G4、watcher-long 各 1 次）；child model 為 haiku，
  `applier` 為 sonnet，`verifier` 為 opus。

仍未證實或有負面證據：

- 重複性 2 pass、1 fail。C-repeat2 沒有 Jev 分類（turn 記錄不存在），
  guard 因此不介入，main 自己寫完。沒有分類的原因未查明（prompt 已通過風險字篩選）。
- G4 的 deny 沒量到：main 一開始就選了 watcher，從未開背景 shell。
- 長指令 fail：660 秒的指令超過前景 Bash 上限（600000 ms），watcher 沒有改用背景 shell，
  指令在約 600 秒被終止，最終沒有 PASS 行。這是 `watcher` 背景 shell 條款的負面 live 證據。
- 每個 case 仍只有 1 次（C 型共 3 次），watcher 的失敗不能排除單次偶發；沒有量到 plan-critic。

### 第四輪補測（v3.0.2 的 watcher 條款，1 次 run）

載入工作樹的 Plugin（`--plugin-dir`、`--setting-sources project`、每次獨立的 XDG 目錄），
腳本 `sleep 660`，USD 0.16，結果在 `results-pass4b.json`，判定 fail。
條款本身有照做：兩個 `watcher` 都用 `run_in_background: true` 的 Bash 啟動、寫 `EXIT_STATUS=`
到 log，再用 60 秒以下的前景迴圈輪詢，沒有任何一次前景呼叫被時限切斷。
但結果沒進最終回答：第一個 watcher 在指令前多加了 `ls -l`（本機互動 shell 的 `ls` 壞掉，
腳本沒跑），main 重派第二個；session 在約 633 秒結束，早於腳本的 660 秒，背景工作被停掉。
session 為何在背景 watcher 還在輪詢時結束沒有查明，單次 run 分不出是 harness 限制還是偶發。

### 互動式 session 的對照（v3.0.2 的 watcher 條款，1 次）

為了分辨上面的失敗是條款問題還是 headless 的限制，在互動式 session 用同一份 render 出來的
`watcher` 本文加 Haiku 5.5（一般 agent，背景派出）跑同一個 `sleep 660` 腳本：約 11 分鐘後
回報 `LONG CHECK PASS` 與 `EXIT_STATUS=0`，main 被自動叫醒收到結果，共 5 次 tool 呼叫。
所以條款可行，headless `-p` 的 session 會在背景 role 還沒回報時結束。限制：這次用的是
一般 agent 加角色本文，不是 Plugin 的 `shoal:watcher`，也只有 1 次。
