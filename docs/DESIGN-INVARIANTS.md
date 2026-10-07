# shoal 設計不變式

方向檢查（`docs/specs/milestone-direction-check/`）的比較基準之一。來源是
2026-10-06 與 上游原始設計（v1.4.2） 的設計對照，以及 Miyago 2026-10-07 的目標
（要有品質、不要有隧道視野）。修改本檔屬於設計變更，需要 spec 與核准。

1. **main 負責判斷**：framing、架構、Plan、整合與最終判斷由 main session 做；
   write role 只接已核准、規格完整的執行契約，discovery role 只接穩定的研究
   契約與停止條件。executor 在 brief 之外做的設計決定，視為未審查，main 逐項
   接受或退回。
2. **派工是淨效益判斷**：要不要派工由 dispatch brake 依淨效益決定，不以數字
   門檻強制；小而局部的工作由 main 直接做。
3. **hook 只強制硬規則**：hook 只擋 leaf 不再派 subagent、verifier 不改檔；
   其餘以提醒呈現，不取代判斷。
4. **各 host 保留自己的形狀**：共用化以持平為準，不藉共用化新增能力；Grok 的
   rules 保持與上游可對照。
5. **core 條款不綁具體模型**：core／host 中立條款不寫具體 model ID；host
   addenda、role frontmatter 與 alias（例如 Luna／Sol／Astra、tier）不在此限。
6. **驗證邊界不省略**：有風險的工作，核准前的 plan review 與完成後的 outcome
   verification 不因使用便宜的 executor 而省略；verdict 是證據，不是授權。
7. **單一來源**：role、條款、模型目錄與安裝都以 shoal 的 committed HEAD 為準；
   本機環境只用 shoal，上游專案只保留 credit 與協作。
