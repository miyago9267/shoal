---
title: 審查列出隱含權衡與隱私檢查
status: approved
approved_by: Miyago
created: 2026-10-04
updated: 2026-10-04
---

<!-- markdownlint-disable MD025 -->

# 審查列出隱含權衡與隱私檢查

## Background

依 Andrew Ng《The AI Engineering Skills Map》（The Batch Issue 366）的實踐
清單，挑出 shoal 的 role contract 接得住的兩項：

- 「接受 agent PR 前，強迫寫下它做的三個隱含權衡」。
- 「為安全與隱私單獨列檢查表（agent 最容易省略的兩軸）」。

現況（2026-10-04 查證，main `747d871`）：

- verifier 有 advisory 與 `finding-fields`，但沒有任何條款要求列出實作做
  了哪些權衡（`core/contracts/verifier.toml`）。
- security-reviewer 有 7 條 core 條款（`identity`、`inspect-scope`、
  `distinguish-evidence`、`report-fields`、`main-session-carries`、
  `no-modify`、`no-delegate`），沒有隱私相關內容。
- Claude 的 orchestration policy 把 identity/privacy 列為 security-sensitive
  trigger（`hosts/claude/src/skills/pilotfish-orchestration/references/`
  `orchestration-policy.md:111-112`）；Codex 的 policy 沒有這份清單。
- 五個 host 都是 `role_text = "core"`，core 條款的改動會 render 到所有 host。

## Requirements (EARS)

- **R1（隱含權衡）**：When verifier 回報 `CONFIRMED` 或 `REFUTED`，it shall
  另列實作做了哪些隱含權衡，最多三項；每項寫明取捨了什麼、換到什麼。
  沒有可辨識的權衡時寫「none identified」。條款須明講權衡項目不是 finding，
  也不是 advisory，不需要附 `finding-fields` 的 P0-P4 欄位。
- **R2（權衡不擋結論）**：The trade-off list shall 是資訊欄位，不得成為
  `REFUTED`、priority 或 `INCONCLUSIVE` 的理由；權衡本身若造成實際缺陷，
  依既有的 finding 規則以 finding 回報，不靠權衡欄位升級。
- **R3（隱私檢查）**：When security-reviewer 檢視的範圍涉及個人資料、
  識別資訊、記錄或保存的資料，it shall 檢查：收集與保存的最小化、資料
  流向（含 log、telemetry、錯誤訊息、第三方）、存取與刪除，並把結果併入
  既有的 `report-fields` 格式。範圍不涉及時寫明「privacy: not in scope」；
  這句只說明隱私範圍，不取代沒有 finding 時必須寫出的「no findings」聲明。
- **R4（條款中立）**：新條款 shall 通過 role-contracts R1 的 host 中立檢查
  （不含 host 專屬工具、模型或機制名稱），以 core 條款形式加入。
- **R5（Codex 輸出與 lock）**：The change shall 通過 prompt document lock：
  受影響 surface 在變更預算內，且同一批變更 bump 根目錄 `VERSION`；
  不修改 `LOCK.json`，不需要 `--allow-lock-update`。
- **R6（legacy 同步）**：Codex 的 `hosts/codex/src/agents/{verifier,`
  `security-reviewer}.md` shall 同步加入相同句子，使
  `test_core_and_addenda_reassemble_the_legacy_text` 維持通過。

## Non-goals

- **A3（判定 interaction shape 時寫一行理由）**：判定者是 main session，
  要改的是各 host 的 orchestration policy，不是 role contract。五個 host
  的 policy 尚未統一（role-contracts 的 Non-goals），只改部分 host 會擴大
  漂移；Codex 側還要同步兩份受 lock 保護、必須逐位元組相同的檔案。等
  policy 統一後另案處理。
- 不在 plan-verifier 加權衡欄位（見 Decision 1）。
- 不改 Claude 或其他 host 的 orchestration policy。
- 不新增 role、不改選模與權限推導。

## Decisions

1. **權衡放 verifier，不放 plan-verifier。** 隱含權衡是「實作做了什麼
   取捨」，只有在 outcome 階段看得到實際 diff；plan 階段只能看到計畫，
   而且 plan-verifier 的 `verdict-ready` 規定 `READY` 不得附其他文字，
   加欄位會直接衝突。
2. **權衡欄位位置**：接在 `finding-fields` 之後，作為獨立段落；
   `checkpoint`（`direction_checkpoint`）回報不需要此欄位。
3. **隱私條款位置**：接在 `distinguish-evidence` 之後（段落邊界），作為
   獨立段落，沿用既有的 `report-fields`，不新增回報格式。不放在
   `inspect-scope` 之後：它與 `distinguish-evidence` 以 `sep = "space"` 接在
   同一段，插入會讓 Codex 模板第 11-13 行整段重排，估計 changed_lines 11、
   ratio 約 0.29，超出 lock 預算。
4. **版本**：根目錄 `VERSION` 依 lock 的 VERSION gate 從 `1.1.0` bump 到
   `1.2.0`，CHANGELOG 新開 v1.2.0 段；Codex host 版本（`hosts/codex/VERSION`、marker、
   `plugin.json`、`install/install.py`）同步 bump（見 Open question 2）。
   註：claude-eval-parity 的 Decision 6（2026-10-04）決定 VERSION gate 改為
   依 host 判斷。該變更合併前，本 spec 仍依現行 gate bump 根目錄
   `VERSION`；合併後改為 bump Codex host 版本。

## 受保護 surface 與預算

只有 Codex 的 `templates/agents/*.toml` 在 prompt lock 內；`hosts/claude`
等其他 host 不在 lock 內（見 claude-eval-parity spec）。

| surface | 目前行數／bytes | 上限 | 預估新增 | 預估變更比例 | 上限比例 |
|---|---|---|---|---|---|
| `templates/agents/verifier.toml` | 80／4920 | 95／6000 | 3–4 行、約 240 字元 | 約 0.02 | 0.2 |
| `templates/agents/security-reviewer.toml` | 24／1153 | 35／1800 | 5 行（第 13 行後純新增）、約 320 字元 | 約 0.12 | 0.2 |
| `templates/agents/plan-verifier.toml` | 46／2353 | 60／3100 | 不變 | 0 | 0.2 |

- 行數與比例依 `install/validate_prompt_lock.py:155-181` 的算法估計（變更
  行 = 舊行數 + 新行數；比例 = 變更字元 / 新舊全文長度和）。
- 最緊的是 security-reviewer 的 bytes：餘裕約 640 bytes，隱私條款不得
  超過 4 行正文。
- 另有絕對變更預算：verifier 是 `max_changed_lines` 16、
  `max_changed_characters` 2200；security-reviewer 是 10、1300。預估新增量
  都在範圍內，security-reviewer 的 10 行與 bytes 並列最緊。
- 兩個 surface 的 `required_fragments` 不受影響（只新增段落）。
- 驗收以 main（`747d871`）為 base 跑 `validate_prompt_lock.py --json`：
  `security-reviewer-agent` 的 changed_lines ≤ 10、change_ratio ≤ 0.2。

## Host 影響

| host | 受影響檔案 | golden |
|---|---|---|
| claude | `hosts/claude/dist/agents/{verifier,security-reviewer}.md` | `tests/golden/claude/agents/` 兩檔 |
| codex | `templates/agents/{verifier,security-reviewer}.toml` | `tests/golden/codex/agents/` 兩檔 |
| agy | `hosts/agy/dist/agents/{verifier,security-reviewer}/agent.md` | `tests/golden/agy/agents/{verifier,security-reviewer}/agent.md` |
| grok | `hosts/grok/dist/agents/{verifier,security-reviewer}.md` | `tests/golden/grok/agents/` 兩檔（`roles/*.toml` 不含 prompt 文字，不變） |
| opencode | `hosts/opencode/dist/roles/{verifier,security-reviewer}.md` | `tests/golden/opencode/roles/` 兩檔 |

- agy 的 dist 被 `~/.gemini` 以 symlink 使用，merge 後立即生效；Claude 隔天
  auto-update 生效；Codex 需重新安裝。
- OpenCode 對 security-reviewer 有 `replace:main-session-carries`、
  `replace:no-delegate`，新條款以 `after:distinguish-evidence` 定位，不衝突。
- grok 的 SubagentStop gate（`hosts/grok/dist/hooks/subagent_stop_gate.py`）
  只檢查格式，不需修改：權衡欄位與「privacy: not in scope」不會被誤擋，
  `tests/test_grok_hooks.py:186-194` 不受影響。但「privacy: not in scope」
  不符合 `NO_FINDING_RE`（`:27-32`），所以 R3 明講它不取代「no findings」。
- `tests/test_role_contracts.py` 的 `EXPECTED_REPLACES`、`EXPECTED_ADDENDA`
  不需要改；`test_every_core_role_contains_every_unreplaced_clause` 會自動
  要求新條款逐字出現在每個 host。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| A1 | verifier 的權衡條款、Codex legacy 原文同步 | 五個 host `--check` 綠；`validate_prompt_lock.py` ok；全套測試綠 |
| A2 | security-reviewer 的隱私條款、Codex legacy 原文同步 | 同上；security-reviewer surface bytes ≤ 1800 |
| A3 | 根目錄 `VERSION` 1.2.0、Codex host 版本、CHANGELOG v1.2.0 段、更新 golden | CI 三平台綠 |

A1 與 A2 可合併成一個 commit，因為 VERSION gate 以 base 為準，一次 bump 即可。

## Rollback

revert 該 commit 即可；agy 立即回到舊文字，Claude 隔天回到舊文字。

## Open questions

1. **（已決定，2026-10-04）WORK-STATUS 的 Claude 限制**：Miyago 決定解除
   限制，Claude 不鎖版本。core 條款的改動照常 render 到 Claude host。
2. **（已決定，2026-10-04，採建議）Codex host 版本同步 bump**：
   Codex 的 agent prompt 會改變，但 marker 仍是 `pilotfish-codex v1.8.1`。同步 bump 會多動到
   `templates/agents-md.*`、`plugin.json`、`install/install.py`、
   `hosts/codex/VERSION`（皆為單行變更，在預算內；mirror 依
   `LOCK.json:248-253` 同步）。同步 bump，以免安裝後的 marker 與內容不符。
3. **（已決定，2026-10-04，採預設）權衡的回報位置**：是否也要 security-reviewer 列權衡（例如安全與
   可用性的取捨）？不要，以保持單一職責。
