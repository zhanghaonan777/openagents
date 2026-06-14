# -*- coding: utf-8 -*-
"""Conformance tests for the standard A2A protocol surface (routers/a2a_protocol)."""


def _hdr(ws):
    return {"X-Workspace-Token": ws["token"]}


def _join(client, ws, name):
    r = client.post("/v1/join", json={"agent_name": name, "network": ws["id"], "token": ws["token"]})
    assert r.status_code == 200, r.text


def _rpc(client, ws, agent, method, params, rid=1):
    return client.post(
        f"/a2a/{ws['id']}/{agent}",
        json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
        headers=_hdr(ws),
    )


def test_agent_card_at_well_known(client, workspace):
    _join(client, workspace, "coder")
    r = client.get(f"/a2a/{workspace['id']}/coder/.well-known/agent-card.json", headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["protocolVersion"] == "1.0"
    assert c["name"] == "coder"
    assert c["preferredTransport"] == "JSONRPC"
    assert c["url"].endswith(f"/a2a/{workspace['id']}/coder")
    assert c["capabilities"]["streaming"] is False
    assert "workspaceToken" in c["securitySchemes"]
    assert isinstance(c["skills"], list)


def test_message_send_get_cancel_roundtrip(client, workspace):
    _join(client, workspace, "coder")
    r = _rpc(client, workspace, "coder", "message/send", {
        "message": {"role": "user", "parts": [{"kind": "text", "text": "Build the login form"}], "messageId": "m1"}
    })
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert res["kind"] == "task"
    assert res["status"]["state"] == "submitted"
    assert res["history"][0]["parts"][0]["text"] == "Build the login form"
    tid = res["id"]

    g = _rpc(client, workspace, "coder", "tasks/get", {"id": tid})
    assert g.json()["result"]["id"] == tid

    lst = _rpc(client, workspace, "coder", "tasks/list", {})
    assert any(t["id"] == tid for t in lst.json()["result"]["tasks"])

    c = _rpc(client, workspace, "coder", "tasks/cancel", {"id": tid})
    assert c.json()["result"]["status"]["state"] == "canceled"
    # already terminal → not cancelable
    c2 = _rpc(client, workspace, "coder", "tasks/cancel", {"id": tid})
    assert c2.json()["error"]["code"] == -32002


def test_jsonrpc_errors(client, workspace):
    _join(client, workspace, "coder")
    assert _rpc(client, workspace, "coder", "bogus/method", {}).json()["error"]["code"] == -32601
    assert _rpc(client, workspace, "coder", "tasks/get", {"id": "nope"}).json()["error"]["code"] == -32001
    assert _rpc(client, workspace, "coder", "message/send", {"message": {"role": "user", "parts": []}}).json()["error"]["code"] == -32602


def test_unknown_agent_and_auth(client, workspace):
    _join(client, workspace, "coder")
    assert _rpc(client, workspace, "ghost", "tasks/list", {}).status_code == 404
    bad = client.post(
        f"/a2a/{workspace['id']}/coder",
        json={"jsonrpc": "2.0", "id": 1, "method": "tasks/list", "params": {}},
        headers={"X-Workspace-Token": "wrong"},
    )
    assert bad.status_code == 401
