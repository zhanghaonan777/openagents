# Adopting Agent Teams (777genius/agent-teams-ai) ideas into OpenAgents

Companion to `docs/multi-agent-landscape-and-gaps.md`. Agent Teams is a desktop
Electron app with the same product thesis as our workspace ("you're the boss,
agents are your team; they take tasks, message each other, review each other,
you watch the board"), but built entirely on local files (per-agent JSON
inboxes, `tasks/*.json`, `kanban-state.json`) — no server, no protocol. They
explicitly rejected A2A/ACP as too heavy for a desktop app.

Conclusion from the deep-read: **our protocol layer (Postgres event bus + A2A
gateway + optimistic locking) is more capable than theirs — don't borrow their
plumbing.** Their value is one layer up: workflow semantics, the review loop,
and a real liveness model. This doc records what we adopted.

## 1. Liveness ladder — fixes the "dead-agent routing" bug

Their strongest idea: never route to an agent that isn't actually reachable.
They classify each member on an evidence ladder and only the strong rungs are
routable.

Adopted as `app/services/liveness.py` — a single source of truth (`online`
**and** a fresh heartbeat, the heartbeat doubling as a lease; cloud agents
trust stored status). This de-duplicated the three inline copies (discover /
network views, and — by omission — the router) and added the missing gate:
`app/mods/workspace_mod.py` now derives a live set and gates **broadcast**,
**LLM-router candidates**, and the **master/first-participant fallback** to
live agents only. An explicit human `@mention` is still honoured (a deliberate
act) but offline targets are surfaced via `offline_skipped` metadata and shown
in chat ("X is offline — didn't reply"). Tests: `tests/test_llm_router.py`.

## 2. Review loop — "agents review each other"

Their headline feature, built on a key decoupling: review state lives in a
separate `kanban-state.json`, never mutating the task protocol state, so the two
can't clobber each other.

Adopted the same decoupling: a **review overlay in `task_metadata.review`**
(`state` = pending | approved | changes_requested, plus reviewer / comment),
exposed by three endpoints on `/v1/a2a` — `review/request` (defaults reviewer to
the delegator, forbids self-review), `review/approve`, and
`review/request-changes` (sends the contractor back to work with the feedback).
The A2A submitted→working→completed lifecycle is never touched. Frontend: the
board pulls a pending-review card into the Review column, shows a review badge +
reviewer + feedback, and offers Request review / Approve / Changes actions; the
sidebar shows a "needs review" count. Tests: `tests/test_a2a.py`.

## 3. Derived agenda (briefing) — "what's mine now"

Instead of returning the whole board, they derive an opinionated per-member
queue. Adopted as `GET /v1/a2a/briefing?agent=…`: an agent's actionable items
only, ordered review-pickup → rework → working → assigned (finished work
excluded). This suits our polling model — the briefing is the *pull* equivalent
of their push nudge, so an agent that hasn't picked up an assigned review sees
it at the top of its next briefing. Tests: `tests/test_a2a.py`.

## Considered, deliberately not adopted

- **Per-hunk diff review UI** (`@codemirror/merge`): our deliverables are text
  artifacts, not code diffs, so a merge editor would be speculative. The review
  card already surfaces the result artifact for the reviewer.
- **File-inbox transport, board lock, atomic-file verify**: our Postgres
  transactions + `version_id` optimistic lock already provide the atomicity
  their file-locking works around.
- **Push review nudges from a control plane**: their agents are file-watchers;
  ours poll, so the pull-based briefing is the natural fit.
