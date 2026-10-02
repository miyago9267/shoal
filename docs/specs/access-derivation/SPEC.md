---
id: spec-access-derivation
title: 權限由存取等級自動推導（role-only 定義的第 3 步）
status: approved
created: 2026-10-02
updated: 2026-10-02
author: Miyago
approved_by: Miyago
tags: [access, permissions, binding, render]
priority: high
---

<!-- markdownlint-disable MD025 -->

# 權限由存取等級自動推導

## Background

role-only 路線的第 3 步（見 [model-catalog](../model-catalog/SPEC.md)
Background）：使用者只定義 role，權限由 shoal 依 host 配置。

第 1 步之後，模型已由規則選出，但每個 host 的 `binding.toml` 仍替每個
role 手寫權限欄位：

| host | 手寫欄位 |
|---|---|
| Claude | `tools` 或 `disallowedTools` |
| Codex | `sandbox_mode`、`web_search` |
| agy | `tools` |
| grok | `capability_mode` |
| OpenCode | `required_capabilities` |

`core/roles.toml` 其實早就有 `access`，只是 render 只拿它做驗證（例如
read-only 不可含 Write），沒有用它產生輸出。同一個等級在同一個 host
重複寫在好幾個 role，新增 role 或調整等級的權限時要逐個 role 改。

## Requirements (EARS)

- **R1**：Each role in `core/roles.toml` shall 以 `access` 宣告存取等級，
  並可用 `capabilities = [...]` 宣告額外能力；core 不含任何 host 專屬的
  工具或欄位名稱。能力詞彙目前只有 `web`。
- **R2**：Each host binding shall 以 `[access.<level>]` 宣告每個存取等級
  在該 host 輸出的權限欄位；binding 實際用到的每個等級都要有對應表
  （沒有欄位要輸出時寫空表），缺少時 render shall 以 exit 2 失敗並指出
  是哪個 role、哪個等級。
- **R3**：Where a role 宣告了 capability，the binding shall 有對應的
  `[capabilities.<name>]`（可以是空表，表示該 host 沒有對應開關）；
  缺少時 exit 2。capability 的 list 欄位 shall 附加到 access 表同名的
  list（access 表沒有該 list 時不輸出）；scalar 欄位直接設定，與 access
  表衝突時 exit 2。
- **R4**：Where a role 層級寫了權限欄位，the field shall 覆寫推導值（以
  欄位為單位整個取代）；Claude 的 `tools` 與 `disallowedTools` 互斥，
  覆寫其中一個時丟掉另一個。
- **R5**：The existing validation rules shall 改成對推導後的結果檢查：
  Claude read-only 必須是 `tools` allowlist 且不含
  `Write`/`Edit`/`Bash`/`NotebookEdit`；agy read-only 必須是 `tools`
  allowlist 且不含 `run_command`；Codex read-only 必須是
  `sandbox_mode = "read-only"`、非 read-only 不可是；grok 只有 read-only
  role 可是 `read-only`。If 對應表或覆寫使 read-only role 取得寫入能力，
  then render shall 以 exit 2 失敗。
- **R6**：Where a host 專屬 role（Claude `Explore`、Codex `sol-executor`）
  在 `[extra_roles.<name>]` 宣告 `access`，the role shall 走同一套推導。
- **R7**：When `render --host <h> --explain` runs，the tool shall 對每個
  role 印出 `access`、`capabilities`、套用的對應表、有無覆寫，以及推導出
  的欄位。
- **R8**：When 這個 spec 的實作完成，五個 host 的 render 結果 shall 與
  目前的 dist、`templates/` 與 golden 逐位元組相同。
- **R9**：If binding 的 `[access.*]`、`[capabilities.*]` 或覆寫使用了不屬於
  該 host 的欄位、不在詞彙內的名稱或錯誤的型別，then render shall 以
  exit 2 失敗並指出位置。

## Non-goals

- 不改 role 的文字內容，不改選模（第 1、2 步的範圍）。
- 不動 `install/`、`hooks/`、`plugin/`。
- 不為了消掉覆寫而發明只給單一 role 用的 capability。
- 不做執行期的權限判斷；推導只發生在 render 時。
- 不處理新增 host 的腳手架（第 4 步）。

## 設計

```text
core/roles.toml
  [roles.security-reviewer]
  access = "read-only"
  capabilities = ["web"]            # 新增、選用、host 中立

hosts/<h>/binding.toml
  [access.read-only|write|verify]   # 新增：等級 -> 該 host 的權限欄位
  [capabilities.web]                # 新增、選用：capability -> 權限欄位
  [roles.<name>]                    # 同名欄位變成選用覆寫
```

推導順序：`[access.<access>]` -> 依序疊加 `[capabilities.<name>]` ->
role 層級覆寫。權限欄位的集合是每個 host 固定的（`PERMISSION_KEYS`）：

| host | 欄位 |
|---|---|
| Claude | `tools`、`disallowedTools` |
| Codex | `sandbox_mode`、`web_search` |
| agy | `tools` |
| grok | `capability_mode` |
| OpenCode | `required_capabilities` |

各 host 的對應表：

| host | read-only | write | verify | `web` |
|---|---|---|---|---|
| Claude | `tools = [Read, Glob, Grep]` | `disallowedTools = [Agent, Workflow]` | `disallowedTools = [Write, Edit, NotebookEdit, Agent, Workflow]` | `tools += [WebSearch, WebFetch]` |
| Codex | `sandbox_mode = "read-only"` | 空 | `sandbox_mode = "workspace-write"` | `web_search = "live"` |
| agy | `tools = [view_file, grep_search, find_by_name, list_dir, send_message]` | 空（不限制） | read-only 的 tools + `run_command` | `tools += [read_url_content, search_web]` |
| grok | `capability_mode = "read-only"` | `"all"` | `"execute"` | 空（無對應開關） |
| OpenCode | `required_capabilities = [tools, streaming]` | `[tools, streaming, reasoning]` | 同 write | 空（無對應開關） |

`web` 疊加在 write 或 verify 等級時：Claude 的這兩級是 denylist，本來
就允許 web 工具，agy 的 write 沒有 allowlist，所以都不輸出；agy 的
verify 是 allowlist，會附加。

### 保留的 role 層級覆寫

| host | role | 欄位 | 原因 |
|---|---|---|---|
| OpenCode | `security-reviewer` | `required_capabilities = [tools, streaming, reasoning]` | `required_capabilities` 是模型能力需求，不是權限。read-only 的 `scout`（fast）只需要 tools 與 streaming，同為 read-only 的 `security-reviewer`（strong）需要 reasoning；兩者差異來自 tier，不來自 access 或 capability。 |

其餘四個 host 沒有覆寫。`tests/test_access_derivation.py` 以清單鎖住這個
集合，新增或移除覆寫要明確改測試與本表；另有測試檢查覆寫值不得等於推導值。

## Alternatives Considered

### 方案 A：對應表加 capability 疊加，覆寫為選用（採用）

role 層級只剩真正的例外；等級的權限只寫一次，換權限時改一處，並由
mutation 測試證明所有該等級的 role 一起改變。

### 方案 B：把 `required_capabilities` 的 `reasoning` 做成 core capability

可以消掉 OpenCode 唯一的覆寫，但 `reasoning` 描述的是模型能力而非 role
需要的權限，只有 `security-reviewer` 一個 role 用，等於為單一 role 發明
capability；而且和 tier 重疊。不採用。

### 方案 C：從 tier 推導 OpenCode 的 `required_capabilities`

方向合理，但引入 tier 到能力需求的第二張對應表，超出第 3 步範圍，等
第 4 步新增 host 時再看是否值得。

## Rabbit Holes

- **capability 在 denylist 上的意義**：Claude write/verify 用 denylist，
  capability 的 allowlist 擴充沒有東西可擴。規則是「access 表沒有該 list
  就不輸出」，而不是報錯，否則每個 role 要依等級決定能不能宣告 web。
- **host 沒有對應開關**：grok、OpenCode 沒有獨立的 web 權限。選擇要求
  binding 明列空的 `[capabilities.web]`，而不是默默忽略，這樣新增
  capability 時不會有 host 靜默漏掉。
- **access 對應表不能表達的差異**：例如 agy 的 verify 比 read-only 多
  `run_command`，用獨立的 `[access.verify]` 表達，不用「疊加」，避免
  access 之間產生階層關係的假設。
- **覆寫的粒度**：以欄位整個取代，不做 list merge；需要 merge 的情況
  就是 capability 該表達的事。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| A1 | `render.py` 推導函式、表驗證、`--explain` | 單元測試：各等級推導、capability 疊加、覆寫、錯誤 |
| A2 | 五個 host 的 binding 加對應表並移除重複欄位；`core/roles.toml` 加 `capabilities` | R8：5 host `--check` 綠、golden 零 diff、全套測試綠 |
| A3 | read-only 不可被覆寫成可寫；對應表 mutation 測試；`core/README.md`、CHANGELOG | 改 `[access.read-only]`，所有 read-only role 的輸出一起改變 |

## Decisions

1. 唯一保留的覆寫是 OpenCode `security-reviewer` 的
   `required_capabilities`（見上表），不為它新增 capability。
2. binding 的 `[access.*]` 只要求實際用到的等級要有表；沒用到的等級可以
   省略，之後新增 role 用到時由 render 報錯提醒。
3. Miyago 已授權這條路線由 agent 決定細節；本 spec 在
   `feat/access-derivation` branch 從 `257d4e0` 實作。
