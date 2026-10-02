# Changelog

shoal 的產品版本紀錄，從 v1.0.0 開始。Codex host 在 v1.8.1 之前的完整歷史
在 [hosts/codex/CHANGELOG.md](./hosts/codex/CHANGELOG.md)。

## Unreleased

模型目錄與自動選模（`docs/specs/model-catalog/`，M1-M3）。

- 新增 `core/models.toml`（模型目錄）、`core/tiers.toml`（tier 選模規則）與
  `tools/resolve.py`；各 host 的 `binding.toml` 改以 `[models]` 宣告可用模型，
  手寫的 `[tiers]` 移除（現在只在要手動覆寫時才寫）。grok 改用
  `selection = "inherit"`。
- 新增 `render --host <h> --explain`，印出每個 role 的 tier、候選模型、
  被排除的原因與結果。沒有模型滿足規則時 exit 2，並指出 host 與 role。
- 移除 `security_avoid_frontier`：security role 改為排除帶
  `refuses_defensive_security` 旗標的模型（Claude 的 fable）。
- security role 被手動指定到帶 `refuses_defensive_security` 旗標的模型時，
  render 失敗。
- 五個 host 的 dist、`templates/` 與 golden 與之前逐位元組相同。
- 新增 [docs/model-catalog.md](./docs/model-catalog.md)：登記新模型與換模型的步驟。

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
