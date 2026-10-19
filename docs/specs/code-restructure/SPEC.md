# code-restructure：把最肥的程式拆成讀得懂的單元，行為不變

狀態：草案（待 Miyago 核准；guard 變更觸發 plan-critic，見 Risk）。

## Background

2026-10-19 量測（main `1ac98ce`）：

| 檔案 | 行數 | 問題 |
| --- | --- | --- |
| `hooks/shoal_guard.py` | 3181 | 一個檔 13 段；`_Guard` 一個 class 980 行；三個 host adapter 各自手寫；9 個 key 的 state literal 在 `_locked` 內出現 3 次；docstring 78 行重複 spec |
| `install/install.py` | 2864 | `install()` 約 700 行、`_validate_committed_state` 約 460 行，各是單一函式 |
| `tools/render.py` | 1573 | claude / codex / agy / grok / opencode 的 `validate_*` / `render_*`（525-1113，約 590 行）形狀相同卻各寫一份 |
| `tools/install_hooks.py` + `install/hook_registration.py` + `install/install.py` + `tools/sync_global.py` | 651 + 696 + 2864 + 680 | hook 登記散在多處；Codex `hooks.json` 有兩條寫入路徑 |

痛點是「找不到東西、改一處要讀全檔」，不是功能不足。guard 在每個 tool call 都跑，
所以任何結構變動都要證明行為與延遲不變。

## Goal

1. 每個檔案有一個主題；最長函式降到約 120 行以下；重複的 table / literal 收斂成一份。
2. 行為不變：guard vectors、unittest、render `--check`、各 host 輸出逐位元組不變
   （guard 的 dist 副本除外，見 D1.4）。
3. hook 啟動延遲不增加（目標：p50 不高於重構前 +1ms）。
4. 淨行數下降，但這不是主要目標：預估 guard -10% 到 -15%，render -150 到 -250，
   install 約持平（拆函式要加簽名）。可讀性是主要驗收，行數只作回報。

## Non-goals

- 不改任何 policy 條款、role、lane、MESSAGES 文字、state 的內容與 key。
- 不改 `core/`、`hosts/*/binding.toml` 既有欄位的語意（D4 只在證明無副作用時新增）。
- 不動 `hooks/shoal_autoroute_gate.py`（1676 行，另案）、OpenCode 的 TS guard。
- 不新增功能、不新增 guard 規則、不改 CLI 參數。
- 不拆 `tests/` 的大檔（只改被結構綁住的部分，見「會被牽動的測試」）。

## Decisions

### D1 guard 拆成 package

D1.1 **目錄與模組**。`hooks/shoal_guard/` 為 package，`hooks/shoal_guard.py` 縮成薄入口：

| 模組 | 內容（原行號） | 預估行數 |
| --- | --- | --- |
| `hosts.py` | 常數與 host 表（100-233）；見 D1.2 | ~110 |
| `messages.py` | roles / lanes / `MESSAGES`（233-438） | ~205 |
| `state.py` | fs / state I/O（439-605）加 `_open_readable`（3087）；見 D1.3 | ~150 |
| `policy.py` | policy / declarations / paths（606-905） | ~300 |
| `shell.py` | shell 寫入目標解析（905-1233） | ~330 |
| `guard.py` | `_Guard` 核心：`__init__`、`log`、`result`、`main`、`_locked`、`edit`、`shell`（約 600 行） | ~600 |
| `subagents.py` | `_Guard` 的 subagent 登記與 lane 規則（1305-1450、1916-2010）以 mixin 形式 | ~230 |
| `agy.py` | `_Guard` 的 agy conversation 方法（1453-1565）加 `adapt_agy` 與其 helper（2827-2906） | ~200 |
| `completion.py` | `note_*`、`stop`、`post_shell`（1565-1750）以 mixin 形式 | ~190 |
| `decide.py` | `_decide`、`evaluate`（2215-2306） | ~95 |
| `chain.py` | guard chain（2307-2557） | ~250 |
| `adapters.py` | claude / codex / grok 三個 adapter 與輸出（2558-2983，不含 agy）；見 D1.2 | ~330 |
| `globalguard.py` | global-guard 偵測、`defer_to_global`（2984-3110） | ~125 |
| `cli.py` | `run`、`main`（3114-3181） | ~70 |
| `__init__.py` | 重新匯出現有公開名稱（tests 與外部用的 `adapt_*`、`evaluate`、`run`、`main`、`MESSAGES`…）；不放邏輯 | ~30 |

`_Guard` 用 mixin 切（`class _Guard(SubagentMixin, AgyMixin, CompletionMixin)`），原因：
方法互相讀 `self` 的欄位，改成函式要傳大量參數，會動到邏輯；mixin 只搬位置、不改簽名。
所有模組都要 `from __future__ import annotations`、只用 relative import、不用 3.10 以上語法。

D1.2 **table 化（行為不變）**。

- host 集合（109-195，約 20 個 `frozenset`）改成一張表：
  `HOSTS = {"claude": HostInfo(default_mode="enforce", role_aware=True, stop=True, ...), ...}`，
  原本的 `ROLE_AWARE_HOSTS`、`STOP_HOSTS` 等名稱由表衍生並保留為模組屬性，
  讓 `guard.STOP_HOSTS` 這類測試引用不必改（改名要另開一次）。
- `_adapt_claude` / `_adapt_codex` / `adapt_grok`（2626-2690、2713-2771、2772-2826）
  共同形狀：取 event 名稱 → 對應 tool kind → 抽 path / command / role / lane 描述。
  差異（tool 名稱表、payload key 路徑、Codex 的 `apply_patch` 與 lane 文字）放進每 host
  一張 `AdapterSpec`，共用一個 `adapt(spec, payload)`。`adapt_agy` 因為 payload 沒有事件名、
  多 conversation，維持獨立函式（在 `agy.py`），不硬塞進表。
  已有 test 釘住 adapter 輸出（`tests/fixtures/*_shapes.json` 與 vectors），
  所以先補齊每個 host 的 shape fixture 再重寫（Red 在前，見 TESTS.md T1.2）。
- `_Guard._locked`（1817-1915）中 3 份 9-key state literal 收成 `_new_state(**overrides)`；
  key 順序必須與現在寫出的 JSON 相同（`test_state_file_*` 與 vectors 驗證）。
- `_open_private`（457）與 `_open_readable`（3087）共用一個 `_open_nofollow(path, flags, mode)`。
- 檔頭 78 行 docstring 改成約 10 行：用途、入口、指向 `docs/specs/dispatch-enforcement`、
  `guard-declared-direct`、`guard-every-gate`。

D1.3 **入口與 import 解析**。同一個 `hooks/` 下同時有 `shoal_guard.py` 與 `shoal_guard/`：
`import shoal_guard` 會解析到 package（package 優先於同名 module），
但 `python3 hooks/shoal_guard.py` 直接執行時它是 `__main__`，不衝突。入口檔：

```python
#!/usr/bin/env python3
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 相容 python -I 與 run.sh
from shoal_guard.cli import main
if __name__ == "__main__":
    sys.exit(main())
```

`plugins/claude-guard/hooks/run.sh` 用 `__import__("shoal_guard").main` 進入，
所以 `shoal_guard/__init__.py` 必須匯出 `main`。同名的陷阱靠 TESTS.md T1.6
（解析結果檢查）固定下來；若 Miyago 偏好避免同名，改 package 名稱為 `shoal_guard_core`
是 O1 的選項，成本是 `__init__` 重新匯出的名稱不變、其餘不動。

D1.4 **發佈單位：guard bundle**。今天所有消費者都假設 guard 是「一個檔」。定義
**guard bundle = `hooks/shoal_guard.py` 加 `hooks/shoal_guard/*.py`（遞迴，排除 `__pycache__`）**，
新增 stdlib-only 的 `install/guard_bundle.py`（py3.9 可用），提供：

- `bundle_files(root) -> dict[相對路徑, bytes]`：從工作樹或 `git show <commit>:<path>` 讀出 bundle。
- `bundle_digest(files) -> str`：把每個檔排序後輸出 `sha256sum` 格式的行
  （`<hex>  <相對路徑>\n`），再整份取 sha256。golden 存這份清單（見下），
  guard 改動時 diff 會指出是哪個模組變了，比單一 hash 好讀。

各消費者的改法：

| 消費者 | 今天 | 之後 |
| --- | --- | --- |
| `tools/render.py` `_guard_script`（787-795）、`render_claude_plugin`（1324）、`render_grok`（816） | 回傳一個檔的 bytes，放進 `{path: bytes}` | `_guard_files(root)` 回傳 bundle 的多個檔，鍵為 `<dist>/shoal_guard.py`、`<dist>/shoal_guard/<module>.py`；`write_dist` / `diff_dist` 本來就逐檔比，舊 dist 內多出的檔會被清掉或在 `--check` 失敗 |
| `tests/render_helpers.py` `GOLDEN_HASHED` | 兩個檔的 `.sha256` | 兩個 bundle 根（`plugins/claude-guard/hooks`、`hooks/shoal-grok`）各存一份 `shoal_guard.manifest`（`sha256sum` 格式）；`GUARD_SOURCE` 改成 bundle |
| `tools/install_grok.py:119` `check_guard_single_source` | 單一 `git show` 比 bytes | 對 bundle 每個檔比 bytes，並檢查 dist 內 bundle 的檔集合相同（不多不少） |
| `tools/shoal_update.py:46`、`verify guard`（569-577） | 比單檔 sha256 | 比 `bundle_digest`；已安裝路徑的整個 bundle 目錄都要比對 |
| `tools/install_hooks.py`（claude / agy）裝到 `~/.local/share/shoal/guard/` | 寫單檔，portable command `f=.../shoal_guard.py; exec python3 "$f"` | 先寫 staging 目錄再 rename 交換 `shoal_guard/`，最後原子替換 `shoal_guard.py`（入口最後換，hook 不會讀到半套）；command 字串不變 |
| `install/install.py` Codex（1477、2295-2320）：`<home>/hooks/shoal_guard.py`、state 的 guard script fingerprint | 單檔 payload、fingerprint 是檔案 sha256 | 同樣寫入 bundle；fingerprint 改為 `bundle_digest`。舊 state 的單檔 fingerprint 仍視為「proven」：現有單檔等於舊 fingerprint 時走既有的 upgrade 路徑覆蓋成 bundle（不報 `installed_hook_drift`），這條路徑要有測試 |
| `install/modules.json` `dispatch-guard.paths` | `hooks/shoal_guard.py` | 加 `hooks/shoal_guard/` |
| `tools/install_hooks.py` `OWNED` regex（以 `shoal_guard.py --host` 辨識 shoal 的 handler） | 比對入口檔名 | 不變（入口檔名與 command 形狀都不變）。這是保留薄入口的主因 |
| `plugins/claude/hooks/shoal_guard.py`（3.8.1 compat shim） | 自給自足 | 不動；它 glob 到 guard plugin 的 `shoal_guard.py` 再 subprocess 呼叫，入口不變即可 |

Uninstall 與 `--no-guard`：要移除整個 bundle（含目錄），且只在內容符合 proven fingerprint 時移除，
規則與今天單檔相同。

D1.5 **延遲**。目前 `python3 -X importtime` 的 `import shoal_guard` 約 10-30ms（本機有雜訊，
包含 `hashlib` / `pathlib` 等 stdlib），`run.sh` 已設 `pycache_prefix`，所以 `.pyc` 有快取。
package 會多約 14 個 module 的 stat 與 pyc 讀取。要求：

- P1 前先建立 baseline：`tests/bench_hook_latency.py`（新增，stdlib only）以 hyperfine 式迴圈對
  `run.sh` 與 `python3 shoal_guard.py` 兩種入口各跑 200 次 `SessionStart`、`PreToolUse(Bash)`、`PreToolUse(Edit)` 三種 payload，
  輸出 p50 / p95。before / after 各量一次存進 PROGRESS.md。
- 驗收：p50 差在 +1ms 內，p95 差在 +3ms 內。超過就啟用 lazy import：
  `chain.py`、`shell.py`、`globalguard.py`、`agy.py` 只在用到的事件才 import
  （非 Bash 事件不需要 `shell.py`；沒有 chain member 不需要 `chain.py`）。lazy 也是 package 的好處，
  可能比現在更快。

D1.6 **Python 3.9**。`tests/test_py39_compat.py` 的 `SCRIPTS` 改成遞迴涵蓋 `hooks/shoal_guard/*.py`；
每個模組都要有 `from __future__ import annotations`（現有測試的第二項檢查）。
不使用 `match`、括號式 context manager、`X | Y` 的 runtime 求值。

### D2 hook 登記收斂到 `install/hook_registration.py`

現況（已讀程式驗證，與原假設有一處差異）：

- `install/hook_registration.py`（696 行）已經是 Codex `hooks.json` 的 canonical projection
  （`TRUSTED_PROJECTIONS`、`merge_registration`、`strip_projection`、digest）。
- `install/install.py` `merge_config_text`（356-449）是 **Codex `config.toml`** 的 routing 設定，**不是** hook 登記，
  不屬於 D2；Codex hook 登記在 `install()` 內 2236-2262 呼叫 `merge_registration`。
- `tools/install_hooks.py`：`apply_claude`（213）寫 `settings.json` 六個事件；`apply_agy`（325）寫 agy `hooks.json`；
  `apply_codex`（255）又用 `TRUSTED_PROJECTIONS` 加 `set_groups` 自己寫一次 Codex `hooks.json`。
  所以 **Codex 有兩條寫入路徑**（`install.py` 與 `install_hooks.py`）。
- `tools/sync_global.py` 在 339-341、515 用 subprocess 呼叫 `install_hooks.py --host codex|agy`（`--json` 取 plan）；
  `tools/shoal_update.py` `run_update` → sync_global subprocess → `install_hooks` / `install.py`。
  `shoal_install.py` 的 `do_install` per-host 路徑較舊（直接呼叫 `install_hooks.py`，335 行）。

決定：

D2.1 **單一 owner：`install/hook_registration.py`**。它已有 strict ownership 與 projection ID，
把 Claude / agy 的 `apply_*`、`set_groups`、`strip_owned_groups`、`is_owned`、`OWNED` / `OWNED_GUARDED` regex、
`portable_command_for` 從 `install_hooks.py` 搬進來；檔案長大到約 900 行，所以內部分三節
（codex projection / claude settings / agy config），必要時之後再拆成 `hook_registration/` package（不在本案）。
`apply_codex` 改成呼叫 `merge_registration`（`with_autoroute=False`、`with_guard=...`），兩條 Codex 路徑產出同一份 `hooks.json`。
這是本案唯一可能改變輸出的地方：先用 characterization test 固定兩條路徑今天的輸出，
若有差異，列為 O3 交 Miyago 決定以哪條為準，不默默選一邊。

D2.2 **之後的 call graph**。

```
shoal_install.py (do_install)  ─┐
shoal_update.py (run_update)   ─┼→ sync_global.py ─→ install_hooks.py (CLI + I/O：backup、symlink、原子寫入)
install.py install()           ─┘                         │
                                                          └→ hook_registration.py  ← install.py 也直接用
                                                              ├ codex：merge_registration / TRUSTED_PROJECTIONS
                                                              ├ claude：apply_claude
                                                              └ agy：apply_agy
```

`install_hooks.py` 只剩 CLI、設定檔路徑、備份、symlink 跟隨與寫入（約 350 行），不再含登記邏輯。
`sync_global` 維持 subprocess 呼叫（保留 `--json` plan 介面與 env 隔離；改成 in-process 要另案）。
`shoal_install.do_install` 的 per-host 路徑不改呼叫對象，只確認它走同一個 `install_hooks.py`。
`install_grok.py` 的 hooks json 由 render 產生，不在 D2 範圍。

### D3 `install/install.py`：拆函式，不拆檔

為什麼不拆檔：`tests/test_install.py` 大量 patch `installer.subprocess`、`installer.shutil` 等 module 屬性，
並以 `installer.install(...)` 驅動；拆檔會讓這些 patch 全部失效，重寫成本高於收益。拆成同檔內的具名函式即可達成可讀性。

- `install()`（2073-2773）拆成依序執行的步驟，共用一個 `@dataclass _Plan`（writes、removals、notes、state 欄位）取代現在的區域變數：
  `_resolve_context` → `_plan_config` → `_plan_roles` → `_plan_policy` → `_plan_hooks`（含 guard bundle，見 D1.4）
  → `_plan_plugin` → `_commit_plan`（呼叫既有 `_commit`）→ `_record_state` → `_post_commit_removals`。
  每步不超過約 120 行；`install()` 本體只剩串接與 dry-run 判斷（約 60 行）。
  順序、交易邊界（先備份、全部成功才提交、post-commit 才刪舊 role）、錯誤訊息一字不改。
- `_validate_committed_state`（897-1359）依 state 區塊拆：
  `_check_state_keys`、`_check_policy_ownership`、`_check_hook_projection`、`_check_guard_script`、
  `_check_role_inventory`、`_check_plugin_record`…，每個回傳錯誤或丟 `InstallAbort`，原有的檢查順序保留。
- 先寫 characterization：對每個 `InstallAbort` 訊息（grep 出的字串）確認至少有一個 test 觸發，缺的先補（Red 在前）。

### D4 `tools/render.py`：host 差異資料化

- 抽出 `HostSpec`（dataclass）：`validate`（共同 `validate_catalog` + `derive_permissions` + read-only tool 檢查）、
  `frontmatter(name, spec, perm, model)`、`forbidden_tools`、`models` 白名單、`extra_files(core, binding, src)`、`rules_path`。
  共同流程 `render_roles(spec, core, binding, src)` 取代五份「迴圈 role → role_body → 組 frontmatter → passthrough → merge_core_policy」。
- 完全適用：claude、agy。部分適用：grok（多 `roles/*.toml`）、codex（root 與 `[agents]` toml）；
  opencode 的 plugin 輸出維持自己的函式，只共用 validate。誠實預期：不是五個都能變 table，約 -150 到 -250 行。
- 常數（`AGY_MODELS`、`READ_ONLY_FORBIDDEN_TOOLS` 等）先放 `HostSpec`，**不**搬進 `binding.toml`：
  搬進去會改 binding 格式，而 `render_generic`（已是 binding 驅動）與 TS plugin 是否讀這些欄位需另行確認。
  搬 binding 列為 O4，不在本案階段內。
- 驗收是 `render --check` 五個 host 輸出逐位元組不變（golden 全綠，不更新任何 golden，D1.4 的 guard manifest 除外）。

## Phases（每階段可單獨出貨）

| 階段 | 內容 | 預估行數變化 | 驗收（每階段都要） |
| --- | --- | --- | --- |
| P0 | 量測基準：`tests/bench_hook_latency.py`；補 characterization tests（adapter shapes、`InstallAbort` 訊息、兩條 Codex hooks.json 路徑） | +250（測試） | 在現有 code 上全綠，baseline 數字存 PROGRESS.md |
| P1 | D1.2 的 in-file 整理：host 表、adapter 表、`_new_state`、`_open_nofollow`、docstring。**仍是單一檔** | guard -250 | 見下方共同驗收；沒有發佈單位變動，風險最低 |
| P2 | D1.1 / D1.3 / D1.4 / D1.6：搬成 package、`guard_bundle.py`、render / install_grok / shoal_update / install_hooks / install.py 的 bundle 處理、golden manifest | guard 再 -50；消費者 +150 | 共同驗收加：五個 host 的 render `--check`、`shoal_update verify guard`、在暫存 HOME 跑 `install_hooks.py` claude / agy / codex 與 `install.py` 實際安裝 → 執行 hook → uninstall，舊 state 升級路徑 |
| P3 | D2：登記收斂 | -150 到 -200 | 共同驗收；`test_hook_registration`、`test_install_hooks`、`test_sync_global`、`test_shoal_update` |
| P4 | D3：`install.py` 拆函式 | 約 0 到 -100，最長函式 ≤ 120 行 | 共同驗收；`test_install` 全綠且不改斷言 |
| P5 | D4：`render.py` table 化 | -150 到 -250 | 共同驗收；golden 全部不變 |

順序理由：P1 先在單檔內降低 guard 的複雜度，且不動任何消費者；P2 只處理發佈單位，邏輯已穩定；
P3、P4、P5 彼此獨立，可以平行或依序，建議 P3 先於 P4（P4 的 `_plan_hooks` 依賴 P3 的 owner）。
P2 與 P3 都碰到 Codex 的 hook / guard 安裝，不要並行。

**共同驗收**：

1. `python3 -m unittest discover -s tests` 全綠（Windows-only 的 skip 照舊）。
2. `python3 tools/render.py --check --host <claude|codex|agy|grok|opencode>` 五個全綠；claude-plugin 同。
3. `tests/fixtures/guard_vectors.json` 全部 vectors 通過（`tests/test_shoal_guard.py::VectorTests`）。
4. hook 延遲：`tests/bench_hook_latency.py` 重構後的 p50 / p95 與 P0 baseline 比較，在 D1.5 容許範圍內。
5. `tests/test_py39_compat.py` 綠。
6. 沒有 golden 內容變動（P2 的 guard manifest 除外）。

## Risk

| 風險 | 緩解 |
| --- | --- |
| guard 變更是 security / trust 邊界（dispatch enforcement） | 依 Risk trigger：P1、P2 實作前以 `plan-critic` 審 plan 並取得 Miyago 核准，完成後以 fresh `verifier` 驗一次；改動走 `security-reviewer` → 核准 → `security-executor`，不用一般 executor |
| package 啟動變慢 | D1.5 量測加 lazy import；超標就不出貨 P2 |
| 已安裝的舊單檔 guard 與新 bundle 的升級 / 降級 | 走既有 proven-fingerprint upgrade；降級（新 bundle 被舊版 install 看到）會被舊版視為 drift，列入 release note；P2 測試包含「舊 state → 新安裝」 |
| 安裝 bundle 時被 hook 讀到半套 | staging 加目錄 rename，入口檔最後換；入口只 import 已存在的 package |
| 同名 `shoal_guard.py` 與 `shoal_guard/` 的 import 解析 | D1.3，T1.6 |
| `-I` / `pycache_prefix` / 沒有可寫的 cache 目錄 | T1.5：以 `python3 -I`、唯讀 cache 啟動仍可運作 |
| Windows 上 guard 是 no-op | 保留 `os.name == "nt"` 早退，且早退發生在 import 重模組之前（lazy） |
| 第三方 chain member 依賴 `shoal_guard.py` 路徑或內部名稱 | 外部介面是 manifest 與 stdin / stdout JSON，不是 import；入口路徑不變；在 CHANGELOG 註明 |
| P3 發現兩條 Codex 路徑今天輸出不同 | 不默默選邊：停下回報（O3） |

## Rollout

- 每個 phase 一個 PR，各自過共同驗收；不排在同一次 release。P1、P3、P4、P5 純內部，可併入 patch；
  P2 改變已安裝檔案配置，建議放進下一個 minor 並寫 release note（依 shoal 發版節奏，累積成批再發）。
- 只修改 `hooks/`、`install/`、`tools/`、`tests/` 與 render 產物；`docs/specs/code-restructure/` 的 TASKS.md 每步更新，
  PROGRESS.md 每 phase 記延遲數字。
- Plugin 版本號：P2 之後 `plugins/claude-guard` 的內容改變，`shoal_update` 需要重新 export marketplace；
  版本升級由發版流程處理，不在本 spec。

## 會被牽動的測試（重寫，不是刪除）

| 測試 | 為什麼綁結構 | 處理 |
| --- | --- | --- |
| `tests/test_shoal_guard.py`（1860 行） | `import shoal_guard as guard`，約 150 處使用 `guard.adapt_*`、`MESSAGES`、`resolve_mode` 等；`guard._chain_call`；`ast.parse` 單檔（166 行）；掃描 guard 原始碼文字（462、643 行附近） | `__init__` 重新匯出，大部分不用改；`_chain_call` 改指向 `chain`；掃原始碼與 ast 的測試改成走 bundle 全部檔案 |
| `tests/test_py39_compat.py` | `hooks/*.py` glob | 遞迴涵蓋 `hooks/shoal_guard/` |
| `tests/render_helpers.py`（`GOLDEN_HASHED`、`GUARD_SOURCE`、`setUp` 只複製單檔） | golden 以單檔 `.sha256` 表示 guard 副本 | 改為 bundle manifest；`setUp` 複製 package；舊 `.sha256` golden 檔刪除、換成 manifest |
| `tests/test_render_grok.py`、`test_claude_plugin.py`、`test_install_grok.py` | 驗 dist 內單檔副本 | 改驗 bundle |
| `tests/test_shoal_update.py`、`test_install_hooks.py`、`test_install.py`、`test_shoal_install.py`、`test_sync_global.py` | 安裝後只檢查單一 `shoal_guard.py` 的存在、內容、權限、fingerprint | 檢查 bundle；fingerprint 改為 `bundle_digest` |
| `tests/test_hook_registration.py`、`test_install_hooks.py` | `apply_*` 位置 | P3 後 import 路徑改為 `hook_registration`；斷言不變 |
| `tests/test_access_derivation.py`、`test_core_policy*.py`、`test_claude_plugin.py` 等 | 直接呼叫 `render.validate_*` / `render_*` | P5 保留這些名稱為薄包裝，直到下一次整理再移除，所以不需要改 |
| `install/stage_smoke_home.py`、`bench/claude_live_probe.py` | 引用 `hooks/shoal_guard.py` 路徑 | 入口路徑不變，P2 只確認 smoke 走通 |

## Open questions

- O1 package 名稱：沿用 `shoal_guard/`（與入口同名，靠 T1.6 固定解析結果）還是改 `shoal_guard_core/`（無歧義，成本只是一個名稱）。建議改名；若沿用，需接受 `import shoal_guard` 永遠是 package。
- O2 發佈單位：本 spec 依指示採「目錄 bundle」。替代案是「由 package 產生單一檔 `hooks/shoal_guard.py` 並提交，`render --check` 擋手改」：render、install_grok、shoal_update、install_hooks、install.py 的 fingerprint 與 golden 全部不用動（D1.4 整張表消失），代價是 repo 內仍有 3000 行產物、review 要看 diff 的來源檔，且單檔 import 的啟動成本與現在相同（不能 lazy）。若 P2 的消費者改動估計超過 +150 行或 state 升級測試太脆，建議退回這個替代案；請 Miyago 在 P2 開工前選一個。
- O3 Codex `hooks.json` 兩條寫入路徑（`install.py` 與 `install_hooks.apply_codex`）今天輸出是否位元組相同，尚未驗證；不同時以哪條為準。
- O4 `AGY_MODELS`、forbidden tools 等常數是否搬進 `binding.toml`（需確認 `render_generic` 與 OpenCode TS plugin 是否讀取）。本案預設不搬。
- O5 與 main 的假設有一處差異：`merge_config_text` 是 Codex `config.toml` routing，不是 hook 登記，D2 因此不含它；若 main 要連同整理，另列 D5。
- O6 `_Guard` 用 mixin 切是為了不改簽名；若 plan-critic 認為 mixin 讓讀者更難追 `self` 欄位來源，替代案是保留一個 `guard.py` 約 1300 行。
- O7 hook 延遲容許值（p50 +1ms、p95 +3ms）是我的估計，沒有歷史資料；P0 量完後可能要調整。
- O8 `guard.STOP_HOSTS` 等舊名稱由表衍生並保留，是否值得（保留省測試改動，但留下兩種寫法）；建議保留一個 release 後再清。
