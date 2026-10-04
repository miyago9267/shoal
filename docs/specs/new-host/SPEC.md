---
id: spec-new-host
title: 不寫程式碼新增 host（role-only 定義的第 4 步）
status: approved
created: 2026-10-04
updated: 2026-10-04
author: Miyago
approved_by: Miyago
tags: [hosts, render, scaffold]
priority: high
---

<!-- markdownlint-disable MD025 -->

# 不寫程式碼新增 host

## Background

前三步完成後，role 只在 `core/` 定義一次，模型（第 1 步）、權限（第 3 步）
與 role 文字（第 2 步）都由 binding 和 core 推導。剩下的限制是：每個 host
仍需要在 `tools/render.py` 寫一個 renderer 函式，新增 host 就得改程式碼。

本步把「輸出格式」也變成 binding 的資料，讓大多數以「一個 role 一個
Markdown 檔加 frontmatter」為格式的 agent 工具，只靠設定就能接上。
Miyago 已授權這條路線由 agent 決定。

## Requirements (EARS)

- **R1**：The repo shall provide a generic renderer，`renderer = "generic-md"`
  的 host 不需要任何專屬程式碼。
- **R2**：Where a binding uses `generic-md`，it shall 以 `[output]` 宣告：
  - `path`：每個 role 的輸出路徑樣式（例如 `agents/{role}.md` 或
    `agents/{role}/agent.md`），dist 固定在 `hosts/<name>/dist/`。
  - `frontmatter`：有序的欄位清單，每個欄位宣告名稱、來源（`name`、
    `description`、`model`、某個權限欄位、`role.<key>`、或固定值）與編碼。
  - `role_fields`：`[roles.<r>]` 除了 `description`、`model`、`role_text` 與
    權限欄位之外允許的 key（例如 `["effort"]`）。來源 `role.<key>` 讀
    `[roles.<r>].<key>`，`<key>` 必須列在 `role_fields`；role 缺值時 exit 2，
    欄位設 `optional = true` 則省略該行。
  - 支援的編碼：`scalar`、`comma-list`（逗號串接成單行）、`block-list`
    （每項一行，可設縮排）、`folded`（`>` 多行，可設寬度與縮排）、
    `nested-map`（一層巢狀的 key: value）。
  - 權限欄位只能來自 `[access.*]` 與 `[capabilities.*]` 中**已宣告型別**
    的欄位（`[output.permissions.<field>] type = "list" | "scalar" | "map"`）；
    對應表出現未宣告的欄位時 exit 2。
- **R3**：The generic renderer shall 以第 1 步的 resolver 取得 model、以
  第 3 步的對應表取得權限欄位、以第 2 步的條款組裝 body（`role_text`
  必須是 `core`）；外框取自 `hosts/<name>/frames/default.md`。
- **R4**：Where a `generic-md` binding 宣告 `[extra_roles]`，the tool shall
  exit 2 並指出 role；host 專屬 role 不在通用 host 的範圍內。
- **R5**：The render tool shall 從 `hosts/*/binding.toml` 的 `renderer`
  欄位探索 generic-md host，`--host <name>` 不需要修改任何 `tools/` 檔案；
  既有五個 host 仍用各自的 renderer。
- **R6**：When `python3 tools/new_host.py <name>` runs，the tool shall 產生
  `hosts/<name>/binding.toml`，內含 `renderer = "generic-md"`、
  `role_text = "core"`、範例 `[output]`、空的 `[models]` 範例註解、三個
  `[access.*]` 表、空的 `[capabilities.web]`、每個 core role 的
  `[roles.<r>]`（含 description 佔位）；以及 `hosts/<name>/frames/default.md`
  與 `hosts/<name>/addenda/`。已存在時拒絕覆寫並 exit 2。未填 `[models]`
  前 `--check` 預期 exit 2，並提示要填 `[models]`。
- **R7**：The repo shall 有一個以探索為基礎的測試
  （`tests/test_generic_hosts.py`），對每個 generic-md host 檢查 `--check`
  與第 2 步的 R5（core 條款逐字出現）；新增 host 不需要新增測試檔。
  generic-md host 不使用 golden：committed dist 加 `--check` 即為回歸基準。
- **R8**：The existing five hosts shall 維持各自的 renderer，輸出逐位元組
  不變。
- **R9**：When a binding 宣告的 frontmatter 來源不存在或編碼不支援，
  the tool shall exit 2 並指出 host、role 與欄位。

## Non-goals

- 不支援非 Markdown 的輸出格式（TOML、JSON）；那類 host 仍寫專屬 renderer。
- 不自動產生 installer；新 host 的安裝方式寫在它自己的文件。
- 不遷移既有五個 host 到 generic-md。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| N1 | generic-md renderer、`[output]` 宣告與驗證、host 探索 | 單元測試：五種編碼、路徑樣式、R4、R9；既有 5 host 零 diff |
| N2 | 用 `[output]` 宣告在測試中重現 Claude 與 agy 的 `scout.md` | 兩者逐位元組相同（證明宣告能表達真實格式） |
| N3 | `tools/new_host.py`、`tests/test_generic_hosts.py`、`docs/new-host.md` | 不改任何 `tools/` 檔：temp 目錄 scaffold 假 host、只填 `[models]` 與對應表值，`render --write`、`--check` exit 0，`unittest discover` 全綠 |

## Decisions

1. 輸出格式以「每 role 一個 Markdown 檔加 YAML frontmatter」為唯一目標；
   N2 以 Claude 與 agy 的實際檔案驗證；grok 的 `${{ }}` 模板屬於外框內容，
   OpenCode 的 permission 以 `nested-map` 表達。
2. host 專屬 role 不支援（R4），需要時該 host 改寫專屬 renderer。
3. generic-md host 不建 golden（R7）。
4. 每個 role 不同的欄位（例如 effort）用 `role.<key>` 來源表達，key 由
   `[output].role_fields` 明確宣告，不開放任意 key；缺值預設失敗，
   `optional = true` 才省略。理由：固定值無法重現 Claude 七個 role 各自的
   effort（N2 要求逐位元組相同）；明確宣告讓拼錯的 key 仍會被拒絕。
