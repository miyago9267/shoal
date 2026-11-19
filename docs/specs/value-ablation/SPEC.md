# value-ablation：每個 shoal 機制都要用實測證明自己值得

狀態：已核准（Miyago 2026-11-19）。同日改動：加 pilotfish arm、正式量測 1 rep、M1 改量 R1 擋或不擋。

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
3. guard log（2026-10-30 至 11-19，Claude）：1637 個 prompt 中有 165 個回合被 R1 擋下
   main 改檔；其中 160 次 main 補一行 `: shoal-direct` 宣告後照樣自己改，只有 1 次改成派工。
   R1 的 deny 幾乎不改變路由，只增加來回。因此 Claude 的 R1 預設改為 `advise`
   （放行、每回合提醒一次、log 記 `undeclared`），見 `guard-declared-direct` 的 M13。

## Goal

shoal 的每個機制要在「可能失敗的題目」上量出效益；量不出效益的機制移除或改成預設關閉。
比較對象是 baseline、shoal 自己的 ablation，以及 pilotfish（Miyago 2026-11-19 改為納入競品比較）。

## 要驗證的機制

| ID | 機制 | 宣稱的效益 | 主要指標 |
| --- | --- | --- | --- |
| M1 | R1 擋 main 改檔（`SHOAL_GUARD_R1=declare`）對比預設 `advise` | 長任務中 main context 保持乾淨，後段決策品質較好 | 長任務通過率、main context token、派工次數 |
| M2 | 改完沒驗證不能結束（verify gate） | 減少「宣稱完成但沒通過」 | 假完成次數、通過率 |
| M3 | 擋非 shoal agent 與 protected 檔寫入 | 減少越界修改 | protected violation 次數 |
| M4 | SessionStart 注入的派工 bootstrap（Claude 上 autoroute Stop hook 不存在，2026-11-19 改量這項） | 該派工時不會漏派 | 通過率、派工次數 vs. 注入的 context token |
| M5 | `#fast` lane | 簡單工作接近 baseline 成本 | 成本、wall |

一份定義 render 到多個 host 的效益不適合 A/B，改用維護面量測：各 host 規則漂移與
跨 host 衝突（如上述 Codex 事件）的件數，在報告中單獨列出。

## 題目

- 8 題，每題至少埋一個陷阱：碰 protected 檔、改 test 讓它變綠、改完不驗證就宣稱完成、
  需要讀很多檔才能定位的長任務、中途需求補充。
- 校準條件：baseline 在 2 rep 中至少要有 30% 的 run 失敗；達不到的題目換掉，不進正式量測。

## Arms

baseline、shoal-full（R1 預設 `advise`）、M1 arm（R1 改回 `declare`），以及從 shoal-full
各關掉 M2–M4 其中一項的 3 個 ablation，再加 pilotfish（最新 release、預設設定），共 7 個。
關 M2 是 `SHOAL_GUARD_STOP=off`，關 M3 是 `SHOAL_GUARD_SUBAGENT_WRITE=off`，關 M4 是 plugin 副本拿掉 SessionStart hook；
protected 違規由 bench 從 diff 判定，每個 arm 都量。M5 沿用現有 `shoal-fast` 數據，不重跑。

## 預算與規模

- 總上限 $30，runner 的 `--max-cost-usd` 設 30，超過即停。
- 先跑 smoke：1 題 × 7 arm × 1 rep，確認 runner、開關、指標收得到。
- 正式：8 題 × 7 arm × 1 rep = 56 run。

## 去留規則（事先固定）

- 以 8 run 計：關掉某機制後，通過率下降或 violation 增加至少 2 run → 保留。
- 差異小於 2 run → 移除或預設關閉，不論理論上的好處。
- 有效益但成本 > 1.5 倍 → 保留，但列入降成本待辦。
- hook 摩擦（被擋的派工、強制續派、規則互相矛盾）每出現一次都記錄，並在報告中附上原因。

## Phases

1. P0：修 autoroute 與 guard 的 task_name 衝突（8bab65b 已修）；Claude R1 預設改 `advise`。
2. P1：在 `miyago9267/shoal-bench` 寫 8 題與陷阱，跑 baseline 校準；runner 加 pilotfish arm。
3. P2：在 runner 加 M1–M4 的開關（環境變數或設定檔），每個開關附一個單元測試。
4. P3：smoke，然後正式量測。
5. P4：報告與砍除清單，交 Miyago 決定（`REPORT.md`，2026-11-19）。

## Out of scope

- pilotfish 以外的 orchestration 專案。
- Codex、Grok、agy、OpenCode host 的 A/B（runner 目前以 Claude 為 main）；P4 後再決定。

## 第三輪：會派工的情境（Miyago 2026-11-19 核准，預算 $50，main 用 Opus）

第二輪的題目每 run 約 30 秒、3 萬 token，派工的三個宣稱效益（main 上下文乾淨、便宜 role 省錢、
平行省時間）都沒有出現的條件，shoal-full 24 run 只派工 1 次（見 `REPORT.md`）。

- 題目 4 題，各對應一個宣稱：
  - 長鏈：同一 session 4–5 個相依子任務，main 全部自己做會超過 150k token 或觸發 compact。
  - 讀很多、改很少：要掃大量檔案或 log 才能定位，改動只有幾行。
  - 平行：4 個彼此獨立的模組各自要修。
  - 中型混合：上述的縮小版，當對照。
- Arms：baseline-opus、baseline-sonnet、shoal（main Opus，bootstrap 為縮短後版本）、pilotfish（main Opus）。
- 規模：4 題 × 4 arm × 2 rep = 32 run，`--max-cost-usd 50`。
- 先 smoke：長鏈題 × shoal 1 run，確認真的有派工；沒有派工就停下，問題在 bootstrap 與政策而非題目。
- 結果：探測後停止，見 `REPORT.md` 第三輪一節。
- 指標：通過率、總成本、wall、main 峰值上下文、compact 次數、派工次數、後段子任務通過率。
- 結論規則：shoal 在任一題型以同等或更好通過率勝過 baseline-opus 的成本或 wall，派工保留為預設；
  四題都沒有，派工改為選用，shoal 主打多 host 定義與 guard。
