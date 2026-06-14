# -*- coding: utf-8 -*-
"""
Conformant Agent2Agent (A2A) protocol surface.

This exposes the workspace's agents over the **standard A2A protocol** so any
A2A client (the official a2a-sdk, Google ADK, CrewAI[a2a], …) can discover and
delegate to them — JSON-RPC 2.0 over HTTP + an Agent Card at the well-known URI.
It's the interoperable layer on top of the internal delegation gateway
(routers/a2a.py): an inbound A2A `message/send` becomes an internal delegation
TaskRecord, and `tasks/get`/`tasks/cancel`/`tasks/list` read it back as A2A Tasks.

Per-agent endpoint:    POST /a2a/{network}/{agent}
Per-agent Agent Card:  GET  /a2a/{network}/{agent}/.well-known/agent-card.json

Conformance covered (slice 1): Agent Card discovery, JSON-RPC 2.0 envelope +
error model, message/send, tasks/get, tasks/cancel, tasks/list, the A2A Task /
Message / Part / Artifact object shapes, and the A2A TaskState lifecycle.
Deferred: streaming (message/stream, tasks/resubscribe), push notifications,
signed Agent Cards, richer security schemes.
"""

import logging
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TaskRecord, WorkspaceMember
from app.routers.network import (
    _emit_event_blocking,
    _resolve_workspace,
    _verify_workspace_access,
)
from app.routers.a2a import (
    LEASE_SECONDS,
    TERMINAL_STATES,
    _WIRE_STATE,
    _agent_address,
    _agent_name,
    _apply_transition,
    _is_member,
    _message,
    _now,
)
from openagents.core.onm_events import Event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/a2a", tags=["A2A-Protocol"])

A2A_PROTOCOL_VERSION = "1.0"

# JSON-RPC + A2A error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
TASK_NOT_FOUND = -32001
TASK_NOT_CANCELABLE = -32002


# ---------------------------------------------------------------------------
# A2A object serialization (spec v1.0 shapes)
# ---------------------------------------------------------------------------

def _wire(state: str) -> str:
    return _WIRE_STATE.get(state, state)


def _a2a_message(m: dict) -> dict:
    """Internal {role, parts:[{text}]} → conformant A2A Message."""
    parts = [{"kind": "text", "text": p.get("text", "")} for p in (m.get("parts") or []) if "text" in p]
    return {"kind": "message", "role": m.get("role", "agent"), "parts": parts}


def _a2a_artifact(a: dict) -> dict:
    parts = [{"kind": "text", "text": p.get("text", "")} for p in (a.get("parts") or []) if "text" in p]
    return {"artifactId": a.get("id", ""), "name": a.get("name"), "parts": parts}


def _a2a_task(t: TaskRecord, history_length: Optional[int] = None) -> dict:
    history = [_a2a_message(m) for m in (t.history or [])]
    if history_length is not None:
        history = history[-history_length:] if history_length > 0 else []
    return {
        "kind": "task",
        "id": t.id,
        "contextId": t.context_id or t.id,
        "status": {"state": _wire(t.state), "timestamp": (t.updated_at or _now()).isoformat()},
        "history": history,
        "artifacts": [_a2a_artifact(a) for a in (t.artifacts or [])],
        "metadata": {"delegator": t.delegator, "contractor": t.contractor, "skillId": t.skill_id},
    }


def _agent_card(member: WorkspaceMember, base_url: str, network: str) -> dict:
    name = member.agent_name
    skills = []
    for s in (member.task_skills or []):
        skills.append({
            "id": s.get("id", ""),
            "name": s.get("name", s.get("id", "")),
            "description": s.get("description", ""),
            "tags": s.get("tags", []),
            "inputModes": s.get("inputModes", ["text/plain"]),
            "outputModes": s.get("outputModes", ["text/plain"]),
        })
    return {
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "name": name,
        "description": member.description or f"OpenAgents workspace agent '{name}'.",
        "url": f"{base_url}/a2a/{network}/{name}",
        "preferredTransport": "JSONRPC",
        "version": "1.0.0",
        "provider": {"organization": "OpenAgents", "url": base_url},
        "capabilities": {"streaming": False, "pushNotifications": False, "stateTransitionHistory": True},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": skills,
        "securitySchemes": {
            "workspaceToken": {"type": "apiKey", "in": "header", "name": "X-Workspace-Token"}
        },
        "security": [{"workspaceToken": []}],
    }


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, message: str, data: Any = None, http: int = 200) -> JSONResponse:
    body = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    if data is not None:
        body["error"]["data"] = data
    return JSONResponse(body, status_code=http)


def _text_of(message: dict) -> str:
    return " ".join(
        p.get("text", "") for p in (message.get("parts") or []) if (p.get("kind") == "text" or "text" in p)
    ).strip()


# ---------------------------------------------------------------------------
# Agent Card discovery (well-known)
# ---------------------------------------------------------------------------

@router.get("/{network}/{agent_name}/.well-known/agent-card.json")
def agent_card(
    network: str,
    agent_name: str,
    request: Request,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return JSONResponse({"error": "Network not found"}, status_code=404)
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.agent_name == agent_name,
        )
    ).scalar_one_or_none()
    if not member:
        return JSONResponse({"error": "Agent not found"}, status_code=404)
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(_agent_card(member, base_url, network))


# ---------------------------------------------------------------------------
# JSON-RPC endpoint
# ---------------------------------------------------------------------------

@router.post("/{network}/{agent_name}")
async def jsonrpc(
    network: str,
    agent_name: str,
    request: Request,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_a2a_caller: Optional[str] = Header(None),
):
    try:
        body = await request.json()
    except Exception:
        return _err(None, PARSE_ERROR, "Parse error")
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or "method" not in body:
        return _err(body.get("id") if isinstance(body, dict) else None, INVALID_REQUEST, "Invalid Request")

    req_id = body.get("id")
    method = body["method"]
    params = body.get("params") or {}

    workspace = _resolve_workspace(db, network)
    if not workspace:
        return _err(req_id, INVALID_PARAMS, "Network not found", http=404)
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return _err(req_id, INVALID_REQUEST, "Unauthorized", http=401)
    contractor_addr = _agent_address(agent_name)
    if not _is_member(db, str(workspace.id), agent_name):
        return _err(req_id, INVALID_PARAMS, f"Unknown agent '{agent_name}'", http=404)

    def _load(task_id: str) -> Optional[TaskRecord]:
        return db.execute(
            select(TaskRecord).where(
                TaskRecord.id == task_id, TaskRecord.workspace_id == str(workspace.id),
                TaskRecord.contractor == contractor_addr,
            )
        ).scalar_one_or_none()

    # ── message/send: inbound A2A task → internal delegation ──
    if method == "message/send":
        msg = params.get("message") or {}
        text = _text_of(msg)
        if not text:
            return _err(req_id, INVALID_PARAMS, "message.parts must contain text")
        delegator = x_a2a_caller or "a2a:client"
        context_id = msg.get("contextId") or (params.get("configuration") or {}).get("contextId")
        task = TaskRecord(
            workspace_id=str(workspace.id),
            context_id=context_id,
            delegator=delegator,
            contractor=contractor_addr,
            skill_id=(params.get("metadata") or {}).get("skillId"),
            state="submitted",
            input=_message("user", text),
            artifacts=[],
            history=[_message("user", text)],
            task_metadata={"a2a": True},
            channel_name=context_id,
            deadline_at=_now() + timedelta(seconds=LEASE_SECONDS),
        )
        db.add(task)
        db.flush()
        if context_id:
            try:
                _emit_event_blocking(Event(
                    type="workspace.message.posted", source=delegator,
                    target=f"channel/{context_id}",
                    payload={"content": f"@{agent_name} {text}", "message_type": "delegate"},
                    metadata={"taskId": task.id},
                ), workspace, db, token=x_workspace_token)
            except Exception:
                logger.exception("a2a-protocol: kick-off failed for %s", task.id)
        db.commit()
        db.refresh(task)
        return _ok(req_id, _a2a_task(task))

    # ── tasks/get ──
    if method == "tasks/get":
        task = _load(params.get("id", ""))
        if not task:
            return _err(req_id, TASK_NOT_FOUND, "Task not found")
        return _ok(req_id, _a2a_task(task, params.get("historyLength")))

    # ── tasks/cancel ──
    if method == "tasks/cancel":
        task = _load(params.get("id", ""))
        if not task:
            return _err(req_id, TASK_NOT_FOUND, "Task not found")
        if task.state in TERMINAL_STATES:
            return _err(req_id, TASK_NOT_CANCELABLE, f"Task is already {task.state}")
        _apply_transition(task, "canceled", _message("agent", "Canceled by A2A client."))
        db.commit()
        db.refresh(task)
        return _ok(req_id, _a2a_task(task))

    # ── tasks/list ──
    if method == "tasks/list":
        q = select(TaskRecord).where(
            TaskRecord.workspace_id == str(workspace.id),
            TaskRecord.contractor == contractor_addr,
        )
        if params.get("contextId"):
            q = q.where(TaskRecord.context_id == params["contextId"])
        if params.get("state"):
            q = q.where(TaskRecord.state == params["state"])
        q = q.order_by(TaskRecord.created_at.desc())
        rows = db.execute(q).scalars().all()
        return _ok(req_id, {"tasks": [_a2a_task(t) for t in rows], "nextPageToken": ""})

    return _err(req_id, METHOD_NOT_FOUND, f"Method not found: {method}")
