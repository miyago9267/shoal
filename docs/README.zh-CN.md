# shoal

只需定义一次 agent role，shoal 就能根据各厂牌 agent 配好模型、权限与 prompt，自
动 orchestration；无需编写任何代码。

[繁體中文](../README.md) · [English](./README.en.md) · 简体中文

## 它解决什么

- 一份 role 定义，五个 host 各自拿到合适的模型、权限和 prompt。
- 主 session 负责判断与整合，改文件和长命令交给对应的 role。
- 派工规则由 guard 在每个 host 强制执行，不靠模型自觉。
- 要支持新工具，填配置就行，不用写代码。

## 运作方式

![分层：core、binding、各 host](./assets/shoal-overview-zh-CN.svg)

role 写在 core，每个 host 用 binding 说明自己的模型与权限，再由 `render.py` 生成
安装文件。

![路由：一个 role 在各 host 选到哪个模型](./assets/shoal-routing-zh-CN.svg)

role 只写 tier，不写模型名称；每个 host 从自己的模型目录里挑出符合的那一个。

![orchestration：一个回合怎么分工](./assets/shoal-orchestration-zh-CN.svg)

主 session 先看工作的形态和风险，再决定自己做、派给哪个 role，还是走完整的审查流
程。

![guard：哪些事会被拦、出口是什么](./assets/shoal-guard-zh-CN.svg)

主 session 没派可写 role 就改文件，或 subagent 不是 shoal 的可写 role 却改文件，
都会被拦；出口是改派可写的 role，或在 prompt 里加 `#direct`。

## 快速开始

```bash
# Codex CLI
bash install/install.sh --codex-home "${CODEX_HOME:-$HOME/.codex}"
# Claude Code（plugin，固定在 tag 上）
claude plugin marketplace add miyago9267/shoal#v3.6.0
claude plugin install shoal@shoal
# Grok Build（不加 --apply 是 dry-run）
python3 tools/install_grok.py
# OpenCode（全局）
sh hosts/opencode/plugin/install/install.sh --global --enable
```

Gemini/agy 与不用 plugin 的 Claude Code 见 [INSTALL.md](../INSTALL.md)。

## 支持的 host

| Host | 安装方式 | guard |
| --- | --- | --- |
| Claude Code | plugin，或 `tools/install_hooks.py` | hook，默认拦截 |
| Codex CLI | `install/install.sh` | hook，需在 `/hooks` 里批准一次 |
| Gemini/agy | `hosts/agy/dist` 加 `tools/install_hooks.py` | hook，默认拦截，没有 `#direct` |
| Grok Build | `tools/install_grok.py` | 原生 hooks |
| OpenCode | `install.sh --enable` | plugin 内置 |

## 快速与严谨

默认走快速路径：读文件、诊断和整合由主 session 直接做，改文件交给可写的 role。
遇到风险或大型工作才走严谨路径：计划审查、批准，完成后再验证。
想让主 session 自己改文件，在 prompt 里加 `#direct`。整个 session 的快速开关将在
下个版本推出。

## 与 pilotfish 的关系

shoal 衍生自 [Nanako0129/pilotfish](https://github.com/Nanako0129/pilotfish)，
Claude 端以 pilotfish v1.4.2 为分叉基准。pilotfish 目前是 v1.5.0（2026-10-10），
是 Claude Code 的多模型 orchestration policy，Plugin 已脱离 beta；其他工具各有姊
妹项目（pilotfish-grok、pilotfish-codex、remora）。

| 方面 | pilotfish | shoal |
| --- | --- | --- |
| 支持范围 | 以 Claude Code 为主，其他工具各一个项目 | 一份 role 定义 render 成 5 个 host |
| 派工判断 | main 按净收益判断，小而局部的工作自己做 | 改文件一律交给可写 role（`#direct` 例外） |
| 强制范围 | hook 只拦硬规则（leaf 不再派工、verifier 不改文件） | 另拦 main 直接改文件、非 shoal agent 改文件、role 未启动、改完没检查就结束 |
| 证据 | 每个决定都附 benchmark 与测量 | 以 payload 抓取和各 host 实测为主，测量较少 |

shoal 不取代 pilotfish，也不是它的上位版本：它把 role 与条款扩到多个厂牌并加上强
制执行，代价是更重、更严。
只用 Claude Code、想要轻量且有测量支撑的 policy，用
[pilotfish](https://github.com/Nanako0129/pilotfish)。
同时用多个 agent 工具、想要一份定义和一致的强制规则，用 shoal。

## 延伸阅读

- [INSTALL.md](../INSTALL.md)：完整安装、guard 规则与环境变量。
- [docs/DESIGN-INVARIANTS.md](./DESIGN-INVARIANTS.md)：不能改的设计原则。
- [docs/new-host.md](./new-host.md)：新增 host 的步骤。
- [CHANGELOG.md](../CHANGELOG.md)：版本记录。

## 来源与致谢

shoal 衍生自
[Nanako0129/pilotfish](https://github.com/Nanako0129/pilotfish)。
grok host 的 orchestration rules 与 agent 原文取自
[Nanako0129/pilotfish-grok](https://github.com/Nanako0129/pilotfish-grok) v1.0.6，
shoal 加上 core 条款、原生 hooks 与 installer；`upstream.lock` 记录版本。
codex host 原本是 `miyago9267/pilotfish-codex`，v1.0.0 起并入本 repo；
v1.0.0 之前的 pinned ref 仍在
[pilotfish-codex](https://github.com/miyago9267/pilotfish-codex)。
上游 Pilotfish 的著作权与授权声明沿用，见 `LICENSE`。
