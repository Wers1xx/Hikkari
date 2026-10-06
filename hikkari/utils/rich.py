# ©️ Wers1xx, 2025-2026
# Rich text mode helpers for Hikkari
# 🌐 https://github.com/Wers1xx/Hikkari

from __future__ import annotations

import re
from typing import Any

# DB key under main module name is set from settings; fallback key:
RICH_DB_MOD = "hikkari.rich"
RICH_DB_KEY = "enabled"
RICH_TPL_KEY = "template"

# Default star used for invert/quote bootstrap
STAR = "<tg-emoji emoji-id=5343785308817236494>✨</tg-emoji>"

# Strip premium emoji tags → keep fallback char
_TG_EMOJI_RE = re.compile(
    r"<tg-emoji[^>]*>\s*([^<]*?)\s*</tg-emoji>"
    r"|<emoji\s+document_id=\d+>\s*([^<]*?)\s*</emoji>",
    re.I,
)


def is_rich_enabled(db: Any = None) -> bool:
    """Return whether Rich mode is on (default: True for premium look)."""
    if db is None:
        return True
    try:
        val = db.get(RICH_DB_MOD, RICH_DB_KEY, None)
        if val is None:
            # also check Settings module config storage
            val = db.get("Settings", "rich_mode", None)
        if val is None:
            return True
        return bool(val)
    except Exception:
        return True


def get_rich_template(db: Any = None) -> str:
    """User template. Placeholders: {text}, {star}"""
    default = "{text}"
    if db is None:
        return default
    try:
        tpl = db.get(RICH_DB_MOD, RICH_TPL_KEY, None)
        if not tpl:
            tpl = db.get("Settings", "rich_template", None)
        if isinstance(tpl, str) and "{text}" in tpl:
            return tpl
    except Exception:
        pass
    return default


def strip_rich(text: str) -> str:
    """Convert rich HTML (premium emoji etc.) to plain-ish text."""
    if not text or not isinstance(text, str):
        return text
    text = _TG_EMOJI_RE.sub(lambda m: (m.group(1) or m.group(2) or "").strip(), text)
    # unwrap expandable blockquotes to simple blockquote
    text = re.sub(
        r"<blockquote\s+expandable>",
        "<blockquote>",
        text,
        flags=re.I,
    )
    return text


def apply_rich(text: str, db: Any = None) -> str:
    """Apply rich mode (or strip) according to user settings."""
    if not text or not isinstance(text, str):
        return text
    if is_rich_enabled(db):
        tpl = get_rich_template(db)
        try:
            return tpl.format(text=text, star=STAR)
        except Exception:
            return text
    return strip_rich(text)


def rich_answer_kwargs(db: Any = None) -> dict:
    """Extra kwargs for answers when rich/quote preferred."""
    return {}
