"""Agent liveness — the single source of truth for *is this agent reachable right now?*

Historically three call sites (the workspace `discover` view, the legacy
`network` view, and — by omission — the message router) each re-derived
"online, unless the heartbeat went stale" inline. The router never did, which
let messages get routed to **dead agents**: a member row whose launcher had
gone away still looked routable, so a broadcast / LLM-router pick / fallback
could select it and the message would wedge with no reply.

This module centralises that judgement as a small *evidence ladder*: a member
is only ``live`` (routable) when it claims ``online`` **and** its heartbeat is
fresh — the heartbeat doubling as a lease. Cloud agents don't heartbeat, so
their stored status is trusted as-is. A member with status ``online`` but no
heartbeat yet (just joined, or a legacy row) is trusted too, matching the
existing view behaviour; only a *stale* heartbeat downgrades to offline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import config

# Heartbeat lease: a non-cloud member that hasn't beat within this window is
# treated as offline regardless of its stored status.
AGENT_TIMEOUT = timedelta(seconds=config.AGENT_TIMEOUT_SECONDS)


def is_cloud_member(member) -> bool:
    """Cloud-hosted agents (agent_type ``cloud:*``) don't send heartbeats."""
    return (getattr(member, "agent_type", None) or "").startswith("cloud:")


def effective_status(member, now: datetime) -> str:
    """The member's status, downgraded to ``offline`` when its lease expired.

    Mirrors the inline logic the discover/network views used, so all three
    surfaces (and the router) agree on who is online.
    """
    status = member.status or "offline"
    if is_cloud_member(member):
        return status
    hb = getattr(member, "last_heartbeat", None)
    if hb is None:
        # Never heartbeat (fresh join / legacy row): trust stored status.
        return status
    if hb.tzinfo is None:
        # SQLite stores naive datetimes; assume UTC for the comparison.
        hb = hb.replace(tzinfo=timezone.utc)
    if (now - hb) > AGENT_TIMEOUT:
        return "offline"
    return status


def is_live(member, now: datetime) -> bool:
    """True when the member is reachable and safe to route work to."""
    return effective_status(member, now) == "online"


def live_agent_names(members, now: datetime) -> set[str]:
    """The subset of ``members`` (by agent_name) that are routable right now."""
    return {m.agent_name for m in members if is_live(m, now)}
