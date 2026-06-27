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
from app.models import Channel, Project, ProjectAgent
from app.response import ResponseCode, json_response, success_response
from app.routers.network import _resolve_workspace, _verify_workspace_access

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def _team(db: Session, project_id: str) -> list:
    """The project's recruited team (active ProjectAgents)."""
    rows = db.execute(
        select(ProjectAgent).where(
            ProjectAgent.project_id == project_id,
            ProjectAgent.status == "active",
        ).order_by(ProjectAgent.created_at.asc())
    ).scalars().all()
    return [
        {"agentName": a.agent_name, "roleId": a.role_id, "workingDir": a.working_dir}
        for a in rows
    ]


def _team_size(db: Session, project_id: str) -> int:
    return db.execute(
        select(func.count()).select_from(ProjectAgent).where(
            ProjectAgent.project_id == project_id, ProjectAgent.status == "active",
        )
    ).scalar() or 0


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
        out.append(_serialize(p, tc, _team(db, p.id)))
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
    data = _serialize(p, len(threads), _team(db, p.id))
    data["threads"] = [
        {"name": ch.name, "title": ch.title, "lastEventAt": ch.last_event_at}
        for ch in threads
    ]
    return success_response(data)


class RecruitRequest(BaseModel):
    network: str
    role_id: str                      # catalog role id, e.g. "backend-developer"
    agent_name: Optional[str] = None  # handle in this project; defaults to role_id
    working_dir: Optional[str] = None


@router.post("/{project_id}/recruit")
def recruit_agent(
    project_id: str,
    body: RecruitRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Recruit a catalog role into the project (the project's own team member).
    Launching its runtime with an isolated working dir is the daemon's job."""
    workspace, err = _auth(db, body.network, x_workspace_token, authorization)
    if err:
        return err
    p = db.get(Project, project_id)
    if not p or str(p.workspace_id) != str(workspace.id):
        return json_response(ResponseCode.NOT_FOUND, "Project not found")
    role_id = (body.role_id or "").strip()
    if not role_id:
        return json_response(ResponseCode.BAD_REQUEST, "role_id required")
    agent_name = (body.agent_name or role_id).strip()
    existing = db.execute(
        select(ProjectAgent).where(
            ProjectAgent.project_id == project_id, ProjectAgent.agent_name == agent_name,
        )
    ).scalar_one_or_none()
    if existing:
        if existing.status != "active":
            existing.status = "active"
            db.commit()
            return success_response({"recruited": True, "agentName": agent_name, "reactivated": True})
        return json_response(ResponseCode.BAD_REQUEST, f"'{agent_name}' is already on this project")
    pa = ProjectAgent(project_id=project_id, role_id=role_id, agent_name=agent_name, working_dir=body.working_dir)
    db.add(pa)
    db.commit()
    return success_response({"recruited": True, "agentName": agent_name, "team": _team(db, project_id)})


class RemoveAgentRequest(BaseModel):
    network: str
    agent_name: str


@router.post("/{project_id}/agents/remove")
def remove_agent(
    project_id: str,
    body: RemoveAgentRequest,
    db: Session = Depends(get_db),
    x_workspace_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Remove a recruited agent from the project (soft — status=removed)."""
    workspace, err = _auth(db, body.network, x_workspace_token, authorization)
    if err:
        return err
    pa = db.execute(
        select(ProjectAgent).where(
            ProjectAgent.project_id == project_id, ProjectAgent.agent_name == body.agent_name,
        )
    ).scalar_one_or_none()
    if not pa:
        return json_response(ResponseCode.NOT_FOUND, "Agent not on this project")
    pa.status = "removed"
    db.commit()
    return success_response({"removed": True, "agentName": body.agent_name})
