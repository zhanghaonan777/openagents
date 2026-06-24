#!/usr/bin/env bash
# Unified live monitor for the multi-agent flow — tails the launcher daemon log
# and the backend log side by side, filtered to the signals that matter when
# troubleshooting routing / consult / liveness issues.
#
# Usage:  workspace/scripts/agent-monitor.sh            # follow live
#         workspace/scripts/agent-monitor.sh --since 30m  # backend backlog window
#
# Signals surfaced:
#   [agent]   Processing message … / Spawned … / adapter stopped / Poll (offline) / error
#   [router]  LLM router decision: next:X | stop
#   [consult] a2a consult: A → B asking / ANSWERED in Ns / TIMED OUT
#   [route]   offline_skipped, task.delegated
set -uo pipefail

DAEMON_LOG="${OPENAGENTS_DAEMON_LOG:-$HOME/.openagents/daemon.log}"
COMPOSE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docker-compose.yml"
SINCE="${2:-15m}"

echo "▶ agent-monitor  (daemon=$DAEMON_LOG, compose=$COMPOSE)"
echo "  Ctrl-C to stop."
echo

# Agent activity (launcher daemon) — strip the verbose poll noise.
if [[ -f "$DAEMON_LOG" ]]; then
  ( tail -n 50 -F "$DAEMON_LOG" 2>/dev/null \
      | grep --line-buffered -E "Processing message|Spawned persistent|adapter stopped|Rate limited|ERROR|error|consult|Poll #[0-9]+ failed|Heartbeat failed" \
      | sed -u -E 's/.*adapter \[([^]]+)\]: /[agent] \1 │ /; s/.*daemon: /[daemon] /' ) &
fi

# Backend routing + consult + liveness.
( docker compose -f "$COMPOSE" logs -f --since "$SINCE" backend 2>/dev/null \
    | grep --line-buffered -iE "LLM router decision|a2a consult|offline_skipped|task.delegated|workspace.task" \
    | sed -u -E 's/^backend-1[ ]*\| ?//; s/INFO:[^:]*://; s/LLM router decision/[router] decision/; s/a2a consult/[consult]/' ) &

wait
