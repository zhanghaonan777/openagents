"""Stable, human-readable short ids for system entities.

The visible "编号": a short code derived deterministically from an agent's
identity, so the *same* code shows up in the API response, the UI badge, and the
logs without having to store or coordinate anything. Two different agents (even
the same role name in two workspaces) get different codes; the same agent always
gets the same one.
"""
import hashlib


def agent_code(workspace_id, agent_name: str) -> str:
    """4-hex-char code for an agent, e.g. "7f3a". Stable per (workspace, agent)."""
    h = hashlib.sha1(f"{workspace_id}:{agent_name}".encode("utf-8")).hexdigest()
    return h[:4]
