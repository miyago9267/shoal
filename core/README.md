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
  `selection = "inherit"`。effort 與 description 也在 binding。
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
- `mech-executor` 是 `fast` tier：Codex 的 fast 與 standard 選到不同
  model，`mech-executor` 與 `executor` 因此分開；Claude 的 fast 與
  standard 選到同一個 model，所以 Claude 的輸出不受影響。
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

policy 文字目前還在各 host 底下（例如 `hosts/claude/src/`），不在 core。
原因是 claude 和 codex 的 policy 已經分岔，先搬家並用 golden test
證明行為不變；要到 P5 才合併成 host 中立的 `core/policy/`。

## role 條款（core/contracts）

role 的 prompt 文字正在從各 host 手寫的 `src/agents`（或 `src/roles`）統一到
core（規格見
[docs/specs/role-contracts/SPEC.md](../docs/specs/role-contracts/SPEC.md)）。
每個 host 在 binding 以 `role_text` 選來源：`"legacy"` 輸出 `src` 內的原文，
`"core"` 輸出 core 條款加該 host 的外框與補充。`[roles.<name>].role_text`
可以逐 role 覆寫；host 專屬 role（`extra_roles`）一律 legacy，不可設定。

- `core/contracts/<role>.toml`：host 中立的條款，順序即輸出順序。每個
  `[[clause]]` 有 `id`（小寫英數加連字號）、`kind`、`text`，選用 `sep`。
  `text` 是逐字文字（可含換行），頭尾不可有空白；`sep` 是這個條款之後接
  什麼：`paragraph`（空行，預設）、`space`（同一行接續）、`newline`（換行，
  用於條列）。一個條款一條義務。`kind` 只能是 `identity`、`scope`、
  `boundary`、`procedure`、`escalation`、`verdict`、`severity`、`security`、
  `foreground`、`final-message`、`leaf`。條款文字不寫 host 專屬的工具、
  模型或機制名稱，`tests/test_role_contracts.py` 有檢查。
- `hosts/<h>/frames/<role>.md`（找不到則 `default.md`）：外框，例如
  frontmatter 之後的標題與前言；必須恰好有一個 `{{role_body}}`，條款與
  addenda 排好後放在那裡。沒有外框就只輸出條款。
- `hosts/<h>/addenda/<role>.toml`：只在該 host 有意義的補充。每個
  `[[addendum]]` 有 `id`、`at`、`text`，選用 `sep`。`at` 是 `start`、`end`、
  `after:<條款 id>`、`before:<條款 id>` 或 `replace:<條款 id>`（用 host 專屬
  措辭取代那個條款；沒寫 `sep` 時沿用被取代條款的）。同一個位置有多個
  addendum 時依檔案順序。選用 `join` 指定「前一段與這個 addendum 之間」的
  分隔（預設沿用前一段原本的 `sep`），用於把 host 的句子接在 core 段落結尾的
  同一行，core 本身在那裡是換段。
- `frames/` 與 `addenda/` 刻意放在 `src/` 之外，不會被 passthrough 帶進 dist。
- 切到 `core` 的 host，每個 role 必須逐字包含每個未被 `replace` 的條款，
  每個 host 的 replace 清單由測試鎖定（新增 replace 要同時改測試）。
- 目前只有 Codex 是 `core`：七個共同 role 的條款由 Codex 1.8.1 的原文切出，
  Codex 專屬的句子（模型綁定、reasoning effort、`semantic_adjudication`）在
  `hosts/codex/addenda/`，所以 `templates/agents/*.toml` 與切換前逐位元組相同。
  `sol-executor` 是 Codex 專屬 role，維持 `src/agents` 的原文。其他 host 仍是
  `legacy`。

## 新增 host（generic-md）

輸出是「每個 role 一個 Markdown 檔加 YAML frontmatter」的 host，不需要寫
renderer（規格見
[docs/specs/new-host/SPEC.md](../docs/specs/new-host/SPEC.md)，步驟見
[docs/new-host.md](../docs/new-host.md)）：

- binding 設 `renderer = "generic-md"` 與 `role_text = "core"`，用 `[output]`
  宣告輸出路徑與 frontmatter 欄位（來源、編碼）。`tools/render.py` 從
  `hosts/*/binding.toml` 探索這類 host，`--host <name>` 不用改程式。
- 權限欄位要在 `[output.permissions.<欄位>]` 宣告型別（`list`、`scalar`、
  `map`），之後 `[access.*]`、`[capabilities.*]` 與 role 覆寫才能使用，
  推導規則與上一節相同。
- 不支援 `[extra_roles]`；既有五個 host 維持各自的 renderer，輸出不變。
- `python3 tools/new_host.py <name>` 產生骨架；
  `tests/test_generic_hosts.py` 自動檢查每個 generic-md host 的 `--check`
  與條款逐字出現。這類 host 不建 golden，committed dist 加 `--check` 即為
  回歸基準。

## 各 host 的 role 子集與 effort

- host 沒有的 role 要在 binding 用 `omitted_roles = [...]` 明列
  （例如 opencode 沒有 `mech-executor`、`plan-verifier`）。
  驗證規則：`roles.toml` 的每個 role，binding 要嘛有
  `[roles.<name>]`，要嘛列在 `omitted_roles`；兩者不可同時出現。
- host 不支援 effort 時（agy），binding 設 `supports_effort = false`；
  render 不輸出 effort 欄位，role 也不可設 effort。

## 產出物不做 Markdown lint

`hosts/*/src`、`hosts/*/dist`、`tests/golden` 裡的 Markdown 是從各 host
原始 repo 逐位元組搬來的文字與其 render 產出，必須和來源一致，
因此排除在 `lint:md` 之外；Codex 的 dist（`templates/`）維持原本的 lint。
