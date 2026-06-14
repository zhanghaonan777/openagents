# Status — role-driven team workspace + A2A delegation

Snapshot of the `feat/a2a-team-workspace` branch. Companion to
[`openagents-team-workspace-proposal.md`](./openagents-team-workspace-proposal.md)
and [`project-context-and-decisions.md`](./project-context-and-decisions.md).

## Done (committed, tested)

- **Visual / shell (module A)** — the new surfaces use the real product's
  design language (zinc/blue, white panels). No reskin needed.
- **Role library (module C)** — `lib/role-templates.data.ts`: **154 real roles**
  ingested from VoltAgent/awesome-claude-code-subagents (10 categories), search
  + category filter, "Add role" entry points (sidebar / chat input / header).
  Regenerate with `frontend/scripts/gen-roles.py`.
- **Kanban board (module B)** — `tasks-view.tsx` is a 4-column board backed by
  **real A2A tasks** (To Do / In Progress / Review / Done).
- **A2A gateway (backend)** — `/v1/a2a`: Agent Card discovery, Task lifecycle
  state machine (`submitted → working → input_required → completed/failed/
  canceled`), todos→task bridge, `task.delegated` event, skill declaration.
  Hardened: **optimistic-lock `version`** (CAS, no lost updates) + **lease +
  reaper** self-heal (orphan/stuck tasks time out). Backend tests **21/21**;
  full suite no new regressions.
- **a2a-delegation skill** — `workspace/skills/a2a-delegation/`: lets a
  launcher-connected agent create/advance real A2A Tasks via `exec`+`curl`,
  with no launcher change (closes the chat↔board gap, **pending a live-agent
  verification pass**).
- **Conformant A2A protocol surface (inbound)** — `routers/a2a_protocol.py` exposes
  each workspace agent over the **standard A2A protocol** so external A2A clients
  (a2a-sdk / ADK / CrewAI[a2a]) can interoperate: an Agent Card at
  `GET /a2a/{network}/{agent}/.well-known/agent-card.json` + a JSON-RPC 2.0
  endpoint (`message/send`, `tasks/get`, `tasks/cancel`, `tasks/list`) with the
  A2A Task/Message/Part/Artifact shapes, TaskState lifecycle, and JSON-RPC error
  model. Inbound `message/send` bridges to the internal delegation layer.
  Hand-rolled to the v1.0 spec (no heavy protobuf dep); verified live via raw
  JSON-RPC + a 4-test conformance suite.
- **Proven live** — real `claude` agents connected to a local self-hosted
  workspace running this backend, conversed, delegated (via bus), and
  brainstormed. (The "connect agents to a *local* workspace" item from the
  context doc is now validated.)

## Remaining backlog (from the multi-agent design review)

### P0
1. **Native delegation contract, end-to-end** — the `a2a-delegation` skill makes
   it *possible* for agents to create Tasks; verify it live and, ideally, fold
   the A2A curl docs into the launcher's generated workspace skill
   (`@openagents-org/agent-launcher`, **separate repo** — not in this fork).
2. **Identity binding (`verifiedSender`) + scoped/attenuated capability tokens.**
   Today the workspace token grants full authority and `source` is
   caller-asserted (spoofable), consistent with `/v1/events` and `/v1/todos`.
   Real fix = server-derived sender + downscoped delegation tokens
   (`{delegator, delegatee, capability, contextRef, exp, maxDepth, maxFanout}`).
   This is a **workspace-wide auth-model change** (touches events/todos/all of
   the backend), not an A2A-only edit. Partial step shipped: contractor must be
   a real member. Also add a `security_events` (allow/deny) audit stream.

### P1
3. Demote the broadcast bus to a fallback; make **Task-based directed delivery**
   the primary path (don't wake unrelated agents); pass `context_ref` pointers
   instead of full history (caps the O(agents×turns) token blow-up).
4. Single `delegation-core` + shared schema package (one source of truth for the
   two collaboration paths; kills contract drift) and **pure-function core**
   (`route` / `transition`) so the logic is unit-testable off the bus/LLM.
5. Structured `DelegationError{code, retryable, cause}` + `traceId` across
   `delegationId → taskId → bus message` for observability.
6. **Frontend tests** — no frontend test setup exists yet (only `tsc` + build).

### P2
7. External A2A interop — **inbound JSON-RPC + `/.well-known/agent-card.json` done**
   (routers/a2a_protocol.py). Remaining: **outbound client** (our agents calling
   *external* A2A agents), **SSE `message/stream`** + `tasks/resubscribe`, push
   notifications, **signed Agent Cards** + richer `securitySchemes`, and the
   `REJECTED`/`AUTH_REQUIRED` states. (True per-agent peer hosting — each agent
   running its own A2A server — needs launcher changes; the central backend
   hosting per-agent A2A endpoints is conformant from a client's perspective.)
8. `canonical()` idempotency-key versioning + golden tests; Task-tree
   `pending_children` accounting.

## Completion estimate (honest)

- As a **working prototype / demo**: ~80% — runs end-to-end with real agents,
  real backend, real UI.
- As a **production feature**: ~45–55% — the scaffolding (UI, A2A data model,
  lifecycle, concurrency hardening) is solid and tested; the two P0s (native
  delegation verified end-to-end + identity binding) and the P1 refactors
  remain. Lives on a feature branch; not merged.
