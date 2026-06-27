# -*- coding: utf-8 -*-
"""Tests for the Project entity + thread/team scoping."""


def _hdr(ws):
    return {"X-Workspace-Token": ws["token"]}


def _create_project(client, ws, name="Login revamp", goal="add remember-me"):
    return client.post("/v1/projects", json={"network": ws["id"], "name": name, "goal": goal}, headers=_hdr(ws))


def test_create_and_list_project(client, workspace):
    r = _create_project(client, workspace)
    assert r.status_code == 200, r.text
    p = r.json()["data"]
    assert p["status"] == "active" and p["name"] == "Login revamp" and p["threadCount"] == 0
    pid = p["id"]
    lr = client.get("/v1/projects", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert any(x["id"] == pid for x in lr.json()["data"]["projects"])


def test_project_detail_scopes_threads(client, workspace):
    pid = _create_project(client, workspace).json()["data"]["id"]
    ev = client.post("/v1/events", json={
        "network": workspace["id"], "type": "network.channel.create",
        "source": "human:user", "target": "core",
        "payload": {"title": "t1", "project_id": pid, "participants": ["alice", "bob"]},
    }, headers=_hdr(workspace))
    assert ev.status_code == 200, ev.text
    d = client.get(f"/v1/projects/{pid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert d["threadCount"] == 1
    assert len(d["threads"]) == 1


def test_discover_surfaces_channel_project_id(client, workspace):
    """The discover endpoint must carry each channel's project_id so the thread
    list can filter by the active project (project-mode-design §4)."""
    pid = _create_project(client, workspace).json()["data"]["id"]
    client.post("/v1/events", json={
        "network": workspace["id"], "type": "network.channel.create",
        "source": "human:user", "target": "core",
        "payload": {"title": "scoped", "project_id": pid, "participants": ["alice"]},
    }, headers=_hdr(workspace))
    client.post("/v1/events", json={
        "network": workspace["id"], "type": "network.channel.create",
        "source": "human:user", "target": "core",
        "payload": {"title": "unscoped", "participants": ["alice"]},
    }, headers=_hdr(workspace))
    chans = client.get("/v1/discover", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]["channels"]
    by_title = {c["title"]: c for c in chans}
    assert by_title["scoped"]["project_id"] == pid
    assert by_title["unscoped"]["project_id"] is None


def test_project_recruit_and_remove(client, workspace):
    pid = _create_project(client, workspace).json()["data"]["id"]
    # recruit two roles
    for rid in ("backend-developer", "frontend-developer"):
        r = client.post(f"/v1/projects/{pid}/recruit", json={"network": workspace["id"], "role_id": rid}, headers=_hdr(workspace))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["recruited"] is True
    # team reflects them (isolated to THIS project)
    d = client.get(f"/v1/projects/{pid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert {m["agentName"] for m in d["team"]} == {"backend-developer", "frontend-developer"}
    # duplicate recruit rejected
    dup = client.post(f"/v1/projects/{pid}/recruit", json={"network": workspace["id"], "role_id": "backend-developer"}, headers=_hdr(workspace))
    assert dup.json()["code"] != 0
    # a SECOND project has its own (empty) team — isolation
    pid2 = _create_project(client, workspace, name="Other").json()["data"]["id"]
    d2 = client.get(f"/v1/projects/{pid2}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert d2["team"] == []
    # remove one
    rm = client.post(f"/v1/projects/{pid}/agents/remove", json={"network": workspace["id"], "agent_name": "backend-developer"}, headers=_hdr(workspace))
    assert rm.status_code == 200
    d3 = client.get(f"/v1/projects/{pid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert {m["agentName"] for m in d3["team"]} == {"frontend-developer"}


def test_project_create_requires_name(client, workspace):
    r = client.post("/v1/projects", json={"network": workspace["id"], "name": "  "}, headers=_hdr(workspace))
    assert r.json()["code"] != 0


def test_unknown_project_404(client, workspace):
    r = client.get("/v1/projects/00000000-0000-0000-0000-000000000000",
                   params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 404
