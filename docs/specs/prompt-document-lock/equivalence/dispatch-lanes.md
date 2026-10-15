# 派工分 lane、先切片再平行：舊條款與新條款對照（v3.10.0）

Miyago 2026-10-15 決定「切小、平行、用最便宜且夠用的 role」成為所有 host 的共用規則，
並核准一次性 migration。`claude-orchestration-policy` surface 跳過 change budget；
`max_lines`、`max_bytes`、required fragments 與 version gate 照舊，caps 不變。
來源是 `core/policy/orchestration.toml` 與 `core/policy/bootstrap.toml`。

| 條款 id | 舊 | 新 |
| --- | --- | --- |
| dispatch-kind-label | 寫入 role 的 label 以 kind 開頭 | 先標 `[fast]`／`[complex]`／`[rigorous]`，再接 kind；guard 擋缺漏或不符 |
| bootstrap-kind-label | 同上（Codex 省略） | 同上 |
| small-parallel-units | 派工要小，disjoint 的一起發 | 派工前先列獨立切片，一份 brief 一個目的，disjoint 切片同一則訊息發出 |
| delegate-cost-benefit / mech-direct-blocker | 較長的 `#direct` 與 unavailable worker 敘述 | 同義縮寫，為 byte cap 讓出空間 |
| mech-default / parallel-launch / watcher-long-commands | 原文 | 只縮短用字，語意不變 |
