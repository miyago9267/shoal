# delegation-default 進度

## S1–S7（完成，`1836f59`，v3.0.0）

- S1 scout haiku、executor medium；S2 改名與 `Explore` 移出清單；S3 effort 與類型標籤；
  S4 `watcher`、`researcher`、`plan-critic` 補漏；S5 預設派工與不變式；S6 guard R1 deny、
  G4、`#direct`；S7 版本與 lock。
- 驗證：unittest 全過；`verifier` 對 S1–S7 回 CONFIRMED，方向檢查 CONTINUE。
- live gate（`docs/benchmarks/delegation-default-gate/`）：第一輪 3/10。原因是 headless
  session 只拿到 bootstrap，完整條款在 skill 內沒被載入。把派工規則寫進 bootstrap
  （`CLAUSES.md` 的修訂段）後第二輪 8/9，剩 case C（三檔小功能 main 自己做）。
  S3、S4、S5 共用這兩輪的 20 次執行；S2、S6、S7 的驗收是測試與 render 檢查。

## G5（完成，`79a8a57`，v3.0.1）

- 真實設定下實測發現 main 用 shell 寫檔繞過 R1；補上 shell 寫檔的字面判斷。
- 第三輪 live gate（真實設定）：Jev 分類 `judgment`，shell 寫檔被 R1 deny，main 改派
  `shoal:applier`。case C 的同型題目通過，但只有 1 次，而且是 guard 擋下後才派工；只靠
  policy 文字時 C 兩輪都沒過。

## S8（完成，dotfile `bc25ccf`）

本機 Claude 改用 Plugin `shoal@shoal`，舊的 global role 檔、skill 副本與 guard hook 已
移除；新 session 的 role 顯示為 `shoal:<role>`，guard 每個事件只判一次。

## 處置

- `verifier` A1（Codex installer 不清舊名 role 檔）：DEFER。清除集中在
  `tools/sync_global.py`，`install/AGENT-INSTALL.md` 已寫明。本機已於 2026-10-10 跑過
  `sync_global.py --apply`，Codex、Grok、agy 的舊名 role 檔已移除、新名已安裝。要讓
  installer 自己清，另開修正。
- A2（`watcher` 超過前景時限）：FIX，已加 `long-command-background` 條款。
- A3（`#direct` 在引用文字內也放行）、A4（prompt 與 tool 的 id 形狀不一致時 `#direct`
  失效）：DEFER。A3 的錯誤方向是放行，不會擋住正常工作；A4 在真實 session 是否會發生
  未確認。
- executor 在 brief 之外的決定（corpus 與 manifest 內的 role 名稱、installer 的升級
  digest、各 host 一起升版、`render_codex` 支援 `omitted_roles`）：接受。

## 最終驗證（2026-10-10）

全新的驗證 agent 對 `79a8a57` 加文件變更回 CONFIRMED，方向檢查 CONTINUE，沒有 P0–P2：
unittest 1479 個全過、六個 render 檢查、lock、舊名掃描、lint 都通過；bootstrap 與
`CLAUSES.md` 一致；G5 以 45 個自選指令實測，唯讀指令沒有誤擋，Python 與 TypeScript
兩份偵測在 65 個指令上結果一致；本機 Plugin 為 3.0.1，內容與 repo 相同。

它列出的限制：目標不明的導向（`> $VAR`、`>$(mktemp)`）在已分類回合一律被擋；subagent
不受 G5 限制，`watcher`、`verifier` 的「不可改檔」只在工具層；agy 同步後回報
`agents/applier`、`agents/plan-critic` 不是 symlink，OpenCode 回報 harness 副本不同
（兩者未處理）。

## 尚未驗證

- R1 對 Edit／Write 在真實 session 的 deny（真實 session 只觀察到 shell 寫檔被擋）。
- `watcher` 的背景 shell 條款與背景 role 遇到權限提示時的行為。
- reviewer 類 role 的 effort 下限（實測中沒有派出 reviewer）；各 case 的重複性。
- G4 在真實 session 的 deny（只有單元測試、向量與手動實測）。
- Jev 的風險字篩選會跳過分類，那類回合 R1 與 G5 不觸發。
- 其他 host 綁定新 role 與同一組條款：第二階段，另開 spec。
