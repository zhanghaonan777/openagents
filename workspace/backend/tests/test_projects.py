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


def test_project_detail_scopes_threads_and_team(client, workspace):
    pid = _create_project(client, workspace).json()["data"]["id"]
    # create a thread under the project with two agents
    ev = client.post("/v1/events", json={
        "network": workspace["id"], "type": "network.channel.create",
        "source": "human:user", "target": "core",
        "payload": {"title": "t1", "project_id": pid, "participants": ["alice", "bob"]},
    }, headers=_hdr(workspace))
    assert ev.status_code == 200, ev.text
    d = client.get(f"/v1/projects/{pid}", params={"network": workspace["id"]}, headers=_hdr(workspace)).json()["data"]
    assert d["threadCount"] == 1
    assert set(d["team"]) == {"alice", "bob"}
    assert len(d["threads"]) == 1


def test_project_create_requires_name(client, workspace):
    r = client.post("/v1/projects", json={"network": workspace["id"], "name": "  "}, headers=_hdr(workspace))
    assert r.json()["code"] != 0


def test_unknown_project_404(client, workspace):
    r = client.get("/v1/projects/00000000-0000-0000-0000-000000000000",
                   params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 404
