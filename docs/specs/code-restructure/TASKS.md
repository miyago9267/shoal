# code-restructure：TASKS

每完成一項就更新；狀態 `[ ]` 未做、`[x]` 完成。階段順序與驗收見 SPEC.md。

## P0 量測與 characterization

- [ ] T0.1 `tests/bench_hook_latency.py`：對 `run.sh` 與直接執行兩種入口，各 200 次 `SessionStart`、`PreToolUse(Bash)`、`PreToolUse(Edit)`，輸出 p50 / p95
- [ ] T0.2 在現有 code 上量 baseline，數字寫入 PROGRESS.md
- [ ] T0.3 補四個 host 的 adapter shape fixture（缺的才補），讓 adapter table 化有 Red 可寫
- [ ] T0.4 列出 `install.py` 全部 `InstallAbort` 訊息，缺 test 的補上
- [ ] T0.5 Codex `hooks.json` 兩條寫入路徑（`install()` 與 `install_hooks.apply_codex`）的輸出對照 test；結果回報 O3

## P1 guard 單檔內整理（plan-critic 前置）

- [ ] T1.1 host 集合改單表，舊名稱由表衍生
- [ ] T1.2 三個 adapter 改 `AdapterSpec` 加共用 `adapt()`；`adapt_agy` 保持獨立
- [ ] T1.3 `_new_state` 取代 `_locked` 內三份 literal，輸出 JSON 與現在位元組相同
- [ ] T1.4 `_open_nofollow` 合併 `_open_private` / `_open_readable`
- [ ] T1.5 docstring 縮成指標
- [ ] T1.6 共同驗收 + 延遲 + fresh `verifier`

## P2 package 與 bundle（plan-critic 前置；先由 Miyago 回答 O1、O2）

- [ ] T2.1 `install/guard_bundle.py`（`bundle_files`、`bundle_digest`）加 unit test
- [ ] T2.2 搬模組（hosts、messages、state、policy、shell、guard、subagents、agy、completion、decide、chain、adapters、globalguard、cli、`__init__`），一次搬一個，每個都跑 vectors
- [ ] T2.3 薄入口 `hooks/shoal_guard.py`；`__init__` 匯出 `main`
- [ ] T2.4 `render.py`：`_guard_files`；`write_dist` / `--check` 清掉 dist 內多餘檔案
- [ ] T2.5 golden：bundle manifest；`render_helpers` 的 `GOLDEN_HASHED` / `GUARD_SOURCE` / `setUp`
- [ ] T2.6 `install_grok.check_guard_single_source`、`shoal_update` 的 verify / marketplace 比對
- [ ] T2.7 `install_hooks.py`：staging 加 rename 安裝 bundle；uninstall 移除 bundle
- [ ] T2.8 `install.py`：Codex bundle 安裝、fingerprint 改 `bundle_digest`、舊單檔 fingerprint 的升級路徑
- [ ] T2.9 `install/modules.json`、`test_py39_compat`、掃原始碼的測試改走 bundle
- [ ] T2.10 延遲驗收（超標則加 lazy import）；共同驗收；fresh `verifier`

## P3 hook 登記收斂

- [ ] T3.1 搬 `apply_claude`、`apply_agy`、`set_groups`、`strip_owned_groups`、`is_owned`、regex、`portable_command_for` 到 `hook_registration.py`
- [ ] T3.2 `apply_codex` 改呼叫 `merge_registration`（依 O3 結果）
- [ ] T3.3 `install_hooks.py` 只留 CLI 與 I/O；`sync_global` / `shoal_install` 呼叫不變
- [ ] T3.4 共同驗收

## P4 install.py 拆函式

- [ ] T4.1 `_Plan` dataclass 與 `install()` 步驟函式
- [ ] T4.2 `_validate_committed_state` 拆檢查函式
- [ ] T4.3 共同驗收；`test_install` 斷言不改

## P5 render.py 資料化

- [ ] T5.1 `HostSpec` 與共同 `render_roles`；claude、agy 先轉
- [ ] T5.2 grok、codex 部分轉；opencode 只共用 validate
- [ ] T5.3 保留 `validate_*` / `render_*` 薄包裝；golden 全部不變
- [ ] T5.4 共同驗收

## Open questions（待 Miyago）

O1 到 O8 見 SPEC.md「Open questions」。P2 開工前必須有 O1、O2 的答案；P3 開工前要有 O3 的對照結果。
