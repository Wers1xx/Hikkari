# ©️ Wers1xx, 2025-2026
# Bot API 10.1+ sendRichMessage bridge for Hikkari
# Official: https://core.telegram.org/bots/api#sendrichmessage
# Rich Messages work ONLY via Bot API (bot token), not user MTProto edit.

from __future__ import annotations

import logging
import re
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


def tg_button(
    text: str,
    *,
    type: str = "callback_data",
    data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    query: str | None = None,
    copy_text: str | None = None,
) -> str:
    """
    Official Rich Message button (Bot API 10.3).
    https://core.telegram.org/bots/api#richmessagebutton
    Types: url | callback_data | web_app | login_url | switch_inline_query |
           switch_inline_query_current_chat | copy_text | disabled
    Styles: danger | success | primary | link
    """
    import html as html_mod
    t = html_mod.escape(str(text)[:64])
    attrs = [f'type="{type}"']
    if style and style in ("danger", "success", "primary", "link"):
        attrs.append(f'style="{style}"')
    if type == "url" and url:
        attrs.append(f'url="{html_mod.escape(str(url), quote=True)}"')
    elif type == "callback_data" and data is not None:
        # 1-64 bytes
        d = str(data)[:64]
        attrs.append(f'data="{html_mod.escape(d, quote=True)}"')
    elif type == "web_app" and url:
        attrs.append(f'url="{html_mod.escape(str(url), quote=True)}"')
    elif type in ("switch_inline_query", "switch_inline_query_current_chat") and query is not None:
        attrs.append(f'query="{html_mod.escape(str(query), quote=True)}"')
    elif type == "copy_text" and copy_text is not None:
        attrs.append(f'text="{html_mod.escape(str(copy_text), quote=True)}"')
    return f"<tg-button {' '.join(attrs)}>{t}</tg-button>"


def tg_button_row(
    buttons: list[str],
    *,
    align: str = "center",
) -> str:
    """
    Official button row block: <tg-button-row align="...">...</tg-button-row>
    1-8 buttons per row.
    """
    if not buttons:
        return ""
    al = align if align in ("left", "center", "right") else "center"
    body = "".join(buttons[:8])
    return f'<tg-button-row align="{al}">{body}</tg-button-row>'


def nav_button_row(
    unit_id: str,
    page: int,
    total: int,
    *,
    prefix: str = "hk",
) -> str:
    """Prev / page indicator / Next as official Rich buttons."""
    if total <= 1:
        return ""
    page = max(0, min(page, total - 1))
    btns = []
    if page > 0:
        btns.append(
            tg_button(
                "◀",
                type="callback_data",
                data=f"{prefix}|{unit_id}|p|{page - 1}",
                style="primary",
            )
        )
    btns.append(
        tg_button(
            f"{page + 1}/{total}",
            type="callback_data",
            data=f"{prefix}|{unit_id}|p|{page}",
            style="link",
        )
    )
    if page < total - 1:
        btns.append(
            tg_button(
                "▶",
                type="callback_data",
                data=f"{prefix}|{unit_id}|p|{page + 1}",
                style="primary",
            )
        )
    return tg_button_row(btns, align="center")


def markup_to_tg_rows(markup: list, unit_id: str = "") -> str:
    """
    Convert Hikkari reply_markup (list of rows of dicts) to official <tg-button-row> HTML.
    """
    if not markup:
        return ""
    import html as html_mod
    rows_out = []
    for row in markup:
        if not isinstance(row, (list, tuple)):
            row = [row]
        btns = []
        for btn in row:
            if not isinstance(btn, dict):
                continue
            text = str(btn.get("text") or "•")[:64]
            if btn.get("url"):
                btns.append(tg_button(text, type="url", url=str(btn["url"]), style=btn.get("style")))
            elif btn.get("web_app"):
                btns.append(tg_button(text, type="web_app", url=str(btn["web_app"]), style=btn.get("style") or "primary"))
            else:
                # callback — prefer pre-assigned _callback_data from form system
                data = btn.get("_callback_data") or btn.get("data") or "noop"
                if unit_id and not str(data).startswith(("hk|", "rh|")):
                    # keep form's short data; events still match unit buttons
                    data = str(data)[:64]
                style = btn.get("style") or "primary"
                btns.append(tg_button(text, type="callback_data", data=str(data)[:64], style=style))
        if btns:
            rows_out.append(tg_button_row(btns, align="center"))
    return "\n".join(rows_out)




def to_rich_compatible(html: str) -> str:
    """Normalize classic / Heroku-style HTML to official Rich HTML tags."""
    if not html or not isinstance(html, str):
        return html or ""
    # Strip HTML comments (break some parsers)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    # <emoji document_id=ID>X</emoji> → <tg-emoji emoji-id="ID">X</tg-emoji>
    html = re.sub(
        r'<emoji\s+document_id=["\']?(\d+)["\']?\s*>\s*([^<]*)</emoji>',
        r'<tg-emoji emoji-id="\1">\2</tg-emoji>',
        html,
        flags=re.I,
    )
    html = re.sub(
        r'<tg-emoji\s+emoji-id=(\d+)\s*>',
        r'<tg-emoji emoji-id="\1">',
        html,
        flags=re.I,
    )
    # Normalize <table ...> → bordered striped compact (drop unknown attrs like padding)
    html = re.sub(
        r"<table\b[^>]*>",
        '<table bordered striped compact>',
        html,
        flags=re.I,
    )
    # <button url="URL">text</button>
    def _btn_url(m: re.Match) -> str:
        url = m.group(1)
        text = (m.group(2) or "•").strip()
        return f'<tg-button type="url" style="primary" url="{url}">{text}</tg-button>'
    html = re.sub(
        r'<button\s+url=["\']([^"\']+)["\']\s*>(.*?)</button>',
        _btn_url,
        html,
        flags=re.I | re.S,
    )
    # <button switch="query">text</button>
    def _btn_sw(m: re.Match) -> str:
        q = m.group(1) or ""
        text = (m.group(2) or "•").strip()
        return (
            f'<tg-button type="switch_inline_query_current_chat" '
            f'style="primary" query="{q}">{text}</tg-button>'
        )
    html = re.sub(
        r'<button\s+switch=["\']([^"\']*)["\']\s*>(.*?)</button>',
        _btn_sw,
        html,
        flags=re.I | re.S,
    )
    # Wrap loose tg-buttons into a row
    if "<tg-button" in html and "tg-button-row" not in html.lower():
        def _wrap_row(m: re.Match) -> str:
            return f'<tg-button-row align="center">{m.group(0)}</tg-button-row>'
        html = re.sub(
            r'(?:<tg-button\b[^>]*>.*?</tg-button>\s*){1,8}',
            _wrap_row,
            count=1,
            string=html,
            flags=re.I | re.S,
        )
    return html



def parse_rich_url_buttons(spec: str) -> str:
    """
    Config string "Text|https://..., Text2|url2" → official <tg-button-row> HTML.
    """
    if not spec or not str(spec).strip():
        return ""
    btns = []
    for part in str(spec).split(","):
        part = part.strip()
        if "|" not in part:
            continue
        t, u = part.split("|", 1)
        t, u = t.strip(), u.strip()
        if t and u.startswith(("http://", "https://", "tg://")):
            btns.append(tg_button(t, type="url", url=u, style="primary"))
    if not btns:
        return ""
    # split into rows of max 3
    rows = []
    for i in range(0, len(btns), 3):
        rows.append(tg_button_row(btns[i : i + 3], align="center"))
    return "\n".join(rows)


async def edit_rich_message(
    token: str,
    html: str,
    *,
    inline_message_id: str | None = None,
    chat_id: int | str | None = None,
    message_id: int | None = None,
) -> bool:
    """
    Edit an existing message to a Rich Message (Bot API editMessageText + rich_message).
    """
    if not token or not html:
        return False
    payload: dict[str, Any] = {
        "rich_message": {
            "html": html,
            "skip_entity_detection": True,
        },
    }
    if inline_message_id:
        payload["inline_message_id"] = str(inline_message_id)
    elif chat_id is not None and message_id is not None:
        payload["chat_id"] = chat_id
        payload["message_id"] = int(message_id)
    else:
        return False
    url = API.format(token=token, method="editMessageText")
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
                if not data.get("ok"):
                    logger.warning(
                        "editMessageText(rich) failed: %s",
                        data.get("description") or data,
                    )
                    return False
                return True
    except Exception as e:
        logger.warning("editMessageText(rich) error: %s", e)
        return False


def html_table(
    rows: list[tuple[str, str]],
    *,
    header: tuple[str, str] = ("Component", "Current release"),
) -> str:
    import html as html_mod
    h0, h1 = header
    body = [
        f"<tr><th>{html_mod.escape(str(h0))}</th>"
        f"<th>{html_mod.escape(str(h1))}</th></tr>"
    ]
    for k, v in rows:
        ks = html_mod.escape(str(k))
        vs = str(v)
        # keep intentional HTML (code, links, emoji) if already tagged
        if not ("<" in vs and ">" in vs):
            vs = html_mod.escape(vs)
        body.append(f"<tr><td>{ks}</td><td>{vs}</td></tr>")
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
