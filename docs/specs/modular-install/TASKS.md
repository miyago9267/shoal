# modular-install 任務

規格：[SPEC.md](./SPEC.md)。進度與結果：[PROGRESS.md](./PROGRESS.md)。

| Slice | 狀態 | Commit |
| --- | --- | --- |
| S1 模組清單與安裝入口 | 完成 | `41d3630`、`c017c42` |
| S2 guard chain 擴充點 | 完成 | `ef30603` |
| S3 `--without` 實作、chain 註冊、改名 | 完成 | `05bf86b`、`ac957e4` |
| S4 Claude 拆成兩個 plugin | 完成，live 已驗 | `9533ea1`、`0cba2da` |
| S5 README、INSTALL.md 的模組說明 | 完成 | 見下方 docs commit |
| issue #3 的成員介面 | 完成 | `40c95a1`、`641e1d1`、`bd568b1`、`296ac44` |
| PR #4 review 與 CI | 完成 | `d8af852`、`6ce52c3` |
| v3.8.1 相容檔 | 完成 | `4a06ddb` |

## S1

- [x] `install/modules.json` schema、`--list`、dry-run 預設（`41d3630`）
- [x] `sync_global.py` 讀 manifest，沒有時走推導（`41d3630`）
- [x] 模組推導改用 `install_hooks` 辨識 guard，判斷不出來視為已安裝（`c017c42`）

## S2

- [x] manifest 的 `chain`、依 `order` 升冪、第一個 deny 勝出、fail-open（`ef30603`）
- [x] Python 與 OpenCode TS 以共用 vectors 驗證一致（`ef30603`）
- [x] 以 fake 外部成員測試只靠設定接入（`ef30603`）

## S3

- [x] `--without dispatch-guard`、`codex-autoroute`、`claude-explore` 真的生效（`05bf86b`）
- [x] `--chain-add`／`--chain-remove`／`--list` 顯示 chain（`05bf86b`）
- [x] 內建 guard 註冊改名為 `shoal-dispatch-guard`，舊 id 原地遷移（`05bf86b`）
- [x] agy 舊群組只遷移 shoal 自己的、manifest 路徑規則與 guard 一致、有 chain 成員時保留 hook（`ac957e4`）

## S4

- [x] `claude-guard-plugin/` 與 `tools/render.py --host claude-plugin`，同一個 marketplace（`9533ea1`）
- [x] `claude_live_probe` 加 plugin-split 檢查案例（`0cba2da`）
- [ ] live：只裝 base 可派 role 且無 hook，再裝 guard 確認 hook 觸發（待補）

## issue #3 成員介面

- [x] `events`、`context`、`SHOAL_GUARD_HOST`／`SHOAL_GUARD_EVENT`、總時限、chain-only（`40c95a1`、`641e1d1`）
- [x] Codex 註冊升為 `shoal-dispatch-guard-v2`，INSTALL 同步（`bd568b1`）
- [x] `--chain-events`、numeric `version`、輸出讀取上限、任何事件的第一個 deny 即停（`d8af852`）

## v3.8.1

- [x] 基礎 plugin 保留 `hooks/shoal_guard.py` 相容檔，不註冊在 `hooks.json`（`4a06ddb`）

## S5

- [x] README 三語的「模組」段落、INSTALL.md 的模組章節更新
- [x] SPEC 的命名例外與 grep 驗收；移除 `chain.ts` 註解裡的外部專案名稱
