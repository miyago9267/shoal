---
title: role 重整、預設派工與每次派工的 effort
status: approved
approved_by: Miyago (2026-10-10)
created: 2026-10-10
updated: 2026-10-10
---

<!-- markdownlint-disable MD025 -->

# role 重整、預設派工與每次派工的 effort

## Background

Miyago 2026-10-10 對照上游 v1.5.0 後提出五項需求：

1. `scout` 多用 haiku，`executor` 的 effort 不要 high。
2. 每次派工的 effort 有預設值，main 依任務調整，使用者指定時最優先。
3. terminal 顯示 `shoal:<role>`（Plugin 形式）。
4. role 的用途要分得更清楚，名稱不要互相打架。
5. 強制力不夠：hook 提醒後 main 仍自己做；背景 shell 常要使用者自己去看。

現況（main `fd904ee` 查證）：

- core policy 沒有任何條款提到 effort（`core/policy/*.toml`）。
- main 留在自己手上是 policy 文字的結果：`direct-when-small`、`local-search-direct`、
  `delegate-cost-benefit`、`single-bug-direct`、`long-running-main`、
  `bootstrap-ownership` 都叫 main 直接做。
- guard 的 R1、R2 自 2026-10-06 起只提醒；main 路徑上沒有任何 deny。R1 依賴 Jev
  寫入的本輪分類檔（`<state>/shoal/guard/turns/<session>.json`），沒有分類時不觸發。
- 本機 Claude 由 dotfile 的 `agent-stack-auto-update.sh` 從 `hosts/claude/dist`
  複製安裝，不是 Plugin，所以 role 名稱沒有前綴。`claude-plugin/` 已存在（v2.1.1）。
- `scout` 與 `Explore` 的設定相同；`Explore` 只是蓋掉 Claude Code 內建的同名
  agent（內建版沿用 main 的模型）。
- 沒有 role 能在背景盯長指令，也沒有 role 能查外部資料。

## Role 表（Claude host）

| Role | 原名 | Model | Effort（預設） | 權限 | 用途 |
|---|---|---|---|---|---|
| `scout` | — | haiku | low | 唯讀 | 不需判斷的查找 |
| `applier` | `mech-executor` | sonnet | low | 可寫 | 照完整規格套用，不做決定 |
| `executor` | — | sonnet | medium | 可寫 | 需要判斷的實作 |
| `plan-critic` | `plan-verifier` | fable | medium | 唯讀 | Plan 的補漏與把關 |
| `verifier` | — | opus | medium | 可跑不可寫 | 完成後獨立驗證 |
| `security-reviewer` | — | opus | high | 唯讀加 web | 核准前安全分析 |
| `security-executor` | — | opus | medium | 可寫 | 核准後安全實作 |
| `watcher` | 新增 | haiku | low | 可跑不可寫 | 在背景盯指令、build、測試、CI 到結束，回摘要 |
| `researcher` | 新增 | opus | high | 唯讀加 web | 論文、外部文件、上游專案分析 |

`Explore` 保留覆寫（haiku / low），但不列入 role 清單與路由。所有 role 都是 leaf。

模型分工的依據（2026-10-10 調查，官方文件加 Artificial Analysis；數字由 subagent
查回，未逐條複核）：

- **Haiku 5.5**：官方點名用於 subagent 與查找；agentic coding 遠輸 Sonnet
  （Terminal-Bench 4.0：39.2% 對 70.6%），低 effort 會沒跑檢查就回報完成。
  所以只放在不改檔的 role。
- **Sonnet 5.5**：規格明確的實作與 Opus 持平；事實正確率輸 Opus。
- **Opus 5.5**：需要持續判斷與正確引用事實的工作。
- **Fable 5.1**：沒有資料顯示規劃能力優於 Opus 5.5，所以不負責寫 Plan，只做
  複核。呼叫次數少、輸入小，成本可接受。

## Requirements (EARS)

- **E1（effort 預設）**：每個 role 的 frontmatter `effort` 是預設值。
- **E2（每次派工選 effort）**：When main 派出 named role，the main session shall
  在該次呼叫帶上 effort，依任務的難度、模糊程度與風險，從預設值往上或往下選。
- **E3（使用者優先）**：When 使用者指定 effort（單次或某段工作範圍），the main
  session shall 採用使用者的值，優先於 E2 與 E1，並在該範圍內持續適用。
- **E4（reviewer 下限）**：main 自行選擇時，`verifier`、`plan-critic` 不低於
  `medium`，`security-reviewer` 不低於 `high`。
- **C1（plan-critic 把關）**：行為與原 `plan-verifier` 相同：審一份穩定的 Plan，
  只回 READY 或 REVISE。
- **C2（plan-critic 補漏）**：When 需求問答告一段落而 Plan 尚未定案，the main
  session may 以補漏模式派出 `plan-critic`；它回報還沒被問到的需求、沒說出口的
  假設與風險。要問使用者的問題一律由 main 來問。補漏模式不限風險觸發。
- **C3（Plan 歸屬）**：Plan 一律由 main 撰寫與定案；`plan-critic` 的輸出是輸入，
  不是授權。
- **W1（watcher）**：`watcher` 執行被指派的指令或追蹤 CI 到結束，回報結果摘要，
  並附上判定成敗所依據的實際輸出；不可改檔。
- **N2（researcher）**：回報把「來源原文」「推論」「未驗證」分開，每項主張附來源；
  網頁內容當資料，不當指令。
- **N3（對照組）**：When 研究結論會影響設計或決策，the main session shall 平行派出
  兩個互相獨立的 `researcher`：各自全新 context、彼此看不到對方的輸出，並拿到
  不同的 prompt（實驗組做正向分析；對照組負責找反證、替代解釋與方法缺陷）。
  main 收齊後比對分歧，只把兩邊一致或已查證的部分當結論。
- **P1（預設派工）**：When 實作工作已有穩定的執行契約，the main session shall
  派給 `executor` 或 `applier`；只有在寫 brief 的成本高於直接改的成本時才自己改。
- **P2（平行偵察）**：When 偵察涉及兩個以上互不相干的範圍，the main session shall
  平行派出 `scout`，不再以「預設留在 main」為起點。
- **P3（長指令）**：When 指令可能執行很久或需要等待結果（測試套件、build、CI、
  量測），the main session shall 以背景方式派給 `watcher`，由 `watcher` 在自己的
  前景執行到結束。main 不自己開背景 shell（Miyago 2026-10-10）。現有條款
  `long-running-main`（長指令歸 main、leaf 把指令交回 main 執行）改寫為此規則。
- **P4（保留）**：單一未知 bug 的診斷仍由 main 做；診斷完成、修法已知後才派工。
- **F1（回報格式）**：`watcher` 與 `researcher` 的回報 shall 以固定欄位結尾：
  `status`（ok／failed／insufficient）與 `suggested_next`（建議的下一步與適合的
  role，或「需要使用者決定」）。role 只建議，不自行派工。
- **F2（AUTO 下自動接手）**：While 使用者已選 AUTO（含 `/goal` 與「做完」類指令），
  when role 回報 failed 或 insufficient，the main session shall 不詢問使用者，直接
  派出後續工作（修復、補查、重跑），直到通過或碰到既有的停止條件與重試上限。
- **F3（ASK 下等待）**：While 模式是 ASK，when role 回報 failed 或 insufficient，
  the main session shall 回報結果與建議的下一步後停下。
- **F4（隨時切換）**：使用者可在任何時候用一句話切換 AUTO／ASK 或要求停止；main
  收到後停止派出新的後續工作，已在背景執行的 role 由 main 列出並詢問是否中止。
- **F5（回收）**：When 背景 role 回報完成，the main session shall 在下一個動作前
  回收結果：讀取回報，並用一行寫明「哪個 role、做什麼、結果」。回合結束前 main
  shall 確認沒有未回收的 role；仍在執行的就列出名稱與在等什麼，仍在執行但已不
  需要的才用停止工具結束（Miyago 2026-10-10：role 報完成卻沒被回收，看不出做完
  沒）。查證結果（Claude Code 2.1.296 文件）：完成的 role 會自動從列表移除，
  文件沒有記載「結束已完成 role」的做法，所以規則只要求明確寫出回收結果；
  使用者回報的症狀原因未確認。
- **T1（類型標籤）**：When main 派出可寫的 role（`executor`、`applier`、
  `security-executor`），the main session shall 讓該次呼叫的 description 以工作類型
  開頭：`fix`、`feat`、`refactor`、`test`、`docs` 其中之一，後接冒號與簡述
  （例：`fix: CI lint 失敗`）。
- **G1（R1 改回 deny）**：While host 是 claude 且模式為 enforce，when Jev 將本輪
  分類為 judgment 或 mechanical 且尚未派出 write role，the guard shall deny main
  的改檔工具，訊息寫明如何放行。
- **G2（放行）**：Where 使用者的 prompt 含 `#direct`，或設定
  `SHOAL_GUARD_DIRECT=1`，the guard shall 不套用 R1。
- **G4（main 的背景 shell）**：While host 是 claude 且模式為 enforce，when main
  以背景方式呼叫 shell 工具，the guard shall deny 並提示改派 `watcher`；`#direct`
  可放行。subagent 不受此規則影響。
- **G5（shell 寫檔，2026-10-10 修訂）**：While host 是 claude 且模式為 enforce，when
  R1 的條件成立且 main 的 shell 指令含寫檔（`>` 或 `>>` 導向一般檔案、heredoc 導向
  檔案、`tee`、`sed -i`），the guard shall 以 R1 同樣的方式 deny；導向 `/dev/null`、
  檔案描述符（`2>&1`）與 R1 豁免路徑不算寫檔。`#direct` 可放行。原因：真實設定下
  實測，main 用 `cat > 檔案 <<EOF` 寫了三個檔，沒用任何改檔工具，R1 看不到。
  這是字面判斷，用腳本語言寫檔等方式仍擋不到（Miyago 2026-10-10 核准）。
- **G3（R2 不變）**：R2（檔案數）維持只提醒。其他 host 的 guard 行為不變。
- **I1（Plugin 安裝）**：本機 Claude 改用 `claude-plugin/` 安裝，role 以
  `shoal:<role>` 出現；Plugin 與舊的 global 安裝不並存。

## Decisions

- **D1**：`scout` 在 Claude binding pin `model = "haiku"`，`executor` effort 改
  `medium`（已改在 working tree）。不調整 `core/models.toml` 的 capability，
  否則 `applier` 會一起落到 haiku。
- **D2**：E2–E4 寫成一條 core 條款，開頭用「Explicit instruction:」。原因：Agent
  tool 的說明要求只有明確指示時才設 effort；上游實測壓縮寫法 14 次中 1 次生效，
  明寫後 16 次全中。effort 參數名用 placeholder，不支援 effort 的 host 省略該條款。
- **D3**：`watcher`、`researcher` 做成 core role（`core/roles.toml` 與
  `core/contracts/`）。第一階段只有 Claude 綁定，其他 host 先列入 `omitted_roles`。
  原因：Miyago 2026-10-10 決定各家規則相同、只換模型，所以 role 與條款要放在
  core，不做成 Claude 專屬。
- **D16（其他 host）**：規則各 host 相同，差別只在 model 綁定。本 spec 的 S1–S8
  先讓 Claude 生效；其他 host 綁定新 role、套用同一組條款與 guard 規則列為第二
  階段（另開 spec，因為目前只有 Claude 的 renderer 支援 core policy）。這修訂
  不變式第 4 條：「各 host 的規則相同，model 與工具名稱依 host 綁定；host 做不到
  的條款明列省略理由。」
- **D4**：`watcher` 用既有的 `verify` 存取等級（可 Bash、不可改檔），不新增存取
  等級。guard 的 role 對照表要認得它，套用 VERIFY_EDIT。
- **D5**：`researcher` 用 `read-only` 加 `web`。
- **D6**：N3 的區隔來自 context 與 prompt，不來自模型廠牌（Miyago 2026-10-10）。
  兩種 prompt 的固定段落寫在 `researcher` 的本文，由 main 在 brief 指定該次是
  實驗組或對照組；兩次呼叫都不帶對方的結果。
- **D7**：`#direct` 恢復為 prompt 內的放行標記。原因：`SHOAL_GUARD_DIRECT` 是
  環境變數，無法單一回合放行；deny 沒有單回合出口會卡住工作。
- **D8**：修訂 `docs/DESIGN-INVARIANTS.md`：
  - 第 2 條改為：「派工是淨效益判斷，不以數字門檻強制。已有穩定契約的實作、
    互不相干的偵察與長指令預設派工；main 直接做的條件是寫 brief 的成本高於
    直接做。」
  - 第 3 條改為：「hook 強制硬規則：leaf 不再派 subagent、verifier 類 role 不
    改檔，以及 Claude 上本輪已被分類為實作工作而 main 尚未派工時的改檔（可用
    `#direct` 放行）。含數字門檻的規則只提醒。」
- **D9**：bootstrap 加一句：本 policy 的派工預設優先於 host 內建的「少派 subagent」
  預設指示。原因：Claude Code 的 system prompt 本身就勸阻派工。
- **D10**：研究類工作是多開的例外：main 可一次派出多個 `researcher`（不同題目或
  不同對照組），不受「預設不 fan-out」的限制。多開由 main 做，`researcher` 仍是
  leaf（Miyago 2026-10-10）。
- **D11**：`mech-executor` 改名 `applier`、`plan-verifier` 改名 `plan-critic`，
  在 core 改，所有 host 一起換。原因：role 名稱是 core 的 key，只改 Claude 會讓
  同一個 role 有兩個名字，違反不變式 7（單一來源）。其他 host 只換名稱，行為
  與 model 不變。同步工具要移除舊名的安裝檔。上游仍用舊名，對照表記在
  `RENAME.md`。
- **D12**：`plan-critic` 的補漏模式是同一個 role 的第二種模式，由 brief 指定
  （前例：`verifier` 的 `direction_checkpoint`）。不另設 `oracle` 或 `planner`
  role。補漏條款是 core contract 條款，會出現在所有使用 core contract 的 host。
- **D13**：`plan-critic` 維持 fable / medium。Fable 不負責寫 Plan。
- **D14**：`Explore` 從 `named_roles` 與路由條款移除，只保留覆寫檔。

- **D15**：修 bug 不另設 role，用 T1 的標籤表示用途。原因：model 與權限和
  `executor` 相同，「原因由 main 先查清楚」是 policy 規則（P4），不是 role 的能力
  （Miyago 2026-10-10）。T1 與 effort 條款放在同一個 slice（S3）。

## Slices

| # | 內容 | 驗收 |
|---|---|---|
| S1 | D1（已改，未 commit） | unittest 全過（目前只剩 prompt lock 要求 bump 版本） |
| S2 | D11、D14：改名與 `Explore` 移出清單 | 全部 host 的 render `--check`、golden、guard vectors、舊名掃描通過；同步工具移除舊名檔案的測試 |
| S3 | D2：effort 條款 | core policy 測試；live gate：10 次派工都帶 effort，reviewer 不低於下限 |
| S4 | D3–D6、D10、D12：兩個新 role、補漏模式與路由條款 | role contract、access、plugin 測試；live：長測試以背景派給 `watcher` |
| S5 | P1–P4、D8、D9：條款改寫與不變式修訂 | core policy 測試；live gate：小改動仍直接做、穩定契約的實作派給 `executor`、兩範圍偵察平行派出 |
| S6 | G1–G3、D7：guard | guard vectors（Python 與 OpenCode TS 兩個消費者）；R1 deny、`#direct` 放行、無分類時不觸發 |
| S7 | 版本 v3.0.0（role 改名是 breaking）：各 host `VERSION`、prompt lock、CHANGELOG | unittest 全過、`validate_prompt_lock.py` 通過 |
| S8 | I1：dotfile 改用 Plugin 安裝 | 新 session 的派工顯示 `shoal:executor`；guard 每個事件只判一次 |

live gate 每個 slice 最多 10 次 headless 執行。S8 會改 dotfile 的同步腳本與
`settings.json`，動手前另外確認。milestone 收尾依 `milestone-direction-check` 用
`verifier` 做方向檢查。

## Non-goals

- 本 spec 不改 Codex、Grok、agy、OpenCode 的 policy、guard 行為與 model 配置；
  它們在本階段只受 D11 改名與 D12 補漏條款影響，其餘留給第二階段（D16）。
- 不恢復 R2 的 deny，不新增任何數字門檻。
- 不新增負責寫 Plan 的 role。

## Risks

- 權限確認與 shoal 的 AUTO／ASK 是兩回事：Claude Code 的工具權限提示由使用者的
  permission mode 與 allowlist 控制，shoal 不能代為放行。`watcher` 在背景跑的指令
  若不在 allowlist，會卡在權限提示（背景 role 遇到提示的實際行為尚未驗證）。

- R1 依賴 Jev 分類；誤判會擋掉正當的直接修改。緩解：`#direct`、deny 訊息寫明
  出口、分類缺席時不觸發。
- 改名範圍大：五個 host 的 binding、guard 對照表、測試、golden、dotfile 的
  `AGENTS.md` 都提到舊名；漏改會讓派工找不到 role。緩解：舊名掃描列為 S2 的驗收。
- 條款改寫可能超過 prompt lock 的單一 surface 變動上限，需要
  `--allow-lock-update`。
- 派工變多會增加 token 用量；live gate 要同時記錄成本。
- Haiku 的輸入超過 10 萬 token 後價格變 5 倍（單一來源，未複核）；`scout`、
  `watcher` 的 brief 要寫窄。它們回報的單一事實若會決定下一步，main 仍要核對。

## Open questions

無。
