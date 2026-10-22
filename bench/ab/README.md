# shoal A/B benchmark

每個 task 跑兩次：`shoal` arm（載入 shoal plugins）與 `baseline` arm（不載入），
兩邊用同一套評分。Runner 是 `run_ab.py`（Python 3 stdlib）。

## Task 契約

`tasks/<id>/`：`repo/`（起始專案）、`task.md`（prompt）、
`hidden_tests/test_accept.py`（含 `__init__.py`）、
`meta.json`（`{"id","category","protected":[globs],"timeout_s"}`）、`solution.patch`。
`meta.json` 可選 `visible_cmd` / `hidden_cmd` 覆寫預設的 unittest discovery。

## 用法

```sh
python3 bench/ab/run_ab.py --self-test                 # 不呼叫 claude，驗 fixtures
python3 bench/ab/run_ab.py --dry-run --model <id>      # 只印計畫與指令
python3 bench/ab/run_ab.py --tasks all --arms shoal,baseline --reps 3 \
    --model <id> --out bench/ab/results/ab.json        # 正式跑，可中斷後重跑續跑
python3 bench/ab/run_ab.py --summarize bench/ab/results/ab.json
```

其他選項：`--max-budget-usd`（每次 run 的上限）、`--retry-errors`（重跑帶 error 的紀錄）、
`--keep-workdirs`、`--keep-failed`（只保留沒通過的 run 的工作目錄）、`--auth auto|token|keychain`、`--claude-bin`、`--tasks-dir`。

## 每次 run

1. 把 `repo/` 複製到新的 temp dir（略過 `__pycache__`），`git init` 並 commit 一次。
2. `claude -p --output-format json --model <id> --permission-mode bypassPermissions
   --setting-sources project --strict-mcp-config [--plugin-dir ...]`，prompt 走 stdin，
   cwd 是 temp repo，逾時 `timeout_s` 時整個 process group 一起 kill。
3. 先用 `git add -A && git diff --cached HEAD` 算改動（含 untracked）與 protected 違規，
   再跑 visible tests（`tests/` 存在時）、複製 `hidden_tests/` 跑 hidden tests；
   測試都設 `PYTHONDONTWRITEBYTECODE=1`。
4. `pass` = hidden 通過 且 visible 通過 且 沒有 protected 違規 且 claude 沒有 error。
5. 每次 run 結束就原子寫回 `--out`；`(task, arm, rep)` 已存在的會跳過。

## Isolation

- `shoal` arm：每次執行從 repo 的 committed HEAD 用 `git archive` 匯出
  `plugins/claude`、`plugins/claude-guard` 到 temp dir，再用兩個 `--plugin-dir` 載入；
  WIP 不會混進去，紀錄帶 `shoal_head`。
- `baseline` arm：同樣的指令，少了 `--plugin-dir`。
- Auth（`--auth auto`）：
  - 環境有 `CLAUDE_CODE_OAUTH_TOKEN` -> `token` mode：全新 `CLAUDE_CONFIG_DIR`、`HOME`、
    `TMPDIR`，只傳 `PATH`/locale，完全碰不到 `~/.claude`。
  - 否則 -> `keychain` mode：沿用使用者的 keychain login，靠 `--setting-sources project`
    擋掉 user settings（hooks、enabledPlugins、output style），
    `--strict-mcp-config` 擋 MCP，
    並清掉 `CLAUDE_CODE_*` / `ANTHROPIC_*` 環境變數。
  - macOS 上只設 temp `CLAUDE_CONFIG_DIR` 會讀不到 keychain login（實測回
    `Not logged in`），所以 token mode 一定要有 token。
- 2026-10-16 實測 keychain mode（CLI 2.1.301）：init 只有兩個 shoal plugin 與 CLI 內建
  plugin，沒有 user skills、沒有 MCP，hook 只有 shoal 的 SessionStart；auto-memory 路徑是
  temp cwd 專屬的新目錄。`~/.claude/CLAUDE.md` 是否被載入無法從 init 確認，
  需要完全隔離時用 token mode。

## shoal-relay arm

`--arms shoal,shoal-relay`：`shoal` 是 relay 關閉的對照；`shoal-relay` 把 `relay.binding.toml`
（`executor`/`applier` 走 Codex、外殼 `haiku`）接在 committed HEAD 的 `hosts/claude/binding.toml`
後面，用 `tools/render.py --host claude-plugin --write --root <temp>` render 成該 arm
自己的
plugin-dir（committed binding 不動）。`--dry-run` 會印每個 arm 的 plugin-dir 與 `relay=on|off`。

- 該 arm 用 `--output-format stream-json --verbose`，才看得到 subagent 內 Bash 印出的 hand-back；
  紀錄的 `codex` 欄位是各次 relay 的 token 加總（`calls`、`statuses`、`input_tokens`、
  `cached_input_tokens`、`output_tokens`），與 Claude 的 `total_cost_usd` 分開，不換算美元。
  `codex.handbacks` 逐次記 `status`、`reason`（沒有就用 `summary`，取前 200 字，runner 已遮蔽）、
  `landed` 與 `landing_reason`（runner 是否已把 worktree 改動落到工作目錄）。
  `codex.calls == 0` 代表 main 沒有走 relay。
- relay 寫入 role 要在 linked worktree 跑（main 以 `isolation: "worktree"` 派工）。task 工作目錄本來就是
  `git init` 過的 repo，所以可用；`.claude/worktrees/` 已加進 `.git/info/exclude`，不算改動。
- token mode 下 HOME 是私有的，runner 找不到 Codex 登入，所以該 arm 會多傳 `CODEX_HOME`
  （預設 `~/.codex`）。

## 評分欄位

`pass`、`hidden`、`visible`、`protected_violations`、`changed_files`、`files_changed`、
`lines_added`、`lines_removed`、`total_cost_usd`、`duration_ms`、`num_turns`、`wall_s`、
`claude_rc`、`error`；`shoal-relay` 另有 `relay`（plugin 是否帶 runner）與 `codex`。
