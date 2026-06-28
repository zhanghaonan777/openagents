# -*- coding: utf-8 -*-
"""Tests for the timeline (decision milestones). No LLM key in tests, so capture
exercises the heuristic fallback (last agent message → decision record)."""


def _hdr(ws):
    return {"X-Workspace-Token": ws["token"]}


def _post(client, ws, channel, source, content):
    return client.post("/v1/events", json={
        "network": ws["id"], "type": "workspace.message.posted",
        "source": source, "target": f"channel/{channel}",
        "payload": {"content": content, "sender_type": "agent" if source.startswith("openagents:") else "human"},
    }, headers=_hdr(ws))


def _make_channel(client, ws):
    ev = client.post("/v1/events", json={
        "network": ws["id"], "type": "network.channel.create",
        "source": "human:user", "target": "core",
        "payload": {"title": "Auth decision", "participants": ["alice", "bob"]},
    }, headers=_hdr(ws))
    assert ev.status_code == 200, ev.text
    # resolve the channel name from discover
    d = client.get("/v1/discover", params={"network": ws["id"]}, headers=_hdr(ws)).json()["data"]
    ch = next(c for c in d["channels"] if c.get("title") == "Auth decision")
    return ch["address"].replace("channel/", "")


def test_capture_and_list_milestone(client, workspace):
    ch = _make_channel(client, workspace)
    _post(client, workspace, ch, "human:user", "Which auth approach?")
    _post(client, workspace, ch, "openagents:alice", "I prefer sessions.")
    _post(client, workspace, ch, "openagents:bob", "Decision: stateful session cookie, 30-day sliding.")

    r = client.post("/v1/timeline/capture", json={"network": workspace["id"], "channel": ch}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    m = r.json()["data"]
    assert m["title"]
    assert "session" in (m["summary"] or "").lower()          # heuristic: last agent message
    assert set(["alice", "bob"]).issubset(set(m["participants"]))

    lr = client.get("/v1/timeline", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert any(x["id"] == m["id"] for x in lr.json()["data"]["milestones"])


def test_record_milestone_dedup_by_summary(client, workspace):
    body = {"network": workspace["id"], "kind": "decision", "title": "Auth approach",
            "summary": "short access JWT + stateful refresh", "participants": ["pm"]}
    r1 = client.post("/v1/timeline/milestones", json=body, headers=_hdr(workspace))
    assert r1.status_code == 200, r1.text
    id1 = r1.json()["data"]["id"]
    # identical summary within 10 min → dedup (no duplicate)
    r2 = client.post("/v1/timeline/milestones", json=body, headers=_hdr(workspace))
    assert r2.json()["data"]["id"] == id1
    # a genuinely NEW conclusion (different summary) → a NEW milestone, never dropped
    r3 = client.post("/v1/timeline/milestones", json={**body, "summary": "revised: stateful session cookie"}, headers=_hdr(workspace))
    assert r3.json()["data"]["id"] != id1
    lr = client.get("/v1/timeline", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert len(lr.json()["data"]["milestones"]) == 2


def test_capture_empty_thread_400(client, workspace):
    ch = _make_channel(client, workspace)
    r = client.post("/v1/timeline/capture", json={"network": workspace["id"], "channel": ch}, headers=_hdr(workspace))
    assert r.status_code == 400
