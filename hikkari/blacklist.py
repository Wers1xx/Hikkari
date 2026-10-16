# ©️ Wers1xx, 2025-2026
# Hikkari project account blacklist (GitHub assets/BlackList.txt)

from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger(__name__)

BLACKLIST_URLS = (
    "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/BlackList.txt",
    "https://cdn.jsdelivr.net/gh/Wers1xx/Hikkari@master/assets/BlackList.txt",
    "https://raw.githubusercontent.com/Wers1xx/Hikkari/beta/assets/BlackList.txt",
)

DB_MODULE = "hikkari_blacklist"
DB_FLAG = "blocked"
DB_REASON = "reason"


def parse_blacklist_text(text: str) -> set[int]:
    ids: set[int] = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split()[0].split("#")[0].strip().rstrip(",")
        if token.isdigit():
            ids.add(int(token))
    return ids


async def fetch_blacklist_ids(timeout: float = 12.0) -> set[int] | None:
    """Return set of blocked IDs, or None on total network failure."""
    ids: set[int] = set()
    ok = False
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
        for url in BLACKLIST_URLS:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()
                    ids |= parse_blacklist_text(text)
                    ok = True
                    break
            except Exception as e:
                logger.debug("blacklist fetch %s failed: %s", url, e)
    if not ok:
        return None
    return ids


def is_locally_blocked(db) -> bool:
    try:
        return bool(db.get(DB_MODULE, DB_FLAG, False))
    except Exception:
        return False


def mark_locally_blocked(db, reason: str = "github_blacklist") -> None:
    try:
        db.set(DB_MODULE, DB_FLAG, True)
        db.set(DB_MODULE, DB_REASON, reason)
    except Exception:
        logger.exception("Failed to persist blacklist flag")


async def notify_blocked(client, user_id: int, text: str | None = None) -> None:
    msg = text or (
        "🚫 <b>Hikkari Userbot</b>\n\n"
        "Your account is on the <b>project blacklist</b>.\n"
        "You can no longer use Hikkari Userbot.\n\n"
        "If you believe this is a mistake, contact the project owner."
    )
    try:
        bot = getattr(getattr(client, "loader", None), "inline", None)
        bot_api = getattr(bot, "bot", None) if bot else None
        if bot_api is not None:
            await bot_api.send_message(user_id, msg, parse_mode="HTML")
            return
    except Exception:
        logger.debug("blacklist bot notify failed", exc_info=True)
    try:
        await client.send_message("me", msg)
    except Exception:
        logger.debug("blacklist Saved Messages notify failed", exc_info=True)


async def enforce_blacklist(client, db, *, user_id: int | None = None) -> bool:
    """True if account is blocked and process should stop."""
    if is_locally_blocked(db):
        return True

    uid = user_id
    if uid is None:
        try:
            me = getattr(client, "hikkari_me", None) or await client.get_me()
            uid = int(getattr(me, "id", 0) or 0)
        except Exception:
            return False
    if not uid:
        return False

    remote = await fetch_blacklist_ids()
    if remote is None:
        return False
    if uid in remote:
        mark_locally_blocked(db, "github_BlackList.txt")
        return True
    return False
