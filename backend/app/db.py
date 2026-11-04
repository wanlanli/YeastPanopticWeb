from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL, DB_MAX_OVERFLOW, DB_POOL_SIZE


class Base(DeclarativeBase):
    pass


def _build_engine():
    """SQLite (the default, a single file) and a real server need different
    tuning, so branch on the URL rather than using one config for both.

    SQLite: `check_same_thread=False` was already needed (FastAPI's
    threadpool means a session can be used from a different thread than it
    was created on); WAL mode is added on top of that so a writer (an
    upload, auto-segment accept, polygon edit, ...) no longer blocks every
    concurrent reader with "database is locked" -- the previous default
    (rollback-journal mode) serializes ALL access, readers included, behind
    the single writer. `busy_timeout` makes the rare remaining writer/writer
    conflict retry briefly instead of failing immediately.

    A real server (Postgres/MySQL/...): there's no "database is locked"
    problem to solve -- the server handles concurrent writers itself -- but
    a long-lived pooled connection can go stale (server-side idle timeout,
    restart). `pool_pre_ping` detects that and transparently reconnects
    instead of surfacing the error on the next query.
    """
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    return create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
    )


engine = _build_engine()
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
    _migrate_polygons_table()


def _table_columns(conn, table_name: str) -> set[str]:
    """Portable across SQLite/Postgres/etc, unlike the old
    `PRAGMA table_info(...)` (SQLite-only) this replaced."""
    return {col["name"] for col in inspect(conn).get_columns(table_name)}


def _migrate_projects_table() -> None:
    """`create_all` only creates missing tables, not new columns on an
    existing one -- there's no Alembic in this project, so patch the
    `projects` table in place for dbs created before user accounts/sandbox
    existed. Additive and idempotent: safe to run on every startup."""
    with engine.begin() as conn:
        existing_cols = _table_columns(conn, "projects")
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


def _migrate_polygons_table() -> None:
    """Additive, idempotent: adds `polygons.prediction_id`, for dbs created
    before per-frame auto-segmentation provenance (see
    app.models.prediction.FramePredictionRun) existed."""
    with engine.begin() as conn:
        existing_cols = _table_columns(conn, "polygons")
        if "prediction_id" not in existing_cols:
            conn.exec_driver_sql(
                "ALTER TABLE polygons ADD COLUMN prediction_id INTEGER"
            )
