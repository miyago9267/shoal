---
title: 補齊泛用化的最後缺口
status: approved
approved_by: Miyago
created: 2026-10-06
updated: 2026-10-06
---

<!-- markdownlint-disable MD025 -->

# 補齊泛用化的最後缺口

## Background

Miyago 2026-10-06 要求補上「泛用版 pilotfish」剩下的四個缺口。缺口 1（policy
共用）拆到 [core-policy](../core-policy/SPEC.md)，本 spec 處理缺口 2 到 4。
現況（main `7bed030` 查證）：

1. **Policy 各 host 各一份**：見 core-policy。
2. **強制力不一致**（`docs/specs/dispatch-enforcement`）：Claude、OpenCode
   enforce；Grok、Codex 停在 shadow（額度與使用量）；agy 無法辨識 subagent，
   固定 shadow。
3. **沒有 Claude Plugin 打包**。上游 pilotfish v1.4.2 有 Plugin beta
   （`.claude-plugin/marketplace.json`、`plugin/agents/`、`plugin/hooks/hooks.json`
   以 SessionStart 注入 policy）。shoal 的 Claude host 只能靠 dotfile 安裝。
4. **Claude guard 漏管接續的回合**。2026-10-06 log 有兩筆
   `skip_reason=missing_id`：DQOP session 執行 `/login` 後，沒有新的使用者
   prompt 就接續上一輪，`UserPromptSubmit` 與後續工具事件都沒有 `prompt_id`，
   guard 因此略過。

## Requirements (EARS)

### F：強制力補齊

- **F1（Grok、Codex）**：shall 依 dispatch-enforcement 的 E6 條件，在額度
  允許時累積 shadow 決策並切 enforce。本 spec 只提供重跑腳本與判定工具，
  實際切換時間依 Miyago 安排。
- **F2（agy）**：shall 先實測能否辨識 subagent。只接受單一 payload 內的正向
  證據（例如 `transcriptPath` 的 subagent 路徑形狀）；跨 conversation 的相關性
  推斷（invoke_subagent 之後出現的新 `conversationId`）不得單獨作為依據，
  判斷不明一律當 main。能可靠辨識就解除 R5 的固定 shadow，走 E6 條件；
  不能就維持 shadow 並記錄證據。

### K：Claude Plugin

- **K1（打包）**：shoal shall 產生 Claude plugin：`.claude-plugin/marketplace.json`
  與 plugin 目錄（agents、orchestration skill、hooks）。內容由 render 從
  `hosts/claude/dist` 產生，`--check` 驗證，不手改。
- **K2（hooks）**：plugin 的 hooks 含 dispatch guard（`UserPromptSubmit`、
  `PreToolUse`）與 SessionStart 的 policy bootstrap 注入。
- **K3（namespace）**：plugin agent 名稱帶 namespace（例如 `shoal:executor`）。
  guard shall 以明確的白名單辨識名稱：裸名稱與 `shoal:` 前綴兩種，派工端
  （解鎖）與 subagent 端（LEAF、VERIFY_EDIT）都要正規化；不得只取 `:` 後綴
  比對，`x:executor` 等其他 namespace 不解鎖。
- **K4（不重複）**：When plugin 與 dotfile／`install_hooks.py` 的全域安裝同時
  存在，the guard shall 每個事件只判斷一次：plugin 那份只在 effective
  settings 確實有 `install_hooks.py` 擁有的 entry、而且該 script 存在時才
  no-op，其他情況照跑（不得變成 0 次）。state 的讀改寫加 `flock`，避免並行
  遺失。SessionStart 另外提示衝突，僅供參考。
- **K5（信任來源）**：marketplace 釘到 tag 或版本，不追預設 branch；hook
  command 寫成 `python3 "${CLAUDE_PLUGIN_ROOT}/..." --host claude`，路徑一律
  加引號；SessionStart script 固定 `PATH`。
- **K6（資料保留）**：plugin 與全域安裝共用同一個 state 與 log 目錄；log 維持
  1 MiB 上限，uninstall 不刪 state 與 log，文件寫明清除方式
  （`${XDG_STATE_HOME:-~/.local/state}/shoal/guard/`）。

### M：missing_id

- **M1**：Claude 的工具事件缺 `prompt_id` 時，shall 沿用該 session state 的
  turn（與 grok、agy 相同），不再略過。缺 `prompt_id` 的 `UserPromptSubmit`
  shall 清除 `dispatched`（fail-closed），保留 turn 與 `edited`，使接續的回合
  不會沿用先前派工的解鎖；state 不存在時一律不解鎖。

## Non-goals

- 不改 role 定義、選模與權限推導。
- 不追上游 pilotfish 的新版本（只參考 Plugin 結構）。
- 不在本 spec 內強制 Grok、Codex 的切換時間（F1 只到工具與流程）。
- 不處理經 shell 寫檔的偵測（dispatch-enforcement 的已知限制）。

## Decisions

1. **Plugin 是第二條安裝路徑**：Miyago 自己維持 dotfile 路徑；plugin 給沒有
   dotfile 的使用者。兩者互斥由 K4 處理；K4 判斷全域 entry 時以 settings 檔
   位置區分，不能只用 `install_hooks.py` 的 `OWNED` regex（plugin 的 command
   也會符合）。
2. **順序**：M（小，獨立）→ K → F2。F1 隨額度執行。

## Phases

| Phase | 內容 | 驗收 |
|---|---|---|
| M | Claude 工具事件缺 id 時沿用 session state；缺 id 的 prompt 清除 `dispatched` | 向量：派 executor 後接無 id 的 prompt，再無 id 地改第 3 個檔要 deny R2；Python 與 TS 重播通過 |
| K1 | Claude plugin 產生與 `--check` | render 產生 plugin 目錄、golden、`claude plugin validate`（若可用）通過 |
| K2 | plugin 的 guard 與 SessionStart、namespace、互斥、flock | temp `CLAUDE_CONFIG_DIR`（路徑含空白）安裝 plugin 後，guard deny 與派 `shoal:executor` 後 allow 各一筆；`shoal:verifier` 加 Edit 為 VERIFY_EDIT deny，`x:executor` 不解鎖；只有 plugin、plugin 加全域、plugin 加壞掉的全域三種情境，每個事件剛好一筆 log |
| F2 | agy subagent 辨識實測 | 結果表與決定；A conversation 呼叫 invoke_subagent 後，B 的第一個編輯仍當 main 評估 |
| F1 | Grok、Codex 的 E6 | 依 dispatch-enforcement Open question 1 |

## Rollback

- Plugin：`claude plugin uninstall`；dotfile 路徑不受影響。
- M：revert 對應 commit。

## Open questions

1. **（已決定，2026-10-06）Plugin 的發佈位置**：shoal repo 根目錄的
   `.claude-plugin/`，與上游相同；Codex 的 `plugin/` 目錄維持不動。
