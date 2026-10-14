# guard-every-gate 進度

規格：[SPEC.md](./SPEC.md)。版本：v3.6.0（S6）。分支 `guard-every-gate`，
draft PR #1。

## 各 slice

| Slice | Commit | 內容 |
| --- | --- | --- |
| spec | `cec173a`、`2054d08` | spec 草稿；依 plan-critic 的缺口修訂 |
| S0 | `3c33ad8`、`6a6fe41` | 只取 payload，不改規則；spec 核准 |
| S1a | `cb79039` | E1 於 Python guard、TS mirror、共用向量，預設關閉 |
| S1b | `67e1a88` | Claude 預設啟用 E1，`#direct` 可放行；不變式第 3 條 |
| S2 | `3097085` | Codex：`SubagentStart` 確認啟動，預設啟用 E1 |
| S3 | `c8e0479`、`9ae4686` | OpenCode：`bash`、`apply_patch`，`session.created` |
| S4 | `a00671e` | Grok：預設 enforce，`subagent_start`，shell 寫檔 |
| S5 | `fe102ed` | agy：預設 enforce，以 conversation 區分 main 與 subagent |
| S6 | 本 commit | 版本 3.6.0、CHANGELOG、INSTALL.md 預設值修正、本檔 |

## 實測 payload 的證據

只存欄位名與形狀，不存內容。

- S0：`tests/fixtures/claude_subagent_tool_shapes.json`（subagent 改檔、
  Workflow 子 agent）、`tests/fixtures/codex_subagent_tool_shapes.json`
  （subagent 改檔、spawn 成功與失敗）、
  `tests/fixtures/opencode_guard_event_shapes.json`（opencode 1.18.31）。
- S0 後段：`tests/fixtures/grok_guard_event_shapes.json`（Grok CLI 1.0.46）、
  `tests/fixtures/agy_guard_event_shapes.json`（agy 1.3.4）。
- 共用向量：`tests/fixtures/guard_vectors.json`（Python 與 TS 共用）。
- 已實測的行為：Grok 的 deny 對 main 與 subagent 的 `write`、
  `spawn_subagent` 都被遵守；agy 的 deny 對 main 與 subagent 的
  `write_to_file` 都被遵守。

## 付費實測用量

| Host | 次數 | 備註 |
| --- | --- | --- |
| Claude | 2 | |
| Codex | 3 | |
| OpenCode | 3 | |
| Grok | 4 | 核准 3 次，多 1 次：capture hook 的 matcher 太寬，重跑 |
| agy | 2 | |

## 尚未 live 驗證

來源是 SPEC 的 E8 檢查表與 INSTALL.md。

- Grok：`stop` 的 `{"decision":"block"}` 輸出（目前只記 `would_block`，
  `SHOAL_GUARD_STOP=enforce` 才擋）。
- Grok：派出不存在的 role 會怎樣（一次觀察像是起了通用 subagent）。
- agy：各事件的先後順序（`SessionStart` 認領 `invoke_subagent` 的 pending）
  只是推斷，沒有多組並行的實測。
- agy：`--event` 參數的 hook 註冊在 agy 實際觸發的情形。
- agy：`Stop` 的擋住輸出格式。
- OpenCode：subagent 的 `bash` 被 throw 後是否真的 deny。
- OpenCode：`permission.ask`（尚未量測）、`session.promptAsync` 重新提示。
- Codex：舊註冊升級到 `shoal-guard-v4` 後，用 `/hooks` 重新核准的流程；
  核准前以第一次工具呼叫作為啟動依據的路徑。

## 已知限制

- 2026-10-14 本機負載過高，完整 unit suite 沒有跑完；只跑了 render、
  prompt lock、install、plugin、delegation default 與 OpenCode `bun test`
  等針對性檢查。整合驗證交給 PR #1 的 CI。
- CI 結果：待 CI。
