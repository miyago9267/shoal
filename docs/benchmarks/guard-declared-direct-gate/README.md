# guard-declared-direct live gate（S4，v3.2.1）

規格：`docs/specs/guard-declared-direct/SPEC.md`。2026-10-12，shoal 68179d9，真實設定，
無分類檔（Claude 有一次例外，見限制）。結果在 `results.json`，prompt 在 `prompts/`。

## 方法

- 每個 case 一個拋棄式 repo（家目錄下，`git init`，小型 Python package：`src/text_utils.py`、
  `src/cli.py`、`tests/test_text_utils.py`，docstring 有一個 `retrun`）。guard 豁免暫存目錄，
  所以不能放在系統 temp。跑完刪除。
- Claude：`claude -p <prompt> --model opus --permission-mode acceptEdits
  --output-format stream-json --verbose --max-budget-usd 2`，在 repo 內執行。
- Codex：`codex exec -m gpt-5.6-sol --json --dangerously-bypass-hook-trust --skip-git-repo-check
  -s workspace-write <prompt> < /dev/null`。設定檔指定的 `gpt-6.1-sol` 被帳號拒絕（HTTP 400），
  第一次嘗試作廢（沒有任何 tool 呼叫），改用命令列 `-m`；設定檔沒有改。
- 證據：stream、`guard.jsonl` 在每次 run 期間新增的行、`turns/<session>.json`。
- 次數：7 次（上限 8），Claude 3 次 USD 1.26，Codex 4 次（1 次作廢）。prompt 都不含 `#direct`。

## 結果

| tool | case | 第一次寫入被擋 | deny 後的出口 | 分類 | 完成 |
|---|---|---|---|---|---|
| claude | CL-small | 否（先宣告） | 無 deny | declared | 是 |
| claude | CL-feature-1 | 否（先宣告） | 無 deny | declared | 是 |
| claude | CL-feature-2 | 否（先宣告） | 無 deny | declared | 是 |
| codex | CX-small | 是（apply_patch，R1） | 錯誤宣告、兩次派工失敗、再自己改 | other | 是 |
| codex | CX-feature-1 | 否（先派工） | 無 deny | other | 是 |
| codex | CX-feature-2 | 否（先派工） | 無 deny | other | 是 |

- Claude 三次的宣告都是 `: shoal-direct "..."` 單獨一次 shell 呼叫，理由：單檔錯字；
  兩個功能都是「寫 brief 比直接改貴」。guard 記 `declare` 後，其餘 Edit 都是 `declared`/allow；
  沒有 subagent。Claude 3 次的測試都通過，turns 為 4、13、10，USD 0.44、0.42、0.40。
- Codex 三次都是 main 派 `applier`／`sol-executor`，但兩個 role 都因帳號不支援其綁定模型而
  沒有啟動；guard 已把 spawn 記成 `dispatch`/allow，之後 main 用 `apply_patch` 自己完成
  （`dispatched`/allow）。CX-small 在這之前被 R1 擋一次，main 執行了不帶 `:` 的
  `shoal-direct "..."`（exit 127，不是宣告）。三次最後檔案與測試都符合要求。
- 分類為 `other`，不算 `delegated`（沒有 role 執行過），也不算 `declared`（沒有有效宣告）。

## 三個問題

1. 無分類時的 deny：Codex 有（1 次，CX-small，`apply_patch` R1 deny）。Claude 沒有觀察到：
   3 次 main 都在第一次寫入前先宣告，deny 路徑沒有在 live 走過，只有單元與手動證據。
2. deny 後：只有 Codex 發生一次。main 沒有照訊息宣告（寫成不帶 `:` 的指令），接著派工，
   派工失敗後自己改。沒有停下來問、也沒有卡住。
3. 宣告率：Claude 小改動 1/1、功能 2/2，全部宣告，所以規則在 Claude 上只留下紀錄，
   沒有改變功能類工作的行為（理由都是「brief 比直接改貴」）。Codex 有效宣告 0/3；
   功能 2/2 先嘗試派工，小改動被擋後才派工。

## 限制

- 每格 n=1，一個 fixture，不能算比率；Claude 沒有量到 deny。
- Codex 的 role 在這個帳號都不能啟動，所以「deny 後派工」無法完成，Codex 的結果不代表
  role 可用時的行為。用的是 `-m gpt-5.6-sol`，不是設定檔的模型。
- 帶 `--dangerously-bypass-hook-trust`（hook 登記今天更新，尚未在互動式 session 重新核准）。
- 疑似 guard 缺口：被拒絕啟動的 spawn 仍被記成 dispatch 並解鎖改檔（CX-small、CX-feature-1、
  CX-feature-2）。這不算 `#direct` 或宣告，也不是 role 實作；規格沒有定義 spawn 失敗的情形。
- CL-feature-2 有 Jev 的 `judgment` 分類檔；declare 模式下它不放寬，結果不受影響。
- Codex 的 deny 訊息文字不在 stream 內，無法確認 main 讀到的是哪一句。
