# 輕量 lane：brief 帶確切修改（v3.12.0）

Miyago 核准一次性 migration，`claude-applier-agent` 這次跳過 change budget；
`max_lines`、`max_bytes`、required fragments 與 version gate 照舊。

| 條款 id | 舊 | 新 |
| --- | --- | --- |
| bootstrap-effort | `#fast` brief = goal、files、done-criteria | brief 加上 main 已讀檔案的確切修改；hand-back 引用的通過檢查即為 main 回報的驗證，模糊才重跑 |
| direct-when-small | light lane brief = goal、files、done-criteria；role 只查自己改的 | 同上；字數精簡，main 仍不改檔（`#direct` 除外） |
| verify-own-work | 完成前跑自己改動相關的檢查 | 不重讀 brief 已給內容的檔；最後只跑一次 done check |
| final-message | 回報驗證了什麼、怎麼驗 | 回報實際跑的檢查指令與結果 |
| write-tools（Claude addendum） | 用 Write/Edit 改檔 | 同一檔所有 hunk 用一次 Edit，或 Write 整檔 |
