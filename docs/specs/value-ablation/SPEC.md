# value-ablation：每個 shoal 機制都要用實測證明自己值得

狀態：草案，等 Miyago 核准（2026-11-16）。

## Background

現有 A/B（`bench/ab/results/ab-v2.json`，Sonnet 5.5 為 main，8 題 × 2 rep，hidden test）：

| arm | 通過 | 平均成本 | 平均 wall |
| --- | --- | --- | --- |
| baseline | 16/16 | $0.149 | 127s |
| shoal | 16/16 | $0.310 | 219s |
| shoal-fast | 16/16 | $0.258 | 119s |
| shoal-workflow | 8/8 | $0.319 | 455s |

`v3.json`（4 題 × 2）：baseline 8/8、shoal-workflow 6/8、$0.545。

1. 題目太簡單，baseline 全過，shoal 宣稱能防的失敗沒有機會發生；目前只量到成本。
2. 2026-11-16 Codex 實際卡住：`hooks/shoal_autoroute_gate.py` 的 Stop hook 規定
   `task_name=automatic_model_route`，`hooks/shoal_guard.py` 要求 Codex write role 的
   task_name 符合 `<lane>_<size>_<slug>`，兩者無法同時滿足；且 Stop hook 在唯讀分析
   已完成後仍要求再派 agent。hook 之間的摩擦目前沒有任何量測。

## Goal

shoal 的每個機制要在「可能失敗的題目」上量出效益；量不出效益的機制移除或改成預設關閉。
比較對象是 baseline 與 shoal 自己的 ablation，不與其他專案比較（Miyago 2026-11-16）。

## 要驗證的機制

| ID | 機制 | 宣稱的效益 | 主要指標 |
| --- | --- | --- | --- |
| M1 | 改檔交給 role（main 不改檔） | 長任務中 main context 保持乾淨，後段決策品質較好 | 長任務通過率、main context token |
| M2 | 改完沒驗證不能結束（verify gate） | 減少「宣稱完成但沒通過」 | 假完成次數、通過率 |
| M3 | 擋非 shoal agent 與 protected 檔寫入 | 減少越界修改 | protected violation 次數 |
| M4 | autoroute／Stop hook 強制續派 | 該派工時不會漏派 | 通過率 vs. hook 摩擦次數 |
| M5 | `#fast` lane | 簡單工作接近 baseline 成本 | 成本、wall |

一份定義 render 到多個 host 的效益不適合 A/B，改用維護面量測：各 host 規則漂移與
跨 host 衝突（如上述 Codex 事件）的件數，在報告中單獨列出。

## 題目

- 8 題，每題至少埋一個陷阱：碰 protected 檔、改 test 讓它變綠、改完不驗證就宣稱完成、
  需要讀很多檔才能定位的長任務、中途需求補充。
- 校準條件：baseline 在 2 rep 中至少要有 30% 的 run 失敗；達不到的題目換掉，不進正式量測。

## Arms

baseline、shoal-full，以及從 shoal-full 各關掉 M1–M4 其中一項的 4 個 ablation，共 6 個。
M5 沿用現有 `shoal-fast` 數據，不重跑。

## 預算與規模

- 總上限 $30，runner 的 `--max-cost-usd` 設 30，超過即停。
- 先跑 smoke：1 題 × 6 arm × 1 rep，確認 runner、開關、指標收得到。
- 正式：8 題 × 6 arm × 2 rep = 96 run；若 smoke 單 run 成本 > $0.30，rep 降為 1。

## 去留規則（事先固定）

- 關掉某機制後，通過率下降或 violation 增加至少 2 run（以 16 run 計）→ 保留。
- 差異小於 2 run → 移除或預設關閉，不論理論上的好處。
- 有效益但成本 > 1.5 倍 → 保留，但列入降成本待辦。
- hook 摩擦（被擋的派工、強制續派、規則互相矛盾）每出現一次都記錄，並在報告中附上原因。

## Phases

1. P0：修 autoroute 與 guard 的 task_name 衝突（進行中）。
2. P1：在 `miyago9267/shoal-bench` 寫 8 題與陷阱，跑 baseline 校準。
3. P2：在 runner 加 M1–M4 的開關（環境變數或設定檔），每個開關附一個單元測試。
4. P3：smoke，然後正式量測。
5. P4：報告與砍除清單，交 Miyago 決定。

## Out of scope

- 與其他 orchestration 專案的比較。
- Codex、Grok、agy、OpenCode host 的 A/B（runner 目前以 Claude 為 main）；P4 後再決定。
