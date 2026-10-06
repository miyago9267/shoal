---
title: Claude policy 對照表（core-policy P1 草稿）
status: draft
created: 2026-10-06
updated: 2026-10-06
---

<!-- markdownlint-disable MD025 -->

# Claude policy 對照表（P1 草稿）

草稿，不是核准。這是 P2（Claude 切 `core`）給 plan-verifier 審的輸入；每條
legacy 規則對應到哪個 core 條款、哪個 host 外框，或明列刪除理由。
legacy 指 `hosts/claude/src/` 目前的四份 policy 文件（HEAD `07eb6c6`），
core 指 `core/policy/*.toml` 加 `hosts/claude/policy-frames/` 的組合結果。

重現預覽（不碰 dist）：

```sh
python3 tools/render.py --host claude --policy-preview /tmp/claude-core
python3 tools/render.py --host claude --explain-policy
```

## 結論

- 刪除：0 條。legacy 的每個詞都在 core 預覽中，沒有未對照的內容。
- 忽略空白後逐詞比對，core 預覽與 legacy 只有兩處不同，都是為了通過
  host 中立禁字檢查（`workflow`）：`SKILL.md` 的「detailed workflow behind」
  改為「detailed procedure behind」，「from the workflow extensions」改為
  「from the policy extensions」。`tests/test_core_policy.py` 的
  `KNOWN_WORDING_CHANGES` 鎖住這兩處，並逐詞比對其餘內容。
- 非文字差異：換行位置（角色清單改由 placeholder 代入、續行縮排在條款拆分處
  消失）。Markdown 渲染相同。
- 變更預算（P2 輸入）：core 預覽相對 legacy 的 `_diff_metrics` 都在 LOCK 現行
  預算內，Claude 不需要 migration 標記，只需要 `hosts/claude/VERSION` 的
  version gate（P2 決定，這裡只提供數字）：

| surface | changed lines（上限） | changed characters（上限） | ratio（上限） |
|---|---|---|---|
| `SKILL.md` | 4（8） | 199（900） | 0.058（0.2） |
| `orchestration-policy.md` | 15（32） | 1311（4000） | 0.040（0.2） |
| `workflow-extensions.md` | 0（30） | 0（4000） | 0（0.2） |
| `claude-md.bootstrap.md`（非 lock surface） | 3 | 289 | 0.090 |

- required 條款：15 個，見最後一節；其中沒有獨立的 secret 處理條款，
  需要 reviewer 決定。
- Decision 4：每個 lock surface 的 `required_fragments`（12 個）都原樣出現在
  core 預覽（`test_claude_core_preview_keeps_lock_required_fragments`）。

## Host 外框（`hosts/claude/policy-frames/`）

外框是 Claude 專屬、逐字沿用的文字，不進 core。

| legacy | 外框檔 | 內容 |
|---|---|---|
| bootstrap L1-3 | `bootstrap.md` | 版本標記、markdownlint 註解、`## Orchestration` 標題 |
| `SKILL.md` L1-7 | `skill.md` | frontmatter（`name`、`description`）、版本標記、`# Pilotfish orchestration` |
| policy L1 | `orchestration.md` | `# Pilotfish orchestration policy` |
| extensions L1-3 | `extensions.md` | `# Pilotfish workflow extensions` 與「Ported from pilotfish-codex 1.8.1 and adapted to Claude Code.」 |

## placeholder 對照

core 條款只寫 `{{key}}`，Claude 的值在 `hosts/claude/binding.toml` 的
`[policy.placeholders]`；代入後與 legacy 字面相同。

| key | Claude 的值 | 核心條款內的使用處 |
|---|---|---|
| `dispatch_tool` | `Agent` | 5 處 |
| `question_tool` | `AskUserQuestion` | 5 處 |
| `named_roles` | `` `scout`, `Explore`, `plan-verifier`, `security-reviewer`, `mech-executor`, `executor`, `verifier`, `security-executor` `` | 2 處 |
| `shell_tool` | `Bash` | 4 處 |
| `write_tools` | `Write/Edit/NotebookEdit` | 1 處 |
| `read_tools` | `Read/Glob/Grep/Bash` | 1 處 |
| `background_option` | `run_in_background: true` | 3 處 |
| `worktree_option` | `isolation: "worktree"` | 1 處 |
| `model_param` | `model` | 3 處 |
| `goal_command` | `/goal` | 1 處 |
| `skill_term` | `Skill` | 3 處 |
| `policy_doc` | `orchestration-policy.md` | 4 處 |
| `extensions_doc` | `workflow-extensions.md` | 2 處 |
| `references_dir` | `references/` | 2 處 |

## bootstrap（`claude-md.bootstrap.md`，27 行）

| legacy 行 | 條款內容（節錄，含 placeholder） | core 條款 | kind | 差異 |
|---|---|---|---|---|
| L5-7 | Named roles ({{named_roles}}): ignore this section, do the assigned task… | `bootstrap-named-roles` | invariant | 角色清單由 `named_roles` 代入；折行位置不同，字句相同；required |
| L9-10 | Main session owns framing, Plan, approval, integration, and final judgme… | `bootstrap-ownership` | invariant | 字句不變 |
| L11-13 | Route by shape first: `co_discover` (unclear outcome), `explore_then_pla… | `bootstrap-routing` | routing | 字句不變 |
| L14-15 | A clear request to fix or finish is one outcome: continue to acceptance.… | `bootstrap-outcome` | extension | 字句不變 |
| L16-19 | Risk precedes size. Risk triggers (explicit review request, security/tru… | `bootstrap-risk` | gate | 字句不變；required |
| L20 | Security work: `security-reviewer` -> approved Plan -> `security-executo… | `bootstrap-security` | authority | 字句不變；required |
| L21-22 | Before every {{dispatch_tool}} call, apply the dispatch brake and state … | `bootstrap-dispatch-brake` | dispatch | placeholder：`dispatch_tool`, `model_param` |
| L23-24 | Ask only material questions, through `{{question_tool}}`, recommendation… | `bootstrap-questions` | routing | placeholder：`question_tool` |
| L25-27 | Load the `pilotfish-orchestration` {{skill_term}} for the full policy be… | `bootstrap-load-skill` | invariant | placeholder：`skill_term` |

## skill（`SKILL.md`，36 行）

| legacy 行 | 條款內容（節錄，含 placeholder） | core 條款 | kind | 差異 |
|---|---|---|---|---|
| L9 | This {{skill_term}} is the detailed procedure behind the always-on Pilot… | `skill-intro` | invariant | 「workflow」改為「procedure」（`workflow` 是 core 禁字詞）；placeholder：`skill_term` |
| L10-11 | The bootstrap stays authoritative for its invariants; this {{skill_term}… | `skill-bootstrap-authority` | invariant | placeholder：`skill_term` |
| L13 | First move | `first-move-heading` | heading | 字句不變 |
| L15-20 | Classify the interaction shape: `co_discover`, `explore_then_plan`, or `… | `first-move-steps` | routing | 「workflow extensions」改為「policy extensions」（禁字詞）；placeholder：`dispatch_tool` |
| L22 | References | `references-heading` | heading | 字句不變 |
| L24 | Read only the part needed for the current decision: | `references-intro` | invariant | 字句不變 |
| L26-28 | [{{policy_doc}}]({{references_dir}}{{policy_doc}}): routing, lifecycle g… | `reference-policy` | routing | 連結由 `references_dir`、`policy_doc` 代入 |
| L29-33 | [{{extensions_doc}}]({{references_dir}}{{extensions_doc}}): outcome-leve… | `reference-extensions` | routing | 連結由 `references_dir`、`extensions_doc` 代入；`AskUserQuestion` 由 `question_tool` 代入 |
| L35-36 | If a reference is unavailable, keep the bootstrap invariants, work fail-… | `reference-fail-soft` | invariant | 字句不變 |

## 主 policy（`orchestration-policy.md`，244 行）

| legacy 行 | 條款內容（節錄，含 placeholder） | core 條款 | kind | 差異 |
|---|---|---|---|---|
| L3-6 | Main-session policy. Named roles ({{named_roles}}): ignore this section,… | `intro-named-roles` | invariant | 角色清單由 `named_roles` 代入；折行位置不同，字句相同；required |
| L8-10 | Main session owns framing, architecture, ambiguity, Plan synthesis, appr… | `main-session-owns` | invariant | 字句不變 |
| L12 | Routing and lifecycle | `routing-heading` | heading | 字句不變 |
| L14-19 | Interaction shape precedes Baton/lifecycle/worker routing. Choose first … | `interaction-shape` | routing | 字句不變 |
| L20-26 | **`explore_then_plan` boundary:** its first turn is `discovery_read_only… | `explore-then-plan-boundary` | routing | legacy 是 `interaction-shape` 條目的縮排續行；core 獨立成條款，續行縮排消失（Markdown 渲染相同）；placeholder：`shell_tool`, `write_tools` |
| L27-33 | After shape selection, inspect available skills. Large/architectural/ris… | `baton-dispatch` | routing | 字句不變 |
| L34-38 | Risk precedes size. Independent-review triggers: explicit user request f… | `risk-triggers` | gate | 字句不變；required |
| L39-40 | Without a risk trigger, small/local/stable work stays direct; cross-file… | `direct-when-small` | routing | 字句不變 |
| L41-43 | Discovery gate: stable question, scope, evidence format, stop; outcome/P… | `discovery-gate` | gate | 字句不變 |
| L44-47 | Plan gate: main synthesizes one Plan. Large work uses program envelope p… | `plan-gate` | gate | 字句不變 |
| L48-51 | Approval gate: large/architectural/risky/plan-first work presents Plan a… | `approval-gate` | gate | 字句不變；required |
| L52-55 | Execution gate: approved contract fixes scope, exclusive ownership, cons… | `execution-gate` | gate | 字句不變 |
| L56-58 | Verification gate: implementation/integration must be concrete enough to… | `verification-gate` | gate | 字句不變 |
| L60 | Dispatch and ownership | `dispatch-heading` | heading | 字句不變 |
| L62-66 | Before every {{dispatch_tool}} call, state phase and apply dispatch brak… | `dispatch-brake` | dispatch | placeholder：`dispatch_tool` |
| L67-71 | Bounded task-local search stays main-session work by default, even cross… | `local-search-direct` | dispatch | 字句不變 |
| L72-75 | Before discovery launch, declare main-owned versus agent-owned read scop… | `discovery-scope-exclusive` | dispatch | placeholder：`read_tools` |
| L76-78 | Collect all discovery results before cross-surface comparison. Post-resu… | `collect-discovery` | dispatch | 字句不變 |
| L79-82 | Stable same-shape multi-file mechanical repetition defaults to one `mech… | `mech-default` | dispatch | 字句不變 |
| L83-85 | Collect mechanical result before main edits; worker files remain worker-… | `mech-collect` | dispatch | 字句不變 |
| L86-88 | Direct main execution of qualifying mechanical work requires prior concr… | `mech-direct-blocker` | dispatch | 字句不變 |
| L89-93 | Outside mechanical shape, delegate only when lower cost/quota, preserved… | `delegate-cost-benefit` | dispatch | 字句不變 |
| L94-97 | Dispatch brakes judge one call at a time. Recurrence qualifies through s… | `brake-per-call` | dispatch | 字句不變 |
| L98-102 | Single unknown bug stays main-session work through root-cause discovery,… | `single-bug-direct` | dispatch | 字句不變 |
| L103-107 | Large cross-surface investigation may use bounded read-only discovery, f… | `large-investigation` | dispatch | 字句不變 |
| L108-110 | One-shot spec includes goal, constraints, done criteria, relevant paths,… | `one-shot-spec` | dispatch | 字句不變 |
| L111-112 | Security-sensitive work (authn/authz, credentials/secrets, identity/priv… | `security-sensitive-routing` | authority | 字句不變；required |
| L113-114 | Before required approval and first readiness review, finish tool-enforce… | `security-reviewer-first` | authority | legacy 同一條目逐句拆成四個條款，字句不變；續行縮排消失；required |
| L114-115 | After approval, send stable contract to `security-executor`. | `security-executor-after-approval` | authority | 同上；required |
| L115-117 | Never run both pre-approval reviews concurrently or send pre-approval wo… | `security-no-preapproval-write` | authority | 同上；required |
| L118-125 | Any independent-review trigger makes that unit risky: pre-approval `plan… | `risk-review-mandatory` | gate | placeholder：`dispatch_tool`；required |
| L126-128 | Named-role model routing lives in agent definitions. Omit invocation `{{… | `model-routing` | dispatch | placeholder：`model_param` |
| L129-134 | `plan-verifier` reviews one stable envelope/slice and returns **READY** … | `review-verdicts` | verification | placeholder：`shell_tool` |
| L135-138 | Review program envelope before slices, then next executable slice only. … | `envelope-then-slice` | verification | 字句不變 |
| L139-148 | Per readiness unit: materially revise after valid `REVISE`, then use fre… | `readiness-loop` | verification | 字句不變 |
| L149-155 | Risk-triggered completed work gets one fresh outcome-verifier pass at sm… | `outcome-verification` | verification | 字句不變 |
| L156-166 | Role verdicts are evidence, never implementation/scope authority. Main c… | `verdict-authority` | verification | 字句不變 |
| L167-174 | Never claim blocker fixed without contrary evidence or successful rechec… | `recheck-and-invalidate` | verification | 字句不變 |
| L175-179 | Scout findings are inputs, not verified outcomes: sanity-check or re-sco… | `scout-inputs` | verification | 字句不變 |
| L181 | Recovery and authority | `recovery-heading` | heading | 字句不變 |
| L183-191 | Severity rules apply every verification run; AUTO/ASK mode selection app… | `recovery-budget` | recovery | 字句不變 |
| L191-198 | Fingerprint complete tested identity from committed HEAD, tracked/staged… | `identity-fingerprint` | recovery | `recovery-budget` 的後半，同一條目拆開，字句不變 |
| L199-205 | Before likely long autonomous work, offer `AUTO` or `ASK` and wait, unle… | `auto-ask-selection` | authority | placeholder：`goal_command` |
| L206-210 | `AUTO` permits approved-scope reversible work plus main-session P2 adjud… | `auto-limits` | authority | 字句不變；required |
| L211-214 | `ASK` uses `{{question_tool}}` when available; otherwise end with `PAUSE… | `ask-mode` | authority | placeholder：`question_tool` |
| L214-218 | Questions belong to main session, never child. P0 freezes affected slice… | `ask-questions-main` | authority | `ask-mode` 的後半，同一條目拆開，字句不變 |
| L219-222 | Final report separates confirmed/fixed/deferred/regraded findings (origi… | `final-report` | recovery | 同一條目拆開，續行縮排消失 |
| L224 | Parallel and runtime mechanics | `parallel-heading` | heading | 字句不變 |
| L226-232 | Schedule by dependency, not eventual need. When selecting 2+ independent… | `parallel-launch` | mechanics | placeholder：`background_option` |
| L232-235 | Parallel writers use `{{worktree_option}}` (requires Git); without Git, … | `parallel-writers` | mechanics | 第一條目的後半拆開，字句不變；placeholder：`worktree_option` |
| L236-237 | Long-running processes belong to main session. {{dispatch_tool}} with po… | `long-running-main` | mechanics | placeholder：`background_option`, `dispatch_tool`, `shell_tool` |
| L238-241 | Leaf unable to finish bounded foreground work returns exact command, abs… | `leaf-cannot-finish` | mechanics | 第二條目逐句拆開，字句不變；placeholder：`background_option`, `shell_tool` |
| L241-242 | Liveness comes from tracked task state/output, never CPU/processes/stale… | `liveness` | mechanics | 同上 |
| L242-244 | Subagent final message is deliverable: read completed output directly; r… | `subagent-final-message` | mechanics | 同上 |

## 擴充規則（`workflow-extensions.md`，150 行）

| legacy 行 | 條款內容（節錄，含 placeholder） | core 條款 | kind | 差異 |
|---|---|---|---|---|
| L3-4 | These rules extend [{{policy_doc}}]({{policy_doc}}). | `ext-extend-policy` | extension | 連結文字與路徑由 `policy_doc` 代入 |
| L4-6 | When a rule here conflicts with that policy, the policy wins: report the… | `ext-conflict-policy-wins` | extension | legacy 的前言段落逐句拆成三個條款 |
| L6-7 | None of these rules expands approval, security, destructive, external, r… | `ext-no-authority` | extension | 同上；列為 required |
| L9 | Outcome-level continuation | `continuation-heading` | heading | 字句不變 |
| L11-12 | The execution unit is the requested user-visible outcome, not one comman… | `execution-unit` | extension | 字句不變 |
| L14-17 | `execution_scope`: `step`, `slice`, or `outcome`. - `continuation_mode`:… | `route-fields` | extension | 字句不變 |
| L19-23 | For a clear `execute` request, default to `execution_scope=outcome` and … | `continuation-default` | extension | 字句不變 |
| L25-29 | Explicit wording such as "only inspect this file", "先做這一步", or "只改這個 mod… | `step-vs-outcome` | extension | 字句不變 |
| L31-35 | Material approval, security, release, destructive, external, or irrevers… | `material-gates-first` | extension | 字句不變；required |
| L37 | Turn-scoped review intent | `review-intent-heading` | heading | 字句不變 |
| L39-41 | Keep `review_intent` separate from the task mode. A clear explicit prefe… | `review-intent-select` | extension | 字句不變 |
| L43-45 | `fast` skips optional review and non-required reasoning on non-mandatory… | `review-intent-fast` | extension | 字句不變 |
| L46-47 | `default` follows the existing risk policy and is the fallback when no c… | `review-intent-default` | extension | 字句不變 |
| L48-49 | `strict` requests the complete primary review and test path. It does not… | `review-intent-strict` | extension | 字句不變 |
| L51-53 | The preference is turn-scoped. Do not infer it from task wording, quoted… | `review-intent-turn-scoped` | extension | 字句不變 |
| L55 | Discovery budget | `discovery-budget-heading` | heading | 字句不變 |
| L57-59 | Discovery has a grounding floor and a stopping ceiling. One discovery un… | `discovery-budget-intro` | extension | 字句不變 |
| L61-66 | \| Budget \| Minimum evidence \| Default ceiling \| \| --- \| --- \| ---… | `discovery-budget-table` | extension | 字句不變 |
| L68-70 | Stop early when evidence no longer changes the route. When the floor can… | `discovery-budget-stop` | extension | 字句不變 |
| L72 | Decision checkpoint | `checkpoint-heading` | heading | 字句不變 |
| L74-78 | Low-risk, reversible, clearly scoped work proceeds on a reasonable defau… | `checkpoint-default` | extension | placeholder：`question_tool` |
| L80 | One high-level question whose answer changes the next gate. | `checkpoint-question` | extension | 字句不變 |
| L81-82 | Two or three mutually exclusive options, recommended option first and la… | `checkpoint-options` | extension | 字句不變 |
| L83-85 | Each option states its concrete effect; the question or a preceding line… | `checkpoint-option-detail` | extension | 字句不變 |
| L87-89 | Resolve replies conservatively: an exact option confirms only that optio… | `checkpoint-reply` | extension | 段落前半，字句不變 |
| L89-91 | Never treat a plausible free-text answer as approval of credentials, ext… | `explicit-approval-only` | extension | 從 `checkpoint-reply` 段落拆出單句，列為 required（見下方 required 說明） |
| L91-92 | Ask follow-ups only after the selected direction resumes and a new mater… | `checkpoint-followups` | extension | `checkpoint-reply` 之後的句子，字句不變 |
| L92-94 | If `{{question_tool}}` is unavailable, end with `PAUSED_NEEDS_USER`, one… | `checkpoint-unavailable` | extension | 同上；placeholder：`question_tool` |
| L96 | Task ledger and blocked-task isolation | `ledger-heading` | heading | 字句不變 |
| L98-101 | When one prompt contains multiple independently executable outcomes, spl… | `ledger-split` | extension | 字句不變 |
| L103-107 | A task is runnable when it is `PENDING`, its dependencies are `DONE`, an… | `ledger-runnable` | extension | 字句不變 |
| L109-112 | When only blocked tasks remain, emit one consolidated reminder with bloc… | `ledger-blocked-only` | extension | 字句不變 |
| L114 | Continuation across user input | `input-heading` | heading | 字句不變 |
| L116-119 | An unfinished objective stays active across decision replies, steering, … | `objective-persists` | extension | 字句不變 |
| L121-127 | Before pausing for input, state the active objective, current phase or s… | `pause-statement` | extension | 字句不變 |
| L129 | Review-service circuit breaker | `breaker-heading` | heading | 字句不變 |
| L131-139 | A missing, failed, or timed-out `plan-verifier`, `security-reviewer`, or… | `review-circuit-breaker` | extension | 字句不變 |
| L141 | Direction checkpoint | `direction-heading` | heading | 字句不變 |
| L143-150 | At a stable slice boundary of multi-slice work, the main session may sen… | `direction-checkpoint` | extension | 字句不變 |

## required 條款

`required` 的條款不可被 binding `omit`，也不可被 addendum `replace`
（P3a，`tests/test_core_policy.py` 的 `EXPECTED_REQUIRED` 鎖定）。

| 類別 | 條款 | 依據的 legacy 規則 |
|---|---|---|
| named-role 豁免 | `bootstrap-named-roles`、`intro-named-roles` | 「named roles: ignore this section … never spawn subagents」 |
| risk trigger 與核准 | `bootstrap-risk`、`risk-triggers`、`risk-review-mandatory`、`approval-gate` | trigger 清單、plan-verifier 與 verifier 為必經、核准前不得動手 |
| security-reviewer → 核准 → security-executor | `bootstrap-security`、`security-sensitive-routing`、`security-reviewer-first`、`security-executor-after-approval`、`security-no-preapproval-write` | security 路徑四句與 bootstrap 摘要 |
| destructive / external 確認 | `auto-limits`、`material-gates-first`、`explicit-approval-only` | AUTO 不得 commit、push、external mutation、destructive 等；關卡優先於 continuation；自由文字不算核准 |
| 擴充規則不擴權 | `ext-no-authority` | 「None of these rules expands approval, security, destructive, external, release, or spending authority」 |

### 需要 reviewer 決定

- 「secret 處理」：legacy 的 Claude policy 沒有獨立的 secret 規則（只有「不得
  把 credentials/secrets 的安全工作交給一般 executor」與「自由文字不算
  credentials 核准」）。目前由 `security-sensitive-routing`、
  `explicit-approval-only` 與 `auto-limits`（不得 credential rotation）承接，
  P1 沒有新增 legacy 沒有的義務。是否要在 core 新增獨立的 secret 條款，是
  行為變更，不屬於等價切換，留給 P2 reviewer。
- `reference-fail-soft` 等降級條款（引用不可用時不得宣稱完整驗證）沒有標
  required；是否要標由 reviewer 決定。

## 未對照或刪除

無。
