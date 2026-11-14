# local-role-model-overlay：TESTS（EARS）

編號前綴 S- 以區別 TASKS.md 的任務編號。「SHALL」為驗收條件。

## 通則

- S0.1 WHEN P1 的變更完成，THE SYSTEM SHALL 通過
  `python3 -m unittest discover -s tests`。
- S0.2 WHEN P1 的變更完成，THE SYSTEM SHALL 讓 `python3 tools/render.py --check`
  對所有 host 通過，且 repo 內 dist 與 golden 沒有 diff。
- S0.3 WHERE 覆寫檔不存在，THE SYSTEM SHALL 匯出與變更前位元組相同的 marketplace（D4）。

## P1

- S1.1 WHERE 覆寫檔指定 `security-reviewer` 的 model，THE SYSTEM SHALL 只改寫
  stage 中 `agents/security-reviewer.md` 的 `model:` 行，其他檔案位元組不變。
- S1.2 WHEN 已套用覆寫並安裝，THE SYSTEM SHALL 讓 `verify` 回報 up-to-date。
- S1.3 IF 覆寫檔指定不存在的 role，THEN THE SYSTEM SHALL 以非零 exit 失敗，且不 swap marketplace。
- S1.4 IF 覆寫檔含 `[roles.<name>].model` 以外的 key，THEN THE SYSTEM SHALL 以非零 exit 失敗。
- S1.5 IF model 值不符合 D3 的格式，THEN THE SYSTEM SHALL 以非零 exit 失敗。
- S1.6 IF 覆寫檔把帶 `refuses_defensive_security` 的模型（`fable`）指定給 security role，
  THEN THE SYSTEM SHALL 以非零 exit 失敗。
- S1.7 WHEN 套用覆寫，THE SYSTEM SHALL 在 `--update` 輸出中列出每個被覆寫的 role 與 model。

- S1.8 IF role 名稱不是已知 role（含路徑型 key），THEN THE SYSTEM SHALL 以非零 exit 失敗，
  且 stage 外的檔案不被改寫（含 dry-run）。
- S1.9 IF security role 的 model 含 flagged alias 的任一段（`fable[1m]`、`claude-fable-5-2`），
  THEN THE SYSTEM SHALL 以非零 exit 失敗。
- S1.10 IF model 值會改變 YAML 型別（`[1m]`、`-`、`]`、`1.0`、`0`），THEN THE SYSTEM SHALL
  以非零 exit 失敗；`opus[1m]` 可通過。
- S1.11 WHEN overlay 改變而 plugin 版本相同，THE SYSTEM SHALL 對 core plugin 先 uninstall 再 install。

## P2

- S2.1 WHEN 派 `shoal:security-reviewer`，THE SYSTEM SHALL 在 transcript 中記錄
  model 為 `claude-mythos-5-2`。

## P3

- S3.1 WHERE 候選模型可用，THE SYSTEM SHALL 把該 role 的 `model:` 改成第一個可用的候選；
  未列在 `[probe.roles]` 的 role（`security-executor`）不變。
- S3.2 WHERE 候選都不可用，THE SYSTEM SHALL 安裝與 HEAD 位元組相同的 agent 檔。
- S3.3 THE SYSTEM SHALL 每次 update 對同一個模型只探測一次。
- S3.4 WHERE overlay 與探測都指定同一個 role，THE SYSTEM SHALL 採用 overlay。
- S3.5 WHEN 原本可用的模型變成不可用，THE SYSTEM SHALL 回到 dist 並 reinstall core plugin。
- S3.6 IF `[probe.roles]` 把 flagged 模型指定給 security role，THEN THE SYSTEM SHALL 以非零 exit 失敗。
