# TASKS — grok-workflow

> `SPEC.md` 已核准（plan-verifier READY）。每個 phase 驗證後各自 commit；
> G5 至 G7 由 main session 處理。

## Phase G1 — orchestration rules 與 grok VERSION

- [x] 上游 v1.0.6 的 `rules.pilotfish-grok.md` 逐字 vendor 到
      `hosts/grok/src/rules/pilotfish-grok.md`，只換 marker。
- [x] 新增 `hosts/grok/VERSION`（`1.0.6-shoal.1`）。
- [x] renderer 輸出 `rules/pilotfish-grok.md`，marker 由 `VERSION` 產生。
- [x] 上游原文放 `tests/fixtures/grok/`，測試確認除 marker 外相同。
- [x] 以 `refresh_golden.py --host grok --from-dist` 更新 golden。
- [x] 五個 host 的 `render --check` 通過，其他四個 host 的 dist 與 golden
      沒有 diff。

## Phase G3 — grok 原生 hooks

- [x] `hosts/grok/src/hooks/` 放設定 JSON 與兩支 Python 腳本（標準函式庫），
      renderer 輸出到 `hosts/grok/dist/hooks/`。
- [x] `SubagentStop` 三個 entry（定錨 matcher），以 hook 的 `env` 欄位
      `PILOTFISH_ROLE` 區分 role。偏離 SPEC R10 的「參數」：官方文件只記載
      「相對於 JSON 的路徑」這種無參數 command，帶參數時是否仍解析相對路徑
      未記載；腳本也接受第一個參數，優先於環境變數。
- [x] 格式規則從 `dist/agents/` 的實際文字推導；測試確認 gate 要求的 token
      仍出現在 agent 文字。
- [x] `stopHookActive` 放行；任何解析錯誤 fail-open。
- [x] `PreToolUse` plan mode 防護（R12 的判斷順序），grok home 可由參數或
      環境變數覆寫。
- [x] 以 `refresh_golden.py --host grok --from-dist` 更新 golden。

## Phase G2 — tools/install_grok.py

- [ ] 從 committed HEAD（`git archive`）取 `hosts/grok/dist` 與 `VERSION`。
- [ ] 預設 dry-run，列出新增、取代、略過；`--apply` 才寫入。
- [ ] 寫入前備份被取代的檔案與 `config.toml` 到
      `<grok-home>/backups/shoal-<timestamp>/`。
- [ ] 偵測 `[subagents.toggle]` 把 shoal role 設成 `false`；`--fix-toggles`
      以最小文字編輯只刪除那些 key。
- [ ] `--restore <dir>` 逐位元組還原；`--uninstall` 只移除 shoal 檔案。
- [ ] 安裝後驗證 hash 與 marker。
- [ ] 測試全部用 temp 目錄當 `--grok-home`。

## Phase G4 — 文件與版本

- [ ] README host 表、安裝方式、歸屬連結。
- [ ] `INSTALL.md` 新增 grok 段落。
- [ ] `upstream.lock` 的 grok 項目。
- [ ] 根目錄 `VERSION` 改 `1.1.0`；`CHANGELOG.md` 的 `## Unreleased`
      改 `## v1.1.0`。
- [ ] `core/README.md` 視需要更新。

## 由 main session 處理

- [ ] G5：實際安裝到 `~/.grok`（含 `--fix-toggles`）。
- [ ] G6：dotfile 的 `check_agent_rule_sync.sh`（R14）。
- [ ] G7：fresh verifier、v1.1.0 tag 與 GitHub Release。
