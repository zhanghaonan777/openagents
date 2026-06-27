"""Tiny logfmt-style helper for structured, ID-tagged log lines.

The system's behaviour spans several hops — an inbound event is routed to agents,
which spawn A2A tasks, which transition through states. To trace one journey you
need a stable correlation id (the inbound ``event.id``) and consistent entity ids
(``ws=`` ``ch=`` ``agent=`` ``task=`` ``role=``) on every line.

``kv()`` renders those as ``key=value`` pairs so logs are greppable and joinable:

    logger.info("route %s", kv(event=event.id, ws=workspace.id, ch=channel.name,
                               src=event.source, targets=targets))
    # → route event=01J… ws=5dcb… ch=session-ab12 src=openagents:alice targets=bob,carol

None values are dropped; empty lists render ``-``; values with spaces are quoted.
"""
from typing import Any


def _fmt(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v) if v else "-"
    s = str(v)
    if s == "":
        return '""'
    if " " in s or "=" in s or '"' in s:
        return '"' + s.replace('"', "'") + '"'
    return s


def kv(**fields: Any) -> str:
    """Render keyword fields as space-separated ``key=value`` pairs, skipping None."""
    return " ".join(f"{k}={_fmt(v)}" for k, v in fields.items() if v is not None)
