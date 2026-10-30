---
id: spec-text-first
title: Text first
status: draft
created: 2026-10-22
updated: 2026-10-23
author: Miyago
tags: [prompts, render, ci, bench]
priority: medium
---

<!-- markdownlint-disable MD025 -->

# Text first：讓 prompt 文字成為 repo 的主體

方向於 2026-10-22 經 Miyago 核准；本文是實作前的規格，量測基準為
main `863943c`，已 rebase 到 `8da4d0f`。後者只合入 PR #34（刪除 `docs/archive`
與 `docs/assets/reel-*`，不動 `tools/`、`tests/`、`hosts/`、`core/`），所以下列
事實不變；`docs/benchmarks` 仍存在，D5 因此要處理它。

## Background

shoal 是文字產品，但文字埋在程式裡：

- 384 段 prompt 文字寫在 TOML 的 `'''` 字串內（共 1125 行正文，其中 147 行
  超過 80 欄、最長 505 欄）。來源有三處：`core/policy/*.toml`（4 份文件，
  1275 行 TOML）、`core/contracts/<role>.toml`（9 個 role，950 行）、
  `hosts/*/addenda`、`hosts/*/policy-addenda`、`hosts/claude/relay` 底下的
  addendum（合計 1208 行 TOML）。每段條款還要背 6 行左右的 TOML 外框
  （`[[clause]]`、`id`、`kind`、`sep`、`text = '''`）。
- 另有約 38 段 role `description`（model 派工時會讀到）寫在
  `hosts/{claude,codex,agy,grok}/binding.toml`；`tools/render.py` 內還有
  寫死的句子（relay 的 write rules、run step、plugin / marketplace / hook
  description，`render.py:591-596`、`:656-683`、`:1418-1530`）。
- 53 個看起來可編輯、實際上被 core 輸出覆蓋的舊檔（共 155,618 bytes）。
  改它們不會有任何效果，只會誤導。
- 同一份文字被 commit 3 到 5 次：`hosts/*/dist`、`plugins/*`、`templates/`、
  `tests/golden/`（107 檔、337,521 bytes）。
- 約 1.5k 行測試（golden 比對、wording 斷言）在驗證「文字等於文字」。
- `bench/`（440 檔、1.19 MB）與 28 個只服務 bench 的測試模組（10,549 行）
  住在產品 repo 裡，卻不參與安裝。

成功標準：改一句 prompt 只需要編輯一個 `.md` 檔，執行一次
`render --write`，diff 只出現在 `prompts/` 與它的輸出；沒有可編輯但無效的檔；
commit 的生成物只剩有人讀得到的那幾份。

依據：Miyago 2026-10-22 的方向核准；以下「已驗證事實」由本 spec 作者在
main `863943c` 實測。

### 已驗證事實（會改變計畫的部分）

量測方法：把每個 `hosts/**`、`core/**` 檔各自附加一行再 render 全部 host 與
claude-plugin，輸出雜湊改變才算 live（168 個檔，104 live、64 dead）。

| 項目 | 結果 | 對計畫的影響 |
| --- | --- | --- |
| 死檔 | 53 個 md：agy 11、claude 13、codex 11、grok 9、opencode 9 | scout 清單漏了 claude 的 `SKILL.md`、`workflow-extensions.md`，agy 的 `rules/shoal-agy.md`、`skills/.../SKILL.md`，codex 的 `agents-md.bootstrap.md` |
| 活的 legacy src | grok 的 `src/rules/shoal-grok.md`（policy 與 hooks 也是活的）；opencode 沒有活的 md src，它的 `src/roles/*.md` 全死 | D2 保留 grok；opencode 的 role src 可刪 |
| 粗暴刪除的代價 | 刪 53 檔後 1906 個測試中 35 個失敗或錯誤（10 個模組） | P1 不是純刪檔，要改 `render_agy` 與測試 |
| agy marker | `rules/shoal-agy.md` 的 `<!-- shoal-agy vX -->` 實際來自 `policy-frames/bootstrap.md` 的手寫字面值；`_versioned_rules` 讀 src 後被 core 覆蓋 | 刪 src 時移除該呼叫；marker 與 `VERSION` 一致改由結構斷言保證 |
| `hosts/agy/dist`、`hosts/grok/dist`、`hosts/opencode/dist` | runtime 會讀：`shoal_install.py` symlink 或複製 agy dist、`install_grok.py` 對 HEAD 做 `git archive`、`opencode_global.py` 從 ref 讀、`modules.json` 列為安裝路徑；dotfile 的 `check_agent_rule_sync.sh` 與 `setup_gemini.sh` 也讀 | D3 不能停止 commit 這三份 |
| `templates/` | codex 的安裝輸入：`install.py`、`validate_agents.py`、`verify_dispatch.py`、`sync_global.py`、`install.sh`、dotfile `setup_codex.sh` 都讀；也是 lock 的 surface | 保留 |
| `plugins/claude*`、`.claude-plugin/` | `shoal_update.py` 對 HEAD 做 `git archive`，Claude plugin 由此同步 | 保留 |
| `hosts/claude/dist` | 與 `plugins/claude/{agents,skills,policy}` 逐位元組相同（`diff -r` 驗證）；runtime 只讀 `agents/Explore.md`（`shoal_install.py:49`、`shoal_update.py:425`、`modules.json:53`）；lock 有 13 個 surface 指向它；dotfile `check_agent_rule_sync.sh:239` 讀它的 `SKILL.md` | 唯一可停止 commit 的 dist，但要 lock renewal 加 dotfile 一行修改（P3b，已核准，排在 P3a 之後） |
| `tests/golden` | 只有測試與 `tools/refresh_golden.py` 讀；內容等於 dist 的 regression 副本 | 可刪 |
| prompt lock | surface 全是輸出路徑（`templates/`、`plugins/codex/`、`hosts/claude/dist/`、`INSTALL_PROMPT.md`），沒有任何 `core/*.toml` | P1、P2、P3a、P4 不動輸出路徑，**不需要 renewal**；只有 P3b 要 |
| CI paths filter | `python-tests.yml` 的 paths 沒有 agy、grok、opencode 的 `hosts/` 路徑，也沒有 `prompts/**`（新） | 已決定：P1 補 `hosts/{agy,grok,opencode}/**` 與 `prompts/**` |
| CI 沒有獨立的 `render --check` | 只經由單元測試（`test_every_host_matches_its_committed_dist` 等）執行 | 已決定：P1 加明確步驟（輸出在 P1 不變，所以可立即生效） |
| bench 耦合 | bench 單向依賴 shoal：`install/{verify_dispatch,stage_smoke_home,routing_contract}.py`、`hooks/shoal_autoroute_gate.py`、`tools/`、`docs/benchmarks/`（`benchmark_routing.py`、`claude_eval_smoke.py`、`role_fitness_claude.py` 與 3 個測試讀它，`FROZEN_MANIFEST_V2_HASH` 釘它的 hash）；shoal 的 runtime 不 import bench。移除 bench 後 28 個測試模組無法 import，另有 1 個測試（`test_relay_render.py` 的 `OVERLAY`）讀 `bench/ab/relay.binding.toml` | D5 的「指回 shoal」要用 `SHOAL_ROOT`，不只是 `SHOAL_AB_PLUGIN_REF`；`docs/benchmarks` 列為相容面 |
| relay overlay | `tests/fixtures/relay/relay.binding.toml` 已存在，與 `bench/ab/relay.binding.toml` 只差開頭註解，內容相同；`render_equiv.py` 若只跑預設 binding，relay 路徑（`relay_shell`、runner 打包、`--overlay`）完全不在等價證明內 | `render_equiv.py` 另跑 relay overlay；P4 把測試的 `OVERLAY` 改指 fixture |
| 基準 | 全套測試 1915 個、297 秒（macOS）、OK（skipped=1） | P1 到 P4 的測試不得變紅 |

## Requirements (EARS)

- **R1**: Where 一段文字會被送進 model 的 context（role 正文、policy、
  frame、addendum、role description、relay 外殼），the system shall 讓它的
  唯一來源是 `prompts/` 底下的 `.md` 檔，TOML 與 Python 內不得再有該文字。
- **R2**: When 任何 phase 完成，the system shall 讓每個 host 與 claude-plugin
  的 render 輸出與 main 上 render 的輸出逐位元組相同；唯一例外是該 phase 明列
  「不再 commit」的檔案，它們仍必須能被 render 重新產生。
- **R3**: If `hosts/<host>/src` 內存在某個路徑，而該路徑是 core 會產生的輸出
  （`[policy.documents]` 的輸出路徑，或 `role_text = "core"` 的 role 的
  `agents/<role>.md`、opencode 的 `roles/<role>.md`），then render shall 以非 0
  結束並在錯誤訊息指出該路徑。判斷依據是檔案系統上 `src/<path>` 是否存在，
  不是比對內容。
- **R4**: The repository shall 只 commit 有 runtime 消費者的生成物
  （見「已驗證事實」），and CI shall 對其餘輸出執行 `render --check`。
- **R5**: While 輸出路徑與內容不變，the prompt lock shall 保持原狀；When lock
  必須改動，the change shall 是 main 上單獨一個 commit，帶 trailer
  `Lock-Renewal: approved`，且不改任何 prompt 內容。
- **R6**: When 文字內容測試被收斂，the test suite shall 保留所有行為測試
  （validation、`--check` / `--write` 行為、權限推導、installer、guard），
  and 文字回歸只由 `render --check`、lock 與少量結構斷言承擔。
- **R7**: Where bench 搬出，shoal shall 不含 `bench/` 與 bench 專用測試與 CI
  設定，and `miyago9267/shoal-bench`（private）shall 保留 bench 的 git 歷史，
  並以 `SHOAL_ROOT`（路徑）與 `SHOAL_AB_PLUGIN_REF`（ref）指回 shoal。
- **R8**: When 任何 phase 的 PR 開啟，CI shall 在 ubuntu、macOS、windows
  全部通過，包含 markdownlint 與 prompt lock 步驟。

## Non-goals

- 不改任何 prompt 的字句、順序、分隔、kind、required；不重排版以符合 80 欄
  （會改變輸出位元組，且需要 lock 預算與版本升級，另案）。
- 不改 role / host 的語意、binding 的權限欄位、模型選擇規則。
- 不動 `hooks/shoal_guard.py`、OpenCode 的 TS plugin、`plugins/codex` 內手寫的
  `SKILL.md`、`openai.yaml`、`plugin.json`、`templates/hooks.json` 的文字。
- 不拆 `docs/benchmarks` 與 `docs/specs/*benchmark*`（決策紀錄留在 shoal；
  shoal-bench 經 `SHOAL_ROOT` 讀它，見 D5）。
- 不碰已結案 spec。`docs/archive` 與 `docs/assets/reel-*` 已由 PR #34 刪除，
  不在本案範圍。
- P3b（停止 commit `hosts/claude/dist`）在本案範圍內（Miyago 2026-10-23
  核准），排在 P3a 之後；含 lock renewal 與 dotfile 修改。
- 不開 PR（本 spec 只 commit 並 push 到 `docs/text-first-spec`）。

## Alternatives Considered

### 方案 A：每條款一個檔（`prompts/roles/<role>/<clause-id>.md`）

metadata 留在 TOML manifest，文字一條款一檔。composer 最單純，但會有約 384
個小檔；讀完整份 policy 要開上百個檔，與「文字是主體」的目標相反。不採用。

### 方案 B：一份文件一個 `.md`，條款用 marker 切開（採用）

一份 policy、一個 role 就是一個可從頭讀到尾的 md。metadata 放在 marker 行，
不需要第二份 manifest；composer 只多一個約 40 行的 parser。

### 方案 C：用標題（`## clause-id`）切條款

不採用：條款正文本身含 `##` 標題（例如 `routing-heading` 的文字就是
`## Routing and lifecycle`），無法區分。

### 方案 D：D3 全部停止 commit `hosts/*/dist`

不可行：agy、grok、opencode 的 dist 是 installer 與 dotfile 的 runtime 輸入
（見事實表）。改成安裝時 render 會讓 installer 依賴 Python render 與 repo 全樹，
風險遠大於省下的檔案數。

## Rabbit Holes

1. 不要順手把 prompt 重排成 80 欄；位元組變了就違反 R2，也會踩 lock 預算。
2. 不要讓 parser 做 trim 以外的正規化；`_check_text` 已保證條款頭尾無空白，
   解析必須是它的逆運算，否則輸出會悄悄漂移。
3. 不要把 `core/contracts/handback.schema.json` 搬走：它被 relay 打包路徑
   `RELAY_PACKAGED` 與 runner 以固定相對路徑讀取。
4. 不要把 `tests/test_adapter_golden.py` 當成 render golden：它是 guard adapter
   的 fixture，與 `tests/golden/` 無關，必須保留。
5. 不要在 P1 以外刪 legacy 機制（`role_text = "legacy"`、`extra_roles`）：
   claude 的 `Explore.md` 與 codex 的 `sol-executor.md` 仍走它。
6. lock renewal 的 trailer 必須在 push 到 main 的 head commit 上；PR merge
   commit 的訊息不含它，CI 會判成未授權。

## Architecture

### 目錄

```text
prompts/
  roles/<role>.md                   # 原 core/contracts/<role>.toml
  policy/<doc>.md                   # 原 core/policy/<doc>.toml
  hosts/<host>/
    addenda/<role>.md               # 原 hosts/<host>/addenda/<role>.toml
    policy-addenda/<doc>.md         # 原 policy-addenda/<doc>.toml
    frames/<role>.md, default.md    # 由 hosts/<host>/frames 搬入
    policy-frames/<doc>.md          # 由 hosts/<host>/policy-frames 搬入
    descriptions.md                 # 原 binding.toml 的 role description
    relay/shell.md                  # 原 hosts/claude/relay/shell.md
    relay/policy-addenda/orchestration.md
    text.md                         # 原 render.py 內寫死的句子（claude）
```

TOML 只留 metadata：`core/roles.toml`、`models.toml`、`tiers.toml`、
`vendors.toml`、`core/policy/placeholders.toml`（詞彙與說明）、各 host 的
`binding.toml`（權限、模型、placeholder 值、omit、路徑對應；不含 description）。

### Marker 語法（D1）

```text
<!-- clause: <id> kind=<kind> [sep=paragraph|space|newline] [required] -->
<!-- addendum: <id> at=<anchor> [sep=<sep>] [join=<sep>] -->
<!-- description: <role> -->
<!-- text: <key> -->
```

- 一個 marker 之後到下一個 marker（或檔尾）之間的內容，去掉頭尾空行，就是
  `text`。`sep` 預設 `paragraph`，與現行 TOML 預設相同。
- 第一個 marker 之前只允許空行。`<id>`、`kind`、`sep`、`at` 的驗證沿用
  `contracts.py` 現有規則；只有 loader 換掉，`compose`、`compose_policy`、
  `check_policy_edits`、`substitute` 不動。
- 正文內任一行以 `<!-- clause:`、`<!-- addendum:`、`<!-- description:`、
  `<!-- text:` 開頭就是錯誤（loader 拒絕），避免歧義。
- 檔案以 UTF-8 逐位元組讀取，含 CR 即拒絕（與 `_check_text` 一致）；
  `.gitattributes` 已強制 `eol=lf`，Windows CI 不受影響。

### 載入端改動面

`tools/contracts.py`（新增 `parse_markdown_contract`、`parse_markdown_addenda`，
`_load` 的 TOML 路徑在 P2 末移除）、`tools/render.py`（`load_contracts`、
`load_policy`、`policy_files`、`explain_policy`、`role_body`、`relay_shell`、
`render_claude_plugin`、`_frontmatter` 的 description 來源）、
`tools/new_host.py`（scaffold 路徑）、`core/README.md` 與 `docs/new-host.md`
（格式說明）。測試 fixture 有 `[[clause]]` 的三個檔：`test_core_policy.py`、
`test_render_codex.py`、`test_role_contracts.py`，與複製 `core/` + `hosts/<host>`
的 `render_helpers.HostRenderCase.setUp`（要多複製 `prompts/`）。

### 等價證明（R2 的做法）

新增 `tools/render_equiv.py`（P1 提供，之後每個 phase 重用）：

```text
python3 tools/render_equiv.py --base origin/main --head HEAD
```

1. 對兩個 ref 各做 `git archive` 到獨立的 temp root。
2. 在各自 root 內用**該 ref 自己的** `tools/render.py` 對 claude、codex、agy、
   grok、opencode、claude-plugin 執行 `--write`。
3. 另把各 ref 的 archive 複製成第二個 root（relay root，每個 ref 一個，與第 2
   步的 root 分開，以免覆蓋預設輸出），在其中用該 ref 自己的
   `render.py --host claude-plugin --write --overlay
   tests/fixtures/relay/relay.binding.toml`。relay 路徑（外殼 agent、runner、
   `--overlay`）因此與預設輸出一樣受等價證明涵蓋。
4. 收集輸出根目錄（各 host dist、`plugins/claude`、`plugins/claude-guard`、
   `.claude-plugin/marketplace.json`、codex 的 mirror 目標，以及 relay root 的
   `plugins/claude*`、`.claude-plugin/marketplace.json`）內每個檔案的
   `(path, sha256)`，relay 輸出以 `relay:` 前綴區分；逐檔比對並印出總雜湊；
   任何差異即非 0 結束。
5. 另對 head 的 working tree 執行 `render --check`，證明「已 commit 的」也一致。

因為 `--write` 會重新產生未 commit 的輸出，被停止 commit 的檔案仍參與比較，
所以 R2 的例外不需要豁免清單。基準 sanity check 已在 main 上做過：archive
HEAD、全部 host `--write` 後與 working tree 的 9 個輸出目錄 `diff -r` 皆相同。

### Lock 與 renewal 的位置（D6）

```text
P1 -> P2 -> P3a -> R -> P3b -> P4
                   已核准（2026-10-23）；P4 最後
```

P4 排在最後：必須在 P1 到 P3b 全部合併、且 render 輸出與基準逐位元組相同之後
才做（2026-10-23 核准），避免 bench 搬出與輸出變更互相干擾。renewal `R`
因 P3b 而存在，必須在 P3b 之前先上 main：

- R 的內容：`LOCK.json` 把 13 個 `hosts/claude/dist/...` surface 的 `path`
  改為內容相同的 `plugins/claude/...`（`Explore.md` 同理），同步
  `validate_prompt_lock.py` 的 `REQUIRED_SURFACE_PATHS` 與相關測試。檔案清單
  只含 lock、validator、測試，不含任何 prompt 內容、不改任何 `VERSION`
  （`claude-eval-parity` R2）。
- 為何不需要 VERSION 變更：新路徑在 base 已存在且內容相同，變更量為 0，
  版本 gate 不觸發。
- 上線方式：單一 commit，message 含獨立一行 `Lock-Renewal: approved`，直接
  push 到 main（CI 讀 push 事件的 head commit message）；不走 PR merge。
  本機先以 `validate_prompt_lock.py --base-ref origin/main --allow-lock-update`
  通過、且不帶旗標時失敗來確認。
- R 是 main 歷史上不可逆的一步：Miyago 已核准 P3b，但**在 push 這個 commit
  之前必須先告知他**（見 TASKS TR.4）。
- dotfile 修改（`check_agent_rule_sync.sh:239`）在 P3b 之前先上；實測 dotfile
  只有這一處讀 `hosts/claude/dist`；`setup_gemini.sh` 讀的是 agy dist，P3b 不
  影響，但執行時仍以 grep 重新確認。

## ADR

### D1 全部 prompt 文字搬到 `prompts/*.md`

- 決策：採方案 B（上節語法與目錄）。包含 role description 與 `render.py` 內
  寫死的句子；metadata 留 TOML。
- 原因：parser 只多一個小函式，compose 路徑完全不動；一份文件可以從頭讀到尾；
  lint 與 diff 以 prose 為單位。
- 取捨：`prompts/` 內有 147 行超過 80 欄的正文，必須排除在 markdownlint 之外
  （比照現有的 `#hosts/*/frames`、`#hosts/*/policy-frames`）。
- 驗證：搬移用一次性腳本 `tools/migrate_text.py`，逐條斷言「md 解析結果等於
  舊 TOML 解析結果」（id、kind、sep、required、at、join、text 全部相等），
  通過後才刪 TOML 文字；腳本在同一個 PR 內最後一個 commit 移除。

### D2 刪除死檔，保留活的 legacy host src

- 決策：刪 53 個死檔（清單在 TASKS P1）。保留 grok 的 `src/rules`、`hooks`、
  `config.snippet.toml`，codex 的 `src/agents/sol-executor.md`、
  `config.snippet.toml`、`hooks.json`，claude 的 `src/agents/Explore.md`、
  `settings.snippet.json`。
- 防回歸（R3）：`merge_core_policy` 目前用 `out.pop(path)` 默默覆蓋 src
  （`render.py:811-816`）。改為檔案系統檢查：對每個 `[policy.documents]` 的輸出
  路徑，以及每個 `role_text = "core"` 的 role 的輸出路徑（`agents/<role>.md`，
  opencode 為 `roles/<role>.md`；`_legacy_body` 讀的就是這些路徑，見
  `:720-723`），只要 `src/<path>` 存在就 `RenderError` 並指名該路徑。agy 的
  `src/rules/shoal-agy.md` 由 `render_agy` 的 `_versioned_rules` 讀取
  （`:897-898`）而不經 `merge_core_policy` 的覆蓋，所以 P1 移除該呼叫後，
  同一個檢查（它是 `[policy.documents]` 路徑）也涵蓋它。policy 檢查只在
  `policy_text = "core"` 的 host 生效，role 檢查只對 `role_text = "core"` 的
  role 生效（含 `[roles.<name>]` 的覆寫）；因此 grok 與 opencode 的
  `policy_text = "legacy"` 不受 policy 檢查約束，grok 的 `src/rules/
  shoal-grok.md` 不會誤報。真實樹在 P1 刪檔後不觸發；legacy 的 `Explore.md`、
  `sol-executor.md` 屬 `extra_roles`，不是 core
  role，不受影響。
- agy：移除 `render_agy` 對 `_versioned_rules` 的呼叫與 `AGY_RULES_PATH` 的
  src 依賴；marker 與 `VERSION` 一致性由 P3a 的結構斷言保證。

### D3 只 commit 有消費者的生成物

- 決策：保留 `templates/`、`plugins/*`、`.claude-plugin/`、`hosts/{agy,grok,
  opencode}/dist`；停止 commit `tests/golden/`（P3a）；`hosts/claude/dist` 列為
  P3b（排在 P3a 之後）。CI 對所有輸出執行 `render --check`。
- 原因：事實表逐一列出消費者。與原假設不同，agy / grok / opencode 的 dist 是
  runtime 輸入（含 repo 外的 dotfile），不是 CI 專用副本。
- P3b 已於 2026-10-23 核准，納入本案。代價為：lock
  renewal、dotfile 一行修改（`check_agent_rule_sync.sh:239`
  改指 `plugins/claude/skills/...`）、`EXPLORE_DIST` 改指
  `plugins/claude/agents/Explore.md`、claude host 的 `--check` 改為只驗證不比對
  dist；收益只有 15 個檔。renewal commit 的 push 前須告知 Miyago。

### D4 文字內容測試收斂

- 決策：刪除「文字等於文字」的測試，改由三道關卡承擔：`render --check`（輸出
  等於來源）、lock（預算與 `required_fragments`）、少量結構斷言（marker 等於
  `VERSION`、mirror 相等、輸出無殘留 `{{`、每個 core role 都有輸出、frame 與
  addendum 不外洩到 dist）。行為測試全部保留。
- 判準（寫入 PROGRESS 的逐項 triage 表）：測試的唯一 oracle 是 golden、另一份
  render、或某句 prompt 是否存在，且該句不是 lock 的 `required_fragments` 以外
  的行為契約 -> 刪；否則保留。
- 範圍（實測，非原估的 2.2k）：golden 基礎設施與 golden 測試（`render_helpers`
  的 golden 函式、`GoldenTests`、`RefreshGoldenTests`、`refresh_golden.py`）、
  `test_templates` 的 wording 段（約 170 行）、`test_policy.py`（409 行 wording）、
  `test_core_policy` / `test_role_contracts` 內與死 src 比對的測試。預估移除
  1.2k 到 1.8k 行，確切數字以 triage 表為準。

### D5 bench 拆成私有 repo

- 決策：`miyago9267/shoal-bench`（private），用 `git filter-repo` 保留歷史，
  路徑清單含 `bench/` 與 28 個 bench 專用測試（`git subtree split` 只能帶
  單一 prefix，會丟掉測試的歷史，所以不採用）。
- 指回 shoal：新增 `bench/shoal_root.py`，讀 `SHOAL_ROOT`（預設 `../shoal`）；
  所有 `Path(__file__).resolve().parents[1] / "install"` 一類的 `sys.path`
  組合改用它；`SHOAL_AB_PLUGIN_REF` 保持現狀，改為對 `SHOAL_ROOT` 做
  `git archive`。
- 相容面（選 a）：`docs/benchmarks/` 留在 shoal，列為 shoal-bench 的相容面，
  shoal-bench 一律經 `shoal_root.py` 讀它（`SHOAL_ROOT/docs/benchmarks`）。
  理由：`FROZEN_MANIFEST_V2_HASH` 釘的是 shoal 內這份 manifest，決策紀錄
  （`docs/specs/*benchmark*`）也在 shoal，搬出會讓同一份資料有兩個版本；
  filter-repo 拆純 fixture JSON 要另算哪些檔是純 fixture，成本高於收益。與
  `docs/benchmarks` 並列的相容面：`tests/fixtures/benchmark_routing`（若 T4.2
  判定不專屬 bench）、`install/`、`hooks/shoal_autoroute_gate.py`、`tools/`、
  `templates/`；這些路徑改名須在 shoal 的 CHANGELOG 註明。
- 留在 shoal：`install/verify_dispatch.py`、`stage_smoke_home.py`、
  `routing_contract.py`、`probe_hybrid_runtime.py`（`AGENT-INSTALL.md` 與 CI
  使用）、`tests/bench_hook_latency.py`（量 guard 延遲，與 bench 無關）。
- 建立 private repo 屬外部操作；Miyago 已於 2026-10-23 核准，P4 最後執行
  （在 P1 到 P3b 輸出逐位元組相同之後）。
- relay overlay：shoal 內 `tests/fixtures/relay/relay.binding.toml` 已存在且
  內容與 `bench/ab/relay.binding.toml` 相同，所以 shoal 側不必搬檔；
  `test_relay_render.py` 的 `OVERLAY` 在 P4 改指該 fixture，測試保留。

### D6 lock renewal 是單獨一個 commit

見「Lock 與 renewal 的位置」。只有 P3b 需要；P1、P2、P3a、P4 都必須在
`validate_prompt_lock.py --base-ref origin/main`（不帶 `--allow-lock-update`）
通過。

## Phase 計畫

| Phase | 內容 | 可獨立合併 | 需要 renewal |
| --- | --- | --- | --- |
| P1 | 刪 53 個死檔、R3 防回歸、`render_equiv.py`（含 relay）、CI paths 補齊與獨立 `render --check` 步驟 | 是 | 否 |
| P2 | 文字搬到 `prompts/` | 是（建議在 P1 之後） | 否 |
| P3a | 刪 `tests/golden`、收斂文字測試 | 是 | 否 |
| R + P3b | 停止 commit `hosts/claude/dist`（已核准，排在 P3a 之後；R 的 push 前須告知 Miyago） | R 先於 P3b | 是（R） |
| P4 | bench 搬出（已核准 2026-10-23；最後執行） | 否（排在 P3b 之後） | 否 |

每個 phase 一個 PR，合併前跑：全套測試、`render_equiv.py`、lock（不帶旗標）、
`npm run lint:md`、三 OS CI。細節見 TASKS.md。

## Risks

| 風險 | 影響 | 緩解 |
| --- | --- | --- |
| parser 對頭尾空行 / 內嵌空行處理與 TOML 不同 | 輸出悄悄漂移 | `migrate_text.py` 逐條相等斷言；`render_equiv.py`；lock 預算作最後防線 |
| 搬移時文字被編輯器改動（全形空白、結尾空白、行尾） | 位元組不同 | 腳本產生 md，不手貼；CI 的 `render --check` |
| 53 個死檔之外還有隱藏讀取者（腳本、docs、dotfile） | 安裝或同步壞掉 | 已 grep repo 與 dotfile；P1 先在 clone 上跑全套；dotfile 的引用列於 TASKS |
| `python-tests.yml` 的 paths 沒涵蓋 agy、grok、opencode 的 `hosts/` 路徑 | 只改這些的 PR 不跑主測試 | P1 補齊並加 `prompts/**` |
| 測試 fixture 大量複製 `core/` 與 `hosts/<host>` | P2 漏複製 `prompts/` 造成假失敗 | 先改 `render_helpers` 與 `repo_fixtures`（T2.1），再改 loader |
| bench 搬出後 28 個測試模組不在 shoal 跑 | bench 腐壞無人發現 | shoal-bench 自己的 CI 檢出 shoal 並跑同一批測試 |
| 其他分支同時改 `package.json`、CI、docs（PR #34 已合入，無待處理分支） | merge conflict | 每個 phase 從最新 `origin/main` 開分支；衝突時 rebase 後重跑 lint |
| `Lock-Renewal` trailer 位置錯誤 | renewal 在 CI 變紅 | 直接 push 單一 commit；本機以旗標預演 |

## Open Questions（需 Miyago 決定）

已決定（2026-10-23）：

- P3b（停止 commit `hosts/claude/dist`）納入本案，排在 P3a 之後；含 lock
  renewal 與 dotfile 修改。
- `python-tests.yml` 補 agy、grok、opencode 的 `hosts/` 路徑與 `prompts/**`，
  並加獨立的 `render --check` 步驟，兩者都放 P1。
- P4 bench 拆成 private repo `miyago9267/shoal-bench` 已核准，最後執行（P1
  到 P3b 輸出逐位元組相同之後）。

仍待決：無。唯一的互動點是 R 的 push 前須告知 Miyago。
