# code-restructure：TASKS

每完成一項就更新；狀態 `[ ]` 未做、`[x]` 完成。階段順序與驗收見 SPEC.md。

## P0 量測與 characterization

- [x] T0.1 `tests/bench_hook_latency.py`：對 `run.sh` 入口各 200 次 `SessionStart`、`PreToolUse(Bash)`、`PreToolUse(Edit)`，輸出 p50 / p95（只服務 P1 前後對照）
- [x] T0.2 在現有 code 上量 baseline，數字寫入 PROGRESS.md
- [x] T0.3 在現有 code 產生 `tests/fixtures/adapter_golden.json`：每個 host、現有 shape fixtures（`tests/fixtures/*payload_shapes*.json`、`claude_subagent_tool_shapes.json`、grok shapes）與 `guard_vectors.json` 的每個 payload -> `adapt_*` 回傳的完整 dict（含 None）；main 上綠、改一個 tool-name 對照會轉紅
- [x] T0.4（部分：136 種訊息模板已凍結；逐字行為測試約 36 種，其餘留待 T4.2 前補） 列出 `install.py` 全部 `InstallAbort` 訊息，缺 test 的補上
- [x] T0.6 Security 回歸測試 S1.5（Workflow 恆為 None）、S1.6（predicate 案例，加入 T0.3 golden 輸入）、S1.9（舊集合 literal、opencode 不在 HOST_DEFAULT_MODE）；在現有 code 全綠，且先於任何 P1 code 變更
- [x] T0.7 另開 security follow-up issue：F9（O_NONBLOCK、chain manifest uid 檢查），P1 不處理（issue #26）

## P1 guard 單檔內整理（plan-critic 前置）

- [x] T1.1 host 集合改單表，舊名稱由表衍生
- [x] T1.2 三個 adapter 改 `AdapterSpec` 加共用 `adapt()`；`adapt_agy` 保持獨立；新輸出對 adapter golden 每筆 assertEqual，P1 不編輯 golden
- [x] T1.3 `_new_state` 取代 `_locked` 內三份 literal，輸出 JSON 與現在位元組相同
- [x] T1.4 （已移除：`_open_private` / `_open_readable` 維持分開，見 SPEC F1）
- [x] T1.5 docstring 縮成指標
- [x] T1.5a S1.7、S1.8、S1.10 加入並全綠；P1 由 `security-executor` 實作
- [x] T1.6 重新產生 guard dist 副本與 `.sha256`；共同驗收 + 延遲 + fresh `verifier`（verifier 由 main 另派）

## P4 install.py 拆函式

- [x] T4.1 `_Plan` dataclass 與 `install()` 步驟函式
- [x] T4.2 `_validate_committed_state` 拆檢查函式
- [x] T4.3 共同驗收；`test_install` 斷言不改

## P5 render.py 資料化

- [ ] T5.1 `HostSpec` 與共同 `render_roles`；claude、agy 先轉（不做：2026-10-19 Miyago 決定丟掉，查表化反而 +38 行）
- [ ] T5.2 grok、codex 部分轉；opencode 只共用 validate（不做：2026-10-19 Miyago 決定丟掉，查表化反而 +38 行）
- [ ] T5.3 保留 `validate_*` / `render_*` 薄包裝；golden 全部不變（不做：2026-10-19 Miyago 決定丟掉，查表化反而 +38 行）
- [ ] T5.4 共同驗收（不做：2026-10-19 Miyago 決定丟掉，查表化反而 +38 行）

## Open questions（待 Miyago）

O1、O2、O3、O5、O6 已解決；待決 O4、O7、O8 見 SPEC.md「Open questions」。
