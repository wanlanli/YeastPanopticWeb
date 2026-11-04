from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FramePredictionRun(Base):
    """Provenance for one accepted auto-segmentation run: which model
    service and post-process thresholds produced the `Polygon` rows that
    reference it via `Polygon.prediction_id`.

    Written once, when the user accepts a preview (see the
    `.../predict-frame/accept` endpoint in app.api.annotations) -- the cheap
    preview/refine loop a user goes through while adjusting thresholds
    beforehand never touches the database, only the segmentation service's
    own short-lived in-memory candidate cache (keyed by `result_id`, see
    app.services.segmentation.base.AutoSegmentationModel.refine_frame)."""

    __tablename__ = "frame_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("image_series.id"))
    frame_index: Mapped[int] = mapped_column(Integer)
    # The segmentation service's own cache key for the run this came from.
    # Not relied on for anything after the fact -- that cache is in-memory
    # and short-lived -- just recorded for debugging/reproducibility.
    result_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str] = mapped_column(String(128), default="panoptic")
    score_threshold: Mapped[float] = mapped_column(Float)
    instance_threshold: Mapped[float] = mapped_column(Float)
    area_threshold: Mapped[int] = mapped_column(Integer)
    hole_area_threshold: Mapped[int] = mapped_column(Integer, default=1000)
    keep_border: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    series: Mapped["ImageSeries"] = relationship(back_populates="predictions")
    polygons: Mapped[list["Polygon"]] = relationship(back_populates="prediction")
