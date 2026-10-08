---
title: Milestone 方向檢查（防止隧道視野）
status: completed
approved_by: Miyago
created: 2026-10-07
updated: 2026-10-07
---

<!-- markdownlint-disable MD025 -->

# Milestone 方向檢查（防止隧道視野）

## Background

Miyago 對 shoal 的目標是「要有品質，並且不要有隧道視野」（2026-10-07）。
2026-10-06 的開發出現隧道視野：一連串切片與 spec 各自通過測試與審查，但整體
偏離了 pilotfish 的設計（架構判斷外包給 executor、dispatch 判斷變成數字門檻、
host 被同質化），直到 Miyago 指出才停下。

現有機制與缺口（main `e177287` 查證）：

- `direction_checkpoint`（Claude
  `hosts/claude/dist/skills/shoal-orchestration/references/workflow-extensions.md`
  的 Direction checkpoint 一節；Codex orchestration 亦有）是**選用**的
  （「may」），只判斷單一切片後的剩餘路徑，比較基準是該 outcome 的原始需求與
  限制。這次偏離發生在跨切片、跨 spec 的累積，當時沒有觸發。
- outcome continuation 預設推進到 acceptance，`/goal` 只保留目標；沒有任何規則
  要求在推進途中退一步，對照專案的設計原則。
- dispatch 規則已寫「不委派 Plan synthesis、integration judgment」，但沒有要求
  main 檢查 executor 回報中「自行做了哪些設計決定」。

## Requirements (EARS)

- **D1（強制觸發）**：When 以下任一情況發生，the main session shall 先做一次
  方向檢查，再繼續或回報完成：
  - 一個 spec 或 milestone 準備標為完成；
  - 同一個目標連續推進到第 3 個切片（含新開 spec 延續同一目標），之後每個
    milestone 收尾再做一次；
  - 準備派出的工作含架構或設計選擇（依 dispatch 規則本應由 main 做）。
- **D2（比較基準）**：方向檢查 shall 以三者為基準：使用者的原始需求、已核准
  spec 的 non-goals 與 decisions、專案宣告的設計不變式（若存在
  `docs/DESIGN-INVARIANTS.md` 或專案指定的同等文件）。
- **D3（獨立視角）**：多切片工作的 milestone 收尾時，方向檢查 shall 以
  `verifier` 的 `direction_checkpoint` 進行（全新 context），brief 帶入 D2 的
  三個基準；其他觸發點可由 main 自行檢查。`CONTINUE`／`PIVOT`／`ROLLBACK` 語意
  沿用現有定義。每個 milestone 一次（不是每個 spec、每個切片一次），與 outcome
  verifier 是不同的 contract、分開呼叫；`review_intent=fast` 不得省略這次檢查。
- **D4（偏離即停）**：When 方向檢查發現偏離設計不變式或使用者原始需求，the
  main session shall 停止新的寫入並向使用者報告偏離點與建議，不得自行修正後
  繼續。路由上對應 `stop_condition=decision`（無互動時為 `PAUSED_NEEDS_USER`）；
  verifier 回 `ROLLBACK` 時，是否回到最近的已驗證狀態由使用者決定，與現行
  AUTO 不得自行 rollback 的規則一致。
- **D5（executor 的設計決定）**：When executor 回報中包含 brief 以外的設計
  決定（新增機制、介面、命名規則或 omit 類取捨），the main session shall
  逐項判定接受或退回，並記入該 spec 的 PROGRESS；不得未檢視即合併。
- **D6（不變式文件）**：shoal 本身 shall 有 `docs/DESIGN-INVARIANTS.md`，
  列出 2026-10-06 設計對照得出的原則（main 負責架構與 Plan；派工是 dispatch
  brake 的淨效益判斷，不以數字門檻強制；hook 只強制硬規則；各 host 保留自身
  形狀、共用化以持平為準；core／host 中立條款不綁具體 model ID，host addenda、
  role frontmatter 與 alias 不在此限；verification 邊界不因便宜的 executor 而
  省略）。每一條寫入前先對照 main 現行的 Claude、Codex dist，必須零偏離。

- **D7（不計代價模式）**：Miyago 2026-10-07 要求：常用 `/goal` 卻還沒做完就停。
  When 使用者明確選擇「不計代價」（在 `/goal` 或 prompt 中寫明，或在 AUTO／ASK 詢問
  時選擇），the main session shall 在已核准的範圍內推進到 acceptance，不因花費、
  token、時間、切片數、discovery budget 或「要不要繼續」而停止或詢問。
  - AUTO 的停止清單與 D4 全部保留，不另列清單；不計代價不授予任何額外權限。
  - review 輪數上限：達到兩次 `REVISE` 時照現行規則做 disposition、縮小或拆分，
    之後由 main 繼續（視同使用者指示的繼續）；每輪仍需 material change，沒有時照常
    `PAUSED_VERIFICATION`；升級只限 executor 換更高 tier 或由 main 接手；未解的 P1
    若超出已核准範圍仍停止。
  - 方向檢查回 `PIVOT` 時，只能在已核准範圍內重新規劃後繼續並記錄；超出範圍即
    `stop_condition=decision`。

## Non-goals

- 不新增 role，不改 guard 與 hook。
- 不讓方向檢查變成每個切片的例行驗證（只在 D1 的觸發點）。
- Grok、agy、OpenCode 的 legacy policy 不加此條款：依 core-policy 修訂，這些
  host 維持 legacy（Grok 逐字取自上游、agy 衍生自 Grok、OpenCode 持平即
  legacy），不藉此新增能力。

## Decisions

1. **落點與預算**：Claude 寫入 `core/policy` 的 workflow extensions 條款（Claude
   走 core）；Codex 以 legacy 原文修改對應段落。硬約束：變更量（含被替換的舊行）
   必須落在現行預算內（Claude workflow-extensions 30 行／4000 字元；Codex
   orchestration 32 行／3000 字元、ratio 0.1，mirror 同）。這是新增行為，不適用
   core-policy 的 migration（migration 只用於行為等價的改寫）；超出時改走
   `Lock-Renewal: approved` 調高 `LOCK.json` 預算，需 Miyago 核准並記入 PROGRESS。
2. **以既有 direction checkpoint 為基礎**：不新增新的回報格式，只把觸發條件與
   比較基準補齊，避免另造一套機制。
3. **版本**：claude、codex host `2.0.0` → `2.1.0`，產品 `2.1.0`。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| M1 | 由 main 撰寫條款文字與 `docs/DESIGN-INVARIANTS.md` | plan-verifier 審過條款與不變式：與 pilotfish 設計一致、不會造成每個切片都要檢查、對 main 現行 Claude／Codex dist 逐條比對零偏離 |
| M2 | Claude core 條款、Codex legacy 修改、render、golden、lock | 六個 render `--check`、全套測試、`validate_prompt_lock` ok 且 `LOCK.json` 未改（或依 Decision 1 帶 trailer 並記錄核准）；條款逐字出現在 Claude 與 Codex 產物 |
| M2b | D7 條款（Claude core 與 Codex legacy），在 M2 已 push 到 main 且 CI 通過之後，以獨立的一次 push（base 已含 M2）提交，各自在 Decision 1 預算內並各自 bump host 版本（M2：2.1.0，M2b：2.1.1） | 條款逐字出現在產物；不含第二份停止清單；保留 material change 與 `PAUSED_VERIFICATION` 字句；以含 M2 的 base 跑 `validate_prompt_lock` ok，`LOCK.json` 未改 |
| M3 | 方向檢查的實際演練 | 以本 spec 自身收尾做一次 D3 的 verifier 方向檢查，結果記入 PROGRESS |
| M4 | 發布 v2.1.0（含 M2 與 M2b） | CI 綠；tag 與 release |

## Rollback

revert M2 的 commit；`docs/DESIGN-INVARIANTS.md` 可保留（文件不影響行為）。

## 完結狀態

- M1：0141e06
- M2：77883f7
- M2b：efa4231
- M3：CONTINUE
- M4：v2.1.0
