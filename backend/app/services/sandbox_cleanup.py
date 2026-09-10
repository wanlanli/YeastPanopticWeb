"""Deletes expired anonymous-visitor sandbox projects -- see
SANDBOX_TTL_HOURS. No scheduler/cron process: this is swept lazily, called
from project list/create and once on startup, which is enough for a
low-traffic lab tool without adding another moving part."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DbSession

from app.config import SANDBOX_TTL_HOURS
from app.models.project import Project
from app.services.project_delete import delete_project_cascade


def sweep_expired_sandboxes(db: DbSession) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SANDBOX_TTL_HOURS)
    expired = (
        db.query(Project)
        .filter(Project.sandbox_session_id.isnot(None), Project.created_at < cutoff)
        .all()
    )
    for project in expired:
        delete_project_cascade(db, project)
