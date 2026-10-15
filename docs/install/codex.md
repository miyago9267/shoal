# Codex 安裝

`install/install.py` 會把 committed HEAD 的 marketplace 檔案匯出到 shoal 擁有的
`${XDG_DATA_HOME:-~/.local/share}/shoal/codex-marketplace`，再用
`codex plugin marketplace add` 登記該目錄；Codex 設定裡不會出現 checkout 路徑。
舊的 `<repo>/plugin` 登記會在下次安裝時被移除並改登記匯出目錄。

## 沒有 checkout 時的替代方式

Git 來源不會被安裝器自動選用，需要時自己執行：

```sh
codex plugin marketplace add miyago9267/shoal@<ref>
codex plugin add shoal-codex@shoal-codex
```

這需要網路；`<ref>` 請釘 tag 或 commit。
