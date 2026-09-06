from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Polygon(Base):
    __tablename__ = "polygons"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("image_series.id"))
    frame_index: Mapped[int] = mapped_column(Integer)
    # list of [x, y] pairs, image pixel coordinates
    points: Mapped[list] = mapped_column(JSON)
    label: Mapped[str] = mapped_column(String(128), default="")
    # "manual" | "model"
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    series: Mapped["ImageSeries"] = relationship(back_populates="polygons")
