# OpenCode role 文字對照表（Phase 2b-2）

OpenCode 的五個 role 從 `legacy` 切到 `core`（D9：沒有 mech-executor 與
plan-verifier，`omitted_roles` 不變）。本表逐條列出
`hosts/opencode/src/roles/<role>.md`（`e7a9e28`）的每一項義務，標示它在
core 輸出中的去處。供 R6 reviewer 比對。

記號：

- 「前言」是 `SPEC.md` Decisions 的前言：條款一律以 Codex 1.8.1 原句為準，
  同一義務的措辭差異以 core 條款承接。
- `D<n>` 是 `SPEC.md` Decisions 的編號。
- 外框是 `hosts/opencode/frames/<role>.md`：每個 role 一份，內容是原檔的
  frontmatter（`description`、`mode: subagent`、`permission`）與
  `# <Title>` 標題，逐字照舊（D6）。
- addendum 在 `hosts/opencode/addenda/<role>.toml`。
- 沒有 Decision 可以引用的義務一律保留成 addendum，沒有刪除。

OpenCode 的用語是 parent session，core 的 `no-spawn`、`no-delegate` 與
`orchestrator-owns` 寫的是 main-session 與 orchestrator，因此在 OpenCode
用 replace 改成 parent session（共 7 個，見
`tests/test_role_contracts.py` 的 `EXPECTED_REPLACES`）：

- scout 的 `no-delegate`、security-reviewer 的 `no-delegate`。
- executor、security-executor、verifier 的 `no-spawn`。
- verifier 的 `orchestrator-owns`：改為「parent session，也就是這份
  instructions 提到的 orchestrator」，同時作為其他條款裡 orchestrator 的對照。
- security-reviewer 的 `main-session-carries`：core 句子提到「第一次
  plan-verifier review」，OpenCode 沒有 plan-verifier，改成 parent session
  在核准前把 findings 與 dispositions 帶進自己的 Plan。

executor 與 security-executor 另有 addendum `parent-session-owns` 以相同
方式說明 orchestrator 是 parent session。

legacy 完全沒有「前景執行、10 分鐘、不 detach」；依 D4，executor、
security-executor、verifier 由 core 條款取得，OpenCode 的 bash 工具有
timeout 參數，不需要 replace。

## scout

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-10 frontmatter，含 `edit`、`bash`、`task`、`webfetch`、`websearch` 全部 `deny` | 外框 | 保留（D6） |
| L12 標題 `# Scout` | 外框 | 保留（D6） |
| L14 針對聚焦的問題收集有範圍的證據 | addendum `assigned-paths` | 保留（無 Decision 可引用） |
| L14-15 只搜尋被指派的路徑 | addendum `assigned-paths`（同一則） | 保留（無 Decision 可引用） |
| L15 讀最小而有用的片段 | `search-breadth` | 保留 |
| L15-16 不編輯檔案、不做實作決定 | `no-edit-design-guess` | 保留 |
| L18-25 固定六欄回報：Scope、Files or sources read、Findings、Evidence、Uncertainty、Next action | 移除 | D3（OpenCode 的六欄回報；回報改用 `report-answer` 與 `state-evidence-gap`） |
| L27 parent session 擁有 synthesis 與最終判斷 | addendum `parent-session-owns` | 保留（無 Decision 可引用） |
| L27-28 被發現的事實在 parent 驗證前只是輸入 | addendum `parent-session-owns`（同一則） | 保留（無 Decision 可引用） |
| 無（legacy 只在 frontmatter 以 `task: deny` 強制） | `no-delegate`（replace 成 parent session 用語） | 新增（core 的 leaf 條款） |

## executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-4 frontmatter | 外框 | 保留（D6） |
| L6 標題 `# Executor` | 外框 | 保留（D6） |
| L8 在被指派的檔案與模組內實作已核准的 contract | addendum `assigned-scope` | 保留（無 Decision 可引用） |
| L8-9 沿用既有的專案慣例 | `work-like-senior`（read context to match conventions） | 保留 |
| L9-10 執行必要且有範圍的檢查 | `work-like-senior`（verify by exercising the change） | 保留 |
| L10 在擴大 scope 前先回報含糊之處 | addendum `assigned-scope`（同一則）；`escalate-fork` | 保留 |
| L12-18 固定五項回報：Changed paths、Behavior changed、Verification run、Remaining risk、Follow-up needed | `final-message` | 移除（D3，回報格式採 Codex） |
| L20 parent session 擁有 scope、整合與最終判斷 | addendum `parent-session-owns` | 保留（無 Decision 可引用） |
| L20-21 不 spawn 其他 agent | `no-spawn`（replace 成 parent session 用語） | 保留 |
| L21-22 不擅自更換 provider、model、permission、session policy | addendum `parent-session-owns`（同一則） | 保留（OpenCode 機制，D6 精神） |

core 新增、legacy 沒有：`identity`、`own-local-design`、`no-extras`、
`escalate-fork`、foreground 全部條款（D4）、`final-message`。

## security-executor

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-4 frontmatter | 外框 | 保留（D6） |
| L6 標題 `# Security Executor` | 外框 | 保留（D6） |
| L8 只套用已核准的 security 變更 | `approved-contract-only` | 保留 |
| L8-9 既有控制至少一樣強 | `work-defensively`（never weaken an existing control） | 保留 |
| L9 不暴露或輪替 credentials | addendum `credentials-and-blockers` | 保留（無 Decision 可引用） |
| L9-10 執行指定的 security 檢查 | addendum `credentials-and-blockers`；`regression-checks` | 保留（無 Decision 可引用） |
| L10 遇到阻礙時回報確切的 blocker，不擴大存取或 scope | addendum `credentials-and-blockers`；`regression-checks`（不超出核准範圍） | 保留（無 Decision 可引用） |
| L12-18 固定五項回報：Changed paths、Security behavior、Verification run、Residual risk、Rollback note | `final-message` | 移除（D3，security 類 role 的回報格式採 Codex） |
| L20 parent session 擁有核准、整合與最終判斷 | addendum `parent-session-owns` | 保留（無 Decision 可引用） |
| L20-21 不 spawn 其他 agent | `no-spawn`（replace 成 parent session 用語） | 保留 |

core 新增：`identity`、`state-assumptions`、foreground 全部條款（D4）。

## security-reviewer

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-10 frontmatter，含 `edit`、`bash`、`task`、`webfetch`、`websearch` 全部 `deny` | 外框 | 保留（D6） |
| L12 標題 `# Security Reviewer` | 外框 | 保留（D6） |
| L14-15 檢查被指派的 authentication、authorization、secret-handling、validation、permission、dependency、trust-boundary surface | addendum `inspect-surfaces`；`inspect-scope` | 保留 |
| L15-16 核准前先收集證據 | `inspect-scope`、replace 後的 `main-session-carries`（核准前帶進 Plan） | 保留 |
| L16 unknown capability 視為 unknown | addendum `inspect-surfaces`（同一則） | 保留（無 Decision 可引用） |
| L18-23 固定五項回報：Findings and severity、Attack or misuse paths、Evidence、`READY` 或 `REVISE`、Next action | `report-fields`、`distinguish-evidence` | 移除（D3，security 類 role 的回報格式與 READY/REVISE 格式） |
| L25 不編輯檔案 | `no-modify` | 保留 |
| L25 不授予 permission、不提出無界的重寫 | addendum `no-permission-grants` | 保留（無 Decision 可引用） |
| 無（legacy 只在 frontmatter 以 `task: deny` 強制） | `no-delegate`（replace 成 parent session 用語） | 新增 |

core 新增：`identity`、`main-session-carries`（replace 後寫成 parent
session 的 Plan）。

## verifier

| legacy 義務 | 去處 | 移除理由 |
|---|---|---|
| L1-7 frontmatter，含 `edit: deny`、`task: deny` | 外框 | 保留（D6） |
| L9 標題 `# Verifier` | 外框 | 保留（D6） |
| L11-12 獨立檢查被宣稱的結果、相關 diff、acceptance 檢查、重要邊界 | `outcome-input`、`falsify-claim`、`primary-flow-first`、`edge-set-after-evidence` | 保留（D2） |
| L12-13 在 OpenCode 授權的範圍內跑有範圍的檢查 | addendum `permission-checks` | 保留（OpenCode 機制，D6 精神） |
| L13 絕不修復實作 | `read-and-run-only`、`no-plan-edit-fix` | 保留 |
| L15-18 兩種 verdict：`CONFIRMED`、`REFUTED` | `verdict-confirmed`、`verdict-refuted`、`verdict-inconclusive` | 取代（D2：所有 host 取得三種 verdict 與 P0 到 P4） |
| L20 附上證據、未驗證的 claim、一個下一步 | `verdict-confirmed`（每項條件與證據）；addendum `report-extras`（同一句保留） | 保留（無 Decision 可引用） |
| L20-21 parent session 擁有最終判斷 | replace 後的 `orchestrator-owns` | 保留 |

core 新增（D2）：`name-one-contract`、`no-inferred-checkpoint`、
`direction_checkpoint` 全部條款、`recheck`、`finding-fields`、
優先序、`security-verification`、foreground 全部條款（D4）、`no-spawn`。
OpenCode 沒有 orchestration policy，不會在 brief 點名 contract，因此加
addendum `default-contract`：未點名時視為 `outcome_verification`。

## 風險與備註

- `hosts/opencode/plugin/src/role-contract.ts` 的 `DEFAULT_ROLE_DEFINITIONS`
  仍描述 security-reviewer 輸出 `REVISE or READY`、verifier 輸出
  `CONFIRMED or REFUTED`。那是 plugin 內部的資料，不經 render，也沒有 TS
  測試把它和 role md 對照；本次沒有改，之後要不要同步需另行決定。
- plugin 的 TS 測試沒有斷言 role md 的內容，沒有為此修改任何 TS 測試。
- `parent-session` 的 replace 讓 OpenCode 的條款與 core 有 7 處不同，
  清單由測試鎖定。
