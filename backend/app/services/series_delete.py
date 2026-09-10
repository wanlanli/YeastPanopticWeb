import shutil
from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from app.config import UPLOAD_DIR
from app.models.quantification import QuantificationDataset
from app.models.series import ImageSeries


def delete_series_cascade(db: DbSession, series: ImageSeries) -> None:
    """Deletes a series' quantification datasets (row + file on disk), its
    own managed upload directory if it has one, and the series row itself
    (cascades to polygons). Commits. Shared by the series-delete endpoint
    and project/sandbox deletion so file cleanup only lives in one place."""
    datasets = (
        db.query(QuantificationDataset)
        .filter(QuantificationDataset.series_id == series.id)
        .all()
    )
    for dataset in datasets:
        Path(dataset.file_path).unlink(missing_ok=True)
        db.delete(dataset)

    # Only ever remove files we manage ourselves (this series' own upload
    # directory). register-path can point at ANY existing folder on disk
    # (e.g. sample_data) -- deleting the series must never touch that.
    try:
        upload_root = UPLOAD_DIR.resolve()
        relative = Path(series.path).resolve().relative_to(upload_root)
        shutil.rmtree(upload_root / relative.parts[0], ignore_errors=True)
    except (OSError, ValueError):
        pass  # not one of our managed uploads (or already gone) -- leave it

    db.delete(series)
    db.commit()
