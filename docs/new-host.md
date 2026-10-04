# 新增 host

輸出格式是「每個 role 一個 Markdown 檔加 YAML frontmatter」的工具，不用寫
程式碼：role 文字、模型與權限都由 core 推導，格式由 binding 的 `[output]`
宣告（規格見 [specs/new-host/SPEC.md](./specs/new-host/SPEC.md)）。TOML 或
JSON 這類格式，仍要在 `tools/render.py` 寫專屬 renderer。

## 步驟

1. 產生骨架：`python3 tools/new_host.py <name>`，建立
   `hosts/<name>/binding.toml`、`frames/default.md` 與 `addenda/`。
   名稱是小寫英數加連字號，已存在的 host 不會被覆寫（exit 2）。
2. 在 `binding.toml` 填 `[models]`：key 是 `core/models.toml` 的
   `vendor/name`，值是它在這個 host 的名稱。沒填之前 render 會 exit 2。
3. 把 `[access.*]` 的範例工具名稱換成這個 host 的實際名稱，並填每個
   `[roles.<role>].description`。
4. 預覽：`python3 tools/render.py --host <name> --explain`。
5. 寫入並檢查：`--write`，再 `--check`，最後跑
   `python3 -m unittest discover -s tests`（探索式測試會自動涵蓋新 host，
   不用新增測試檔）。dist 在 `hosts/<name>/dist/`，要 commit。

## `[output]` 宣告

```toml
[output]
path = "agents/{role}.md"        # 每個 role 一個檔，必須有一個 {role}

[[output.frontmatter]]           # 依宣告順序輸出
key = "tools"
source = "tools"                 # name、description、model 或權限欄位
encoding = "comma-list"

[output.permissions.tools]       # 權限欄位先宣告型別
type = "list"                    # list、scalar 或 map
```

- `source` 與 `value` 擇一：`value` 是固定值（例如 `value = "low"`）。
- 權限欄位來自 `[access.*]`、`[capabilities.*]` 與 role 層級的覆寫，沒有
  這個欄位的 role 就不輸出該行。未宣告型別的欄位寫進對應表會 exit 2。
- 編碼要和來源型別相符：`scalar`、`folded` 接字串，`comma-list`、
  `block-list` 接 list，`nested-map` 接 map（值都是字串）。
- `block-list`、`nested-map`、`folded` 可設 `indent`（預設 2）；`folded`
  另可設 `width`（含縮排，會重排文字；省略則沿用原文的換行）。
- `scalar` 不加 YAML 引號；含冒號加空白、空白加井字號，或以特殊字元開頭的值
  會被拒絕，改寫文字或改用 `folded`。

## 限制

- 不支援 `[extra_roles]`（host 專屬 role）與 `role_text = "legacy"`。
- frontmatter 沒有 role 層級的來源，所以 effort 這類每個 role 不同的欄位只能
  寫固定值。
- role 的外框是 `frames/default.md`（要恰好一個 `{{role_body}}`），host
  專屬的句子寫在 `addenda/<role>.toml`，見 [core/README.md](../core/README.md)。
- 不建 golden：committed dist 加 `--check` 就是回歸基準。
- 安裝方式不由工具產生，寫在這個 host 自己的文件。
