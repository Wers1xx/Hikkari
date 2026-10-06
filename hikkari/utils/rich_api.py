# ©️ Wers1xx, 2025-2026
# Telegram Bot API 10.1+ Rich Messages helper for Hikkari
# 🌐 https://github.com/Wers1xx/Hikkari

from __future__ import annotations

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


def html_table(
    rows: list[tuple[str, str]],
    *,
    header: tuple[str, str] = ("Component", "Current release"),
    bordered: bool = True,
    striped: bool = True,
    compact: bool = False,
) -> str:
    """Build official Rich Message <table> HTML."""
    attrs = []
    if bordered:
        attrs.append("bordered")
    if striped:
        attrs.append("striped")
    if compact:
        attrs.append("compact")
    attr = (" " + " ".join(attrs)) if attrs else ""
    h0, h1 = header
    body = [f"<tr><th>{h0}</th><th>{h1}</th></tr>"]
    for k, v in rows:
        body.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
    return f"<table{attr}>{''.join(body)}</table>"


def build_info_html(
    *,
    title: str,
    rows: list[tuple[str, str]],
    footer: str = "",
    header: tuple[str, str] = ("Component", "Current release"),
) -> str:
    parts = [
        f"<h2>{title}</h2>",
        html_table(rows, header=header),
    ]
    if footer:
        parts.append(f"<p>{footer}</p>")
    return "\n".join(parts)


async def send_rich_message(
    token: str,
    chat_id: int | str,
    html: str,
    *,
    message_thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    reply_markup: dict | None = None,
    skip_entity_detection: bool = True,
) -> dict | None:
    """
    Call Bot API sendRichMessage.
    Returns parsed JSON result or None on failure.
    """
    if not token:
        return None
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "rich_message": {
            "html": html,
            "skip_entity_detection": skip_entity_detection,
        },
    }
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id
    if reply_to_message_id is not None:
        payload["reply_parameters"] = {"message_id": reply_to_message_id}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    url = API.format(token=token, method="sendRichMessage")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json(content_type=None)
                if not data.get("ok"):
                    logger.warning(
                        "sendRichMessage failed: %s",
                        data.get("description") or data,
                    )
                    return None
                return data.get("result")
    except Exception:
        logger.exception("sendRichMessage request error")
        return None


def _resolve_chat_id(chat_id) -> int | str | None:
    """Bot API needs int chat id or @username — not Peer objects."""
    if chat_id is None:
        return None
    if isinstance(chat_id, int):
        return chat_id
    if isinstance(chat_id, str):
        return chat_id
    # Telethon PeerUser / PeerChannel / InputPeer*
    for attr in ("user_id", "channel_id", "chat_id"):
        v = getattr(chat_id, attr, None)
        if isinstance(v, int):
            # channels need -100 prefix for Bot API
            if attr == "channel_id":
                return int(f"-100{v}")
            if attr == "chat_id":
                return -v if v > 0 else v
            return v
    return None


async def try_send_rich(
    client,
    chat_id,
    html: str,
    **kwargs,
) -> bool:
    """
    Send via Bot API sendRichMessage using the inline bot token.
    CRITICAL: only bots can sendRichMessage reliably; user client path is unsupported.
    """
    token = None
    try:
        inline = getattr(client, "hikkari_inline", None) or getattr(
            getattr(client, "loader", None), "inline", None
        )
        if inline is not None:
            token = (
                getattr(inline, "token", None)
                or getattr(inline, "_token", None)
                or getattr(inline, "bot_token", None)
            )
        if not token:
            db = getattr(client, "hikkari_db", None)
            if db is not None:
                for key in (
                    ("hikkari.inline", "bot_token"),
                    ("hikka.inline", "bot_token"),
                    ("heroku.inline", "bot_token"),
                ):
                    token = db.get(key[0], key[1], None)
                    if token:
                        break
    except Exception:
        logger.debug("token lookup failed", exc_info=True)
        token = None
    if not token:
        logger.debug("sendRichMessage skipped: no bot token")
        return False

    cid = _resolve_chat_id(chat_id)
    if cid is None:
        # try message peer from kwargs
        logger.debug("sendRichMessage skipped: bad chat_id %r", chat_id)
        return False

    result = await send_rich_message(str(token), cid, html, **kwargs)
    return result is not None
