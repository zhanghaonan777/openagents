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
import time
import uuid as _uuidlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.database import get_db
from app.models import Channel, ChannelMember, EventRecord, TaskRecord, TodoRecord, WorkspaceMember
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

# Marker that prefixes the internal contractor instruction embedded in a
# delegation kick-off message. The frontend splits display content on this same
# marker to hide the plumbing from humans, so it is a cross-stack contract —
# keep it in sync with the frontend `A2A_DELEGATION_MARKER` (lib/a2a.ts).
DELEGATION_MARKER = "[A2A delegation"


def build_delegation_kickoff(contractor_name: str, text: str, task_id: str) -> str:
    """The channel message that wakes a contractor and tells it to drive the task.

    One definition shared by the internal gateway (routers/a2a.py) and the
    conformant protocol surface (routers/a2a_protocol.py) so the wording and the
    embedded status endpoint can never drift between them.
    """
    return (
        f"@{contractor_name} {text}\n\n"
        f"{DELEGATION_MARKER} · task {task_id}] You are the contractor. Drive this task's "
        f"lifecycle with the a2a-delegation skill — mark it `working`, then report the result "
        f"via POST /v1/a2a/tasks/{task_id}/status (state=completed, artifact_text=<result>) "
        f"or state=failed. Don't just reply in chat."
    )


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
        # Review overlay (decoupled from the A2A protocol state): {state,
        # reviewer, comment, ...} or None. Lets the board show a Review/Approved
        # lane without mutating the task's protocol lifecycle.
        "review": (t.task_metadata or {}).get("review"),
        # Discussion thread on the task (author/text/createdAt), oldest first.
        "comments": (t.task_metadata or {}).get("comments") or [],
        # Dependency edges (task ids). blockedBy = tasks that must finish first;
        # blocks = tasks waiting on this one. Maintained as a pair by /link.
        "blockedBy": ((t.task_metadata or {}).get("dependencies") or {}).get("blockedBy") or [],
        "blocks": ((t.task_metadata or {}).get("dependencies") or {}).get("blocks") or [],
        # Clarification overlay: {state: 'needs_user', question, askedAt} when the
        # task is waiting on a human, else None.
        "clarification": (t.task_metadata or {}).get("clarification"),
        # Subtask fan-out: parentId links a child delegation to its parent; the UI
        # rolls up child progress on the parent card. Children are plain tasks.
        "parentId": (t.task_metadata or {}).get("parentId"),
        # Structured, typed activity timeline (status_changed/review_*/commented/
        # reassigned/…), oldest first — distinct from the raw A2A message history.
        "events": (t.task_metadata or {}).get("events") or [],
        # Soft delete (recycle bin): hidden from the board but restorable.
        "deleted": bool((t.task_metadata or {}).get("deleted")),
        "deletedAt": ((t.task_metadata or {}).get("deleted") or {}).get("at"),
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

        # Apply the transitions inside a SAVEPOINT. If a concurrent reaper or
        # status update bumped a task's version, the optimistic-lock conflict
        # rolls back ONLY these task changes (best-effort) instead of surfacing
        # at the caller's commit (todos.py) and failing the whole todo write.
        try:
            with db.begin_nested():
                # Start any submitted delegations the contractor is now working on.
                for t in tasks:
                    if t.state == "submitted":
                        _apply_transition(t, "working", _message("agent", "Started working."),
                                          actor=_agent_name(t.contractor))

                # Auto-complete only when the mapping is unambiguous: exactly one
                # delegation shares this *named* channel. With multiple — or with a
                # channel-less delegation — completion stays explicit (POST
                # /tasks/{id}/status) to avoid completing the wrong one.
                if channel and len(tasks) == 1 and tasks[0].state == "working":
                    todos = db.execute(
                        select(TodoRecord).where(
                            TodoRecord.workspace_id == workspace_id,
                            TodoRecord.created_by == contractor_addr,
                            TodoRecord.channel_name == channel,
                        )
                    ).scalars().all()
                    if todos and all(td.status == "completed" for td in todos):
                        t = tasks[0]
                        _apply_transition(t, "completed", _message("agent", "All to-dos completed."),
                                          actor=_agent_name(t.contractor))
                        summary = "; ".join(td.content for td in todos)
                        t.artifacts = list(t.artifacts or []) + [
                            {"id": t.id, "name": "result", "parts": [{"text": summary}]}
                        ]
                db.flush()
        except StaleDataError:
            # A worker/reaper advanced the task first — drop our changes, keep todos.
            logger.info("a2a: bridge task-advance skipped — task changed concurrently")
    except Exception:  # pragma: no cover - bridge must never break todos
        logger.exception("a2a: failed to advance tasks on contractor activity")


def _append_event(t: TaskRecord, etype: str, actor: Optional[str] = None,
                  detail: Optional[str] = None, **extra) -> None:
    """Append a typed event to the task's structured timeline (task_metadata.events).

    A decoupled overlay — like the review/comment/dependency overlays it lives in
    task_metadata and never touches the A2A history/state machine. Reassigns the
    whole dict so SQLAlchemy's change-tracking (and the version bump) fires.
    """
    meta = dict(t.task_metadata or {})
    events = list(meta.get("events") or [])
    ev: dict = {"type": etype, "at": _iso(_now())}
    if actor:
        ev["actor"] = actor
    if detail:
        ev["detail"] = detail
    ev.update(extra)
    events.append(ev)
    meta["events"] = events
    t.task_metadata = meta


def _apply_transition(t: TaskRecord, new_state: str, status_msg: Optional[dict],
                      actor: str = "system") -> None:
    t.state = new_state
    t.updated_at = _now()
    if status_msg:
        t.history = list(t.history or []) + [status_msg]
    _append_event(t, "status_changed", actor=actor, detail=new_state)
    if new_state in TERMINAL_STATES:
        t.completed_at = _now()
        t.deadline_at = None              # terminal — reaper must never touch it
    else:
        t.deadline_at = _now() + timedelta(seconds=LEASE_SECONDS)  # extend the lease


REVIEW_STATES = {"pending", "approved", "changes_requested"}


def _set_review(t: TaskRecord, **fields) -> dict:
    """Merge ``fields`` into the task's review overlay (in task_metadata).

    The overlay is a *workflow* layer kept separate from the A2A protocol state
    (mirroring agent-teams-ai's kanban/task decoupling): reviewing a deliverable
    never mutates the task's submitted/working/completed lifecycle, so the two
    can't clobber each other. Reassigns the whole JSON dict so SQLAlchemy's
    change-tracking (and the version bump that guards concurrent writes) fires.
    """
    meta = dict(t.task_metadata or {})
    review = dict(meta.get("review") or {})
    review.update(fields)
    meta["review"] = review
    t.task_metadata = meta
    t.updated_at = _now()
    return review


def _edit_dep(t: TaskRecord, key: str, other_id: str, add: bool) -> None:
    """Add/remove a dependency edge (key='blockedBy'|'blocks') on a task,
    reassigning the JSON dict so SQLAlchemy tracks the change + bumps version."""
    meta = dict(t.task_metadata or {})
    deps = dict(meta.get("dependencies") or {})
    lst = list(deps.get(key) or [])
    if add:
        if other_id not in lst:
            lst.append(other_id)
    else:
        lst = [x for x in lst if x != other_id]
    deps[key] = lst
    meta["dependencies"] = deps
    t.task_metadata = meta
    t.updated_at = _now()


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

MAX_WAIT_SECONDS = 180


class CreateTaskRequest(BaseModel):
    network: str
    source: str                       # delegator, e.g. "openagents:pm" or "human:you@x"
    contractor: str                   # agent name or "openagents:<name>"
    text: str                         # the task instruction (becomes the input Message)
    skill_id: Optional[str] = None
    context_id: Optional[str] = None  # channel name to delegate within (enables the kick-off)
    wait: int = 0                     # >0: block (long-poll) up to N s until the task is terminal,
                                      # returning the final task + artifact ("agent-as-tool" / A2A blocking)


class TaskStatusRequest(BaseModel):
    network: str
    state: str                        # working | input_required | completed | failed | rejected
    text: Optional[str] = None        # optional status message
    artifact_text: Optional[str] = None  # optional result captured as an Artifact


class CancelTaskRequest(BaseModel):
    network: str


class ReviewRequestRequest(BaseModel):
    network: str
    reviewer: Optional[str] = None    # agent to review; defaults to the delegator (if an agent)
    actor: Optional[str] = None       # who asked for review (advisory, for history)


class ReviewDecisionRequest(BaseModel):
    network: str
    reviewer: Optional[str] = None    # who decided (advisory, for attribution)
    comment: Optional[str] = None     # review feedback


class CommentRequest(BaseModel):
    network: str
    author: str                       # "openagents:agent" | "human:email" | bare name
    text: str
    reply_to: Optional[str] = None    # id of the comment this one replies to


class DependencyRequest(BaseModel):
    network: str
    blocked_by: str                   # task id this task should wait on
    action: str = "add"               # "add" | "remove"


class ReassignRequest(BaseModel):
    network: str
    contractor: str                   # the new contractor (agent name or address)
    actor: Optional[str] = None       # who reassigned (advisory)


class NudgeRequest(BaseModel):
    network: str
    text: Optional[str] = None        # optional custom nudge text


class ClarificationRequest(BaseModel):
    network: str
    action: str                       # "set" | "resolve"
    question: Optional[str] = None    # what input is needed (on set)
    answer: Optional[str] = None      # the human's answer (on resolve)
    actor: Optional[str] = None


class SubtaskRequest(BaseModel):
    network: str
    source: str                       # delegator of the subtask (lead/agent/human)
    contractor: str                   # agent the subtask is fanned out to
    text: str                         # the subtask instruction
    skill_id: Optional[str] = None


class ActorRequest(BaseModel):
    network: str
    actor: Optional[str] = None       # who performed the action (advisory, for the timeline)


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

def _build_and_kickoff_task(
    db: Session,
    workspace,
    *,
    source: str,
    contractor_addr: str,
    text: str,
    skill_id: Optional[str],
    context_id: Optional[str],
    parent_id: Optional[str] = None,
    token: Optional[str] = None,
) -> TaskRecord:
    """Create a `submitted` delegation, post the @-mention kick-off, and emit the
    directed task.delegated event — the shared core of create_task and the
    subtask fan-out. The caller must already have validated that the contractor
    is a member of `workspace`.
    """
    contractor_name = _agent_name(contractor_addr)
    meta: dict = {}
    if parent_id:
        meta["parentId"] = parent_id

    task = TaskRecord(
        workspace_id=str(workspace.id),
        context_id=context_id,
        delegator=source,
        contractor=contractor_addr,
        skill_id=skill_id,
        state="submitted",
        input=_message("user", text),
        artifacts=[],
        history=[_message("user", text)],
        task_metadata=meta,
        channel_name=context_id,
        deadline_at=_now() + timedelta(seconds=LEASE_SECONDS),
    )
    _append_event(task, "task_created", actor=_agent_name(source), detail=contractor_name)
    db.add(task)
    db.flush()

    # Kick-off: post an @-mention so the contractor's runtime acts on it.
    # Best-effort — a routing hiccup must not fail the delegation itself.
    if context_id:
        try:
            event = Event(
                type="workspace.message.posted",
                source=source,
                target=f"channel/{context_id}",
                payload={
                    "content": build_delegation_kickoff(contractor_name, text, task.id),
                    "message_type": "delegate",
                },
                metadata={"taskId": task.id},
            )
            _emit_event_blocking(event, workspace, db, token=token)
        except Exception:
            logger.exception("a2a: kick-off message failed for task %s", task.id)

    # Deliver a directed task.delegated event so a task-aware contractor can
    # discover the assignment from its own event stream (Phase 2/3 native flow).
    # Unhandled event type → passes through the pipeline and is persisted.
    try:
        delegated = Event(
            type="workspace.task.delegated",
            source=source,
            target=contractor_addr,
            payload={"task": _serialize_task(task)},
            metadata={"taskId": task.id},
            visibility="direct",
        )
        _emit_event_blocking(delegated, workspace, db, token=token)
    except Exception:
        logger.exception("a2a: task.delegated event failed for task %s", task.id)

    db.commit()
    db.refresh(task)
    return task


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

    # Agent→agent task with no channel (e.g. a `consult`/`delegate` MCP tool call):
    # route the kick-off through the pair's private DM channel so the contractor is
    # actually triggered. Explicit context_id and human delegators are unchanged.
    context_id = body.context_id
    if not context_id and body.source.startswith("openagents:"):
        context_id = _ensure_dm_channel(db, workspace, _agent_name(body.source), contractor_name)

    task = _build_and_kickoff_task(
        db, workspace,
        source=body.source,
        contractor_addr=contractor_addr,
        text=body.text,
        skill_id=body.skill_id,
        context_id=context_id,
        token=x_workspace_token,
    )

    # Blocking ("delegate and wait"): long-poll until the contractor drives the
    # task to a terminal state, then return it with its result artifact — so the
    # delegator can synthesize the result into its own answer (agent-as-tool).
    if body.wait and body.wait > 0:
        task_id = task.id
        deadline = time.time() + min(body.wait, MAX_WAIT_SECONDS)
        while task.state not in TERMINAL_STATES and time.time() < deadline:
            # Release the pooled DB connection while we sleep, so a long blocking
            # delegation doesn't pin a connection (pool is 40+8) for the whole
            # wait. Re-read on a fresh connection each tick. (The threadpool slot
            # is still held — that's inherent to a sync blocking handler.)
            db.close()
            time.sleep(2)
            refreshed = db.get(TaskRecord, task_id)
            if refreshed is None:
                break
            task = refreshed

    return success_response(_serialize_task(task))


@router.get("/tasks")
def list_tasks(
    network: str = Query(...),
    context_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    delegator: Optional[str] = Query(None),
    deleted: bool = Query(False),     # True → only the recycle bin; False → only live tasks
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
    # Soft-delete is a task_metadata overlay (not a column), so partition in
    # Python: the board asks for live tasks, the recycle bin for deleted ones.
    tasks = [_serialize_task(t) for t in rows]
    tasks = [t for t in tasks if bool(t["deleted"]) == deleted]
    return success_response({"tasks": tasks})


# Priority order for an agent's derived agenda (highest first). Mirrors
# agent-teams-ai's "opinionated queue": pick up assigned reviews before doing
# new work, and rework (changes requested) before fresh tasks.
_AGENDA_RANK = {"review_pickup": 0, "rework": 1, "working": 2, "assigned": 3}


def _derive_agenda(db: Session, workspace_id: str, agent_name: str) -> list[dict]:
    """The agent's actionable queue — only *what's mine now*, not the whole board.

    Returns a small, deterministically-ordered list so an agent (or the UI)
    knows what to do next without re-reasoning over every task. Two kinds:
      - `review`: a pending review assigned to this agent (review-pickup duty);
      - `work`: a task this agent contracts that still needs doing (with
        `rework` ranked above fresh `working`/`assigned` items).
    """
    rows = db.execute(
        select(TaskRecord).where(TaskRecord.workspace_id == workspace_id)
    ).scalars().all()
    # A task is "done enough" to unblock dependents once it's completed or its
    # review is approved; anything else still blocks.
    def _resolved(t: TaskRecord) -> bool:
        rv = (t.task_metadata or {}).get("review") or {}
        return t.state == "completed" or rv.get("state") == "approved"
    state_by_id = {t.id: _resolved(t) for t in rows}
    items: list[dict] = []
    for t in rows:
        review = (t.task_metadata or {}).get("review") or {}
        # Review-pickup duty: assigned reviewer, review still pending.
        if review.get("reviewer") == agent_name and review.get("state") == "pending":
            items.append({
                "taskId": t.id,
                "kind": "review",
                "priority": "review_pickup",
                "reason": "review_assigned",
                "state": _WIRE_STATE.get(t.state, t.state),
                "contractorName": _agent_name(t.contractor),
                "request": (t.input or {}).get("parts", [{}])[0].get("text") if t.input else None,
            })
            continue
        # Work duty: this agent is the contractor and the task isn't finished.
        if _agent_name(t.contractor) == agent_name and t.state not in TERMINAL_STATES:
            # Frontier scheduling: skip tasks still blocked by unfinished deps.
            blocked_by = ((t.task_metadata or {}).get("dependencies") or {}).get("blockedBy") or []
            if any(not state_by_id.get(bid, False) for bid in blocked_by):
                continue
            if review.get("state") == "changes_requested":
                priority = "rework"
            elif t.state == "working":
                priority = "working"
            else:
                priority = "assigned"
            items.append({
                "taskId": t.id,
                "kind": "work",
                "priority": priority,
                "reason": "changes_requested" if priority == "rework" else "owner_assigned",
                "state": _WIRE_STATE.get(t.state, t.state),
                "contractorName": _agent_name(t.contractor),
                "request": (t.input or {}).get("parts", [{}])[0].get("text") if t.input else None,
            })
    items.sort(key=lambda it: (_AGENDA_RANK.get(it["priority"], 9), it["taskId"]))
    return items


@router.get("/briefing")
def get_briefing(
    network: str = Query(...),
    agent: str = Query(...),
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """An agent's derived agenda — its actionable queue, review-pickup first."""
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    agent_name = _agent_name(agent)
    items = _derive_agenda(db, str(workspace.id), agent_name)
    counts = {
        "review": sum(1 for it in items if it["kind"] == "review"),
        "work": sum(1 for it in items if it["kind"] == "work"),
    }
    return success_response({"agent": agent_name, "items": items, "counts": counts})


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
    _apply_transition(task, new_state, status_msg, actor=_agent_name(task.contractor))
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

    _apply_transition(task, "canceled", _message("user", "Canceled by delegator."), actor="user")
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        return json_response(ResponseCode.CONFLICT, "Task was modified concurrently; retry")
    db.refresh(task)
    return success_response(_serialize_task(task))


# ---------------------------------------------------------------------------
# Review loop — peer review of a delegated deliverable (decoupled overlay)
# ---------------------------------------------------------------------------
# "Agents review each other": a reviewer is asked to check a contractor's work,
# then approves it or requests changes. This rides on a review overlay in
# task_metadata (see _set_review) and never mutates the A2A protocol state, so
# it's safe on tasks at any point in their lifecycle.

def _commit_review(db: Session, task: TaskRecord):
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        return json_response(ResponseCode.CONFLICT, "Task was modified concurrently; retry")
    db.refresh(task)
    return success_response(_serialize_task(task))


@router.post("/tasks/{task_id}/review/request")
def request_review(
    task_id: str,
    body: ReviewRequestRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Ask a reviewer to check the contractor's deliverable (→ review: pending).

    Reviewer defaults to the delegator (the agent who handed off the work) and
    must be a workspace member other than the contractor — you can't review your
    own work. Posts an @-mention so the reviewer's runtime picks it up.
    """
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")

    # Resolve the reviewer: explicit, else the delegator if it's an agent.
    reviewer = body.reviewer
    if not reviewer and (task.delegator or "").startswith("openagents:"):
        reviewer = _agent_name(task.delegator)
    if not reviewer:
        return json_response(ResponseCode.BAD_REQUEST, "No reviewer given and delegator is not an agent")
    reviewer = _agent_name(reviewer)
    if reviewer == _agent_name(task.contractor):
        return json_response(ResponseCode.BAD_REQUEST, "Reviewer cannot be the contractor (no self-review)")
    if not _is_member(db, str(workspace.id), reviewer):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown reviewer '{reviewer}'")

    _set_review(
        task,
        state="pending",
        reviewer=reviewer,
        requestedAt=_iso(_now()),
        requestedBy=body.actor or _agent_name(task.delegator),
        comment=None,
    )
    _append_event(task, "review_requested", actor=body.actor or _agent_name(task.delegator), detail=reviewer)
    task.history = list(task.history or []) + [_message("user", f"Review requested from {reviewer}.")]

    # Nudge the reviewer in the task's channel (best-effort).
    if task.channel_name:
        try:
            event = Event(
                type="workspace.message.posted",
                source=task.delegator,
                target=f"channel/{task.channel_name}",
                payload={
                    "content": f"@{reviewer} please review {_agent_name(task.contractor)}'s "
                               f"work on this task and approve or request changes.",
                    "message_type": "chat",
                },
                metadata={"taskId": task.id, "review": "requested"},
            )
            _emit_event_blocking(event, workspace, db, token=x_workspace_token)
        except Exception:
            logger.exception("a2a: review-request nudge failed for task %s", task.id)

    return _commit_review(db, task)


@router.post("/tasks/{task_id}/review/approve")
def approve_review(
    task_id: str,
    body: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Reviewer signs off on the deliverable (→ review: approved)."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")
    review = (task.task_metadata or {}).get("review")
    if not review or review.get("state") != "pending":
        return json_response(ResponseCode.BAD_REQUEST, "Task has no pending review")

    _set_review(
        task,
        state="approved",
        decidedAt=_iso(_now()),
        decidedBy=body.reviewer or review.get("reviewer"),
        comment=body.comment,
    )
    _append_event(task, "review_approved", actor=body.reviewer or review.get("reviewer"))
    task.history = list(task.history or []) + [_message("user", "Review approved.")]
    return _commit_review(db, task)


@router.post("/tasks/{task_id}/review/request-changes")
def request_changes(
    task_id: str,
    body: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Reviewer sends the work back for changes (→ review: changes_requested),
    posting the feedback to the contractor so they pick it up again."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")
    review = (task.task_metadata or {}).get("review")
    if not review or review.get("state") != "pending":
        return json_response(ResponseCode.BAD_REQUEST, "Task has no pending review")

    _set_review(
        task,
        state="changes_requested",
        decidedAt=_iso(_now()),
        decidedBy=body.reviewer or review.get("reviewer"),
        comment=body.comment,
    )
    contractor_name = _agent_name(task.contractor)
    _append_event(task, "changes_requested", actor=body.reviewer or review.get("reviewer"), detail=body.comment)
    task.history = list(task.history or []) + [
        _message("user", f"Changes requested: {body.comment or '(no detail)'}")
    ]

    # Send the contractor back to work with the feedback (best-effort).
    if task.channel_name:
        try:
            reviewer = review.get("reviewer") or "reviewer"
            feedback = body.comment or "please revise your deliverable."
            event = Event(
                type="workspace.message.posted",
                source=_agent_address(reviewer),
                target=f"channel/{task.channel_name}",
                payload={
                    "content": f"@{contractor_name} changes requested on your task: {feedback}",
                    "message_type": "chat",
                },
                metadata={"taskId": task.id, "review": "changes_requested"},
            )
            _emit_event_blocking(event, workspace, db, token=x_workspace_token)
        except Exception:
            logger.exception("a2a: request-changes nudge failed for task %s", task.id)

    return _commit_review(db, task)


# ---------------------------------------------------------------------------
# Task comments — a lightweight discussion thread on a delegation
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/comments")
def add_comment(
    task_id: str,
    body: CommentRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Append a comment to the task's discussion thread (agents + humans)."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    text = (body.text or "").strip()
    if not text:
        return json_response(ResponseCode.BAD_REQUEST, "Empty comment")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")

    meta = dict(task.task_metadata or {})
    comments = list(meta.get("comments") or [])
    comments.append({
        "id": _uuidlib.uuid4().hex,
        "author": _agent_name(body.author),
        "text": text,
        "createdAt": _iso(_now()),
        "replyTo": body.reply_to,
    })
    meta["comments"] = comments
    task.task_metadata = meta
    _append_event(task, "commented", actor=_agent_name(body.author))
    task.updated_at = _now()
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        return json_response(ResponseCode.CONFLICT, "Task was modified concurrently; retry")
    db.refresh(task)
    return success_response(_serialize_task(task))


# ---------------------------------------------------------------------------
# Task dependencies — blocks / blocked-by edges (frontier scheduling)
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/dependencies")
def edit_dependency(
    task_id: str,
    body: DependencyRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Add or remove a 'blocked by' edge: this task waits on `blocked_by`.

    Maintains both sides of the edge — this task's blockedBy and the other
    task's blocks — so the graph stays consistent.
    """
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")
    if body.action not in ("add", "remove"):
        return json_response(ResponseCode.BAD_REQUEST, "action must be add|remove")
    if body.blocked_by == task_id:
        return json_response(ResponseCode.BAD_REQUEST, "A task cannot block itself")

    task = _load_task(db, str(workspace.id), task_id)
    blocker = _load_task(db, str(workspace.id), body.blocked_by)
    if not task or not blocker:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")

    add = body.action == "add"
    _edit_dep(task, "blockedBy", blocker.id, add)
    _edit_dep(blocker, "blocks", task.id, add)
    _append_event(task, "dependency_added" if add else "dependency_removed", detail=blocker.id)
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        return json_response(ResponseCode.CONFLICT, "Task was modified concurrently; retry")
    db.refresh(task)
    return success_response(_serialize_task(task))


# ---------------------------------------------------------------------------
# Team coordination — reassign, nudge, clarification (boss ⇄ agent interactions)
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/reassign")
def reassign_task(
    task_id: str,
    body: ReassignRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Hand a non-terminal task to a different contractor and re-kick it off."""
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

    new_name = _agent_name(body.contractor)
    if not _is_member(db, str(workspace.id), new_name):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown contractor '{new_name}'")
    old_name = _agent_name(task.contractor)
    if new_name == old_name:
        return json_response(ResponseCode.BAD_REQUEST, "Already assigned to that agent")

    task.contractor = _agent_address(new_name)
    task.updated_at = _now()
    _append_event(task, "reassigned", actor=body.actor, detail=f"{old_name} → {new_name}")
    task.history = list(task.history or []) + [_message("user", f"Reassigned from {old_name} to {new_name}.")]

    # Re-kick-off the new contractor with the original instruction.
    req_text = ((task.input or {}).get("parts") or [{}])[0].get("text") if task.input else None
    if task.channel_name and req_text:
        try:
            event = Event(
                type="workspace.message.posted",
                source=task.delegator,
                target=f"channel/{task.channel_name}",
                payload={"content": build_delegation_kickoff(new_name, req_text, task.id), "message_type": "delegate"},
                metadata={"taskId": task.id},
            )
            _emit_event_blocking(event, workspace, db, token=x_workspace_token)
        except Exception:
            logger.exception("a2a: reassign kick-off failed for task %s", task.id)
    return _commit_review(db, task)


@router.post("/tasks/{task_id}/nudge")
def nudge_task(
    task_id: str,
    body: NudgeRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Poke the contractor of a non-terminal task to continue / report status."""
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

    contractor_name = _agent_name(task.contractor)
    text = body.text or f"reminder — this task is still {_WIRE_STATE.get(task.state, task.state)}. Please continue or report status."
    task.updated_at = _now()
    _append_event(task, "nudged", detail=contractor_name)
    task.history = list(task.history or []) + [_message("user", "Nudged the contractor.")]
    if task.channel_name:
        try:
            event = Event(
                type="workspace.message.posted",
                source=task.delegator,
                target=f"channel/{task.channel_name}",
                payload={"content": f"@{contractor_name} {text}", "message_type": "chat"},
                metadata={"taskId": task.id, "nudge": True},
            )
            _emit_event_blocking(event, workspace, db, token=x_workspace_token)
        except Exception:
            logger.exception("a2a: nudge failed for task %s", task.id)
    return _commit_review(db, task)


@router.post("/tasks/{task_id}/clarification")
def set_clarification(
    task_id: str,
    body: ClarificationRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Mark a task as waiting on human input, or resolve it with an answer."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")
    if body.action not in ("set", "resolve"):
        return json_response(ResponseCode.BAD_REQUEST, "action must be set|resolve")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")

    meta = dict(task.task_metadata or {})
    if body.action == "set":
        meta["clarification"] = {
            "state": "needs_user",
            "question": (body.question or "").strip() or "needs your input",
            "askedAt": _iso(_now()),
            "askedBy": body.actor or _agent_name(task.contractor),
        }
        task.history = list(task.history or []) + [_message("agent", f"Needs input: {meta['clarification']['question']}")]
    else:
        meta["clarification"] = None
        if body.answer:
            comments = list(meta.get("comments") or [])
            comments.append({"id": _uuidlib.uuid4().hex, "author": _agent_name(body.actor or "human:you"),
                             "text": body.answer, "createdAt": _iso(_now()), "replyTo": None})
            meta["comments"] = comments
            # Nudge the contractor with the answer so it can continue.
            if task.channel_name:
                try:
                    event = Event(
                        type="workspace.message.posted",
                        source=task.delegator,
                        target=f"channel/{task.channel_name}",
                        payload={"content": f"@{_agent_name(task.contractor)} (clarification) {body.answer}", "message_type": "chat"},
                        metadata={"taskId": task.id},
                    )
                    _emit_event_blocking(event, workspace, db, token=x_workspace_token)
                except Exception:
                    logger.exception("a2a: clarification answer relay failed for task %s", task.id)
        task.history = list(task.history or []) + [_message("user", "Clarification resolved.")]
    task.task_metadata = meta
    if body.action == "set":
        _append_event(task, "clarification_requested",
                      actor=body.actor or _agent_name(task.contractor),
                      detail=(meta.get("clarification") or {}).get("question"))
    else:
        _append_event(task, "clarification_resolved", actor=body.actor, detail=body.answer)
    task.updated_at = _now()
    return _commit_review(db, task)


# ---------------------------------------------------------------------------
# Subtasks — fan a parent task out to multiple contractors (team decomposition)
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/subtasks")
def create_subtask(
    task_id: str,
    body: SubtaskRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Break a parent task into a child delegation assigned to another agent.

    The child is a first-class A2A task (its own lifecycle) linked to the parent
    via task_metadata.parentId; the UI rolls up children's progress on the parent
    card. The child inherits the parent's channel so its kick-off lands in the
    same thread.
    """
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    parent = _load_task(db, str(workspace.id), task_id)
    if not parent:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")
    if parent.task_metadata and parent.task_metadata.get("parentId"):
        return json_response(ResponseCode.BAD_REQUEST, "Subtasks cannot have their own subtasks")

    contractor_addr = _agent_address(body.contractor)
    contractor_name = _agent_name(contractor_addr)
    if not _is_member(db, str(workspace.id), contractor_name):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown contractor '{contractor_name}'")

    child = _build_and_kickoff_task(
        db, workspace,
        source=body.source,
        contractor_addr=contractor_addr,
        text=body.text,
        skill_id=body.skill_id,
        context_id=parent.context_id,
        parent_id=parent.id,
        token=x_workspace_token,
    )

    # Record the fan-out on the parent's timeline (best-effort — the child is
    # already committed and is the source of truth).
    parent = _load_task(db, str(workspace.id), task_id)
    if parent:
        _append_event(parent, "subtask_created", actor=_agent_name(body.source), detail=contractor_name)
        parent.updated_at = _now()
        try:
            db.commit()
        except StaleDataError:
            db.rollback()
    db.refresh(child)
    return success_response(_serialize_task(child))


# ---------------------------------------------------------------------------
# Soft delete / restore — a recycle bin for the board (overlay, not a real drop)
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/delete")
def soft_delete_task(
    task_id: str,
    body: ActorRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Move a task to the recycle bin (hidden from the board, fully restorable).

    A task_metadata overlay — the TaskRecord is never destroyed, so the A2A
    lifecycle/history survive and the task can be brought back intact.
    """
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")

    meta = dict(task.task_metadata or {})
    if not meta.get("deleted"):
        meta["deleted"] = {"at": _iso(_now()), "by": body.actor or "user"}
        task.task_metadata = meta
        _append_event(task, "deleted", actor=body.actor)
        task.updated_at = _now()
    return _commit_review(db, task)


@router.post("/tasks/{task_id}/restore")
def restore_task(
    task_id: str,
    body: ActorRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Bring a task back from the recycle bin."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    task = _load_task(db, str(workspace.id), task_id)
    if not task:
        return json_response(ResponseCode.NOT_FOUND, "Task not found")

    meta = dict(task.task_metadata or {})
    if meta.get("deleted"):
        meta.pop("deleted", None)
        task.task_metadata = meta
        _append_event(task, "restored", actor=body.actor)
        task.updated_at = _now()
    return _commit_review(db, task)


# ---------------------------------------------------------------------------
# Agent ↔ agent direct messaging (peer lane — a private 2-party conversation)
# ---------------------------------------------------------------------------
# Direct agent-to-agent communication, distinct from task delegation: no board
# lifecycle, just a back-and-forth. It rides on a private 2-member channel so
# today's polling agents are triggered through the normal @mention routing (the
# member event-poll only delivers channel events, not arbitrary directed ones) —
# no launcher change. One lane serves both fire-and-forget DMs and "consult"
# (expects_reply: ask a peer and get an answer back).

def _strip_leading_mention(content: str) -> str:
    """Drop a leading @name token so the DM thread reads as plain conversation."""
    c = (content or "").strip()
    if c.startswith("@"):
        parts = c.split(None, 1)
        return parts[1].strip() if len(parts) > 1 else ""
    return c


def _dm_channel_name(a_name: str, b_name: str) -> str:
    """Stable, order-independent private-channel name for an agent pair."""
    return "dm-" + "~".join(sorted([a_name, b_name]))


def _ensure_dm_channel(db: Session, workspace, a_name: str, b_name: str) -> str:
    """Get-or-create the pair's private DM channel and ensure both are members."""
    name = _dm_channel_name(a_name, b_name)
    ch = db.execute(
        select(Channel).where(Channel.workspace_id == str(workspace.id), Channel.name == name)
    ).scalar_one_or_none()
    if ch is None:
        ch = Channel(
            workspace_id=str(workspace.id),
            name=name,
            title=f"{a_name} ↔ {b_name}",
            created_by="system",
            status="active",
        )
        db.add(ch)
        db.flush()
    have = set(db.execute(
        select(ChannelMember.agent_name).where(ChannelMember.channel_id == ch.id)
    ).scalars().all())
    for nm in (a_name, b_name):
        if nm not in have:
            db.add(ChannelMember(channel_id=ch.id, agent_name=nm))
    db.flush()
    return name


class PeerMessageRequest(BaseModel):
    network: str
    source: str                   # sender agent (name or address)
    to: str                       # recipient agent (name or address)
    text: str
    expects_reply: bool = False   # consult flavor — ask a peer and get an answer back


@router.post("/messages")
def send_peer_message(
    body: PeerMessageRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Send a direct agent→agent message. Lands in the pair's private DM channel,
    triggering the recipient via the normal @mention routing. `expects_reply`
    marks a consult (ask and wait for an answer in the same thread)."""
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    text = (body.text or "").strip()
    if not text:
        return json_response(ResponseCode.BAD_REQUEST, "Empty message")

    from_name = _agent_name(body.source)
    to_name = _agent_name(body.to)
    if from_name == to_name:
        return json_response(ResponseCode.BAD_REQUEST, "An agent cannot message itself")
    if not _is_member(db, str(workspace.id), from_name):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown sender '{from_name}'")
    if not _is_member(db, str(workspace.id), to_name):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown recipient '{to_name}'")

    channel = _ensure_dm_channel(db, workspace, from_name, to_name)

    content = f"@{to_name} {text}"
    if body.expects_reply:
        content += "  · please reply here when done."
    try:
        event = Event(
            type="workspace.message.posted",
            source=_agent_address(from_name),
            target=f"channel/{channel}",
            payload={"content": content, "message_type": "peer"},
            metadata={"peer": {"from": from_name, "to": to_name, "expectsReply": body.expects_reply}},
        )
        _emit_event_blocking(event, workspace, db, token=x_workspace_token)
    except Exception:
        logger.exception("a2a: peer message delivery failed (%s → %s)", from_name, to_name)
        return json_response(ResponseCode.BAD_REQUEST, "Failed to deliver message")
    db.commit()

    return success_response({
        "channel": channel,
        "from": from_name,
        "to": to_name,
        "text": text,
        "expectsReply": body.expects_reply,
    })


@router.get("/messages")
def list_peer_messages(
    network: str = Query(...),
    channel: Optional[str] = Query(None),   # a specific dm- channel → return its thread
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """List agent↔agent DM threads, or one thread's messages (with `channel`)."""
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    if channel:
        rows = db.execute(
            select(EventRecord).where(
                EventRecord.network_id == workspace.id,
                EventRecord.target == f"channel/{channel}",
                EventRecord.type == "workspace.message.posted",
            ).order_by(EventRecord.timestamp.asc())
        ).scalars().all()
        messages = [{
            "id": e.id,
            "from": _agent_name(e.source),
            "text": _strip_leading_mention((e.payload or {}).get("content") or ""),
            "at": e.timestamp,
            "kind": (e.payload or {}).get("message_type"),
            "consult": bool(((e.metadata_ or {}).get("peer") or {}).get("expectsReply")),
        } for e in rows]
        return success_response({"channel": channel, "messages": messages})

    chans = db.execute(
        select(Channel).where(
            Channel.workspace_id == str(workspace.id),
            Channel.name.startswith("dm-"),
            Channel.status == "active",
        )
    ).scalars().all()
    threads = []
    for ch in chans:
        members = db.execute(
            select(ChannelMember.agent_name).where(ChannelMember.channel_id == ch.id)
        ).scalars().all()
        last = db.execute(
            select(EventRecord).where(
                EventRecord.network_id == workspace.id,
                EventRecord.target == f"channel/{ch.name}",
                EventRecord.type == "workspace.message.posted",
            ).order_by(EventRecord.timestamp.desc()).limit(1)
        ).scalar_one_or_none()
        threads.append({
            "channel": ch.name,
            "participants": sorted(members),
            "lastText": _strip_leading_mention((last.payload or {}).get("content") or "") if last else None,
            "lastFrom": _agent_name(last.source) if last else None,
            "lastAt": last.timestamp if last else None,
        })
    threads.sort(key=lambda t: t["lastAt"] or 0, reverse=True)
    return success_response({"threads": threads})


# ---------------------------------------------------------------------------
# Consult — synchronous "ask a teammate and get the answer back" (nested chat)
# ---------------------------------------------------------------------------
# The distributed-architecture analogue of AG2/AutoGen's register_nested_chats
# (conversable_agent.py): an agent, before answering, runs a sub-conversation
# with a teammate and uses the result. Here the *server* orchestrates that
# sub-conversation: post the question into the pair's DM channel (which triggers
# the teammate), block until the teammate replies, and return the reply — so the
# asker's single call gets the answer inline. Agents invoke it via curl/exec or
# the consult_teammate MCP tool.

class ConsultRequest(BaseModel):
    network: str
    source: str                   # the asking agent
    to: str                       # the teammate being consulted
    question: str
    wait: int = 60                # max seconds to block for the reply


@router.post("/consult")
def consult_teammate(
    body: ConsultRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Ask a teammate a question and block until they answer (or timeout).

    Posts the question into the pair's private DM channel (triggering the
    teammate via normal routing), then long-polls for the teammate's reply and
    returns it. The server runs the sub-conversation; the caller gets the answer
    back in one synchronous call (AG2 nested-chat, adapted to our event bus).
    """
    workspace = _resolve_workspace(db, body.network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    question = (body.question or "").strip()
    if not question:
        return json_response(ResponseCode.BAD_REQUEST, "Empty question")
    from_name = _agent_name(body.source)
    to_name = _agent_name(body.to)
    if from_name == to_name:
        return json_response(ResponseCode.BAD_REQUEST, "An agent cannot consult itself")
    if not _is_member(db, str(workspace.id), from_name):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown asker '{from_name}'")
    if not _is_member(db, str(workspace.id), to_name):
        return json_response(ResponseCode.BAD_REQUEST, f"Unknown teammate '{to_name}'")

    channel = _ensure_dm_channel(db, workspace, from_name, to_name)
    # Watermark just before posting — we wait for a reply from `to` newer than this.
    asked_at_ms = int(_now().timestamp() * 1000)
    try:
        event = Event(
            type="workspace.message.posted",
            source=_agent_address(from_name),
            target=f"channel/{channel}",
            payload={"content": f"@{to_name} {question}  · please answer concisely.", "message_type": "peer"},
            metadata={"peer": {"from": from_name, "to": to_name, "consult": True}},
        )
        _emit_event_blocking(event, workspace, db, token=x_workspace_token)
    except Exception:
        logger.exception("a2a: consult question delivery failed (%s → %s)", from_name, to_name)
        return json_response(ResponseCode.BAD_REQUEST, "Failed to deliver question")
    db.commit()

    # Long-poll for the teammate's reply in this DM channel (skip thinking/status).
    # Capture plain values up front — db.close() between polls detaches ORM
    # objects, so the query must not touch `workspace`/other ORM attributes.
    to_addr = _agent_address(to_name)
    ws_id = str(workspace.id)
    channel_target = f"channel/{channel}"
    started = time.time()
    deadline = started + min(max(body.wait, 1), MAX_WAIT_SECONDS)
    logger.info("a2a consult: %s → %s asking (channel=%s, wait=%ss)", from_name, to_name, channel, body.wait)
    while time.time() < deadline:
        db.close()                # release the pooled connection while we wait
        time.sleep(3)
        # Earliest message from `to` after the watermark. The teammate often
        # posts an intermediate "thinking"/status before the real answer, so on
        # those we ADVANCE the watermark past them — otherwise the ascending
        # `.first()` keeps returning the same status message and never reaches
        # the chat reply (the bug where the teammate answered but consult still
        # timed out).
        reply = db.execute(
            select(EventRecord).where(
                EventRecord.network_id == ws_id,
                EventRecord.target == channel_target,
                EventRecord.type == "workspace.message.posted",
                EventRecord.source == to_addr,
                EventRecord.timestamp > asked_at_ms,
            ).order_by(EventRecord.timestamp.asc())
        ).scalars().first()
        if reply is None:
            continue
        if (reply.payload or {}).get("message_type") in ("thinking", "status", "todos"):
            asked_at_ms = reply.timestamp     # step past the intermediate message
            continue
        text = _strip_leading_mention((reply.payload or {}).get("content") or "")
        if text:
            logger.info("a2a consult: %s → %s ANSWERED in %.0fs (%d chars)",
                        from_name, to_name, time.time() - started, len(text))
            return success_response({"answered": True, "from": to_name, "answer": text, "channel": channel})

    logger.info("a2a consult: %s → %s TIMED OUT after %ss (no reply)", from_name, to_name, body.wait)
    return success_response({
        "answered": False, "from": to_name, "answer": None, "channel": channel,
        "note": f"{to_name} did not reply within {body.wait}s (may be offline or busy).",
    })
