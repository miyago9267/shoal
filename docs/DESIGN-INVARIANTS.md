# shoal 設計不變式

方向檢查（`docs/specs/milestone-direction-check/`）的比較基準之一。來源是
2026-10-06 與 上游原始設計（v1.4.2） 的設計對照，以及 Miyago 2026-10-07 的目標
（要有品質、不要有隧道視野）。修改本檔屬於設計變更，需要 spec 與核准。

1. **main 負責判斷**：framing、架構、Plan、整合與最終判斷由 main session 做；
   write role 只接已核准、規格完整的執行契約，discovery role 只接穩定的研究
   契約與停止條件。executor 在 brief 之外做的設計決定，視為未審查，main 逐項
   接受或退回。
2. **派工不以數字門檻強制**。改檔一律由可寫的 role 執行，除非使用者以
   `#direct` 授權 main 直接改；互不相干的偵察與長指令預設派工。讀檔、診斷、
   整合與判斷由 main 直接做。
3. **hook 強制硬規則**：leaf 不再派 subagent、verifier 類 role 不改檔、main
   以背景方式開 shell，以及 main 未派工就改檔（`#direct` 可放行）。
   這些規則不依賴任何分類器。含數字門檻的規則只提醒。
4. **規則與策略由 core 定義，所有 host 共用。** host 的 adapter 只放三類內容：
   工具與參數名稱、model 綁定、該 host 特有的調校參數。host 做不到的條款明列
   省略理由。
5. **core 條款不綁具體模型**：core／host 中立條款不寫具體 model ID；host
   addenda、role frontmatter 與 alias（例如 Luna／Sol／Astra、tier）不在此限。
6. **驗證邊界不省略**：有風險的工作，核准前的 plan review 與完成後的 outcome
   verification 不因使用便宜的 executor 而省略；verdict 是證據，不是授權。
7. **單一來源**：role、條款、模型目錄與安裝都以 shoal 的 committed HEAD 為準；
   本機環境只用 shoal，上游專案只保留 credit 與協作。
