# shoal 設計不變式

方向檢查（`docs/specs/milestone-direction-check/`）的比較基準之一。來源是
2026-10-06 與 上游原始設計（v1.4.2） 的設計對照，以及 Miyago 2026-10-07 的目標
（要有品質、不要有隧道視野）。修改本檔屬於設計變更，需要 spec 與核准。

1. **main 負責判斷**：framing、架構、Plan、整合與最終判斷由 main session 做；
   write role 只接已核准、規格完整的執行契約，discovery role 只接穩定的研究
   契約與停止條件。executor 在 brief 之外做的設計決定，視為未審查，main 逐項
   接受或退回。
2. **派工是淨效益判斷**，不以數字門檻強制。已有穩定契約的實作、互不相干的
   偵察與長指令預設派工；main 直接做的條件是寫 brief 的成本高於直接做。
3. **hook 強制硬規則**：leaf 不再派 subagent、verifier 類 role
   不改檔，以及 Claude 上本輪已被分類為實作工作而 main 尚未派工時的改檔、main
   以背景方式開 shell（兩者可用 `#direct` 放行）。含數字門檻的規則只提醒。
4. **各 host 的規則相同**，model 與工具名稱依 host 綁定；host 做不到的條款明列
   省略理由。
5. **core 條款不綁具體模型**：core／host 中立條款不寫具體 model ID；host
   addenda、role frontmatter 與 alias（例如 Luna／Sol／Astra、tier）不在此限。
6. **驗證邊界不省略**：有風險的工作，核准前的 plan review 與完成後的 outcome
   verification 不因使用便宜的 executor 而省略；verdict 是證據，不是授權。
7. **單一來源**：role、條款、模型目錄與安裝都以 shoal 的 committed HEAD 為準；
   本機環境只用 shoal，上游專案只保留 credit 與協作。
