# -*- coding: utf-8 -*-
"""Tests for the role catalog search endpoint."""


def _hdr(ws):
    return {"X-Workspace-Token": ws["token"]}


def test_roles_lists_catalog_and_categories(client, workspace):
    r = client.get("/v1/roles", params={"network": workspace["id"]}, headers=_hdr(workspace))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert len(d["categories"]) == 10
    assert 0 < len(d["roles"]) <= 30          # default limit
    assert {"id", "name", "cat", "tagline", "skills"} <= set(d["roles"][0])


def test_roles_free_text_search_ranks_name_match(client, workspace):
    r = client.get("/v1/roles", params={"network": workspace["id"], "q": "backend"}, headers=_hdr(workspace))
    roles = r.json()["data"]["roles"]
    assert any(x["id"] == "backend-developer" for x in roles)


def test_roles_category_filter(client, workspace):
    r = client.get("/v1/roles", params={"network": workspace["id"], "category": "core-development", "limit": 154}, headers=_hdr(workspace))
    roles = r.json()["data"]["roles"]
    assert roles and all(x["cat"] == "core-development" for x in roles)


def test_roles_skill_filter(client, workspace):
    r = client.get("/v1/roles", params={"network": workspace["id"], "skill": "GraphQL"}, headers=_hdr(workspace))
    roles = r.json()["data"]["roles"]
    assert roles and all(any("graphql" in s.lower() for s in x["skills"]) for x in roles)


def test_roles_requires_auth(client, workspace):
    r = client.get("/v1/roles", params={"network": workspace["id"]})   # no token
    assert r.status_code == 401
