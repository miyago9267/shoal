# milestone-direction-check 進度

## M1（完成，`0141e06`）

main 撰寫 `CLAUSES.md` 與 `docs/DESIGN-INVARIANTS.md`；plan-verifier 三輪後 READY
（條款改為取代既有段落、限定多切片 milestone、不變式第 1 條區分 write／discovery
role）。

## M2（完成，`77883f7`，CI 綠）

- 條款逐字寫入 Claude core（`direction-checkpoint`）與 Codex legacy（取代原段落與
  三項清單，mirror 同步）；claude、codex host 2.1.0；`LOCK.json` 未改，Codex
  orchestration changed_lines 31／32。
- D5 executor 設計決定的處置：
  - Claude legacy 來源同步改寫（test_core_policy 要求 legacy 與 core 一致）：接受，
    屬 M2 必要範圍。
  - `hosts/codex/CHANGELOG.md` 新增 v2.1.0 條目：接受。
  - `tests/test_install.py` newer-plugin fixture 改為 2.1.1：接受（版本號需大於現行）。
  - `tests/test_check_rename.py` 的 rebrand 等價測試改為無條件 skip：DEFER。該測試是
    2.0.0 改名的一次性等價檢查，policy 自此刻意偏離 base；目前無回歸風險。若要保留，
    之後改為只檢查改名對照表涉及的檔案。
  - `DESIGN-INVARIANTS.md` 原文提及上游名稱造成 legacy 名稱掃描命中：main 改寫為
    「上游原始設計」。

## M2b（完成，`efa4231`，CI 綠）

- 條款逐字新增為 `cost-unbounded-continuation`（Claude core 與 legacy 來源）與 Codex
  M2 段落之後；claude、codex host 2.1.1；`LOCK.json` 未改，Codex changed_lines
  14、Claude workflow-extensions 12。
- D5：`tests/test_install.py` fixture 改為 2.1.2：接受。

## M3 方向檢查演練（2026-10-08）

多切片 milestone 收尾，以 fresh `verifier` 的 `direction_checkpoint` 進行，基準為
Miyago 原始需求、本 spec 的 non-goals 與 decisions、`docs/DESIGN-INVARIANTS.md`。

- 結果：**CONTINUE**。non-goals 皆守住（未碰 hook、guard、role、LOCK、Grok、agy、
  OpenCode）；條款逐字一致、舊的「may」文字已移除；只在 milestone 檢查、非逐切片；
  不計代價模式不授予權限。
- 提出的 P3：上列 test skip，處置為 DEFER。
- 提醒的收尾事項：產品版本與 host 版本分開（host 2.1.1、產品 2.1.0 由 M4 bump）；
  M4 屬發布，Miyago 已於 2026-10-07 指示「READY 就直接做到底」。
- 第一次執行時 verifier 卡住超過 600 秒被中止，以縮小讀取範圍續跑後完成。
