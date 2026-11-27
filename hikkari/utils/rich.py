from __future__ import annotations
import contextlib
# ©️ Wers1xx, 2025-2026
# Rich text mode for Hikkari — Telegram-style tables, blockquotes, premium emoji
# 🌐 https://github.com/Wers1xx/Hikkari


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
        return False
    try:
        for mod, key in (
            (RICH_DB_MOD, RICH_DB_KEY),
            ("Settings", "rich_mode"),
            ("HikkariSettings", "rich_mode"),
            ("CoreMod", "rich_mode"),
            ("Help", "rich_mode"),
            ("HelpMod", "rich_mode"),
            ("TestMod", "rich_mode"),
            ("HikkariInfo", "rich_mode"),
            ("HikkariInfoMod", "rich_mode"),
        ):
            with contextlib.suppress(Exception):
                val = db.get(mod, key, None)
                if val is not None and bool(val):
                    return True
        for mod in (
            "Settings", "CoreMod", "HikkariSettings", "TestMod", "Help", "HelpMod",
            "HikkariInfo", "HikkariInfoMod", "test",
        ):
            for conf_key in ("__config__", "config"):
                with contextlib.suppress(Exception):
                    conf = db.get(mod, conf_key, None)
                    if isinstance(conf, dict) and conf.get("rich_mode"):
                        return True
        return False
    except Exception:
        return False


def can_use_rich(client: Any = None, db: Any = None) -> bool:
    if not is_rich_enabled(db):
        return False
    if client is None:
        return False
    try:
        me = (
            getattr(client, "hikkari_me", None)
            or getattr(client, "hikka_me", None)
            or getattr(client, "_me", None)
            or getattr(client, "me", None)
        )
        if me is not None:
            return bool(getattr(me, "premium", False))
        if hasattr(client, "premium"):
            return bool(getattr(client, "premium", False))
        with contextlib.suppress(Exception):
            ent = getattr(client, "hikkari_entity", None)
            if ent is not None:
                return bool(getattr(ent, "premium", False))
        return False
    except Exception:
        return False


def to_classic_text(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    return strip_rich(text)


_API_GATES: dict[str, Any] = {}
_API_LAST: dict[str, float] = {}


async def api_gate(client: Any = None, *, min_interval: float = 0.35) -> None:
    """Serialize and space out client API bursts to reduce session risk."""
    import asyncio
    import time

    key = "main"
    with contextlib.suppress(Exception):
        tid = getattr(client, "tg_id", None) if client is not None else None
        if tid is None and client is not None:
            me = getattr(client, "hikkari_me", None) or getattr(client, "hikka_me", None)
            tid = getattr(me, "id", None)
        if tid is not None:
            key = str(tid)
    gate = _API_GATES.get(key)
    if gate is None:
        gate = asyncio.Lock()
        _API_GATES[key] = gate
    async with gate:
        now = time.monotonic()
        last = _API_LAST.get(key, 0.0)
        wait = min_interval - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)
        _API_LAST[key] = time.monotonic()


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
    """
    Classic path only. Never strip premium <tg-emoji> / <emoji document_id>.
    When rich_mode is OFF → return text unchanged (keeps premium emoji).
    When ON → optional template wrap; still keep emoji tags intact.
    Native Rich (Help/Info/Tester/Loader) goes through inline.rich, not here.
    """
    if not text or not isinstance(text, str):
        return text
    if not is_rich_enabled(db):
        return text  # do NOT strip_rich — that killed premium emoji
    tpl = get_rich_template(db)
    if not tpl or tpl.strip() == "{text}":
        return text
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


def to_rich_html(text: str, *, banner_url: str | None = None) -> str:
    """
    Convert normal module HTML into Rich Message HTML.
    - optional banner as <figure><img>
    - key:value blocks → <table>
    - rest → <p> / keep blockquotes as <blockquote>
    """
    if not text:
        return ""
    parts: list[str] = []
    if banner_url and str(banner_url).startswith(("http://", "https://")):
        parts.append(f'<figure><img src="{html_mod.escape(str(banner_url))}"/></figure>')

    # Already has table/h2 — treat as rich-ready
    if "<table" in text.lower() or "<h2" in text.lower() or "<figure" in text.lower():
        parts.append(text)
        return "\n".join(parts)

    # Try KV table extraction
    table = rich_blocks_from_kv_text(text)
    if table:
        # strip those lines from body
        body_lines = []
        for line in text.splitlines():
            plain = _TG_EMOJI_RE.sub(lambda m: (m.group(1) or m.group(2) or "").strip(), line)
            plain = re.sub(r"<[^>]+>", "", plain).strip()
            if _KV_RE.match(plain or ""):
                continue
            body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if body:
            # wrap remaining as paragraphs
            for block in re.split(r"\n{2,}", body):
                block = block.strip()
                if not block:
                    continue
                if block.startswith("<blockquote"):
                    parts.append(block)
                else:
                    parts.append(f"<p>{block}</p>")
        parts.append(table)
        return "\n".join(parts)

    # Generic: keep structure, wrap loose text
    if "<blockquote" in text:
        parts.append(text)
    else:
        parts.append(f"<p>{text}</p>")
    return "\n".join(parts)
