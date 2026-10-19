# code-restructure：TASKS

每完成一項就更新；狀態 `[ ]` 未做、`[x]` 完成。階段順序與驗收見 SPEC.md。

## P0 量測與 characterization

- [ ] T0.1 `tests/bench_hook_latency.py`：對 `run.sh` 入口各 200 次 `SessionStart`、`PreToolUse(Bash)`、`PreToolUse(Edit)`，輸出 p50 / p95（只服務 P1 前後對照）
- [ ] T0.2 在現有 code 上量 baseline，數字寫入 PROGRESS.md
- [ ] T0.3 在現有 code 產生 `tests/fixtures/adapter_golden.json`：每個 host、現有 shape fixtures（`tests/fixtures/*payload_shapes*.json`、`claude_subagent_tool_shapes.json`、opencode/grok shapes）與 `guard_vectors.json` 的每個 payload -> `adapt_*` 回傳的完整 dict（含 None）；main 上綠、改一個 tool-name 對照會轉紅
- [ ] T0.4 列出 `install.py` 全部 `InstallAbort` 訊息，缺 test 的補上
- [ ] T0.5 `install_hooks.apply_codex` characterization golden，輸入矩陣：無檔、空 hooks、只有 user group、user group + 舊 shoal group v1..v5、autoroute group 存在、command=None 移除

## P1 guard 單檔內整理（plan-critic 前置）

- [ ] T1.1 host 集合改單表，舊名稱由表衍生
- [ ] T1.2 三個 adapter 改 `AdapterSpec` 加共用 `adapt()`；`adapt_agy` 保持獨立；新輸出對 adapter golden 每筆 assertEqual，P1 不編輯 golden
- [ ] T1.3 `_new_state` 取代 `_locked` 內三份 literal，輸出 JSON 與現在位元組相同
- [ ] T1.4 `_open_nofollow` 合併 `_open_private` / `_open_readable`
- [ ] T1.5 docstring 縮成指標
- [ ] T1.6 重新產生 guard dist 副本與 `.sha256`；共同驗收 + 延遲 + fresh `verifier`

## P3 hook 登記收斂

- [ ] T3.2 `apply_codex` 改呼叫 `merge_registration`，輸出與 T0.5 golden 位元組相同；與 `install()` 的一致性測試只比 guard group 子集
- [ ] T3.3 共同驗收
- [ ] T3.4 `sync_global --json` 對同一 home 的 plan，`changes` 在 P3 前後相同

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

O1、O2、O3、O5、O6 已解決；待決 O4、O7、O8 見 SPEC.md「Open questions」。
