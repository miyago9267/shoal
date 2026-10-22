---
spec: text-first
created: 2026-10-22
---

# Progress: Text first

> Spec: `docs/specs/text-first/SPEC.md`

## Phase 0: Spec 與量測

> Status: in-progress

- 目標：記錄基準、確認每個消費者，取得 Miyago 對 Open Questions 的決定。
- 2026-10-23 量測（main `863943c`）：
  - 全套測試 1915 個、297 秒、OK（skipped=1）。
  - 死檔 53 個（155,618 bytes），粗暴刪除造成 35 個失敗或錯誤。
  - 移除 `bench/` 後 28 個測試模組無法 import。
  - 對 main archive 全部 host `--write` 後，9 個輸出目錄與 working tree
    `diff -r` 皆相同（等價證明的基準）。
- 2026-10-23 rebase 到 main `8da4d0f`（PR #34 只刪 `docs/archive`、
  `docs/assets/reel-*`；`tools/`、`tests/`、`hosts/`、`core/` 無變動，量測仍有效；
  `docs/benchmarks` 仍存在）。
- 2026-10-23 決定（Miyago）：P3b 納入本案，排在 P3a 之後（含 lock renewal 與
  dotfile 修改；R 的 push 前須告知 Miyago）；P4 bench 拆分已核准，最後執行
  （P1 到 P3b 輸出逐位元組相同之後）；CI paths 補齊與獨立 `render --check`
  放 P1。plan-critic REVISE 的三項 blocker 已併入 spec。
- 待決：無。

## Phase 1: 刪除死檔

> Status: not-started

- 目標：53 檔刪除、R3 防回歸、`render_equiv.py`。
- 基準雜湊：（P1 開始時由 `render_equiv.py` 填入）

## Phase 2: 文字搬到 `prompts/`

> Status: not-started

- 目標：R1、R2。
- 記錄：`migrate_text.py` 相等斷言結果、`render_equiv.py` 總雜湊。

## Phase 3a: 停止 commit golden、收斂測試

> Status: not-started

- 目標：R4（golden）、R6。
- 記錄：triage 表（每個測試 keep / drop / convert 與理由）、測試數與行數
  前後對照。

## Phase R + 3b: lock renewal 與停止 commit claude dist

> Status: not-started（2026-10-23 已核准；排在 P3a 之後、P4 之前）

- 記錄：renewal commit sha、告知 Miyago 的時間、CI lock 步驟結果、dotfile
  修改 commit。

## Phase 4: bench 拆出

> Status: not-started（已核准 2026-10-23；最後執行，P1 到 P3b 完成後）

- 目標：R7。
- 記錄：`filter-repo` 路徑清單、shoal-bench 初始 commit sha、兩邊測試結果。

---

## Completed Phases

<!-- Phase 完成後用 spec-archive.sh phase <slug> 將 phase block 搬到 archive/ -->
<!-- 這裡只留已封存 phase 的簡要記錄 -->
