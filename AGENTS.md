# shoal repo 的 agent 指引

這份檔案給在本 repo 內工作的 agent 與貢獻者，不會安裝到使用者的機器上。

## 測試

- 迭代時只跑相關的 module 或關鍵字，例如
  `python3 tools/run_tests.py test_shoal_guard`、
  `python3 tools/run_tests.py -k relay`。
- 全套測試只在提交前跑一次：`python3 tools/run_tests.py`。它平行執行，
  預設進程數等於 CPU 數（8 核約 1 分鐘；單線程的 `python3 -m unittest discover -s tests`
  約 6 分鐘）。
- 改了 render 的輸入（`core/`、`hosts/*/binding.toml`、`prompts/`）時，另外跑
  `python3 tools/render.py --host <host> --check`。
- 測試新增了無法平行的項目（共用固定路徑、埠號或全域 state）時，把它的 test id
  前綴加進 `tools/run_tests.py` 的 `SERIAL_PREFIXES`，不要刪測試。
- 大幅改動測試後，用 `python3 tools/run_tests.py --write-timings` 更新
  `tests/timings.json`（只影響排程順序，不影響結果）。
