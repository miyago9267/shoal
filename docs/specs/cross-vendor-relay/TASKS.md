# cross-vendor-relay：TASKS

每完成一項就更新；狀態 `[ ]` 未做、`[x]` 完成。決策與範圍見 SPEC.md。

## P0 安全審查

- [x] T0.1 `security-reviewer` 審 D5–D8 與 `SHOAL_RELAY_ROLE` guard 變更，
  finding 與處置寫入 SPEC.md「Security review」（F1–F12，2026-10-21）

## P1 Claude host -> Codex（executor、applier）

- [x] T1.0 實測：在 Claude Code subagent 裡跑
  `codex exec --sandbox workspace-write --json -o <f>`（stdin 關閉），記錄巢狀
  sandbox 是否成功與需要的設定；確認 D6 各 `-c` key 的實際名稱；記錄
  `--ignore-user-config` 下 AGENTS.md、hooks、`spawn_agent` 何者仍在；確認
  F2、F3、F6、F12 標「實測」的項目並跑 S1.20 canary。任何一項無法達成就停下
  回報。結果寫入 PROGRESS.md（完成；F2/F3/F6 由 Miyago 2026-10-21 決定，見
  SPEC.md「T1.0 後的決策」）
- [x] T1.1 `core/contracts/handback.schema.json` 與 `core/vendors.toml`
  （codex：指令、access -> sandbox 對應、固定旗標、最低版本）
- [x] T1.2 `tools/shoal_relay.py`：組指令（含 D6 固定旗標與 D7 brief 標記）、
  關 stdin、逾時 kill、讀 `-o` 檔、驗 schema、印正規化 hand-back，含 Security
  review F1、F6–F11；以假 vendor binary 測試（S1.1–S1.7、S1.14–S1.19）；由
  `security-executor` 實作
- [x] T1.3 `tools/render.py` 讀 `[relay.roles]` 與 `[relay] shell_model`：產出
  同名 relay 外殼 subagent、把 runner 打包進 plugin、relay-only addendum 只在
  啟用時併入、拒絕 security role 與未知 vendor；`render --check` 涵蓋（S0.3、
  S1.8–S1.10）
- [x] T1.4 guard 支援 `SHOAL_RELAY_ROLE` 備援（S1.11）；由 `security-executor` 實作
- [x] T1.5 `shoal doctor`：binary、登入、版本、API key 環境變數警告（S1.12）
- [x] T1.6 bench/ab 新增 `shoal-relay` arm：用 bench 專用 relay binding overlay
  render 到該 arm 的 plugin-dir，`shoal` arm 維持 relay 關閉；跑 v2 任務，結果
  寫入 PROGRESS.md（S1.13）（S1.13 未達標，見 PROGRESS 2026-10-22）
- [ ] T1.7 S1.13 達標後才做：`hosts/claude/binding.toml` 啟用
  `executor = "codex"`、`applier = "codex"`，重新 render dist 與 `.sha256`
  （S1.13 已於 2026-10-22 放寬並達標。阻塞：relay 開啟後 `hosts/claude/dist` 的
  `agents/executor.md`、`agents/applier.md` 與 `orchestration-policy.md` 超過
  `docs/specs/prompt-document-lock/LOCK.json` 的行數、位元組與變更預算，需要
  Miyago 核准的 lock renewal；待核准前不改 binding。）
- [ ] T1.8 共同驗收（S0.x）與 fresh `verifier`
