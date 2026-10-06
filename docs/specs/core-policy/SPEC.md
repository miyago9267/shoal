---
title: Orchestration policy 抽成 core 條款
status: approved
approved_by: Miyago
created: 2026-10-06
updated: 2026-10-06
---

<!-- markdownlint-disable MD025 -->

# Orchestration policy 抽成 core 條款

## Background

自 [generic-shoal](../generic-shoal/SPEC.md) 拆出（plan-verifier 2026-10-06
建議：P 有獨立的 rollback、lock renewal 與逐 host 驗證迴圈）。現況（main
`7bed030` 查證）：

role 文字已由 `core/contracts` 加 host addenda 組成，policy 仍是逐字複製：

- Claude：bootstrap 27 行、SKILL 36 行、`orchestration-policy.md` 244 行、
  `workflow-extensions.md` 150 行（`tools/render.py:340-358`）。
- Codex：bootstrap 47 行、`agents-md.orchestration.md` 674 行
  （`render.py:409-440`），另有 plugin 內的 byte-identical mirror
  （`render.py:943-947`）。
- agy：rules 35 行、SKILL 124 行（`render.py:498`）。
- Grok：rules 257 行，逐字取自上游 pilotfish-grok v1.0.6（`render.py:547-557`）。
- OpenCode：沒有任何 policy 文字（`render.py:619-647`）。
- 共同的段落（named-role 豁免、lifecycle 關卡、READY／REVISE、dispatch brake、
  ownership、P0-P4 裁決、recovery、AUTO／ASK）在 Claude、Codex、Grok、agy 都有，
  但措辭各自改寫，不只是工具名稱不同（`Agent`、`spawn_agent`、
  `spawn_subagent`、`invoke_subagent`）。
- workflow extensions（outcome continuation、review intent、decision
  checkpoint、task ledger、continuation、circuit breaker、direction
  checkpoint）只有 Claude 與 Codex 有；interaction shape 與 risk triggers
  Grok、agy 沒有。
- `core/README.md:62-64` 已預留 `core/policy/`。

### Prompt lock 的硬上限

`install/validate_prompt_lock.py:52-55、104-112` 對既有路徑的 surface 有
不能經 `LOCK.json` 放寬的上限：每次 32 changed lines、4000 changed
characters、ratio 0.35；只有 base 不存在的新路徑才跳過 diff 預算
（`:341-359`）。renewal（`Lock-Renewal: approved`）只放寬 `LOCK.json` 本身的
變動（`docs/specs/prompt-document-lock/SPEC.md:47-52`）。Codex
`templates/agents-md.orchestration.md`（674 行）與其 plugin mirror、Claude 的
policy surface 切到 core 條款，一次必然超過上限。

## Requirements (EARS)

- **P1（單一來源）**：The orchestration policy shall 由 `core/policy/` 的條款
  加各 host 的 policy addenda 與 frame 組成，沿用 role 契約的機制（`id`、
  `sep`、`after:`／`before:`／`replace:`），不另寫一套組裝器。
- **P2（host 中立）**：core 條款 shall 不含 host 專屬的工具、模型或機制名稱；
  派工工具等名稱以 binding 提供的 placeholder 代入（例如 `{{dispatch_tool}}`）。
  沿用 `tests/test_role_contracts.py` 的禁字檢查。placeholder 以單次 regex
  代入：未知 key 直接報錯，值不得含 `{{` 或換行。
- **P3（能力差異）**：When 某 host 缺少某項能力（例如沒有 decision checkpoint
  的 UI），the binding shall 以 `[policy].omit` 列出省略的條款與理由；測試要求
  每個省略都有理由，未列出的條款一律輸出。
- **P3a（不可省略的條款）**：core 條款中標為 `required` 的集合（至少包含
  named-role 豁免、risk trigger 與核准、security-reviewer 到 security-executor
  的路徑、destructive／external 確認、secret 處理）shall 不得被 omit 或
  `replace:`；各 host 的 omit 與 replace 清單比照 `EXPECTED_REPLACES`
  （`tests/test_role_contracts.py:591-599`）鎖在測試內，變更要同時改測試。
- **P4（切換與 rollback）**：binding 以 `policy_text = "core" | "legacy"` 選擇
  來源，與 `role_text` 相同；`legacy` 保留現行原文，作為逐 host rollback。
- **P5（OpenCode）**：OpenCode shall 也輸出 policy，並由 installer 接到
  OpenCode 的 instructions 設定；具體掛載點以實測決定。
- **P6（lock）**：Claude、Codex 的 policy surface 改寫幅度會超出現行預算，
  shall 依 Open question 1 的 migration 規則逐 host 切換：每個 host 一個 migration
  commit，bump 該 host 版本，各自需 Miyago 核准。

## Non-goals

- 不改 role 定義、選模、權限推導與 dispatch guard。
- 不追上游 pilotfish 的新版本。

## Decisions

1. **canonical 基準取 Claude**：Claude 的 policy 加 workflow extensions 最
   完整，也已移植 Codex 1.8.1 的 7 段規則（`upstream.lock`）。Codex 專屬的
   Luna／Sol／Astra 選模段落放 Codex addenda。
2. **Grok rules 不再逐字取自上游**：`upstream.lock` 的 grok 已是
   `kind = "derived"`，只需更新 `source` 說明 rules 改由 core 條款產生。
3. **行為等價的驗證**：每個 host 切到 `core` 前，產出 legacy 與 core 的逐段
   對照表（每條 legacy 規則對應到哪個 core 條款或 addendum，或明列刪除理由），
   由 plan-verifier 審。不以文字相同為標準。
4. **`required_fragments`**：core 條款保留各 lock surface 的
   `required_fragments` 原文，或在同一次 lock 變更內更新。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| P0 | prompt-document-lock 的一次性 migration；CI `paths` 加入 `core/**` | prompt-document-lock SPEC 改寫「不放寬既有 surface 預算」一句並記錄 decision、status 改回 active；validator 測試：base 與 head 都有標記且無 flag 時超預算失敗、有 flag 但標記已在 base 時失敗、PR label 路徑拒絕 migration、標記 surface 超 `max_bytes` 或缺 fragment 仍失敗、對照表不存在或在 repo 外時失敗、未標記的 surface 不受影響、反向 migration 通過 |
| P1 | `core/policy/` 條款與組裝、placeholder、omit、required、`policy_text` 開關 | 組裝器測試（含 omit／replace required 條款時失敗、placeholder 單次代入）；`legacy` 輸出與現行 dist byte-identical |
| P2 | Claude 切 `core` | 逐段對照表經 plan-verifier 審過；core 輸出跑 `validate_prompt_lock.py` 為 ok；golden |
| P3 | Codex、Grok、agy、OpenCode 逐 host 切 `core` | 同 P2；OpenCode 的 instructions 掛載實測 |

## Rollback

該 host 的 binding 改回 `policy_text = "legacy"`。切回 legacy 的 diff 同樣
超過 hard ceiling，所以 rollback 也是一個帶 `migration`（新的 `migration_id`，
對照表可引用原表的反向對應）與 `Lock-Renewal: approved` trailer 的 commit，
需 Miyago 核准。

## Open questions

1. **（已決定，2026-10-06）Lock 上限怎麼處理**：採一次性 migration，規則
   如下（P0 實作與測試以此為準）：
   - **標記**：`LOCK.json` 的 surface 加 `migration`，內容為唯一的
     `migration_id` 與逐段對照表路徑 `equivalence`。
   - **生效條件**：同時滿足才生效：validator 帶 `--allow-lock-update`；base 的
     manifest 中該 surface 沒有相同 `migration_id`；CI 走 push 路徑（head commit
     含 `Lock-Renewal: approved`）。PR label 路徑不接受 migration。
   - **失效**：base 已含相同 `migration_id` 時，validator 忽略標記，照常套用
     hard ceiling；標記留著無效，下一次 renewal 時移除。
   - **只放寬變更預算**：只跳過 `check_change_budget`；`max_lines`、
     `max_bytes`、`required_fragments`、mirror 與 version gate 照常檢查。
   - **對照表**：`equivalence` 必須是 repo 內的相對路徑（通過
     `_is_relative_repo_path`），在 HEAD 存在且非空，固定放在
     `docs/specs/core-policy/equivalence/<host>.md`。
   - **逐 host 各一次**：Claude、Codex 等每個 host 的切換是各自的 migration
     commit，各自要 Miyago 核准。
   - hard ceiling 本身不變。
2. **（已決定，2026-10-06）OpenCode policy 的掛載點**：`opencode.json` 的
   `instructions`，不碰使用者的 AGENTS.md。
