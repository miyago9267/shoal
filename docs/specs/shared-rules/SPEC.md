---
title: 規則共用：各 host 只留 model 與調校參數
status: approved
approved_by: Miyago (2026-10-13)
created: 2026-10-13
updated: 2026-10-13
---

<!-- markdownlint-disable MD025 -->

# 規則共用：各 host 只留 model 與調校參數

## Background

Miyago 2026-10-13：規則和策略全部抽象出來，所有廠牌的 agent 共用同一套規則；
只有「接什麼 model」和少數調校參數需要 adapter，host 之間的差別應只剩 model 的
強弱與價格。同一天他也要求：寧可多花時間檢查，也不要事後才說「前面講過頭」或
「前面沒發現」。

現況（v3.3.1，`9f0be51` 查證）：

- role 文字：五個 host 都由 `core/` 產生。
- 派工條款：只有 Claude 由 `core/policy/` 產生（`policy_text = "core"`）；Codex、
  Grok、agy、OpenCode 仍是各自的舊條款（`legacy`）。`tools/render.py` 目前只允許
  Claude 使用 core 條款。
- 這是 2026-10-06 的決定造成的：`docs/specs/core-policy/SPEC.md` 的「修訂：持平
  優先」寫明「不做 P3，其他 host 維持 legacy」，理由是切換會帶來 40 項以上的行為
  變更，當時把它視為「把 host 同質化」。本 spec 推翻那個決定。
- Codex 的舊條款與共用條款互相矛盾的地方（節錄）：Codex 允許 main 直接做小改動、
  role 派不出去時由 main 接手、長指令歸 main；共用條款是 main 不自己改檔、派不
  出去要回報、長指令交給 `watcher`。
- 沒有任何 host 檢查「宣告完成前有沒有驗證」。Codex 現有的 Stop gate
  （`hooks/shoal_autoroute_gate.py`）擋的是「該做的 Plan 審查或 model 升級沒做」，
  不是完成宣告；它的骨架（結束前查證據、只擋一次、讀不到就放行）可以沿用。
- 常駐的 bootstrap 沒有任何一句要求完成宣告要附驗證證據；相關條款只在按需載入的
  文件裡。
- guard 目前不記錄「本回合有沒有跑過檢查」與「有沒有派出 verify 類 role」。

## Requirements (EARS)

### A：條款共用

- **A1**：Codex 的 main session 條款 shall 由 `core/policy/` 產生，與 Claude 相同的
  條款集合。
- **A2**：host 之間允許不同的只有三類，全部放在該 host 的 binding、frame 或
  addenda：工具與參數的名稱（placeholder）、model 與 tier 的綁定、該 host 特有的
  調校參數。Codex 的 Luna／Sol／Astra 分層、Astra main session 模式、
  `sol-executor`、typed spawn 的傳輸細節、decision card 的接法屬於第三類。
- **A3**：共用條款與 Codex 舊條款矛盾時，以共用條款為準：main 不自己改檔；role
  派不出去時回報使用者，不由 main 接手；長指令交給 `watcher`；研究用兩個
  `researcher`。
- **A4**：host 做不到的條款 shall 在 binding 的 `omit` 明列理由（例：Codex 不允許
  呼叫端指定子 agent 的 effort，所以省略「每次派工帶 effort」）。required 條款不可
  省略。
- **A5**：常駐的 bootstrap 對每個 host 都要放得進該 host 現有的大小上限；放不下
  時縮短共用文字，不提高上限（沿用 2026-10-10 對 `watcher` 的決定）。
- **A6**：Codex 的切換以 prompt lock 的一次性 migration 進行，附逐節對照表
  `docs/specs/core-policy/equivalence/codex.md`；表中的「行為變更」不再要求為空，
  但每一項都要列出並標明是 A3 的預期變更。

### B：完成前的檢查

- **B1（條款）**：常駐的 bootstrap shall 要求：回報完成前，寫明本回合做了哪些驗證
  與結果、哪些檢查沒有跑；沒有證據的說法要標為未驗證。
- **B2（guard 記錄）**：guard shall 逐回合記錄三件事：有沒有發生改檔（可寫的 role
  已派出或啟動，或 main 的改檔被放行）；最後一次改檔之後有沒有 verify 類 role
  （`verifier`、`watcher`）被派出或啟動；最後一次改檔之後 main 有沒有執行過前景
  shell 指令。
- **B3（gate）**：When main 要結束一個發生過改檔的回合，而最後一次改檔之後既沒有
  verify 類 role、也沒有 main 的前景 shell 指令，the guard shall 擋下這次結束一次，
  訊息要求補做驗證，或在回報中明寫未驗證。同一回合只擋一次；讀不到資料、payload
  不合預期、或 host 表示這已是被擋後的重試時一律放行。
- **B4（適用 host）**：B2、B3 在 Claude 與 Codex 啟用。其他 host 在有對應的結束
  事件前不啟用，並在文件寫明。
- **B5（逐句核對）**：多切片工作的收尾，`verifier` 除了現有的方向檢查，shall 拿
  main 的回報草稿逐句核對，標出沒有證據支持的句子；main 修正後才回報。
- **B6（對設計本身提問）**：方向檢查 shall 多回答一題：已核准的設計中哪一個前提
  最可能是錯的，以及用什麼便宜的方法可以驗證。原因：現有的方向檢查只比對「有沒有
  偏離 spec」，擋不住 spec 本身的前提有問題。

### C：其他 host

- **C1**：agy 與 OpenCode 在 Codex 完成並實測後，以同樣方式改由 core 產生條款，並
  各自實測。Miyago 2026-10-13 更正：agy 有訂閱；OpenCode 是路由，接的是已有的
  provider（本機設定有 openai 等），兩者都能實測，本機也都有可用的 CLI
  （`agy` 1.3.3、`opencode` 1.18.31 的 `opencode run`）。OpenCode 目前沒有任何條款的
  掛載點，需要先建立。
- **C2**：Grok 同樣改由 core 產生條款；能不能實測以當時是否有可用的訂閱為準，
  不能實測時驗收只到 render 與測試，並在文件寫明。

## Decisions

- **D1**：推翻 `core-policy` 的「持平優先」與「不做 P3」。原因：Miyago 的原則是規則
  共用；2026-10-06 擔心的「同質化」指的是把 role 形狀與工具綁定抹平，不是共用規則。
  `docs/DESIGN-INVARIANTS.md` 第 4 條改為：「規則與策略由 core 定義，所有 host
  共用。host 的 adapter 只放三類內容：工具與參數名稱、model 綁定、該 host 特有的
  調校參數。host 做不到的條款明列省略理由。」
- **D2**：順序是 Codex、agy、OpenCode、Grok。Codex 的舊條款最長、矛盾最多，先做
  可以把共用條款的缺口一次找出來；agy 已經有 bootstrap 加 skill 的分法，最接近
  Claude；OpenCode 要先建立掛載點；Grok 的實測條件最不確定，放最後。
- **D3**：B3 的證據門檻刻意放低（任何一個前景指令都算）。原因：gate 只擋一次，
  目的是讓「完全沒檢查就宣告完成」多一步；判斷指令是不是測試需要猜，會變成另一個
  分類器。講過頭的問題交給 B5 的逐句核對。
- **D4**：B2、B3 寫在共用的 `hooks/shoal_guard.py`，不擴充 Codex 專用的
  `shoal_autoroute_gate.py`。原因：規則共用。
- **D5**：實作 B3 前，先各用一次真實執行取得 Claude 與 Codex 的 Stop payload 形狀
  （repo 內 Claude 沒有紀錄、Codex 只有測試自己組的樣本），不靠猜。

- **D6（2026-10-13 的 payload 實測）**：各用一次真實執行取得 hook payload 的形狀
  （Claude Code 2.1.x、codex-cli 0.160.1）：
  - Claude `Stop`：`session_id`、`prompt_id`、`transcript_path`、`stop_hook_active`
    （bool）、`last_assistant_message`、`background_tasks`（list）、`session_crons`、
    `permission_mode`、`effort`、`cwd`。
  - Codex `Stop`：`session_id`、`turn_id`、`transcript_path`、`stop_hook_active`
    （bool）、`last_assistant_message`、`model`、`permission_mode`、`cwd`。
  - Codex 的派工工具是 `collaborationspawn_agent`（`tool_input`：`agent_type`、
    `task_name`、`message`），而且有 `PostToolUse`（帶 `tool_response`）；subagent
    自己的工具呼叫帶 `agent_id` 與 `agent_type`，main 的沒有。
  - 同一次實測中 Codex 以預設 model 派出 `applier`，role 正常啟動並完成修改。
    2026-10-12 那幾次 role 啟動失敗沒有重現；當時 main 是以命令列指定的 model 執行。

## Slices

| # | 內容 | 驗收 |
|---|---|---|
| S1 | D1：不變式第 4 條、`core-policy` 與 `milestone-direction-check` 的修訂註記 | 文件與釘住文字的測試 |
| S2 | B1、B5、B6：條款與 `verifier` contract | render 檢查、core policy 測試；bootstrap 仍在各 host 上限內 |
| S3 | D5、B2、B3、B4：取得 Stop payload；guard 記錄與 gate；Claude、Codex 的 hook 註冊 | guard 向量；Claude、Codex 各實測：改檔後直接結束被擋一次、有檢查時不擋 |
| S4 | A1–A6：Codex 條款改由 core 產生、addenda、對照表、lock migration | render 與測試；對照表逐項列出行為變更；Codex 實測三題 |
| S5 | C1：agy 改由 core 產生條款 | render 與測試；agy 實測三題 |
| S6 | C1：OpenCode 建立條款掛載點並改由 core 產生 | render 與測試；OpenCode 實測三題 |
| S7 | C2：Grok 改由 core 產生條款 | render 與測試；有訂閱時實測 |
| S8 | 版本、CHANGELOG、本機同步；`verifier` 做方向檢查並逐句核對最終回報 | CI 三個平台通過 |

每個 host 切換各自一個 commit。live 實測預估 Claude 與 Codex 12 次以內，agy 與
OpenCode 各 5 次以內。

## Non-goals

- 不改 Codex 的 model 分層與 Astra 模式的內容，只把它們移到 addenda。
- 不做判斷「指令是不是測試」的分類。

## Risks

- **Codex 可能被卡住。** 2026-10-12 的實測中 Codex 的 role 沒能啟動，main 是靠舊
  條款的「由 main 接手」才把題目做完。A3 拿掉這條後，role 啟動不了時 Codex 只能
  回報。2026-10-13 以預設 model 重測時 role 正常啟動（D6），失敗的原因仍未確認。
  S4 的實測若再出現 role 啟動不了，就不切換 Codex，回來檢討。
- Codex 的使用者升級後行為會明顯改變（main 不再自己改檔）。CHANGELOG 要寫明。
- bootstrap 放不下：Claude 的常駐文字現在 3046 bytes，Codex 的上限是 3000，而 B1
  還要加一句。S2 要先縮短。
- B3 會多擋一次結束。每回合最多一次；若實測顯示它擋到不該擋的情況（例如只改文件），
  回來調整條件。
- hook 註冊變更後，Codex 要再用 `/hooks` 核准一次。

## Open questions

無。需要 Miyago 核准的是 D1（推翻 2026-10-06 的決定）與 A3（Codex 行為改變）。
