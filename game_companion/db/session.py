"""Engine/session factories."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    kwargs: dict = {}
    is_sqlite = url.startswith("sqlite")
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, echo=echo, **kwargs)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _record):  # pragma: no cover - driver glue
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
