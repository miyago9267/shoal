# core-policy 進度

## P0 prompt-document-lock 一次性 migration（2026-10-06，完成）

commit `53ada42`。`LOCK.json` 的 surface 可標 `migration`（`migration_id`、
`equivalence`），只在帶 `--allow-lock-update`、base 沒有相同 `migration_id`、
CI 走 push 路徑時生效，且只跳過變更預算；PR label 路徑以 `--no-migration` 拒絕。
CI `paths` 加入 `core/**`。prompt-document-lock SPEC 已改寫並記錄 decision。

## P1 條款、組裝、placeholder、omit、required、開關（2026-10-06，完成，未 commit）

所有 host 維持 `policy_text = "legacy"`，五個 host 的 `render --check` 與 dist 逐位元組
相同；Claude 的 `core` 輸出只能經預覽取得。

- **條款**：`core/policy/` 四份文件（`bootstrap` 9、`skill` 9、`orchestration` 54、
  `extensions` 39，共 111 個條款）加 `placeholders.toml`（14 個 key）。由 Claude 的
  四份 policy 切出（Decision 1），其中 15 個標 `required`。
- **組裝**：沿用 `tools/contracts.py` 的 `compose`、`load_frame`、`load_addenda`；
  新增 `Clause.required`、`POLICY_KINDS`、`load_policy_contract`、`substitute`
  （單次 regex）、`check_placeholder_values`、`check_policy_edits`、`compose_policy`。
  role 條款不接受 `required`，role 的 kind 詞彙不變。
- **binding**：`[policy]` 的 `policy_text`、`omit`（`{id, reason}`）、
  `[policy.placeholders]`、`[policy.documents]`；五個 host 都加了 `[policy]`
  （`legacy`、`omit = []`），Claude 另有 placeholders 與 documents。只有 Claude 的
  renderer 支援 `core`，其他 host 設 `core` 會被 `validate_catalog` 拒絕（P3）。
- **Claude 外框**：`hosts/claude/policy-frames/<doc>.md` 四個，沒有 policy addenda
  （Claude 是 canonical）。`package.json` 的 `lint:md` 排除 `policy-frames`。
- **預覽**：`render.py --host <h> --policy-preview DIR`（寫入 core 組出的文件，不碰
  dist、不清理 DIR 內其他檔案、拒絕 dist 之內的目錄）與 `--explain-policy`。
- **測試**：`tests/test_core_policy.py` 51 項：格式與 kind、placeholder 單次代入與
  錯誤、omit 與 required 的錯誤、`policy_text` 開關、preview、addenda、禁字詞（沿用
  `HOST_SPECIFIC_TERMS`）、`EXPECTED_REQUIRED`／`EXPECTED_POLICY_TEXT`／
  `EXPECTED_POLICY_OMITS`／`EXPECTED_POLICY_REPLACES`／`EXPECTED_POLICY_ADDENDA`
  鎖定、Claude 預覽與 legacy 逐詞比對（只允許 `KNOWN_WORDING_CHANGES` 兩處）、
  Decision 4 的 `required_fragments` 檢查。
- **對照表草稿**：`docs/specs/core-policy/equivalence/claude.md`（`status: draft`），
  是 P2 給 plan-verifier 審的輸入，不是核准。結論：沒有刪除；與 legacy 忽略空白後
  只差兩處「workflow」改寫（禁字詞）；相對 legacy 的變更量在現行 LOCK 預算內
  （orchestration-policy 15 行、SKILL 4 行、extensions 0 行），Claude 可能不需要
  migration 標記，是否仍走 migration 由 P2 決定。

### 驗證（2026-10-06）

- 五個 host `render --check` 全部 OK（claude 13、codex 12、agy 9、grok 20、opencode 7
  個檔案）。
- `python3 -m unittest discover -s tests`：1350 項，OK（skipped=1）。
- `validate_prompt_lock.py`：ok surfaces=27。`bun run lint:md`：0 errors。
  `check_links.py`：0 missing。

### 留給 P2 的問題

- legacy 沒有獨立的 secret 處理規則；`required` 目前由 `security-sensitive-routing`、
  `explicit-approval-only`、`auto-limits` 承接。是否新增獨立條款是行為變更，需 reviewer
  決定（對照表最後一節）。
- 外框內的版本標記（`pilotfish v1.4.2-claude.3`）是逐字文字，切換時要與
  `hosts/claude/VERSION` 一起更新。
- Claude plugin 的 `policy/claude-md.bootstrap.md` 與 golden（`tests/golden/`）會跟著
  `core` 輸出改變，P2 要同步 `render --write` 與 golden。
