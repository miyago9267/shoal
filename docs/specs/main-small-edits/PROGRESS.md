# main-small-edits 進度

狀態：approved（Miyago，2026-10-25）。P1、P2 已實作；P3 本機試用中。

- [x] P1 plans 豁免（Python、TS、向量、grok／claude-guard 副本；2026-10-25，分支 `fix/claude-plans-exempt`）
- [x] P2 預設與條款（分支 `feat/claude-declare-default`，2026-10-25）
  - guard：Claude `SHOAL_GUARD_R1` 預設 `declare`
    （Python、TS mirror、grok／claude-guard 副本、向量、docs/guard.md、docs/reference.md）
  - policy：`prompts/hosts/claude/policy-addenda/bootstrap.md`
    以 `replace:bootstrap-delegate-default` 改寫 Claude bootstrap；
    Codex 輸出與 LOCK.json 位元組不變
  - DESIGN-INVARIANTS 第 2、3 條、
    `tests/test_policy.py`、`tests/test_delegation_default.py` 同步
  - `prompts/hosts/claude/policy-addenda/orchestration.md`
    以 `replace:direct-when-small` 改寫 Claude 的 `orchestration-policy.md`；
    `hosts/claude/VERSION` 升為 3.14.0-beta（LOCK version gate），
    `orchestration-policy.md` 19598 / 19600 bytes
- [ ] P3 本機試用：2026-10-25 至 2026-11-01。結束後檢視 guard log 的宣告率（`rule: declare` 紀錄與 `reason`），
  判斷 main 是否在非簡單工作上宣告後自己做；偏高就回到本 spec 檢討（含退回 `strict`）。

決定紀錄（Miyago，2026-10-25）：

- D1：直接改 Claude host 預設為 `declare`；`SHOAL_GUARD_R1=strict` 還原。
- D2：簡單工作沿用 `lean-default` D2 定義，不設檔數門檻；簡單工作宣告後自己改，其餘仍派 role；risk trigger 不變。
- D4：保留一行宣告 `: shoal-direct "<理由>"`。
- D5：不跑 benchmark，改本機試用一週後檢視宣告 log。

- 2026-10-25：合入 origin/main 的 guard 修正（#43，3.13.2-beta），
  `hosts/claude/VERSION` 升為 3.14.1-beta；declare 預設與 python 寫檔偵測並存。
