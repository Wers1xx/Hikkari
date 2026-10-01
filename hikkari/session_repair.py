# ©️ Wers1xx, 2025-2026
# Session SQLite self-heal (entities / version schema)

from __future__ import annotations

import logging
import contextlib
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Match Telethon / hikkaritl CURRENT_VERSION
CURRENT_VERSION = 8

_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS version (
        version integer primary key
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        dc_id integer primary key,
        server_address text,
        port integer,
        auth_key blob,
        takeout_id integer,
        tmp_auth_key blob
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entities (
        id integer primary key,
        hash integer not null,
        username text,
        phone integer,
        name text,
        date integer
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sent_files (
        md5_digest blob,
        file_size integer,
        type integer,
        id integer,
        hash integer,
        primary key(md5_digest, file_size, type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS update_state (
        id integer primary key,
        pts integer,
        qts integer,
        date integer,
        seq integer
    )
    """,
]


def repair_session_file(path: Path) -> bool:
    """Ensure session schema is valid for SQLiteSession.__init__."""
    path = Path(path)
    if not path.is_file():
        return False
    name = path.name
    if name.endswith("-journal") or path.suffix == ".session-journal":
        return False
    if not name.endswith(".session"):
        return False

    try:
        con = sqlite3.connect(str(path))
        try:
            cur = con.cursor()
            for sql in _SCHEMA_SQL:
                cur.execute(sql)

            # Critical: version table must contain a row
            cur.execute("SELECT version FROM version LIMIT 1")
            row = cur.fetchone()
            if row is None:
                cur.execute("DELETE FROM version")
                cur.execute(
                    "INSERT INTO version VALUES (?)",
                    (CURRENT_VERSION,),
                )
                logger.warning(
                    "Inserted missing version=%s into %s",
                    CURRENT_VERSION,
                    path.name,
                )
            else:
                try:
                    ver = int(row[0])
                except Exception:
                    ver = 0
                if ver < 1 or ver > 64:
                    cur.execute("DELETE FROM version")
                    cur.execute(
                        "INSERT INTO version VALUES (?)",
                        (CURRENT_VERSION,),
                    )
                    logger.warning("Reset invalid version in %s", path.name)

            # entities must exist (already CREATE IF NOT EXISTS)
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
            )
            if not cur.fetchone():
                cur.execute(_SCHEMA_SQL[2])
                logger.warning("Created entities table in %s", path.name)

            con.commit()
            return True
        finally:
            con.close()
    except Exception:
        logger.exception("Failed to repair session %s", path)
        return False


def repair_sessions_dir(directory: str | Path) -> int:
    """Repair all session files. Returns number of files touched."""
    directory = Path(directory)
    if not directory.is_dir():
        return 0

    n = 0
    for path in sorted(directory.glob("*.session")):
        if "-bot-" in path.name and not path.name.startswith("hikkari-"):
            pass
        if repair_session_file(path):
            n += 1

    for path in directory.glob("*.session-journal"):
        try:
            path.unlink()
            logger.info("Removed stale journal %s", path.name)
        except Exception:
            pass
    return n


def patch_sqlite_session_class() -> None:
    """Make process_entities tolerant to missing entities table."""
    try:
        from hikkaritl.sessions.sqlite import SQLiteSession
    except Exception:
        logger.debug("SQLiteSession not available for patch")
        return

    if getattr(SQLiteSession.process_entities, "_hikkari_patched", False):
        return

    original = SQLiteSession.process_entities

    def safe_process_entities(self, tlo):
        try:
            return original(self, tlo)
        except sqlite3.OperationalError as e:
            if "entities" not in str(e).lower():
                raise
            try:
                fname = getattr(self, "filename", None)
                if fname and fname != ":memory:":
                    repair_session_file(Path(fname))
                elif hasattr(self, "_execute"):
                    self._execute(_SCHEMA_SQL[2])
                logger.warning("entities missing on process_entities; repaired")
                return original(self, tlo)
            except Exception:
                logger.exception("entities recover failed")
                return None

    safe_process_entities._hikkari_patched = True
    SQLiteSession.process_entities = safe_process_entities
    logger.debug("Patched SQLiteSession.process_entities")



def unlock_session(path: Path | str) -> None:
    """Drop stale -journal/-wal/-shm so a single process can open the session."""
    path = Path(path)
    if path.suffix == ".session":
        base = path
    else:
        base = Path(str(path) + ("" if str(path).endswith(".session") else ".session"))
    for suffix in ("-journal", "-wal", "-shm"):
        p = Path(str(base) + suffix)
        if p.exists():
            try:
                p.unlink()
                logger.info("Removed stale lock file %s", p.name)
            except Exception:
                logger.debug("Could not remove %s", p, exc_info=True)
    # ensure schema after lock clear
    if base.is_file():
        with contextlib.suppress(Exception):
            repair_session_file(base)
