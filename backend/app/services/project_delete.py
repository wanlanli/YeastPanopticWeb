from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from app.models.project import Project
from app.models.quantification import QuantificationDataset
from app.models.series import ImageSeries
from app.services.series_delete import delete_series_cascade


def delete_project_cascade(db: DbSession, project: Project) -> None:
    """Deletes every series under `project` (and their files, via
    delete_series_cascade), any project-level quantification dataset not
    tied to a series (manual uploads), then the project row itself. Used
    both for user-initiated project deletion and sandbox TTL cleanup."""
    for series in db.query(ImageSeries).filter(ImageSeries.project_id == project.id).all():
        delete_series_cascade(db, series)

    orphan_datasets = (
        db.query(QuantificationDataset)
        .filter(
            QuantificationDataset.project_id == project.id,
            QuantificationDataset.series_id.is_(None),
        )
        .all()
    )
    for dataset in orphan_datasets:
        Path(dataset.file_path).unlink(missing_ok=True)
        db.delete(dataset)

    db.delete(project)
    db.commit()
