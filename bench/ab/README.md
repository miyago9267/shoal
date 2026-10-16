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
`--keep-workdirs`、`--auth auto|token|keychain`、`--claude-bin`、`--tasks-dir`。

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
    擋掉 user settings（hooks、enabledPlugins、output style），`--strict-mcp-config` 擋 MCP，
    並清掉 `CLAUDE_CODE_*` / `ANTHROPIC_*` 環境變數。
  - macOS 上只設 temp `CLAUDE_CONFIG_DIR` 會讀不到 keychain login（實測回
    `Not logged in`），所以 token mode 一定要有 token。
- 2026-10-16 實測 keychain mode（CLI 2.1.301）：init 只有兩個 shoal plugin 與 CLI 內建
  plugin，沒有 user skills、沒有 MCP，hook 只有 shoal 的 SessionStart；auto-memory 路徑是
  temp cwd 專屬的新目錄。`~/.claude/CLAUDE.md` 是否被載入無法從 init 確認，
  需要完全隔離時用 token mode。

## 評分欄位

`pass`、`hidden`、`visible`、`protected_violations`、`changed_files`、`files_changed`、
`lines_added`、`lines_removed`、`total_cost_usd`、`duration_ms`、`num_turns`、`wall_s`、
`claude_rc`、`error`。
