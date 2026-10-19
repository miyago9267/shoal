# Pilotfish value Matrix

這張表回答兩個問題：Pilotfish 是否能提升品質，以及使用者把主 session 開成 Sol 時，Pilotfish 是否能把一般工作導回 Luna 而省錢。

## 12-case projection：品質與成本

| 策略 | 品質平均 | supported findings | weighted tokens | 估算成本 | 可支持的結論 |
| --- | ---: | ---: | ---: | ---: | --- |
| Luna-only | 71.15 | 14 | 183,045 | `$0.195` | 品質基準最高 |
| Sol-only | 60.42 | 10 | 241,132 | `$0.929` | 成本高、品質低於 Luna |
| Pilotfish selective（Sol-primary 情境） | 60.42 | 10 | 221,026 | ≤ `$0.851` | 品質持平 Sol，成本至少低 8.34% |

`Pilotfish selective` 的美元數字是保守上限：先把全部 token 都按 Sol 單價計算；實際上它會把部分工作送給 Luna，因此實際成本應不高於此上限。

## Pilotfish 的品質提升證據

| 策略 | 品質平均 | 相對 Luna | 成本 / 12 cases | 判定 |
| --- | ---: | ---: | ---: | --- |
| Luna-only | 56.08 | — | `$0.193` | baseline |
| Luna-first + disagreement Sol adjudicator | 61.46 | `+5.38` | `$0.430` | 點估計品質上升，且低於純 Sol/Terra |
| 純 Sol reference | — | — | `$2.932` | 成本參考 |
| 純 Terra reference | — | — | `$1.364` | 成本參考 |

但這個 `+5.38` 的 paired confidence lower bound 是 `0`，所以它是「品質提升的方向性證據」，還不是「已證明品質顯著提升」。

## 白目使用者把主 session 設成 Sol 的情境

這是目前最直接的證據：

| Cohort | Sol-only | Pilotfish routing | 品質差異 | token 節省 |
| --- | ---: | ---: | ---: | ---: |
| 12-case projection | 60.42 | 60.42 | `0.00` | `8.34%` |
| 6-case live slice | 83.33 | 83.33 | `0.00` | `16.80%` |

意思是：即使使用者偏好 Sol，Pilotfish 也不必把所有工作都交給 Sol。
一般工作交給 Luna，安全、複合風險或 Luna 不確定時才保留 Sol，已在這兩個
cohort 中維持 Sol 的觀察品質並降低 token 使用量。

## 結論

目前可以負責任地宣稱：

1. Pilotfish 有方向性品質提升證據：disagreement adjudication 相對 Luna `+5.38` quality points。
2. Pilotfish 有較強的成本證據：Sol-primary routing 維持 Sol 品質，
   12-case 少 `8.34%` token，6-case live 少 `16.80%`。
3. Pilotfish 尚不能宣稱「統計上已證明比 Luna 品質好」；目前最穩固的 production value 是「品質不降的前提下，避免 Sol 全程執行而省錢」。

機器可讀結果：[role-fitness-v1-pilotfish-value-matrix.json](role-fitness-v1-pilotfish-value-matrix.json)。
產生器：[evaluate_pilotfish_value_matrix.py](../../../bench/evaluate_pilotfish_value_matrix.py)。
