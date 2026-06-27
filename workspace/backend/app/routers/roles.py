# -*- coding: utf-8 -*-
"""Role catalog — read-only search over the role hiring library.

The data (154 roles, 10 categories) is generated from
VoltAgent/awesome-claude-code-subagents via frontend/scripts/gen-roles.py and
mirrored into app/data/roles.json. Serving it here lets the PM recruiter agent
(and the project UI) query the catalog by goal/skill instead of being handed all
154 roles at once.
"""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.response import ResponseCode, json_response, success_response
from app.routers.network import _resolve_workspace, _verify_workspace_access

router = APIRouter(prefix="/v1", tags=["roles"])

_ROLES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "roles.json")
with open(_ROLES_PATH, encoding="utf-8") as _f:
    _ROLES = json.load(_f)
_CATEGORIES = sorted({r["cat"] for r in _ROLES})

# All catalog role ids (e.g. "backend-developer"). Used to default a member's
# role_id from its agent name when an explicit role_id wasn't supplied on join.
KNOWN_ROLE_IDS = frozenset(r["id"] for r in _ROLES)


def _score(role: dict, q: str) -> int:
    """Relevance of a role to free-text query q (higher = better, 0 = no match)."""
    if q in role["id"].lower() or q in role["name"].lower():
        return 3
    if q in role["tagline"].lower():
        return 2
    if any(q in s.lower() for s in role["skills"]):
        return 1
    return 0


@router.get("/roles")
def list_roles(
    network: str,
    q: Optional[str] = None,
    category: Optional[str] = None,
    skill: Optional[str] = None,
    limit: int = Query(30, ge=1, le=154),
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Search the role hiring catalog. Filters by free-text ``q`` (id/name/tagline/
    skill), ``category``, and a specific ``skill``; returns ranked summaries plus
    the category list. Read-only; the data is a static org-level library."""
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, x_workspace_token, authorization):
        return json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")

    ql = (q or "").strip().lower()
    sk = (skill or "").strip().lower()
    rows = []
    for r in _ROLES:
        if category and r["cat"] != category:
            continue
        if sk and not any(sk in s.lower() for s in r["skills"]):
            continue
        if ql and _score(r, ql) == 0:
            continue
        rows.append(r)
    if ql:
        rows.sort(key=lambda r: _score(r, ql), reverse=True)
    rows = rows[:limit]
    return success_response({
        "total": len(rows),
        "categories": _CATEGORIES,
        "roles": [
            {
                "id": r["id"], "name": r["name"], "cat": r["cat"],
                "model": r["model"], "tagline": r["tagline"], "skills": r["skills"],
            }
            for r in rows
        ],
    })
