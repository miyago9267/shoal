---
title: repo 佈局與安裝入口整理（v3.11.0）
status: draft
approved_by:
created: 2026-10-15
updated: 2026-10-15
---

<!-- markdownlint-disable MD025 -->

# repo 佈局與安裝入口整理（v3.11.0）

## Background

Miyago 2026-10-15：「專案目錄和安裝方式有點醜」。他選了兩件事一起做：(1) 安
裝與文件，(2) 目錄重整，以 v3.11.0 出貨。本檔只是規格草稿，不改任何程式或檔
案。

現況（main `7b572a4`，v3.10.0，已查證）：

- README 快速開始有四種寫法：Codex 用 `bash install/install.sh`，Claude 用兩
  行 `claude plugin`，Grok 用 `python3 tools/install_grok.py`，OpenCode 用
  `sh hosts/opencode/plugin/install/install.sh`，agy 只寫「見 INSTALL.md」。
  統一入口 `tools/shoal_install.py`（540 行薄前端）已存在，但只在「模組」一
  節提到。
- `INSTALL.md` 1425 行，中英混寫，實際是 Codex 安裝手冊（1-513）加上 Grok、
  guard、Claude plugin、OpenCode、模組、每日同步，最後 1243-1425 是「從
  README 移入的參考資料」。
- `install/` 有 48 個追蹤檔：26 支 benchmark、eval、role_fitness、matrix 腳
  本跟安裝無關；另有 `previous/`（4 個版本、7 檔）與 `retired/`（2 檔）。
- 三個 plugin 散在根目錄：`claude-plugin/`、`claude-guard-plugin/`（render
  產出）與 `plugin/plugins/shoal-codex`（手寫，且和 `shoal-jev-router` 共用
  `plugin/` 當 Codex marketplace 根）。
- `docs/specs/_templates/` 不存在；本檔格式沿用
  `docs/specs/modular-install/`（SPEC.md 加 TASKS.md）。

## Principles

1. **可移植性優先**（Miyago 2026-10-15，最高原則）。安裝與更新的核心路徑只靠
   stdlib-only Python（`tools/shoal_install.py`），在 macOS、Linux、Windows
   行為相同，不依賴 bash 或 zsh；不寫死絕對路徑；更新由 shoal 自己負責，
   dotfile 或其他外部腳本只是呼叫它。與這條衝突的方案，其他考量都讓步。
2. 搬移優先於改寫：文件與程式碼用 `git mv` 與路徑更新，不順手重寫內容。
3. 每個 phase 可獨立出貨與驗證，不留半套狀態。
4. 不動受保護 surface：能不動 `docs/specs/prompt-document-lock/LOCK.json` 就
   不動，要動就明講並交給 Miyago 套用 renewal。

## Findings

### F1. shoal_install.py 的覆蓋缺口

五個 host 都有對應，但下列缺口讓「一個指令裝完」目前不成立：

| # | host | 缺口 |
| --- | --- | --- |
| G1 | claude | `--apply` 不執行任何安裝，只印三行 `claude plugin ...` 要使用者手動跑；`claude-explore` 模組只有「移除」邏輯，沒有安裝 `Explore.md`（目前只有 dotfile updater 會裝） |
| G2 | agy | 只呼叫 `install_hooks.py`（guard hook）。agents、skills、rules 是指向 `hosts/agy/dist` 的 symlink，由 dotfile `setup_gemini.sh` 建；沒有 dotfile 的新使用者裝完只有 hook，沒有 role。修法：入口建 symlink；`os.symlink` 丟 `OSError`（Windows 無權限）時改為複製檔案，並在 `modules.json` 記 `agy_mode: copy`。`tools/sync_global.py:402-403`（`不是 symlink` 檢查）與 `--update` 在 copy 模式改比對內容 sha256 |
| G3 | 全部 | dry-run 只印「would run: ...」，沒有真的跑底層 installer 的預覽（`install.py --dry-run`；`install_hooks.py` 與 `install_grok.py` 預設就是 dry-run）。INSTALL.md 要求 codex 先 dry-run 再核准，入口卻看不到差異 |
| G4 | opencode | 快速開始假設 `hosts/opencode/plugin/dist` 已有 bundle；該目錄在 `.gitignore`，`sync_global.py` 是用 `bun` 現建。全新 clone 不帶 bun 能否 `--enable` 未驗證（P1 要先查證，不假設） |
| G5 | opencode、windows | 入口用 `sh hosts/opencode/plugin/install/install.sh` 裝 opencode，Windows 沒有 `sh` 就失敗；違反可移植性。codex 另有 `install.ps1`，但入口走的是 `install.py`，不受影響 |
| G6 | 全部 | 外部 CLI（`claude`、`codex`）以 `subprocess` 直接呼叫名稱；Windows 上是 `.cmd` shim，要用 `shutil.which` 解析。dry-run 在 CLI 不存在時不得失敗 |
| G7 | 更新 | 入口沒有更新功能。「匯出 committed HEAD、刷新 Claude 本機 marketplace、plugin update、同步各 host」目前寫在 dotfile 的 bash `update_shoal`（約 70 行）加 `sync_global.py`；沒有 dotfile 的使用者無法更新，Windows 完全沒有路徑 |

不處理：`--host all`、安裝後自動 `verify_dispatch`。需要時另開。

### F1b. 絕對路徑盤點與 Codex marketplace

- `install.py:661-679` 以 `codex plugin marketplace add <repo>/plugin` 登
  記，來源是使用者 checkout 的絕對路徑；checkout 一搬家、一刪除，Codex 的登
  記就壞。
- Claude 本機 marketplace 是 shoal 自己擁有的暫存位置
  （`${XDG_DATA_HOME:-~/.local/share}/shoal/claude-marketplace`），絕對路徑
  只寫進 Claude 的 `settings.json`，由 dotfile 的 `portable_paths.py` 還原成
  `~` 形式；這不是 shoal repo 的問題，也不放進 `--update`。
- Codex CLI 的 `marketplace add` 接受本機路徑、`owner/repo[@ref]` 與 Git URL
  （`codex plugin marketplace add --help`）。所以 Codex **不是**被迫用絕對路
  徑；本機路徑形式才會存成絕對路徑（推論：`install.py` 以
  `marketplaceSource` 與 `plugin_root` 的路徑比對）。
- 可移植方案：`install.py` 與 `--update` 一律把 committed HEAD 匯出到 shoal
  擁有的 `${XDG_DATA_HOME:-~/.local/share}/shoal/codex-marketplace`，登記該
  目錄（離線可用，內容與 checkout 一致）。Git 來源
  （`codex plugin marketplace add miyago9267/shoal@<ref>`）只寫進
  `docs/install/codex.md`，當作沒有 checkout 的替代方式，不會被自動選用。匯
  出什麼由 P2 的 live 驗證決定，結果要寫進本 spec：(甲) 若 Codex 接受根目錄
  manifest，repo 根新增 `.agents/plugins/marketplace.json`（plugin 的
  `source.path` 寫 `./plugin/plugins/shoal-codex`、
  `./plugin/plugins/shoal-jev-router`，檔案不搬，LOCK 的 5 個 surface 路徑不
  變），匯出該 manifest 加 `plugin/plugins/**`，舊的
  `plugin/.agents/plugins/marketplace.json` 留一個 release；(乙) 若不接受，
  匯出 `plugin/` 子樹當 marketplace 根，不新增根 manifest，也不設舊 manifest
  的下架期。已安裝判斷改為比對 `marketplaceSource` 與匯出目錄。
  `INSTALL_PROMPT.md` 是鎖定 surface，不更動。

### F2. 要不要根目錄 shim

建議不加。理由：入口仍要 `python3`，shim（`./shoal` 或 `install.sh`）只省下
`python3 tools/` 這幾個字；多一個檔就多一個要維護、要測的 surface，Windows
又要再一個 `.ps1`。`install/install.sh` 已是 Codex 遠端 bootstrap 的穩定 URL
（INSTALL.md 的 `raw.githubusercontent.com/.../install/install.sh`），根目錄
再放同名檔會混淆。唯一合理的替代是把 `tools/shoal_install.py` 移到更顯眼的位
置，但這會讓 CI 與 `sync_global` 的引用多一輪改動，收益不到成本。

### F3. 各搬移項目的實際耦合

下列是「搬動前不查就會壞」的事實，依風險排序：

1. **`docs/specs/prompt-document-lock/LOCK.json` 有 5 個 surface 路徑在
   `plugin/plugins/shoal-codex/`**（2 個 references、1 個 agents、1 個 skill
   目錄、1 個 `.codex-plugin`）。`validate_prompt_lock.py` 的
   `REQUIRED_SURFACE_PATHS` 也寫死其中的檔案。搬 Codex plugin 一定要
   `--allow-lock-update`，需 Miyago 核准（PR label `lock-renewal` 或 push 訊
   息 `Lock-Renewal: approved`）。`claude-plugin/`、`claude-guard-plugin/`、
   `templates/`、`hosts/claude/dist` 不受影響（LOCK 只列
   `hosts/claude/dist`，`templates/` 與 `INSTALL_PROMPT.md` 留在原處）。
2. **Codex marketplace 的根就是 `plugin/`**：`install.py:661-679` 以
   `codex plugin marketplace add <repo>/plugin` 登記（絕對路徑），
   `install.py:631-643` 用 `marketplaceSource` 路徑與 `plugin_root` 比對判斷
   是否已裝；`legacy_codex.detect`、`sync_global.py:285,297` 也用
   `repo/plugin`。已安裝者的 Codex config 與 plugin cache 都指著舊路徑；搬了
   之後比對失敗，會走重新登記，但「同名 marketplace 指向已不存在的路徑」
   Codex CLI 怎麼處理沒有證據，需要 live 驗證。`shoal-jev-router` 也在同一個
   marketplace，會一起被牽動。
3. **dotfile updater 會硬失敗（但 fail-safe）；這是 `--update` 要取代的對象
   **：`~/.claude/hooks/agent-stack-auto-update.sh:154`（dotfile 內為
   `config/ai/claude/hooks/agent-stack-auto-update.sh`）對 `HEAD` 執行
   `git archive`，pathspec 是 `.claude-plugin`、`claude-plugin`、
   `claude-guard-plugin` 與 `hosts/claude/dist/agents/Explore.md`。任一
   pathspec 不存在，`git archive` 就失敗，函式 `return 1`，輸出
   `shoal update failed`，暫存目錄被清掉、既有 marketplace 不動。也就是
   Miyago 自己的 shoal checkout 一旦進到新佈局，Claude 端每天都更新失敗，直
   到 updater 改好。
4. **`hosts/claude/plugin-src/shoal_guard_compat.py:45`** 以
   `<marketplace>/claude-guard-plugin/hooks/` 找 guard 腳本（3.8.1 相容
   檔）。搬動後第一個候選路徑要改成 `<marketplace>/claude-guard/`；後兩個候
   選（plugin cache glob）不受影響，所以失敗模式是退而求其次，不是中斷。
5. **`install/` 內部依賴與保留清單**：`verify_dispatch.py` import
   `stage_smoke_home`、`routing_contract`、`install`、`validate_agents`；
   `install.py` import `hook_registration`、`legacy_codex`、
   `validate_agents`；`probe_hybrid_runtime.py` import `install`；bench 腳本
   又 import 上述多個。所以保留清單（13 個檔）是 `AGENT-INSTALL.md`、
   `hook_registration.py`、`install.ps1`、`install.py`、`install.sh`、
   `legacy_codex.py`、`modules.json`、`probe_hybrid_runtime.py`、
   `routing_contract.py`、`stage_smoke_home.py`、`validate_agents.py`、
   `validate_prompt_lock.py`、`verify_dispatch.py`。其餘 26 支搬到 `bench/`
   （清單見 P5）。tests 用 `sys.path.insert(0, ROOT / "install")` 載入，搬動
   後要多加 `bench/`。`probe_hybrid_runtime.py` 留在 `install/`（它是 Codex
   安裝後的啟動檢查，`AGENT-INSTALL.md:184` 與 CI `py_compile` 清單都用
   `install/` 路徑，不用改）。
6. **`install/previous/` 與 `install/retired/` 不能直接刪**：
   - `previous/`：`install.py` 執行期不讀（已知 digest 寫在
     `install.py:1332` 附近），但 `tests/test_install.py` 有 6 個 test 定義
     路徑、約 30 行讀 `install/previous/v1.3.x/agents/*.toml` 的位元組當升級
     fixture（`:424-2024`）。
   - `retired/`：程式與測試都沒讀；`install/AGENT-INSTALL.md:251` 的 runbook
     叫 agent 比對這兩個檔案，SHA-256 只在
     `docs/specs/codex-native-multi-agent-migration/` 內。
7. **`INSTALL_PROMPT.md` 是鎖定 surface**：LOCK.json 要求它含
   ``Read `INSTALL.md` completely``。所以 `INSTALL.md` 檔名必須留在根目錄，
   改成索引後要明講「Codex 讀 `docs/install/codex.md`」；`INSTALL_PROMPT.md`
   本身不動，免 lock renewal。另有 3 個 tests 讀 INSTALL.md 的內容（版本表
   等），要跟著改路徑。
8. **CI path filter**（`.github/workflows/python-tests.yml`，pull_request 與
   push 各一份）列了 `install/**`、`plugin/**`、`claude-plugin/**`、
   `.claude-plugin/**`，另有 `py_compile` 一行含
   `install/evaluate_dispatch.py`。新目錄 `bench/**`、`plugins/**` 沒加進去
   就不會觸發 CI。

### F4. templates/、artifacts/、upstream.lock

| 項目 | 是什麼 | 處置 |
| --- | --- | --- |
| `templates/` | Codex host 的 dist（render 產出）：`agents/*.toml`、`agents-md.*.md`、`hooks.json`、`config.snippet.toml`。LOCK.json 有 14 個 surface 在這裡；`install.sh`、`install.py`、`sync_global.py`、dotfile `setup_codex.sh`（`git show HEAD:templates/agents-md.bootstrap.md`）都讀它 | 保留。搬了要 lock renewal 加外部 dotfile 改動，不值得；README 佈局表註明它等於 Codex 的 dist |
| `artifacts/` | 本機實驗證據（`.gitignore` 的 `artifacts/usage-routing/`），origin/main 沒有追蹤任何檔；只有 `docs/plans/astra-plan-v2.md:674` 引用 | 不動。它不在 repo，只有 Miyago 本機 checkout 才有 |
| `upstream.lock` | 各 host 上游與版本記錄（spec R6），README、INSTALL.md、`tools/scan_legacy_names.py`、5 個 tests 引用 | 保留在根目錄（上游溯源是頂層事實，搬了只增加引用修改） |

## Decisions

每項是 Miyago 要拍板的，附建議。可移植性優先改變了 D1、D2，新增 D9-D11。

| # | 問題 | 建議 |
| --- | --- | --- |
| D1 | Claude 兩個 plugin 移到 `plugins/claude`、`plugins/claude-guard` | 做，但依賴 `--update`（P3）上線且 dotfile 改成呼叫它（原本依賴「dotfile 雙佈局」，已取消）。`--update` 從 repo 自己讀佈局，之後再搬目錄不會再破壞 updater |
| D2 | Codex plugin 實體搬移與登記方式 | 拆成兩件。(a) **登記改可移植（P2，這版做）**：一律登記 shoal 擁有的匯出目錄（見 F1b），檔案不搬，不動 LOCK；Git 來源只是文件中的替代方式。(b) **實體搬到 `plugins/codex`、`plugins/jev-router`（P8）仍延後**：登記改可移植後，搬移只剩外觀收益，卻要 lock renewal，不符合「不動受保護 surface」 |
| D3 | benchmark 目錄名 | `bench/`：短、和 `docs/benchmarks/`（結果）對應。`eval/` 不好，因為 `validate_*`、`verify_dispatch` 也是驗證但屬安裝 |
| D4 | `stage_smoke_home.py`、`routing_contract.py`、`probe_hybrid_runtime.py` 留在 `install/` | 留（理由見 F3-5）。把 `verify_dispatch` 一起搬進 `bench/` 會動到 CI、INSTALL 文件與 `AGENT-INSTALL.md` 的指令，不值得 |
| D5 | `install/previous/` 與 `install/retired/` | 不全刪：`previous/` 用 `git mv` 到 `tests/fixtures/install-history/previous/`（tests 當 fixture 用）；`retired/` 刪除，並把兩個 SHA-256 寫進 `AGENT-INSTALL.md:251` 取代檔案路徑。這比「全刪」少改約 30 行 tests，且 runbook 不失去判斷依據 |
| D6 | `INSTALL_PROMPT.md` 是否一併改成指向 `docs/install/codex.md` | 不改。避免 lock renewal；`INSTALL.md` 索引裡寫明 Codex agent 要完整讀 `docs/install/codex.md`。若 P8 要 renew，一起處理 |
| D7 | 「從 README 移入的參考資料」（1243-1425）去哪 | 新增 `docs/reference.md`，逐字搬移（只更新「目錄結構」一節，且每個後續 phase 都要同步它）。Miyago 列的清單沒有它，但不放就得塞進別的檔 |
| D8 | 根目錄 shim | 不加（見 F2）；可移植性下 shim 還要多一個 Windows 版 |
| D9 | opencode 安裝步驟：把 `install.sh` 的複製邏輯移植成 Python，或接受 Windows 需要 `sh`（Git for Windows 帶有） | 移植成 Python（放在 `tools/`，`install.sh` 變成薄包裝或保留給舊文件）。接受 `sh` 等於核心路徑有 shell 依賴，違反原則；先查證 `install.sh` 與 `sync_global.py` 的 opencode 步驟能否共用同一份 Python |
| D10 | `--update` 是否包含 `git pull` | 不包含：它只更新「本機 checkout 的 committed HEAD」，與今天 `update_shoal` 相同；拉取最新由使用者或 dotfile 自己做 |
| D11 | Windows CI | 用現有 `python-tests.yml` 的 `windows-latest` matrix，加入口 dry-run 與 `--update` dry-run 步驟；不新增 workflow |

## Requirements (EARS)

- **R1**：When 使用者照 README 快速開始任一 host 的指令，the system shall 只
  有一種寫法：`python3 tools/shoal_install.py --host <h> --apply`（不帶
  `--apply` 為 dry-run）。
- **R2**：When `--host` 是 claude、codex、grok、opencode、agy 之一，
  `--apply` shall 讓該 host 的 role、policy 與（預設）guard 都到位，不需再手
  動補步驟（G1、G2 補齊）。
- **R3**：When 不帶 `--apply`，the system shall 呼叫底層 installer 的
  dry-run 並顯示其輸出（G3）；外部 CLI 不存在時 shall 回報 `skipped`，不失敗
  （G6）。
- **R4**：The Claude plugin marketplace 路徑
  （`claude plugin marketplace add miyago9267/shoal`）shall 保留為 Claude 的
  替代方式，並在 README 與 `docs/install/claude.md` 說明。
- **R5**：`INSTALL.md` shall 是 100 行以內的索引；每個 host 一份
  `docs/install/<host>.md`，另有 `docs/guard.md`、`docs/modules.md`、
  `docs/reference.md`。內容用搬移，不改寫（除了更新過期路徑與新入口指令）。
- **R6**：`README.md`、`docs/README.en.md`、`docs/README.zh-CN.md` shall 有
  相同的快速開始。
- **R7**：`install/` shall 只留保留清單的 13 個檔；其他 26 支腳本在
  `bench/`，且原有 tests 全部通過。
- **R8**：When Claude plugin 目錄搬到 `plugins/`，the system shall 讓既有
  GitHub marketplace 使用者執行 `claude plugin marketplace update shoal` 後
  無需其他動作。
- **R9**：The change shall 不改動 LOCK.json（P8 暫不做）；
  `validate_prompt_lock.py` 在無 renewal 旗標下通過。
- **R10**：Phase 之間 shall 可獨立出貨：每個 phase 結束時 CI 全綠、各 host
  的 dry-run 結果與 phase 前一致。
- **R11**（可移植性）：The entrypoint 的核心路徑 shall 只用 Python stdlib，
  並在 macOS、Linux、Windows 行為相同；不得呼叫 `sh`、`bash`、`tar`、`zsh`
  （外部 CLI 僅限 `git`、`claude`、`codex`、`bun`，以 `shutil.which` 解
  析）。
- **R12**（可移植性）：The system shall 不把使用者 checkout 的絕對路徑寫進任
  何 host 的設定；Codex 一律登記 shoal 擁有的匯出目錄
  `${XDG_DATA_HOME:-~/.local/share}/shoal/codex-marketplace`，不自動選用 Git
  來源。When 偵測到舊的 `<repo>/plugin` 登記，`install.py` shall 先移除再登
  記匯出目錄；已安裝判斷 shall 比對 `marketplaceSource` 與匯出目錄。
- **R13**：When 執行 `python3 tools/shoal_install.py --update [--apply]`，
  the system shall 做 `update_shoal` 現在做的事，且每步一行
  `<step>: up-to-date | updated | skipped | failed`：(1) 以 `git archive` 匯
  出 committed HEAD（Python `tarfile`，不用 `tar`）到
  `${XDG_DATA_HOME:-~/.local/share}/shoal/` 底下的暫存目錄；(2) 與現有
  marketplace 逐檔比對 sha256，全部相同則回報 `up-to-date` 且不交換；(3) 有
  差異時以兩次 rename 交換：現有目錄改名為 `.old`，暫存目錄改名為正式名稱
  （不用 rmtree 加複製；Windows 的 `os.replace` 不能覆蓋非空目錄）；
  `claude-explore` 未被模組清單停用時安裝 `Explore.md`；(4)
  `claude plugin marketplace add|update`、`plugin install|update`（guard
  plugin 依模組清單與 chain 決定）；其中任何一步失敗，shall 把 `.old` 改名還
  原並回報 `failed`，全部成功後才刪 `.old`；(5) Codex plugin 以 R12 的匯出目
  錄登記；(6) 各 host 同步（沿用 `sync_global.py` 的邏輯）；(7) hash 檢查：
  匯出內容與已安裝的 marketplace、`Explore.md` 逐位元組比對 sha256，不符為
  `failed`。啟動時 shall 先清掉上次殘留的 `.old` 與暫存目錄（`.old` 在上次失
  敗後已還原，殘留者直接刪除）。不帶 `--apply` 為 dry-run，只回報會做什麼。
- **R14**：The `--update` shall 不依賴 dotfile；dotfile 的 `update_shoal`
  shall 只呼叫它。Claude `settings.json` 的 `~` 還原與 remora、calico 更新留
  在 dotfile。
- **R15**（可移植性）：CI shall 在 `windows-latest` 跑入口對五個 host 的
  dry-run（暫存 `HOME`）與 `--update` dry-run，皆 exit 0。

## Inventory

指令：`rg -n --no-heading -g '!.git' -g '!CHANGELOG.md' <pattern> .`，以
`7b572a4` 計；格式為「行數(檔案數)」。specs-history 是 `docs/specs`、
`docs/plans`、`docs/verification`、`docs/benchmarks` 的歷史紀錄，不回改（與
`docs/specs/delegation-default/RENAME.md` 的慣例一致）。CI 欄是
`.github/workflows/python-tests.yml` 的行數（rg 預設略過隱藏目錄，這欄用
`--hidden` 另查）。

| 搬移項目 | code | tests | goldens | docs | specs-history | CI | LOCK.json | 外部 dotfile |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `claude-plugin/` | 10(3) | 24(3) | 1(1) | 9(1) | 18(8) | 2 | 0 | 1 行（updater `:154`） |
| `claude-guard-plugin/` | 5(4) | 11(1) | 2(2) | 6(1) | 5(3) | 0 | 0 | 同上 |
| `.claude-plugin/marketplace.json`（留原處，`source` 要改） | 2(1) | 2(1) | 1(1) | 3(1) | 3(2) | 2 | 0 | 同上 |
| `plugin/`（Codex，D2 延後） | 41(12) | 35(12) | 2(1) | 0 | 4(4) | 2 | 7(1) | 0 |
| bench 腳本（26 支） | 39(16) | 54(27) | 0 | 4(1) | 59(15) | 3 | 0 | 0 |
| `install/previous`、`install/retired` | 0 | 約 30 行(1) | 0 | 1(1) | 15(6) | 0 | 0 | 0 |
| `INSTALL.md` | 1(1) | 7(5) | 0 | 27(10) | 41(24) | 0 | 1(1) | 0 |

補充：

- `tests/golden/claude-plugin/` 有 23 個追蹤檔，內部路徑是
  `claude-plugin/...`、`claude-guard-plugin/...`，另有 `SOURCE` 記錄
  `path: claude-plugin claude-guard-plugin ...`；搬動後要用
  `tools/refresh_golden.py --host claude-plugin --from-dist` 重產（SOURCE 的
  commit 也會變）。
- `code` 欄的主要檔案：`tools/render.py`（`CLAUDE_PLUGIN`、
  `CLAUDE_GUARD_PLUGIN`、`CLAUDE_MARKETPLACE` 常數與輸出路徑，`:1230-1340`；
  `:1175` 一個 codex plugin 路徑）、`install/modules.json`（`paths` 欄，3
  處）、`package.json`（`lint:md` 的 ignore `#claude-plugin`）、
  `hosts/claude/plugin-src/shoal_guard_compat.py:45`（及其 render 產出
  `claude-plugin/hooks/shoal_guard.py:45`）。
- CI 行：兩份 path filter 各含 `install/**`、`plugin/**`、
  `claude-plugin/**`、`.claude-plugin/**`，加一行 `py_compile`
  （`python-tests.yml:75`）列出 `install/evaluate_dispatch.py`（bench 搬動時
  要改）。bench 的 3 行是 `install/**` 兩份加 `py_compile`。
- LOCK.json 的 7 行：5 個 surface `path`，加 `references` 與 `agents` 子項的
  重複行；全部在 `plugin/plugins/shoal-codex/`。
- 外部 dotfile：`~/dotfile/script/common/setup_codex.sh` 只讀
  `HEAD:templates/agents-md.bootstrap.md`（`templates/` 不動，不受影響）。
  `tools/sync_global.py` 在 repo 內，其 `plugin`、`install` 路徑檢查
  （`:285,297`）只在 D2 做時才需要改。
- `INSTALL.md` 的內部錨點被引用：`README.md` 的 `INSTALL.md#模組`、
  `install/AGENT-INSTALL.md:209` 的 `INSTALL.md#prove-the-hook-can-launch`、
  `hosts/codex/README*.md`；`tools/check_links.py` 不驗錨點，搬完要另外
  grep。

## INSTALL.md 搬移對照（行號為 `7b572a4`）

| 目的檔 | 來源行 |
| --- | --- |
| `docs/install/codex.md` | 1-262、418-513（含 Safe rerun、Recovery、Final report）|
| `docs/install/grok.md` | 514-595 |
| `docs/install/claude.md` | 959-1059（Claude Code plugin）|
| `docs/install/agy.md` | 596-626 的安裝指令與 627-659 的 agy 條目；加一段新文字說明 agents、skills、rules 的 symlink（G2 修好後改為 installer 負責）。這是唯一需要新寫的段落 |
| `docs/install/opencode.md` | 1060-1102 |
| `docs/guard.md` | 263-417（Codex guard）、596-958（Claude／agy guard 行為、規則表、guard chain）|
| `docs/modules.md` | 1103-1242（模組、旗標、chain、改名、每日同步、從舊名升級）|
| `docs/reference.md` | 1243-1425（逐字，目錄結構一節更新）|
| `INSTALL.md`（新） | 索引：五個 host 連結、`docs/guard.md`、`docs/modules.md`、`docs/reference.md`；Codex agent 完整讀 `docs/install/codex.md` |

## Migration impact

### Claude marketplace 使用者（GitHub，`marketplace add miyago9267/shoal`）

Claude 讀預設 branch 的 `.claude-plugin/marketplace.json`，`source` 是相對路
徑。v3.11.0 的 `source` 變成 `./plugins/claude`、`./plugins/claude-guard`。
使用者跑 `claude plugin marketplace update shoal` 會抓新的 manifest；plugin
cache 以 `name@marketplace/version` 為鍵，與 repo 內路徑無關。預期不需任何動
作；釘在 `#vX.Y.Z` 的使用者讀的是舊 tag，不受影響。這是推論，P6 要做一次
live 驗證（暫時 `CLAUDE_CONFIG_DIR`，從 v3.10.0 的 tag 加入 marketplace，再
把來源換到 P6 的 commit 做 update，確認 plugin 清單與 hook 路徑）。

### 本機 marketplace（dotfile updater）

今天 `update_shoal` 以寫死的 pathspec 做 `git archive`，P6 搬目錄會讓它每天
失敗（fail-safe，不破壞既有安裝）。新做法：P3 讓 `--update` 以 repo 自己的
`.claude-plugin/marketplace.json` 決定要匯出哪些目錄，不寫死
`claude-plugin`；dotfile 的 `update_shoal` 改成呼叫
`python3 tools/shoal_install.py --update --apply`。順序：P3 合併、Miyago 套
用 dotfile 變更並驗證一天，然後才合併 P6。補丁由 Miyago 或在他核准下套用，本
spec 不改 dotfile。

### Codex plugin cache 與 marketplace 登記

P2 改登記方式，所以現有 Codex 安裝會被動到：舊登記是 `<repo>/plugin` 絕對路
徑，plugin cache 在 `~/.codex/plugins/cache/shoal-codex/`。`install.py` 偵測
到舊 `marketplaceSource` 時，先
`codex plugin marketplace remove shoal-codex`，再登記匯出目錄，然後
`plugin add`。需實測的事項：remove 後 cache 是否保留、同名重新登記是否沿用已
啟用的 plugin 設定、`sync_global` 的 legacy 偵測（`:285,297`）不誤判。P2 的
驗收包含在暫存 `CODEX_HOME` 上從舊登記升級。

### dotfile 其他入口

`setup_codex.sh` 只讀 `templates/`（不動）。`setup_gemini.sh` 連
`hosts/agy/dist`（不動）。opencode harness 路徑
（`hosts/opencode/plugin/...`）不動。

## 舊路徑相容（一個 release）

結論：不放 symlink 或轉發檔。

- GitHub 使用者：manifest 一更新就換成新路徑，舊路徑無人讀取；釘 tag 的讀舊
  tag 內容。
- 本機 dotfile：由 `--update` 提供（讀 repo 自己的 manifest），與佈局無關。
- symlink 的成本：`git archive` 與 Windows checkout 對 symlink 行為不一致，
  違反可移植性，還會讓 render `--check` 的「擁有的路徑清單」多一組要排除。
- Codex：只有 F1b 甲案才保留 `plugin/.agents/plugins/marketplace.json` 一個
  release，讓尚未升級的舊登記（指向 `<repo>/plugin`）仍可讀；乙案沒有下架
  期。
- `shoal_guard_compat.py` 的候選路徑（F3-4）要新增 `claude-guard/`，同時保留
  `claude-guard-plugin/` 一個 release，因為舊 session 可能混著新舊
  marketplace 目錄。

## Prompt-lock 影響

- P1-P7 不改變 `docs/specs/prompt-document-lock/LOCK.json` 的任何 surface 路
  徑或內容：受保護的是 `templates/`、`hosts/claude/dist`、
  `INSTALL_PROMPT.md` 與 `plugin/plugins/shoal-codex/*`，這幾個都不動（P2 新
  增的根 manifest 與 plugin 實體檔案不同，不在 LOCK 內）。`version_gate` 的
  規則是：某個 surface 的內容有變，該 surface 宣告的 `version_file`（例如
  `hosts/codex/VERSION`）就必須跟著變；它不看 repo 根的 `VERSION`，所以本次
  沒有 surface 變動就不觸發。
- P8（Codex 實體搬移）才會動 5 個 surface `path` 與
  `REQUIRED_SURFACE_PATHS`；`manifest_immutable` 要求走
  `--allow-lock-update`，也就是 Miyago 套用 renewal（PR label `lock-renewal`
  或 main 的 commit 訊息 `Lock-Renewal: approved`），CI 的 PR 路徑會帶
  `--no-migration`。
- 動 `INSTALL_PROMPT.md`（D6）同樣要 renewal，所以本版不動。

## Phases

每個 phase 一個 PR，可獨立合併。共用驗證指令（repo 根）：
`python -m unittest discover -s tests`、
`python3 install/validate_prompt_lock.py --base-ref origin/main`、
`python3 tools/render.py --check`（各 host）、
`markdownlint-cli2 "**/*.md"`、`python3 tools/check_links.py`。

### P1 可移植入口、安裝缺口與 README

內容：補 G1-G6（G4 先查證）；opencode 步驟 Python 化（D9）；`shutil.which`
解析外部 CLI；README 與兩份語言版快速開始改成單一入口，保留 Claude
marketplace 替代；`python-tests.yml` 新增 R15 的 Windows dry-run 步驟（入口
部分，`--update` 在 P3 加）。停止條件：五個 host 的 dry-run 與 `--apply`（暫
存 `HOME`，並用 `CODEX_HOME` 等環境變數指到暫存目錄）通過，Windows job 綠。
驗收：新增涵蓋 G1-G3、G5、G6 的 tests；`tests/test_install_entrypoints.py`
通過；三份 README 快速開始除語言外相同；
`rg -n "\b(sh|bash|tar)\b" tools/shoal_install.py` 在核心路徑無呼叫；
`check_links.py README.md docs/README.*.md` 通過。不碰 LOCK surface。

### P2 Codex 可移植登記（不搬檔案）

內容：live 驗證決定匯出內容（F1b 甲或乙，結果寫回本 spec）；
`install/install.py` 與 `tools/sync_global.py` 改為匯出 committed HEAD 到
`${XDG_DATA_HOME:-~/.local/share}/shoal/codex-marketplace` 並登記該目錄；偵
測舊 `<repo>/plugin` 登記並遷移；已安裝判斷改比對 `marketplaceSource` 與匯出
目錄；Git 來源只寫進 `docs/install/codex.md`；甲案才新增根 manifest 並保留
`plugin/.agents/plugins/marketplace.json` 一個 release。停止條件：live 驗證
結果已寫入 spec。驗收：在暫存 `CODEX_HOME`、離線
（`GIT_ALLOW_PROTOCOL=none`）、從舊 `<repo>/plugin` 登記升級；跑完後
`codex plugin marketplace list --json` 的 root 是匯出目錄、不含 checkout 路
徑，兩個 plugin 都列出，重跑全為 `up-to-date`；`tests/test_install.py`、
`tests/test_plugin.py`、`tests/test_jev_router.py` 更新後通過；
`validate_prompt_lock.py` 無旗標通過；`INSTALL_PROMPT.md` 無 diff。

### P3 `--update`（dotfile 隨後改成呼叫它）

內容：R13、R14。停止條件：在這台機器上
`python3 tools/shoal_install.py --update --apply` 的結果與今天
`update_shoal` 加 `sync_global.py --apply` 的結果一致（marketplace 目錄逐位
元組相同、`Explore.md` 相同、各 host 摘要行相同）；Windows job 加 `--update`
dry-run。驗收：新增 tests（暫存 `HOME`、假的 `claude` 與 `codex` 可執行
檔），涵蓋模組停用、hash 不符、CLI 不存在、第二次全為 `up-to-date`，另外兩個
交換案例：(a) 假的 `claude` 在第 2 次呼叫 exit 1，輸出含 `failed`，
marketplace 的 sha256 與執行前相同，且沒有殘留 `.old`；(b) 預先放一個殘留
`.old` 與暫存目錄，重跑能成功並清掉它們。G2 的 tests：monkeypatch
`os.symlink` 丟 `OSError`，執行 `--host agy --apply`，目標檔案與
`hosts/agy/dist` 相同、`modules.json` 記 `agy_mode: copy`；接著 `--update`
dry-run 回報 agy `up-to-date`（`sync_global.py:402-403` 改為 copy 模式比對
sha256）。以上全部在 `windows-latest` 執行。**P3b（dotfile，Miyago）**：
`update_shoal` 改為呼叫入口；驗收：`~/.local/share/shoal/update.log` 一天的
記錄無 `failed`。P6 以 P3b 完成為前置。

### P4 文件拆分

內容：`INSTALL.md` 拆成索引與上表的檔案，用搬移，描述的是**合併當下**的佈局
（`claude-plugin/`、`install/` 含 bench 腳本都還在）。停止條件：新檔合計行數
等於原 1425 行加減索引與標題調整（以 `wc -l` 與 diff 驗證沒有內容遺失）。驗
收：`markdownlint-cli2` 與 `check_links.py` 通過；錨點引用（README、
AGENT-INSTALL、`hosts/codex/README*`）全部更新並以 grep 驗證；
`test_render_claude`、`test_render_grok`、`test_astra_routing` 改讀新位置後
通過；`INSTALL_PROMPT.md` 無 diff、`validate_prompt_lock.py` 通過；
`docs/reference.md` 目錄樹的每個路徑都 `test -e` 成立。

### P5 install/ 瘦身

內容：

- 26 支 `git mv` 到 `bench/`：`astra_session`、`benchmark_role_fitness`、
  `benchmark_routing`、`claude_eval_smoke`、`claude_live_probe`、
  `decision_checkpoint`、`evaluate_dispatch`、`evaluate_intent_matrix`、
  `evaluate_pilotfish_value_matrix`、`evaluate_quality_cost_frontier`、
  `execution_contract`、`intent_review_matrix`、`quality_cost_frontier`、
  `regrade_role_fitness_adjudicator`、`review_intent_contract`、
  `role_fitness_adjudicator_matrix`、`role_fitness_claude`、
  `role_fitness_fixtures`、`role_fitness_routing_matrix`、
  `role_fitness_scorecard`、`role_fitness_stage`、
  `run_role_fitness_adjudicator`、`run_role_fitness_content`、
  `run_role_fitness_live`、`run_role_fitness_native_adjudicator`、
  `run_role_fitness_sol_effort`（皆為 `.py`）。
- 保留 13 個檔（見 F3-5），`probe_hybrid_runtime.py` 留在 `install/`，所以
  `AGENT-INSTALL.md:184` 不改。
- `previous/` 移到 `tests/fixtures/install-history/previous/`，改
  `tests/test_install.py` 的路徑；`retired/` 刪除，`AGENT-INSTALL.md:251` 改
  為列出兩個 SHA-256。
- `python-tests.yml`：兩份 path filter 加 `bench/**`；第 75 行 `py_compile`
  清單的 `install/evaluate_dispatch.py` 改為 `bench/evaluate_dispatch.py`
  （其餘 `install/` 路徑不變，含 `install/probe_hybrid_runtime.py`）。
- `tools/scan_legacy_names.py:52` 的 `EXEMPT_FILES` 改為 `bench/evaluate_` +
  `pilot` + `fish_value_matrix.py`；同步
  `tests/test_scan_legacy_names.py:108` 與
  `tests/test_check_rename.py:101,103` 的路徑；
  `tools/scan_legacy_names.py:13` 註解。
- tests 的 `sys.path` 加 `bench/`；`docs/reference.md` 的目錄樹與
  `docs/install/*.md` 內提到 install 腳本的路徑同步。

停止條件：`install/` 只剩保留清單，`git log --follow` 確認歷史保留。驗收指令
（全部 exit 0 或指定輸出）：

```bash
python -m unittest discover -s tests
python -m unittest tests.test_scan_legacy_names \
  tests.test_check_rename tests.test_hybrid_probe
python3 tools/scan_legacy_names.py
# 無輸出才算通過（實際搬動的 stems）
rg "install/(astra_session|benchmark_|claude_eval_smoke|claude_live_probe|\
decision_checkpoint|evaluate_|execution_contract|intent_review_matrix|\
quality_cost_frontier|regrade_role_fitness|review_intent_contract|\
role_fitness_|run_role_fitness_)" \
  -g '!docs/specs' -g '!docs/plans' -g '!CHANGELOG.md'
# AGENT-INSTALL.md 的每個 install 路徑都要存在
rg -o "install/[a-z_]+\.py" install/AGENT-INSTALL.md | sort -u |
  while read -r p; do test -e "$p" || echo "missing $p"; done
```

另外：`docs/reference.md` 目錄樹的每個路徑 `test -e` 成立；
`install/install.sh --help`、`install/install.ps1 --help`、
`verify_dispatch.py --help` 照舊；CI path filter 含 `bench/**`。

### P6 Claude plugin 搬到 plugins/（依賴 P3b）

內容：`tools/render.py` 常數與輸出路徑、`.claude-plugin/marketplace.json` 的
`source`、`install/modules.json`、`package.json` ignore、
`shoal_guard_compat.py` 候選路徑、CI path filter（加 `plugins/**`）、
`tests/golden/claude-plugin` 重產、`test_claude_plugin.py` 路徑；
`docs/reference.md` 與 `docs/install/claude.md`（以及其他 docs）內的
`claude-plugin/`、`claude-guard-plugin/` 路徑。停止條件：
`render.py --check --host claude-plugin` 通過且舊目錄不存在。驗收：unittest
全綠；`validate_prompt_lock.py` 無旗標通過（證明 LOCK 未動）；
`docs/reference.md` 目錄樹每個路徑 `test -e` 成立；以暫存
`CLAUDE_CONFIG_DIR` 做 live（舊 tag 加入 marketplace，更新到 P6，
`claude plugin list` 兩個 plugin 都在，
`claude plugin install shoal-dispatch-guard@shoal` 後 hook 可執行；P3b 的
`--update --apply` 在新佈局成功）。docs 路徑檢查如下：P6 之前有輸出（文件描
述當時佈局），P6 之後無輸出。

```bash
rg -n "claude-plugin/|claude-guard-plugin/" docs README.md INSTALL.md \
  -g '!docs/specs' -g '!docs/plans' -g '!docs/verification' \
  -g '!docs/benchmarks' | rg -v "\.claude-plugin/"
```

### P7 v3.11.0 發佈

內容：`VERSION`、`.claude-plugin/marketplace.json` 兩個 `version`、render 產
出的 plugin.json 版本、`CHANGELOG.md`（寫明新路徑與升級說明）、README 佈局表
（含 `templates/`、`upstream.lock`、`plugin/` 與 `plugins/` 並存的說明）。停
止條件：P1-P6 已合併、CI 綠。驗收：`render.py --check` 全 host；
`python3 install/validate_prompt_lock.py --base-ref origin/main` 無旗標通
過；三個 OS 的 CI 綠。tag 與 push 由 Miyago 決定，本 spec 不做。

### P8 Codex plugin 實體搬移（延後，需 lock renewal）

內容：`plugin/plugins/*` 移到 `plugins/codex`、`plugins/jev-router`，同步
`.agents/plugins/marketplace.json` 的 `source.path`。停止條件：Miyago 套用
lock renewal 且 live 驗證通過。不在 v3.11.0 範圍。

## Out of scope

P8 的 Codex plugin 實體搬移、`INSTALL_PROMPT.md` 內容、`templates/` 與
`upstream.lock` 的移動、`--host all`、`--update` 內的 `git pull`、dotfile 本
體的修改（只提供補丁需求）、Claude `settings.json` 的 `~` 還原與 remora、
calico 更新。
