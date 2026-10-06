# ©️ Wers1xx, 2025-2026
# Bot API 10.1+ sendRichMessage bridge for Hikkari
# Official: https://core.telegram.org/bots/api#sendrichmessage
# Rich Messages work ONLY via Bot API (bot token), not user MTProto edit.

from __future__ import annotations

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"

def pick_banner_url(banner) -> str | None:
    """RandomLinkList / list / str → first http(s) URL."""
    if banner is None:
        return None
    if isinstance(banner, str):
        s = banner.strip()
        # "[https://...]" style
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1].strip()
        if s.startswith(("http://", "https://")):
            return s.split()[0].strip("[],")
        return None
    if isinstance(banner, (list, tuple)):
        for item in banner:
            u = pick_banner_url(item)
            if u:
                return u
    return None



def html_table(
    rows: list[tuple[str, str]],
    *,
    header: tuple[str, str] = ("Component", "Current release"),
) -> str:
    h0, h1 = header
    body = [f"<tr><th>{h0}</th><th>{h1}</th></tr>"]
    for k, v in rows:
        body.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
    return f"<table bordered striped>{''.join(body)}</table>"


def build_info_html(
    *,
    title: str,
    rows: list[tuple[str, str]],
    footer: str = "",
    header: tuple[str, str] = ("Component", "Current release"),
    banner_url: str | None = None,
) -> str:
    """Official Rich HTML (html field) for answerInlineQuery / sendRichMessage."""
    parts: list[str] = []
    if banner_url and str(banner_url).startswith(("http://", "https://")):
        # Official Rich HTML media block
        parts.append(
            f'<figure><img src="{banner_url}"/>'
            f"<figcaption>{title}</figcaption></figure>"
        )
    parts.append(f"<h2>{title}</h2>")
    parts.append(html_table(rows, header=header))
    if footer:
        parts.append(f"<p><i>{footer}</i></p>")
    return "\n".join(parts)


def _resolve_chat_id(chat_id) -> int | str | None:
    if chat_id is None:
        return None
    if isinstance(chat_id, bool):
        return None
    if isinstance(chat_id, int):
        return chat_id
    if isinstance(chat_id, str):
        s = chat_id.strip()
        if s.startswith("@"):
            return s
        try:
            return int(s)
        except ValueError:
            return s
    for attr in ("user_id", "channel_id", "chat_id"):
        v = getattr(chat_id, attr, None)
        if isinstance(v, int) and v:
            if attr == "channel_id":
                return int(f"-100{v}")
            if attr == "chat_id":
                return -abs(v)
            return v
    return None


def _find_bot_token(client) -> str | None:
    token = None
    try:
        inline = getattr(client, "hikkari_inline", None) or getattr(
            getattr(client, "loader", None), "inline", None
        )
        if inline is not None:
            token = (
                getattr(inline, "_token", None)
                or getattr(inline, "token", None)
                or getattr(inline, "bot_token", None)
            )
        if not token:
            db = getattr(client, "hikkari_db", None) or getattr(
                getattr(client, "loader", None), "_db", None
            )
            if db is not None:
                for ns, key in (
                    ("hikkari.inline", "bot_token"),
                    ("hikka.inline", "bot_token"),
                    ("heroku.inline", "bot_token"),
                ):
                    token = db.get(ns, key, None)
                    if token:
                        break
    except Exception:
        logger.debug("token lookup error", exc_info=True)
    if token:
        return str(token).strip()
    return None


async def send_rich_message(
    token: str,
    chat_id: int | str,
    html: str,
    *,
    message_thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    reply_markup: dict | None = None,
) -> dict | None:
    """
    Official Bot API sendRichMessage.
    Payload uses rich_message.html (NOT fake rich_text blocks).
    """
    if not token or not html:
        return None
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "rich_message": {
            "html": html,
            "skip_entity_detection": True,
        },
    }
    if message_thread_id is not None:
        payload["message_thread_id"] = int(message_thread_id)
    if reply_to_message_id is not None:
        payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    url = API.format(token=token, method="sendRichMessage")
    try:
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
                if not data.get("ok"):
                    logger.warning(
                        "sendRichMessage failed chat=%s desc=%s",
                        chat_id,
                        data.get("description") or data,
                    )
                    return None
                logger.info("sendRichMessage OK chat=%s", chat_id)
                return data.get("result")
    except Exception as e:
        logger.warning("sendRichMessage request error: %s", e)
        return None


async def try_send_rich(
    client,
    chat_id,
    html: str,
    **kwargs,
) -> bool:
    """
    Send Rich Message via inline bot token.
    Tries current chat, then falls back to owner's user id (bot DM).
    """
    token = _find_bot_token(client)
    if not token:
        logger.warning(
            "sendRichMessage skipped: no bot token "
            "(create inline bot / .yesbot / .ch_bot_token)"
        )
        return False

    candidates: list[int | str] = []
    cid = _resolve_chat_id(chat_id)
    if cid is not None:
        candidates.append(cid)

    # Fallback: DM with bot (user must have /start'ed the bot)
    try:
        me = getattr(client, "hikkari_me", None) or await client.get_me()
        uid = getattr(me, "id", None)
        if isinstance(uid, int) and uid not in candidates:
            candidates.append(uid)
    except Exception:
        pass

    last_ok = False
    for target in candidates:
        result = await send_rich_message(token, target, html, **kwargs)
        if result is not None:
            last_ok = True
            break
    return last_ok


async def answer_inline_rich(
    token: str,
    inline_query_id: str | int,
    html: str,
    *,
    title: str = "Hikkari",
    description: str = "Rich message",
    result_id: str | None = None,
    reply_markup: dict | None = None,
    thumbnail_url: str | None = None,
) -> bool:
    """
    Answer an inline query with a native Rich Message.
    When the userbot clicks the result, the message appears with via @bot.
    Official: answerInlineQuery + InputRichMessageContent.
    """
    if not token or not inline_query_id or not html:
        return False
    rid = result_id or "rich_" + str(abs(hash(html)))[:12]
    article: dict[str, Any] = {
        "type": "article",
        "id": rid,
        "title": title[:64],
        "description": (description or "")[:120],
        "input_message_content": {
            "rich_message": {
                "html": html,
                "skip_entity_detection": True,
            }
        },
    }
    if thumbnail_url and str(thumbnail_url).startswith(("http://", "https://")):
        article["thumbnail_url"] = str(thumbnail_url)
    if reply_markup is not None:
        article["reply_markup"] = reply_markup

    payload = {
        "inline_query_id": str(inline_query_id),
        "results": [article],
        "cache_time": 0,
        "is_personal": True,
    }
    url = API.format(token=token, method="answerInlineQuery")
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
                if not data.get("ok"):
                    logger.warning(
                        "answerInlineQuery(rich) failed: %s",
                        data.get("description") or data,
                    )
                    return False
                logger.info("answerInlineQuery(rich) OK id=%s", inline_query_id)
                return True
    except Exception as e:
        logger.warning("answerInlineQuery(rich) error: %s", e)
        return False
