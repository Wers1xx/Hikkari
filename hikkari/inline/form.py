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
from pathlib import Path
import copy
import logging
import os
import random
import time
import traceback
import typing
from collections.abc import Callable
import asyncio
from asyncio import Event
from urllib.parse import urlparse

import grapheme
from hikkaritl.errors.rpcerrorlist import ChatSendInlineForbiddenError
from hikkaritl.tl.types import InputGeoPoint, Message

from .. import main, utils
from ..types import HikkariReplyMarkup
from .types import InlineMessage, InlineUnit

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager

logger = logging.getLogger(__name__)

VERIFICATION_EMOJIES = list(
    grapheme.graphemes(
        "👨‍🏫👩‍🏫👨‍🎤🧑‍🎤👩‍🎤👨‍🎓👩‍🎓👩‍🍳👩‍🌾👩‍⚕️🕵️‍♀️💂‍♀️👷‍♂️👮‍♂️👴🧑‍🦳👩‍🦳👱‍♀️👩‍🦰👨‍🦱👩‍⚖️🧙‍♂️🧝‍♀️🧛‍♀️"
        "🎅🧚‍♂️🙆‍♀️🙍‍♂️👩‍👦🧶🪢🪡🧵🩲👖👕👚🦺👗👙🩱👘🥻🩴🥿🧦🥾👟👞"
        "👢👡👠🪖👑💍👝👛👜💼🌂🥽🕶👓🧳🎒🐶🐱🐭🐹🐰🦊🐻🐷🐮"
        "🦁🐯🐨🐻‍❄️🐼🐽🐸🐵🙈🙉🙊🐒🦆🐥🐣🐤🐦🐧🐔🦅🦉🦇🐺🐗🐴"
        "🦄🐜🐞🐌🦋🐛🪱🐝🪰🪲🪳🦟🦗🕷🕸🐙🦕🦖🦎🐍🐢🦂🦑🦐🦞"
        "🦀🐡🐠🐟🐅🐊🦭🦈🐋🐳🐬🐆🦓🦍🦧🦣🐘🦛🐃🦬🦘🦒🐫🐪🦏"
        "🐂🐄🐎🐖🐏🐑🦙🐈🐕‍🦺🦮🐩🐕🦌🐐🐈‍⬛🪶🐓🦃🦤🦚🦜🦡🦨🦝🐇"
        "🕊🦩🦢🦫🦦🦥🐁🐀🐿🦔🌳🌲🌵🐲🐉🐾🎋🍂🍁🍄🐚🌾🪨💐🌷"
        "🥀🌺🌸🌻🌞🌜🌘🌗🌎✨💫⭐️✨⚡️☄️💥☀️🌪🔥🌈🌤⛅️❄️⛄️🌊"
        "☂️🍏🍎🍐🍊🍋🍌🍉🥭🍑🍒🍈🫐🍓🍇🍍🥥🥝🍅🥑🥦🧔‍♂️"
    )
)


class Placeholder:
    """Placeholder"""

class Form(InlineUnit):
    async def form(
        self: "InlineManager",
        text: str,
        message: Message | int,
        reply_markup: HikkariReplyMarkup | None = None,
        *,
        force_me: bool = False,
        always_allow: list[int] | None = None,
        manual_security: bool = False,
        disable_security: bool = False,
        ttl: int | None = None,
        on_unload: Callable | None = None,
        photo: str | None = None,
        gif: str | None = None,
        file: str | None = None,
        mime_type: str | None = None,
        video: str | None = None,
        location: str | None = None,
        audio: dict | str | None = None,
        silent: bool = False,
    ) -> InlineMessage | bool:
        """
        Send inline form to chat
        :param text: Content of inline form. HTML markdown supported
        :param message: Where to send inline. Can be either `Message` or `int`
        :param reply_markup: List of buttons to insert in markup. List of dicts with keys: text, callback
        :param force_me: Either this form buttons must be pressed only by owner scope or no
        :param always_allow: Users, that are allowed to press buttons in addition to previous rules
        :param ttl: Time, when the form is going to be unloaded. Unload means, that the form
                    buttons with inline queries and callback queries will become unusable, but
                    buttons with type url will still work as usual. Pay attention, that ttl can't
                    be bigger, than default one (1 day) and must be either `int` or `False`
        :param on_unload: Callback, called when form is unloaded and/or closed. You can clean up trash
                          or perform another needed action
        :param manual_security: By default, Hikkari will try to inherit inline buttons security from the caller (command)
                                If you want to avoid this, pass `manual_security=True`
        :param disable_security: By default, Hikkari will try to inherit inline buttons security from the caller (command)
                                 If you want to disable all security checks on this form in particular, pass `disable_security=True`
        :param photo: Attach a photo to the form. URL must be supplied
        :param gif: Attach a gif to the form. URL must be supplied
        :param file: Attach a file to the form. URL must be supplied
        :param mime_type: Only needed, if `file` field is not empty. Must be either 'application/pdf' or 'application/zip'
        :param video: Attach a video to the form. URL must be supplied
        :param location: Attach a map point to the form. List/tuple must be supplied (latitude, longitude)
                         Example: (55.749931, 48.742371)
                         ⚠️ If you pass this parameter, you'll need to pass empty string to `text` ⚠️
        :param audio: Attach a audio to the form. Dict or URL must be supplied
        :param silent: Whether the form must be sent silently (w/o "Opening form..." message)
        :return: If form is sent, returns :obj:`InlineMessage`, otherwise returns `False`
        """
        with contextlib.suppress(AttributeError):
            _hikkari_client_id_logging_tag = copy.copy(self._client.tg_id)  # noqa: F841

        if reply_markup is None:
            reply_markup = []

        if always_allow is None:
            always_allow = []

        if not isinstance(text, str):
            logger.error(
                "Invalid type for `text`. Expected `str`, got `%s`",
                type(text),
            )
            return False

        text = self.sanitise_text(text)
        needs_premium_emoji_pre_edit = self._needs_premium_emoji_pre_edit(text)

        if not isinstance(silent, bool):
            logger.error(
                "Invalid type for `silent`. Expected `bool`, got `%s`",
                type(silent),
            )
            return False

        if not isinstance(manual_security, bool):
            logger.error(
                "Invalid type for `manual_security`. Expected `bool`, got `%s`",
                type(manual_security),
            )
            return False

        if not isinstance(disable_security, bool):
            logger.error(
                "Invalid type for `disable_security`. Expected `bool`, got `%s`",
                type(disable_security),
            )
            return False

        if not isinstance(message, (Message, int)):
            logger.error(
                "Invalid type for `message`. Expected `Message` or `int`, got `%s`",
                type(message),
            )
            return False

        if not isinstance(reply_markup, (list, dict)):
            logger.error(
                "Invalid type for `reply_markup`. Expected `list` or `dict`, got `%s`",
                type(reply_markup),
            )
            return False

        if photo is not None:
            if not isinstance(photo, str):
                logger.error(
                    "Invalid type for `photo`. Expected `str` (URL or local path), got `%s`",
                    type(photo),
                )
                return False
            if not utils.check_url(photo) and not Path(photo).is_file():
                logger.error(
                    "Invalid `photo`: not a URL and not an existing file: %s",
                    photo,
                )
                return False

        try:
            path = urlparse(photo).path
            ext = os.path.splitext(path)[1]
        except Exception:
            ext = None

        if photo is not None and ext in {".gif", ".mp4"}:
            gif = copy.copy(photo)
            photo = None

        if gif and (not isinstance(gif, str) or not utils.check_url(gif)):
            logger.error(
                "Invalid type for `gif`. Expected `str` with URL, got `%s`",
                type(gif),
            )
            return False

        if file and (not isinstance(file, str) or not utils.check_url(file)):
            logger.error(
                "Invalid type for `file`. Expected `str` with URL, got `%s`",
                type(file),
            )
            return False

        if file and not mime_type:
            logger.error(
                "You must pass `mime_type` along with `file` field\n"
                "It may be either 'application/zip' or 'application/pdf'"
            )
            return False

        if video and (not isinstance(video, str) or not utils.check_url(video)):
            logger.error(
                "Invalid type for `video`. Expected `str` with URL, got `%s`",
                type(video),
            )
            return False

        if isinstance(audio, str):
            audio = {"url": audio}

        if audio and (
            not isinstance(audio, dict)
            or "url" not in audio
            or not utils.check_url(audio["url"])
        ):
            logger.error(
                "Invalid type for `audio`. Expected `dict` with `url` key, got `%s`",
                type(audio),
            )
            return False

        if location and (
            not isinstance(location, (list, tuple))
            or len(location) != 2
            or not all(isinstance(item, float) for item in location)
        ):
            logger.error(
                (
                    "Invalid type for `location`. Expected `list` or `tuple` with 2"
                    " `float` items, got `%s`"
                ),
                type(location),
            )
            return False

        if [
            photo is not None,
            gif is not None,
            file is not None,
            video is not None,
            audio is not None,
            location is not None,
        ].count(True) > 1:
            logger.error("You passed two or more exclusive parameters simultaneously")
            return False

        reply_markup = self._validate_markup(reply_markup) or []

        if not isinstance(force_me, bool):
            logger.error(
                "Invalid type for `force_me`. Expected `bool`, got `%s`",
                type(force_me),
            )
            return False

        if not isinstance(always_allow, list):
            logger.error(
                "Invalid type for `always_allow`. Expected `list`, got `%s`",
                type(always_allow),
            )
            return False

        if not isinstance(ttl, int) and ttl:
            logger.error("Invalid type for `ttl`. Expected `int`, got `%s`", type(ttl))
            return False

        if isinstance(message, Message) and not silent:
            try:
                status_message = await (
                    message.edit if message.out else message.respond
                )(
                    (
                        utils.get_platform_emoji()
                        if self._client.hikkari_me.premium
                        else "✨"
                    )
                    + self.translator.getkey("inline.opening_form"),
                    **({"reply_to": utils.get_topic(message)} if message.out else {}),
                )
            except Exception:
                status_message = None
        else:
            status_message = None

        unit_id = utils.rand(16)

        perms_map = None if manual_security else self._find_caller_sec_map()

        if not reply_markup and not ttl:
            logger.debug("Patching form reply markup with empty data")
            base_reply_markup = copy.deepcopy(reply_markup) or None
            reply_markup = self._validate_markup({"text": "­", "data": "­"})
        else:
            base_reply_markup = Placeholder()

        if (
            not any(
                any("callback" in button or "input" in button for button in row)
                for row in reply_markup
            )
            and not ttl
        ):
            logger.debug(
                "Patching form ttl to 10 minutes, because it doesn't contain any"
                " buttons"
            )
            ttl = 10 * 60

        self._units[unit_id] = {
            "type": "form",
            "text": text,
            "buttons": reply_markup,
            "premium_emoji_pre_edit": needs_premium_emoji_pre_edit,
            "caller": message,
            "chat": None,
            "message_id": None,
            "top_msg_id": utils.get_topic(message),
            "uid": unit_id,
            "on_unload": on_unload,
            "future": Event(),
            **({"photo": photo} if photo else {}),
            **({"video": video} if video else {}),
            **({"gif": gif} if gif else {}),
            **({"location": location} if location else {}),
            **({"audio": audio} if audio else {}),
            **({"location": location} if location else {}),
            **({"perms_map": perms_map} if perms_map else {}),
            **({"message": message} if isinstance(message, Message) else {}),
            **({"force_me": force_me} if force_me else {}),
            **({"disable_security": disable_security} if disable_security else {}),
            **({"ttl": round(time.time()) + ttl} if ttl else {}),
            **({"always_allow": always_allow} if always_allow else {}),
        }

        async def answer(msg: str):
            nonlocal message
            if isinstance(message, Message):
                await (message.edit if message.out else message.respond)(
                    msg,
                    **({} if message.out else {"reply_to": utils.get_topic(message)}),
                )
            else:
                await self._client.send_message(message, msg)

        try:
            m = await self._invoke_unit(unit_id, message)
        except ChatSendInlineForbiddenError:
            await answer(self.translator.getkey("inline.inline403"))
            with contextlib.suppress(Exception):
                del self._units[unit_id]
            return False
        except Exception as e:
            logger.exception("Can't send form")

            with contextlib.suppress(Exception):
                del self._units[unit_id]

            if "No query results" in str(e):
                await answer(
                    self.translator.getkey("inline.no_query_results").format(
                        prefix=getattr(self._client, "command_prefix", "."),
                    ),
                )

            else:
                await answer(
                    self.translator.getkey("inline.invoke_failed_logs").format(
                        utils.escape_html(
                            "\n".join(traceback.format_exc().splitlines()[1:])
                        )
                    )
                    if self._db.get(main.__name__, "inlinelogs", True)
                    else self.translator.getkey("inline.invoke_failed")
                )

            return False

        # Save chat/msg immediately from clicked result
        self._units[unit_id]["chat"] = utils.get_chat_id(m)
        self._units[unit_id]["message_id"] = m.id

        # Delete original command / status ASAP (do not wait for chosen feedback)
        if isinstance(message, Message) and message.out:
            with contextlib.suppress(Exception):
                await message.delete()
        if status_message is not None:
            with contextlib.suppress(Exception):
                await status_message.delete()
            # if status was an edit of inbound reply path, also try delete original
            if isinstance(message, Message) and not message.out:
                with contextlib.suppress(Exception):
                    await message.delete()

        # Wait for UpdateBotInlineSend to get inline_message_id (needed for edit)
        # Timeout: without BotFather /setinlinefeedback this never arrives
        try:
            await asyncio.wait_for(self._units[unit_id]["future"].wait(), timeout=2)
        except (asyncio.TimeoutError, KeyError):
            logger.warning(
                "Inline form %s: no chosen_inline feedback in 2s "
                "(enable /setinlinefeedback in @BotFather). Continuing without it.",
                unit_id,
            )
        with contextlib.suppress(Exception):
            if "future" in self._units.get(unit_id, {}):
                del self._units[unit_id]["future"]

        inline_message_id = self._units[unit_id].get("inline_message_id")

        msg = InlineMessage(
            inline_manager=self, unit_id=unit_id, inline_message_id=inline_message_id
        )

        # Optional post-edit (premium emoji / markup refresh).
        # Do NOT delete the form if edit fails — content already in the article.
        if inline_message_id and (
            needs_premium_emoji_pre_edit or not isinstance(base_reply_markup, Placeholder)
        ):
            with contextlib.suppress(Exception):
                if needs_premium_emoji_pre_edit:
                    await asyncio.sleep(0.2)
                await msg.edit(
                    text,
                    reply_markup=(
                        base_reply_markup
                        if not isinstance(base_reply_markup, Placeholder)
                        else reply_markup
                    ),
                )

        return msg


    async def rich(
        self: "InlineManager",
        message: typing.Union[Message, int],
        html: str,
        *,
        title: str = "Hikkari",
        description: str = "Rich message",
        silent: bool = False,
        reply_markup: typing.Optional[list] = None,
        thumbnail_url: typing.Optional[str] = None,
        pages: typing.Optional[list] = None,
        page: int = 0,
    ) -> typing.Union[Message, bool]:
        """
        Send a native Rich Message via inline (appears with via @bot),
        same invocation path as form/list.
        `html` — official Rich HTML (<table>, <h2>, <details>, ...).
        """
        if not isinstance(html, str) or not html.strip():
            logger.error("inline.rich: empty html")
            return False

        if not self.init_complete:
            await self.register_manager(ignore_token_checks=True)
        if not self.bot_username:
            logger.error("inline.rich: no bot username")
            return False

        unit_id = utils.rand(16)
        markup = self._validate_markup(reply_markup) if reply_markup else []
        # Official Rich buttons inside HTML (<tg-button-row>), not only reply_markup
        try:
            from ..utils.rich_api import markup_to_tg_rows, nav_button_row
            page_list = list(pages) if pages else None
            cur = int(page or 0)
            body = html
            if page_list:
                cur = max(0, min(cur, len(page_list) - 1))
                body = page_list[cur]
                nav = nav_button_row(unit_id, cur, len(page_list))
                if nav:
                    body = body + "\n" + nav
            btn_html = markup_to_tg_rows(markup, unit_id) if markup else ""
            if btn_html:
                body = body + "\n" + btn_html
            html = body
        except Exception:
            logger.debug("rich button embed failed", exc_info=True)
            page_list = list(pages) if pages else None
            cur = int(page or 0)
        self._units[unit_id] = {
            "type": "rich",
            "rich_html": html,
            "text": html,  # fallback if client ignores rich
            "title": title,
            "description": description,
            "buttons": markup or [],
            "pages": page_list,
            "page": cur if page_list else 0,
            "caller": message,
            "chat": None,
            "message_id": None,
            "top_msg_id": utils.get_topic(message) if isinstance(message, Message) else None,
            "uid": unit_id,
            "future": Event(),
            "force_me": True,
            "disable_security": True,
            **({"thumbnail_url": thumbnail_url} if thumbnail_url else {}),
            **({"message": message} if isinstance(message, Message) else {}),
        }

        status_message = None
        if isinstance(message, Message) and not silent:
            try:
                status_message = await (
                    message.edit if message.out else message.respond
                )(
                    (
                        utils.get_platform_emoji()
                        if getattr(self._client, "hikkari_me", None)
                        and self._client.hikkari_me.premium
                        else "✨"
                    )
                    + " <i>Opening rich…</i>",
                    **({"reply_to": utils.get_topic(message)} if message.out else {}),
                )
            except Exception:
                status_message = None

        try:
            m = await self._invoke_unit(unit_id, message)
        except Exception as e:
            logger.exception("Can't send rich inline")
            with contextlib.suppress(Exception):
                del self._units[unit_id]
            if status_message is not None:
                with contextlib.suppress(Exception):
                    await status_message.delete()
            return False

        self._units[unit_id]["chat"] = utils.get_chat_id(m) if m else None
        self._units[unit_id]["message_id"] = getattr(m, "id", None)

        if isinstance(message, Message) and message.out:
            with contextlib.suppress(Exception):
                await message.delete()
        if status_message is not None:
            with contextlib.suppress(Exception):
                await status_message.delete()

        return m


    async def _form_inline_handler(self: "InlineManager", inline_query):
        try:
            query = inline_query.query.split()[0]
        except IndexError:
            return

        for unit in self._units.copy().values():
            for button in utils.array_sum(unit.get("buttons", [])):
                if (
                    "_switch_query" in button
                    and "input" in button
                    and button["_switch_query"] == query
                    and inline_query.from_user.id
                    in [self._me]
                    + self._client.dispatcher.security._owner
                    + unit.get("always_allow", [])
                ):
                    if not getattr(self, "_pending_config_input", None):
                        self._pending_config_input = {}
                    if button.get("handler"):
                        self._pending_config_input[inline_query.from_user.id] = (
                            button["handler"],
                            unit.get("uid") if isinstance(unit, dict) else None,
                            list(button.get("args") or []),
                            dict(button.get("kwargs") or {}),
                        )
                    await inline_query.answer(
                        [
                            await inline_query.builder.article(
                                title=button["input"],
                                description=(
                                    self.translator.getkey("inline.keep_id").format(
                                        random.choice(VERIFICATION_EMOJIES)
                                    )
                                ),
                                text=(
                                    "🔄 <b>Transferring value to"
                                    " userbot...</b>\n<i>This message will be"
                                    " deleted automatically</i>"
                                    if inline_query.from_user.id == self._me
                                    else "🔄 <b>Transferring value to userbot...</b>"
                                ),
                                parse_mode="HTML",
                                link_preview=False,
                                id=utils.rand(20),
                            )
                        ],
                        cache_time=60,
                    )
                    return

        if (
            inline_query.query not in self._units
            or self._units[inline_query.query]["type"] not in ("form", "rich")
        ):
            return


        form = self._units[inline_query.query]
        # --- Native Rich Message via answerInlineQuery (via @bot) ---
        if form.get("type") == "rich":
            try:
                from ..utils.rich_api import answer_inline_rich, _find_bot_token
                token = _find_bot_token(self._client) or getattr(self, "_token", None)
                qid = (
                    getattr(inline_query, "query_id", None)
                    or getattr(inline_query, "id", None)
                    or getattr(getattr(inline_query, "query", None), "query_id", None)
                )
                if not token or qid is None:
                    logger.warning("rich inline: missing token or query_id token=%s qid=%s", bool(token), qid)
                    return
                html = form.get("rich_html") or form.get("text") or ""
                # Bot API inline keyboard for article (optional)
                rm = None
                buttons = form.get("buttons") or []
                if buttons:
                    try:
                        rm = {"inline_keyboard": []}
                        for row in buttons:
                            r = []
                            for btn in row:
                                if not isinstance(btn, dict):
                                    continue
                                if btn.get("url"):
                                    r.append({"text": btn.get("text", "•"), "url": btn["url"]})
                                elif btn.get("data") or btn.get("callback"):
                                    r.append({
                                        "text": btn.get("text", "•"),
                                        "callback_data": str(btn.get("data") or "noop")[:64],
                                    })
                            if r:
                                rm["inline_keyboard"].append(r)
                        if not rm["inline_keyboard"]:
                            rm = None
                    except Exception:
                        rm = None
                ok = await answer_inline_rich(
                    str(token),
                    qid,
                    html,
                    title=form.get("title") or "Hikkari",
                    description=form.get("description") or "Rich",
                    result_id=form.get("uid") or utils.rand(16),
                    reply_markup=rm,
                    thumbnail_url=form.get("thumbnail_url"),
                )
                if not ok and form.get("uid") in self._error_events:
                    self._error_events[form["uid"]].set()
                    self._error_events[form["uid"]] = Exception("answerInlineQuery rich failed")
                return
            except Exception as e:
                logger.exception("rich inline handler error")
                if form.get("uid") in self._error_events:
                    self._error_events[form["uid"]].set()
                    self._error_events[form["uid"]] = e
                return

        form_text = form.get("text") or "✨"

        try:
            match True:
                case _ if "photo" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.photo(
                                form["photo"],
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "gif" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["gif"],
                                title="Hikkari",
                                type="gif",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "video" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["video"],
                                title="Hikkari",
                                description="Hikkari",
                                type="video",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                mime_type="video/mp4",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "file" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["file"],
                                title="Hikkari",
                                description="Hikkari",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                mime_type=form["mime_type"],
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "location" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.article(
                                title="Hikkari",
                                geo=InputGeoPoint(
                                    lat=form["location"][0],
                                    long=form["location"][1],
                                ),
                                period=60,
                                id=utils.rand(20),
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _ if "audio" in form:
                    await inline_query.answer(
                        [
                            await inline_query.builder.document(
                                form["audio"]["url"],
                                title=form["audio"].get("title", "Hikkari"),
                                type="audio",
                                id=utils.rand(20),
                                text=form_text,
                                parse_mode="HTML",
                                buttons=self.generate_markup(
                                    form["uid"],
                                ),
                            )
                        ],
                        cache_time=0,
                    )
                case _:
                    await inline_query.answer(
                        [
                            await inline_query.builder.article(
                                title="Hikkari",
                                text=form_text,
                                parse_mode="HTML",
                                link_preview=False,
                                buttons=self.generate_markup(inline_query.query),
                                id=utils.rand(20),
                            )
                        ],
                        cache_time=0,
                    )
        except Exception as e:
            if form["uid"] in self._error_events:
                self._error_events[form["uid"]].set()
                self._error_events[form["uid"]] = e
