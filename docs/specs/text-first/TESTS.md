---
spec: text-first
batch: 1
created: 2026-10-22
---

# Tests: Text first

> Spec: `docs/specs/text-first/SPEC.md`

編號 R1 到 R8 對應 SPEC 的 Requirements。`Shall` 為驗收條件；「每個 phase」
指 P1、P2、P3a、P3b、P4。

## 驗收條件 (EARS)

### R1：文字單一來源

- **When**: P2 完成。
- **Shall**: `prompts/` 之外的 TOML 與 Python 不含送進 model 的文字；
  `prompts/` 內每個 marker 都被某個 host 的 render 使用或有明確的 omit 理由。
- **驗證方式**:
  - `git grep -n "'''" -- core hosts/*/addenda hosts/*/policy-addenda` 無輸出。
  - `migrate_text.py` 的逐條相等斷言全過（id、kind、sep、required、at、join、
    text、description）。
  - 單元測試：每個 `prompts/` marker 的 id 皆被 `render --explain-policy` 或
    role 輸出涵蓋；孤兒 marker 使測試失敗。
- **狀態**: [ ] 未驗證

### R2：輸出逐位元組不變

- **When**: 每個 phase 完成。
- **Shall**: claude、codex、agy、grok、opencode 與 claude-plugin 的 render 輸出
  與 `origin/main` 逐檔 sha256 相同。
- **驗證方式**: `python3 tools/render_equiv.py --base origin/main --head HEAD`
  退出 0，印出的總雜湊寫入該 phase 的 PROGRESS。工具以各 ref 自己的
  `render.py --write` 在 temp root 重新產生所有輸出再比對，所以被停止 commit
  的檔案也被涵蓋；另對 head working tree 執行 `render --check`。
- **狀態**: [ ] 未驗證

### R3：死檔不能復活

- **When**: `hosts/*/src` 內存在會被 core policy 輸出覆蓋的檔案。
- **Shall**: render 以非 0 結束並在錯誤訊息指出該路徑。
- **驗證方式**: 單元測試在 temp root 放入 `hosts/claude/src/claude-md.bootstrap.md`
  及一個 agy 的 `src/rules/shoal-agy.md`，兩者皆被拒絕；main 的真實樹不觸發。
- **狀態**: [ ] 未驗證

### R4：只 commit 有消費者的生成物

- **When**: P3a 與（選配）P3b 完成。
- **Shall**: `tests/golden/` 不存在；`templates/`、`plugins/*`、
  `.claude-plugin/`、agy / grok / opencode dist 仍被 commit 且 `render --check`
  通過；若做 P3b，`hosts/claude/dist` 不存在且 `EXPLORE_DIST` 指向存在的檔。
- **驗證方式**: `test_render_check.py`；CI 的 render check 步驟；刻意改 `prompts/`
  一個字而不 `--write`，兩者皆紅；`shoal_install.py --update` 在 temp HOME 的
  dry-run 通過。
- **狀態**: [ ] 未驗證

### R5：lock 有效、renewal 乾淨

- **When**: P1、P2、P3a、P4。
- **Shall**: `validate_prompt_lock.py --base-ref origin/main` 不帶旗標通過，
  `LOCK.json` 與所有 surface 檔案無 diff。
- **驗證方式**: 該指令退出 0，且 `git diff origin/main --stat -- LOCK.json
  docs/specs/prompt-document-lock templates plugins/codex` 為空。
- **When**: 採用 P3b，renewal commit R。
- **Shall**: R 只含 `LOCK.json`、`validate_prompt_lock.py` 與測試；訊息含獨立
  一行 `Lock-Renewal: approved`；不改 `VERSION` 與任何 prompt 內容。
- **驗證方式**: `git show --stat R` 的檔案清單；不帶旗標的 validator 在 R 上
  失敗、帶 `--allow-lock-update` 通過；push 後 CI 的 lock 步驟綠。
- **狀態**: [ ] 未驗證

### R6：行為測試保留

- **When**: P3a 完成。
- **Shall**: validation、`--check` / `--write` 行為、權限推導、installer、guard、
  relay、plugin 的測試數量不減；被刪的每個測試在 triage 表有理由。
- **驗證方式**: PROGRESS 的 triage 表；P3a 前後各列
  `python3 -m unittest discover -s tests -v` 的測試名稱，差集只含 triage 表中
  標 drop / convert 的項目。
- **狀態**: [ ] 未驗證

### R7：bench 拆出

- **When**: P4 完成。
- **Shall**: shoal 不含 `bench/` 與 28 個 bench 專用測試模組；shoal-bench 保留
  歷史並在 `SHOAL_ROOT` 指向 shoal 時測試全綠。
- **驗證方式**: shoal 的全套測試綠且 `git ls-files bench` 為空；shoal-bench
  的 `git log --follow bench/ab/run_ab.py` 保留原 commit；shoal-bench CI 綠；
  `SHOAL_AB_PLUGIN_REF` 指向 branch 時 `export_tree` 取得該 branch 的 plugin。
- **狀態**: [ ] 未驗證

### R8：三 OS CI 綠

- **When**: 每個 phase 的 PR。
- **Shall**: ubuntu、macOS、windows 的 Python tests、Markdown lint、prompt lock
  步驟全綠；PR 上 macOS / windows 跑跨平台子集，合併到 main 後三平台跑全套。
- **驗證方式**: PR checks 與 main 上 push 事件的 checks。Windows 特別檢查 md
  loader 對 LF 與 UTF-8 的處理（`.gitattributes` `eol=lf`）。
- **狀態**: [ ] 未驗證

## 測試案例

### 正常路徑

| # | 測試 | 預期結果 | 狀態 |
|---|------|----------|------|
| 1 | main 對 main 跑 `render_equiv.py` | 退出 0，雜湊相同 | [ ] |
| 2 | P1 刪 53 檔後全套測試 | 1915 個以內全綠，無新增失敗 | [ ] |
| 3 | P2 後 `render_equiv.py` | 退出 0 | [ ] |
| 4 | P2 後 `render --explain-policy` 各 host | 條款狀態與 P2 前相同 | [ ] |
| 5 | P3a 後 `test_render_check.py` | 六個 host 全綠 | [ ] |
| 6 | P4 後 shoal 全套測試 | 全綠，測試數減少 28 個模組 | [ ] |
| 7 | P4 後 shoal-bench 測試 | 全綠 | [ ] |

### 邊界案例

| # | 測試 | 預期結果 | 狀態 |
|---|------|----------|------|
| 1 | md 條款內含空行與列表 | 解析後 text 與 TOML 版相等 | [ ] |
| 2 | 條款 `sep=newline` / `space` + `join` addendum | compose 結果與 TOML 版相等 | [ ] |
| 3 | agy 多行 description 的尾端換行 | frontmatter 位元組相同 | [ ] |
| 4 | `required` 條款被 omit | 仍報 `required 條款不可 omit` | [ ] |
| 5 | 全部條款被 omit 的文件（codex skill） | 不輸出，與現況相同 | [ ] |
| 6 | relay 開啟（`--overlay`）時的 claude-plugin | 輸出與 P2 前相同 | [ ] |
| 7 | VERSION 升版而 frame marker 沒改 | 結構斷言失敗（agy、grok、claude） | [ ] |

### 錯誤處理

| # | 測試 | 預期結果 | 狀態 |
|---|------|----------|------|
| 1 | md 第一個 marker 前有文字 | `ContractError` 指名檔案與行 | [ ] |
| 2 | 重複 id / 未知 kind / 未知屬性 / 缺 `kind` | `ContractError` | [ ] |
| 3 | 正文行以 `<!-- clause:` 開頭 | 拒絕 | [ ] |
| 4 | md 含 CR | 拒絕 | [ ] |
| 5 | `render_equiv.py` 對改一個位元組的 ref | 非 0 並列出路徑 | [ ] |
| 6 | 不帶旗標改 `LOCK.json` | validator 失敗 | [ ] |
| 7 | 移除 `SHOAL_ROOT` 且預設路徑不存在 | shoal-bench 以明確訊息失敗 | [ ] |

## 備註

<!-- Batch 完成後隨 TASKS.md 一起封存 -->
