# Workspace agent skills

Reusable skills that give launcher-connected agents extra workspace abilities
beyond the ones the launcher injects automatically (files / browser / todos /
knowledge).

These work with **any** runtime the agent-launcher drives (`agn`) because they
ride on the agent's own `exec`/`Bash` + `curl` — the launcher already hands the
agent the workspace endpoint, token header and channel. No launcher change
needed.

## a2a-delegation

Structured agent-to-agent delegation via the `/v1/a2a` gateway: an agent can
**create real Task objects** (not just `@mention`), drive their lifecycle, and
report results as artifacts — so delegations show up on the Tasks board with
accurate state. This is what connects the chat layer to the A2A task layer.

### Install (per agent / role)

Drop the skill into the agent's Claude Code skills directory. For a launcher
role at `~/.openagents/roles/<role>/`:

```sh
mkdir -p ~/.openagents/roles/<role>/.claude/skills/a2a-delegation
cp workspace/skills/a2a-delegation/SKILL.md \
   ~/.openagents/roles/<role>/.claude/skills/a2a-delegation/SKILL.md
```

Claude Code auto-discovers it on the agent's next turn (alongside the
launcher-generated `openagents-workspace` skill).

### Verify (live)

1. Bring up the workspace (`cd workspace && docker compose up -d`) and connect
   two `claude` agents to it via `agn` (a `master`/PM and a worker).
2. In chat, ask the PM to **delegate** a unit of work to the worker.
3. Confirm a card appears on the **Tasks** board in `submitted`, then moves to
   `working` and `completed` as the worker drives the lifecycle — i.e. the
   delegation is a real A2A Task, not just an `@mention`.

> Without this skill, agents fall back to delegating via plain `@mention` on the
> message bus; the A2A board is then only populated from the UI / API.
