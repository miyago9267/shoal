# 登記新模型與換模型

模型由 `core/tiers.toml` 的規則在 host 的可用模型內選出，不手寫在
binding。規則細節見 [core/README.md](../core/README.md)。

## 登記新模型

1. 在 `core/models.toml` 加一筆，key 用 `vendor/name`：

   ```toml
   [models."examplevendor/example-model"]
   vendor = "examplevendor"
   capability = 5
   cost = 4
   ```

   `capability`、`cost` 是 1-5 的相對級距，只在同一個 host 內比較。
   分類器會誤拒防禦性資安工作的模型，加
   `flags = ["refuses_defensive_security"]`。
2. 在要使用它的 `hosts/<host>/binding.toml` 的 `[models]` 加一行，
   值是它在該 host 的名稱（OpenCode 是 `{ provider, model }`）。
3. 預覽：`python3 tools/render.py --host <host> --explain`，確認哪些
   role 會改選它。
4. 寫入：`python3 tools/render.py --host <host> --write`，再跑
   `python3 -m unittest discover -s tests`。

## 換掉舊模型

在 `[models]` 移除舊的、加入新的，其餘同上。舊模型沒有 host 使用後，
才可以從 `core/models.toml` 刪除。

## 注意

- 只有 `--explain` 列出的 role 會改變；dist 與 golden 的 diff 要逐一
  review，這是 catalog 數值的 review 關卡。
- 想固定某個 role 或 tier，才寫 `[roles.<name>].model` 或 `[tiers]`；
  手動指定優先於規則，`--explain` 會標示。但不能繞過 security 排除：
  `security = true` 的 role 被指定到帶旗標的模型時，render 以 exit 2 失敗。
- `[root].model`（Codex）、`[extra_roles.*].model` 是 host 專屬的手動
  指定，不經規則。
- 沒有模型滿足某個 role 時，render 以 exit 2 失敗並指出 host 與 role。

## 本機覆寫（只有 Claude host）

只有自己帳號能用的模型（例如 CVP 提供的 Mythos）不寫進 repo，改寫在
`${XDG_CONFIG_HOME:-~/.config}/shoal/claude.local.toml`：

```toml
[roles.security-reviewer]
model = "claude-mythos-5-2"
```

- `shoal_install.py --update --apply` 匯出 HEAD 後，改寫安裝內容中該 role 的
  `model:` 行，輸出一行 `overlay: applied (...)`；repo 的 dist 與 golden 不變。
- 只接受 `[roles.<name>].model`。role 不存在、出現其他 key、model 格式不合法，
  或把帶 `refuses_defensive_security` 的模型指定給 security role，update 都會失敗，
  不會安裝。
- 模型無法使用時，Claude Code 會依 `fallbackModel` 改用其他模型，只在回覆前加一行
  提示，不會報錯。看到這行提示時，該次 review 結果不可採用。
