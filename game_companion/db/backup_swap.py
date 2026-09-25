"""Live database swap used by restore: dispose engine, replace file, reconnect.

SQLite only (the default for this app). The engine is recreated on
``app.state`` so a restore needs no service restart.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from game_companion.db.session import create_db_engine, create_session_factory


def swap_live_database(app, staged_db: Path, staging_dir: Path) -> None:
    settings = app.state.settings
    live_db = Path(settings.resolved_database_url.removeprefix("sqlite:///"))
    if not str(live_db).startswith(str(settings.resolved_data_dir)):
        raise ValueError("refusing to restore: database lives outside the data dir")

    old_engine = app.state.engine
    old_engine.dispose()

    for suffix in ("", "-wal", "-shm"):
        target = Path(str(live_db) + suffix)
        if target.exists():
            target.unlink()

    live_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staged_db, live_db)

    staged_personas = staging_dir / "personas"
    if staged_personas.is_dir():
        live_personas = settings.resolved_data_dir / "personas"
        if live_personas.exists():
            shutil.rmtree(live_personas)
        shutil.copytree(staged_personas, live_personas)

    engine = create_db_engine(settings.resolved_database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
