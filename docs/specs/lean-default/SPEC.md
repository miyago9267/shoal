# lean-default：保留 role 分工，壓低小工作的成本與延遲

狀態：Miyago 2026-10-16 核准。

## Background

2026-10-16 的 A/B benchmark（`bench/ab/run_ab.py`，Sonnet 5.5 為 main）：

| 任務組 | baseline | shoal | shoal-fast（prompt 加 `#fast`） |
| --- | --- | --- | --- |
| v1 小任務 8×3 | 21/24、$0.083、13.5s | 21/24、$0.151、41.9s | 21/24、$0.158、67.7s |
| v2 多步驟 8×2 | 16/16、$0.150、127s | 14/16、$0.331、219s | 15/16、$0.258、119s |

觀察（不是結論）：

1. 品質沒有提升；成本 1.7–2.2 倍，小任務時間約 3 倍。
2. `#fast` 只放寬 guard，條款仍叫 main 派工，所以沒變快。
3. 每次 hook 呼叫 0.3–0.45 秒（guard 本身約 0.1 秒，其餘是 pyenv
   的 `python3` shim 與 guard chain 成員）；一個任務數十次 hook。

## Goal

在維持「main 判斷整合、role 做事」分工的前提下，讓簡單工作的成本與時間
接近 baseline，品質不低於 baseline。不採「main 自己改檔」為預設。

## Principles

1. 分工不變：改檔仍由 role 做；`#direct` 照舊是唯一讓 main 改檔的出口。
2. 簡單工作走最便宜的 lane：`[fast]` applier（Claude 上是 haiku）、
   effort `low`、短 brief、不排 plan-critic 或 verifier。
3. 嚴謹路線只在觸發條件時啟動，條件與現在相同。
4. 每次 hook 的額外延遲要能量測，並有目標值。

## Decisions（附建議）

| # | 問題 | 建議 |
| --- | --- | --- |
| D1 | `#fast` 的意思 | 改為「整個 session 走輕量 lane」：簡單工作派 haiku applier、effort low、跳過選配審查；main 仍不改檔。main 改檔只留給 `#direct` |
| D2 | 什麼算簡單工作 | 單一目的、範圍已知（檔案或 symbol 已點名）、不碰觸發條件、預期 10 分鐘內完成。不設行數或檔數門檻（pilotfish 原則：不用數字門檻擋派工） |
| D3 | 輕量 lane 的 brief | 目標、檔案、完成條件三項；不要求附計畫，role 只跑自己改動相關的檢查 |
| D4 | hook 延遲目標 | 每次 p50 ≤ 150ms（目前 300–450ms） |
| D5 | 降延遲做法 | (a) guard 對不需要判斷的事件提早結束；(b) chain 成員只在它登記的事件上呼叫；(c) 檢查能否不經 pyenv shim 啟動 python（安裝時解析直譯器路徑）；(d) 移除重複的 hook 事件 |
| D6 | 驗收 | 同一套 benchmark 重跑：真實任務（v2）維持通過數 ≥ baseline、成本 ≤ 1.3 倍、時間 ≤ 1.5 倍；小任務只設成本門檻、不設時間門檻，因為一次 role 派工有約 20 秒的下限（role 分工原則）。benchmark 隔離 `XDG_DATA_HOME`，不跑使用者的 chain 成員 |

2026-10-18 實測：v1 成本 1.27 倍、時間 2.1 倍、通過數相同；v2 成本 1.19 倍、平均時間 0.51 倍、隱藏驗收相同。

## Scope

- 改：`core/policy/orchestration.toml`、`bootstrap.toml`、`extensions.toml`
  中與 `#fast`、派工成本、brief 相關的條款；guard 的 fast 模式語意與
  hook 熱路徑；Claude plugin 的 `hooks.json`。
- 不改：role 權限、lane 標籤規則、嚴謹路線觸發條件、Codex plugin 位置。
- Lock：條款變動會超過 change budget，需要一次 Miyago 核准的 lock renewal
  （與 v3.10.0 同流程）。

## Phases

1. P1 hook 延遲：量測腳本與 D5，不動條款。可單獨出貨。
2. P2 條款與 `#fast` 語意（D1–D3），含 lock renewal。
3. P3 benchmark 驗收（D6），決定是否發 minor 版。

## Out of scope

- shoal 加 Workflow 的組合：另外量測（`shoal-workflow` arm），結果出來再決定
  是否寫進條款。
