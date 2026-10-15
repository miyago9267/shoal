# applier 改為快速執行器：舊條款與新條款對照（v3.9.0）

Miyago 2026-10-15 決定把執行分成快速、複雜、嚴謹安全三層，`applier` 是快速層，並核准一次性
migration。兩個 applier surface（`mechanical-executor-agent`、
`claude-applier-agent`）跳過 change budget；
`max_lines`、`max_bytes`、required fragments 與 version gate 照舊。來源是
`core/contracts/applier.toml`。

| 條款 id | 舊 | 新 |
| --- | --- | --- |
| identity | leaf mechanical executor | fast leaf executor for small, bounded changes；仍不能 delegate |
| exact-execution | fully-specified tasks，exactly | 小而有界的 task，照 brief；可做局部小判斷，不做設計決定 |
| verify-own-work | 跑 spec 指定的檢查 | 只跑自己改動相關的檢查，不跑 full suite；約 10 分鐘 time-box |
| route-judgment | 需要 judgment 或跨系統就停 | 範圍超出 brief、需要設計決定、或跨 module 就停，交給 `executor` |
| stop-on-bad-spec | spec 有誤就停，re-spec | 同，改稱 brief，re-brief 或改派 |
| foreground / no-detach / final-message / no-spawn | 原文 | 不變 |

Claude binding 同時把 `applier` 的 model 從 `sonnet` pin 為 `haiku`，effort 維持 `low`。
