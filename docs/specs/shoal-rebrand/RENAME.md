# 改名對照表

shoal-rebrand 的唯一對照來源（SPEC N1）。同時作為 lock migration 的
`equivalence`（SPEC N7）：受保護 surface 的變動只能是本表列出的替換、
版本號改為 2.0.0，或 lock 本身的路徑與 id 更新。

## 規則

| 舊 | 新 | 說明 |
|---|---|---|
| `Pilotfish`（文字中的產品名） | `shoal`（句首寫 `Shoal`） | policy、role、SKILL、README、INSTALL、訊息 |
| `pilotfish-orchestration` | `shoal-orchestration` | skill 名稱與目錄 |
| `pilotfish-claude`、`<!-- pilotfish v… -->` | `shoal-claude`、`<!-- shoal-claude v… -->` | Claude marker |
| `<!-- pilotfish:begin -->`／`end` | `<!-- shoal:begin -->`／`end` | dotfile skill 區塊 |
| `pilotfish-codex`、`Pilotfish-Codex`、`PILOTFISH-CODEX` | `shoal-codex`、`Shoal-Codex`、`SHOAL-CODEX` | Codex plugin、marketplace、marker（含 `:begin`、`:end`、`:spawn-transport:*`） |
| `pilotfish-jev-router`、`pilotfish-jev` | `shoal-jev-router`、`shoal-jev` | Codex Jev plugin 與 `<CODEX_HOME>/shoal-jev/` |
| `pilotfish_autoroute_gate`（`.py`）、`pilotfish-autoroute-gate` | `shoal_autoroute_gate`、`shoal-autoroute-gate` | Codex hook |
| projection `pilotfish-autoroute-v1`、`pilotfish-autoroute-v2` | 新的獨立 projection `shoal-autoroute-v1` | 兩個舊 id 與其 digest 保留為 `LEGACY_` 常數，只供遷移辨識 |
| `.pilotfish-v1.2-pristine`、`pilotfish-codex-v1.2-adapter-pristine` | `.shoal-v1.2-pristine`、`shoal-codex-v1.2-adapter-pristine` | install.py 的 pristine 備份名 |
| `pilotfish-codex-tooling` | `shoal-codex-tooling` | package.json／bun.lock 的 package 名 |
| `pilotfish_optional_jev_router`、`PILOTFISH_HYBRID_SESSION_PROBE_7F3C`、`pilotfish-work-status` | `shoal_optional_jev_router`、`SHOAL_HYBRID_SESSION_PROBE_7F3C`、`shoal-work-status` | 其他識別字 |
| 測試用字串（暫存目錄前綴 `pilotfish-…`、`chatcmpl-pilotfish-title`、`call_pilotfish_route` 等） | 同形狀換成 `shoal` | 只在 tests/ |
| `tools/guard_parity.py` | 刪除 | 對照的 dotfile 舊 guard 已移除，工具已無作用 |
| `pilotfish-decision-checkpoint-v1` | `shoal-decision-checkpoint-v1` | decision checkpoint schema |
| `.pilotfish-install-state.json`（含 `.pending`）、state 欄位 `pilotfish_policy` | `.shoal-install-state.json`、`shoal_policy` | Codex 安裝紀錄；舊檔只用於遷移辨識 |
| `.pilotfish-codex-<ts>`、`.staged.pilotfish-stage-` | `.shoal-codex-<ts>`、`.staged.shoal-stage-` | 備份與暫存檔名 |
| `pilotfish_behavior` | `shoal_behavior` | runtime 驗證欄位 |
| `pilotfish-grok`（rules、hooks json、hooks 目錄、marker） | `shoal-grok` | Grok |
| `pilotfish-agy`（rules、marker） | `shoal-agy` | agy |
| `pilotfish-opencode`（plugin 檔、package 名）、`pilotfish-plugin.ts` | `shoal-opencode`、`shoal-plugin.ts` | OpenCode |
| `pilotfish_route`、`chatcmpl-pilotfish-route` | `shoal_route`、`chatcmpl-shoal-route` | OpenCode tool 與測試 id |
| `.opencode/pilotfish/`、`<config-dir>/pilotfish/` | `.opencode/shoal/`、`<config-dir>/shoal/` | OpenCode 設定目錄 |
| `PilotfishOpenCodePlugin`、`createPilotfishRouteTool`、`PilotfishPluginOptions`、`pilotfishHome`、`pilotfishDir` | `ShoalOpenCodePlugin`、`createShoalRouteTool`、`ShoalPluginOptions`、`shoalHome`、`shoalDir` | 程式識別字 |
| `PILOTFISH_REGISTRATION_KEY`、`Symbol.for("shoal.pilotfish-opencode.route-registered")` | `SHOAL_REGISTRATION_KEY`、`Symbol.for("shoal.opencode.route-registered")` | OpenCode 去重 key |
| `PILOTFISH_<NAME>` 環境變數 | `SHOAL_<NAME>` | 例：`PILOTFISH_GROK_HOME`→`SHOAL_GROK_HOME`、`PILOTFISH_REF`→`SHOAL_REF`、`PILOTFISH_TARGET_HOME`→`SHOAL_TARGET_HOME`、`PILOTFISH_CLAUDE_ROOT`→`SHOAL_ROOT`、`PILOTFISH_OPENCODE_SOURCE`→`SHOAL_ROOT`、`PILOTFISH_CLIPROXYAPI_KEY`→`SHOAL_CLIPROXYAPI_KEY`。`PILOTFISH_GUARD`、`PILOTFISH_GUARD_MAX_FILES` 直接刪除（`SHOAL_GUARD*` 已存在） |
| dotfile `install-pilotfish.sh`、`PILOTFISH_ROUTING.md` | `install-shoal.sh`、`SHOAL_ROUTING.md` | OpenCode harness |

## 例外（保留原文）

- 上游的真實名稱與網址：`Nanako0129/pilotfish`、`Nanako0129/pilotfish-grok`、
  `miyago9267/pilotfish-codex`（README 中 v1.0.0 之前 pinned ref 的說明）、
  `upstream.lock` 的 `upstream` 與 `source` 欄位。
- credit：README「來源與致謝」、`LICENSE`、`ATTRIBUTION.md`。
- 歷史紀錄：`docs/specs/`（本 spec 之外）、`docs/benchmarks/`、`docs/plans/`、
  CHANGELOG 過去版本段落、`hosts/codex/CHANGELOG.md` 歷史段落。
- 遷移用的舊名清單（installer 與 `sync_global.py` 中辨識舊安裝的常數）與其
  測試 fixture；這些地方以 `LEGACY_` 前綴的常數集中，測試排除這些常數。
- 歷史 benchmark 的工具與資料格式：`install/evaluate_pilotfish_value_matrix.py`
  與其 `pilotfish-value-matrix-v1` schema、`pilotfish_*` 欄位（讀取 N3 保留的
  `docs/benchmarks` JSON）。
- 上游原文 fixture：`tests/fixtures/grok/rules.pilotfish-grok.upstream-v1.0.6.txt`。

## 掃描範圍（N1 檢查）

`git grep -iE 'pilotfish'`，排除：`docs/specs/`（`shoal-rebrand/` 除外）、
`docs/benchmarks/`、`docs/plans/`、`tests/golden/`、`CHANGELOG.md` 與
`hosts/codex/CHANGELOG.md` 的 v2.0.0 以前段落、上列例外檔案、`LEGACY_` 常數所在
的行、README「來源與致謝」一節、`LICENSE`、`ATTRIBUTION.md`、`upstream.lock`。
結果必須為 0。

## 遷移辨識的舊名（N5）

| Host | 舊安裝物 |
|---|---|
| Claude | dotfile `config/ai/claude/skills/pilotfish-orchestration/`（`<!-- pilotfish:begin -->` 區塊）；plugin 內 skill `shoal:pilotfish-orchestration` |
| Codex | `<CODEX_HOME>/hooks/pilotfish_autoroute_gate.py`、`hooks.json` 中 `pilotfish-autoroute-v1`／`v2` projection 的群組（含 Windows command 與 pinned digest）、`AGENTS.md` 的 `<!-- pilotfish-codex:begin/end -->` 區塊、`.pilotfish-install-state.json` 與 `.pending`、`config.toml` 的 `[marketplaces.pilotfish-codex]`、`[plugins."pilotfish-codex@pilotfish-codex"]`、`[plugins."pilotfish-jev-router@pilotfish-codex"]`、`<CODEX_HOME>/plugins/cache/pilotfish-codex/`、`<CODEX_HOME>/pilotfish-jev/`。使用者自改的 `pilotfish_autoroute_gate.py` 依 N8 保留為備份 |
| Grok | `<GROK_HOME>/hooks/pilotfish-grok.json`、`hooks/pilotfish-grok/`、`rules/pilotfish-grok.md` |
| agy | `~/.gemini/config/skills/pilotfish-orchestration`（symlink）、rules `pilotfish-agy.md` 的安裝位置 |
| OpenCode | `<config-dir>/plugins/pilotfish-opencode.js`、`<config-dir>/pilotfish/`、專案 `.opencode/pilotfish/`、全域 manifest `~/.local/state/shoal/opencode-global/install.manifest` 中的舊相對路徑（遷移以舊 manifest `--disable` 後再以新名 `--enable`） |
| dotfile | `config/opencode/plugins/pilotfish-opencode.js`、`opencode-harness/plugins/pilotfish-opencode.js`、`opencode-harness/opencode.json` 的 plugin file URL、`opencode-harness/install-pilotfish.sh`、auto-update 的 `PILOTFISH_CLAUDE_ROOT`、`PILOTFISH_OPENCODE_SOURCE`（只在 dotfile） |
