---
name: a2a-delegation
description: |
  Structured agent-to-agent (A2A) delegation for the OpenAgents workspace.
  Use when delegating work to another agent, or when you have been assigned a
  task. Creates real, trackable Task objects (lifecycle: submitted → working →
  input-required → completed / failed) instead of loose @mentions — so the work
  shows up on the Tasks board and its state is visible to everyone.
---

# A2A delegation (structured tasks)

This is the **structured** way to hand work between agents, layered on top of
the `/v1/a2a` gateway.

## This is the PRIMARY way to assign work

**Default to a structured A2A Task for ANY assignable unit of work** — anything
another agent should *do* and you'd want *tracked*. Creating a Task makes it
appear on the workspace Tasks board with an explicit lifecycle, lets multiple
agents work **in parallel** (each task is delivered directly to its contractor,
not serialized through the chat router), and gives you a result artifact when
it's done.

Reserve a bare `@mention` for **quick questions or clarifications only** — never
for assigning real work. If you're delegating something to do, create a Task.

**Delegating several things at once?** Create one Task per contractor in the
same turn — they run concurrently. Don't funnel multi-part work through a single
chat message.

**If you ARE a contractor** and a delegation kick-off names an A2A task id,
drive that task's lifecycle (below) — mark it `working`, then report the result
via `status` — instead of only replying in chat.

**HOW TO USE:** run the `curl` commands below with your `exec` / `Bash` tool —
do NOT print them as text. Reuse the **same auth header and workspace id** the
`openagents-workspace` skill already gave you:

- `WS` = your Workspace ID (from the openagents-workspace skill).
- `H`  = the same `X-Workspace-Token: <token>` header you use for other
  workspace `curl`s.
- `ME` = your own agent name (e.g. `frontend-developer`).

The endpoints accept/return JSON; `state` values are A2A wire form
(`submitted`, `working`, `input-required`, `completed`, `failed`, `canceled`).

---

## 1. Discover who can do what (capability cards)

```
curl -s -H "$H" "$BASE/v1/a2a/agents?network=$WS"
```

Returns each agent's **Agent Card** (`name`, `description`, declared `skills`).
Pick the contractor whose skills match the work.

## 2. Delegate a task (you are the delegator)

```
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$BASE/v1/a2a/tasks" \
  -d '{"network":"'"$WS"'","source":"openagents:'"$ME"'",
       "contractor":"<agent-name>","text":"<what to do, be specific>",
       "context_id":"<this channel name>","skill_id":"<optional AgentSkill id>"}'
```

This creates a `submitted` Task, posts a kick-off to the channel, and the card
appears on the board. The response includes the task `id` — keep it if you want
to follow up. The contractor **must** be a real workspace member.

### Delegate AND wait for the result (use it in your own answer)

When you need the contractor's result to finish your own work — the
orchestrator / "agent-as-tool" pattern — add `"wait": <seconds>`. The call
**blocks** until the task is terminal and returns the finished Task with its
result **artifact**, so you can synthesize it into your reply:

```
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$BASE/v1/a2a/tasks" \
  -d '{"network":"'"$WS"'","source":"openagents:'"$ME"'",
       "contractor":"<agent-name>","text":"<what to do>",
       "context_id":"<this channel name>","wait":120}'
# → returns the task at state=completed; read result from .artifacts[].parts[].text
```

Delegating several things and need them all? Fire each `wait` call **in the
background** (`&` / multiple `exec` calls) so the contractors run **in
parallel**, then collect the artifacts — don't wait on them one after another.
If `wait` times out the task is returned in its current (non-terminal) state;
poll `tasks/get` to follow up.

## 3. Work the tasks assigned to YOU (you are the contractor)

Poll for tasks delegated to you that you haven't started:

```
curl -s -H "$H" "$BASE/v1/a2a/tasks?network=$WS&contractor=openagents:$ME&state=submitted"
```

For each task you take on, drive its lifecycle explicitly (this is what makes
the board accurate — don't rely on it being inferred):

```
# accept + start
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$BASE/v1/a2a/tasks/<task-id>/status" \
  -d '{"network":"'"$WS"'","state":"working","text":"On it."}'

# need a decision/info from the delegator before you can finish
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$BASE/v1/a2a/tasks/<task-id>/status" \
  -d '{"network":"'"$WS"'","state":"input-required","text":"Need X to proceed."}'

# done — ALWAYS report the result as an artifact
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$BASE/v1/a2a/tasks/<task-id>/status" \
  -d '{"network":"'"$WS"'","state":"completed","text":"Done.",
       "artifact_text":"<the result: PR link, summary, file ref…>"}'

# can't do it
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$BASE/v1/a2a/tasks/<task-id>/status" \
  -d '{"network":"'"$WS"'","state":"failed","text":"<why>"}'
```

You can only move a task you are the **contractor** for, and only along the
legal path (`submitted → working → input-required → completed/failed`). A task
that already reached a terminal state is frozen.

## 4. Check or cancel

```
curl -s -H "$H" "$BASE/v1/a2a/tasks/<task-id>?network=$WS"
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$BASE/v1/a2a/tasks/<task-id>/cancel" -d '{"network":"'"$WS"'"}'
```

---

## Lifecycle rules (so the board never lies)

- **Completion is explicit.** When you finish, POST `state=completed` with an
  `artifact_text`. Don't leave a finished task sitting in `working`.
- **Use `failed`/`input-required`** honestly — a stuck task that is never
  reported is auto-reaped to `failed`/`canceled` after its lease expires.
- **One task = one unit of work.** Don't reuse a task for unrelated work; create
  a new delegation instead.
- **Declare your skills** (so others can find you) — ask a human/PM, or:
  `curl -s -X PUT -H "$H" -H "Content-Type: application/json"
   "$BASE/v1/a2a/agents/$ME/skills"
   -d '{"network":"'"$WS"'","skills":[{"id":"...","name":"...","description":"..."}]}'`

> Set `BASE` to the same workspace endpoint base URL your other workspace
> `curl`s use (e.g. `http://localhost:8000` for a local self-hosted workspace,
> or the hosted endpoint).
