# ©️ Wers1xx, 2025-2026
# Session SQLite self-heal (entities table and related schema)

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Schema aligned with Telethon / hikkaritl SQLiteSession (6-column entities)
_ENTITIES_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    id integer primary key,
    hash integer not null,
    username text,
    phone integer,
    name text,
    date integer
)
"""

# Minimal tables some session builds expect
_EXTRA_TABLES = (
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
        auth_key blob
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
)


def repair_session_file(path: Path) -> bool:
    """Ensure required tables exist. Returns True if file was modified/usable."""
    path = Path(path)
    if not path.is_file():
        return False
    # skip journals
    if path.name.endswith("-journal") or path.suffix == ".session-journal":
        return False

    try:
        con = sqlite3.connect(str(path))
        try:
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}
            changed = False
            if "entities" not in tables:
                cur.execute(_ENTITIES_SQL)
                changed = True
                logger.warning("Repaired missing entities table in %s", path.name)
            for sql in _EXTRA_TABLES:
                # only create if completely empty session skeleton is needed
                # still IF NOT EXISTS so safe
                cur.execute(sql)
            con.commit()
            return True
        finally:
            con.close()
    except Exception:
        logger.exception("Failed to repair session %s", path)
        return False


def repair_sessions_dir(directory: str | Path) -> int:
    """Repair all hikkari-*.session files in directory. Returns count repaired."""
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    n = 0
    for path in directory.glob("hikkari-*.session"):
        if path.name.endswith("-journal"):
            continue
        before = None
        try:
            con = sqlite3.connect(str(path))
            cur = con.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
            )
            before = cur.fetchone()
            con.close()
        except Exception:
            before = None
        if repair_session_file(path) and before is None:
            n += 1
    # drop stale journals that can lock corrupt dbs
    for path in directory.glob("*.session-journal"):
        try:
            path.unlink()
            logger.info("Removed stale journal %s", path.name)
        except Exception:
            pass
    return n


def patch_sqlite_session_class() -> None:
    """Monkey-patch hikkaritl SQLiteSession.process_entities to auto-create table."""
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
            msg = str(e).lower()
            if "no such table: entities" not in msg and "entities" not in msg:
                raise
            # recreate table and retry once
            try:
                c = self._cursor if hasattr(self, "_cursor") else None
                conn = getattr(self, "_conn", None)
                if conn is None and hasattr(self, "_connection"):
                    conn = self._connection
                # Telethon uses self._conn and cursor via execute
                if hasattr(self, "_execute"):
                    self._execute(_ENTITIES_SQL)
                elif conn is not None:
                    conn.execute(_ENTITIES_SQL)
                    conn.commit()
                else:
                    # filename based repair
                    fname = getattr(self, "filename", None) or getattr(
                        self, "_filename", None
                    )
                    if fname:
                        repair_session_file(Path(str(fname)).with_suffix(".session") if not str(fname).endswith(".session") else Path(str(fname)))
                logger.warning("entities table was missing; recreated and retrying")
                return original(self, tlo)
            except Exception:
                logger.exception("Failed to recover entities table")
                # swallow on disconnect path so userbot can exit cleanly
                return None

    safe_process_entities._hikkari_patched = True
    SQLiteSession.process_entities = safe_process_entities
    logger.debug("Patched SQLiteSession.process_entities for entities self-heal")
