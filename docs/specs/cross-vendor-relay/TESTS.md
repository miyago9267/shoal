# cross-vendor-relay：TESTS（EARS）

編號前綴 S- 以區別 TASKS.md 的任務編號；S1.x 對應 P1。「SHALL」為驗收條件。

## 通則

- S0.1 WHEN P1 的變更完成，THE SYSTEM SHALL 通過
  `python3 -m unittest discover -s tests`。
- S0.2 WHEN P1 的變更完成，THE SYSTEM SHALL 讓
  `python3 tools/render.py --check` 對所有 host 與 claude-plugin 通過。
- S0.3 WHERE binding 沒有 `[relay.roles]`，THE SYSTEM SHALL 產出與變更前位元組相同的
  dist（relay 關閉時零影響）。guard 的逐字副本（
  `hosts/grok/dist/hooks/shoal-grok/shoal_guard.py`、
  `plugins/claude-guard/hooks/shoal_guard.py`）隨 S1.11 的 guard 變更而更新，
  不在此條範圍；其行為不變由 S0.4 保證。
- S0.4 THE SYSTEM SHALL NOT 讓 `tests/fixtures/guard_vectors.json` 與
  `adapter_golden.json` 的任何既有結果改變。

## Runner（P1）

- S1.1 WHEN runner 以 vendor codex、role executor 執行，THE SYSTEM SHALL 組出
  包含 `exec --json --output-schema <schema> -o <file> --sandbox
  workspace-write -C <cwd>` 的指令，且 stdin 為 `/dev/null`。
- S1.2 WHEN role 的 access 為 `read-only`，THE SYSTEM SHALL 使用
  `--sandbox read-only`；WHEN 任一 access level，THE SYSTEM SHALL 在 argv 帶上
  D6 的固定旗標（approval never、writable_roots 為空、network 關閉、MCP 關閉）；
  THE SYSTEM SHALL NOT 在任何情況下產生 `danger-full-access` 或 bypass 類旗標。
- S1.2a WHEN runner 組 brief，THE SYSTEM SHALL 在開頭放入 D7 的 named role 標記。
- S1.3 IF vendor 以 exit 0 結束但 `-o` 檔不存在、為空或不符 schema，THEN THE
  SYSTEM SHALL 回傳 `status: failed` 並註明原因。
- S1.4 IF vendor 超過 wall-clock 上限，THEN THE SYSTEM SHALL 結束整個 process
  group，並回傳 `status: failed`、原因 timeout 與已取得的部分輸出。
- S1.5 IF vendor binary 不存在或回報未登入，THEN THE SYSTEM SHALL 回傳
  `status: blocked` 與原因，且不改用 native 執行。
- S1.6 WHEN vendor 以非 0 結束，THE SYSTEM SHALL 回傳 `status: failed`、exit
  code 與 stderr 最後 20 行。
- S1.7 THE SYSTEM SHALL 讓 runner 的 stdout 只包含一份符合
  `handback.schema.json` 的 JSON，且不含任何環境變數值或 credential。

## Render（P1）

- S1.8 WHEN binding 寫 `executor = "codex"`，THE SYSTEM SHALL 產出名為
  `executor` 的 subagent，內容以
  `${CLAUDE_PLUGIN_ROOT}/tools/shoal_relay.py` 呼叫 runner，模型等於 binding
  的 `[relay] shell_model`，tools 等於 `["Bash"]`（F8）；IF plugin 輸出缺少該
  runner 檔，THEN `render --check` SHALL 失敗。
- S1.9 IF `[relay.roles]` 指定 security role（`security-reviewer`、
  `security-executor`）或 `core/vendors.toml` 沒有的 vendor，THEN render SHALL
  失敗並說明原因。
- S1.10 WHEN relay 的 role 為 write access，THE SYSTEM SHALL 在外殼與 policy
  中要求以 worktree 隔離派工。

## Guard 與 doctor（P1）

- S1.11 WHEN host 為 codex、`SHOAL_RELAY_ROLE` 屬於 {executor, applier}、且
  guard_dir 下有對應 `SHOAL_RELAY_NONCE` 的檔，THE SYSTEM SHALL 把整個 session
  視為該 named role：允許改檔、不要求派工、不允許再派 subagent。IF 只有 env
  沒有 nonce 檔，或 host 不是 codex，THEN 行為與變更前相同（新增 guard vectors
  覆蓋，既有 vectors 不變）；採用與忽略都寫 log。WHEN 該 session 呼叫
  `spawn_agent` 或其他派工工具，guard SHALL 拒絕。

## Security（P1，對應 SPEC Security review）

- S1.14 IF `realpath(cwd)` 不是 linked worktree，或 role 不屬於
  {executor, applier}，THEN runner SHALL 回 `blocked` 且不 spawn vendor（F1）。
- S1.14a IF worktree 內存在 `.codex/`，THEN runner SHALL 回 `blocked` 且不
  spawn vendor（F3）。
- S1.15 WHEN runner spawn vendor，THE SYSTEM SHALL 只傳 env allowlist 內的變數，
  並帶上 F2、F6 的 pin；用假 binary 斷言 child env 與 argv（F2、F6）。
- S1.16 THE SYSTEM SHALL NOT 讓 fixture 裡的 secret 值出現在 runner stdout，含
  部分輸出與 stderr 尾段（F7）。
- S1.17 WHEN 回傳 hand-back，THE SYSTEM SHALL 以 `git status --porcelain -z`
  計算 `changed_files`；vendor 自報路徑剝掉 `(deleted)` 類註記與 `./`、`a -> b`
  兩邊都算後仍不一致時標出、不改 status；schema 拒絕額外欄位與超長字串（F8）。
- S1.18 WHEN runner 逾時或收到 SIGTERM/HUP/INT，THE SYSTEM SHALL 結束所有後代
  程序，包括 setsid 且忽略 SIGTERM 的孫程序；事後沒有殘留（F9）。
- S1.19 IF vendor 回報 sandbox 套用失敗，THEN runner SHALL 回 `failed`，且
  SHALL NOT 以放寬的 sandbox 重跑（F10）；IF brief 為 symlink、非一般檔案或超過
  大小上限，THEN runner SHALL 拒絕（F11）。
- S1.20 WHEN T1.0 在 relay 中跑 canary，寫 worktree 外、寫 `/tmp`、`curl`、
  `spawn_agent`、列 MCP tools、觸發 repo 內 `.codex/hooks.json` SHALL 全部失敗，
  `env` 輸出不含 secret 名稱（F2、F3、F6）。
- S1.12 WHEN 執行 doctor，THE SYSTEM SHALL 回報 vendor binary 路徑、版本是否 ≥
  `core/vendors.toml` 的最低版本、登入狀態，並在 `OPENAI_API_KEY` 或
  `ANTHROPIC_API_KEY` 存在時警告計費方式改變，且不印出其值。

## 效益（P1）

- S1.13a WHEN 執行 `run_ab.py --arms shoal,shoal-relay --dry-run`，THE SYSTEM
  SHALL 顯示兩個不同的 plugin-dir，且 `shoal` arm 的 relay 為關閉。
- S1.13 WHEN bench/ab 以 v2 任務比較 `shoal-relay` 與 `shoal`，THE SYSTEM SHALL
  使 relay 的通過數 ≥ shoal 的通過數減 1、時間中位數 ≤ shoal 的 2.0 倍；兩家的
  token / 成本分開記錄。未達標時 P2 不開始。
  （2026-10-22 Miyago 決定放寬，原為通過數 ≥ shoal 且 ≤ 1.5x）
