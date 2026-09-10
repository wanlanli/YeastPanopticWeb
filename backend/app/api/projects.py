from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_visitor_session
from app.db import get_db
from app.models.project import Project
from app.models.session import VisitorSession
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut
from app.services import access
from app.services.project_delete import delete_project_cascade
from app.services.sandbox_cleanup import sweep_expired_sandboxes

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    sweep_expired_sandboxes(db)
    visible = [Project.is_sample.is_(True)]
    if user is not None:
        visible.append(Project.owner_id == user.id)
    else:
        visible.append(Project.sandbox_session_id == visitor_session.id)
    return (
        db.query(Project)
        .filter(or_(*visible))
        .order_by(Project.created_at.desc())
        .all()
    )


@router.post("", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    sweep_expired_sandboxes(db)
    project = Project(
        name=body.name,
        owner_id=user.id if user is not None else None,
        sandbox_session_id=visitor_session.id if user is None else None,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    return access.require_project(db, project_id, user, visitor_session)


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    project = access.require_project(db, project_id, user, visitor_session)
    if project.is_sample:
        raise HTTPException(403, "The sample project can't be deleted")
    delete_project_cascade(db, project)
    return {"ok": True}
