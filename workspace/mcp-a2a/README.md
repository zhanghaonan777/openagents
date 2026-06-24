# openagents-a2a-mcp

An MCP server that gives each OpenAgents agent **native tools to talk to its teammates** — `consult`, `delegate`, `message`, and `list`. Each tool is a thin wrapper over the workspace **A2A gateway** (`workspace/backend/app/routers/a2a.py`); there is no separate state.

The skeleton is adapted from [gilbarbara/agent-hub-mcp](https://github.com/gilbarbara/agent-hub-mcp) (verified with Claude Code); the tool semantics follow CrewAI's delegation tools (*Ask question / Delegate work to coworker*).

## Why a tool (not a message bus)

Agents reliably *initiate* contact when the action is a tool their model can choose to call. The two industry-standard patterns map onto our two A2A modes:

| Tool | Pattern | A2A backing |
|---|---|---|
| `consult_teammate(coworker, question)` | agent-as-tool (ask & get an answer) | `POST /v1/a2a/tasks` with `wait` (blocking) |
| `delegate_to_teammate(coworker, task)` | handoff (give the whole task) | `POST /v1/a2a/tasks` |
| `message_teammate(coworker, text)` | direct 1:1 DM | `POST /v1/a2a/messages` |
| `list_teammates()` | discovery | `GET /v1/a2a/agents` (Agent Cards) |
| `my_tasks()` | inbox | `GET /v1/a2a/tasks?contractor=me` |

## Build

```bash
cd workspace/mcp-a2a
npm install
npm run build
```

## Configure (per agent)

One instance runs per agent — `A2A_AGENT` identifies "me". Add to that agent's Claude Code MCP config:

```json
{
  "mcpServers": {
    "teammates": {
      "command": "node",
      "args": ["/abs/path/workspace/mcp-a2a/dist/index.js"],
      "env": {
        "A2A_BASE_URL": "http://localhost:8000",
        "A2A_NETWORK": "<workspace id>",
        "A2A_TOKEN": "<workspace token>",
        "A2A_AGENT": "frontend-developer"
      }
    }
  }
}
```

## Verify wiring (no MCP client needed)

```bash
A2A_NETWORK=<id> A2A_TOKEN=<token> A2A_AGENT=alice npm run smoke -- bob
```

## Note on triggering

A `consult`/`delegate` reaches the coworker through the same routing as the rest of the workspace: it lands in the pair's private channel and triggers the coworker **if they are online**. An offline teammate's task is recorded but not run until they're live — by design (the workspace never force-runs a dead agent).
