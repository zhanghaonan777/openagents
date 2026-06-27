# -*- coding: utf-8 -*-
"""Timeline — the project's institutional memory (a faithful event archive).

`POST /v1/timeline/capture` records a discussion thread's concluding message
VERBATIM as a DECISION milestone — no AI rewriting, so the archive is accurate.
`GET /v1/timeline` lists the milestones, newest first.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Channel, EventRecord, Milestone
from app.response import ResponseCode, json_response, success_response
from app.routers.network import _resolve_workspace, _verify_workspace_access

router = APIRouter(prefix="/v1/timeline", tags=["timeline"])


def _auth(db, network, token, authorization):
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return None, json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, token, authorization):
        return None, json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")
    return workspace, None


def _serialize(m: Milestone) -> dict:
    return {
        "id": m.id,
        "kind": m.kind,
        "title": m.title,
        "summary": m.summary,
        "detail": m.detail,
        "participants": m.participants or [],
        "channelId": m.channel_id,
        "createdBy": m.created_by,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
    }


class CaptureRequest(BaseModel):
    network: str
    channel: str                 # channel name (the thread to distill)
    kind: str = "decision"
    created_by: Optional[str] = None


def _channel_history(db, workspace_id, channel_name: str, limit: int = 40):
    """Return (history_text, speakers, last_agent_text) for a channel's chat."""
    rows = db.execute(
        select(EventRecord)
        .where(
            EventRecord.network_id == workspace_id,
            EventRecord.target == f"channel/{channel_name}",
            EventRecord.type == "workspace.message.posted",
        )
        .order_by(EventRecord.timestamp.desc())
        .limit(limit)
    ).scalars().all()
    rows.reverse()
    lines, speakers, last_agent = [], [], None
    for evt in rows:
        p = evt.payload or {}
        if p.get("message_type") in ("thinking", "status", "todos"):
            continue
        src = evt.source
        label = "human" if src.startswith("human:") else src.split(":", 1)[-1]
        text = (p.get("content") or "").strip()
        if not text:
            continue
        if src.startswith("openagents:"):
            if label not in speakers:
                speakers.append(label)
            last_agent = text  # the concluding agent message, by the end of the loop
        lines.append(f"[{label}] {text[:800]}")
    return "\n".join(lines), speakers, last_agent


@router.post("/capture")
def capture_milestone(
    body: CaptureRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace, err = _auth(db, body.network, x_workspace_token, authorization)
    if err:
        return err

    channel = db.execute(
        select(Channel).where(Channel.workspace_id == workspace.id, Channel.name == body.channel)
    ).scalar_one_or_none()

    history, speakers, last_agent = _channel_history(db, workspace.id, body.channel)
    if not history:
        return json_response(ResponseCode.BAD_REQUEST, "Nothing to capture — the thread has no messages")

    # Faithful record — NO AI rewriting. The decision is the thread's concluding
    # message, kept verbatim (summary = its first line, detail = the message as-is),
    # so the timeline is an accurate archive, not an AI re-narration.
    title = (channel.title if channel and channel.title else "Decision")
    summary = last_agent.split("\n", 1)[0].lstrip("#* ").strip()[:220] if last_agent else None
    detail = last_agent[:4000] if last_agent else None
    parts = speakers

    m = Milestone(
        workspace_id=workspace.id,
        channel_id=channel.id if channel else None,
        kind=body.kind,
        title=title[:200],
        summary=summary,
        detail=detail,
        participants=parts,
        created_by=body.created_by,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return success_response(_serialize(m))


@router.get("")
def list_timeline(
    network: str,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace, err = _auth(db, network, x_workspace_token, authorization)
    if err:
        return err
    rows = db.execute(
        select(Milestone)
        .where(Milestone.workspace_id == workspace.id)
        .order_by(Milestone.created_at.desc())
        .limit(200)
    ).scalars().all()
    return success_response({"milestones": [_serialize(m) for m in rows]})
