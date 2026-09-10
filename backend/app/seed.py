"""Seeds a default sample project from local test images on first run, so
there's something to explore immediately after cloning/starting the app.
Idempotent (checked by project name) and a no-op if the sample data isn't
present (e.g. in a deployment that doesn't ship it) -- see `sample_data/`,
which is gitignored, at the repo root."""

from __future__ import annotations

import logging

from app.config import SAMPLE_DATA_DIR
from app.db import SessionLocal
from app.models.project import Project
from app.models.series import ImageSeries
from app.services import image_io

logger = logging.getLogger(__name__)

SAMPLE_PROJECT_NAME = "Sample Project"
SAMPLE_SERIES_NAME = "yeast_demo"


def seed_sample_project() -> None:
    sample_dir = SAMPLE_DATA_DIR / SAMPLE_SERIES_NAME
    if not sample_dir.is_dir():
        return

    db = SessionLocal()
    try:
        if db.query(Project).filter(Project.name == SAMPLE_PROJECT_NAME).first():
            return

        try:
            meta = image_io.probe_series("folder", str(sample_dir))
        except Exception:
            logger.exception("Could not probe sample data at %s; skipping seed", sample_dir)
            return

        project = Project(name=SAMPLE_PROJECT_NAME, is_sample=True)
        db.add(project)
        db.flush()

        db.add(
            ImageSeries(
                project_id=project.id,
                name=SAMPLE_SERIES_NAME,
                source_type="folder",
                path=str(sample_dir),
                frame_count=meta.frame_count,
                width=meta.width,
                height=meta.height,
                dtype=meta.dtype,
                channels=meta.channels,
                channel_count=meta.channel_count,
                dic_channel_index=meta.dic_channel_index,
            )
        )
        db.commit()
        logger.info("Seeded %r with %d frame(s) from %s", SAMPLE_PROJECT_NAME, meta.frame_count, sample_dir)
    finally:
        db.close()
