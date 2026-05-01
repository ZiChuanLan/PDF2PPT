"""SQLite database setup and session management."""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_engine = None
_SessionLocal = None


def _get_database_url() -> str:
    """Resolve SQLite database URL from settings."""
    settings = get_settings()
    db_path = getattr(settings, "sqlite_path", None) or "data/pdf2ppt.db"
    # Resolve relative paths under the api/ directory
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.path.dirname(__file__), "..", db_path)
    db_path = os.path.abspath(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return f"sqlite:///{db_path}"


def get_engine():
    """Get or create the SQLAlchemy engine singleton."""
    global _engine
    if _engine is None:
        url = _get_database_url()
        logger.info("Connecting to database: %s", url)
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        # Enable WAL mode for better concurrency
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return _engine


def get_session_factory():
    """Get or create the session factory singleton."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables."""
    from app.models.user import Base  # noqa: F811

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")


def reset_db() -> None:
    """Reset database singletons (used by tests)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
