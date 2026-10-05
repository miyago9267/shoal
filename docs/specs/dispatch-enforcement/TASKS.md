# TASKS - dispatch-enforcement

> 規格見 [SPEC.md](./SPEC.md)（approved），進度細節見 [PROGRESS.md](./PROGRESS.md)。
> `docs/specs/_templates/` 不存在，格式沿用 `docs/specs/grok-workflow/TASKS.md`。
> 狀態以 2026-10-05 的工作樹為準；尚未 commit 的項目標註「未 commit」。

## Phase E0 - 實測（完成）

- [x] 五個 host 的 deny 能力、id 欄位、subagent 與 role 辨識、派工與編輯工具，
      結果在 [E0-RESULTS.md](./E0-RESULTS.md)。
- [x] Codex per-role sandbox 與網路實測：不生效，列為已知限制（R6）。

## Phase E1 - 核心與 Claude adapter（程式完成，未 commit）

- [x] `hooks/shoal_guard.py`：標準函式庫、單檔、`--host claude|codex|grok|agy`。
- [x] `tests/fixtures/guard_vectors.json` 與 `tests/guard_vectors_helper.py`（R8）。
- [x] `tools/guard_parity.py` 對照 dotfile guard，差異逐筆對應 R2。
- [ ] Jev provider 改寫 `turns/<session>.json`（dotfile，另案）。

## Phase E2 - Codex、grok adapter（程式完成，未 commit）

- [x] guard 的 codex、grok、agy adapter 與單元測試。
- [x] Codex installer 註冊 guard（見 E5）；reinstall 不觸發 `installed_hook_drift`。

## Phase E3 - OpenCode TS 移植、agy adapter

- [x] agy adapter（`shoal_guard.py`）。
- [ ] OpenCode TS 移植：由另一位 executor 進行中（`hosts/opencode/plugin/**`），
      本文件不涵蓋。

## Phase E4 - R6 權限補強

- [ ] binding、render、golden、lock：工作樹已有 claude、opencode 的變更（另一位
      executor），本次未驗證；Codex per-role 設定的實測結論已寫入 E0-RESULTS.md。

## Phase E5 - 安裝與註冊

程式（本次，未 commit）：

- [x] Codex：`install/install.py`、`install/hook_registration.py`。guard 是獨立的
      projection ID `shoal-guard-v1`，script 為
      `<codex-home>/hooks/shoal_guard.py`，state 新增
      `guard_registration` 與 target `hooks/shoal_guard.py`。群組定義放在
      `hook_registration.py`，不改 `templates/hooks.json`（lock surface，預算只容許 4 行）。
      `hosts/codex/VERSION` 1.8.2 到 1.8.3。`install/stage_smoke_home.py` 同步容許 guard。
- [x] Grok：`tools/render.py` 從 `hooks/shoal_guard.py` 產生
      `hosts/grok/dist/hooks/pilotfish-grok/shoal_guard.py`；`hosts/grok/src/hooks/pilotfish-grok.json`
      新增 `UserPromptSubmit` 與 `PreToolUse`（`^(search_replace|spawn_subagent)$`），保留
      plan_mode_guard。`tools/install_grok.py` 增加 dist 與同 commit 來源的一致檢查。
- [x] Claude、agy：新增 `tools/install_hooks.py`。
- [x] 文件：INSTALL.md、README.md、`hosts/codex/CHANGELOG.md`。
- [ ] `hosts/claude` 不放 settings snippet：entry 由 `install_hooks.py` 產生，靜態 snippet
      會成為第二份來源。

live（commit 之後，需要使用者核准）：

- [ ] Claude：`install_hooks.py --host claude --apply`，驗證實際擋下一次 main 越權改檔並放行
      派工後的改檔；dotfile 移除舊 guard 兩處註冊（獨立 commit）。
- [ ] Codex：`install/install.py` 真實安裝，使用者在 Codex 內以 `/hooks` 核准新 hook 一次。
- [ ] Grok、agy：`install_grok.py --apply`、`install_hooks.py --host agy
      --apply`，shadow log 產生
      `would_deny` 與派工後 allow 各一筆。
- [ ] OpenCode：隨 plugin 安裝（E3）。
- [ ] dotfile 設定：OpenCode `monika` 的 `task` 權限加入 `executor`。

## Phase E6 - 非 Claude host 切 enforce（條件化）

- [ ] 依 SPEC Open question 1：每個 host 至少 20 筆決策、至少 1 筆 `would_deny`、誤擋 0、
      `skip_reason` 比例 0，逐 host 切換並實際擋下一次。
