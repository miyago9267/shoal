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

## 第三輪：探測後停止（2026-11-19）

長鏈題改成同一 session 連續 8 個 prompt（shoal-bench 7d3c89f），baseline-sonnet 探測一次：

- 成本 $3.47，wall 163 秒；8 輪的峰值上下文從 49.6k 增加到 78.0k，0 次 compact。
- 8 個 stage 過 7 個（Stage7 是 docs 措辭檢查過嚴，已放寬，未重跑）。
- 模型自己用 `grep`／`tail` 壓縮輸出，27 個工具結果合計約 58k 字元，每個 prompt 只多 3–6k。

結論：在 8 個任務的長 session 裡，便宜的 main 自己做就沒有被上下文拖垮，shoal「保護 main 上下文」
的前提不成立。照原計畫用 Opus 量 32 run 估計要 $125–130；Miyago 判斷「越量越貴」本身就是派工性價比
不好的證據，第三輪正式量測不跑。value-ablation 總花費約 $28.9。

## 方向（Miyago 2026-11-19 修正）

main session 有 1M 上下文，模型記憶不是瓶頸。派工要保護的是人：main 只負責討論，執行的工具輸出、
diff 與重試不進人看的對話，人才不會失焦。這個效益不在 headless benchmark 的量測範圍內。

1. 派工維持預設，但理由從「保護模型上下文」改成「保護人的注意力」；成本代價約 +25%（本報告第二輪）。
2. 已量到的問題是派工根本沒發生：R1 deny 時 main 補宣告照改（160/165），advise 時 24 run 只派 1 次。
   下一步要解決的是「main 為什麼不派」，不是「派工值不值得」。
3. 改用免費的量法：從真實 session 的 transcript 與 guard log 算「每個使用者回合，main 自己跑了多少
   工具呼叫、吐了多少輸出到對話」，當作人的雜訊指標。
4. shoal 對外主打：一份定義通用多個 host、guard 的規則執行，以及讓 main 保持在討論層。
