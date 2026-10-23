# core

host 中立的來源，供 `tools/render.py` 產生各 host 的輸出。

- `roles.toml`：canonical role catalog。每個 role 標 `access`
  （read-only / write / verify）、`tier`（fast / standard / strong /
  frontier）與 `security`，需要額外能力時加 `capabilities`（目前只有
  `"web"`）。不寫任何 model 名稱，也不寫任何 host 專屬的工具名稱。
- `models.toml`：模型目錄。key 是 `vendor/name`，欄位有 `vendor`、
  `capability`（1-5）、`cost`（1-5）、`flags`。不寫任何 host 專屬的名稱。
  初版數值是校準到能重現現行配置，不是客觀量測。
- `tiers.toml`：每個 tier 的選模規則。`fast`、`standard`、`strong` 選
  capability 不低於 `min_capability` 的模型中 cost 最低者；`frontier`
  選 capability 最高者。同分依序比 cost 或 capability、再依 key，結果是
  確定的。
- `hosts/<host>/binding.toml` 的 `[models]` 宣告該 host 可用的模型與
  host 內名稱，resolver 只在這個集合內選；grok 不指定模型，用
  `selection = "inherit"`。effort 也在 binding；description 在 `prompts/hosts/<host>/descriptions.md`。
- 手動覆寫優先於規則：`[roles.<name>].model` > `[tiers].<tier>` > 規則。
  `[tiers]` 與 role 的 `model` 只在要手動指定時才寫。手動指定不能繞過
  security 排除；`security = true` 的 role 被指定到帶旗標的模型時，
  render 直接失敗。
- `python3 tools/render.py --host <h> --explain` 印出每個 role 的 tier、
  候選模型、被排除的原因與結果。換模型的步驟見
  [docs/model-catalog.md](../docs/model-catalog.md)。
- host 專屬 role（例如 Claude 的 `Explore`、Codex 的 `sol-executor`）
  放在該 host 的 binding，不進 core；它們在 `[extra_roles.<name>]` 自己
  宣告 `access`（與選用的 `capabilities`），權限同樣由對應表推導。
- `applier` 是 `fast` tier 的快速執行器（小而有界的改動）。Codex 的 fast 與
  standard 選到不同 model，`applier` 與 `executor` 因此分開；Claude 的規則會讓兩者
  選到同一個 model，所以 Claude 的 `applier` 在 binding 手動 pin `haiku`。
- `watcher`（`verify`、`fast`）在背景跑指令、build、測試或追 CI 到結束，回摘要，
  不改檔；`researcher`（`read-only` 加 `web`、`strong`）查論文、外部文件與上游專案，
  回報把來源原文、推論、未驗證分開。兩者的回報都以 `status` 與 `suggested_next`
  結尾，只建議、不派工。五個 host 都綁定並安裝這兩個 role（spec D17）；其他 host 只提供 role，
  派工條款與 guard 規則仍只有 Claude 的 policy 渲染。
  `watcher` 在 Claude pin haiku；haiku 的 capability 低於 `fast` 的門檻，
  所以和 `scout` 一樣手動指定（見 Claude binding 的註解）。
- `plan-critic` 有第二種模式：brief 設 `mode: gaps` 時不回 READY／REVISE，
  回還沒被問到的需求、假設、風險與替代做法（條款 `gap-mode`）。這是 core 條款，
  所有使用 core 契約的 host 都會帶；要不要用它由 policy 決定，目前只有 Claude 的
  policy 會叫 main 這樣派。
- `security = true` 的 role 不會選到帶 `refuses_defensive_security` 旗標
  的模型（例如 Claude 的 fable，分類器會誤拒防禦性資安工作）。取代舊的
  `security_avoid_frontier` 開關。

## 權限由 access 與 capabilities 推導

role 只在 `roles.toml` 宣告 `access` 與 `capabilities`；各 host 的權限欄位
由該 host 的 `binding.toml` 對應表產生（規格見
[docs/specs/access-derivation/SPEC.md](../docs/specs/access-derivation/SPEC.md)）：

- `[access.<level>]`：這個存取等級在該 host 要輸出的權限欄位。binding 用到
  的每個等級都要有對應表；`write` 沒有欄位要輸出時寫空表。
- `[capabilities.<name>]`（選用）：role 宣告了某個 capability，binding 就必須
  有這張表（可以是空表，表示這個 host 沒有對應的開關）。list 欄位附加到
  access 表同名的 list（access 表沒有該 list 代表不受限，不輸出）；scalar
  欄位直接設定，與 access 表衝突時 render 失敗。
- `[roles.<name>]` 可以寫同名欄位當**覆寫**，以欄位為單位整個取代推導值。
  Claude 的 `tools` 與 `disallowedTools` 互斥，覆寫其中一個會丟掉另一個。
  覆寫只在現況無法由 access 加 capabilities 推導時才留，不為單一 role 發明
  capability。
- 驗證對推導後的結果做：read-only role 必須是 allowlist 且不含寫入工具
  （Claude、agy），Codex read-only 必須是 `sandbox_mode = "read-only"`，
  grok 必須是 `capability_mode = "read-only"`。覆寫不能繞過這些檢查。
- 各 host 的權限欄位：Claude `tools` / `disallowedTools`、Codex
  `sandbox_mode` / `web_search`、agy `tools`、grok `capability_mode`、
  OpenCode `required_capabilities`（模型能力需求，不是權限，仍沿用同一套
  對應表）。
- `--explain` 對每個 role 印出 `access`、`capabilities`、套用的對應表、
  覆寫與推導出的欄位。

orchestration policy 的條款在 `prompts/policy/`（見下一節）；目前只有 Claude 輸出
core 條款，其他 host 仍輸出 `hosts/<h>/src/` 內的 legacy 原文。規則共用是既定方向，
其他 host 逐 host 改為 core 的計畫見
[docs/specs/shared-rules/SPEC.md](../docs/specs/shared-rules/SPEC.md)；切換是逐 host
的 migration。

## prompts/：送進 model 的文字

所有會被送進 model context 的文字（role 條款、policy 條款、外框、addenda、role
description、relay 外殼、plugin 說明）只存在 `prompts/` 底下的 `.md`；TOML 只留
metadata（`core/roles.toml`、`models.toml`、`tiers.toml`、`vendors.toml`、
`core/policy/placeholders.toml`、各 host 的 `binding.toml`）。`prompts/` 不受
markdownlint 檢查（正文有超過 80 欄的行，換行位置就是輸出位元組）。

```text
prompts/
  roles/<role>.md                   # role 條款
  policy/<doc>.md                   # policy 條款
  hosts/<host>/
    addenda/<role>.md, policy-addenda/<doc>.md
    frames/<role>.md, default.md, policy-frames/<doc>.md
    descriptions.md                 # role description（claude、codex、agy、grok）
    relay/shell.md, relay/policy-addenda/<doc>.md   # 只有 claude
    text.md                         # render 需要的固定句子（只有 claude）
```

條款檔用 HTML comment 當 marker，一個 marker 之後到下一個 marker 之間、去掉頭尾空行
的內容就是 `text`（中間的空行與縮排逐字保留）：

```text
<!-- clause: <id> kind=<kind> [sep=paragraph|space|newline] [required] -->
<!-- addendum: <id> at=<anchor> [sep=<sep>] [join=<sep>] -->
<!-- description: <role> -->
<!-- text: <key> -->
```

- 第一個 marker 之前只允許空行；檔案不可含 CR；正文內任何一行以 `<!-- clause:`、
  `<!-- addendum:`、`<!-- description:`、`<!-- text:` 開頭都會被當成 marker，
  種類與檔案不符或格式不合就是錯誤。
- `sep` 預設 `paragraph`；`required` 只有 policy 條款可用。`id`、`kind`、`at` 的驗證與下面
  各節相同，loader 是 `tools/contracts.py` 的 `parse_markdown_*`。
- `text.md` 的值可含 `{{key}}` placeholder，由 render 代入（relay 的執行步驟用
  `{{timeout}}`（runner 的秒數）與 `{{bash_timeout_ms}}`（Bash 工具的毫秒數，render 計算））；
  `descriptions.md` 與 binding 內的 `description` 不可對同一個 role 並存。
- 改一句 prompt：編輯對應的 `.md`，執行 `python3 tools/render.py --host <host> --write`
  （claude 的 plugin 用 `--host claude-plugin`），diff 只會出現在 `prompts/` 與它的輸出。

## role 條款（prompts/roles）

role 的 prompt 文字正在從各 host 手寫的 `src/agents`（或 `src/roles`）統一到
core（規格見
[docs/specs/role-contracts/SPEC.md](../docs/specs/role-contracts/SPEC.md)）。
每個 host 在 binding 以 `role_text` 選來源：`"legacy"` 輸出 `src` 內的原文，
`"core"` 輸出 core 條款加該 host 的外框與補充。`[roles.<name>].role_text`
可以逐 role 覆寫；host 專屬 role（`extra_roles`）一律 legacy，不可設定。

- `prompts/roles/<role>.md`：host 中立的條款，順序即輸出順序。每個
  `<!-- clause: ... -->` 有 `id`（小寫英數加連字號）、`kind`，選用 `sep`，正文是 `text`。
  `text` 是逐字文字（可含換行），頭尾不可有空白；`sep` 是這個條款之後接
  什麼：`paragraph`（空行，預設）、`space`（同一行接續）、`newline`（換行，
  用於條列）。一個條款一條義務。`kind` 只能是 `identity`、`scope`、
  `boundary`、`procedure`、`escalation`、`verdict`、`severity`、`security`、
  `foreground`、`final-message`、`leaf`。條款文字不寫 host 專屬的工具、
  模型或機制名稱，`tests/test_role_contracts.py` 有檢查。
- `prompts/hosts/<h>/frames/<role>.md`（找不到則 `default.md`）：外框，例如
  frontmatter 之後的標題與前言；必須恰好有一個 `{{role_body}}`，條款與
  addenda 排好後放在那裡。沒有外框就只輸出條款。
- `prompts/hosts/<h>/addenda/<role>.md`：只在該 host 有意義的補充。每個
  `<!-- addendum: ... -->` 有 `id`、`at`，選用 `sep`，正文是 `text`。`at` 是 `start`、`end`、
  `after:<條款 id>`、`before:<條款 id>` 或 `replace:<條款 id>`（用 host 專屬
  措辭取代那個條款；沒寫 `sep` 時沿用被取代條款的）。同一個位置有多個
  addendum 時依檔案順序。選用 `join` 指定「前一段與這個 addendum 之間」的
  分隔（預設沿用前一段原本的 `sep`），用於把 host 的句子接在 core 段落結尾的
  同一行，core 本身在那裡是換段。
- `frames/` 與 `addenda/` 刻意放在 `hosts/` 之外（`prompts/hosts/<h>/`），
  不會被 passthrough 帶進 dist。
- core 會產生的輸出，`src/` 內不可有同路徑的檔案（`role_text = "core"` 的
  role 的 `src/agents/<role>.md` 或 `src/roles/<role>.md`，與
  `policy_text = "core"` 的 `[policy.documents]` 路徑）：這種檔案不會進 dist，
  改了也沒效果，render 會直接失敗並指名該路徑。
- 切到 `core` 的 host，每個 role 必須逐字包含每個未被 `replace` 的條款，
  每個 host 的 replace 清單由測試鎖定（新增 replace 要同時改測試）。
- 五個 host 都已經是 `core`：條款由 Codex 1.8.1 的原文切出，所以 Codex 的
  輸出與切換前逐位元組相同。各 host 專屬的句子放在各自的 `prompts/hosts/<h>/addenda/`；
  host 專屬 role（`Explore`、`sol-executor`）維持 `src/agents` 的原文；
  core role 的 legacy 原文已刪除，`role_text = "legacy"` 只剩 host 專屬 role 使用。
  對照表在 `docs/specs/role-contracts/MAPPING-*.md`。

## policy 條款（prompts/policy）

orchestration policy（bootstrap、skill、主 policy、擴充規則）以 Claude 的文字為
canonical，切成 host 中立的條款（規格見
[docs/specs/core-policy/SPEC.md](../docs/specs/core-policy/SPEC.md)）。組裝沿用
role 條款的機制（`tools/contracts.py` 的 `compose`、`load_frame`、
`load_addenda`），不另有一套組裝器。

- `prompts/policy/<doc>.md`：一份輸出文件一個檔案（`bootstrap`、`skill`、
  `orchestration`、`extensions`），格式同 `prompts/roles`（`id`、`kind`、正文、
  選用 `sep`），另有選用的 `required` 旗標。條款 id 跨文件唯一。`kind` 只能是
  `heading`、`invariant`、`routing`、`gate`、`dispatch`、`verification`、
  `recovery`、`authority`、`mechanics`、`extension`（`contracts.POLICY_KINDS`）；
  role 條款不接受 `required`。
- `required` 的條款（named-role 豁免、risk trigger 與核准、security-reviewer 到
  security-executor 的路徑、destructive／external 確認、extension 不擴權）不可被
  `omit`，也不可被 addendum `replace:`，render 直接失敗。集合鎖在
  `tests/test_core_policy.py` 的 `EXPECTED_REQUIRED`。
- host 專屬的名稱（派工工具、問答工具、shell、參數寫法、文件檔名）不寫在條款裡，
  用 `{{key}}` placeholder。詞彙在 `core/policy/placeholders.toml`；條款用到詞彙外的
  key、詞彙內的 key 沒人用、或 host 少給 key 都會失敗。代入是單次 regex：未知 key
  或格式不合的 `{{` 報錯，值不得含 `{{` 或換行。條款文字同樣不得含
  `HOST_SPECIFIC_TERMS`（`tests/test_role_contracts.py`）。
- binding 的 `[policy]`：
  - `policy_text = "legacy" | "core"`：與 `role_text` 相同的開關，`legacy` 輸出 src
    原文，是逐 host 的 rollback。目前只有 Claude 是 `core`，其餘四個是 `legacy`；
    只有 Claude 的 renderer 支援 `core`，其他 host 設 `core` 會失敗。這個限制保留到
    shared-rules 的 S4 起逐 host 開放（計畫見 `docs/specs/shared-rules/SPEC.md`）。
  - `omit = [{ id, reason }]`：該 host 省略的條款，每項都要有理由；未列出的條款一律
    輸出。整份文件的條款都被省略（且沒有 addendum）時，該文件不輸出。
  - `[policy.placeholders]`：詞彙內每個 key 的值。
  - `[policy.documents]`：core 文件對應的輸出路徑（相對 dist）。
- `prompts/hosts/<h>/policy-frames/<doc>.md`（找不到則 `default.md`）：外框，必須恰好有一個
  `{{role_body}}`；`prompts/hosts/<h>/policy-addenda/<doc>.md`：host 專屬補充，`at` 語法與
  role addenda 相同，不可掛在被 omit 的條款上。兩者不會被帶進 dist。每個 host 的 omit 與 replace 清單鎖在
  `EXPECTED_POLICY_OMITS`、`EXPECTED_POLICY_REPLACES`。
- 預覽（不論 `policy_text`、不碰 dist）：`python3 tools/render.py --host claude
  --policy-preview DIR` 把 core 組出來的文件寫到 DIR，用來和 legacy 對照；
  `--explain-policy` 印出每個條款是 core、omitted 或 replaced。對照表放在
  `docs/specs/core-policy/equivalence/<host>.md`。

## 新增 host（generic-md）

輸出是「每個 role 一個 Markdown 檔加 YAML frontmatter」的 host，不需要寫
renderer（規格見
[docs/specs/new-host/SPEC.md](../docs/specs/new-host/SPEC.md)，步驟見
[docs/new-host.md](../docs/new-host.md)）：

- binding 設 `renderer = "generic-md"` 與 `role_text = "core"`，用 `[output]`
  宣告輸出路徑與 frontmatter 欄位（來源、編碼）。`tools/render.py` 從
  `hosts/*/binding.toml` 探索這類 host，`--host <name>` 不用改程式。
- role 層級的欄位（例如 effort）用來源 `role.<key>` 讀
  `[roles.<name>].<key>`，key 要列在 `[output].role_fields`。
- 權限欄位要在 `[output.permissions.<欄位>]` 宣告型別（`list`、`scalar`、
  `map`），之後 `[access.*]`、`[capabilities.*]` 與 role 覆寫才能使用，
  推導規則與上一節相同。
- 不支援 `[extra_roles]`；既有五個 host 維持各自的 renderer，輸出不變。
- `python3 tools/new_host.py <name>` 產生骨架；
  `tests/test_generic_hosts.py` 自動檢查每個 generic-md host 的 `--check`
  與條款逐字出現。這類 host 的回歸基準是 committed dist 加 `--check`。

## 各 host 的 role 子集與 effort

- host 沒有的 role 要在 binding 用 `omitted_roles = [...]` 明列
  （例如 opencode 沒有 `applier`、`plan-critic`，所以列入 `omitted_roles`）。
  `render_codex` 也遵守 `omitted_roles`。
  驗證規則：`roles.toml` 的每個 role，binding 要嘛有
  `[roles.<name>]`，要嘛列在 `omitted_roles`；兩者不可同時出現。
- host 不支援 effort 時（agy），binding 設 `supports_effort = false`；
  render 不輸出 effort 欄位，role 也不可設 effort。

## 產出物不做 Markdown lint

`hosts/*/src`、`hosts/*/dist` 裡的 Markdown 是從各 host
原始 repo 逐位元組搬來的文字與其 render 產出，必須和來源一致，
因此排除在 `lint:md` 之外；Codex 的 dist（`templates/`）維持原本的 lint。
