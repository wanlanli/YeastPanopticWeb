from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class QuantificationDataset(Base):
    __tablename__ = "quantification_datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    # Set when this dataset was computed from a series' own segmentation
    # (see app.services.quantification_compute); null for manual uploads.
    series_id: Mapped[int | None] = mapped_column(ForeignKey("image_series.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    # "features" | "tracking"
    kind: Mapped[str] = mapped_column(String(16))
    file_path: Mapped[str] = mapped_column(String(1024))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    project: Mapped["Project"] = relationship(back_populates="quant_datasets")
