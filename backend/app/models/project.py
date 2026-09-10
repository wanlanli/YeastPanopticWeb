from datetime import datetime, timezone

from sqlalchemy import Boolean, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    # Exactly one of these three describes who a project belongs to (see
    # app.services.access): a signed-in user's private project, an
    # anonymous visitor's ephemeral sandbox project (subject to
    # SANDBOX_TTL_HOURS cleanup), or a permanent world-readable sample.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sandbox_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True
    )
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def is_sandbox(self) -> bool:
        return self.sandbox_session_id is not None

    series: Mapped[list["ImageSeries"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    quant_datasets: Mapped[list["QuantificationDataset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
