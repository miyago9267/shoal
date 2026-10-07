---
title: shoal 獨立成新產品（去除 pilotfish 命名）
status: approved
approved_by: Miyago
created: 2026-10-07
updated: 2026-10-07
---

<!-- markdownlint-disable MD025 -->

# shoal 獨立成新產品（去除 pilotfish 命名）

## Background

Miyago 2026-10-07 決定：shoal 直接作為新產品，所有安裝路線與命名都是新的，
pilotfish 只保留 credit 給原作。現況（main `5c2a7d1` 查證）：

- 本機五個 host 的全域安裝都來自 shoal，pilotfish 系列 repo 只做上游協作
  （記憶 `shoal-vs-pilotfish-roles`），但安裝出去的東西仍叫 pilotfish：
  skill `pilotfish-orchestration`、Codex plugin `pilotfish-codex` 與
  `pilotfish-jev-router`、hook `pilotfish_autoroute_gate.py`、Grok 的
  `pilotfish-grok`、agy 的 `pilotfish-agy`、OpenCode 的 `pilotfish-opencode` 與
  tool `pilotfish_route`、marker（`<!-- pilotfish v... -->`、
  `<!-- pilotfish-codex:begin -->` 等）、環境變數 `PILOTFISH_*`（10 個以上）。
- repo 內（排除 `docs/specs` 與 golden）1092 行、30 個檔名含 pilotfish。
- prompt lock 有 7 個 `required_fragments` 含 Pilotfish 字樣，Codex 與 Claude 的
  受保護 surface 路徑也含 pilotfish。
- dotfile 有約 20 個檔案引用（skill 同步、auto-update、harness、jev-route、
  generated 的 AGENTS／GEMINI 等）。

## Requirements (EARS)

- **N1（改名對照表）**：所有產品面的名稱 shall 依 `RENAME.md` 的對照表改名；
  對照表是唯一來源，測試檢查 repo 內產品面不再出現舊名。
- **N2（範圍）**：產品面包含：會被安裝或載入的檔案與目錄名、marker、skill／
  plugin／tool／hook 名稱、環境變數、policy 與 role 文字中的產品名、README、
  INSTALL、安裝腳本輸出。
- **N3（保留的歷史與 credit）**：以下不改：`docs/specs/`、`docs/benchmarks/`、
  `docs/plans/` 的歷史紀錄、CHANGELOG 過去版本的段落、
  `hosts/codex/CHANGELOG.md` 的歷史段落、上游 repo 的真實名稱與網址。credit
  集中在 README「來源與致謝」、`LICENSE`、`ATTRIBUTION.md`、`upstream.lock`。
- **N4（不留舊名相容層）**：新產品不接受 `PILOTFISH_*` 環境變數與舊 marker
  作為設定；舊名只用於 N5 的遷移辨識。
- **N5（遷移已安裝的環境）**：每個 installer 與 `tools/sync_global.py` shall
  辨識自己先前以舊名安裝的檔案（marker、hash 或安裝紀錄），移除後以新名安裝；
  不是 shoal 安裝的舊名檔案一律不動並回報。
- **N6（版本重新起算）**：產品版本 `2.0.0`；各 host 的 `VERSION` 一律改為
  `2.0.0`（agy 新增 VERSION 檔，OpenCode plugin 的 package.json 同步），
  不再沿用上游衍生的版本號；上游版本只記在 `upstream.lock`。
- **N7（lock）**：受保護 surface 的路徑與內容變動，走一次 lock renewal：
  `LOCK.json` 更新 path、mirrors 與 `required_fragments`（surface id 不含舊名，
  不改），每個內容變動的 surface 帶 `migration`（`equivalence` 指向
  `RENAME.md`），以帶 `Lock-Renewal: approved` trailer 的單一 commit 推上 main。
  路徑改名的 surface 在 validator 會走「新增」分支、跳過預算與 migration，所以
  另以 rename-aware 檢查證明等價：base 的舊路徑內容套用 RENAME 的替換（加上版本
  號改為 2.0.0）後，必須與新路徑逐位元組相同。
- **N8（使用者本機的改動）**：Codex 本機的 `pilotfish_autoroute_gate.py` 是使用者
  自改的實驗版本（`gpt-6.1-sol`），遷移時保留為備份檔、不再註冊，改用 repo 版的
  `shoal_autoroute_gate.py`；Codex 的新 hook 路徑需要使用者再以 `/hooks`
  核准一次。

## Non-goals

- 不改 role 名稱（scout、executor 等）、選模、權限與 guard 規則。
- 不改歷史文件與已發布的 tag、release。
- 不動 pilotfish 系列 repo（上游協作用）。

## Decisions

1. **新名稱的形狀**：`shoal` 加 host 後綴（`shoal-claude`、`shoal-codex`、
   `shoal-grok`、`shoal-agy`、`shoal-opencode`），skill 為
   `shoal-orchestration`，tool 為 `shoal_route`，環境變數前綴 `SHOAL_`。
   完整對照見 `RENAME.md`。
2. **一次切換**：repo 的改名與 installer／`sync_global.py` 的遷移邏輯放在同一個
   commit（同時是 lock renewal commit）。dotfile 的每日 hook 以本機 HEAD 執行
   `sync_global.py --apply`，若改名先於遷移落地，新名會裝在舊名旁邊（重複的
   Codex gate、兩個 OpenCode plugin、兩份 Grok rules）。
3. **遷移由 shoal 負責**：installer 與 `sync_global.py` 處理舊名移除；dotfile
   只更新它自己持有的檔案（skill 同步路徑、auto-update、harness、文件）。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| R0 | 由 main 撰寫 `RENAME.md` 對照表 | 對照表涵蓋盤點出的每個舊名；plan-verifier 審過 |
| R1 | 同一個 commit：repo 改名、版本 2.0.0、lock renewal 與 migration、installer 與 `sync_global.py` 的遷移 | 六個 render `--check`、全套測試、`validate_prompt_lock --allow-lock-update` ok；rename-aware 檢查對 7 個改路徑的 surface 為 0 diff；產品面舊名掃描（RENAME「掃描範圍」）為 0；N3 範圍未變；temp home 預置舊名安裝，對該 commit 跑 `sync_global.py` 的計畫只含「移除舊名＋安裝新名」，無重複 hook 群組或 plugin；套用後只剩新名、非 shoal 檔案不動、再跑一次無變更 |
| R2 | 本機遷移與 dotfile 更新 | 五個 host 實際遷移；`sync_global.py` 回報 up-to-date；dotfile 產品面不再引用舊名（備份檔與歷史除外） |
| R3 | 發布 v2.0.0 | CI 綠；tag 與 release；Plugin 以 `#v2.0.0` 安裝驗證 |

## Rollback

- repo：revert R1 commit（同為 lock renewal，revert 需另一個帶 trailer 的
  migration commit）。本機會由每日 hook 依 revert 後的 HEAD 再遷移回去，因此
  revert 前先停用 auto-update 或先手動 rollback 各 host。
- 本機：installer 的備份目錄還原；dotfile revert 對應 commit。

## Open questions

（無；Miyago 已決定方向，名稱形狀見 Decision 1。）
