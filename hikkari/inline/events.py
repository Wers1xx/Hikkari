import contextlib
# ©️ Dan Gazizullin (hikariatama), 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
#
# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/coddrago/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
#
# ©️ Wers1xx, 2025-2026
# This file is a part of Hikkari Userbot
# 🌐 https://github.com/Wers1xx/Hikkari
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import contextlib
import inspect
import logging
import typing
from asyncio import Event

from hikkaritl.tl.types import UpdateBotInlineSend

from .. import utils, security
from .types import BotInlineCall, InlineCall, InlineQuery, InlineUnit

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager

logger = logging.getLogger(__name__)


class Events(InlineUnit):
    async def _message_handler(self: "InlineManager", message):
        """Processes incoming messages"""
        if not message.is_private:
            return

        # Config "enter value" PM fallback (when chosen_inline is unavailable)
        pending = getattr(self, "_pending_config_input", None) or {}
        uid = getattr(message, "sender_id", None) or getattr(
            getattr(message, "from_id", None), "user_id", None
        )
        if uid in pending and (message.raw_text or message.message):
            value = (message.raw_text or message.message or "").strip()
            # Ignore transfer placeholder / empty
            if (
                not value
                or "Transferring value" in value
                or "will be deleted automatically" in value
            ):
                return
            entry = pending.pop(uid, None)
            if entry:
                try:
                    handler, unit_id, args, kwargs = entry
                    from .types import InlineCall

                    self_ref = self

                    class _PmCall:
                        id = f"pm-{uid}"
                        data = b""
                        chat_id = uid
                        message_id = getattr(message, "id", None)
                        inline_message_id = None
                        sender_id = uid
                        query = None

                        async def answer(self, *a, **k):
                            return None

                        async def edit(self, *a, **k):
                            try:
                                return await self_ref._edit_unit(
                                    *a, unit_id=unit_id, **k
                                )
                            except Exception:
                                return False

                    call = InlineCall(_PmCall(), self, unit_id)
                    await handler(call, value, *args, **kwargs)
                    with contextlib.suppress(Exception):
                        await message.delete()
                    return
                except Exception:
                    logger.exception("Pending config PM input failed")

        wrapped_message = self._bot_message(message)
        match True:
            case _ if (
                wrapped_message.chat.type != "private"
                or wrapped_message.text == "/start hikkari init"
            ):
                return

        for mod in self._allmodules.modules:
            if (
                not hasattr(mod, "bot_watcher")
                or wrapped_message.text == "/start"
                and mod.__class__.__name__ != "InlineStuff"
            ):
                continue

            try:
                await mod.bot_watcher(wrapped_message)
            except Exception:
                logger.exception("Error on running bot watcher!")

    def _bot_message(self: "InlineManager", message):
        from .types import BotInlineMessage

        return BotInlineMessage(self, message=message)

    async def _inline_handler(self: "InlineManager", inline_query):
        """Inline query handler (forms' calls)"""
        wrapped_query = InlineQuery(inline_query=inline_query)
        inline_query.inline_manager = self
        uid = getattr(wrapped_query.from_user, "id", None) or wrapped_query.sender_id
        owners = []
        try:
            owners = list(self._client.dispatcher.security._owner or [])
        except Exception:
            pass
        all_users = []
        try:
            all_users = list(self._client.dispatcher.security.all_users or [])
        except Exception:
            pass
        # Owner / self always allowed (fixes empty inline results / No query results)
        if not (
            self._db.get(security.__name__, "allow_inline_query", False)
            or uid == self._me
            or uid in owners
            or uid in all_users
        ):
            logger.debug("Inline query denied for user %s", uid)
            return

        if not (query := wrapped_query.query):
            await self._query_help(wrapped_query)
            return

        cmd = query.split()[0].lower()
        if (
            cmd in self._allmodules.inline_handlers
            and await self.check_inline_security(
                func=self._allmodules.inline_handlers[cmd],
                user=wrapped_query.from_user.id,
            )
        ):
            try:
                if not (
                    result := await self._allmodules.inline_handlers[cmd](wrapped_query)
                ):
                    return
            except Exception:
                logger.exception("Error on running inline watcher!")
                return

            if isinstance(result, dict):
                result = [result]

            if not isinstance(result, list):
                logger.error(
                    "Got invalid type from inline handler. It must be `dict`, got `%s`",
                    type(result),
                )
                await wrapped_query.e500()
                return

            for res in result:
                mandatory = ["message", "photo", "gif", "video", "file"]
                if all(item not in res for item in mandatory):
                    logger.error(
                        (
                            "Got invalid type from inline handler. It must contain one"
                            " of `%s`"
                        ),
                        mandatory,
                    )
                    await wrapped_query.e500()
                    return

                if "file" in res and "mime_type" not in res:
                    logger.error(
                        "Got invalid type from inline handler. It contains field"
                        " `file`, so it must contain `mime_type` as well"
                    )

            try:
                await wrapped_query.answer(
                    [
                        await self._build_inline_result(wrapped_query, res)
                        for res in result
                    ],
                    cache_time=0,
                )
            except Exception:
                logger.exception(
                    "Exception when answering inline query with result from %s",
                    cmd,
                )
                return

        await self._form_inline_handler(wrapped_query)
        await self._gallery_inline_handler(wrapped_query)
        await self._list_inline_handler(wrapped_query)

    async def _build_inline_result(
        self: "InlineManager", query: InlineQuery, res: dict
    ):
        buttons = self.generate_markup(res.get("reply_markup"))
        match True:
            case _ if "message" in res:
                return await query.builder.article(
                    title=self.sanitise_text(res["title"]),
                    description=self.sanitise_text(res.get("description")),
                    text=self.sanitise_text(res["message"]),
                    parse_mode="HTML",
                    link_preview=False,
                    thumb=self._web_document(res.get("thumb")),
                    buttons=buttons,
                    id=utils.rand(20),
                )
            case _ if "photo" in res:
                return await query.builder.photo(
                    res["photo"],
                    text=self.sanitise_text(res.get("caption")),
                    parse_mode="HTML",
                    buttons=buttons,
                    id=utils.rand(20),
                )
            case _ if "gif" in res:
                return await query.builder.document(
                    res["gif"],
                    title=self.sanitise_text(res.get("title")),
                    type="gif",
                    text=self.sanitise_text(res.get("caption")),
                    parse_mode="HTML",
                    buttons=buttons,
                    id=utils.rand(20),
                )
            case _ if "video" in res:
                return await query.builder.document(
                    res["video"],
                    title=self.sanitise_text(res.get("title")),
                    description=self.sanitise_text(res.get("description")),
                    type="video",
                    mime_type="video/mp4",
                    text=self.sanitise_text(res.get("caption")),
                    parse_mode="HTML",
                    buttons=buttons,
                    id=utils.rand(20),
                )
            case _:
                return await query.builder.document(
                    res["file"],
                    title=self.sanitise_text(res.get("title")),
                    description=self.sanitise_text(res.get("description")),
                    mime_type=res["mime_type"],
                    text=self.sanitise_text(res.get("caption")),
                    parse_mode="HTML",
                    buttons=buttons,
                    id=utils.rand(20),
                )


    def _inline_allowed_users(
        self: "InlineManager",
        unit: dict | None = None,
        button: dict | None = None,
    ) -> set[int]:
        """Owner account + security owners + per-unit/button always_allow."""
        allowed: set[int] = set()
        with contextlib.suppress(Exception):
            if self._me:
                allowed.add(int(self._me))
        with contextlib.suppress(Exception):
            for x in self._client.dispatcher.security._owner or []:
                allowed.add(int(x))
        if unit:
            with contextlib.suppress(Exception):
                for x in unit.get("always_allow") or []:
                    allowed.add(int(x))
        if button:
            with contextlib.suppress(Exception):
                for x in button.get("always_allow") or []:
                    allowed.add(int(x))
        return allowed

    def _inline_user_allowed(
        self: "InlineManager",
        user_id: int,
        unit: dict | None = None,
        button: dict | None = None,
    ) -> bool:
        """Only account owner and co-owners may use inline forms/buttons by default."""
        if user_id is None:
            return False
        # Explicit public button (rare): both flags must opt-in
        if button and button.get("allow_public") is True:
            return True
        if unit and unit.get("allow_public") is True:
            return True
        return int(user_id) in self._inline_allowed_users(unit, button)


    async def _callback_query_handler(
        self: "InlineManager",
        call,
        reply_markup: None | (list[list[dict[str, typing.Any]]]) = None,
    ):
        """Callback query handler (buttons' presses)"""
        if reply_markup is None:
            reply_markup = []

        call_data = (
            call.data.decode("utf-8", errors="ignore")
            if isinstance(call.data, (bytes, bytearray))
            else call.data
        )
        user_id = call.sender_id

        # --- Official Rich Message navigation (Bot API 10.3 <tg-button>) ---
        # callback_data format: hk|<unit_id>|p|<page>
        if isinstance(call_data, str) and call_data.startswith("hk|"):
            try:
                parts = call_data.split("|")
                if len(parts) >= 4 and parts[2] == "p":
                    uid = parts[1]
                    try:
                        new_page = int(parts[3])
                    except ValueError:
                        await call.answer("Bad page")
                        return
                    unit = self._units.get(uid)
                    if not unit or unit.get("type") != "rich":
                        # stop spinner even on expired
                        with contextlib.suppress(Exception):
                            await call.answer("Expired — run .help again")
                        return
                    if not self._inline_user_allowed(user_id, unit):
                        await call.answer("⛔")
                        return
                    pages = unit.get("pages") or []
                    if not pages:
                        await call.answer()
                        return
                    new_page = max(0, min(new_page, len(pages) - 1))
                    if new_page == unit.get("page"):
                        await call.answer(f"{new_page + 1}/{len(pages)}")
                        return
                    # Answer FIRST so Telegram stops the loading spinner
                    with contextlib.suppress(Exception):
                        await call.answer(f"{new_page + 1}/{len(pages)}")
                    from ..utils.rich_api import (
                        edit_rich_message,
                        _find_bot_token,
                    )
                    # Page HTML only — navigation lives in reply_markup under the message
                    body = pages[new_page]
                    unit["page"] = new_page
                    unit["rich_html"] = body
                    token = _find_bot_token(self._client)
                    imid = (
                        getattr(call, "inline_message_id", None)
                        or getattr(call, "inlineMessageId", None)
                    )
                    ok = False
                    if token and imid:
                        ok = await edit_rich_message(
                            str(token), body, inline_message_id=str(imid)
                        )
                    if not ok and token:
                        chat_id = getattr(call, "chat_id", None)
                        if chat_id is None:
                            msg = getattr(call, "message", None)
                            if msg is not None:
                                chat = getattr(msg, "chat", None)
                                chat_id = getattr(chat, "id", None) if chat else None
                        mid = getattr(call, "message_id", None)
                        if mid is None:
                            msg = getattr(call, "message", None)
                            mid = getattr(msg, "message_id", None) or getattr(msg, "id", None)
                        if chat_id is not None and mid is not None:
                            ok = await edit_rich_message(
                                str(token),
                                body,
                                chat_id=chat_id,
                                message_id=int(mid),
                            )
                    if not ok:
                        logger.warning(
                            "rich nav edit failed unit=%s page=%s imid=%s",
                            uid,
                            new_page,
                            imid,
                        )
                    else:
                        # Refresh under-message keyboard page indicator
                        try:
                            import aiohttp
                            from ..utils.rich_api import API
                            nav_row = []
                            if new_page > 0:
                                nav_row.append({"text": "◀", "callback_data": f"hk|{uid}|p|{new_page - 1}"})
                            nav_row.append({"text": f"{new_page + 1}/{len(pages)}", "callback_data": f"hk|{uid}|p|{new_page}"})
                            if new_page < len(pages) - 1:
                                nav_row.append({"text": "▶", "callback_data": f"hk|{uid}|p|{new_page + 1}"})
                            rm = {"inline_keyboard": [nav_row]}
                            payload = {"reply_markup": rm}
                            if imid:
                                payload["inline_message_id"] = str(imid)
                            else:
                                payload["chat_id"] = chat_id
                                payload["message_id"] = int(mid)
                            url = API.format(token=str(token), method="editMessageReplyMarkup")
                            async with aiohttp.ClientSession() as session:
                                async with session.post(url, json=payload) as resp:
                                    await resp.json(content_type=None)
                        except Exception:
                            logger.debug("rich nav markup refresh failed", exc_info=True)
                    return
            except Exception:
                logger.exception("rich nav callback failed")
                with contextlib.suppress(Exception):
                    await call.answer("Error", show_alert=True)


        # --- Hikkari Config Rich buttons (Bot API sendRichMessage + tg-button) ---
        if isinstance(call_data, str) and call_data.startswith("cfg|"):
            try:
                with contextlib.suppress(Exception):
                    await call.answer()
                action = call_data.split("|", 1)[1] if "|" in call_data else ""
                # Find HikkariConfig / Config module
                mod = None
                for m in getattr(self._allmodules, "modules", []) or []:
                    n = getattr(m, "name", "") or getattr(getattr(m, "strings", {}), "get", lambda *_: "")("name")
                    if n in ("HikkariConfig", "Config", "Hikkari Config") or "config" in str(type(m).__name__).lower():
                        if hasattr(m, "inline__global_config") or hasattr(m, "inline__choose_category"):
                            mod = m
                            break
                if mod is None:
                    for m in getattr(self._allmodules, "modules", []) or []:
                        if hasattr(m, "inline__global_config"):
                            mod = m
                            break
                if mod is None:
                    await call.answer("Config module not found", show_alert=True)
                    return
                # Use module-level imports (local import would shadow InlineCall for whole fn)
                icall = (InlineCall if getattr(call, "via_inline", False) else BotInlineCall)(
                    call, self, None
                )
                if action == "builtin":
                    await mod.inline__global_config(icall, obj_type=True)
                elif action == "external":
                    await mod.inline__global_config(icall, obj_type=False)
                elif action == "close":
                    with contextlib.suppress(Exception):
                        await call.answer()
                    with contextlib.suppress(Exception):
                        if hasattr(call, "edit"):
                            await call.edit("✖️", reply_markup=None)
                    with contextlib.suppress(Exception):
                        await call.delete()
                    with contextlib.suppress(Exception):
                        await self._close_unit_handler(call)
                else:
                    await call.answer(action or "ok")
                return
            except Exception:
                logger.exception("cfg rich callback failed")
                with contextlib.suppress(Exception):
                    await call.answer("Error", show_alert=True)
                return

        for func in self._allmodules.callback_handlers.values():
            if await self.check_inline_security(func=func, user=user_id):
                try:
                    await func(
                        (InlineCall if call.via_inline else BotInlineCall)(
                            call, self, None
                        ),
                    )
                except Exception:
                    logger.exception("Error on running callback watcher!")
                    await call.answer(
                        "Error occured while processing request. More info in logs",
                        alert=True,
                    )
                    continue

        for unit_id, unit in self._units.copy().items():
            for button in utils.array_sum(unit.get("buttons", [])):
                if not isinstance(button, dict):
                    logger.warning(
                        "Can't process update, because of corrupted button: %s",
                        button,
                    )
                    continue

                if button.get("_callback_data") == call_data:
                    # Strict: only account owner + co-owners (unless allow_public)
                    if not self._inline_user_allowed(user_id, unit, button):
                        with contextlib.suppress(Exception):
                            await call.answer(
                                self.translator.getkey("inline.button403")
                                if hasattr(self, "translator")
                                else "⛔"
                            )
                        return

                    # Answer ASAP so the button does not spin forever
                    with contextlib.suppress(Exception):
                        await call.answer()

                    try:
                        result = await button["callback"](
                            (InlineCall if call.via_inline else BotInlineCall)(
                                call, self, unit_id
                            ),
                            *button.get("args", []),
                            **button.get("kwargs", {}),
                        )
                    except Exception:
                        logger.exception("Error on running callback watcher!")
                        with contextlib.suppress(Exception):
                            await call.answer(
                                "Error occurred while processing request. More info in logs",
                                alert=True,
                            )
                        return

                    return result

        if call_data in self._custom_map:
            entry = self._custom_map[call_data]
            owners = set()
            with contextlib.suppress(Exception):
                owners.add(int(self._me))
            with contextlib.suppress(Exception):
                owners |= {int(x) for x in (self._client.dispatcher.security._owner or [])}

            allowed = self._inline_user_allowed(user_id, entry if isinstance(entry, dict) else None)
            if entry.get("allow_public") is True or entry.get("disable_security") is True:
                allowed = True
            if not allowed and user_id in (entry.get("always_allow") or []):
                allowed = True
            if not allowed and entry.get("force_me", False) and user_id == self._me:
                allowed = True
            if not allowed and user_id == self._me:
                allowed = True
            if not allowed:
                with contextlib.suppress(Exception):
                    allowed = await self.check_inline_security(
                        func=entry.get(
                            "perms_map",
                            lambda: self._client.dispatcher.security._default,
                        )(),
                        user=user_id,
                    )

            if not allowed:
                await call.answer(self.translator.getkey("inline.button403"), alert=True)
                return

            args = entry.get("args", ()) or ()
            if isinstance(args, dict):
                args = ()
            kwargs = entry.get("kwargs", {}) or {}
            if not isinstance(kwargs, dict):
                kwargs = {}

            icall = (InlineCall if getattr(call, "via_inline", False) else BotInlineCall)(
                call, self, None
            )
            # attach unit_id if handler is list/gallery partial
            await entry["handler"](icall, *args, **kwargs)
            return

    async def _chosen_inline_handler(
        self: "InlineManager",
        chosen_inline_query,
    ):
        """Handle chosen inline result (config "enter value", etc).

        Mirrors Heroku: match input button by _switch_query, pass value to handler.
        """
        if not isinstance(chosen_inline_query, UpdateBotInlineSend):
            # Some TL layers may wrap the update
            if not hasattr(chosen_inline_query, "query"):
                return

        query = getattr(chosen_inline_query, "query", None)
        if not query:
            return

        query = str(query)
        query_key = query.strip().split()[0] if query.strip() else ""
        user_id = getattr(chosen_inline_query, "user_id", None)
        msg_id = getattr(chosen_inline_query, "msg_id", None)

        logger.debug(
            "chosen_inline: query=%r user=%s msg_id=%s units=%s",
            query[:80],
            user_id,
            msg_id,
            list(self._units.keys())[:10],
        )

        # Form open: unit_id was the full query
        for unit_id, unit in self._units.items():
            if (
                unit_id in (query, query_key)
                and "future" in unit
                and isinstance(unit["future"], Event)
            ):
                if msg_id is not None:
                    unit["inline_message_id"] = msg_id
                unit["future"].set()
                return

        owners = [self._me]
        try:
            owners += list(self._client.dispatcher.security._owner or [])
        except Exception:
            pass

        for unit_id, unit in self._units.copy().items():
            buttons = unit.get("buttons", [])
            try:
                flat = utils.array_sum(buttons)
            except Exception:
                flat = []
                for row in buttons or []:
                    if isinstance(row, list):
                        flat.extend(row)
                    else:
                        flat.append(row)

            for button in flat:
                if not isinstance(button, dict):
                    continue
                if "_switch_query" not in button or "input" not in button:
                    continue
                if button["_switch_query"] != query_key:
                    continue
                if not button.get("handler"):
                    logger.warning(
                        "Input button %s has no handler", button.get("text")
                    )
                    continue

                always_allow = unit.get("always_allow", []) or []
                if user_id is not None and user_id not in owners + list(always_allow):
                    logger.warning(
                        "chosen_inline rejected: user %s not in owners %s",
                        user_id,
                        owners,
                    )
                    continue

                value = (
                    query.split(maxsplit=1)[1] if len(query.split()) > 1 else ""
                )

                if msg_id is not None:
                    unit["inline_message_id"] = msg_id

                class ChosenInlineCall:
                    data = b""
                    chat_id = None
                    message_id = None

                    def __init__(self, update):
                        self.id = getattr(update, "id", None)
                        self.sender_id = getattr(update, "user_id", None)
                        self.query = update
                        # Heroku-compatible: expose msg_id on query
                        try:
                            self.query.msg_id = getattr(update, "msg_id", None)
                        except Exception:
                            pass
                        self.inline_message_id = getattr(update, "msg_id", None)
                        self.chat_id = unit.get("chat")
                        self.message_id = unit.get("message_id")

                    async def answer(self, *args, **kwargs):
                        return None

                try:
                    call = InlineCall(
                        ChosenInlineCall(chosen_inline_query), self, unit_id
                    )
                    # Prefer live msg_id on the call/unit
                    if msg_id is not None:
                        call.inline_message_id = msg_id
                        unit["inline_message_id"] = msg_id

                    handler = button["handler"]
                    args = list(button.get("args") or [])
                    kwargs = dict(button.get("kwargs") or {})

                    # Config handlers: (mod, option, inline_message_id)
                    if len(args) >= 3:
                        args[2] = call.inline_message_id or args[2]
                        kwargs.pop("inline_message_id", None)
                    elif call.inline_message_id is not None:
                        kwargs.setdefault(
                            "inline_message_id", call.inline_message_id
                        )

                    if not (value or "").strip():
                        # User selected result without typing a value — keep pending
                        logger.debug(
                            "chosen_inline empty value for %s — ignored",
                            unit_id,
                        )
                        return
                    if "Transferring value" in value:
                        logger.debug("chosen_inline transfer text ignored")
                        return
                    logger.info(
                        "chosen_inline → handler %s value=%r unit=%s",
                        getattr(handler, "__name__", handler),
                        value[:50],
                        unit_id,
                    )
                    # Clear PM-fallback pending so next chat message is NOT saved as config
                    try:
                        pend = getattr(self, "_pending_config_input", None)
                        if isinstance(pend, dict) and user_id in pend:
                            pend.pop(user_id, None)
                    except Exception:
                        pass
                    return await handler(call, value, *args, **kwargs)
                except Exception:
                    logger.exception(
                        "Exception while running chosen query watcher!"
                    )
                    return

        # Fallback: config rich input_map (buttons registered outside unit)
        entry = None
        with contextlib.suppress(Exception):
            imap = getattr(self, "_input_map", None) or {}
            entry = imap.get(query_key) or imap.get(str(query_key).strip())
        if entry and callable(entry.get("handler")):
            value = (
                query.split(maxsplit=1)[1] if len(query.split()) > 1 else ""
            )
            if not (value or "").strip() or "Transferring value" in value:
                return
            try:
                unit_id = entry.get("unit_id")
                unit = (
                    self._units.get(unit_id)
                    if unit_id and getattr(self, "_units", None)
                    else None
                )
                chat = unit.get("chat") if isinstance(unit, dict) else None
                mid = unit.get("message_id") if isinstance(unit, dict) else None

                class ChosenInlineCall:
                    data = b""

                    def __init__(self, update, chat_id, message_id):
                        self.id = getattr(update, "id", None)
                        self.sender_id = getattr(update, "user_id", None)
                        self.query = update
                        self.inline_message_id = getattr(update, "msg_id", None)
                        self.chat_id = chat_id
                        self.message_id = message_id

                    async def answer(self, *args, **kwargs):
                        return None

                call = InlineCall(
                    ChosenInlineCall(chosen_inline_query, chat, mid),
                    self,
                    unit_id,
                )
                if msg_id is not None:
                    call.inline_message_id = msg_id
                handler = entry["handler"]
                args = list(entry.get("args") or [])
                kwargs = dict(entry.get("kwargs") or {})
                if len(args) >= 3:
                    args[2] = getattr(call, "inline_message_id", None) or args[2]
                elif getattr(call, "inline_message_id", None) is not None:
                    kwargs.setdefault(
                        "inline_message_id", call.inline_message_id
                    )
                logger.info(
                    "chosen_inline input_map → %s value=%r",
                    getattr(handler, "__name__", handler),
                    value[:50],
                )
                return await handler(call, value, *args, **kwargs)
            except Exception:
                logger.exception("chosen_inline input_map failed")
                return

        logger.debug(
            "chosen_inline: no matching input button for key=%r", query_key
        )

    async def _query_help(self: "InlineManager", inline_query: InlineQuery):
        _help = []
        for name, fun in self._allmodules.inline_handlers.items():
            if not await self.check_inline_security(
                func=fun,
                user=inline_query.from_user.id,
            ):
                continue

            try:
                doc = inspect.getdoc(fun)
            except Exception:
                doc = "🦥 No docs"

            try:
                thumb = getattr(fun, "thumb_url", None) or fun.__self__.hikkari_meta_pic
            except Exception:
                thumb = None

            thumb = thumb or "https://img.icons8.com/fluency/50/000000/info-squared.png"

            _help += [
                (
                    await inline_query.builder.article(
                        title=self.translator.getkey("inline.command").format(name),
                        description=doc,
                        text=(
                            self.translator.getkey("inline.command_msg").format(
                                utils.escape_html(name),
                                utils.escape_html(doc),
                            )
                        ),
                        parse_mode="HTML",
                        link_preview=False,
                        thumb=self._web_document(thumb),
                        buttons=self.generate_markup(
                            {
                                "text": self.translator.getkey("inline.run_command"),
                                "switch_inline_query_current_chat": f"{name} ",
                            }
                        ),
                        id=utils.rand(20),
                    ),
                    (
                        f"🎹 <code>@{self.bot_username} {utils.escape_html(name)}</code>"
                        f" - {utils.escape_html(doc)}\n"
                    ),
                )
            ]

        if not _help:
            await inline_query.answer(
                [
                    await inline_query.builder.article(
                        title=self.translator.getkey("inline.show_inline_cmds"),
                        description=self.translator.getkey("inline.no_inline_cmds"),
                        text=self.translator.getkey("inline.no_inline_cmds_msg"),
                        parse_mode="HTML",
                        link_preview=False,
                        thumb=self._web_document(
                            "https://img.icons8.com/fluency/50/000000/info-squared.png"
                        ),
                        id=utils.rand(20),
                    )
                ],
                cache_time=0,
            )
            return

        await inline_query.answer(
            [
                await inline_query.builder.article(
                    title=self.translator.getkey("inline.show_inline_cmds"),
                    description=(
                        self.translator.getkey("inline.inline_cmds").format(len(_help))
                    ),
                    text=(
                        self.translator.getkey("inline.inline_cmds_msg").format(
                            "\n".join(map(lambda x: x[1], _help))
                        )
                    ),
                    parse_mode="HTML",
                    link_preview=False,
                    thumb=self._web_document(
                        "https://img.icons8.com/fluency/50/000000/info-squared.png"
                    ),
                    id=utils.rand(20),
                )
            ]
            + [i[0] for i in _help],
            cache_time=0,
        )
