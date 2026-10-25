---
title: main 自己改簡單檔案，並修 plan mode 寫不了 plan 檔
status: approved
approved_by: Miyago (2026-10-25)
created: 2026-10-25
updated: 2026-10-25
---

<!-- markdownlint-disable MD025 -->

# main 自己改簡單檔案，並修 plan mode 寫不了 plan 檔

## Background

Miyago 2026-10-25 daily interview：shoal「太複雜」，希望 main session 自己改小檔案，不要
每次都派 applier／executor。同一天另發現：Claude plan mode 下 guard 擋掉 plan 檔
`~/.claude/plans/<name>.md`（plan mode 唯一允許寫的檔），main 完全產不出 plan 檔。

查證（2026-10-25，`hooks/shoal_guard.py` 為正本；`plugins/claude-guard/hooks/shoal_guard.py`
是逐位元組副本，`plugins/claude/hooks/shoal_guard.py` 只是相容 shim）：

- `resolve_r1`（`hooks/shoal_guard.py:716-726`）：`SHOAL_GUARD_R1` 未設定時，claude、codex、
  grok、agy、opencode 都是 `strict`。`strict` 只有已派可寫 role、`#direct`、
  `SHOAL_GUARD_DIRECT=1` 或豁免路徑會放行；宣告指令在 `strict` 是 no-op（`:1779-1787`）。
  `declare` 與宣告 `: shoal-direct "<理由>"` 已存在，要靠 env 選用。
- `is_exempt`（`:839-852`）只豁免 `/tmp`、`$TMPDIR`、`.ai` 目錄、
  `~/.claude/projects` 與 `$CLAUDE_CONFIG_DIR/projects`。沒有 `plans`，
  plan mode 的 bug 由此而來。
  TypeScript mirror 同樣缺：`hosts/opencode/plugin/src/guard/core.ts:848-858`。
- 條款：`prompts/policy/bootstrap.md:11`「The main session does not edit files itself」與
  `prompts/policy/orchestration.md:59`（`direct-when-small` 條款）。`plugins/claude/policy/
  claude-md.bootstrap.md:11` 是 `tools/render.py:1512` 產出的副本，不直接改。
- `docs/DESIGN-INVARIANTS.md:11-13`（第 2 條）與 `:14-17`（第 3 條）寫死「改檔一律由可寫的
  role 執行」「main 未派工就改檔（`#direct` 可放行）」。
- `lean-default`（2026-10-16 核准）原則 1 與 Goal 明訂不採 main 自己改檔為預設；2026-10-18
  實測仍是 v1 小任務成本 1.27 倍、時間 2.1 倍（baseline 為 1）。品質沒有因為多一層 role 變好。
- 歷史教訓：`guard-declared-direct` 的 live gate 發現 `declare` 模式下 Claude 每次都先宣告
  再自己做，宣告沒有改變行為，所以 2026-10-12 加 M9 `strict` 當預設。本 spec 等於刻意回頭，
  原本要防的「小功能全由 main 做」現在被接受為目標；風險改由 risk trigger 與 role 派工條件
  承擔。

## Supersedes

- `lean-default` 原則 1（「改檔仍由 role 做；`#direct` 是唯一出口」）與 Goal 的
  「不採 main 自己改檔為預設」：改為「簡單工作可由 main 宣告後直接改」。lean-default 其餘
  決定（D1 的 `#fast` 輕量 lane、D3、D4–D7）不變。
- `guard-declared-direct` M9／M10／M12 與 D6 中「`strict` 為預設」「不再寫宣告指令」的部分，
  僅限 Claude。
- `docs/DESIGN-INVARIANTS.md` 第 2、3 條需配合改寫（見 P2）。

## Requirements (EARS)

- **R1（plan 檔豁免）**：When host 是 claude，the guard shall 把 `~/.claude/plans` 與
  `$CLAUDE_CONFIG_DIR/plans`（絕對路徑時）下的路徑視為豁免，與 `projects` 同等處理；
  Python 與 TypeScript mirror 一致，加入 guard 測試向量。
- **R2（預設）**：Where host 是 claude 且 `SHOAL_GUARD_R1` 未設定，the guard shall 使用
  `declare`；其他 host 預設不變（`strict`）。`strict`、`classified`、`off` 仍可由 env 選用。
- **R3（簡單工作）**：While 工作符合簡單工作定義（沿用 `lean-default` D2：單一目的、範圍已知、
  不碰觸發條件、預期 10 分鐘內），when main 要改檔，the main session shall 先執行宣告指令再
  自己改；不設行數或檔數門檻。
- **R4（仍要派工）**：While 工作是多檔、需要判斷，或命中任一 risk trigger（security／trust、
  destructive／irreversible／external mutation、data／schema／migration、release、使用者要求
  獨立 review），the main session shall 派可寫的 role。Risk trigger 的條件與 role 權限不變。
- **R5（條款）**：Claude 的 bootstrap 與 orchestration 條款 shall 改寫為：簡單工作宣告後自己
  改；其餘派 role。`#direct` 仍可用。其他 host 的條款內容不變。
- **R6（不變）**：硬規則（leaf 不得派工、verify 類 role 不得改檔）、G4、R2 提醒、
  fail-open、subagent 行為不變。

## Decisions

| # | 問題 | 建議 |
| --- | --- | --- |
| D1 | Claude 預設 R1：`strict` 或 `declare` | **已決定（Miyago，2026-10-25）：直接改 Claude host 預設為 `declare`**，P2 實作。原建議：`declare`，只改 Claude 的 host 預設（不動 codex 等）。理由：宣告有 log 可稽核，不需新機制。替代：維持 `strict`，只在 Miyago 本機設 `SHOAL_GUARD_R1=declare`，零 public 影響但每台機器都要設。shoal 是 public repo，預設變更會影響其他使用者，release note 要寫清楚；可用 `SHOAL_GUARD_R1=strict` 還原 |
| D2 | policy 文字 | **已決定（Miyago，2026-10-25）**：簡單工作沿用 `lean-default` D2 定義（單一目的、範圍已知、不碰 risk trigger、預期 10 分鐘內），不設檔數門檻；main 宣告後直接改。多檔、需判斷、命中 risk trigger 仍派 role，risk trigger 不動。實作走 Claude 專屬 policy addendum（`prompts/hosts/claude/policy-addenda/`），Codex surface 與 LOCK.json 位元組不變 |
| D3 | exempt 加 `~/.claude/plans` 與 `$CLAUDE_CONFIG_DIR/plans` | 做。這是 bugfix，與 D1 無關，可獨立先出（P1） |
| D4 | 宣告成本：main 可否不宣告直接改簡單工作 | **已決定（Miyago，2026-10-25）**：保留一行宣告 `: shoal-direct "<理由>"`。成本是一次空 shell 呼叫，換來 log 理由可稽核，也保有「這件事該不該派工」的停頓點 |
| D5 | 驗收 | **已決定（Miyago，2026-10-25）**：不跑 benchmark。改為本機試用一週（2026-10-25 至 2026-11-01），結束後檢視 guard log 的宣告率（`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/guard.jsonl` 中 `rule: declare` 的紀錄與 `reason`），判斷 main 是否把非簡單工作也宣告後自己做 |

## Scope

- 改：
  - `hooks/shoal_guard.py`（`is_exempt`、`resolve_r1` 的 claude 預設）與副本
    `plugins/claude-guard/hooks/shoal_guard.py`；
  - TypeScript mirror `hosts/opencode/plugin/src/guard/core.ts`（`isExempt`、預設）；
  - `tests/fixtures/guard_vectors.json` 新增 plans 豁免與 claude 預設向量；
  - 條款來源 `prompts/policy/bootstrap.md:11`、`orchestration.md:59`，再用 `tools/render.py`
    產出 `plugins/claude/policy/claude-md.bootstrap.md` 與 Claude skill 的
    `orchestration-policy.md`；
  - `docs/DESIGN-INVARIANTS.md` 第 2、3 條；
  - 受影響測試：`tests/test_shoal_guard.py`、`tests/test_policy.py`（`:142-143`、`:153-154`
    斷言「main still does not edit files itself」）、`tests/test_delegation_default.py`。
- Lock：`templates/agents-md.bootstrap.md` 等 Codex surface 在
  `docs/specs/prompt-document-lock/LOCK.json`（`bootstrap-policy` 的 required
  fragment 含「The main session does not edit files itself」）。
  bootstrap／orchestration 來源是跨 host 共用，
  若條款改動波及這些 surface，需要一次 Miyago 核准的 lock renewal（流程見
  `docs/specs/prompt-document-lock/SPEC.md:47`，用 `validate_prompt_lock.py
  --allow-lock-update`，與 lean-default 相同）。建議先做成 Claude 專屬條款，讓 Codex surface
  位元組不變、免 renewal；做不到再 renew。待實作時確認，這是本 spec 最大的未知。
- 不改：role 權限、risk trigger、`strict` 模式本身、其他 host 的預設與條款、Jev。

## Phases

1. **P1 plans 豁免（獨立出貨）**：R1、guard 向量、Python／TS 一致，patch 版本。不碰條款與
   預設，無需 lock renewal。
2. **P2 預設與條款**：R2–R5、DESIGN-INVARIANTS、受影響測試；視 Scope 的判斷做 lock
   renewal；需 Miyago 核准後才實作。
3. **P3 本機試用**：2026-10-25 至 2026-11-01，之後依 D5 檢視宣告 log 決定是否發版；
   宣告用在非簡單工作的比例偏高就回到本 spec 檢討（含是否退回 `strict`）。

## Out of scope

- 檔數或行數門檻（沿用 `lean-default` D2，不設數字）。
- 其他 host（codex、grok、agy、opencode）的預設與條款。
- 降低 hook 延遲（屬 `lean-default` P1）。
- 取消 risk trigger 或 role 分工本身。

## Risks

- 回到 `declare` 後，main 可能把多檔或高風險工作也當簡單工作自己做。緩解：R4 與條款寫明
  觸發條件；P3 檢視宣告 log；log 可稽核。
- 預設改變影響 public 使用者。緩解：只改 Claude；release note 與還原方式
  （`SHOAL_GUARD_R1=strict`）。
- 條款改動超過 change budget。緩解：先做 Claude 專屬條款；不行就 lock renewal。
  實測（P2，2026-10-25）：Claude 專屬 addendum 可行，Codex surface 與 LOCK.json 不動、免 renewal。
  但 `claude-orchestration-policy` 與 `claude-orchestration-skill` 等 Claude surface 在 LOCK 內，
  任何改動都要升 `hosts/claude/VERSION`（version gate），且 `orchestration-policy.md` 只剩
  19598 / 19600 bytes 預算，`direct-when-small` 改寫須等量精簡。bootstrap 不在 LOCK 內。
  因此 P2 同時改 bootstrap 與 `orchestration.md:59` 的 Claude 版（addendum 精簡到不超過預算），
  並升 `hosts/claude/VERSION` 為 3.14.0-beta（2026-10-25 Miyago 核准）。
