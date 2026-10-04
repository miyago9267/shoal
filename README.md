# shoal

一份 host 中立的 role catalog，render 成 5 個 host 的 agent 設定：
Claude Code、Codex CLI、Gemini/agy、Grok Build、OpenCode。

shoal 只維護一份 role 定義（`scout`、`executor`、`verifier` 等）。每個 host
用自己的 binding 決定 model、effort，並把 role 的存取等級對應成該 host 的權限欄位，再由 renderer 產生該 host
要安裝的檔案。產物有 golden 測試，改動一律看得到 diff。

## 目錄結構

```text
core/roles.toml            host 中立的 role 定義
hosts/<host>/binding.toml  可用 model、access 對應的權限、effort
hosts/<host>/src/          該 host 的 policy 與 skill 原文
hosts/<host>/dist/         render 產出，已 commit（codex 產出在 templates/）
tools/render.py            renderer 與 --check
tools/install_grok.py      由 committed HEAD 安裝 grok host（預設 dry-run）
tools/check_links.py       文件相對連結檢查
tests/golden/<host>/       各 host 的逐位元組基準
upstream.lock              各 host 對應的上游與版本
```

`hosts/codex/` 另含 `VERSION`、`README.md`、`CHANGELOG.md`，是 Codex host 自己
的文件。安裝腳本 `install/`、`INSTALL.md` 留在 repo 根目錄。

## render

```bash
# 檢查：dist 與 core、binding、src 是否一致，不一致 exit 1
python3 tools/render.py --host claude --check

# 寫入：重新產生該 host 的 dist
python3 tools/render.py --host claude --write
```

`--host` 可選 `claude`、`codex`、`agy`、`grok`、`opencode`，以及 binding 設
`renderer = "generic-md"` 的 host。修改 core 或 binding 後先 `--write`，再跑
`python3 -m unittest discover -s tests` 確認 golden 差異是預期的。

## 新增 host

輸出格式是「每個 role 一個 Markdown 檔加 frontmatter」的工具，不用寫程式碼：
`python3 tools/new_host.py <name>` 產生骨架，填 `[models]` 與工具對應表後
`--write`。步驟見 [docs/new-host.md](./docs/new-host.md)。

## 安裝入口

| Host | 目前的安裝方式 |
| --- | --- |
| Codex CLI | [INSTALL.md](./INSTALL.md)，腳本在 `install/install.sh` |
| Claude Code | 取用 `hosts/claude/dist`，由 dotfile auto-update 安裝 |
| Gemini/agy | `hosts/agy/dist`，由 dotfile `setup_gemini.sh` 連結 |
| Grok Build | `python3 tools/install_grok.py`（預設 dry-run，`--apply` 才寫入），見 [INSTALL.md](./INSTALL.md#grok-build) |
| OpenCode | `hosts/opencode/plugin/install/install.sh --target DIR --enable` |

Claude Code、Gemini/agy 的安裝步驟仍依賴 dotfile 的腳本；Grok Build 由
`tools/install_grok.py` 安裝 agents、roles、rules 與原生 hooks，不再手動複製。

## 版本

| 項目 | 版本 |
| --- | --- |
| shoal（產品） | 1.1.0 |
| codex host | 1.8.1（`hosts/codex/VERSION`） |
| claude host | 1.4.2-claude.1 |
| agy host | 0.1.0 |
| grok host | 1.0.6-shoal.1（`hosts/grok/VERSION`，衍生自上游 v1.0.6） |
| opencode host | 以 `hosts/opencode/plugin/package.json` 為準 |

產品版本記在根目錄 `VERSION`，各 host 版本另外維護，互不連動。

## 驗證

```bash
python3 -m unittest discover -s tests
python3 tools/check_links.py
bun install --frozen-lockfile && bun run lint:md
```

## 來源與致謝

shoal 衍生自 [Nanako0129/pilotfish](https://github.com/Nanako0129/pilotfish)。
grok host 的 orchestration rules 與 agent 原文取自
[Nanako0129/pilotfish-grok](https://github.com/Nanako0129/pilotfish-grok)
v1.0.6，shoal 加上 core 條款、原生 hooks 與 installer；`upstream.lock` 記錄版本。
codex host 原本是 `miyago9267/pilotfish-codex`，v1.0.0 起併入本 repo；
v1.0.0 之前的 pinned ref 仍在
[pilotfish-codex](https://github.com/miyago9267/pilotfish-codex)，安裝時請用
該 repo 名稱。上游 Pilotfish 的著作權與授權聲明沿用，見 `LICENSE`。

## 已知限制

- 各 host 的 policy 文字尚未合併成一份，目前只有 role 與 binding 共用（規劃中）。
- 只有 Codex 與 grok 有 shoal 自己的 installer；Claude Code、agy、OpenCode 的
  安裝仍在 dotfile 或 host 的 plugin。

Codex host 的完整說明與歷史紀錄在 [hosts/codex/README.md](./hosts/codex/README.md)
與 [hosts/codex/CHANGELOG.md](./hosts/codex/CHANGELOG.md)。
