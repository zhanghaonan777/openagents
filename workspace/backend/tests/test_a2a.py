# -*- coding: utf-8 -*-
"""Tests for the A2A gateway (agent-to-agent structured delegation)."""

from datetime import datetime, timedelta, timezone

import pytest


def _hdr(ws):
    return {"X-Workspace-Token": ws["token"]}


def _join(client, ws, name):
    r = client.post("/v1/join", json={
        "agent_name": name, "network": ws["id"], "token": ws["token"],
    })
    assert r.status_code == 200, r.text
    return r


def _delegate(client, ws, contractor="coder", text="Build the login form", channel=None):
    return client.post("/v1/a2a/tasks", json={
        "network": ws["id"],
        "source": "openagents:pm",
        "contractor": contractor,
        "text": text,
        "context_id": channel if channel is not None else ws["channel"]["name"],
    }, headers=_hdr(ws))


# ---------------------------------------------------------------------------
# Capability discovery — Agent Cards
# ---------------------------------------------------------------------------

def test_agent_cards_have_a2a_shape(client, workspace):
    _join(client, workspace, "coder")
    r = client.get("/v1/a2a/agents", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    agents = r.json()["data"]["agents"]
    card = next(a for a in agents if a["name"] == "coder")
    assert card["id"] == "openagents:coder"
    assert card["capabilities"] == {
        "streaming": False, "pushNotifications": False, "extendedAgentCard": False,
    }
    assert card["skills"] == []  # none declared yet


def test_single_agent_card(client, workspace):
    _join(client, workspace, "coder")
    r = client.get("/v1/a2a/agents/coder/card", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == "coder"

    missing = client.get("/v1/a2a/agents/ghost/card", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Task lifecycle
# ---------------------------------------------------------------------------

def test_delegate_creates_submitted_task(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    r = _delegate(client, workspace)
    assert r.status_code == 200, r.text
    task = r.json()["data"]
    assert task["state"] == "submitted"
    assert task["status"]["state"] == "submitted"
    assert task["contractor"] == "openagents:coder"
    assert task["delegator"] == "openagents:pm"
    assert task["history"][0]["parts"][0]["text"] == "Build the login form"


def test_todos_bridge_advances_to_working(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]

    # Contractor acts (posts todos) in the task's channel → bridge → working.
    r = client.put("/v1/todos", json={
        "network": workspace["id"], "source": "openagents:coder",
        "channel": workspace["channel"]["name"],
        "todos": [{"content": "scaffold form", "status": "in_progress"}],
    }, headers=_hdr(workspace))
    assert r.status_code == 200, r.text

    got = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert got.json()["data"]["state"] == "working"


def test_explicit_completion_with_artifact(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]

    r = client.post(f"/v1/a2a/tasks/{tid}/status", json={
        "network": workspace["id"], "state": "working", "text": "on it",
    }, headers=_hdr(workspace))
    assert r.json()["data"]["state"] == "working"

    r = client.post(f"/v1/a2a/tasks/{tid}/status", json={
        "network": workspace["id"], "state": "completed",
        "text": "done", "artifact_text": "PR #42",
    }, headers=_hdr(workspace))
    done = r.json()["data"]
    assert done["state"] == "completed"
    assert done["completedAt"] is not None
    assert done["artifacts"][0]["parts"][0]["text"] == "PR #42"


def test_illegal_transition_rejected(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "completed"}, headers=_hdr(workspace))

    # Terminal → no further transitions.
    r = client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_unknown_state_rejected(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "bogus"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_cancel(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/cancel", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.json()["data"]["state"] == "canceled"
    assert r.json()["data"]["completedAt"] is not None


def test_list_and_filter(client, workspace):
    _join(client, workspace, "coder")
    _delegate(client, workspace, text="t0")
    _delegate(client, workspace, text="t1")
    r = client.get("/v1/a2a/tasks", params={"network": workspace["id"], "contractor": "coder"}, headers=_hdr(workspace))
    assert len(r.json()["data"]["tasks"]) == 2


def test_auth_required(client, workspace):
    r = client.get("/v1/a2a/agents", params={"network": workspace["id"]}, headers={"X-Workspace-Token": "wrong"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Hardening — contractor validation, optimistic lock, lease/reaper self-heal
# ---------------------------------------------------------------------------

def test_unknown_contractor_rejected(client, workspace):
    # No agent joined → "ghost" is not a member; delegation must be rejected.
    r = client.post("/v1/a2a/tasks", json={
        "network": workspace["id"], "source": "openagents:pm",
        "contractor": "ghost", "text": "x", "context_id": workspace["channel"]["name"],
    }, headers=_hdr(workspace))
    assert r.status_code == 400


def test_version_increments_on_transition(client, workspace, db):
    from app.models import TaskRecord
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    db.expire_all()
    v0 = db.get(TaskRecord, tid).version
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    db.expire_all()
    assert db.get(TaskRecord, tid).version > v0


def test_optimistic_lock_blocks_concurrent_update(client, workspace, db):
    """Two writers loading the same task; the late committer must lose (the CAS
    that prevents a reaper/worker lost-update)."""
    from sqlalchemy.orm import Session as SASession
    from sqlalchemy.orm.exc import StaleDataError
    from app.models import TaskRecord
    from app.routers.a2a import _apply_transition

    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    db.expire_all()
    other = SASession(bind=db.get_bind())
    try:
        ta = db.get(TaskRecord, tid)
        tb = other.get(TaskRecord, tid)
        _apply_transition(ta, "working", None)
        db.commit()                       # winner → version bumps
        _apply_transition(tb, "working", None)
        with pytest.raises(StaleDataError):
            other.commit()                # loser → stale version
    finally:
        other.rollback()
        other.close()


def test_bridge_survives_concurrent_version_bump(client, workspace, db):
    """H2: if a task is advanced concurrently while the todos→task bridge runs,
    the bridge's optimistic-lock conflict is isolated in a SAVEPOINT and must
    NOT fail the caller's todo commit."""
    from sqlalchemy import update
    from sqlalchemy.orm import Session as SASession
    from app.models import TaskRecord, TodoRecord
    from app.routers.a2a import advance_tasks_on_contractor_activity, _agent_address

    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]  # state: submitted
    ws_id = workspace["id"]
    chan = workspace["channel"]["name"]
    coder = _agent_address("coder")

    db.expire_all()
    # The caller's pending write that must survive (todos.py commits this).
    db.add(TodoRecord(workspace_id=ws_id, channel_name=chan, created_by=coder,
                      assignee=coder, content="scaffold", status="in_progress"))
    # Cache the task in this session at version N, then bump the DB version behind
    # its back (a concurrent reaper/status writer) — keeping it in the bridge's
    # query range so the bridge still tries to advance it and hits the conflict.
    cached = db.get(TaskRecord, tid)
    assert cached.state == "submitted"
    other = SASession(bind=db.get_bind())
    try:
        other.execute(update(TaskRecord).where(TaskRecord.id == tid).values(version=cached.version + 1))
        other.commit()
    finally:
        other.close()

    # Bridge runs against the stale cached task → StaleDataError swallowed.
    advance_tasks_on_contractor_activity(db, ws_id, coder, chan)
    db.commit()  # must NOT raise

    db.expire_all()
    todos = db.query(TodoRecord).filter_by(workspace_id=ws_id, created_by=coder).all()
    assert any(t.content == "scaffold" for t in todos)  # caller's write persisted


def test_wait_returns_non_terminal_task_on_timeout(client, workspace):
    """H3: blocking `wait` releases the DB connection each tick and returns the
    task (still non-terminal) when the contractor doesn't finish in time."""
    _join(client, workspace, "coder")
    r = client.post("/v1/a2a/tasks", json={
        "network": workspace["id"], "source": "openagents:pm",
        "contractor": "coder", "text": "do x",
        "context_id": workspace["channel"]["name"], "wait": 1,
    }, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["state"] in ("submitted", "working")


def _force_lease_expired(db, task_id):
    from app.models import TaskRecord
    db.expire_all()
    t = db.get(TaskRecord, task_id)
    t.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    db.commit()


def test_reaper_times_out_stale_working_task(client, workspace, db):
    from app.routers.a2a import reap_stale_tasks
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    _force_lease_expired(db, tid)
    assert reap_stale_tasks(db) >= 1
    got = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert got["state"] == "failed"


def test_reaper_cancels_stale_input_required(client, workspace, db):
    from app.routers.a2a import reap_stale_tasks
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "input_required"}, headers=_hdr(workspace))
    _force_lease_expired(db, tid)
    reap_stale_tasks(db)
    got = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert got["state"] == "canceled"


def test_reaper_leaves_fresh_and_terminal_tasks_alone(client, workspace, db):
    from app.routers.a2a import reap_stale_tasks
    _join(client, workspace, "coder")
    # fresh working task (lease in the future) — must not be reaped
    fresh = _delegate(client, workspace, text="fresh").json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{fresh}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    # completed task with a (cleared) lease — must not be reaped
    done = _delegate(client, workspace, text="done").json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{done}/status", json={"network": workspace["id"], "state": "completed"}, headers=_hdr(workspace))
    reap_stale_tasks(db)
    g = lambda tid: client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["state"]
    assert g(fresh) == "working"
    assert g(done) == "completed"


# ---------------------------------------------------------------------------
# Phase 2 — native flow: skill declaration, task.delegated event, auto-complete
# ---------------------------------------------------------------------------

def test_declare_and_discover_skills(client, workspace):
    _join(client, workspace, "coder")
    skills = [{"id": "code-review", "name": "Code Review", "description": "Reviews PRs", "tags": ["quality"]}]
    r = client.put("/v1/a2a/agents/coder/skills", json={"network": workspace["id"], "skills": skills}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["skills"][0]["id"] == "code-review"

    card = client.get("/v1/a2a/agents/coder/card", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert card.json()["data"]["skills"][0]["name"] == "Code Review"


def test_task_delegated_event_persisted(client, workspace, db):
    from sqlalchemy import select
    from app.models import EventRecord

    _join(client, workspace, "coder")
    _delegate(client, workspace).json()["data"]["id"]

    rows = db.execute(
        select(EventRecord).where(EventRecord.type == "workspace.task.delegated")
    ).scalars().all()
    assert any(e.target == "openagents:coder" for e in rows)


def test_all_todos_done_auto_completes_task(client, workspace):
    _join(client, workspace, "coder")
    ch = workspace["channel"]["name"]
    tid = _delegate(client, workspace).json()["data"]["id"]

    # in_progress todo → working
    client.put("/v1/todos", json={
        "network": workspace["id"], "source": "openagents:coder", "channel": ch,
        "todos": [{"content": "scaffold", "status": "in_progress"}],
    }, headers=_hdr(workspace))
    assert client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["state"] == "working"

    # all todos completed → task auto-completes with a result artifact
    client.put("/v1/todos", json={
        "network": workspace["id"], "source": "openagents:coder", "channel": ch,
        "todos": [{"content": "scaffold", "status": "completed"}],
    }, headers=_hdr(workspace))
    done = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert done["state"] == "completed"
    assert done["artifacts"] and "scaffold" in done["artifacts"][0]["parts"][0]["text"]


def test_input_required_uses_a2a_wire_form(client, workspace):
    """The flat `state` field must use the hyphenated A2A wire form so the UI
    board can map it (regression: it previously leaked the snake_case DB value)."""
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    r = client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "input_required"}, headers=_hdr(workspace))
    data = r.json()["data"]
    assert data["state"] == "input-required"
    assert data["status"]["state"] == "input-required"


def test_multiple_delegations_in_one_channel_do_not_auto_complete(client, workspace):
    """With >1 delegation sharing a channel, the single shared todo list can't be
    attributed to one task, so auto-completion must NOT fire (stays working)."""
    _join(client, workspace, "coder")
    ch = workspace["channel"]["name"]
    t1 = _delegate(client, workspace, text="a").json()["data"]["id"]
    t2 = _delegate(client, workspace, text="b").json()["data"]["id"]
    client.put("/v1/todos", json={
        "network": workspace["id"], "source": "openagents:coder", "channel": ch,
        "todos": [{"content": "x", "status": "completed"}],
    }, headers=_hdr(workspace))
    for tid in (t1, t2):
        st = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["state"]
        assert st == "working"
