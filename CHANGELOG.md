# Changelog

shoal 的產品版本紀錄，從 v1.0.0 開始。Codex host 在 v1.8.1 之前的完整歷史
在 [hosts/codex/CHANGELOG.md](./hosts/codex/CHANGELOG.md)。

## v1.0.0

shoal 首次發布：把 pilotfish-codex 擴成 host 中立的 role catalog。

- 新增 `core/roles.toml` 與 `hosts/<host>/binding.toml`，由
  `tools/render.py` 產生 Claude Code、Codex CLI、Gemini/agy、Grok Build、
  OpenCode 共 5 個 host 的輸出，並提供 `--check` / `--write`。
- 5 個 host 的首次 render 與原本的安裝來源逐位元組相同（golden 測試）。
- 產品版本與 host 版本分開：根目錄 `VERSION` 為 1.0.0，codex host 版本改記在
  `hosts/codex/VERSION`（1.8.1），其他 host 版本見 README。
- Codex 的 `README.md`、`CHANGELOG.md` 搬到 `hosts/codex/`，相對連結已改寫；
  新增繁體中文的根目錄 `README.md` 與本檔。
- 新增 `tools/check_links.py` 與 `tests/test_links.py`，檢查文件的相對連結。
- 安裝來源改為 `miyago9267/shoal`（`install/install.sh`、`install/install.ps1`、
  `INSTALL.md`、`install/AGENT-INSTALL.md`）。v1.0.0 之前的 pinned ref 仍需使用
  `miyago9267/pilotfish-codex`。
- `upstream.lock` 記錄各 host 的上游與版本。

已知限制：policy 尚未合併成一份；grok 仍由外部安裝。
