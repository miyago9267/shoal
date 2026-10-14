<!-- markdownlint-disable MD013 -->
# shoal

只需定義一次 agent role，shoal 就能依照各廠牌 agent 配好模型、權限與 prompt，自動 orchestration；毋需撰寫任何程式。

繁體中文 · [English](docs/README.en.md) · [简体中文](docs/README.zh-CN.md)

## 它解決什麼

- 一份 role 定義，五個 host 各自拿到合適的模型、權限和 prompt。
- 主 session 負責判斷與整合，改檔和長指令派給對應的 role。
- 派工規則由 guard 在每個 host 強制執行，不靠模型自覺。
- 要支援新工具，填設定就好，不用寫程式。

## 運作方式

![分層：core、binding、各 host](docs/assets/shoal-overview-zh-TW.svg)

role 寫在 core，每個 host 用 binding 說明自己的模型與權限，再由 `render.py` 產出安裝檔。

![路由：一個 role 在各 host 選到哪個模型](docs/assets/shoal-routing-zh-TW.svg)

role 只寫 tier，不寫模型名稱；每個 host 從自己的模型目錄挑出符合的那一個。

![orchestration：一個回合怎麼分工](docs/assets/shoal-orchestration-zh-TW.svg)

主 session 先看工作的形狀和風險，再決定自己做、派給哪個 role，或走完整的審查流程。

![guard：哪些事會被擋、出口是什麼](docs/assets/shoal-guard-zh-TW.svg)

主 session 沒派可寫 role 就改檔，或 subagent 不是 shoal 的可寫 role 卻改檔，都會被擋；出口是改派可寫的 role，或在 prompt 加 `#direct`。

## 快速開始

```bash
# Codex CLI
bash install/install.sh --codex-home "${CODEX_HOME:-$HOME/.codex}"
# Claude Code（plugin，裝最新穩定版）
claude plugin marketplace add miyago9267/shoal
claude plugin install shoal@shoal
# Grok Build（不加 --apply 是 dry-run）
python3 tools/install_grok.py
# OpenCode（全域）
sh hosts/opencode/plugin/install/install.sh --global --enable
```

Gemini/agy 與不用 plugin 的 Claude Code 見 [INSTALL.md](./INSTALL.md)。

## 支援的 host

| Host | 安裝方式 | guard |
| --- | --- | --- |
| Claude Code | plugin，或 `tools/install_hooks.py` | hook，預設擋 |
| Codex CLI | `install/install.sh` | hook，需在 `/hooks` 核准一次 |
| Gemini/agy | `hosts/agy/dist` 加 `tools/install_hooks.py` | hook，預設擋，沒有 `#direct` |
| Grok Build | `tools/install_grok.py` | 原生 hooks |
| OpenCode | `install.sh --enable` | plugin 內建 |

## 快速與嚴謹

預設走快速路徑：讀檔、診斷和整合由主 session 直接做，改檔派給可寫的 role。遇到風險或大型工作才走嚴謹路徑：計畫審查、核准，完成後再驗證。想讓主 session 自己改檔，在 prompt 加 `#direct`。要整個 session 都走快，在 prompt 加 `#fast`：主 session 可以直接改檔，硬規則（role 不再派工、審查 role 不改檔）和結束前的檢查照舊。`#strict` 關閉；沒有 prompt 文字的工具（agy）設 `SHOAL_GUARD_FAST=1`。

## 和 pilotfish 的關係

shoal 衍生自 [Nanako0129/pilotfish](https://github.com/Nanako0129/pilotfish)，Claude 端以 pilotfish v1.4.2 為分岔基準。pilotfish 目前是 v1.5.0（2026-10-10），是 Claude Code 的多模型 orchestration policy，Plugin 已脫離 beta；其他工具各有姊妹專案（pilotfish-grok、pilotfish-codex、remora）。

| 面向 | pilotfish | shoal |
| --- | --- | --- |
| 支援範圍 | Claude Code 為主，其他工具各一個專案 | 一份 role 定義 render 成 5 個 host |
| 派工判斷 | main 依淨效益判斷，小而局部的工作自己做 | 改檔一律交給可寫 role（`#direct` 例外） |
| 強制範圍 | hook 只擋硬規則（leaf 不再派工、verifier 不改檔） | 另擋 main 直接改檔、非 shoal agent 改檔、role 未啟動、改完沒檢查就結束 |
| 證據 | 每個決定都附 benchmark 與量測 | 以 payload 擷取與各 host 實測為主，量測較少 |

shoal 不取代 pilotfish，也不是它的上位版本：它把 role 與條款擴到多個廠牌並加上強制執行，代價是比較重、比較嚴。只用 Claude Code、想要輕量且有量測支撐的 policy，用 [pilotfish](https://github.com/Nanako0129/pilotfish)。同時用多個 agent 工具、想要一份定義和一致的強制規則，用 shoal。

## 延伸閱讀

- [INSTALL.md](./INSTALL.md)：完整安裝、guard 規則與環境變數。
- [docs/DESIGN-INVARIANTS.md](./docs/DESIGN-INVARIANTS.md)：不能改的設計原則。
- [docs/new-host.md](./docs/new-host.md)：新增 host 的步驟。
- [CHANGELOG.md](./CHANGELOG.md)：版本紀錄。

## 來源與致謝

shoal 衍生自 [Nanako0129/pilotfish](https://github.com/Nanako0129/pilotfish)。grok host 的 orchestration rules 與 agent 原文取自 [Nanako0129/pilotfish-grok](https://github.com/Nanako0129/pilotfish-grok) v1.0.6，shoal 加上 core 條款、原生 hooks 與 installer；`upstream.lock` 記錄版本。codex host 原本是 `miyago9267/pilotfish-codex`，v1.0.0 起併入本 repo；v1.0.0 之前的 pinned ref 仍在 [pilotfish-codex](https://github.com/miyago9267/pilotfish-codex)。上游 Pilotfish 的著作權與授權聲明沿用，見 `LICENSE`。
