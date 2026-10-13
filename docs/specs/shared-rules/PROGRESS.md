# shared-rules 進度

## S1（完成，v3.4.0）

- `docs/DESIGN-INVARIANTS.md` 第 4 條改為 D1 的字句，
  `tests/test_delegation_default.py` 的釘住文字同步。
- `docs/specs/core-policy/SPEC.md` 末尾加「修訂：規則共用（2026-10-13）」，
  `docs/specs/milestone-direction-check/SPEC.md` 加註記（「同質化」指抹平
  role 形狀與工具綁定）。`core/README.md` 改指向 shared-rules；渲染器只允許
  Claude 用 core 條款的限制保留到 S4，文字已寫明。

## S2（B1、B5、B6 完成；bootstrap 上限未達）

- B1：`core/policy/bootstrap.toml` 新增 `bootstrap-verify-report`（非
  required，排在 `bootstrap-collect` 之後）。
- B5、B6：`core/contracts/verifier.toml` 新增 `checkpoint-draft-report` 與
  `checkpoint-premise`；`core/policy/extensions.toml` 的
  `direction-checkpoint` 加一句收尾時 main 把回報草稿交給檢查、修正後才回報。
  Claude 的 legacy 對照來源（`hosts/claude/src/...`）與 Codex 的
  `hosts/codex/src/agents/verifier.md` 同步，逐字拼回的測試維持通過。
  `tests/test_direction_milestone.py` 的 M2 逐字測試改為：Claude 的 core 輸出
  含新句，Codex 的 legacy 模板維持原文。
- 這句是 core 文字：五個 host 的 `verifier` 都會帶到，已重新渲染。
- 位元組（渲染後的 Claude bootstrap）：3046（v3.3.1）→ 3103。**沒有達到
  2900。** B1 約 +170，縮短其他條款約 -113，差 203。縮短的條款（前 → 後）：
  - delegate-default：「diagnosing a bug, integrating, and judging stay with
    the main session」→「diagnosing, integrating, and judging stay with
    main」；「including the same change across several files」→「also one
    change across several files」；「test suite」→「tests」。
  - routing：「Route by shape first」→「Route by shape」。
  - outcome：「stops at that boundary」→「stops there」。
  - dispatch-brake：冒號句改為括號句（「the role default, lower for trivial
    ... work」→「(role default; lower if trivial ...」）、「of every call to a
    write-capable role」→「of every write-capable call」。
  - load-skill：刪「for the full policy」、兩句併成一句。
  - 沒有動 required 條款，也沒有刪規則。再縮需要刪掉有意義的內容（剩下的都是
    被測試釘住的句子或 required 條款），選項：把 routing／outcome 兩條移到
    skill、縮減 named roles 清單的寫法，或讓 Codex 的 frame 吃掉差額。
- Prompt lock：`LOCK.json` 沒有變動；`verifier` 與 workflow-extensions 的
  大小仍在上限內（Claude verifier 90 行／6792 bytes，上限 104／7700；
  workflow-extensions 172／9457，上限 180／9600；Codex verifier 90／5702，
  上限 95／6000）。commit 不需要 `Lock-Renewal: approved`。

## S3（實作完成；live 驗收待 main 執行）

- `hooks/shoal_guard.py` 與 `hosts/opencode/plugin/src/guard/core.ts`：state
  新增 `changed`、`checked`、`stop_blocked`；`Stop` adapter（Claude：
  `prompt_id`；Codex：`turn_id`）；`STOP_HOSTS`、`SHOAL_GUARD_STOP`。向量
  `tests/fixtures/guard_vectors.json` 新增 64 筆（Python 與 TypeScript 共用）。
- 閘門條件：同一回合的 state、`changed`、非 `checked`、`stop_hook_active`
  恰為 `false`、enforce、這回合沒擋過、`SHOAL_GUARD_STOP` 不是 `off`。先把
  `stop_blocked` 寫入再輸出 block，寫入失敗就不擋。
- 前景 `Bash`（非寫檔、非宣告）只在 `changed` 已為真且未 `checked` 時才取鎖
  寫 state，其餘只讀一次 state；不寫 log。
- 註冊：`tools/render.py` 的 plugin `hooks.json`、
  `tools/install_hooks.py`（Claude `Stop`）、`install/hook_registration.py`
  （`shoal-guard-v3`；v1、v2 原地升級）。Codex 升級後要用 `/hooks` 核准一次。
- Payload 證據：`tests/fixtures/stop_payload_shapes.json`（2026-10-13 的兩次
  真實執行，只記 key 與型別）。
- **未驗證：Claude 對 `{"decision":"block","reason":...}` 的處理。** repo 內
  沒有實測紀錄；格式不被接受時 Claude 照常結束（失敗開放）。Codex 的格式
  與 `shoal_autoroute_gate.py` 相同。
- **Live 驗收尚未執行**（改檔後直接結束被擋一次、有檢查時不擋；Claude 與
  Codex 各一次），由 main 執行。已做的是以暫存 HOME 與 XDG_STATE_HOME 對
  真實形狀的 payload 手動餵給腳本。
- 未驗證：Claude 的 `Stop` 的 `prompt_id` 是否等於同一回合
  `UserPromptSubmit` 的 `prompt_id`（假設相等，不相等時完全不擋）。
