---
title: guard 改用「宣告直接做」，分類來源變為可選
status: approved
approved_by: Miyago (2026-10-12)
created: 2026-10-12
updated: 2026-10-12
---

<!-- markdownlint-disable MD025 -->

# guard 改用「宣告直接做」，分類來源變為可選

## Background

`delegation-default` 的 R1 與 G5 只在「本回合已被分類為實作工作」時才擋 main 改檔，
分類來自本機 dotfile 的 Jev（一個外部模型的分類器）。查證與實測（v3.1.0）：

- Jev 送出的 729 次中，門檻 0.8 時只有 19% 給出分類；沒有分類的回合 guard 不介入。
- 只靠 policy 文字時，小功能都由 main 自己做；被 guard 擋下一次後才派工。
- Jev 不屬於 shoal，換廠牌或換機器就沒有。

Miyago 2026-10-12：好的策略不分模型、不分廠牌；Jev 的分流要變成可選。

## Requirements (EARS)

- **M1（模式）**：guard 的 main 改檔規則由 `SHOAL_GUARD_R1` 決定：`declare`、
  `classified`、`off`。未設定時 claude 與 codex 用 `declare`，其他 host 維持現狀
  （不 deny）。`classified` 是 v3.1.0 的行為，保留給想用分類來源的人。
- **M2（declare 規則）**：While 模式是 `declare` 且 guard 為 enforce，when main
  session 呼叫改檔工具，或以 shell 寫檔（沿用 G5 的字面判斷），the guard shall
  deny，除非本回合符合下列任一條件：
  - 已派出可寫的 role；
  - 使用者的 prompt 含獨立的 `#direct`，或設定 `SHOAL_GUARD_DIRECT=1`；
  - main 已在本回合宣告直接做（M3）；
  - 目標路徑屬於既有的豁免路徑。
- **M3（宣告）**：宣告是一次 shell 呼叫，整個指令只有
  `: shoal-direct "<理由>"`（`:` 是 shell 內建的空指令；理由可用單引號、雙引號或
  不加引號，去掉空白後不得為空；不得與其他指令串接）。guard 記下本回合的宣告旗標，
  下一回合失效。guard 不判斷理由內容，只把理由（截短）寫進 log。
- **M4（訊息自帶出口）**：deny 訊息 shall 寫明三個出口：派出可寫的 role、執行宣告
  指令、請使用者加 `#direct`。沒有 policy 文字的 host 只靠這則訊息就能繼續。
- **M5（分類來源可選）**：分類檔（`<state>/shoal/guard/turns/<session>.json`，內容
  `{"turn_id", "role"}`）的格式列為公開契約，任何工具都可以寫入。在 `declare` 模式
  下它只能放寬：`role` 為 `parent_local` 時視同已宣告；其他值或沒有檔案都不影響
  規則。在 `classified` 模式下行為與 v3.1.0 相同。
- **M6（不變的部分）**：硬規則（leaf 不得派工、verify 類 role 不得改檔）、G4（main
  開背景 shell）、R2（檔案數提醒）、shadow 與 off 模式、fail-open，行為不變。
  subagent 不受 M2 影響。
- **M7（Codex）**：Codex 的 adapter shall 辨識 main session 的 shell 呼叫，使 M2 的
  shell 寫檔判斷與 M3 的宣告在 Codex 上生效；`#direct` 也在 Codex 的 prompt 事件
  生效。做不到的部分明列原因，該部分維持現狀。
- **M8（Claude bootstrap）**：bootstrap 加一句：要自己改檔，先執行宣告指令，而且只在
  符合直接做的條件時宣告。

### 修訂（2026-10-12，live gate 之後）

live gate 顯示 Claude 在小功能上每次都先宣告再自己做，宣告沒有讓 main 改成派工。
Miyago 2026-10-12 決定拿掉 main 自己給自己的出口。

- **M9（strict 模式）**：`SHOAL_GUARD_R1` 新增 `strict`，並成為 claude 與 codex 的
  預設。While 模式是 `strict` 且 guard 為 enforce，when main session 呼叫改檔工具
  或以 shell 寫檔，the guard shall deny，除非本回合已派出可寫的 role、使用者的
  prompt 含獨立的 `#direct`（或設定 `SHOAL_GUARD_DIRECT=1`），或目標屬於豁免路徑。
  宣告指令與分類檔在 `strict` 模式都不放行。`declare`、`classified`、`off` 保留為
  可選。
- **M10（訊息）**：`strict` 的 deny 訊息只列兩個出口：派出可寫的 role，或請使用者在
  prompt 加 `#direct`。
- **M11（派工要真的啟動）**：Where host 提供 role 已啟動的事件，the guard shall 以
  該事件而不是派工呼叫本身，作為「已派出可寫的 role」的依據；role 沒能啟動時不
  放行。沒有這種事件的 host 維持以派工呼叫為準，並在文件寫明這個限制。
- **M12（條款一致）**：Claude 的 bootstrap 與 policy 不再寫「main 可以自己做小改動」
  或宣告指令；改成：main 不自己改檔，改檔一律派可寫的 role，除非使用者以
  `#direct` 授權。讀檔、執行指令、診斷仍由 main 直接做。
- **D6**：`docs/DESIGN-INVARIANTS.md` 第 2 條改為：「派工不以數字門檻強制。改檔
  一律由可寫的 role 執行，除非使用者以 `#direct` 授權 main 直接改；互不相干的偵察
  與長指令預設派工。讀檔、診斷、整合與判斷由 main 直接做。」第 3 條的「未派工、
  未宣告就改檔（宣告或 `#direct` 可放行）」改為「未派工就改檔（`#direct` 可放行）」。

## Decisions

- **D1**：用「宣告」而不是分類器決定擋不擋。原因：規則是確定性的，不需要任何
  模型；判斷仍由 main 做（不變式第 2 條），只是從默默決定變成留下紀錄的決定。
- **D2**：宣告用 shell 的空指令，不做 CLI。原因：不需要安裝任何東西，任何有 shell
  的 agent 都能用；guard 本來就看得到 shell 呼叫。
- **D3**：只有 claude 與 codex 預設啟用。原因：兩者的 guard 分得出 main 與
  subagent 且預設 enforce；Miyago 只訂閱這兩家，實測也只做這兩家。
- **D4**：`docs/DESIGN-INVARIANTS.md` 第 3 條改為：「hook 強制硬規則：leaf 不再派
  subagent、verifier 類 role 不改檔、main 以背景方式開 shell，以及 main 未派工、
  未宣告就改檔（宣告或 `#direct` 可放行）。這些規則不依賴任何分類器。含數字門檻的
  規則只提醒。」
- **D5**：Jev 留在 dotfile，當作可選的提示與 M5 的放寬來源；shoal 不再假設它存在。

## Slices

| # | 內容 | 驗收 |
|---|---|---|
| S1 | M1–M6：guard 與 TypeScript mirror、測試向量 | guard vectors（Python 與 TS 一致）、unittest 全過 |
| S2 | M7：Codex adapter 與 hook 註冊 | Codex payload 的向量；安裝後的 hooks 設定涵蓋 shell 工具 |
| S3 | M8、D4、文件、v3.2.0 | render 檢查、lock、文件連結 |
| S4 | live gate（Miyago 2026-10-12 同意，只跑 Claude 與 Codex，最多 8 次） | 見下 |

live gate 要回答的問題：

1. 沒有分類檔時，main 未宣告就改檔會被擋（Claude、Codex 各至少一次）。
2. 被擋之後 main 怎麼做：派工、宣告，還是卡住。記錄每次的選擇。
3. 小改動（一個錯字）與三檔小功能各跑，量「宣告率」：小改動宣告是合理的，
   小功能若每次都宣告，表示規則沒有改變行為。

## Non-goals

- 不移植 Claude 的派工條款到其他 host。
- 不刪除 `classified` 模式，不修改 dotfile 的 Jev 程式。
- 不啟用 grok、agy、opencode 的 deny。

## Risks

- main 每次都宣告了事，規則形同虛設。緩解：理由進 log 可稽核；live gate 量宣告率，
  結果寫進 PROGRESS，不好就回到本 spec 檢討。
- 宣告的字面判斷若太鬆，會被夾帶在其他指令裡。緩解：只認整個指令就是宣告的情況。
- Codex 的 shell 工具名稱與 payload 形狀要以實際 payload 為準；無法確認時該部分
  不啟用並寫明。
- Codex 平常是單一 agent 在做事，預設改成 `declare` 會讓它每回合多一次宣告。
