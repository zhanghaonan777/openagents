# -*- coding: utf-8 -*-
"""Projects — goal-scoped grouping of threads inside a workspace (project mode).

Phase 2: the Project entity + CRUD + thread/team scoping. PM-driven recruitment
and per-project agent instances land in a later phase; for now a project's "team"
is derived from the agents participating in its threads.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Channel, Project
from app.response import ResponseCode, json_response, success_response
from app.routers.network import _resolve_workspace, _verify_workspace_access

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def _serialize(p: Project, thread_count: int = 0, team: Optional[list] = None) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "goal": p.goal,
        "status": p.status,
        "createdBy": p.created_by,
        "createdAt": p.created_at.isoformat() if p.created_at else None,
        "archivedAt": p.archived_at.isoformat() if p.archived_at else None,
        "threadCount": thread_count,
        "team": team or [],
    }


class CreateProjectRequest(BaseModel):
    network: str
    name: str
    goal: Optional[str] = None
    created_by: Optional[str] = None


def _auth(db, network, token, authorization):
    """Resolve + verify; returns (workspace, error_response)."""
    workspace = _resolve_workspace(db, network)
    if not workspace:
        return None, json_response(ResponseCode.NOT_FOUND, "Network not found")
    if not _verify_workspace_access(workspace, token, authorization):
        return None, json_response(ResponseCode.UNAUTHORIZED, "Invalid credentials")
    return workspace, None


@router.post("")
def create_project(
    body: CreateProjectRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace, err = _auth(db, body.network, x_workspace_token, authorization)
    if err:
        return err
    name = (body.name or "").strip()
    if not name:
        return json_response(ResponseCode.BAD_REQUEST, "Project name required")
    p = Project(
        workspace_id=str(workspace.id),
        name=name,
        goal=body.goal,
        created_by=body.created_by,
        status="active",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return success_response(_serialize(p))


@router.get("")
def list_projects(
    network: str,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace, err = _auth(db, network, x_workspace_token, authorization)
    if err:
        return err
    rows = db.execute(
        select(Project).where(Project.workspace_id == str(workspace.id))
        .order_by(Project.created_at.desc())
    ).scalars().all()
    out = []
    for p in rows:
        tc = db.execute(
            select(func.count()).select_from(Channel).where(Channel.project_id == p.id)
        ).scalar() or 0
        out.append(_serialize(p, tc))
    return success_response({"projects": out})


@router.get("/{project_id}")
def get_project(
    project_id: str,
    network: str,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    workspace, err = _auth(db, network, x_workspace_token, authorization)
    if err:
        return err
    p = db.get(Project, project_id)
    if not p or str(p.workspace_id) != str(workspace.id):
        return json_response(ResponseCode.NOT_FOUND, "Project not found")
    threads = db.execute(
        select(Channel).where(Channel.project_id == p.id, Channel.status != "deleted")
        .order_by(Channel.last_event_at.desc().nullslast())
    ).scalars().all()
    # Derived team: the agents participating in this project's threads.
    team = sorted({m.agent_name for ch in threads for m in (ch.participants or [])})
    data = _serialize(p, len(threads), team)
    data["threads"] = [
        {"name": ch.name, "title": ch.title, "lastEventAt": ch.last_event_at}
        for ch in threads
    ]
    return success_response(data)
