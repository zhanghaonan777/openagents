# -*- coding: utf-8 -*-
"""Timeline — the project's institutional memory.

`POST /v1/timeline/capture` distills a discussion thread into a structured
DECISION milestone via the LLM (title + one-line verdict + rationale +
participants) so a concluded discussion is remembered instead of scrolling away.
`GET /v1/timeline` lists the milestones, newest first.
"""
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm
from app.database import get_db
from app.models import Channel, EventRecord, Milestone
from app.response import ResponseCode, json_response, success_response
from app.routers.network import _resolve_workspace, _verify_workspace_access

router = APIRouter(prefix="/v1/timeline", tags=["timeline"])
logger = logging.getLogger(__name__)


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


_DISTILL_PROMPT = """You are recording a team discussion as a structured DECISION for a project timeline.

Discussion (oldest first):
{history}

Return ONLY a JSON object (no markdown fences, no prose) with exactly these keys:
- "title": short noun phrase naming the decision, <= 12 words
- "summary": the FINAL decision in ONE sentence (empty string "" if no clear decision was reached)
- "detail": 2-4 sentences of rationale — key tradeoffs and who argued what (markdown allowed)
- "participants": array of the participant names that took part

Answer in the SAME language as the discussion."""


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


def _parse_json(raw: str) -> Optional[dict]:
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


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

    # Distill with the LLM when one is configured; otherwise fall back to the
    # concluding agent message as the decision record (so capture always works).
    data: dict = {}
    if llm.available():
        try:
            data = _parse_json(llm.complete(_DISTILL_PROMPT.format(history=history), max_tokens=900)) or {}
        except Exception as e:
            logger.warning("timeline: LLM distill failed, using heuristic: %s", e)

    title = (data.get("title") or "").strip() or (channel.title if channel else "Decision")
    summary = (data.get("summary") or "").strip() or None
    detail = (data.get("detail") or "").strip() or None
    parts = data.get("participants")
    if not isinstance(parts, list) or not parts:
        parts = speakers

    if not summary and not detail and last_agent:
        # Heuristic: the last substantive agent message is the conclusion.
        summary = last_agent.split("\n", 1)[0].lstrip("#* ").strip()[:220]
        detail = last_agent[:1500]

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
