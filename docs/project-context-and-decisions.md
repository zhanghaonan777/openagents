# 项目上下文与决策记录

> 把 OpenAgents 改造成「多角色 AI 团队工作台」项目的探索历程、关键决策、已验证技术配方。供延续工作和团队理解背景。配套设计文档见 [`openagents-team-workspace-proposal.md`](./openagents-team-workspace-proposal.md)。

## 0. 一句话目标
让**多个不同角色的 Claude / OpenClaw agent 在一个界面里相互对话、协作**，并把承载它的 OpenAgents 改造得更好看（换皮）、协作更有结构（看板）、以「角色卡片」为核心交互。

## 1. 为什么是 OpenAgents（探索历程）
- 路径：**pixel-agents**（2D 工作可视化，只可视化单会话，方向不对）→ **Claw3D**（3D AI 办公室，`~/project/Claw3D`，连 OpenClaw gateway）→ **OpenAgents**（"agent 版 Slack"，原生支持 Claude Code + OpenClaw，最终落定）。
- OpenAgents：`github.com/openagents-org/openagents`，Apache-2.0。前端 Next.js 16 + React 19 + Tailwind 4 + Radix；后端 Python；可 `docker-compose` 本地自部署。

## 2. 已验证的关键技术配方
1. **装 launcher**：`npm i -g @openagents-org/agent-launcher`（CLI 名 `agn`）。
2. **建 workspace**：`agn workspace create <名>` → 直接命令行拿到 URL + token（无需账号）。当前 demo：`workspace.openagents.org/75906f5d`（token 用 `agn workspace list` 查）。
3. **加 claude 角色**：`agn create <名> --type claude --path <角色目录>` → `agn connect <名> <token>` → `agn up`。**claude runtime 复用 Claude Code 登录，免 API key**；角色人格 = `--path` 目录里的 `CLAUDE.md`。
4. **加 openclaw 角色（MiniMax）**：`agn create <名> --type openclaw` → 在 `~/.openagents/daemon.yaml` 给该 agent 加一行 `openclaw_agent_id: captain` → `agn down && agn up`。本地 OpenClaw gateway 跑在 `localhost:18789`，其 `captain` agent 用 `minimax/MiniMax-M3`。
5. **自定义专业角色**：建 `~/.openagents/roles/<role>/CLAUDE.md`（身份 + 方法论 + 风格），`create --path` 指过去。已验证 `security-auditor` 角色生效。
6. **已实测**：claude-reviewer + claude-coder + openclaw-dev(队长/MiniMax) + security-auditor 四角色群聊，会互相 `@` 接力、自发帮对方诊断报错——真协作。

## 3. 角色模板来源（角色卡片库的数据源）
- **首选：VoltAgent/awesome-claude-code-subagents**（~22k★，164 个角色，10 大类，格式最干净）。body 剥掉 frontmatter 直接当 `CLAUDE.md`。需重新 clone（之前在 /tmp 已清理）。
- 备选：**BMAD-METHOD**（~49k★，成体系敏捷团队岗位）、wshobson/agents（~37k★）、本机已装的 **ruflo**（`.claude/agents/*.md`）。

## 4. 关键设计决策
- 改造主线：**A 视觉换皮 + B 结构化协作（任务看板）先做；C 角色卡片系统为核心**（不同角色不同卡片、对话中可加入）。详见 proposal。
- 交付方式：本文档 + proposal 交**专业设计团队**细化，再实现。
- 现有前端可改基础：`components/{chat,agents,tasks,layout,ui}` 已有对应雏形（agent-status-card / tasks-view 等）。

## 5. 协作范式认知（重要）
- OpenAgents 的交互是**中心化消息总线**（所有 agent 连 workspace hub，`@mention` 经 hub 中转寻址），本质是 "agent 版 Slack"——**不是 A2A 协议**，也没用结构化任务委派。
- 优点：现成 UI、上手低。缺点：易七嘴八舌、缺编排、token 随角色/轮次叠加。
- **若未来要真正结构化的点对点委派**：A2A 协议（Google 发起→Linux Foundation，v1.0 稳定，5 官方 SDK）。推荐框架：**Google ADK**（最成熟，`RemoteA2aAgent` 零样板）/ **CrewAI[a2a]**（最易上手，声明式委派）/ MS Agent Framework（企业/.NET）。都能接 Claude，但**无现成可视化 UI，要自己加**。

## 6. 开放问题 / 下一步
- 设计团队细化 proposal 里的 6 项开放设计决策（视觉风格、卡片形态、看板布局等）。
- 本地 `docker-compose` 自部署 OpenAgents，以便改前端、让 agent 连本地 workspace。
- 决定角色卡片库对接哪个模板源（建议 VoltAgent）。

## 7. 资源指针
- 本仓库（OpenAgents fork）：`~/project/open-agents`
- 设计文档：`docs/openagents-team-workspace-proposal.md`
- 3D 可视化备选：`~/project/Claw3D`（连 OpenClaw gateway / Hermes / demo）
- 本地 OpenClaw gateway：`localhost:18789`（captain = minimax/MiniMax-M3）
- launcher 配置：`~/.openagents/daemon.yaml`、自定义角色：`~/.openagents/roles/`
