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

- `verifier` A1（Codex installer 不清舊名 role 檔）：FIX（v3.0.3）。`install/install.py`
  的完整與 `--roles-only` 模式會備份後移除位元組等於已發行 template 的 `mech-executor.toml`、
  `plan-verifier.toml`，改過的檔案不動並回報 drift；dry-run 只回報。
- A2（`watcher` 超過前景時限）：FIX，已加 `long-command-background` 條款。
- A3（`#direct` 在引用文字內也放行）：FIX（v3.0.3）。只算獨立 token（前面是開頭或空白、
  後面是結尾、空白或句末標點），fenced block 與行內 code 內不算；Python 與 TypeScript 共用
  `tests/fixtures/direct_token_vectors.json`。A4（prompt 與 tool 的 id 形狀不一致時
  `#direct` 失效）：DEFER，在真實 session 是否會發生未確認。
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

## 第四輪 live gate 與 v3.0.2（2026-10-10）

真實設定下 6 次（`results-pass4.json`）加 1 次補測與 1 次互動式對照：

- R1 對 Edit、Write 的 deny：兩次都觀察到（各擋三次後 main 改派 `shoal:applier`）。
- reviewer 下限：`shoal:verifier` 以 effort medium 派出一次，model 為 Opus 5.5。
- 長指令：main 兩次都直接派背景 `watcher`，沒有自己開背景 shell，所以 G4 的 deny 沒有
  機會觸發。
- 小功能派工 3 次過 2 次；沒過的那次 Jev 沒有分類，guard 不介入。
- `watcher` 盯 11 分鐘指令：v3.0.1 失敗（單次前景呼叫在時限被中斷）。v3.0.2 改成指令
  多久不確定時一律背景執行再輪詢；headless 補測中 `watcher` 有照做，但 session 在約
  10 分鐘時結束；互動式對照通過。`watcher` 檔 30 行、2573 bytes，在既有上限內，lock
  以 `delegation-default-3-0-2` 標記更新（Miyago 2026-10-10 核准）。

## 尚未驗證

- G4 在真實 session 的 deny（main 沒有嘗試開背景 shell）；`plan-critic` 與
  `security-reviewer` 的 effort 下限（實測中沒有被派出）。
- Plugin 的 `shoal:watcher` 在互動式 session 盯長指令（對照用的是一般 agent 加角色
  本文）；背景 role 遇到權限提示時的行為。
- 各 case 的重複性：多數只有 1 次。
- Jev 不給分類的回合（風險字、信心不足）R1 與 G5 不觸發，小功能會由 main 自己做。
- 其他 host 綁定新 role 與同一組條款：第二階段，另開 spec。

## 不再追加實測（2026-10-10）

Miyago 在 2026-10-10 決定停止付費的 live 實測，接受現有證據。上面「尚未驗證」是已知限制的
紀錄，不是待辦；之後若要補，另開 spec。

## v3.0.3 缺口清理（2026-10-10）

- A1、A3 見「處置」。
- agy 回報 `agents/applier`、`agents/plan-critic` 不是 symlink：原因是遷移的缺口，不是機器
  狀態誤報。`tools/sync_global.py` 移除指向本 repo 的舊名 role symlink，卻不補新名
  （skill 的舊名會改指新名，role 不會），而 `agy_link_problems` 對 dist 裡每個 role 都
  要求 symlink。v3.0.3 改成移除舊名後，新名不存在就補上指向 `hosts/agy/dist/agents/<新名>`
  的 symlink。這台機器的舊名連結已在先前的 `--apply` 移除，不會自動補；要執行
  `ln -s <repo>/hosts/agy/dist/agents/applier ~/.gemini/config/agents/applier` 與
  `plan-critic` 同樣一條。OpenCode 的 harness 副本不同仍未處理。
- `docs/assets/shoal-model-routing.svg` 的範例與 Claude 欄 scout 改為 haiku。
