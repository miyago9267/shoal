# value-ablation 報告（P4）

日期：2026-11-19。main 模型 Sonnet 5.5，題目 `shoal-bench` 的 `bench/ab/tasks-ablation/`（b4e8ca1），
shoal 為 `feat/r1-advise-ablation`（a34969a），pilotfish v1.5.0。總花費約 $25.3（上限 $30）。

## 數據

結果檔在 shoal-bench `bench/ab/results/`：`abl-calib11.json`（加難後校準）、`abl-formal.json`
（7 arm × 8 題 × 1 rep）、`abl-reps.json`（3 arm × 8 題 × 2 rep）。

### 7 arm，各 1 rep

| arm | 通過 | 平均成本 | 假完成 | 摩擦 | 派工 |
| --- | --- | --- | --- | --- | --- |
| baseline | 4/8 | $0.131 | 3 | 0 | 0 |
| pilotfish | 5/8 | $0.157 | 1 | 0 | 0 |
| shoal-full（R1 advise） | 3/8 | $0.153 | 1 | 0 | 0 |
| M1（R1 declare） | 4/8 | $0.176 | 0 | 6 | 0 |
| 關 M2（STOP） | 7/8 | $0.255 | 1 | 1 | 3 |
| 關 M3（subagent 寫檔） | 5/8 | $0.159 | 1 | 0 | 0 |
| 關 M4（bootstrap） | 4/8 | $0.131 | 2 | 0 | 0 |

### 3 arm，各 3 rep

| arm | 通過 | 每 rep 通過 | 平均成本 | 假完成 | 派工 |
| --- | --- | --- | --- | --- | --- |
| baseline | 13/24 | 6, 3, 4 | $0.132 | 6 | 0 |
| shoal-full | 11/24 | 5, 3, 3 | $0.165 | 3 | 1 |
| pilotfish | 15/24 | 4, 6, 5 | $0.157 | 4 | 0 |

同一 arm 不同 rep 的通過數差到 3 run（以 8 題計），大於 SPEC 去留規則的 2 run 門檻。

## 結論

1. 通過率：baseline、shoal-full、pilotfish 的差距都在 rep 雜訊內，量不出任何一方較好。
2. 成本：shoal-full 比 baseline 多 25%，pilotfish 多 19%。
3. 派工：shoal-full 24 run 只派工 1 次。main 在 advise 下幾乎全部自己做，shoal-full 等於
   baseline 加上 bootstrap 與 hook 的成本。
4. M1（R1 擋）：6 次摩擦、0 次派工、成本多 15%，與 guard log（165 次 deny 只有 1 次改派工）一致。
   維持 Claude 預設 `advise`。
5. M4（bootstrap）：拿掉後成本與 baseline 相同，派工次數不變（都是 0）。效益未證明，列入砍除或大幅縮短。
6. M2、M3：本批題目幾乎沒有觸發，量不出效益也量不出成本，維持現狀，等有會觸發的題目再量。
7. 假完成：baseline 6/24，shoal-full 3/24，pilotfish 4/24，方向一致但樣本太小，不作結論。

## abl-5 的差異

abl-5（第二輪補需求）baseline 3/3 通過，shoal-full 0/3、pilotfish 1/3。失敗的 3 個 run 都卡在同一個
hidden test：`blog/routes.py` 的 `RESERVED = {"new", "edit", "feed"}` 不得被當成 slug（應得 `new-2`）。
這條規則不在需求文字裡，要自己讀到 routes.py。超幾何檢定 p ≈ 0.048，只是邊緣顯著。推測是 plugin
注入的上下文讓 main 少讀了檔案；runner 沒有保存完整 transcript，無法確認。

## 砍除與待辦清單（交 Miyago 決定）

1. bootstrap 注入：縮到只剩派工規則的最小版本，或預設關閉。
2. R1 `declare`：不再是任何 host 的建議值；Codex 預設 `strict` 是否跟進另外量。
3. runner 保存每個 run 的 stream-json，下次才能查 abl-5 這類差異。
4. 要量 M2、M3 與派工本身的效益，需要會讓 main 派工的情境（長任務、多檔平行），或改量
   「便宜 main + role」的組合；單 session 的 Sonnet 題目量不到。
