from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.db.models import Base

_DEFAULT_SQLITE_URL = "sqlite:///data/macromind.db"
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_db_initialized = False


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return url


def _validate_database_driver(url: str) -> None:
    if url.startswith("postgresql+psycopg://") and importlib.util.find_spec("psycopg") is None:
        raise RuntimeError(
            "DATABASE_URL está configurada para PostgreSQL, mas o driver 'psycopg' "
            "não está instalado. Rode 'uv sync' antes de iniciar o bot."
        )


def get_database_url() -> str:
    settings = get_settings()
    url = _normalize_database_url(settings.database_url or _DEFAULT_SQLITE_URL)

    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    _validate_database_driver(url)
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_database_url()
        connect_args: dict[str, object]
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        elif url.startswith("postgresql"):
            connect_args = {"connect_timeout": 5}
        else:
            connect_args = {}
        _engine = create_engine(
            url,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def _ensure_postgres_compat_schema(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    statements = (
        "ALTER TABLE IF EXISTS users ALTER COLUMN telegram_id TYPE BIGINT",
        "ALTER TABLE IF EXISTS meals ALTER COLUMN source_message_id TYPE BIGINT",
    )

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def init_db() -> None:
    global _db_initialized
    if _db_initialized and _engine is not None and _session_factory is not None:
        return
    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_postgres_compat_schema(engine)
    _db_initialized = True


@contextmanager
def session_scope() -> Iterator[Session]:
    init_db()
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
