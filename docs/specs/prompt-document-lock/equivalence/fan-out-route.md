# fan_out 路由（v3.13.0）

一次性 migration：`orchestration-template`、`packaged-orchestration-policy`、
`claude-orchestration-policy` 這次跳過 change budget；上限、required fragments
與 version gate 照舊。

| 條款 id | 變更 |
| --- | --- |
| fan-out-route | 新增：清單明確、項目獨立且各有份量，或要獨立視角才選；以整合檢查收尾，失敗只重派一次 |
| direct-when-small | 刪「Else see lifecycle below.」 |
| execution-gate | 刪與 delegate-cost-benefit 重複的 Routes 句 |
| mech-default | 刪「Foreground unless…」句 |
| delegate-cost-benefit | 括號定義改指 execution contract；刪與 direct-when-small 重複的 `#direct` 句 |
| brake-per-call | 刪與 mech-collect 重複的 Main retains 句 |
| large-investigation | 字詞精簡，意思不變 |
| risk-review-mandatory | 刪 mandatory 已含的 no extra opt-in |
| claude-fan-out-workflow | Claude 專屬 extensions addendum：Workflow 同意、agentType、改用並行 Agent |
