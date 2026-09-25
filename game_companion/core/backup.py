"""Backup/restore of the local data dir (SQLite DB + personas).

Exports are left alone (regenerable); backups live under
``<data_dir>/backups/``. Restore is staged to a temp dir and swapped into
place by the caller (the API route swaps the live engine; the CLI exits).
"""

from __future__ import annotations

import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from game_companion.config import Settings
from game_companion.errors import NotFoundError, ValidationError

DB_FILENAME = "gacha_companion.db"
_BACKUP_RE = re.compile(r"^backup-\d{8}-\d{6}\.zip$")


def backups_dir(settings: Settings) -> Path:
    return settings.resolved_data_dir / "backups"


def _sqlite_path(settings: Settings) -> Path:
    url = settings.resolved_database_url
    if not url.startswith("sqlite:///"):
        raise ValidationError("backups require the default SQLite database")
    return Path(url.removeprefix("sqlite:///"))


def create_backup(settings: Settings) -> Path:
    data_dir = settings.resolved_data_dir
    db_path = _sqlite_path(settings)
    if not db_path.exists():
        raise NotFoundError(f"no database found at {db_path}")

    # Fold the WAL into the main file so the copied .db is complete.
    from game_companion.db.session import create_db_engine

    engine = create_db_engine(settings.resolved_database_url)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        engine.dispose()

    backups_dir(settings).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = backups_dir(settings) / f"backup-{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, arcname=DB_FILENAME)
        for folder in ("personas",):
            for path in sorted((data_dir / folder).glob("*")) if (data_dir / folder).exists() else []:
                if path.is_file():
                    zf.write(path, arcname=f"{folder}/{path.name}")
    return target


def list_backups(settings: Settings) -> list[dict]:
    out = []
    for path in sorted(backups_dir(settings).glob("backup-*.zip"), reverse=True):
        if not _BACKUP_RE.match(path.name):
            continue
        out.append(
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "created_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
            }
        )
    return out


def stage_restore(settings: Settings, name: str) -> tuple[Path, Path]:
    """Validate + extract ``name`` into a staging dir. Returns (staging_dir, db_path)."""
    if not _BACKUP_RE.match(name):
        raise ValidationError(f"not a backup file name: {name}")
    source = backups_dir(settings) / name
    if not source.exists():
        raise NotFoundError(f"backup '{name}' not found")
    with zipfile.ZipFile(source) as zf:
        names = zf.namelist()
        if DB_FILENAME not in names:
            raise ValidationError(f"backup '{name}' does not contain {DB_FILENAME}")
        staging = settings.resolved_data_dir / "restore-staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        zf.extractall(staging)
    return staging, staging / DB_FILENAME


def cleanup_staging(settings: Settings) -> None:
    staging = settings.resolved_data_dir / "restore-staging"
    if staging.exists():
        shutil.rmtree(staging)
