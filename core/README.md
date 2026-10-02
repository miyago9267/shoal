# core

host 中立的來源，供 `tools/render.py` 產生各 host 的輸出。

- `roles.toml`：canonical role catalog。每個 role 標 `access`
  （read-only / write / verify）、`tier`（fast / standard / strong /
  frontier）與 `security`。不寫任何 model 名稱。
- `models.toml`：模型目錄。key 是 `vendor/name`，欄位有 `vendor`、
  `capability`（1-5）、`cost`（1-5）、`flags`。不寫任何 host 專屬的名稱。
  初版數值是校準到能重現現行配置，不是客觀量測。
- `tiers.toml`：每個 tier 的選模規則。`fast`、`standard`、`strong` 選
  capability 不低於 `min_capability` 的模型中 cost 最低者；`frontier`
  選 capability 最高者。同分依序比 cost 或 capability、再依 key，結果是
  確定的。
- `hosts/<host>/binding.toml` 的 `[models]` 宣告該 host 可用的模型與
  host 內名稱，resolver 只在這個集合內選；grok 不指定模型，用
  `selection = "inherit"`。effort、description、工具限制也在 binding。
- 手動覆寫優先於規則：`[roles.<name>].model` > `[tiers].<tier>` > 規則。
  `[tiers]` 與 role 的 `model` 只在要手動指定時才寫。手動指定不能繞過
  security 排除；`security = true` 的 role 被指定到帶旗標的模型時，
  render 直接失敗。
- `python3 tools/render.py --host <h> --explain` 印出每個 role 的 tier、
  候選模型、被排除的原因與結果。換模型的步驟見
  [docs/model-catalog.md](../docs/model-catalog.md)。
- host 專屬 role（例如 Claude 的 `Explore`、Codex 的 `sol-executor`）
  放在該 host 的 binding，不進 core。
- `mech-executor` 是 `fast` tier：Codex 的 fast 與 standard 選到不同
  model，`mech-executor` 與 `executor` 因此分開；Claude 的 fast 與
  standard 選到同一個 model，所以 Claude 的輸出不受影響。
- `security = true` 的 role 不會選到帶 `refuses_defensive_security` 旗標
  的模型（例如 Claude 的 fable，分類器會誤拒防禦性資安工作）。取代舊的
  `security_avoid_frontier` 開關。

policy 文字目前還在各 host 底下（例如 `hosts/claude/src/`），不在 core。
原因是 claude 和 codex 的 policy 已經分岔，先搬家並用 golden test
證明行為不變；要到 P5 才合併成 host 中立的 `core/policy/`。

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
