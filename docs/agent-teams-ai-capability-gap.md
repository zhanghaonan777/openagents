# Agent Teams (777genius/agent-teams-ai) 能力差距总表

对 `_ref-agent-teams-ai` 做的穷尽式盘点(4 个并行 Explore 读遍 renderer / main-process IPC / mcp-server / controller + 8 张产品截图)。
对照我们 OpenAgents workspace 当前状态。状态列:✅ 已有 · ⚠️ 部分 · ❌ 没有。
工作量:S(<1d) · M(1–3d) · L(1–2w) · XL(>2w/需新子系统)。

> 一句话结论:**他们是一个成熟桌面 IDE 级的多 agent 工作台**;我们在「协议层(A2A/事件总线/乐观锁)」更强,但在「**代码审查 diff、运行时管理/终端、多 Provider、会话分析报告、应用外壳(多窗格/命令面板)、治理审批、内置编辑器**」这些**交互/展示密集**的能力上整片缺失。下面逐域列清。

---

## A. 看板 / 任务板 (Kanban)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 5 列看板 | Todo / In Progress / **Review** / Done / **Approved**(Approved 是独立列) | ⚠️ 我们 4 列,Approved 只是 Done 里的徽章 | S |
| 拖拽排序 | 列内 + 跨列拖拽移动,manual sort 模式,dnd-kit | ❌ | M |
| 视图切换 | Grid 视图 ↔ Columns 视图,列宽可拖拽并持久化 | ❌ | M |
| 过滤 popover | 按 session / owner / 列 过滤,激活计数徽章 | ❌(看板上无过滤) | S |
| 排序 popover | updatedAt / createdAt / owner / manual | ❌ | S |
| 每列「+ Add task」 | 人直接在看板上建任务(→ CreateTaskDialog) | ❌(只能聊天 @ 或 delegate 弹窗) | M |
| 软删除 + 回收站 | Trash dialog,删除的任务可恢复 | ⚠️ 只有 cancel | M |
| 分页 | 每列「Show more」每次 20 条 | ❌ | S |
| 卡片依赖 chip | `Blocked by #x` / `Blocks #x`,点击滚动到依赖卡 | ❌(无依赖) | M |
| 卡片未读评论徽章 | 总数 + 未读数 + 新评论脉冲动画 | ❌ | M |
| 卡片改动指示 | FileCode 图标(sky / amber 表示 needs-attention) | ❌(无 diff) | — |
| 卡片澄清/需修复徽章 | needs-clarification(红)、needs-fix(橙,点击开 diff) | ❌ | S |
| 卡片实时活动指示 | OngoingIndicator(有实时日志时脉冲) | ⚠️ 有 working 脉冲 | S |
| 卡片内联快捷动作 | Start / Complete / Approve / Request Review / Cancel / Delete(随列变化) | ⚠️ 只有 review 三个 | M |
| 任务 hover 悬浮卡 | id/subject/status/owner/描述预览 | ❌ | S |
| 状态汇总条 | 进度条 + 各状态计数 | ✅ 本会话已加 | — |

## B. 任务详情 (Task Detail)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 内联编辑 | subject + description 富文本(Tiptap)就地编辑 | ❌(只读) | M |
| 改 owner | MemberSelect 下拉重新指派 | ❌ | S |
| 状态历史时间线 | 结构化事件(task_created/status_changed/review_*/owner_changed)+ 时长 | ⚠️ 我们渲染 message history,非结构化事件 | M |
| 依赖区 | Blocked-by / Blocks 列表,可点击跳转 | ❌ | M |
| 描述内任务链接 | `task://` 链接解析、悬浮预览 | ❌ | M |
| 内嵌 diff 审查 | 任务详情里直接看改动 | ❌ | XL |
| 评论 | 线程 + 输入框 | ✅ 基础版已加 | — |
| 评论增强 | 回复/引用、@mention、附件、视口已读追踪、草稿、反应、taskRefs | ❌(我们只有作者+文本) | L |
| 附件 | 图片/文件、拖拽上传、lightbox 预览 | ❌ | M |
| 任务日志面板 | 该任务的实时执行日志 | ❌ | M |
| 实现耗时时钟 | in-progress 时实时跑 | ❌ | S |
| 在编辑器打开 | 跳到改动文件 | ❌ | — |

## C. 代码审查 / Diff(整片缺失,他们的招牌)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 每任务 diff 计算 | ChangeExtractorService:从 git / OpenCode ledger / 日志算出改了哪些文件+hunks | ❌ | XL(后端) |
| 逐 hunk accept/reject | merge 工具条按钮 + 键盘 Ctrl+Enter/Alt+Enter | ❌ | L |
| 文件树侧栏 | 状态图标、搜索、已看追踪、mark-viewed、路径变更标注 | ❌ | M |
| CodeMirror 统一 diff | 语法高亮、折叠未变区、行号 | ❌ | M |
| Accept All / Reject All / Undo | 批量决策 + 撤销 | ❌ | S |
| 应用决策到工作区 | git apply 把接受的 hunk 落盘 | ❌ | L |
| 已看进度条 | % 文件已审 | ❌ | S |
| 审查中内联编辑 | 直接改 + keep draft / discard | ❌ | M |
| 冲突检测 | hunk 合并冲突 | ❌ | M |
| 范围越界警告 | 改动超出声明范围时 banner | ❌ | S |
| AI 置信度徽章 | confidence 评分 | ❌ | — |
| 改动统计 | +行/-行/文件数 | ❌ | S |
| 文件编辑时间线 | FileEditTimeline | ❌ | — |

## D. 成员 / 运行时 / 存活 (Members & Runtime)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 运行时遥测 sparkline | 每成员 CPU/RSS 历史(5s 采样)微图 + 悬浮 tooltip(PID/进程树/汇总 RSS) | ❌ | L |
| git branch / worktree 徽章 | 显示成员所在分支 + worktree 隔离标识 | ❌ | M |
| 启动状态阶梯 | starting/connecting/queued/bootstrap pending/failed + 诊断 | ⚠️ 我们只有 online/offline(本会话加了 last-seen) | M |
| 成员操作 | restart/relaunch、skip-for-launch、restore、复制启动诊断 JSON | ❌ | M |
| 任务进度条 | 该成员 % 完成 | ❌ | S |
| 等待回复指示 | awaiting-reply 旋转/告警 | ❌ | S |
| 成员详情 Stats 标签 | token 进/出、按文件 token、点击看文件改动 | ❌ | M |
| 成员详情 Logs 标签 | 执行日志流(工具调用/推理/bash 分解) | ⚠️ 我们有 Activity 标签(更简单) | M |
| 成员 hover 卡 | 悬浮显示状态/当前任务/最近活动 | ❌ | S |
| 实时运行时区 | 每成员 running/starting/waiting/degraded/stopped + model/lane/PID/source | ❌ | M |
| work-sync / nudge | agenda 同步、review-pickup、停滞时主动 nudge | ⚠️ 我们有 briefing(pull),无 push nudge | M |

## E. 实时进程 / 终端 (Live Processes & Terminal)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 进程面板 | 列出 agent 起的子进程,**Kill** 按钮、**Open URL** 按钮、端口、PID、归属成员、时间 | ❌ | M |
| 内嵌终端 (PTY) | spawn/write/resize/kill、命令历史、输出滚动 | ❌ | L |
| 终端 modal | Provider 登录流程(device-code 等) | ❌ | M |
| 接管/旁观 | 每成员可 watch / take-over 终端 | ❌ | L |

## F. 执行日志 / 会话分析 (Logs & Session Analysis)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| CLI 富日志视图 | 按 turn 折叠分组,工具调用(名/输入/输出)、思考、输出、**每步 token 数**、可展开输入输出 + 时长、搜索/严重度过滤 | ⚠️ 我们 Activity 简单版(无 token 计量、无可展开工具 I/O、无 turn 分组) | L |
| Claude logs 区 | 紧凑 + 全屏,source 选择器(lead/成员),live 指示 | ❌ | M |
| 成员日志流 | in_progress 时实时流 + 自动刷新 | ⚠️ 部分 | M |
| **会话报告 Tab** | 巨型报告:Key Takeaways、成本、按类别 token、工具、子 agent 树、错误、git、摩擦信号、时间线、质量、洞见 | ❌(整片缺失) | XL |
| 上下文窗口追踪 | 按 6 类(claude-md/文件/工具输出/思考/团队协调/用户)计 token + compaction 重置 | ❌ | L |
| Waterfall 时间线 | 会话时序可视化 | ❌ | M |

## G. 应用外壳 / 导航 (App Shell)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 多窗格分屏 | 最多并排多个 pane,可拖拽分隔,每 pane 独立 tab 栏与状态 | ❌(我们单窗格) | XL |
| Tab 布局 | 跨 pane 拖拽 tab、右键菜单(close/split/pin)、多选、中键关闭 | ❌ | L |
| 命令面板 (Cmd+K) | projects/sessions 搜索,匹配高亮,键盘导航 | ❌ | M |
| 全局全文搜索 | 跨 session/project 全文检索 | ⚠️ 我们有消息搜索 | M |
| 侧栏双标签 | Tasks \| Sessions,过滤/排序 popover,按日期分组,pin/hide | ⚠️ 部分 | M |
| 键盘快捷键 | Cmd+B 侧栏 / Cmd+K 面板 / Cmd+/ 帮助 / Cmd+P 快开 | ❌ | M |

## H. 设置 / 治理 (Settings & Governance)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 通用设置 | 主题/语言/启动项/浏览器/claude-root 路径/内置 HTTP server | ⚠️ 基础设置 | M |
| 连接设置 | SSH 模式、host 自动补全、auth 方式、测试连接、profiles | ❌ | L |
| 通知设置 | 细到每类型 + 每状态(Blocked/Completed/Review/...) + snooze + 自定义触发器 + solo-only + 测试 | ⚠️ 我们只有基础 inbox | M |
| 高级设置 | 重置/导出/导入 config、JSON 编辑器 | ❌ | S |
| **逐动作工具审批 / 自治治理** | 每个 MCP 工具 ask/do/delegate 策略,审批面板带 diff 预览,失焦 OS 通知 | ❌(整片缺失,战略空白) | L |
| 工作区信任 | workspace-trust 安全设置 | ❌ | M |

## I. 扩展 / 多 Provider (Extensions & Providers)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| Plugins 市场 | 安装/卸载、分类、详情 | ❌ | L |
| **MCP 服务器市场** | 搜索/浏览/安装/自定义/健康诊断 | ❌(我们只有 Skill Hub) | L |
| Skills 面板 | CRUD、代码编辑器、审核/批准 | ⚠️ 我们有 Skill Hub | M |
| API Keys 管理 | 掩码显示、增删改、Keychain 安全存储 | ❌ | M |
| Provider 仪表盘 | 多 provider 认证(Claude/Codex/OpenCode/Gemini)、装运行时、登录/登出、模型目录、速率限额、device-code 登录 | ❌(我们单 runtime) | XL |
| **多运行时** | codex/opencode/gemini 适配器,**每成员可选不同 runtime**,混编队 | ❌(后端) | XL |

## J. 调度 / Cron (Scheduling)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 调度视图 | cron 任务列表、pause/resume/trigger-now、运行历史 + 日志、时区 | ⚠️ 我们有 Routines(相近),但无运行历史/日志/立即触发 UI | M |

## K. Git / Worktree / 内置编辑器

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| **git worktree 隔离** | 每成员独立 worktree(clone/checkout/status/diff),防并行冲突 | ❌(后端,整片) | XL |
| **内置代码编辑器** | CodeMirror、文件树、多 tab、git 状态、搜索替换、goto-line、Cmd+P 快开、markdown 预览、minimap | ❌(整片) | XL |
| git 操作 | init repo、首次提交、分支跟踪、status | ❌ | M |

## L. 消息 / 跨团队 (Messaging & Cross-Team)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 跨团队消息 | 给另一个 team 的成员发消息、outbox、列目标 | ❌(后端+UI) | L |
| 发消息弹窗 | 收件人选择、action-mode(do/ask/delegate)、引用、附件、summary | ⚠️ 我们有聊天 + delegate | M |
| 语义消息元数据 | actionMode / messageKind / taskRefs / workSyncIntent / slashCommand | ⚠️ 我们有 delegate 类型 | M |
| 结构化任务引用 | `task://` 链接贯穿 消息/评论/描述,零宽字符保真 | ❌ | M |
| @mention 增强 | 建议下拉 + chip + 读追踪 | ⚠️ 我们有 @mention 路由 | M |
| slash 命令 | 输入框内 slash command + 结果回显 | ❌ | M |

## M. 任务数据模型 gap(后端字段)

他们的 Task 有、我们没有的字段:`displayId`(短 ID)、`description`(独立于 input)、`prompt`(给 agent 的特别指示)、`blockedBy[]`/`related[]`(依赖图)、`reviewIntervals[]`(每次审查计时)、结构化 `historyEvents[]`(带 type)、`attachments[]`、`sourceMessage`、`changePresence`(改动指纹)、`descriptionTaskRefs`。
我们已通过 task_metadata 覆盖层补了:`review`、`comments`(基础)。

## N. 通知系统 (Notifications)

| 能力 | 细节 | 我们 | 工作量 |
|---|---|---|---|
| 通知中心 | 类型化、未读徽章、OS 原生通知、snooze、自定义触发器、mark-read、clear、测试 | ⚠️ 我们有 inbox + push(更简单) | M |

---

## 汇总(按域,他们有而我们整片/大体没有的「大块」)

战略级缺失(XL,需新子系统):
1. **代码审查 / per-hunk diff**(C 全域)—— 他们的招牌,需后端 diff 引擎 + 前端 merge UI。
2. **多 Provider + 多运行时**(codex/opencode/gemini,每成员可选)—— 我们绑死单 runtime。
3. **git worktree 隔离** —— 并行 agent 不互相踩。
4. **内置代码编辑器**(K)。
5. **会话分析报告 + 上下文/成本追踪**(F)。
6. **多窗格/Tab 应用外壳 + 命令面板**(G)。

高价值中等(L/M,我们数据模型大体能撑):
7. **逐动作工具审批 / 自治治理**(H)—— 战略空白,只需策略层 + 审批 UI。
8. **实时进程面板 + 内嵌终端**(E)。
9. **运行时遥测(CPU/RSS sparkline) + 成员启动状态阶梯**(D)。
10. **跨团队消息 + 语义消息元数据 + task:// 引用**(L)。
11. **任务依赖图(blocks/blocked-by) + 附件**(A/B/M)。
12. **看板拖拽 + 过滤/排序 + 每列建任务 + 回收站**(A)。
13. **评论增强(回复/附件/已读/@) + 通知细粒度**(B/N)。
14. **执行日志富视图(token 计量 + 可展开工具 I/O + turn 分组)**(F)。

我们已经追平或更强的:A2A 协议层(REST+JSON-RPC、Agent Card、乐观锁、lease/reaper)、事件总线、存活性阶梯门控路由、review 解耦覆盖层、briefing(pull 式 agenda)、多 agent flight-recorder Timeline(他们只有单 agent)、聊天里的实时委派卡(他们没有)。
