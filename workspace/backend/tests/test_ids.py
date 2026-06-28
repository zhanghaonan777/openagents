# -*- coding: utf-8 -*-
"""Tests for the short agent code (the visible 编号 badge)."""
from app.ids import agent_code


def test_agent_code_is_stable_4hex():
    c = agent_code("ws-1", "backend-developer")
    assert c == agent_code("ws-1", "backend-developer")          # deterministic / stable
    assert len(c) == 4 and all(ch in "0123456789abcdef" for ch in c)


def test_agent_code_distinguishes_agents_and_workspaces():
    base = agent_code("ws-1", "backend-developer")
    assert agent_code("ws-1", "frontend-developer") != base       # different agent
    assert agent_code("ws-2", "backend-developer") != base        # same name, different workspace
