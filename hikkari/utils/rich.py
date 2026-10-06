# ©️ Wers1xx, 2025-2026
# Rich text mode for Hikkari — Telegram-style tables, blockquotes, premium emoji
# 🌐 https://github.com/Wers1xx/Hikkari

from __future__ import annotations

import html as html_mod
import re
from typing import Any, Iterable

RICH_DB_MOD = "hikkari.rich"
RICH_DB_KEY = "enabled"
RICH_TPL_KEY = "template"

STAR = "<tg-emoji emoji-id=5343785308817236494>✨</tg-emoji>"

_TG_EMOJI_RE = re.compile(
    r"<tg-emoji[^>]*>\s*([^<]*?)\s*</tg-emoji>"
    r"|<emoji\s+document_id=\d+>\s*([^<]*?)\s*</emoji>",
    re.I,
)

# "Key: value" / "• Key: value" lines → table rows
_KV_RE = re.compile(
    r"^(?:[•\-\*]\s*)?(?:<[^>]+>\s*)*"
    r"(?P<key>[A-Za-zА-Яа-яЁё0-9 _/.\-]{2,40})\s*[:=\-–—]\s+"
    r"(?P<val>.+)$"
)


def is_rich_enabled(db: Any = None) -> bool:
    if db is None:
        return True
    try:
        val = db.get(RICH_DB_MOD, RICH_DB_KEY, None)
        if val is None:
            val = db.get("Settings", "rich_mode", None)
        if val is None:
            return True
        return bool(val)
    except Exception:
        return True


def get_rich_template(db: Any = None) -> str:
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
    if not text or not isinstance(text, str):
        return text
    text = _TG_EMOJI_RE.sub(lambda m: (m.group(1) or m.group(2) or "").strip(), text)
    text = re.sub(r"<blockquote\s+expandable>", "<blockquote>", text, flags=re.I)
    # unwrap simple tree markers for plain mode
    return text


def rich_table(
    rows: Iterable[tuple[str, str]],
    *,
    header: tuple[str, str] | None = ("Component", "Current release"),
    native: bool = False,
) -> str:
    """
    native=True  → official Rich Message HTML <table> (ONLY for sendRichMessage)
    native=False → classic Telegram HTML (blockquote tree) for sendMessage/edit
    """
    h0, h1 = header or ("Component", "Current release")
    if native:
        parts = [
            f'<table bordered striped>'
            f"<tr><th>{html_mod.escape(h0)}</th><th>{html_mod.escape(h1)}</th></tr>"
        ]
        for k, v in rows:
            ks = html_mod.escape(str(k))
            vs = str(v)
            if not ("<" in vs and ">" in vs):
                vs = html_mod.escape(vs)
            parts.append(f"<tr><td>{ks}</td><td>{vs}</td></tr>")
        parts.append("</table>")
        return "".join(parts)

    # Classic readable card (works in normal messages)
    lines = [
        f"<b>{html_mod.escape(h0)}</b> · <b>{html_mod.escape(h1)}</b>",
        "─────────────────",
    ]
    for k, v in rows:
        ks = html_mod.escape(str(k))
        vs = str(v)
        if not ("<" in vs and ">" in vs):
            vs = f"<code>{html_mod.escape(vs)}</code>"
        lines.append(f"• <b>{ks}</b>: {vs}")
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"




def rich_blocks_from_kv_text(text: str) -> str | None:
    """If text is mostly key:value lines, convert to rich table. Else None."""
    # strip outer tags for analysis
    plain = re.sub(r"<[^>]+>", "", text)
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None
    pairs = []
    for ln in lines:
        m = _KV_RE.match(ln)
        if m:
            pairs.append((m.group("key").strip(), m.group("val").strip()))
    if len(pairs) < 3:
        return None
    # keep original values with HTML from matching lines if possible
    return rich_table(pairs)


def enhance_rich_html(text: str) -> str:
    """
    Upgrade plain-ish HTML to richer look:
    - multi-line non-blockquote content → expandable blockquote groups
    - preserve existing tg-emoji / blockquote
    """
    if not text or not isinstance(text, str):
        return text
    # already has tree blockquotes like Heroku info — leave
    if "├" in text or "┌" in text or "└" in text:
        return text
    # already has our table separator
    if "────────────────────" in text:
        return text
    # try kv table
    as_table = rich_blocks_from_kv_text(text)
    if as_table and len(as_table) > 40:
        # keep leading header line (emoji title) if present
        first = text.split("\n", 1)[0]
        if first and ("<tg-emoji" in first or "<b>" in first) and ":" not in re.sub(r"<[^>]+>", "", first):
            return first + "\n" + as_table
        return as_table
    return text


def apply_rich(text: str, db: Any = None) -> str:
    if not text or not isinstance(text, str):
        return text
    if not is_rich_enabled(db):
        return strip_rich(text)
    text = enhance_rich_html(text)
    tpl = get_rich_template(db)
    try:
        return tpl.format(text=text, star=STAR)
    except Exception:
        return text


def info_rich_message(
    *,
    title: str,
    rows: list[tuple[str, str]],
    footer: str = "",
    header: tuple[str, str] = ("Component", "Current release"),
    native: bool = False,
) -> str:
    """Info card. native=True only when sending via sendRichMessage."""
    if native:
        parts = [f"<h2>{title}</h2>", rich_table(rows, header=header, native=True)]
        if footer:
            parts.append(f"<p>{footer}</p>")
        return "\n".join(parts)
    parts = [title, rich_table(rows, header=header, native=False)]
    if footer:
        parts.append(footer)
    return "\n".join(parts)
