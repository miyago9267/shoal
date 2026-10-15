# repo-layout 任務

規格：[SPEC.md](./SPEC.md)。狀態：草稿，尚未核准；以下全部未開始。最高原則是
可移植性優先（SPEC 的 Principles）。

| Phase | 狀態 | 前置 |
| --- | --- | --- |
| P1 可移植入口、安裝缺口、README | 未開始 | 無 |
| P2 Codex 可移植登記（不搬檔案） | 未開始 | P1 |
| P3 `--update`；P3b dotfile 改呼叫它 | 未開始（P3b 是 dotfile，Miyago） | P2 |
| P4 文件拆分 | 未開始 | P1（README 衝突時 P1 先） |
| P5 install/ 瘦身 | 未開始 | P4 |
| P6 Claude plugin 搬到 plugins/ | 未開始 | P3b、P5 |
| P7 v3.11.0 發佈 | 未開始 | P1-P6 |
| P8 Codex plugin 實體搬移 | 延後 | lock renewal |

開工前 Miyago 要決定 D1-D11（見 SPEC）；建議值全部採用時可直接開始。

## P1 可移植入口、安裝缺口、README

- [ ] 查證 G4：全新 clone、沒有 `bun` 時 opencode 的行為
- [ ] 先寫 failing tests：G1（claude `--apply` 呼叫 `claude plugin ...`，已
  存在則 update）、G2（agy 建 agents、skills、rules 連結，不覆蓋非 symlink；
  Windows 無 symlink 權限時的退路寫在 tests）、G3（dry-run 呼叫底層
  dry-run）、G5（核心路徑不呼叫 `sh`、`bash`、`tar`）、G6（CLI 不存在時
  dry-run 為 `skipped`）
- [ ] G1：claude `--apply` 執行 marketplace add、plugin install；
  `claude-explore` 選中時安裝 `Explore.md`
- [ ] G2：agy 補 agents、skills、rules 連結；`os.symlink` 丟 `OSError` 時改
  複製並在 `modules.json` 記 `agy_mode: copy`；
  `tools/sync_global.py:402-403` 在 copy 模式改比對內容 sha256
- [ ] G2 測試（含 `windows-latest`）：monkeypatch `os.symlink` 丟
  `OSError`，`--host agy --apply` 後檔案等於 `hosts/agy/dist`；`--update`
  dry-run 回報 agy `up-to-date`
- [ ] G3：dry-run 轉呼叫底層 installer 的 dry-run 並顯示輸出
- [ ] G5（D9）：opencode 安裝步驟 Python 化，與 `sync_global.py` 共用
- [ ] G6：外部 CLI 一律 `shutil.which`
- [ ] `README.md` 快速開始改為
  `python3 tools/shoal_install.py --host <h> --apply`，Claude marketplace 兩
  行放在「替代方式」
- [ ] `docs/README.en.md`、`docs/README.zh-CN.md` 同步
- [ ] `python-tests.yml`：每個 OS 對五個 host 跑入口 dry-run（暫存 `HOME`）
- [ ] 驗收：unittest、`check_links.py`、markdownlint；
  `validate_prompt_lock.py` 通過；Windows job 綠

停止條件：五個 host 在暫存 `HOME` 下 dry-run 與 `--apply` 都符合預期，三個
OS 的 CI 綠。

## P2 Codex 可移植登記

- [ ] 在暫存 `CODEX_HOME` live 驗證：根 `.agents/plugins/marketplace.json`
  指向 `./plugin/plugins/...` 是否被接受；`miyago9267/shoal@<ref>` 是否可
  用；remove 後 cache 與啟用狀態
- [ ] 把 live 驗證結果與選擇（甲：根 manifest 加 `plugin/plugins/**`；乙：匯
  出 `plugin/` 子樹）寫回 SPEC F1b
- [ ] 甲案才新增 `.agents/plugins/marketplace.json` 並保留
  `plugin/.agents/plugins/marketplace.json` 一個 release；乙案不新增、無下架
  期
- [ ] `install/install.py`、`tools/sync_global.py`：匯出 committed HEAD 到
  `${XDG_DATA_HOME:-~/.local/share}/shoal/codex-marketplace` 並登記；偵測舊
  `<repo>/plugin` 登記後 remove 再 add；已安裝判斷比對 `marketplaceSource`
  與匯出目錄
- [ ] Git 來源只寫進 `docs/install/codex.md`（不自動選用）；
  `INSTALL_PROMPT.md` 不動
- [ ] 更新 `tests/test_install.py`、`tests/test_plugin.py`、
  `tests/test_jev_router.py`
- [ ] 驗收：暫存 `CODEX_HOME`、離線（`GIT_ALLOW_PROTOCOL=none`）從舊登記升
  級；`marketplace list --json` 的 root 是匯出目錄、無 checkout 路徑，兩個
  plugin 都列出，重跑全為 `up-to-date`；`validate_prompt_lock.py` 無旗標通
  過；`INSTALL_PROMPT.md` 無 diff

停止條件：live 驗證通過；不被接受時改採匯出目錄，並在 SPEC 記錄。

## P3 `--update`

- [ ] 先寫 failing tests（暫存 `HOME`，假的 `claude`、`codex` 可執行檔，全部
  在 `windows-latest` 跑）：模組停用、hash 不符、CLI 不存在、第二次全為
  `up-to-date`
- [ ] 交換案例 (a)：假的 `claude` 第 2 次呼叫 exit 1 → 輸出含 `failed`、
  marketplace sha256 不變、沒有殘留 `.old`
- [ ] 交換案例 (b)：預先放殘留 `.old` 與暫存目錄，可重跑且被清掉
- [ ] 匯出 committed HEAD（`git archive` 加 Python `tarfile`）到同一 data
  dir 的暫存目錄，逐檔 sha256 比對現有 marketplace，相同則 `up-to-date` 不交
  換
- [ ] 交換為兩次 rename（舊→`.old`、暫存→正式），不用 rmtree 加複製；後續
  `claude` 步驟失敗時還原並回報 `failed`，成功才刪 `.old`；啟動時清殘留
- [ ] `Explore.md` 安裝（依模組清單）
- [ ] `claude plugin marketplace add|update`、`plugin install|update`（guard
  依模組清單與 chain）
- [ ] Codex plugin 匯出登記
- [ ] 各 host 同步沿用 `sync_global.py` 邏輯
- [ ] hash 檢查：sha256 逐位元組比對，不符為 `failed`
- [ ] 逐步輸出 `<step>: up-to-date | updated | skipped | failed`；dry-run 只
  回報
- [ ] `python-tests.yml`：加 `--update` dry-run（含 Windows）
- [ ] 驗收：與今天 `update_shoal` 加 `sync_global.py --apply` 的結果一致

停止條件：上述一致性驗收通過。

### P3b dotfile（Miyago）

- [ ] `agent-stack-auto-update.sh` 的 `update_shoal` 改為呼叫
  `python3 tools/shoal_install.py --update --apply`
- [ ] 同步 dotfile repo 內 `config/ai/claude/hooks/` 的版本
- [ ] 驗收：`update.log` 一天的記錄無 `failed`

停止條件：Miyago 合併並驗證。

## P4 文件拆分

- [ ] 依 SPEC 對照表建立
  `docs/install/{codex,grok,claude,agy,opencode}.md`、`docs/guard.md`、
  `docs/modules.md`、`docs/reference.md`（搬移，描述合併當下的佈局）
- [ ] `INSTALL.md` 改成 100 行以內的索引，保留「Codex 完整讀
  `docs/install/codex.md`」
- [ ] 更新錨點引用：`README.md`、`install/AGENT-INSTALL.md:209`、
  `hosts/codex/README*.md`、`hosts/opencode/plugin/src/guard/opencode.ts:23`
  註解
- [ ] 更新讀 INSTALL.md 的 tests：`test_render_claude.py:82`、
  `test_render_grok.py:164`、`test_astra_routing.py:120`
- [ ] 驗收：`wc -l` 與 diff 確認沒有內容遺失；markdownlint；
  `check_links.py`；`INSTALL_PROMPT.md` 無 diff；`docs/reference.md` 目錄樹
  每個路徑 `test -e`

停止條件：上述驗收通過，且 `rg "INSTALL.md#" -g '!docs/specs'` 的每個錨點都
指到存在的標題。

## P5 install/ 瘦身

- [ ] `git mv` 26 支到 `bench/`（清單見 SPEC P5）；保留 13 個檔，
  `probe_hybrid_runtime.py` 不動
- [ ] tests 的 `sys.path` 加 `bench/`
- [ ] `install/previous/` 移到 `tests/fixtures/install-history/previous/`，
  改 `tests/test_install.py`
- [ ] 刪除 `install/retired/`；`AGENT-INSTALL.md:251` 改為列出兩個 SHA-256
- [ ] `python-tests.yml`：path filter 加 `bench/**`；第 75 行 `py_compile`
  的 `install/evaluate_dispatch.py` 改 `bench/evaluate_dispatch.py`
- [ ] `tools/scan_legacy_names.py:52` `EXEMPT_FILES` 與第 13 行註解改路徑
- [ ] `tests/test_scan_legacy_names.py:108`、
  `tests/test_check_rename.py:101,103` 改路徑
- [ ] 更新 `docs/reference.md` 目錄樹與 `docs/install/*.md` 內的 install 腳
  本路徑
- [ ] 驗收：unittest 全綠；`python -m unittest` 單獨跑
  `tests.test_scan_legacy_names`、`tests.test_check_rename`、
  `tests.test_hybrid_probe`；`python3 tools/scan_legacy_names.py`；SPEC P5
  的 `rg` 以實際 stems 無殘留
- [ ] 驗收：`install/AGENT-INSTALL.md` 內每個 `python3 install/...` 路徑
  `test -e`；`docs/reference.md` 目錄樹每個路徑 `test -e`
- [ ] 驗收：`--help` 檢查（`install.sh`、`install.ps1`、
  `verify_dispatch.py`）；`git log --follow` 確認歷史

停止條件：`install/` 只含保留清單的 13 個檔。

## P6 Claude plugin 搬到 plugins/

- [ ] 先更新 tests 與 golden 期望（failing），再改 `tools/render.py` 常數與
  輸出路徑
- [ ] `.claude-plugin/marketplace.json` 的 `source` 改 `./plugins/claude`、
  `./plugins/claude-guard`
- [ ] `install/modules.json`、`package.json` lint ignore、CI path filter（加
  `plugins/**`）
- [ ] `shoal_guard_compat.py` 候選路徑新增 `claude-guard/`，保留舊名一個
  release
- [ ] `tools/refresh_golden.py --host claude-plugin --from-dist` 重產 golden
- [ ] 更新 `docs/reference.md`、`docs/install/claude.md` 與其他 docs 的路徑
- [ ] live 驗證（暫時 `CLAUDE_CONFIG_DIR`）：舊 tag 加入，更新到新 commit，
  兩個 plugin 都在，hook 可執行
- [ ] 驗收：unittest；`render.py --check`；`validate_prompt_lock.py` 無旗標
  通過；P3b 的 `--update --apply` 在新佈局成功
- [ ] 驗收：docs 的 `claude-plugin/|claude-guard-plugin/` 命中（排除 specs
  歷史與 `.claude-plugin/`）P6 前非空、P6 後為空；`docs/reference.md` 目錄樹
  每個路徑 `test -e`

停止條件：舊目錄 `claude-plugin/`、`claude-guard-plugin/` 不存在，live 驗證
通過。

## P7 v3.11.0 發佈

- [ ] `VERSION`、marketplace 兩個 `version`、render 產出的 plugin.json 版本
- [ ] `CHANGELOG.md`：新路徑與升級說明
- [ ] README 佈局表（含 `templates/`、`upstream.lock`、`plugin/` 與
  `plugins/` 並存的說明）
- [ ] 驗收：`render.py --check` 全 host；
  `python3 install/validate_prompt_lock.py --base-ref origin/main` 無旗標通
  過；三個 OS 的 CI 綠

停止條件：Miyago 決定 tag 與 push（本 spec 不做）。

## P8 Codex plugin 實體搬移（延後）

- [ ] 另開 spec：LOCK 5 個 surface 與 `REQUIRED_SURFACE_PATHS`、Miyago 套用
  lock renewal、live 驗證
