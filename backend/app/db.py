from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
    _migrate_projects_table()


def _migrate_projects_table() -> None:
    """`create_all` only creates missing tables, not new columns on an
    existing one -- there's no Alembic in this project, so patch the
    `projects` table in place for dbs created before user accounts/sandbox
    existed. Additive and idempotent: safe to run on every startup."""
    with engine.begin() as conn:
        existing_cols = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(projects)")
        }
        added_any = False
        if "owner_id" not in existing_cols:
            conn.exec_driver_sql("ALTER TABLE projects ADD COLUMN owner_id INTEGER")
            added_any = True
        if "sandbox_session_id" not in existing_cols:
            conn.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN sandbox_session_id VARCHAR(64)"
            )
            added_any = True
        if "is_sample" not in existing_cols:
            conn.exec_driver_sql(
                "ALTER TABLE projects ADD COLUMN is_sample BOOLEAN DEFAULT 0"
            )
            added_any = True
        if added_any:
            # Every project that existed before ownership was enforced
            # becomes world-visible, like the seeded Sample Project -- so
            # nothing already in the db is hidden or swept up by the
            # sandbox TTL cleaner once this migration lands.
            conn.exec_driver_sql(
                "UPDATE projects SET is_sample = 1 "
                "WHERE owner_id IS NULL AND sandbox_session_id IS NULL"
            )
