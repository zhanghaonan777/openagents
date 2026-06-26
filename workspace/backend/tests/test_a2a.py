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


# ---------------------------------------------------------------------------
# Review loop — peer review of a delegated deliverable
# ---------------------------------------------------------------------------

def _review_of(client, ws, tid):
    got = client.get(f"/v1/a2a/tasks/{tid}", params={"network": ws["id"]}, headers=_hdr(ws))
    return got.json()["data"]["review"]


def test_review_request_defaults_to_delegator(client, workspace):
    """Requesting review with no reviewer assigns the delegator (an agent)."""
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/review/request",
                    json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    review = r.json()["data"]["review"]
    assert review["state"] == "pending"
    assert review["reviewer"] == "pm"


def test_review_approve(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/review/request",
                json={"network": workspace["id"]}, headers=_hdr(workspace))
    r = client.post(f"/v1/a2a/tasks/{tid}/review/approve",
                    json={"network": workspace["id"], "comment": "LGTM"}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    review = r.json()["data"]["review"]
    assert review["state"] == "approved"
    assert review["comment"] == "LGTM"


def test_review_request_changes(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/review/request",
                json={"network": workspace["id"]}, headers=_hdr(workspace))
    r = client.post(f"/v1/a2a/tasks/{tid}/review/request-changes",
                    json={"network": workspace["id"], "comment": "fix the validation"},
                    headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    review = r.json()["data"]["review"]
    assert review["state"] == "changes_requested"
    assert review["comment"] == "fix the validation"


def test_review_explicit_reviewer(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    _join(client, workspace, "qa")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/review/request",
                    json={"network": workspace["id"], "reviewer": "qa"}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["review"]["reviewer"] == "qa"


def test_review_self_review_rejected(client, workspace):
    """The contractor cannot be the reviewer of their own work."""
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/review/request",
                    json={"network": workspace["id"], "reviewer": "coder"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_review_unknown_reviewer_rejected(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/review/request",
                    json={"network": workspace["id"], "reviewer": "ghost"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_review_approve_without_pending_rejected(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/review/approve",
                    json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_review_does_not_change_protocol_state(client, workspace):
    """Review is a decoupled overlay — it must not mutate the A2A task state."""
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    before = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["state"]
    client.post(f"/v1/a2a/tasks/{tid}/review/request", json={"network": workspace["id"]}, headers=_hdr(workspace))
    client.post(f"/v1/a2a/tasks/{tid}/review/approve", json={"network": workspace["id"]}, headers=_hdr(workspace))
    after = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["state"]
    assert before == after == "submitted"


# ---------------------------------------------------------------------------
# Derived agenda (briefing) — "what's mine now"
# ---------------------------------------------------------------------------

def test_briefing_lists_contractor_work(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    _delegate(client, workspace, text="task one")
    r = client.get("/v1/a2a/briefing", params={"network": workspace["id"], "agent": "coder"}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["counts"]["work"] == 1
    assert data["items"][0]["kind"] == "work"
    assert data["items"][0]["contractorName"] == "coder"


def test_briefing_orders_review_pickup_first(client, workspace):
    """An assigned review outranks the reviewer's own pending work."""
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    # pm delegates to coder; coder also delegates something to pm so pm has work.
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post("/v1/a2a/tasks", json={
        "network": workspace["id"], "source": "openagents:coder",
        "contractor": "pm", "text": "pm do this", "context_id": workspace["channel"]["name"],
    }, headers=_hdr(workspace))
    # Request review from pm on coder's task.
    client.post(f"/v1/a2a/tasks/{tid}/review/request", json={"network": workspace["id"]}, headers=_hdr(workspace))

    r = client.get("/v1/a2a/briefing", params={"network": workspace["id"], "agent": "pm"}, headers=_hdr(workspace))
    items = r.json()["data"]["items"]
    assert items[0]["kind"] == "review"           # review-pickup first
    assert items[0]["priority"] == "review_pickup"
    assert any(it["kind"] == "work" for it in items)  # pm's own work still listed, but after


def test_briefing_rework_outranks_fresh_work(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    t_rework = _delegate(client, workspace, text="rework one").json()["data"]["id"]
    _delegate(client, workspace, text="fresh one")
    # Put t_rework into changes_requested.
    client.post(f"/v1/a2a/tasks/{t_rework}/review/request", json={"network": workspace["id"]}, headers=_hdr(workspace))
    client.post(f"/v1/a2a/tasks/{t_rework}/review/request-changes",
                json={"network": workspace["id"], "comment": "redo"}, headers=_hdr(workspace))

    r = client.get("/v1/a2a/briefing", params={"network": workspace["id"], "agent": "coder"}, headers=_hdr(workspace))
    items = r.json()["data"]["items"]
    assert items[0]["taskId"] == t_rework
    assert items[0]["priority"] == "rework"


def test_briefing_excludes_finished_work(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "completed"}, headers=_hdr(workspace))
    r = client.get("/v1/a2a/briefing", params={"network": workspace["id"], "agent": "coder"}, headers=_hdr(workspace))
    assert r.json()["data"]["counts"]["work"] == 0


# ---------------------------------------------------------------------------
# Task comments — discussion thread on a delegation
# ---------------------------------------------------------------------------

def test_comment_append_and_serialize(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/comments",
                    json={"network": workspace["id"], "author": "openagents:pm", "text": "looks good, ship it"},
                    headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    comments = r.json()["data"]["comments"]
    assert len(comments) == 1
    assert comments[0]["author"] == "pm"
    assert comments[0]["text"] == "looks good, ship it"
    assert comments[0]["createdAt"]


def test_comment_order_preserved(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    for txt in ("first", "second", "third"):
        client.post(f"/v1/a2a/tasks/{tid}/comments",
                    json={"network": workspace["id"], "author": "openagents:coder", "text": txt},
                    headers=_hdr(workspace))
    got = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace))
    texts = [c["text"] for c in got.json()["data"]["comments"]]
    assert texts == ["first", "second", "third"]


def test_comment_empty_rejected(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/comments",
                    json={"network": workspace["id"], "author": "human:you", "text": "   "},
                    headers=_hdr(workspace))
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Task dependencies — blocks / blocked-by + frontier scheduling
# ---------------------------------------------------------------------------

def test_dependency_link_maintains_both_sides(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    a = _delegate(client, workspace, text="task A").json()["data"]["id"]
    b = _delegate(client, workspace, text="task B").json()["data"]["id"]
    # A is blocked by B
    r = client.post(f"/v1/a2a/tasks/{a}/dependencies",
                    json={"network": workspace["id"], "blocked_by": b}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["blockedBy"] == [b]
    # B should now record that it blocks A
    bt = client.get(f"/v1/a2a/tasks/{b}", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert bt.json()["data"]["blocks"] == [a]


def test_dependency_unlink(client, workspace):
    _join(client, workspace, "coder")
    a = _delegate(client, workspace, text="A").json()["data"]["id"]
    b = _delegate(client, workspace, text="B").json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{a}/dependencies", json={"network": workspace["id"], "blocked_by": b}, headers=_hdr(workspace))
    r = client.post(f"/v1/a2a/tasks/{a}/dependencies",
                    json={"network": workspace["id"], "blocked_by": b, "action": "remove"}, headers=_hdr(workspace))
    assert r.json()["data"]["blockedBy"] == []


def test_dependency_self_rejected(client, workspace):
    _join(client, workspace, "coder")
    a = _delegate(client, workspace, text="A").json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{a}/dependencies", json={"network": workspace["id"], "blocked_by": a}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_briefing_excludes_blocked_work(client, workspace):
    """A task blocked by an unfinished task is not in the contractor's agenda."""
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    a = _delegate(client, workspace, text="blocked A").json()["data"]["id"]
    b = _delegate(client, workspace, text="blocker B").json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{a}/dependencies", json={"network": workspace["id"], "blocked_by": b}, headers=_hdr(workspace))
    # While B is open, A is blocked → coder's agenda should only have B (and not A)
    items = client.get("/v1/a2a/briefing", params={"network": workspace["id"], "agent": "coder"}, headers=_hdr(workspace)).json()["data"]["items"]
    ids = [it["taskId"] for it in items]
    assert b in ids and a not in ids
    # Finish B → A becomes actionable
    client.post(f"/v1/a2a/tasks/{b}/status", json={"network": workspace["id"], "state": "completed"}, headers=_hdr(workspace))
    items2 = client.get("/v1/a2a/briefing", params={"network": workspace["id"], "agent": "coder"}, headers=_hdr(workspace)).json()["data"]["items"]
    assert a in [it["taskId"] for it in items2]


def test_comment_reply_to(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    c1 = client.post(f"/v1/a2a/tasks/{tid}/comments", json={"network": workspace["id"], "author": "openagents:pm", "text": "first"}, headers=_hdr(workspace)).json()["data"]["comments"][0]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/comments", json={"network": workspace["id"], "author": "openagents:coder", "text": "reply", "reply_to": c1}, headers=_hdr(workspace))
    comments = r.json()["data"]["comments"]
    assert comments[1]["replyTo"] == c1


# ---------------------------------------------------------------------------
# Team coordination — reassign / nudge / clarification
# ---------------------------------------------------------------------------

def test_reassign_changes_contractor(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    _join(client, workspace, "coder2")
    tid = _delegate(client, workspace, contractor="coder").json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/reassign", json={"network": workspace["id"], "contractor": "coder2"}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["contractorName"] == "coder2"


def test_reassign_unknown_rejected(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/reassign", json={"network": workspace["id"], "contractor": "ghost"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_reassign_terminal_rejected(client, workspace):
    _join(client, workspace, "coder")
    _join(client, workspace, "coder2")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "completed"}, headers=_hdr(workspace))
    r = client.post(f"/v1/a2a/tasks/{tid}/reassign", json={"network": workspace["id"], "contractor": "coder2"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_nudge_non_terminal(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/nudge", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text


def test_nudge_terminal_rejected(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/cancel", json={"network": workspace["id"]}, headers=_hdr(workspace))
    r = client.post(f"/v1/a2a/tasks/{tid}/nudge", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_clarification_set_and_resolve(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    r = client.post(f"/v1/a2a/tasks/{tid}/clarification", json={"network": workspace["id"], "action": "set", "question": "Which database?"}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    cl = r.json()["data"]["clarification"]
    assert cl["state"] == "needs_user" and cl["question"] == "Which database?"
    r2 = client.post(f"/v1/a2a/tasks/{tid}/clarification", json={"network": workspace["id"], "action": "resolve", "answer": "Postgres"}, headers=_hdr(workspace))
    assert r2.json()["data"]["clarification"] is None
    # the answer is recorded as a comment
    assert any(c["text"] == "Postgres" for c in r2.json()["data"]["comments"])


# ---------------------------------------------------------------------------
# Subtasks — fan a parent out to multiple contractors
# ---------------------------------------------------------------------------

def _subtask(client, ws, parent_id, contractor="qa", text="write tests"):
    return client.post(f"/v1/a2a/tasks/{parent_id}/subtasks", json={
        "network": ws["id"], "source": "openagents:coder",
        "contractor": contractor, "text": text,
    }, headers=_hdr(ws))


def test_subtask_links_to_parent(client, workspace):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    _join(client, workspace, "qa")
    parent = _delegate(client, workspace).json()["data"]["id"]
    r = _subtask(client, workspace, parent, contractor="qa")
    assert r.status_code == 200, r.text
    child = r.json()["data"]
    assert child["parentId"] == parent
    assert child["contractor"] == "openagents:qa"
    assert child["state"] == "submitted"
    # the child is a first-class task that shows up in the list
    listed = client.get("/v1/a2a/tasks", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["tasks"]
    assert child["id"] in [t["id"] for t in listed]


def test_subtask_records_event_on_parent(client, workspace):
    _join(client, workspace, "pm"); _join(client, workspace, "coder"); _join(client, workspace, "qa")
    parent = _delegate(client, workspace).json()["data"]["id"]
    _subtask(client, workspace, parent, contractor="qa")
    got = client.get(f"/v1/a2a/tasks/{parent}", params={"network": workspace["id"]}, headers=_hdr(workspace))
    types = [e["type"] for e in got.json()["data"]["events"]]
    assert "subtask_created" in types


def test_subtask_of_subtask_rejected(client, workspace):
    _join(client, workspace, "pm"); _join(client, workspace, "coder"); _join(client, workspace, "qa")
    parent = _delegate(client, workspace).json()["data"]["id"]
    child = _subtask(client, workspace, parent, contractor="qa").json()["data"]["id"]
    r = _subtask(client, workspace, child, contractor="qa")
    assert r.status_code == 400  # no nested subtasks


def test_subtask_unknown_contractor_rejected(client, workspace):
    _join(client, workspace, "pm"); _join(client, workspace, "coder")
    parent = _delegate(client, workspace).json()["data"]["id"]
    r = _subtask(client, workspace, parent, contractor="ghost")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Soft delete / restore (recycle bin)
# ---------------------------------------------------------------------------

def test_soft_delete_hides_then_restore_brings_back(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]

    d = client.post(f"/v1/a2a/tasks/{tid}/delete", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert d.status_code == 200, d.text
    assert d.json()["data"]["deleted"] is True

    # default list excludes it; the recycle bin shows only it
    live = client.get("/v1/a2a/tasks", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["tasks"]
    assert tid not in [t["id"] for t in live]
    binned = client.get("/v1/a2a/tasks", params={"network": workspace["id"], "deleted": "true"}, headers=_hdr(workspace)).json()["data"]["tasks"]
    assert tid in [t["id"] for t in binned]

    r = client.post(f"/v1/a2a/tasks/{tid}/restore", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.json()["data"]["deleted"] is False
    live2 = client.get("/v1/a2a/tasks", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["tasks"]
    assert tid in [t["id"] for t in live2]


def test_soft_delete_preserves_lifecycle(client, workspace):
    """Deleting is an overlay — the A2A state/history survive intact."""
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    client.post(f"/v1/a2a/tasks/{tid}/delete", json={"network": workspace["id"]}, headers=_hdr(workspace))
    got = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert got["state"] == "working"  # unchanged by the soft delete


# ---------------------------------------------------------------------------
# Structured timeline events
# ---------------------------------------------------------------------------

def test_timeline_records_create_and_status(client, workspace):
    _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/status", json={"network": workspace["id"], "state": "working"}, headers=_hdr(workspace))
    events = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["events"]
    types = [e["type"] for e in events]
    assert types[0] == "task_created"
    assert "status_changed" in types
    sc = next(e for e in events if e["type"] == "status_changed")
    assert sc["detail"] == "working"


def test_timeline_records_overlay_actions(client, workspace):
    _join(client, workspace, "pm"); _join(client, workspace, "coder")
    tid = _delegate(client, workspace).json()["data"]["id"]
    client.post(f"/v1/a2a/tasks/{tid}/comments", json={"network": workspace["id"], "author": "openagents:pm", "text": "looks good"}, headers=_hdr(workspace))
    client.post(f"/v1/a2a/tasks/{tid}/review/request", json={"network": workspace["id"]}, headers=_hdr(workspace))
    events = client.get(f"/v1/a2a/tasks/{tid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["events"]
    types = [e["type"] for e in events]
    assert "commented" in types
    assert "review_requested" in types


# ---------------------------------------------------------------------------
# Agent ↔ agent direct messaging (peer lane)
# ---------------------------------------------------------------------------

def _peer(client, ws, frm, to, text="can you take a look?", expects_reply=False):
    return client.post("/v1/a2a/messages", json={
        "network": ws["id"], "source": frm, "to": to, "text": text, "expects_reply": expects_reply,
    }, headers=_hdr(ws))


def test_peer_message_creates_dm_thread(client, workspace):
    _join(client, workspace, "alice")
    _join(client, workspace, "bob")
    r = _peer(client, workspace, "alice", "bob")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["from"] == "alice" and d["to"] == "bob"
    assert d["channel"] == "dm-alice~bob"          # order-independent name
    # the thread shows up in the DM list with both participants
    threads = client.get("/v1/a2a/messages", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["threads"]
    t = next(t for t in threads if t["channel"] == "dm-alice~bob")
    assert t["participants"] == ["alice", "bob"]
    assert t["lastFrom"] == "alice"


def test_peer_message_name_is_order_independent(client, workspace):
    _join(client, workspace, "alice")
    _join(client, workspace, "bob")
    a = _peer(client, workspace, "alice", "bob").json()["data"]["channel"]
    b = _peer(client, workspace, "bob", "alice").json()["data"]["channel"]
    assert a == b == "dm-alice~bob"   # same private thread both directions


def test_peer_thread_messages_in_order(client, workspace):
    _join(client, workspace, "alice")
    _join(client, workspace, "bob")
    _peer(client, workspace, "alice", "bob", text="first")
    _peer(client, workspace, "bob", "alice", text="second")
    msgs = client.get("/v1/a2a/messages", params={"network": workspace["id"], "channel": "dm-alice~bob"}, headers=_hdr(workspace)).json()["data"]["messages"]
    texts = [(m["from"], m["text"]) for m in msgs]
    assert ("alice", "first") in texts and ("bob", "second") in texts
    # leading @mention is stripped from the display text
    assert all(not m["text"].startswith("@") for m in msgs)


def test_peer_message_self_rejected(client, workspace):
    _join(client, workspace, "alice")
    r = _peer(client, workspace, "alice", "alice")
    assert r.status_code == 400


def test_peer_message_unknown_recipient_rejected(client, workspace):
    _join(client, workspace, "alice")
    r = _peer(client, workspace, "alice", "ghost")
    assert r.status_code == 400


def test_peer_consult_flag_carried(client, workspace):
    _join(client, workspace, "alice")
    _join(client, workspace, "bob")
    r = _peer(client, workspace, "alice", "bob", text="what DB did we pick?", expects_reply=True)
    assert r.json()["data"]["expectsReply"] is True


def test_agent_to_agent_task_without_channel_uses_dm_channel(client, workspace):
    """A consult/delegate from one agent to another with no channel routes the
    kick-off through their private DM channel (so the contractor is triggered)."""
    _join(client, workspace, "alice")
    _join(client, workspace, "bob")
    r = client.post("/v1/a2a/tasks", json={
        "network": workspace["id"], "source": "openagents:alice",
        "contractor": "bob", "text": "what's our DB choice?",
    }, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["channel"] == "dm-alice~bob"


def test_human_task_without_channel_stays_channelless(client, workspace):
    """A human delegator with no channel is unchanged (no DM channel invented)."""
    _join(client, workspace, "bob")
    r = client.post("/v1/a2a/tasks", json={
        "network": workspace["id"], "source": "human:you", "contractor": "bob", "text": "do x",
    }, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["channel"] is None


# ---------------------------------------------------------------------------
# Full-system journey — exercises every team-interaction feature end to end.
# In-process (TestClient + SQLite), so it verifies the real app without docker.
# ---------------------------------------------------------------------------

def test_full_team_journey(client, workspace):
    net = workspace["id"]
    for name in ("alice", "bob", "carol"):
        _join(client, workspace, name)
    ch = workspace["channel"]["name"]

    def post(path, body):
        return client.post(path, json={"network": net, **body}, headers=_hdr(workspace))

    # 1) alice delegates a task to bob (handoff)
    tid = post("/v1/a2a/tasks", {"source": "openagents:alice", "contractor": "bob",
                                 "text": "build login", "context_id": ch}).json()["data"]["id"]

    # 2) fan out a subtask to carol; parent rolls it up
    sub = post(f"/v1/a2a/tasks/{tid}/subtasks", {"source": "openagents:alice", "contractor": "carol",
                                                 "text": "write tests"}).json()["data"]
    assert sub["parentId"] == tid

    # 3) dependency: tid blocked by a new task
    blk = post("/v1/a2a/tasks", {"source": "openagents:alice", "contractor": "bob",
                                 "text": "provision db", "context_id": ch}).json()["data"]["id"]
    dep = post(f"/v1/a2a/tasks/{tid}/dependencies", {"blocked_by": blk, "action": "add"}).json()["data"]
    assert blk in dep["blockedBy"]

    # 4) progress + review loop (alice's delegation reviewed by carol)
    post(f"/v1/a2a/tasks/{tid}/status", {"state": "working"})
    post(f"/v1/a2a/tasks/{tid}/review/request", {"reviewer": "carol"})
    approved = post(f"/v1/a2a/tasks/{tid}/review/approve", {}).json()["data"]
    assert approved["review"]["state"] == "approved"

    # 5) comment + clarification round-trip
    post(f"/v1/a2a/tasks/{tid}/comments", {"author": "openagents:bob", "text": "done"})
    post(f"/v1/a2a/tasks/{tid}/clarification", {"action": "set", "question": "which provider?"})
    resolved = post(f"/v1/a2a/tasks/{tid}/clarification", {"action": "resolve", "answer": "Auth0"}).json()["data"]
    assert resolved["clarification"] is None

    # 6) soft delete + recycle bin + restore (on the blocker)
    assert post(f"/v1/a2a/tasks/{blk}/delete", {}).json()["data"]["deleted"] is True
    binned = client.get("/v1/a2a/tasks", params={"network": net, "deleted": "true"}, headers=_hdr(workspace)).json()["data"]["tasks"]
    assert blk in [t["id"] for t in binned]
    assert post(f"/v1/a2a/tasks/{blk}/restore", {}).json()["data"]["deleted"] is False

    # 7) timeline captured the journey
    events = client.get(f"/v1/a2a/tasks/{tid}", params={"network": net}, headers=_hdr(workspace)).json()["data"]["events"]
    types = {e["type"] for e in events}
    assert {"task_created", "status_changed", "review_requested", "review_approved",
            "commented", "dependency_added", "subtask_created"} <= types

    # 8) agent↔agent peer lane: plain DM + consult, consult flag surfaced
    post("/v1/a2a/messages", {"source": "alice", "to": "bob", "text": "hi"})
    post("/v1/a2a/messages", {"source": "alice", "to": "bob", "text": "which db?", "expects_reply": True})
    msgs = client.get("/v1/a2a/messages", params={"network": net, "channel": "dm-alice~bob"}, headers=_hdr(workspace)).json()["data"]["messages"]
    assert any(m["consult"] for m in msgs) and any(not m["consult"] for m in msgs)

    # 9) agent→agent consult with no channel auto-routes through the private DM
    consult_task = post("/v1/a2a/tasks", {"source": "openagents:alice", "contractor": "carol",
                                          "text": "quick question"}).json()["data"]
    assert consult_task["channel"] == "dm-alice~carol"


# ---------------------------------------------------------------------------
# Consult — synchronous ask-a-teammate (AG2 nested-chat analogue)
# ---------------------------------------------------------------------------

def test_consult_self_rejected(client, workspace):
    _join(client, workspace, "alice")
    r = client.post("/v1/a2a/consult", json={"network": workspace["id"], "source": "alice", "to": "alice", "question": "x"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_consult_unknown_teammate_rejected(client, workspace):
    _join(client, workspace, "alice")
    r = client.post("/v1/a2a/consult", json={"network": workspace["id"], "source": "alice", "to": "ghost", "question": "x"}, headers=_hdr(workspace))
    assert r.status_code == 400


def test_consult_times_out_and_posts_question(client, workspace):
    """With no live teammate, consult posts the question into the DM thread and
    returns answered=False after the wait — the question is delivered."""
    _join(client, workspace, "alice")
    _join(client, workspace, "bob")
    r = client.post("/v1/a2a/consult", json={"network": workspace["id"], "source": "alice", "to": "bob", "question": "which database did we pick?", "wait": 1}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["answered"] is False and d["from"] == "bob"
    msgs = client.get("/v1/a2a/messages", params={"network": workspace["id"], "channel": "dm-alice~bob"}, headers=_hdr(workspace)).json()["data"]["messages"]
    assert any("which database" in m["text"] for m in msgs)


def test_consult_skips_intermediate_status_message(client, workspace, db):
    """Regression: the teammate posts a 'thinking'/status message before the
    real chat answer. The ascending poll must step past the status and return
    the chat — not get stuck on the status and time out (the bug where the
    teammate answered in seconds but consult still reported a timeout)."""
    import time as _t
    from app.models import EventRecord
    _join(client, workspace, "alice")
    _join(client, workspace, "bob")
    future = int(_t.time() * 1000) + 60000
    for i, (ts, mt, content) in enumerate([
        (future, "status", "thinking..."),
        (future + 1, "chat", "@alice the IP limit is 60/min"),
    ]):
        db.add(EventRecord(
            id=f"csk{i}", network_id=workspace["id"], type="workspace.message.posted",
            source="openagents:bob", target="channel/dm-alice~bob",
            payload={"content": content, "message_type": mt}, metadata_={},
            timestamp=ts, visibility="channel",
        ))
    db.commit()
    r = client.post("/v1/a2a/consult", json={
        "network": workspace["id"], "source": "alice", "to": "bob",
        "question": "rate limit?", "wait": 20,
    }, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["answered"] is True, d
    assert "60/min" in d["answer"]


# ---------------------------------------------------------------------------
# Proactive kickoff — give a live agent a self-directed turn
# ---------------------------------------------------------------------------

def _kickoff_events(db, ws, agent):
    from sqlalchemy import select
    from app.models import EventRecord
    return db.execute(
        select(EventRecord).where(
            EventRecord.network_id == ws["id"],
            EventRecord.type == "workspace.message.posted",
            EventRecord.target == f"channel/kickoff:{agent}",
        )
    ).scalars().all()


def test_kickoff_targets_a_live_agent(client, workspace, db):
    _join(client, workspace, "frontend")
    r = client.post("/v1/a2a/agents/frontend/kickoff", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["kicked"] is True and d["agent"] == "frontend"
    # A directed kickoff message landed in the agent's private system channel,
    # targeting only that agent (so it bypasses the LLM router like a routine).
    ev = _kickoff_events(db, workspace, "frontend")
    assert ev, "kickoff message not posted"
    assert ev[-1].source == "system:kickoff"
    assert (ev[-1].metadata_ or {}).get("target_agents") == ["frontend"]


def test_kickoff_unknown_agent_404(client, workspace):
    r = client.post("/v1/a2a/agents/ghost/kickoff", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 404


def test_kickoff_digest_lists_open_tasks(client, workspace, db):
    _join(client, workspace, "pm")
    _join(client, workspace, "coder")
    _delegate(client, workspace, contractor="coder", text="Build the login form")
    r = client.post("/v1/a2a/agents/coder/kickoff", json={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["openTasks"] >= 1
    ev = _kickoff_events(db, workspace, "coder")
    assert any("Build the login form" in (e.payload or {}).get("content", "") for e in ev)
