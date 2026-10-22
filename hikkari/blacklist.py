# ©️ Wers1xx, 2025-2026
# Hikkari project account blacklist — multi-mirror, obfuscated, integrity-aware.
# NOTE: open-source clients cannot be 100% unbypassable on a machine the user controls.
# Goal: raise cost of trivial path edits; persist block; multi-point enforcement.

from __future__ import annotations

import base64
import hashlib
import hmac
import asyncio
import logging
import time
from typing import Iterable

import aiohttp

logger = logging.getLogger(__name__)

# Obfuscated URL fragments (not a single searchable "BlackList.txt" string in one place)
def _u(*parts: str) -> str:
    return "".join(parts)


def _blacklist_urls() -> tuple[str, ...]:
    # assembled at runtime
    gh = _u("https://raw.github", "usercontent.com/")
    repo = _u("Wers1xx", "/", "Hikkari")
    path = _u("/assets/", "Black", "List", ".txt")
    cdn = _u("https://cdn.jsdelivr.net/gh/")
    return (
        _u(gh, repo, "/master", path),
        _u(cdn, repo, "@master", path),
        _u(gh, repo, "/beta", path),
        # optional private mirror (set env HIKKARI_BL_MIRROR) — checked first if present
    )


def _extra_mirrors() -> list[str]:
    import os
    extra = os.environ.get("HIKKARI_BL_MIRROR") or os.environ.get("HIKKARI_BLACKLIST_URL")
    if extra:
        return [extra.strip()]
    return []


DB_MODULE = "hikkari_blacklist"
DB_FLAG = "blocked"
DB_REASON = "reason"
DB_SEEN = "last_remote_ok"
DB_HASH = "payload_hash"

# Optional HMAC: if server sends X-Hikkari-Sig = hex(hmac_sha256(key, body))
# Key material is split so a single-string replace is harder.
def _sig_key() -> bytes:
    a = base64.b64decode(b"SGlra2FyaQ==")  # Hikkari
    b = b"BL"
    c = hashlib.sha256(b"wers1xx-project-seal-2026").digest()[:8]
    return a + b + c


def parse_blacklist_text(text: str) -> set[int]:
    ids: set[int] = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split()[0].split("#")[0].strip().rstrip(",")
        if token.isdigit():
            ids.add(int(token))
        elif token.startswith("-") and token[1:].isdigit():
            # signed lines reserved; ignore
            pass
    return ids


def _verify_sig(body: bytes, header: str | None) -> bool:
    if not header:
        return True  # unsigned mirrors still accepted; signed ones must match
    try:
        expect = hmac.new(_sig_key(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expect, header.strip().lower())
    except Exception:
        return False


_BL_CACHE: set | None = None
_BL_CACHE_AT: float = 0.0
_BL_CACHE_TTL = 300.0  # 5 min — avoid network on every restart / loop tick


async def fetch_blacklist_ids(timeout: float = 2.0) -> set[int] | None:
    """Fetch union of IDs from mirrors (parallel). Cached briefly in-process."""
    global _BL_CACHE, _BL_CACHE_AT
    now = time.time()
    if _BL_CACHE is not None and (now - _BL_CACHE_AT) < _BL_CACHE_TTL:
        return _BL_CACHE

    urls = list(_extra_mirrors()) + list(_blacklist_urls())
    if not urls:
        return _BL_CACHE

    timeout_cfg = aiohttp.ClientTimeout(total=timeout)

    async def _one(session, url: str) -> set[int]:
        try:
            async with session.get(
                url,
                headers={
                    "User-Agent": "HikkariUserbot/2.0",
                    "Cache-Control": "no-cache",
                },
            ) as resp:
                if resp.status != 200:
                    return set()
                raw = await resp.read()
                sig = resp.headers.get("X-Hikkari-Sig") or resp.headers.get(
                    "X-Hikkari-Signature"
                )
                if sig and not _verify_sig(raw, sig):
                    logger.warning(
                        "blacklist mirror signature mismatch: %s", url[:48]
                    )
                    return set()
                return parse_blacklist_text(raw.decode("utf-8", errors="ignore"))
        except Exception as e:
            logger.debug("blacklist fetch failed: %s", e)
            return set()

    ids: set[int] = set()
    any_ok = False
    try:
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            parts = await asyncio.gather(*[_one(session, u) for u in urls])
            for chunk in parts:
                if chunk:
                    ids |= chunk
                    any_ok = True
    except Exception as e:
        logger.debug("blacklist session failed: %s", e)

    if any_ok:
        _BL_CACHE = ids
        _BL_CACHE_AT = now
        return ids
    return _BL_CACHE  # stale better than None on flaky net if we had one


def is_locally_blocked(db) -> bool:
    try:
        return bool(db.get(DB_MODULE, DB_FLAG, False))
    except Exception:
        return False


def mark_locally_blocked(db, reason: str = "github_blacklist") -> None:
    try:
        db.set(DB_MODULE, DB_FLAG, True)
        db.set(DB_MODULE, DB_REASON, reason)
        db.set(DB_MODULE, "blocked_at", int(time.time()))
    except Exception:
        logger.exception("Failed to persist blacklist flag")


def clear_local_block(db) -> None:
    """Only for recovery if remote list no longer contains the id (optional policy)."""
    try:
        db.set(DB_MODULE, DB_FLAG, False)
    except Exception:
        pass


async def notify_blocked(client, user_id: int) -> None:
    text = (
        "🚫 <b>Hikkari</b>\n\n"
        "Your account is on the <b>project blacklist</b>.\n"
        "Userbot will not start.\n\n"
        f"<code>{user_id}</code>"
    )
    try:
        inline = getattr(getattr(client, "loader", None), "inline", None)
        bot = getattr(inline, "bot", None) if inline else None
        if bot:
            await bot.send_message(user_id, text)
            return
    except Exception:
        logger.debug("blacklist bot notify failed", exc_info=True)
    try:
        await client.send_message("me", text)
    except Exception:
        logger.debug("blacklist Saved Messages notify failed", exc_info=True)


def _integrity_ok() -> bool:
    """Cheap self-check: critical names must exist and fetch URL builder non-empty."""
    try:
        urls = _blacklist_urls()
        if len(urls) < 2:
            return False
        # function source fingerprint — if someone empties enforce_blacklist, this still runs
        src = (enforce_blacklist.__code__.co_code[:32] if hasattr(enforce_blacklist, "__code__") else b"x")
        return len(src) > 8
    except Exception:
        return False


async def enforce_blacklist(client, db, *, user_id: int | None = None) -> bool:
    """
    Returns True if account is blocked and must shut down.
    Once blocked locally, stays blocked even if mirrors are offline
    (prevents "block network + edit code" soft bypass after ban).
    """
    if not _integrity_ok():
        logger.critical("blacklist integrity check failed")
        mark_locally_blocked(db, "integrity")
        return True

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
        # network fail — do not clear local; do not block new users offline
        return is_locally_blocked(db)

    try:
        db.set(DB_MODULE, DB_SEEN, int(time.time()))
        db.set(DB_MODULE, DB_HASH, hashlib.sha256(str(sorted(remote)[:50]).encode()).hexdigest()[:16])
    except Exception:
        pass

    if int(uid) in remote:
        mark_locally_blocked(db, "github_BlackList")
        return True
    return False
