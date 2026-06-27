# Launcher / claude-adapter follow-ups

Two issues found during live end-to-end testing of the A2A team workspace. Both
live in the **daemon / claude adapter** (the `openagents` CLI agent runtime),
**not** in `workspace/` (the gateway backend + web app), so they're tracked here
as cross-repo follow-ups rather than fixed in this repo.

Evidence below is from a real E2E run (3 online agents — product-manager,
frontend-developer, backend-developer — coordinating on a "remember me" feature).
The gateway backend itself was clean during the run: 4314 log lines, zero
errors/warnings, all HTTP 200.

---

## 1. Agent posts every answer twice (`thinking` carries full content + duplicate `chat`)

**Severity:** medium (correctness / cost; masked from the UI by a frontend workaround)
**Component:** claude adapter — message-posting path

### Symptom
For every substantive agent message, two events are emitted ~250ms apart:
1. `message_type=thinking` whose content is the **entire final answer** (not a `thinking…` placeholder)
2. `message_type=chat` with the **same** content

Verified in the gateway event stream: product-manager's "## 记住我需求拆解…" and
backend-developer's answer each appear twice (`thinking` then `chat`, identical
text, ~250ms apart).

### Impact
- 2× storage and 2× routing/event traffic for every agent turn.
- Leaks into any raw/unfiltered consumer (the A2A REST `/v1/a2a/messages`, future
  integrations). The web UI hides it with a thinking→chat dedup
  (`chat-messages.tsx`), but the source is wrong.

### Root cause (hypothesis)
The streaming `thinking` placeholder is populated with the fully-streamed final
text and then **not superseded** — the adapter posts a separate final `chat`
instead of finalizing the existing `thinking` message in place.

### Proposed fix
Either (a) keep `thinking` as a real lightweight placeholder and emit the full
content only once, as `chat`; or (b) finalize the streamed message in place
(same id, flip type → `chat`) instead of emitting a second event.

### Acceptance
One agent turn → exactly one persisted substantive message. The backend
`_SKIP_PERSIST` / frontend dedup workarounds become unnecessary.

---

## 2. Tool calls leak into the channel; agents consult via raw `curl` instead of the MCP tool

**Severity:** medium (noise + token-exposure smell)
**Component:** claude adapter (tool-use surfacing) + agent persona/tooling

### Symptom
A tool-invocation line surfaced into the team channel as a chat message:

    Bash › curl -s -H "X-Workspace-Token: …" …

captured live when frontend-developer consulted backend-developer mid-thread.

### Two problems
1. **Tool-use is surfaced as a channel message.** The adapter posts the agent's
   tool call as visible `chat` content. It should stay internal — or be a
   `status`/`thinking`-typed step that consumers filter — never a `chat` message.
2. **Agents consult via raw `curl` to `/v1/a2a/consult`** (per their CLAUDE.md
   persona) instead of the existing **MCP `consult_teammate` tool**
   (`workspace/mcp-a2a`). The MCP path is invisible plumbing and already wired
   (blocks for the reply, returns a structured result).

### Impact
- Channel noise (raw curl commands shown as messages).
- **Security smell:** the workspace token is printed verbatim into a persisted
  channel message.

### Proposed fix
- Adapter: never emit tool-call invocations as `chat`; if shown at all, type them
  `status`/`thinking` so consumers filter them (the gateway already drops those
  from routing).
- Personas: switch the consult instruction from `curl …/v1/a2a/consult` to the
  MCP `consult_teammate` tool.

### Acceptance
A mid-thread consult produces no `Bash › curl…` channel message and no token in
any persisted content; the consult still completes (verified live: backend
answered in 27s, 743 chars).
