# -*- coding: utf-8 -*-
"""
A2A — agent-to-agent structured delegation (Agent2Agent protocol semantics).

A gateway that layers the A2A Task model on top of the ONM event bus so the
workspace's own agents can delegate point-to-point with a real task lifecycle
and capability discovery — without each agent hosting its own HTTP server.

Endpoints (REST mirror of the A2A methods; JSON-RPC envelope + /.well-known +
SSE streaming are deferred to a later phase for external interop):

  GET  /v1/a2a/agents               Capability discovery — Agent Card list
  GET  /v1/a2a/agents/{name}/card   A single Agent Card
  POST /v1/a2a/tasks                message/send — delegate a task (→ submitted)
  GET  /v1/a2a/tasks                tasks/list
  GET  /v1/a2a/tasks/{id}           tasks/get
  POST /v1/a2a/tasks/{id}/status    advance the task lifecycle (contractor side)
  POST /v1/a2a/tasks/{id}/cancel    tasks/cancel

Task lifecycle (A2A TaskState):
  submitted → working → input_required → completed | failed | canceled | rejected
The first four terminal states cannot transition further.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.database import get_db
from app.models import TaskRecord, TodoRecord, WorkspaceMember
from app.response import ResponseCode, json_response, success_response
from app.routers.network import (
    _emit_event_blocking,
    _resolve_workspace,
    _verify_workspace_access,
)
from openagents.core.onm_events import Event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/a2a", tags=["A2A"])


# ---------------------------------------------------------------------------
# Task-state machine (A2A TaskState)
# ---------------------------------------------------------------------------

TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}
ALLOWED_TRANSITIONS = {
    "submitted": {"working", "input_required", "completed", "failed", "canceled", "rejected"},
    "working": {"input_required", "completed", "failed", "canceled", "rejected"},
    "input_required": {"working", "completed", "failed", "canceled", "rejected"},
}
# snake_case stored internally ↔ hyphenated A2A wire form
_WIRE_STATE = {"input_required": "input-required"}

# Lease length: a non-terminal task whose deadline passes with no further
# activity is reaped (working → failed[timeout], input_required → canceled).
LEASE_SECONDS = int(os.environ.get("A2A_TASK_LEASE_SECONDS", "3600"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _agent_name(addr: str) -> str:
    """Bare agent name from an 'openagents:<name>' address."""
    if addr.startswith("openagents:"):
        return addr[len("openagents:"):]
    if addr.startswith("human:"):
        return addr[len("human:"):]
    return addr


def _agent_address(name_or_addr: str) -> str:
    """Normalize a bare name to an 'openagents:<name>' address."""
    if ":" in name_or_addr:
        return name_or_addr
    return f"openagents:{name_or_addr}"


# ---------------------------------------------------------------------------
# Serialization (A2A objects)
# ---------------------------------------------------------------------------

def _agent_card(m: WorkspaceMember) -> dict:
    return {
        "id": f"openagents:{m.agent_name}",
        "name": m.agent_name,
        "description": m.description or "",
        "provider": {"organization": "OpenAgents"},
        "url": f"/v1/a2a/agents/{m.agent_name}",
        "skills": m.task_skills or [],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
    }


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _serialize_task(t: TaskRecord) -> dict:
    """Render a TaskRecord as an A2A Task object (plus flat fields the UI uses)."""
    wire_state = _WIRE_STATE.get(t.state, t.state)
    return {
        "id": t.id,
        "contextId": t.context_id,
        "status": {
            "state": wire_state,
            "timestamp": _iso(t.updated_at),
        },
        "history": t.history or [],
        "artifacts": t.artifacts or [],
        "metadata": {
            **(t.task_metadata or {}),
            "delegator": t.delegator,
            "contractor": t.contractor,
            "skillId": t.skill_id,
        },
        # Flat convenience fields for the workspace UI / board.
        # `state` is the A2A wire form (hyphenated, e.g. "input-required") to
        # match status.state and the frontend's A2ATaskState union.
        "delegator": t.delegator,
        "contractor": t.contractor,
        "contractorName": _agent_name(t.contractor),
        "skillId": t.skill_id,
        "state": wire_state,
        "channel": t.channel_name,
        "createdAt": _iso(t.created_at),
        "updatedAt": _iso(t.updated_at),
        "completedAt": _iso(t.completed_at),
    }


def _message(role: str, text: str) -> dict:
    """Build a minimal A2A Message with a single TextPart."""
    return {"role": role, "parts": [{"text": text}], "timestamp": _iso(_now())}


# ---------------------------------------------------------------------------
# Bridge: contractor activity → task progression (called from todos router)
# ---------------------------------------------------------------------------

def advance_tasks_on_contractor_activity(
    db: Session, workspace_id: str, contractor_addr: str, channel: Optional[str]
) -> None:
    """Drive a delegation's lifecycle from the contractor's real todo activity in
    the task's channel — so today's agents advance tasks natively without a
    launcher change:

      - any `submitted` task there → `working` (the agent started);
      - a `working` task there → `completed` once the contractor's todos in that
        channel are all done (≥1), capturing them as the result Artifact.

    Phase 3's native status reporting (POST /tasks/{id}/status) supersedes this
    heuristic for precise, per-task control. Best-effort; never raises into the
    caller's request flow.
    """
    try:
        q = select(TaskRecord).where(
            TaskRecord.workspace_id == workspace_id,
            TaskRecord.contractor == contractor_addr,
            TaskRecord.state.in_(["submitted", "working"]),
        )
        if channel:
            q = q.where(TaskRecord.channel_name == channel)
        tasks = db.execute(q).scalars().all()
        if not tasks:
            return

        # Start any submitted delegations the contractor is now working on.
        for t in tasks:
            if t.state == "submitted":
                _apply_transition(t, "working", _message("agent", "Started working."))

        # Auto-complete only when the mapping is unambiguous: exactly one
        # delegation shares this channel. With multiple, a single shared todo
        # list can't be attributed to one task, so completion stays explicit
        # (POST /tasks/{id}/status) to avoid completing the wrong one.
        if len(tasks) == 1 and tasks[0].state == "working":
            todos = db.execute(
                select(TodoRecord).where(
                    TodoRecord.workspace_id == workspace_id,
                    TodoRecord.created_by == contractor_addr,
                    TodoRecord.channel_name == (channel or "default"),
                )
            ).scalars().all()
            if todos and all(td.status == "completed" for td in todos):
                t = tasks[0]
                _apply_transition(t, "completed", _message("agent", "All to-dos completed."))
                summary = "; ".join(td.content for td in todos)
                t.artifacts = list(t.artifacts or []) + [
                    {"id": t.id, "name": "result", "parts": [{"text": summary}]}
                ]
        db.flush()
    except Exception:  # pragma: no cover - bridge must never break todos
        logger.exception("a2a: failed to advance tasks on contractor activity")


def _apply_transition(t: TaskRecord, new_state: str, status_msg: Optional[dict]) -> None:
    t.state = new_state
    t.updated_at = _now()
    if status_msg:
        t.history = list(t.history or []) + [status_msg]
    if new_state in TERMINAL_STATES:
        t.completed_at = _now()
        t.deadline_at = None              # terminal — reaper must never touch it
    else:
        t.deadline_at = _now() + timedelta(seconds=LEASE_SECONDS)  # extend the lease


def _is_member(db: Session, workspace_id: str, agent_name: str) -> bool:
    return db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.agent_name == agent_name,
        )
    ).scalar_one_or_none() is not None


def reap_stale_tasks(db: Session) -> int:
    """Self-heal: time out non-terminal tasks whose lease has expired.

    working/submitted → failed(timeout); input_required → canceled(no response).
    Concurrency-safe via the optimistic version lock: a task a worker just
    advanced raises StaleDataError on commit and is skipped (the worker wins).
    Called from the backend maintenance loop (app/main.py).
    """
    now = _now()
    rows = db.execute(
        select(TaskRecord).where(
            TaskRecord.state.in_(["submitted", "working", "input_required"]),
            TaskRecord.deadline_at.is_not(None),
            TaskRecord.deadline_at < now,
        )
    ).scalars().all()
    reaped = 0
    for t in rows:
        if t.state == "input_required":
            _apply_transition(t, "canceled", _message("agent", "No response — lease expired."))
        else:
            _apply_transition(t, "failed", _message("agent", "Timed out — lease expired."))
        try:
            db.commit()
            reaped += 1
        except StaleDataError:
            db.rollback()   # a worker advanced it first — let them win
    return reaped


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateTaskRequest(BaseModel):
    network: str
    source: str                       # delegator, e.g. "openagents:pm" or "human:you@x"
    contractor: str                   # agent name or "openagents:<name>"
    text: str                         # the task instruction (becomes the input Message)
    skill_id: Optional[str] = None
    context_id: Optional[str] = None  # channel name to delegate within (enables the kick-off)


class TaskStatusRequest(BaseModel):
    network: str
    state: str                        # working | input_required | completed | failed | rejected
    text: Optional[str] = None        # optional status message
    artifact_text: Optional[str] = None  # optional result captured as an Artifact


class CancelTaskRequest(BaseModel):
    network: str


# ---------------------------------------------------------------------------
# Capability discovery — Agent Cards
# ---------------------------------------------------------------------------

@router.get("/agents")
def list_agent_cards(
    network: str = Query(...),
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    members = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id)
    ).scalars().all()
    return success_response({"agents": [_agent_card(m) for m in members]})


@router.get("/agents/{name}/card")
def get_agent_card(
    name: str,
    network: str = Query(...),
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.agent_name == name,
        )
    ).scalar_one_or_none()
    if not member:
        return json_response(ResponseCode.NOT_FOUND, "Agent not found")
    return success_response(_agent_card(member))


class SetSkillsRequest(BaseModel):
    network: str
    skills: List[dict]   # A2A AgentSkill[] — {id, name, description?, tags?, ...}


@router.put("/agents/{name}/skills")
def set_agent_skills(
    name: str,
    body: SetSkillsRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Declare the A2A skills an agent advertises (Agent Card capability discovery)."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.agent_name == name,
        )
    ).scalar_one_or_none()
    if not member:
        return json_response(ResponseCode.NOT_FOUND, "Agent not found")

    member.task_skills = body.skills
    db.commit()
    db.refresh(member)
    return success_response(_agent_card(member))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.post("/tasks")
def create_task(
    body: CreateTaskRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """message/send — delegate a task from `source` to `contractor` (→ submitted).

    Also posts an @-mention kick-off message into `context_id` (if given) so the
    contractor's existing runtime starts working; that activity advances the
    task to `working` via the todos bridge.

    Auth model: like /v1/todos and /v1/events, the workspace token grants full
    workspace authority and `source` (the delegator identity) is caller-asserted,
    not cryptographically bound to the principal. Delegation provenance is
    therefore advisory within a trusted workspace.
    """
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    contractor_addr = _agent_address(body.contractor)
    contractor_name = _agent_name(contractor_addr)

    # Contractor must be a real member of this workspace — reject ghosts/typos
    # (a delegation to a non-member could never be picked up).
    if not _is_member(db, str(workspace.id), contractor_name):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown contractor '{contractor_name}'")

    task = TaskRecord(
        workspace_id=str(workspace.id),
        context_id=body.context_id,
        delegator=body.source,
        contractor=contractor_addr,
        skill_id=body.skill_id,
        state="submitted",
        input=_message("user", body.text),
        artifacts=[],
        history=[_message("user", body.text)],
        task_metadata={},
        channel_name=body.context_id,
        deadline_at=_now() + timedelta(seconds=LEASE_SECONDS),
    )
    db.add(task)
    db.flush()

    # Kick-off: post an @-mention so the contractor's runtime acts on it.
    # Best-effort — a routing hiccup must not fail the delegation itself.
    if body.context_id:
        try:
            event = Event(
                type="workspace.message.posted",
                source=body.source,
                target=f"channel/{body.context_id}",
                payload={
                    "content": (
                        f"@{contractor_name} {body.text}\n\n"
                        f"[A2A delegation · task {task.id}] You are the contractor. Drive this task's "
                        f"lifecycle with the a2a-delegation skill — mark it `working`, then report the "
                        f"result via POST /v1/a2a/tasks/{task.id}/status (state=completed, "
                        f"artifact_text=<result>) or state=failed. Don't just reply in chat."
                    ),
                    "message_type": "delegate",
                },
                metadata={"taskId": task.id},
            )
            _emit_event_blocking(event, workspace, db, token=x_workspace_token)
        except Exception:
            logger.exception("a2a: kick-off message failed for task %s", task.id)

    # Deliver a directed task.delegated event so a task-aware contractor can
    # discover the assignment from its own event stream (Phase 2/3 native flow).
    # Unhandled event type → passes through the pipeline and is persisted.
    try:
        delegated = Event(
            type="workspace.task.delegated",
            source=body.source,
            target=contractor_addr,
            payload={"task": _serialize_task(task)},
            metadata={"taskId": task.id},
            visibility="direct",
        )
        _emit_event_blocking(delegated, workspace, db, token=x_workspace_token)
    except Exception:
        logger.exception("a2a: task.delegated event failed for task %s", task.id)

    db.commit()
    db.refresh(task)
    return success_response(_serialize_task(task))


@router.get("/tasks")
def list_tasks(
    network: str = Query(...),
    context_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    delegator: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    q = select(TaskRecord).where(TaskRecord.workspace_id == str(workspace.id))
    if context_id:
        q = q.where(TaskRecord.context_id == context_id)
    if state:
        q = q.where(TaskRecord.state == state)
    if contractor:
        q = q.where(TaskRecord.contractor == _agent_address(contractor))
    if delegator:
        q = q.where(TaskRecord.delegator == delegator)
    q = q.order_by(TaskRecord.created_at.desc())
    rows = db.execute(q).scalars().all()
    return success_response({"tasks": [_serialize_task(t) for t in rows]})


def _load_task(db: Session, workspace_id: str, task_id: str) -> Optional[TaskRecord]:
    return db.execute(
        select(TaskRecord).where(
            TaskRecord.id == task_id,
            TaskRecord.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    network: str = Query(...),
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")
    return success_response(_serialize_task(task))


@router.post("/tasks/{task_id}/status")
def update_task_status(
    task_id: str,
    body: TaskStatusRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Advance the task lifecycle. The contractor (Phase 2: via a delegation
    skill) or the UI calls this to move working/completed/failed/etc."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")

    new_state = body.state
    if new_state not in (TERMINAL_STATES | {"working", "input_required"}):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown state '{new_state}'")
    if task.state in TERMINAL_STATES:
        return json_response(ResponseCode.BAD_REQUEST, f"Task is already {task.state}")
    if new_state not in ALLOWED_TRANSITIONS.get(task.state, set()):
        return json_response(
            ResponseCode.BAD_REQUEST,
            f"Illegal transition {task.state} → {new_state}",
        )

    status_msg = _message("agent", body.text) if body.text else None
    _apply_transition(task, new_state, status_msg)
    if body.artifact_text:
        task.artifacts = list(task.artifacts or []) + [
            {"id": task.id, "name": "result", "parts": [{"text": body.artifact_text}]}
        ]
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        return json_response(ResponseCode.CONFLICT, "Task was modified concurrently; retry")
    db.refresh(task)
    return success_response(_serialize_task(task))


@router.post("/tasks/{task_id}/cancel")
def cancel_task(
    task_id: str,
    body: CancelTaskRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")
    if task.state in TERMINAL_STATES:
        return json_response(ResponseCode.BAD_REQUEST, f"Task is already {task.state}")

    _apply_transition(task, "canceled", _message("user", "Canceled by delegator."))
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        return json_response(ResponseCode.CONFLICT, "Task was modified concurrently; retry")
    db.refresh(task)
    return success_response(_serialize_task(task))
