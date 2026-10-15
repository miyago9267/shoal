# OpenCode 安裝

## OpenCode

OpenCode host 的 installer 是 `hosts/opencode/plugin/install/install.sh`，有兩種
範圍。兩者都需要 `bun`，動作語意相同：`--enable` 安裝、`--disable` 移除、
`--rollback` 還原。

```bash
# 專案：寫進 <project>/.opencode/
sh hosts/opencode/plugin/install/install.sh --target DIR --enable

# 全域：寫進 OpenCode 的 config dir
sh hosts/opencode/plugin/install/install.sh --global --enable
sh hosts/opencode/plugin/install/install.sh --global --config-dir DIR --enable
sh hosts/opencode/plugin/install/install.sh --global --disable
sh hosts/opencode/plugin/install/install.sh --global --rollback
```

`--global` 安裝 shoal committed `HEAD` 的內容：五個 role 到 `<config-dir>/agents/`，
plugin 到 `<config-dir>/plugins/shoal-opencode.js`，`catalog.json` 與
`routing.json` 到 `<config-dir>/shoal/`。plugin 是在暫存目錄用
`git archive HEAD hosts/opencode`、`bun install --frozen-lockfile` 與 `bun build`
產生，不吃未 commit 的修改。`<config-dir>` 依序取 `--config-dir`、
`OPENCODE_CONFIG_DIR`、`~/.config/opencode`，必須已存在。

- manifest 與備份放在 `${XDG_STATE_HOME:-$HOME/.local/state}/shoal/opencode-global`，
  不寫進 config dir（config dir 可能被 dotfile 追蹤）。
- 目標路徑已有不是本 installer 安裝的檔案（內容與來源不同，且 manifest 沒有記錄或
  hash 不符）時中止並列出衝突，完全不寫入。
- `--disable`、`--rollback` 只在每個檔案的 hash 都與 manifest 相符時動作，否則整批
  不動；config dir 以 manifest 記錄的為準。`--rollback` 之後 installer 新增的檔案與
  它建立的 `agents/`、`plugins/`、`shoal/` 目錄都會消失。
- 安裝後檢查 `routing.json` 的候選 provider 是否出現在
  `<config-dir>/opencode.json` 的 `provider` keys 或 `enabled_providers`，沒有就
  警告（不中止）；只比對 key 名稱，auth 或環境變數型 provider 無法在這裡驗證。
- 目前目錄（或其 git root）已有專案的 `.opencode/plugins/shoal-opencode.js`
  時警告：全域與專案兩份 plugin 會同時載入。新版 plugin 以 `globalThis` 登記表避免
  重複註冊 `shoal_route`，舊版專案 plugin 沒有這個保護。

plugin 查找設定時，專案的 `.opencode/shoal/catalog.json` 存在就只用專案層，
否則改用全域 `<config-dir>/shoal/`（同一層內 `routing.json` 可省略，缺少時回退
native routing）。從 shoal 以外的目錄執行時，installer 需要在 shoal checkout 內
（它用 `git` 讀取 HEAD）。安裝後重新啟動 OpenCode。
