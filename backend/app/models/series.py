from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ImageSeries(Base):
    __tablename__ = "image_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    # "folder" | "multipage_tiff" | "upload"
    source_type: Mapped[str] = mapped_column(String(32))
    # Absolute path to the registered folder, tiff file, or upload directory.
    path: Mapped[str] = mapped_column(String(1024))
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    dtype: Mapped[str] = mapped_column(String(32), default="uint8")
    channels: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    project: Mapped["Project"] = relationship(back_populates="series")
    polygons: Mapped[list["Polygon"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
