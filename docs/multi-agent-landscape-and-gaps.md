# Multi-Agent Landscape — A2A, Task Management, Frontend — and where OpenAgents-team stands

Competitive/landscape research (2024–2026) to position our role-driven A2A team workspace.
Three lenses: **coordination & A2A protocols**, **task management**, **frontend display** — each
mapped against what we actually built, with a prioritized gap list.

---

## 0. TL;DR

- The field has **converged on orchestrator-worker + handoff coordination over shared *structured
  state*** — and the best systems (Anthropic, MetaGPT, ChatDev) **deliberately avoid open multi-agent
  chat** because free-form chatter causes cascading hallucination + context blow-up. Our design
  bet — *structured A2A Task delegation as the primary path, @mention only for quick sync* — is the
  right one.
- The **wire is standardizing**: MCP (vertical: agent→tools) + **A2A** (horizontal: agent→agent,
  donated to the Linux Foundation Jun 2025; IBM ACP merged in Sep 2025; v1.0 stable ~Mar 2026). Our
  hand-rolled A2A gateway + Agent Card + Task lifecycle is **standards-aligned** — rare for a fork.
- **Frontend split-screen (chat + live workspace) is now table stakes.** The differentiators are the
  things that make **multi-agent parallelism legible and governed**: flight-recorder timelines with
  per-agent lanes, taskboards + receipts + plan→approve gates, and orchestrator→subagent hierarchy
  views. We already have a taskboard + a typed per-agent activity timeline + an agent inspector — a
  strong base; the gaps are lanes/failures-first, receipts/approval gates, and a hierarchy view.
- **Parallelism is the field's open problem.** Everyone is adding concurrency (AutoGen v0.4 actors,
  LangGraph Send API, Devin multi-VM), but Anthropic admits orchestrators still **wait synchronously**
  and multi-agent burns **~15× tokens**. Our parallel-delegation + delegate-and-wait sits exactly on
  this frontier.

---

## 1. Coordination patterns & A2A protocols

**Dominant coordination archetypes (2025–2026):**

| Pattern | Who | Note |
|---|---|---|
| **Orchestrator-worker** (lead decomposes → delegates via task strings → aggregates) | Anthropic research system, Magentic-One, Devin/MultiDevin, Manus, CrewAI hierarchical, LangGraph supervisor | **Dominant for complex open-ended work.** Comms = delegation-and-return, *not* peer chat. |
| **Handoff** (control + history transfers; receiver "becomes" active) | OpenAI Swarm / Agents SDK, LangGraph `Command`/swarm, AG2 swarm | Dominant for conversational routing. |
| **Group-chat** (shared thread, manager picks next speaker) | AutoGen / AG2 GroupChat | Good for brainstorm/critique; criticized for cost, non-determinism, context pressure. |
| **SOP pipeline** (fixed role assembly line) | MetaGPT, ChatDev, CrewAI sequential | Best for well-specified, decomposable work (software gen). |
| **Blackboard / shared structured state** | LangGraph state, ADK `session.state`, MetaGPT message pool, Manus `todo.md` | The *underlying mechanism* — passing typed state beats passing free-form messages. |

**Protocol consolidation** ([survey arXiv:2505.02279](https://arxiv.org/abs/2505.02279)):

| Protocol | Layer | Transport | For |
|---|---|---|---|
| **MCP** (Anthropic, 2024) | agent ↔ tools (vertical) | JSON-RPC 2.0 / stdio / HTTP+SSE | "USB-C for AI"; tools/resources/prompts |
| **A2A** (Google→[Linux Foundation](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents)) | agent ↔ agent (horizontal) | JSON-RPC 2.0 / HTTP / SSE | opaque cross-vendor delegation; Agent Cards + Tasks |
| **ACP** (IBM) | agent ↔ agent (REST) | REST / MIME | **merged into A2A, Sep 2025** |
| **ANP** | agent ↔ agent (open internet) | HTTPS / JSON-LD / W3C DIDs | future fully-decentralized marketplace |

Key references: [A2A spec](https://a2a-protocol.org/latest/specification/) · [Anthropic multi-agent system](https://www.anthropic.com/engineering/built-multi-agent-research-system) · [Magentic-One](https://arxiv.org/html/2411.04468v1) · [building effective agents](https://www.anthropic.com/research/building-effective-agents).

---

## 2. Task management — the strongest ideas

- **Typed Task + explicit state machine** (A2A): server-generated id; 9 states across *active*
  (`submitted`/`working`), *interrupted-resumable* (`input-required`/`auth-required`), *terminal*
  (`completed`/`failed`/`canceled`/`rejected`), `unknown`. Terminal rejects new input; interrupted
  resumes by re-sending against the same `taskId`+`contextId`.
- **Message-vs-Task duality**: return the *cheapest representation that fits* — a stateless `Message`
  for quick Q&A, a tracked `Task` only for long-running/artifact work.
- **Artifacts, not chat, for results** — with `append`/`last_chunk` streaming so large outputs flow
  incrementally to files/external memory instead of bloating the orchestrator context.
- **"What to do" vs "what done looks like"** (CrewAI `description` + `expected_output`) — the latter
  doubles as prompt, acceptance rubric, and guardrail anchor.
- **Dependency-as-barrier parallelism** (CrewAI `context=[asyncA, asyncB]`, LangGraph super-steps):
  declare the dependency, get fan-out → synchronize for free, no manual awaits.
- **Dual-ledger orchestrator** (Magentic-One): *Task Ledger* (facts + plan) + *Progress Ledger*
  (satisfied? looping? progressing? who's next? + **stall counter** → rewrite plan & reset). The best
  self-correcting task-tracking loop.
- **Two delegation modes, chosen on purpose**: *handoff* (control transfers, specialist owns the
  user) vs *agent-as-tool* (control returns, orchestrator synthesizes).
- **Durable execution**: checkpoint after each step, resume at the failed unit, cache completed
  sub-tasks so they don't re-run (LangGraph checkpointer / `@task`; Temporal-style replay).
- **HITL as a first-class interrupted state** + a product-layer **plan-approval pause** (Devin's 30s
  gate; Claude Code Plan Mode).
- **Two async-update channels**: SSE (live, with resubscribe) + webhooks/push (long/disconnected).
- **Scale effort to complexity & bound fan-out** (Anthropic): explicit complexity→subagent-count
  rules; granular task boundaries to avoid duplicate work; tokens drive ~80% of perf variance.
- Product task UIs: Claude Code's persistent, cross-session, **dependency-aware** `TaskCreate/Update`
  (`blockedBy`); Manus's `todo.md` as *attention control* (but over-updating wastes ~⅓ of actions).

---

## 3. Frontend display — what actually wins

- **Split-screen (chat left / live workspace viewer right)** = now the default (Operator, Manus,
  Devin). **Table stakes, not a differentiator.** ([Emerge Haus](https://www.emerge.haus/blog/the-new-dominant-ui-design-for-ai-agents))
- **The real differentiators** make multi-agent work *legible + governed*:
  - **Flight-recorder activity timeline** — chronological, collapsible, drill-to-trace; **horizontal
    lanes per parallel agent**; **"failures only"** filter; pivot to the full trace waterfall.
    ([Honeycomb Agent Timeline](https://www.honeycomb.io/blog/agent-timeline-flight-recorder-for-your-ai-agents))
  - **Taskboard + receipts + plan→validate→execute gates** — kanban of goals/tasks/owners/status;
    every action emits a reversible, audited *receipt*; irreversible actions gated. ([HatchWorks](https://hatchworks.com/blog/ai-agents/agent-ux-patterns/))
  - **Orchestrator→subagent hierarchy / org-chart view** — Claude Code's [Agent View](https://claude.com/blog/agent-view-in-claude-code)
    (one dashboard of background sessions: needs-input / working / done, answer inline to unblock).
  - **Agent inspector / role cards** — role, tools, permissions, sessions, *why routing happened*.
- **Streaming**: render reasoning ("Thinking… → Thought for Xs", collapsible), tool calls as they
  assemble, separated from final output — and surface **rationale/sources, not raw chain-of-thought**.
- **Progressive disclosure** is the throughline: simple status by default, full trace on demand —
  never a wall of text.
- Emerging standard for agent→UI streaming: **AG-UI** (17 typed events over SSE/WS; LangGraph/CrewAI/
  Mastra/etc. plug into any AG-UI frontend). Dev observability standard: **OpenTelemetry GenAI**
  (`invoke_agent`→`chat`+`execute_tool` spans threaded by `conversation.id`).

---

## 4. Where OpenAgents-team stands (the mapping)

| Dimension | Industry best | **What we have** | Gap / opportunity |
|---|---|---|---|
| **Coordination** | orchestrator-worker + handoff over structured state; avoid open chat | **Dual path**: @mention + Haiku next-speaker router (serial chat) **and** structured A2A Task delegation (parallel). `@all` broadcast. | ✅ Strong — matches "delegate-and-return". Add a **dual-ledger PM** (Task+Progress ledger, stall→replan) via the skill. |
| **A2A conformance** | Agent Card + JSON-RPC 2.0 + Task lifecycle + artifacts; SSE + webhooks; signed cards | Agent Card at `/.well-known/agent-card.json`, JSON-RPC `message/send`/`tasks.*`, Task objects, artifacts. | ✅ Standards-aligned (rare). Missing: **`message/stream` (SSE)**, **push webhooks**, signed cards, `auth-required`/`unknown` states. |
| **Task object** | typed state machine; optimistic lock; durable resume; expected_output | `TaskRecord`: 7/9 A2A states, **version_id optimistic lock**, **lease + reaper self-heal**, artifacts, history, `contextId`=channel, todos→task bridge. | Add **message-vs-task duality** (don't always mint a task), **`expected_output`/acceptance rubric**, **checkpoint resume** (we self-heal but don't resume). |
| **Delegation modes** | handoff vs agent-as-tool | **delegate** (kickoff @mention) + **delegate-and-wait** (blocking → synthesize) = agent-as-tool. | ✅ Both present. |
| **Parallelism** | fan-out; but orchestrators still wait; ~15× tokens | **Parallel delegation** (N tasks, background `&`); board shows concurrent flow. | On the frontier. Add **dependency-as-barrier** (declare `blockedBy`, auto fan-out→synthesize) + **async updates** (replace 5s poll w/ SSE/webhook). |
| **HITL** | interrupted state + plan-approval gate + receipts | `input-required` state exists. | Add a **plan→approve gate** for consequential delegations + **action receipts**. |
| **Frontend** | split-screen; flight-recorder lanes; taskboard+receipts; hierarchy view; role cards | **Tasks Kanban** (4 cols) · **per-agent Activity timeline with typed tags** (Thinking/Tool/Message/Delegate) · **agent inspector panel** (Tasks/Activity/Profile, click→session) · **monitor grid** (multi-agent tiles) · role library (154 roles) · markdown + **live 5s polling**. | Strong base. Add: **parallel-agent lanes + "failures only"** in the timeline; **receipts + plan/approve**; **orchestrator→subagent hierarchy tree**; deeper **split-screen workspace viewer**. |
| **Observability** | OTel GenAI spans; trace waterfall; cost tracking | Per-agent activity stream (our `source`-filtered events). | Add **OTel GenAI** export, a **trace/waterfall**, and **token/cost tracking** per task/agent. |
| **Agents** | mostly framework objects | **Real launcher-driven processes** (claude / openclaw), runtime-decoupled roles. | ✅ Differentiator — these are actual agents, not just SDK objects. |

---

## 5. Recommended next steps (prioritized)

**High value / low-to-medium effort**
1. **Streaming task updates** — implement A2A `message/stream` (SSE) and/or webhook push; let the
   board + activity timeline subscribe instead of 5s polling. Most-cited gap; improves latency + scale.
2. **Message-vs-task duality** — for quick `@mention` asks, return a plain reply; only mint a
   `TaskRecord` for trackable work. Stops the board filling with trivia.
3. **Flight-recorder upgrades to the activity timeline** — we already tag Thinking/Tool/Message;
   add **per-agent lanes** + a **"failures only"** filter + drill-into-tool-detail.
4. **Action receipts + plan→approve gate** — surface "what changed / by whom / undo" and a two-phase
   confirm before consequential delegations (the production trust layer).

**Medium**
5. **Dependency-aware tasks** (`blockedBy`) + **dependency-as-barrier** parallel fan-out → auto
   synthesize (CrewAI/LangGraph pattern); show edges on the board.
6. **Orchestrator→subagent hierarchy view** — extend the monitor grid into a tree (Claude Agent View
   style: needs-input / working / done at a glance).
7. **Dual-ledger PM** — encode Magentic-One's Task+Progress ledger + stall→replan into the PM agent's
   skill for self-correcting multi-step delegation.

**Larger / standards**
8. **Durable resume** — checkpoint task progress + resume the failed unit (we self-heal via reaper but
   restart, not resume).
9. **Adopt standards** — **AG-UI** for agent→frontend streaming and **OpenTelemetry GenAI** for
   observability, so we interoperate with the wider ecosystem instead of bespoke polling.
10. **External A2A interop** (deprioritized per current scope) — signed Agent Cards + the missing
    JSON-RPC surface for true cross-vendor delegation, if/when we want outside agents to participate.

---

### Source index
A2A: [spec](https://a2a-protocol.org/latest/specification/) · [LF launch](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents) · [ACP→A2A](https://lfaidata.foundation/communityblog/2025/08/29/acp-joins-forces-with-a2a-under-the-linux-foundations-lf-ai-data/) · protocol survey [arXiv:2505.02279](https://arxiv.org/abs/2505.02279).
Coordination: [Anthropic multi-agent](https://www.anthropic.com/engineering/built-multi-agent-research-system) · [building effective agents](https://www.anthropic.com/research/building-effective-agents) · [Magentic-One](https://arxiv.org/html/2411.04468v1) · [CrewAI processes](https://docs.crewai.com/en/concepts/processes) · [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) · [OpenAI Agents SDK multi-agent](https://openai.github.io/openai-agents-python/multi_agent/) · [Google ADK patterns](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/) · [MetaGPT](https://arxiv.org/abs/2308.00352) · [ChatDev](https://arxiv.org/abs/2307.07924).
Task mgmt: [CrewAI tasks](https://docs.crewai.com/en/concepts/tasks) · [A2A streaming](https://a2a-protocol.org/latest/topics/streaming-and-async/) · [Claude Code todos/tasks](https://code.claude.com/docs/en/agent-sdk/todo-tracking) · [Manus context engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) · [OTel GenAI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/).
Frontend: [Emerge Haus split-screen](https://www.emerge.haus/blog/the-new-dominant-ui-design-for-ai-agents) · [HatchWorks UX patterns](https://hatchworks.com/blog/ai-agents/agent-ux-patterns/) · [Honeycomb Agent Timeline](https://www.honeycomb.io/blog/agent-timeline-flight-recorder-for-your-ai-agents) · [Claude Code Agent View](https://claude.com/blog/agent-view-in-claude-code) · [AG-UI](https://www.copilotkit.ai/blog/introducing-ag-ui-the-protocol-where-agents-meet-users) · [LangGraph Studio](https://www.langchain.com/blog/langgraph-studio-the-first-agent-ide).
