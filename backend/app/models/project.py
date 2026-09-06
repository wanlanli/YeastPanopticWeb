from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    series: Mapped[list["ImageSeries"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    quant_datasets: Mapped[list["QuantificationDataset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
