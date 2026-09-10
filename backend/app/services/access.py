from fastapi import HTTPException
from sqlalchemy.orm import Session as DbSession

from app.models.polygon import Polygon
from app.models.project import Project
from app.models.quantification import QuantificationDataset
from app.models.series import ImageSeries
from app.models.session import VisitorSession
from app.models.user import User


def check_project_access(
    project: Project, user: User | None, visitor_session: VisitorSession
) -> None:
    """Raise 404 (not 403 -- an unauthorized project's existence isn't
    revealed) unless `project` is world-readable, owned by `user`, or is
    this browser's own sandbox project."""
    if project.is_sample:
        return
    if user is not None and project.owner_id == user.id:
        return
    if project.sandbox_session_id and project.sandbox_session_id == visitor_session.id:
        return
    raise HTTPException(404, "Project not found")


def require_project(
    db: DbSession, project_id: int, user: User | None, visitor_session: VisitorSession
) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    check_project_access(project, user, visitor_session)
    return project


def require_series(
    db: DbSession, series_id: int, user: User | None, visitor_session: VisitorSession
) -> ImageSeries:
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    require_project(db, series.project_id, user, visitor_session)
    return series


def require_dataset(
    db: DbSession, dataset_id: int, user: User | None, visitor_session: VisitorSession
) -> QuantificationDataset:
    dataset = db.get(QuantificationDataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    require_project(db, dataset.project_id, user, visitor_session)
    return dataset


def require_polygon(
    db: DbSession, polygon_id: int, user: User | None, visitor_session: VisitorSession
) -> Polygon:
    polygon = db.get(Polygon, polygon_id)
    if not polygon:
        raise HTTPException(404, "Polygon not found")
    require_series(db, polygon.series_id, user, visitor_session)
    return polygon
