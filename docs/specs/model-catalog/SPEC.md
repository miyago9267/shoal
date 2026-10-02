---
id: spec-model-catalog
title: 模型目錄與自動選模（role-only 定義的第 1 步）
status: approved
created: 2026-10-02
updated: 2026-10-02
author: Miyago
approved_by: Miyago
tags: [models, routing, binding, render]
priority: high
---

<!-- markdownlint-disable MD025 -->

# 模型目錄與自動選模

## Background

shoal 的長期方向：使用者只定義 role，模型、權限與提示文字由 shoal
依 host 自動配置，換到任何廠牌的 agent 都適用。分四步：

1. 模型目錄與 resolver（本 spec）
2. role 文字統一到 `core/`
3. 權限由 adapter 依存取等級推導
4. 新增 host 的腳手架

現況：`core/roles.toml` 已經中立，但每個 host 的 `binding.toml` 仍手寫
`[tiers]`（能力等級對模型）。換一個模型要改 binding、src、templates、
golden 與多個測試；2026-09-30 把 codex root 換成 `gpt-6.1-sol` 的改動
就動到 13 個檔案。

## Requirements (EARS)

- **R1**：The repo shall hold one model catalog（`core/models.toml`），
  每個模型記錄 `vendor`、`capability`（1–5）、`cost`（1–5）與旗標；
  catalog 不含任何 host 專屬的名稱。
- **R2**：`core/tiers.toml` shall 定義每個 tier 的選模規則：
  `fast`、`standard`、`strong` 為「capability 不低於門檻的模型中 cost
  最低者」，`frontier` 為「capability 最高者」；同分時依 cost、再依
  名稱排序，結果必須是確定的。
- **R3**：Each host binding shall 以 `[models]` 宣告這個 host 可用的
  模型與它在該 host 的名稱（例如 Claude 的 alias `sonnet`、OpenCode 的
  `{provider, model}`），resolver 只在這個集合內選。
- **R4**：Where a role has `security = true`，the resolver shall 排除
  帶有 `refuses_defensive_security` 旗標的模型，取代現有的
  `security_avoid_frontier` 開關。
- **R5**：Where a binding 明寫 `[tiers]`、`[roles.<name>].model` 或
  `[root].model`，the pinned value shall 優先於 resolver 的結果，
  且 `--explain` 要標示它是手動指定。例外：R4 優先於 pin；
  `security = true` 的 role 被 pin 到帶 `refuses_defensive_security`
  旗標的模型時，render shall 以 exit 2 失敗。
- **R6**：Where a host 不指定模型（grok 的 `inherit`），binding shall
  以 `selection = "inherit"` 宣告，resolver 不介入。
- **R7**：When `render --host <h> --explain` runs，the tool shall 印出
  每個 role 的 tier、候選模型、被排除的原因與最後結果。
- **R8**：When 這個 spec 的實作完成，五個 host 在移除手寫 `[tiers]`
  之後的 render 結果 shall 與目前的 dist 逐位元組相同。
- **R9**：If catalog 中沒有任何模型滿足某個 role 的規則，then the tool
  shall 以 exit 2 失敗並指出是哪個 host 的哪個 role。

## Non-goals

- 不做執行期的動態選模；選模只發生在 render 時。
- 不自動發現新模型；新模型由人登記進 catalog。
- 不統一 role 文字、不改權限對應（第 2、3 步）。
- 不改任何 host 目前實際使用的模型（R8）。

## 設計

```text
core/
  roles.toml      # 既有：access、tier、security
  tiers.toml      # 新增：每個 tier 的門檻與選法
  models.toml     # 新增：模型目錄
hosts/<h>/binding.toml
  [models]        # 新增：這個 host 可用的模型與 host 內名稱
  [tiers]         # 變成選用：只在要手動覆寫時寫
```

`core/models.toml`（示意，數值在實作時校準到能重現現況）：

```toml
[models."anthropic/haiku"]
vendor = "anthropic"
capability = 1
cost = 1

[models."anthropic/fable"]
vendor = "anthropic"
capability = 5
cost = 5
flags = ["refuses_defensive_security"]
```

`core/tiers.toml`：

```toml
[tiers.fast]
min_capability = 2
pick = "cheapest"

[tiers.frontier]
pick = "most_capable"
```

`hosts/claude/binding.toml`：

```toml
[models]
"anthropic/sonnet" = "sonnet"
"anthropic/opus" = "opus"
"anthropic/fable" = "fable"
"anthropic/haiku" = "haiku"
```

換模型的流程（以 codex 把 strong 換成新模型為例）：在
`core/models.toml` 加一筆、在 `hosts/codex/binding.toml` 的 `[models]`
加一行，執行 `render --host codex --write`；dist 與 golden 由工具更新。

## Alternatives Considered

### 方案 A：catalog 加規則式 resolver（採用）

規則簡單、結果可解釋，`--explain` 能說明每個選擇。

### 方案 B：維持手寫 tiers，只加一個「批次替換模型」的 script

改動最小，但沒有往「只定義 role」前進，也無法表達資安排除這類限制。

### 方案 C：用 benchmark 分數自動排名

長期可以拿來校準 `capability`，但分數會隨測試集變動，直接驅動選模
會讓 render 結果不穩定。先以人工登記的等級為準，benchmark 只當參考。

## Rabbit Holes

- **跨廠牌的 capability 可比性**：resolver 只在單一 host 的可用集合內
  比較，第 1 步只需要同一 host 內的相對順序正確。
- **為了重現現況而倒推數值**：初版數值確實是校準出來的，要在
  `models.toml` 註明；之後用 benchmark 修正時必須走 golden diff review。
- **cost 的單位**：用 1–5 的相對級距，不放實際價格，避免價格變動
  就要改 catalog。
- **OpenCode 的 fallback 候選**：維持在 binding 的 per-role 欄位，
  不納入 resolver。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| M1 | `core/models.toml`、`core/tiers.toml`、resolver、`--explain` | 單元測試：選法、同分排序、R4 排除、R9 失敗 |
| M2 | 五個 host 加 `[models]`，移除手寫 `[tiers]`（grok 改 `selection = "inherit"`） | R8：5 host `--check` 綠、golden 零 diff、全套測試綠 |
| M3 | 換模型流程文件與 mutation 測試 | 在 catalog 加一個假模型，只有預期的 role 改變 |

## Decisions

1. 既有 WIP（codex root 改 `gpt-6.1-sol`）非必要，已收進
   `git stash`（2026-10-02）；本 spec 在 `feat/model-catalog` branch
   從 `e4e1808` 實作。
2. `security_avoid_frontier` 在 M2 直接移除，不留相容期。
