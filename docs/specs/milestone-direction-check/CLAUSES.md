# 條款原文（M1，main 撰寫）

M2 與 M2b 照抄本檔的英文段落，不改寫。M2 **取代**既有的 Direction checkpoint
段落（Claude：`core/policy/extensions.toml` 的 `direction-checkpoint` clause；
Codex：`templates/agents-md.orchestration.md` 的 direction_checkpoint 段落與其
三項 disposition 清單，mirror 同步），不保留舊的「may」文字。M2b 加在 M2 之後。

## M2：milestone 方向檢查（D1-D6，取代既有段落）

```text
At multi-slice milestone closes the main session sends the `verifier` a
`direction_checkpoint` brief: the original request, the approved spec's
non-goals and decisions, the declared design invariants
(`docs/DESIGN-INVARIANTS.md` or equivalent), and current evidence. It returns
`CONTINUE`, `PIVOT` (outcome stands; bounded re-plan within approved scope),
or `ROLLBACK` (an invariant or acceptance condition is broken); insufficient
evidence stays `INCONCLUSIVE`. Required when one objective reaches its third
slice (a new spec continuing it counts) and at every later milestone close:
once per milestone, separate from outcome verification, not skipped by `fast`
review intent. Before closing a single-slice spec or dispatching architecture
or design work, main runs the same comparison itself; otherwise optional. On
deviation or `ROLLBACK`, stop new writes and report it with a recommendation
(`stop_condition=decision`, or `PAUSED_NEEDS_USER` without interaction);
rolling back is the user's decision. Executor design decisions beyond the
brief (mechanism, interface, naming, omission) are unreviewed: accept or
reject each and record it before merging.
```

## M2b：不計代價（D7）

```text
Cost-unbounded continuation applies only when the user explicitly selects it
(in `/goal`, the prompt, or the AUTO/ASK choice). Within approved scope,
continue to acceptance without stopping or asking because of cost, tokens,
time, slice count, discovery budget, or whether to continue. The AUTO stop
list and the milestone direction check stay in force, and the mode grants no
extra authority. At the two-`REVISE` cap, disposition, narrow, or split as
usual, then continue as user-directed continuation; every pass still needs a
material change, otherwise `PAUSED_VERIFICATION`. Escalate only to a higher
executor tier or main-session takeover; an unresolved P1 outside approved
scope still stops. A `PIVOT` re-plans only within approved scope; beyond it,
stop at `decision`.
```
