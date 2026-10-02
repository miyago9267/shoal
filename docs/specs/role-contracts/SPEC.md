---
id: spec-role-contracts
title: Role 契約統一到 core（role-only 定義的第 2 步）
status: approved
created: 2026-10-02
updated: 2026-10-02
author: Miyago
approved_by: Miyago
tags: [roles, prompts, contracts, render]
priority: high
---

<!-- markdownlint-disable MD025 -->

# Role 契約統一到 core

## Background

role-only 路線的第 2 步。第 1 步（模型目錄）與第 3 步（權限推導）之後，
各 host 還手寫的只剩 role 的 prompt 文字。2026-10-02 的盤點結果：

- 五個 host 風格不同：Claude 是電報體，Codex、agy、grok 是完整句子，
  OpenCode 是「描述加 `Return:` 條列」。
- 契約有落差：`direction_checkpoint` 只在 Claude 與 Codex 的 verifier；
  OpenCode 的 verifier 缺 `INCONCLUSIVE` 與 P0–P4；「前景執行、最多 10
  分鐘、不可 detach」OpenCode 全缺。
- 有互相矛盾的條款：plan-verifier 對「後續 slice 資料不完整」，Claude
  版要求擋下，Codex 版明講不算 REVISE 理由。

Miyago 已授權這條路線由 agent 決定並直接推進。

## Requirements (EARS)

- **R1**：The repo shall hold one host-neutral contract per core role at
  `core/contracts/<role>.toml`，由有序的條款組成；每個條款有穩定的
  `id`、完整句子的 `text` 與 `kind`（例如 `identity`、`boundary`、
  `procedure`、`verdict`、`final-message`、`leaf`、`foreground`）。
  條款文字不得出現 host 專屬的工具、模型或機制名稱。
- **R2**：Each host shall 以 `hosts/<h>/frames/` 提供外框（frontmatter、
  標題、host 專屬前言）與 `hosts/<h>/addenda/<role>.toml` 提供只在該
  host 有意義的補充；兩者都放在 `src/` 之外，不會被 passthrough 進
  dist。每個 addendum 有定位：`start`、`end`、`after:<clause-id>`、
  `before:<clause-id>`，或 `replace:<clause-id>`（以 host 專屬措辭取代
  某個條款）。render 的結果是「外框 + 依序排列的 core 條款與 addenda」。
- **R3**：Each host binding shall 有 `role_text = "core" | "legacy"`。
  `legacy` 時輸出現有 `src/agents`（或 `src/roles`）的原文。
- **R4**：When 2a 完成，所有 host 為 `legacy`，五個 host 的 dist shall
  與 2a 之前逐位元組相同。
- **R5**：When a host 切到 `core`，its rendered role shall 包含該 role
  在 `core/contracts` 的每一個條款（條款文字逐字出現），被
  `replace:<clause-id>` 取代的除外；每個 host 的 replace 清單由測試
  鎖定，新增 replace 必須同時改測試。
- **R6**：When a host 切到 `core`，an independent reviewer shall 比對
  該 host 每個 role 的新舊文字，確認舊文字中的每一條義務都由某個 core
  條款或 addendum 承接，或在本 spec 的 Decisions 明列為刻意移除。
- **R7**：Where a host 沒有某個 role（binding 的 `omitted_roles`），
  the renderer shall 不輸出它。
- **R8**：core 條款 shall 從 Codex 1.8.1 的 `developer_instructions`
  原句切出；Codex 專屬的句子以定位 addendum 放回原位置。When Codex
  切到 `core`，its rendered `templates/agents/*.toml` shall 與切換前
  逐位元組相同，因此 prompt document lock（`LOCK.json` 的變更預算與
  `required_fragments`）、`tests/test_templates.py` 的逐句斷言、版本
  marker、`VERSION`、`plugin.json` 與 `install.py` 的版本都不需要變動。
  If 某個 Codex role 無法逐位元組重現，then 那個 role 在 Codex 維持
  `legacy` 並在本 spec 列出，不得為此修改 lock。
- **R9**：`role_text` shall 可以在 binding 的 role 層級覆寫
  （`[roles.<name>].role_text`），供 R8 的例外與分批切換使用。

## Non-goals

- 不統一 orchestration policy（Claude 的 skill、Codex 的 AGENTS.md 政策）；
  那是 main session 的規則，host 機制差異大，另案處理。
- 不新增 role，不改選模，不改權限推導。
- 不把 Claude 的文字壓回電報體；core 條款以精簡的完整句子為準。

## Decisions

條款一律以 Codex 1.8.1 的原句為準（Miyago 最近親自演進、有 prompt lock
保護、Claude fork 也以移植它為目標）。其他 host 切到 `core` 後承接這些
條款，因此：

1. plan-verifier 對後續 slice 資料不完整：採 Codex 版（不算 REVISE
   理由）。Claude 版的「remains blocking」刻意移除。
2. verifier：所有 host 都取得 `CONFIRMED` / `REFUTED` / `INCONCLUSIVE`、
   P0–P4、REFUTED 優先，以及 `outcome_verification` 與
   `direction_checkpoint` 兩種 contract。
3. scout、executor、security 類 role 的回報格式與「停下回報」的措辭
   都採 Codex 的寫法；Claude 的 `mis-routed` 用語、OpenCode 的六欄
   回報與 READY/REVISE 格式刻意移除。
4. 寫入與驗證類 role 的「前景執行、每個指令最多 10 分鐘、不可 detach」
   採 Codex 的句子；Codex 某個 role 沒有這句的，其他 host 也不補。
5. Codex 專屬內容（`semantic_adjudication`、`ESCALATE_TO_EXECUTOR`、
   模型與 effort 綁定說明）是 Codex 的 addenda，不進 core。
6. Claude 的工具停用說明、grok 的 frontmatter 與 `${{ tools.* }}`
   模板、agy 的 `# Agent System Instructions` 標題與工具限制句、
   OpenCode 的 frontmatter 與 permission 是各自的外框或 addenda。
7. grok 切到 `core` 後不再與上游 v1.0.6 逐位元組相同；`upstream.lock`
   改記為 `derived`，`test_vendored_files_are_copied_verbatim` 改成只
   比對 `agents/` 以外的檔案。
8. host 專屬 role（`Explore`、`sol-executor`）維持 host 自己的文字。
9. OpenCode 只有 5 個 role，`omitted_roles` 不變。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| 2a | 條款結構、`role_text` 開關、`frames/` 與 `addenda/` 機制；全部 host 設 `legacy` | R4：dist、templates、golden 零 diff；全套測試綠；CI 三平台綠 |
| 2b-1 | 從 Codex 切出 `core/contracts` 七個 role 與 Codex addenda；Codex 切到 `core` | R8：Codex `templates/` 零 diff、`validate_prompt_lock.py` ok、R5 測試綠；CI 綠 |
| 2b-2 | 依序切換 agy、grok、OpenCode、Claude 到 `core`；每個 host 一個 commit，更新該 host 的 golden | 每個 host：R5 測試綠、R6 reviewer 通過、CI 綠後才切下一個 |
| 2c | 移除不再使用的 `legacy` 原文與開關（保留一個 release 之後） | 另行決定 |

2b-1 同時是條款切分的證明：core 條款加 Codex addenda 能逐位元組拼回
Codex 原文，代表切分沒有遺漏或改寫。

## Rollback

任一 host 把 `role_text` 改回 `legacy` 並 `render --write` 即可回到舊
文字；Claude 隔天 auto-update 生效，agy 立即生效，Codex 需重新安裝。
