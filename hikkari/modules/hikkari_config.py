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

import ast
import re
import io
import contextlib
import difflib
import functools
import logging
logger = logging.getLogger(__name__)
import typing
from pathlib import Path
from math import ceil

from hikkaritl.tl.types import Message
from hikkaritl.extensions import html

from .. import loader, translations, utils
from ..inline.types import InlineCall
from ..types import HikkariReplyMarkup

# Everywhere in this module, we use the following naming convention:
# `obj_type` of non-core module = False
# `obj_type` of core module = True
# `obj_type` of library = "library"


ROW_SIZE = 3
NUM_ROWS = 12


class _InlineFormDraft:
    inline_message_id = None

    def __init__(self):
        self.text: str | None = None
        self.reply_markup: HikkariReplyMarkup | None = None
        self.kwargs: dict[str, typing.Any] = {}

    async def edit(
        self,
        text: str | None = None,
        reply_markup: HikkariReplyMarkup | None = None,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        if text is None:
            text = kwargs.pop("text", None)

        if reply_markup is None and args:
            reply_markup = args[0]

        self.text = text
        self.reply_markup = reply_markup
        self.kwargs = kwargs


@loader.tds
class HikkariConfigMod(loader.Module):
    """Interactive configurator for Hikkari Userbot"""

    strings = {"name": "HikkariConfig"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "cfg_emoji",
                "<emoji document_id=5283176512747507510>✨</emoji>",
                "Change emoji when opening config",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "banner_url",
                "",
                lambda: "Banner for config UI (http URL or empty for built-in)",
                validator=loader.validators.String(),
            ),
        )


    def _cfg_rich_html(self, body: str, *, title: str = "Hikkari Config") -> str:
        """Wrap config body as Rich HTML (Heroku 2.2 style) + banner figure."""
        import html as html_mod
        from .._internal import normalize_rich_html

        def _resolve_banner(url: str) -> str | None:
            url = (url or "").strip()
            if not url:
                return None
            if url.startswith("local:"):
                name = url[6:].lstrip("/")
                return f"https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/{name}"
            if url.startswith(("http://", "https://")):
                if url.lower().endswith((".mp4", ".webm", ".mov", ".gif")):
                    return None  # video/gif not as <img> in rich
                return url
            # bare filename
            if "/" not in url and "." in url:
                return f"https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/{url}"
            return None

        banner = ""
        try:
            raw = self.config.get("banner_url")
            if isinstance(raw, list) and raw:
                import random as _r
                raw = _r.choice(raw)
            url = _resolve_banner(str(raw or ""))
            if not url:
                url = "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-config.jpg"
            banner = f'<figure><img src="{html_mod.escape(url)}"/></figure>'
        except Exception:
            pass

        body = body or ""
        if "<details" in body or "<h2" in body or "<p>" in body:
            html = banner + body
        else:
            lines = [
                ln.strip()
                for ln in body.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n").split("\n")
                if ln.strip()
            ]
            paras = "".join(f"<p>{ln}</p>" for ln in lines) or f"<p>{body}</p>"
            html = f"{banner}<h2>{html_mod.escape(title)}</h2>{paras}"
        return normalize_rich_html(html)


    def _cfg_use_rich(self) -> bool:
        # Always try Rich path (Heroku 2.2). Non-premium falls back via form/answer.
        return True

    async def _cfg_form(self, text, message, reply_markup=None, **kwargs):
        """Config UI only via inline form in the SAME chat (no bot-PM / rich divert)."""
        import logging
        import contextlib
        _log = logging.getLogger(__name__)

        for k in ("photo", "video", "gif", "file", "audio"):
            kwargs.pop(k, None)

        markup = reply_markup if reply_markup is not None else []
        banner = self._cfg_banner_kwargs()
        # Remote video URLs often fail TG WebpageCurl / InputDocument cast on
        # inline results. Prefer photo banners as media; for video use rich form
        # and keep the URL only as a text link so config still opens.
        media = {}
        if banner.get("photo"):
            media["photo"] = banner["photo"]
        elif banner.get("gif"):
            media["gif"] = banner["gif"]
        elif banner.get("video"):
            # do not attach video URL as document — breaks form; show link in text
            vurl = banner["video"]
            if vurl and vurl not in (text or ""):
                text = f'🎬 <a href="{vurl}">banner</a>
{text or "⚙️"}'

        rich = kwargs.pop("rich_message", None)
        if not media:
            rich = rich or self._cfg_rich_html(text, title="⚙️ Hikkari Config")
        else:
            rich = None

        form_kwargs = dict(
            text=text or "⚙️",
            message=message,
            reply_markup=markup,
            silent=True,
            force_me=True,
            **media,
        )
        if rich is not None:
            form_kwargs["rich_message"] = rich

        try:
            form_msg = await self.inline.form(**form_kwargs)
            if form_msg:
                return form_msg
        except Exception:
            _log.exception("cfg form failed")

        # last resort: plain article form
        form_kwargs.pop("rich_message", None)
        for k in ("photo", "video", "gif", "file", "audio"):
            form_kwargs.pop(k, None)
        with contextlib.suppress(Exception):
            return await self.inline.form(**form_kwargs)
        return None


    def _cfg_banner_kwargs(self) -> dict:
        """Banner from URL only — no download, no RAM. TG fetches by link."""
        from urllib.parse import urlparse

        raw = None
        with contextlib.suppress(Exception):
            raw = (self.config.get("banner_url") or self.config.get("banner") or "").strip()
        if not raw:
            with contextlib.suppress(Exception):
                raw = (self.db.get("HikkariConfig", "banner_url", None) or "").strip()
        if not raw or not str(raw).startswith("http"):
            return {}

        url = str(raw).strip()
        low = url.lower()
        path = (urlparse(url).path or "").lower()

        # Prefer explicit media keys so form/inline uses remote URL (no local file)
        if any(x in low or path.endswith(x) for x in (".mp4", ".mov", ".webm", "mime=video")):
            return {"video": url}
        if any(x in low or path.endswith(x) for x in (".gif", ".mp4.gif", "format=gif")):
            return {"gif": url}
        if any(x in low or path.endswith(x) for x in (".png", ".jpg", ".jpeg", ".webp", ".bmp")):
            return {"photo": url}
        # Unknown — try photo URL (preview); if TG rejects, form still shows text
        return {"photo": url}


    @staticmethod
    def prep_value(value: typing.Any) -> typing.Any:
        if isinstance(value, str):
            return f"<b><code>{utils.escape_html(value.strip())}</code></b>"

        if isinstance(value, list) and value:
            return (
                "<b><code>[</code></b>\n    "
                + "\n    ".join(
                    [
                        f"<b><code>{utils.escape_html(str(item))}</code></b>"
                        for item in value
                    ]
                )
                + "\n<b><code>]</code></b>"
            )

        return f"<b><code>{utils.escape_html(value)}</code></b>"

    def hide_value(self, value: typing.Any) -> str:
        if isinstance(value, list) and value:
            return self.prep_value(["*" * len(str(i)) for i in value])

        return self.prep_value("*" * len(str(value)))

    def _get_value(self, mod: str, option: str) -> str:
        return (
            self.prep_value(self.lookup(mod).config[option])
            if (
                not self.lookup(mod).config._config[option].validator
                or self.lookup(mod).config._config[option].validator.internal_id
                != "Hidden"
            )
            else self.hide_value(self.lookup(mod).config[option])
        )

    def _get_inline_value(self, mod: str, option: str, limit: int = 2500) -> str:
        value = self._get_value(mod, option)
        if len(value) <= limit:
            return value

        plain = utils.remove_html(value)
        suffix = "\n... <i>значение обрезано для inline-сообщения</i>"
        plain_limit = max(0, limit - len(suffix) - len("<b><code></code></b>"))
        return f"<b><code>{utils.escape_html(plain[:plain_limit])}</code></b>{suffix}"

    def _paginate_text_markup(
        self,
        text: str,
        page: int,
        callback: typing.Any,
        length: int | None = None,
        with_media: bool = False,
    ) -> tuple[str, list[list[dict[str, typing.Any]]]]:
        """
        Paginate ONLY when text exceeds Telegram limits.
        - with media/caption: 1024
        - plain message: 4096
        No nav buttons if content fits on one page.
        """
        if length is None:
            length = 1024 if with_media else 4096

        # Fast path: under limit → no pagination
        if len(text or "") <= length:
            return text, []

        parsed_text, parsed_entities = html.parse(text)
        if len(parsed_text or "") <= length:
            return text, []

        pages = list(
            utils.smart_split(
                parsed_text,
                typing.cast(typing.Any, parsed_entities),
                length,
            )
        )

        if len(pages) <= 1:
            return text, []

        page = min(max(page, 0), len(pages) - 1)

        row = []
        if page > 0:
            row.append({"text": "◀️", "callback": callback, "args": (page - 1,)})

        row.append(
            {"text": f"{page + 1}/{len(pages)}", "callback": callback, "args": (page,)}
        )

        if page < len(pages) - 1:
            row.append({"text": "▶️", "callback": callback, "args": (page + 1,)})

        return pages[page], [row]

    @staticmethod
    def _put_pagination_before_nav(
        reply_markup: list[list[dict[str, typing.Any]]],
        pagination: list[list[dict[str, typing.Any]]],
    ) -> list[list[dict[str, typing.Any]]]:
        if not pagination:
            return reply_markup

        return reply_markup[:-1] + pagination + reply_markup[-1:]

    def _guess_back_to_page(
        self,
        mod: str,
        option: str,
        obj_type: bool | str = False,
    ) -> dict:
        kwargs = {"obj_type": obj_type}
        cat = self.lookup(mod).config.get_category(option)
        if cat is not None:
            kwargs["category"] = cat.name
        return kwargs

    @staticmethod
    def _config_categories(instance: typing.Any) -> dict[str, list[str]]:
        return {
            category: options
            for category, options in instance.config.grouped_options().items()
            if category is not None
        }

    @staticmethod
    def _get_category_doc(instance: typing.Any, category: str) -> str:
        cat_obj = getattr(instance.config, "_categories", {}).get(category)
        return cat_obj.getdoc() if cat_obj else ""

    async def inline__set_config(
        self,
        call: InlineCall,
        query: str,
        mod: str,
        option: str,
        inline_message_id: str | None = None,
        obj_type: bool | str = False,
    ):
        # Heroku-compatible: assign first, then edit form
        try:
            if isinstance(query, str):
                query = query.strip()
            # Reject placeholder / transfer garbage from broken inline input
            if isinstance(query, str) and (
                "Transferring value" in query
                or "will be deleted automatically" in query
                or query in {"🔄", "✨"}
            ):
                await call.edit(
                    self.strings.get(
                        "validation_error",
                        "🚫 <b>Invalid value</b>",
                    ).format("empty or transfer placeholder — type the value in the inline field and send it"),
                    reply_markup={
                        "text": self.strings.get("try_again", "Try again"),
                        "callback": self.inline__configure_option,
                        "kwargs": {
                            "obj_type": obj_type,
                            "mod": mod,
                            "config_opt": option,
                        },
                    },
                )
                return
            if query == "" and option not in {"banner_url", "custom_message"}:
                # empty might be intentional for some options; still allow for string
                pass
            prev_q = None
            with contextlib.suppress(Exception):
                prev_q = self.lookup(mod).config[option]
            self.lookup(mod).config[option] = query
            if self._is_banner_option(str(option)):
                qs = str(query or "")
                if not qs.startswith(("audio:", "audio_ref:")):
                    self._cleanup_audio_banner_files(mod, str(option), prev_q)
        except loader.validators.ValidationError as e:
            await call.edit(
                self.strings["validation_error"].format(e.args[0]),
                reply_markup={
                    "text": self.strings["try_again"],
                    "callback": self.inline__configure_option,
                    "kwargs": {"obj_type": obj_type, "mod": mod, "config_opt": option},
                },
            )
            return

        # Flush DB so value is not lost on restart
        with contextlib.suppress(Exception):
            self._db.save()

        imid = (
            inline_message_id
            or getattr(call, "inline_message_id", None)
            or (
                (call._units.get(call.unit_id) or {}).get("inline_message_id")
                if getattr(call, "unit_id", None) and getattr(call, "_units", None)
                else None
            )
        )

        text = self.strings[
            "option_saved" if isinstance(obj_type, bool) else "option_saved_lib"
        ].format(
            utils.escape_html(option),
            utils.escape_html(mod),
            self._get_inline_value(mod, option),
        )
        markup = [
            [
                {
                    "text": self.strings["back_btn"],
                    "callback": self.inline__configure,
                    "args": (mod,),
                    "style": "primary",
                    "kwargs": self._guess_back_to_page(mod, option, obj_type),
                },
                {
                    "text": self.strings["close_btn"],
                    "action": "close",
                    "style": "danger", "emoji_id": 5283176512747507510},
            ]
        ]
        try:
            if imid is not None:
                await call.edit(text, reply_markup=markup, inline_message_id=imid)
            else:
                await call.edit(text, reply_markup=markup)
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("inline__set_config edit failed (value already saved)")

    async def inline__reset_default(
        self,
        call: InlineCall,
        mod: str,
        option: str,
        obj_type: bool | str = False,
    ):
        mod_instance = self.lookup(mod)
        mod_instance.config[option] = mod_instance.config.getdef(option)

        await call.edit(
            self.strings[
                "option_reset" if isinstance(obj_type, bool) else "option_reset_lib"
            ].format(
                utils.escape_html(option),
                utils.escape_html(mod),
                self._get_inline_value(mod, option),
            ),
            reply_markup=[
                [
                    {
                        "text": self.strings["back_btn"],
                        "callback": self.inline__configure,
                        "args": (mod,),
                        "style": "primary",
                        "kwargs": self._guess_back_to_page(mod, option, obj_type),
                    },
                    {
                        "text": self.strings["close_btn"],
                        "action": "close",
                        "style": "danger", "emoji_id": 5283176512747507510},
                ]
            ],
        )

    async def inline__set_bool(
        self,
        call: InlineCall,
        mod: str,
        option: str,
        value: bool,
        obj_type: bool | str = False,
    ):
        try:
            self.lookup(mod).config[option] = value
        except loader.validators.ValidationError as e:
            await call.edit(
                self.strings["validation_error"].format(e.args[0]),
                reply_markup={
                    "text": self.strings["try_again"],
                    "callback": self.inline__configure_option,
                    "kwargs": {"obj_type": obj_type, "mod": mod, "config_opt": option},
                },
            )
            return

        validator = self.lookup(mod).config._config[option].validator
        doc = utils.escape_html(
            next(
                (
                    validator.doc[lang]
                    for original_lang in self._db.get(
                        translations.__name__, "lang", "en"
                    ).split(" ")
                    for lang in translations.iter_language_codes(original_lang)
                    if lang in validator.doc
                ),
                validator.doc["en"],
            )
        )

        await call.edit(
            self.strings[
                (
                    "configuring_option"
                    if isinstance(obj_type, bool)
                    else "configuring_option_lib"
                )
            ].format(
                utils.escape_html(option),
                utils.escape_html(mod),
                utils.escape_html(self.lookup(mod).config.getdoc(option)),
                self.prep_value(self.lookup(mod).config.getdef(option)),
                (
                    self.prep_value(self.lookup(mod).config[option])
                    if not validator or validator.internal_id != "Hidden"
                    else self.hide_value(self.lookup(mod).config[option])
                ),
                (
                    self.strings["typehint"].format(
                        doc,
                        eng_art="n" if doc.lower().startswith(tuple("euioay")) else "",
                    )
                    if doc
                    else ""
                ),
            ),
            reply_markup=self._generate_bool_markup(mod, option, obj_type),
        )

        await call.answer("✅")

    def _generate_bool_markup(
        self,
        mod: str,
        option: str,
        obj_type: bool | str = False,
    ) -> list:
        return [
            [
                *(
                    [
                        {
                            "text": f"❌ {self.strings['set']} `False`",
                            "callback": self.inline__set_bool,
                            "args": (mod, option, False),
                            "kwargs": {"obj_type": obj_type},
                        }
                    ]
                    if self.lookup(mod).config[option]
                    else [
                        {
                            "text": f"✅ {self.strings['set']} `True`",
                            "callback": self.inline__set_bool,
                            "args": (mod, option, True),
                            "kwargs": {"obj_type": obj_type},
                        }
                    ]
                )
            ],
            [
                *(
                    [
                        {
                            "text": self.strings["set_default_btn"],
                            "callback": self.inline__reset_default,
                            "args": (mod, option),
                            "kwargs": {"obj_type": obj_type},
                        }
                    ]
                    if self.lookup(mod).config[option]
                    != self.lookup(mod).config.getdef(option)
                    else []
                )
            ],
            [
                {
                    "text": self.strings["back_btn"],
                    "callback": self.inline__configure,
                    "args": (mod,),
                    "style": "primary",
                    "kwargs": self._guess_back_to_page(mod, option, obj_type),
                },
                {
                    "text": self.strings["close_btn"],
                    "action": "close",
                    "style": "danger", "emoji_id": 5283176512747507510},
            ],
        ]

    async def inline__add_item(
        self,
        call: InlineCall,
        query: str,
        mod: str,
        option: str,
        inline_message_id: str | None = None,
        obj_type: bool | str = False,
    ):
        try:
            with contextlib.suppress(Exception):
                query = ast.literal_eval(query)

            if isinstance(query, (set, tuple)):
                query = list(query)

            if not isinstance(query, list):
                query = [query]

            self.lookup(mod).config[option] = self.lookup(mod).config[option] + query
        except loader.validators.ValidationError as e:
            await call.edit(
                self.strings["validation_error"].format(e.args[0]),
                reply_markup={
                    "text": self.strings["try_again"],
                    "callback": self.inline__configure_option,
                    "kwargs": {"obj_type": obj_type, "mod": mod, "config_opt": option},
                },
            )
            return

        await call.edit(
            self.strings[
                "option_saved" if isinstance(obj_type, bool) else "option_saved_lib"
            ].format(
                utils.escape_html(option),
                utils.escape_html(mod),
                self._get_inline_value(mod, option),
            ),
            reply_markup=[
                [
                    {
                        "text": self.strings["back_btn"],
                        "callback": self.inline__configure,
                        "args": (mod,),
                        "style": "primary",
                        "kwargs": self._guess_back_to_page(mod, option, obj_type),
                    },
                    {
                        "text": self.strings["close_btn"],
                        "action": "close",
                        "style": "danger", "emoji_id": 5283176512747507510},
                ]
            ],
            inline_message_id=inline_message_id or call.inline_message_id,
        )

    async def inline__remove_item(
        self,
        call: InlineCall,
        query: str,
        mod: str,
        option: str,
        inline_message_id: str | None = None,
        obj_type: bool | str = False,
    ):
        try:
            with contextlib.suppress(Exception):
                query = ast.literal_eval(query)

            if isinstance(query, (set, tuple)):
                query = list(query)

            if not isinstance(query, list):
                query = [query]

            query = list(map(str, query))

            old_config = list(self.lookup(mod).config[option])
            old_config_len = len(old_config)

            # Long audio_ref values often get truncated in UI — remove by prefix
            drop_audio = any(
                q.startswith("audio_ref:") or q.startswith("audio:") for q in query
            )

            def _keep(item) -> bool:
                s = str(item)
                if s in query:
                    return False
                if drop_audio and (
                    s.startswith("audio_ref:") or s.startswith("audio:")
                ):
                    return False
                # partial match for truncated audio_ref in user input
                for q in query:
                    if len(q) >= 24 and (s.startswith(q) or q.startswith(s[:40])):
                        return False
                return True

            new_list = [i for i in old_config if _keep(i)]
            self.lookup(mod).config[option] = new_list

            if drop_audio:
                self._cleanup_audio_banner_files(mod, str(option), old_config)

            if old_config_len == len(self.lookup(mod).config[option]) and not drop_audio:
                raise loader.validators.ValidationError(
                    f"Nothing from passed value ({self.prep_value(query)}) is not in"
                    " target list"
                )
        except loader.validators.ValidationError as e:
            await call.edit(
                self.strings["validation_error"].format(e.args[0]),
                reply_markup={
                    "text": self.strings["try_again"],
                    "callback": self.inline__configure_option,
                    "kwargs": {"obj_type": obj_type, "mod": mod, "config_opt": option},
                },
            )
            return

        await call.edit(
            self.strings[
                "option_saved" if isinstance(obj_type, bool) else "option_saved_lib"
            ].format(
                utils.escape_html(option),
                utils.escape_html(mod),
                self._get_inline_value(mod, option),
            ),
            reply_markup=[
                [
                    {
                        "text": self.strings["back_btn"],
                        "callback": self.inline__configure,
                        "args": (mod,),
                        "style": "primary",
                        "kwargs": self._guess_back_to_page(mod, option, obj_type),
                    },
                    {
                        "text": self.strings["close_btn"],
                        "action": "close",
                        "style": "danger", "emoji_id": 5283176512747507510},
                ]
            ],
            inline_message_id=inline_message_id or call.inline_message_id,
        )

    def _generate_series_markup(
        self,
        call: InlineCall,
        mod: str,
        option: str,
        obj_type: bool | str = False,
    ) -> list:
        return [
            [
                {
                    "text": self.strings["enter_value_btn"],
                    "input": self.strings["enter_value_desc"],
                    "handler": self.inline__set_config,
                    "args": (mod, option, call.inline_message_id),
                    "kwargs": {"obj_type": obj_type},
                }
            ],
            [
                *(
                    [
                        {
                            "text": self.strings["remove_item_btn"],
                            "input": self.strings["remove_item_desc"],
                            "handler": self.inline__remove_item,
                            "args": (mod, option, call.inline_message_id),
                            "kwargs": {"obj_type": obj_type},
                        },
                        {
                            "text": self.strings["add_item_btn"],
                            "input": self.strings["add_item_desc"],
                            "handler": self.inline__add_item,
                            "args": (mod, option, call.inline_message_id),
                            "kwargs": {"obj_type": obj_type},
                        },
                    ]
                    if self.lookup(mod).config[option]
                    else []
                ),
            ],
            [
                *(
                    [
                        {
                            "text": self.strings["set_default_btn"],
                            "callback": self.inline__reset_default,
                            "args": (mod, option),
                            "kwargs": {"obj_type": obj_type},
                        }
                    ]
                    if self.lookup(mod).config[option]
                    != self.lookup(mod).config.getdef(option)
                    else []
                )
            ],
            [
                {
                    "text": self.strings["back_btn"],
                    "callback": self.inline__configure,
                    "args": (mod,),
                    "style": "primary",
                    "kwargs": self._guess_back_to_page(mod, option, obj_type),
                },
                {
                    "text": self.strings["close_btn"],
                    "action": "close",
                    "style": "danger", "emoji_id": 5283176512747507510},
            ],
        ]

    async def _choice_set_value(
        self,
        call: InlineCall,
        mod: str,
        option: str,
        value: bool,
        obj_type: bool | str = False,
    ):
        try:
            self.lookup(mod).config[option] = value
        except loader.validators.ValidationError as e:
            await call.edit(
                self.strings["validation_error"].format(e.args[0]),
                reply_markup={
                    "text": self.strings["try_again"],
                    "callback": self.inline__configure_option,
                    "kwargs": {"obj_type": obj_type, "mod": mod, "config_opt": option},
                },
            )
            return

        await call.edit(
            self.strings[
                "option_saved" if isinstance(obj_type, bool) else "option_saved_lib"
            ].format(
                utils.escape_html(option),
                utils.escape_html(mod),
                self._get_inline_value(mod, option),
            ),
            reply_markup=[
                [
                    {
                        "text": self.strings["back_btn"],
                        "callback": self.inline__configure,
                        "args": (mod,),
                        "style": "primary",
                        "kwargs": self._guess_back_to_page(mod, option, obj_type),
                    },
                    {
                        "text": self.strings["close_btn"],
                        "action": "close",
                        "style": "danger", "emoji_id": 5283176512747507510},
                ]
            ],
        )

        await call.answer("✅")

    async def _multi_choice_set_value(
        self,
        call: InlineCall,
        mod: str,
        option: str,
        value: bool,
        obj_type: bool | str = False,
    ):
        try:
            if value in self.lookup(mod).config._config[option].value:
                self.lookup(mod).config._config[option].value.remove(value)
            else:
                self.lookup(mod).config._config[option].value += [value]

            self.lookup(mod).config.reload()
        except loader.validators.ValidationError as e:
            await call.edit(
                self.strings["validation_error"].format(e.args[0]),
                reply_markup={
                    "text": self.strings["try_again"],
                    "callback": self.inline__configure_option,
                    "kwargs": {"obj_type": obj_type, "mod": mod, "config_opt": option},
                },
            )
            return

        await self.inline__configure_option(
            call, mod=mod, config_opt=option, force_hidden=False, obj_type=obj_type
        )
        await call.answer("✅")

    def _generate_choice_markup(
        self,
        call: InlineCall,
        mod: str,
        option: str,
        obj_type: bool | str = False,
    ) -> list:
        possible_values = list(
            self.lookup(mod)
            .config._config[option]
            .validator.validate.keywords["possible_values"]
        )
        return [
            [
                {
                    "text": self.strings["enter_value_btn"],
                    "input": self.strings["enter_value_desc"],
                    "handler": self.inline__set_config,
                    "args": (mod, option, call.inline_message_id),
                    "kwargs": {"obj_type": obj_type},
                }
            ],
            *utils.chunks(
                [
                    {
                        "text": (
                            f"{'☑️' if self.lookup(mod).config[option] == value else '🔘'} "
                            f"{value if len(str(value)) < 20 else str(value)[:20]}"
                        ),
                        "callback": self._choice_set_value,
                        "args": (mod, option, value, obj_type),
                    }
                    for value in possible_values
                ],
                2,
            )[
                : (
                    6
                    if self.lookup(mod).config[option]
                    != self.lookup(mod).config.getdef(option)
                    else 7
                )
            ],
            [
                *(
                    [
                        {
                            "text": self.strings["set_default_btn"],
                            "callback": self.inline__reset_default,
                            "args": (mod, option),
                            "kwargs": {"obj_type": obj_type},
                        }
                    ]
                    if self.lookup(mod).config[option]
                    != self.lookup(mod).config.getdef(option)
                    else []
                )
            ],
            [
                {
                    "text": self.strings["back_btn"],
                    "callback": self.inline__configure,
                    "args": (mod,),
                    "style": "primary",
                    "kwargs": self._guess_back_to_page(mod, option, obj_type),
                },
                {
                    "text": self.strings["close_btn"],
                    "action": "close",
                    "style": "danger", "emoji_id": 5283176512747507510},
            ],
        ]

    def _generate_multi_choice_markup(
        self,
        call: InlineCall,
        mod: str,
        option: str,
        obj_type: bool | str = False,
    ) -> list:
        possible_values = list(
            self.lookup(mod)
            .config._config[option]
            .validator.validate.keywords["possible_values"]
        )
        return [
            [
                {
                    "text": self.strings["enter_value_btn"],
                    "input": self.strings["enter_value_desc"],
                    "handler": self.inline__set_config,
                    "args": (mod, option, call.inline_message_id),
                    "kwargs": {"obj_type": obj_type},
                }
            ],
            *utils.chunks(
                [
                    {
                        "text": (
                            f"{'☑️' if value in self.lookup(mod).config[option] else '◻️'} "
                            f"{value if len(str(value)) < 20 else str(value)[:20]}"
                        ),
                        "callback": self._multi_choice_set_value,
                        "args": (mod, option, value, obj_type),
                    }
                    for value in possible_values
                ],
                2,
            )[
                : (
                    6
                    if self.lookup(mod).config[option]
                    != self.lookup(mod).config.getdef(option)
                    else 7
                )
            ],
            [
                *(
                    [
                        {
                            "text": self.strings["set_default_btn"],
                            "callback": self.inline__reset_default,
                            "args": (mod, option),
                            "kwargs": {"obj_type": obj_type},
                        }
                    ]
                    if self.lookup(mod).config[option]
                    != self.lookup(mod).config.getdef(option)
                    else []
                )
            ],
            [
                {
                    "text": self.strings["back_btn"],
                    "callback": self.inline__configure,
                    "args": (mod,),
                    "style": "primary",
                    "kwargs": self._guess_back_to_page(mod, option, obj_type),
                },
                {
                    "text": self.strings["close_btn"],
                    "action": "close",
                    "style": "danger", "emoji_id": 5283176512747507510},
            ],
        ]

    def _clip_cfg_text(self, text: str, limit: int = 950) -> str:
        if not text or len(text) <= limit:
            return text
        cut = text[: max(0, limit - 1)]
        if "<" in cut and cut.rfind("<") > cut.rfind(">"):
            cut = cut[: cut.rfind("<")]
        return cut + "…"


    async def _safe_cfg_edit(self, call, text, reply_markup=None, **kwargs):
        """Edit config form; Rich when possible so buttons keep working."""
        try:
            with contextlib.suppress(Exception):
                await call.answer()
        except Exception:
            pass
        if self._cfg_use_rich() and "rich_message" not in kwargs:
            try:
                kwargs["rich_message"] = self._cfg_rich_html(
                    text, title="⚙️ Hikkari Config"
                )
            except Exception:
                pass

        text_clip = self._clip_cfg_text(text, 950)
        try:
            return await call.edit(
                text_clip, reply_markup=reply_markup, **kwargs
            )
        except Exception:
            logger.debug("cfg edit failed, hard clip", exc_info=True)
            with contextlib.suppress(Exception):
                return await call.edit(
                    self._clip_cfg_text(text, 500),
                    reply_markup=reply_markup,
                )
            return False


    async def inline__configure_option(
        self,
        call: InlineCall,
        page: int = 0,
        mod: str = "",
        config_opt: str = "",
        force_hidden: bool = False,
        obj_type: bool | str = False,
    ):
        module = self.lookup(mod)
        # Like Heroku: full value in form, split via smart_split (caption-safe page size)
        args = [
            utils.escape_html(config_opt),
            utils.escape_html(mod),
            utils.escape_non_html(str(module.config.getdoc(config_opt) or "")),
            self.prep_value(module.config.getdef(config_opt)),
            (
                self.prep_value(module.config[config_opt])
                if not module.config._config[config_opt].validator
                or module.config._config[config_opt].validator.internal_id != "Hidden"
                or force_hidden
                else self.hide_value(module.config[config_opt])
            ),
        ]

        if (
            module.config._config[config_opt].validator
            and module.config._config[config_opt].validator.internal_id == "Hidden"
        ):
            additonal_button_row = (
                [
                    [
                        {
                            "text": self.strings["hide_value"],
                            "callback": self.inline__configure_option,
                            "kwargs": {
                                "obj_type": obj_type,
                                "mod": mod,
                                "config_opt": config_opt,
                                "force_hidden": False,
                            },
                        }
                    ]
                ]
                if force_hidden
                else [
                    [
                        {
                            "text": self.strings["show_hidden"],
                            "callback": self.inline__configure_option,
                            "kwargs": {
                                "obj_type": obj_type,
                                "mod": mod,
                                "config_opt": config_opt,
                                "force_hidden": True,
                            },
                        }
                    ]
                ]
            )
        else:
            additonal_button_row = []

        try:
            validator = module.config._config[config_opt].validator
            doc = utils.escape_html(
                next(
                    (
                        validator.doc[lang]
                        for original_lang in self._db.get(
                            translations.__name__, "lang", "en"
                        ).split(" ")
                        for lang in translations.iter_language_codes(original_lang)
                        if lang in validator.doc
                    ),
                    validator.doc["en"],
                )
            )
        except Exception:
            doc = None
            validator = None
            args += [""]
        else:
            args += [
                self.strings["typehint"].format(
                    doc,
                    eng_art="n" if doc.lower().startswith(tuple("euioay")) else "",
                )
            ]
            text = self.strings[
                (
                    "configuring_option"
                    if isinstance(obj_type, bool)
                    else "configuring_option_lib"
                )
            ].format(*args)
            text, pagination = self._paginate_text_markup(
                text,
                page,
                functools.partial(
                    self.inline__configure_option,
                    mod=mod,
                    config_opt=config_opt,
                    force_hidden=force_hidden,
                    obj_type=obj_type,
                ),
                with_media=True,
            )
            match validator.internal_id:
                case "Boolean":
                    await call.edit(
                        text,
                        reply_markup=additonal_button_row
                        + self._put_pagination_before_nav(
                            self._generate_bool_markup(mod, config_opt, obj_type),
                            pagination,
                        ),
                    )
                    return
                case "Series":
                    await call.edit(
                        text,
                        reply_markup=additonal_button_row
                        + self._put_pagination_before_nav(
                            self._generate_series_markup(
                                call, mod, config_opt, obj_type
                            ),
                            pagination,
                        ),
                    )
                    return
                case "Choice":
                    await call.edit(
                        text,
                        reply_markup=additonal_button_row
                        + self._put_pagination_before_nav(
                            self._generate_choice_markup(
                                call, mod, config_opt, obj_type
                            ),
                            pagination,
                        ),
                    )
                    return
                case "MultiChoice":
                    await call.edit(
                        text,
                        reply_markup=additonal_button_row
                        + self._put_pagination_before_nav(
                            self._generate_multi_choice_markup(
                                call, mod, config_opt, obj_type
                            ),
                            pagination,
                        ),
                    )
                    return

        text = self.strings[
            (
                "configuring_option"
                if isinstance(obj_type, bool)
                else "configuring_option_lib"
            )
        ].format(*args)

        text, pagination = self._paginate_text_markup(
            text,
            page,
            functools.partial(
                self.inline__configure_option,
                mod=mod,
                config_opt=config_opt,
                force_hidden=force_hidden,
                obj_type=obj_type,
            ),
            with_media=True,
        )

        markup = additonal_button_row + [
            [
                {
                    "text": self.strings["enter_value_btn"],
                    "input": self.strings["enter_value_desc"],
                    "handler": self.inline__set_config,
                    "args": (
                        mod,
                        config_opt,
                        getattr(call, "inline_message_id", None)
                        or getattr(call, "message_id", None),
                    ),
                    "kwargs": {"obj_type": obj_type},
                }
            ],
            [
                {
                    "text": self.strings["set_default_btn"],
                    "callback": self.inline__reset_default,
                    "args": (mod, config_opt),
                    "kwargs": {"obj_type": obj_type},
                }
            ],
            *pagination,
            [
                {
                    "text": self.strings["back_btn"],
                    "callback": self.inline__configure,
                    "args": (mod,),
                    "style": "primary",
                    "kwargs": self._guess_back_to_page(mod, config_opt, obj_type),
                },
                {
                    "text": self.strings["close_btn"],
                    "action": "close",
                    "style": "danger", "emoji_id": 5283176512747507510},
            ],
        ]
        try:
            await call.edit(text, reply_markup=markup)
        except Exception:
            logger.exception("configure_option edit failed")
            with contextlib.suppress(Exception):
                await call.edit(self._clip_cfg_text(text, 500), reply_markup=markup)
            with contextlib.suppress(Exception):
                await call.answer("⚠️ text truncated", show_alert=False)

    async def inline__configure_page(
        self,
        call: InlineCall,
        page: int = 0,
        mod: str = "",
        obj_type: bool | str = False,
        folder: str | None = None,
        category: str | None = None,
    ):
        await self.inline__configure(
            call,
            mod,
            page=page,
            obj_type=obj_type,
            folder=folder,
            category=category,
        )

    async def inline__configure(
        self,
        call: InlineCall,
        mod: str,
        page: int = 0,
        obj_type: bool | str = False,
        folder: str | None = None,
        category: str | None = None,
    ):

        module = self.lookup(mod)
        grouped = module.config.grouped_options()

        def fmt_value(option: str) -> str:
            value = self._get_inline_value(mod, option)
            if len(value) >= 200:
                value = list(utils.smart_split(*html.parse(value), 200))[0] + "..."
            return value

        close_btn = {
            "text": self.strings["close_btn"],
            "action": "close",
            "style": "danger", "emoji_id": 5283176512747507510}

        if category is not None:
            params = list(grouped.get(category, []))
            option_lines = [
                f"<tg-emoji emoji-id=5253713110111365241>▫️</tg-emoji> <code>{utils.escape_html(p)}</code>: {fmt_value(p)}"
                for p in params
            ]
            options_text = "\n".join(option_lines) if option_lines else "No options"

            cat_doc = self._get_category_doc(module, category)

            cat_text = self.strings[
                (
                    "configuring_category"
                    if isinstance(obj_type, bool)
                    else "configuring_category_lib"
                )
            ].format(
                utils.escape_html(mod),
                utils.escape_html(category),
                utils.escape_html(cat_doc),
                options_text,
            )
            cat_text, pagination = self._paginate_text_markup(
                cat_text,
                page,
                functools.partial(
                    self.inline__configure_page,
                    mod=mod,
                    obj_type=obj_type,
                    category=category,
                ),
            )

            return await call.edit(
                cat_text,
                reply_markup=list(
                    utils.chunks(
                        [
                            {
                                "text": opt,
                                "callback": self.inline__configure_option,
                                "kwargs": {
                                    "obj_type": obj_type,
                                    "mod": mod,
                                    "config_opt": opt,
                                },
                            }
                            for opt in params
                        ],
                        2,
                    )
                )
                + pagination
                + [
                    [
                        {
                            "text": self.strings["back_btn"],
                            "callback": self.inline__configure,
                            "args": (mod,),
                            "style": "primary",
                            "kwargs": {"obj_type": obj_type},
                        },
                        close_btn,
                    ]
                ],
            )

        elif folder is not None:
            params = list(module.config)
            option_lines = [
                f"<tg-emoji emoji-id=5253713110111365241>▫️</tg-emoji> <code>{utils.escape_html(p)}</code>: {fmt_value(p)}"
                for p in params
            ]
            text = "\n".join(option_lines) if option_lines else "No options"
            text = self.strings[
                ("configuring_mod" if isinstance(obj_type, bool) else "configuring_lib")
            ].format(utils.escape_html(mod), text)
            text, pagination = self._paginate_text_markup(
                text,
                page,
                functools.partial(
                    self.inline__configure_page,
                    mod=mod,
                    obj_type=obj_type,
                    folder=folder,
                ),
            )

            return await call.edit(
                text,
                reply_markup=list(
                    utils.chunks(
                        [
                            {
                                "text": opt,
                                "callback": self.inline__configure_option,
                                "kwargs": {
                                    "obj_type": obj_type,
                                    "mod": mod,
                                    "config_opt": opt,
                                },
                            }
                            for opt in params
                        ],
                        2,
                    )
                )
                + pagination
                + [
                    [
                        {
                            "text": self.strings["back_btn"],
                            "callback": self.inline__global_config,
                            "style": "primary",
                            "kwargs": {"obj_type": obj_type},
                        },
                        close_btn,
                    ]
                ],
            )

        sections = []
        btns = []
        for section_name, section_params in grouped.items():
            if section_name is None:
                visible = [
                    p
                    for p in section_params
                    if not getattr(module.config._config.get(p), "folder", None)
                ]
                if not visible:
                    continue
                sections.append(
                    "\n".join(
                        "<tg-emoji emoji-id=5253713110111365241>▫️</tg-emoji> <code>{}</code>: {}".format(
                            utils.escape_html(p), fmt_value(p)
                        )
                        for p in visible
                    )
                )
                btns += [
                    {
                        "text": opt,
                        "callback": self.inline__configure_option,
                        "kwargs": {"obj_type": obj_type, "mod": mod, "config_opt": opt},
                    }
                    for opt in visible
                ]
            else:
                cat_lines = [
                    "∟ <tg-emoji emoji-id=5253713110111365241>▫️</tg-emoji> <code>{}</code>: {}".format(
                        utils.escape_html(p), fmt_value(p)
                    )
                    for p in section_params
                ]
                cat_text = [
                    self.strings["category_header"].format(
                        utils.escape_html(section_name)
                    ),
                    "<blockquote expandable>" + "\n".join(cat_lines),
                    "</blockquote>",
                ]
                sections.append("\n".join(cat_text))
                btns.append(
                    {
                        "text": f"📂 {section_name}",
                        "callback": self.inline__configure,
                        "args": (mod,),
                        "kwargs": {"obj_type": obj_type, "category": section_name},
                    }
                )

        text = "\n".join(sections).lstrip("\n") if sections else "No options"
        text = self.strings[
            "configuring_mod" if isinstance(obj_type, bool) else "configuring_lib"
        ].format(utils.escape_html(mod), text)
        text, pagination = self._paginate_text_markup(
            text,
            page,
            functools.partial(self.inline__configure_page, mod=mod, obj_type=obj_type),
        )

        await call.edit(
            text,
            reply_markup=list(utils.chunks(btns, 2))
            + pagination
            + [
                [
                    {
                        "text": self.strings["back_btn"],
                        "callback": self.inline__global_config,
                        "style": "primary",
                        "kwargs": {"obj_type": obj_type},
                    },
                    close_btn,
                ]
            ],
        )

    def _fuzzy_lookup_configurable(self, query: str) -> tuple[str | None, bool]:
        query_lower = query.lower()
        best_score = -1.0
        best_name: str | None = None

        for mod in self.allmodules.modules:
            if not hasattr(mod, "config") or not mod.config:
                continue
            try:
                mod_name = (
                    mod.strings("name")
                    if callable(mod.strings)
                    else mod.__class__.__name__
                )
            except Exception:
                mod_name = mod.__class__.__name__

            cls_name = mod.__class__.__name__
            names = {mod_name, cls_name}
            if cls_name.endswith("Mod"):
                names.add(cls_name[:-3])

            for name in names:
                if name.lower() == query_lower:
                    return mod_name, True
                score = difflib.SequenceMatcher(None, query_lower, name.lower()).ratio()
                if score > best_score:
                    best_score = score
                    best_name = mod_name

        for lib in self.allmodules.libraries:
            if not hasattr(lib, "config") or not lib.config:
                continue
            lib_name = getattr(lib, "name", lib.__class__.__name__)
            if lib_name.lower() == query_lower:
                return lib_name, True
            score = difflib.SequenceMatcher(None, query_lower, lib_name.lower()).ratio()
            if score > best_score:
                best_score = score
                best_name = lib_name

        return best_name, False

    def _get_all_folders(self) -> dict:
        folders = {}
        for mod in self.allmodules.modules:
            if not hasattr(mod, "config") or not mod.config:
                continue
            mod_name = (
                mod.strings("name") if callable(mod.strings) else mod.__class__.__name__
            )
            module_folders = set()
            for param in mod.config:
                config_value = mod.config._config.get(param)
                if (
                    config_value
                    and hasattr(config_value, "folder")
                    and config_value.folder
                ):
                    module_folders.add(config_value.folder)

            for folder_name in module_folders:
                if folder_name not in folders:
                    folders[folder_name] = {}
                folders[folder_name][mod_name] = [p for p in mod.config]
        try:
            preset_folders = self.db.get("presets", "folders")
        except Exception:
            preset_folders = {}

        if preset_folders:
            for folder_name, mod_list in preset_folders.items():
                if folder_name not in folders:
                    folders[folder_name] = {}
                for raw_mod in mod_list:
                    for mod in self.allmodules.modules:
                        try:
                            if mod.__class__.__name__.lower() == raw_mod.lower():
                                mod_name = (
                                    mod.strings("name")
                                    if callable(mod.strings)
                                    else mod.__class__.__name__
                                )
                                if mod_name not in folders[folder_name]:
                                    folders[folder_name][mod_name] = [
                                        p for p in mod.config
                                    ]
                                break
                        except Exception:
                            continue

        return folders

    async def inline__choose_category(self, call: Message | InlineCall):
        all_folders = self._get_all_folders()

        folder_btns = [
            {
                "text": f"📁 {folder_name}",
                "callback": self.inline__global_folder,
                "kwargs": {"folder": folder_name},
            }
            for folder_name in sorted(all_folders.keys())
        ]

        markup = [
                [
                    {
                        "text": self.strings["builtin"],
                        "callback": self.inline__global_config,
                        "kwargs": {"obj_type": True},
                        "emoji_id": 5321304062715517873,
                    },
                    {
                        "text": self.strings["external"],
                        "callback": self.inline__global_config,
                        "emoji_id": 5319139188744936824,
                    },
                ],
                *(
                    [
                        [
                            {
                                "text": self.strings["libraries"],
                                "callback": self.inline__global_config,
                                "kwargs": {"obj_type": "library"},
                            }
                        ]
                    ]
                    if self.allmodules.libraries
                    and any(hasattr(lib, "config") for lib in self.allmodules.libraries)
                    else []
                ),
                *list(utils.chunks(folder_btns, 2)),
                [
                    {
                        "text": self.strings["close_btn"],
                        "action": "close",
                        "style": "danger",
                        "emoji_id": 5283176512747507510,
                    }
                ],
            ]
        # Rich only (no photo) — banner inside Rich HTML
        if isinstance(call, InlineCall) or getattr(call, "inline_message_id", None):
            await self._safe_cfg_edit(
                call, self.strings["choose_core"], reply_markup=markup
            )
        else:
            await self._cfg_form(
                self.strings["choose_core"],
                message=call,
                reply_markup=markup,
            )

    async def _send_initial_config_form(
        self,
        message: Message,
        handler: typing.Callable[..., typing.Awaitable[typing.Any]],
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        draft = _InlineFormDraft()
        await handler(draft, *args, **kwargs)

        if draft.text is None:
            return

        form_kwargs = dict(draft.kwargs)
        form_kwargs.pop("inline_message_id", None)
        # Do NOT inject photo/gif/video — that forces classic Inline Mode.
        # Banner goes into Rich HTML as <figure> inside _cfg_rich_html / _cfg_form.
        for _k in ("photo", "video", "gif", "file", "audio"):
            form_kwargs.pop(_k, None)
        await self._cfg_form(
            draft.text,
            message=message,
            reply_markup=draft.reply_markup,
            silent=True,
            **form_kwargs,
        )

    async def inline__global_folder(
        self,
        call: InlineCall,
        folder: str,
    ):
        all_folders = self._get_all_folders()
        folder_options = all_folders.get(folder, {})

        btns = [
            {
                "text": f"{mod_name}",
                "callback": self.inline__configure,
                "kwargs": {"obj_type": False, "mod": mod_name, "folder": folder},
            }
            for mod_name in sorted(folder_options.keys())
        ]

        text_parts = []
        for mod_name, params in folder_options.items():
            try:
                raw_parts = []
                for param in params:
                    try:
                        raw_value = str(self.lookup(mod_name).config[param])
                        if len(raw_value) > 100:
                            raw_value = raw_value[:100] + "..."
                        raw_parts.append(
                            f"<code>{utils.escape_html(param)}</code>: <code>{utils.escape_html(raw_value)}</code>"
                        )
                    except Exception:
                        raw_parts.append(f"<code>{utils.escape_html(param)}</code>")
                text_parts.append(
                    f"<tg-emoji emoji-id=5253713110111365241>▫️</tg-emoji> <b>{utils.escape_html(mod_name)}</b>"
                )
            except Exception:
                text_parts.append(
                    f"<tg-emoji emoji-id=5253713110111365241>▫️</tg-emoji> <b>{utils.escape_html(mod_name)}</b>"
                )

        await call.edit(
            self.strings["configuring_folder"].format(
                utils.escape_html(folder),
                "\n".join(text_parts) if text_parts else "No options",
            ),
            reply_markup=list(utils.chunks(btns, 1))
            + [
                [
                    {
                        "text": self.strings["back_btn"],
                        "callback": self.inline__choose_category,
                        "style": "primary",
                    },
                    {
                        "text": self.strings["close_btn"],
                        "action": "close",
                        "style": "danger", "emoji_id": 5283176512747507510},
                ]
            ],
        )

    async def inline__global_config(
        self,
        call: InlineCall,
        page: int = 0,
        obj_type: bool | str = False,
    ):
        if isinstance(obj_type, bool):
            to_config = [
                mod.strings("name")
                for mod in self.allmodules.modules
                if hasattr(mod, "config")
                and callable(mod.strings)
                and (mod.__origin__.startswith("<core") or not obj_type)
                and (not mod.__origin__.startswith("<core") or obj_type)
            ]
        else:
            to_config = [
                lib.name for lib in self.allmodules.libraries if hasattr(lib, "config")
            ]

        to_config.sort()

        kb = []
        for mod_row in utils.chunks(
            to_config[page * NUM_ROWS * ROW_SIZE : (page + 1) * NUM_ROWS * ROW_SIZE],
            3,
        ):
            row = [
                {
                    "text": btn,
                    "callback": self.inline__configure,
                    "args": (btn,),
                    "kwargs": {"obj_type": obj_type},
                }
                for btn in mod_row
            ]
            kb += [row]

        if len(to_config) > NUM_ROWS * ROW_SIZE:
            kb += self.inline.build_pagination(
                callback=functools.partial(
                    self.inline__global_config, obj_type=obj_type
                ),
                total_pages=ceil(len(to_config) / (NUM_ROWS * ROW_SIZE)),
                current_page=page + 1,
            )

        kb += [
            [
                {
                    "text": self.strings["back_btn"],
                    "callback": self.inline__choose_category,
                    "style": "primary",
                },
                {
                    "text": self.strings["close_btn"],
                    "action": "close",
                    "style": "danger", "emoji_id": 5283176512747507510},
            ]
        ]

        await call.edit(
            self.strings[
                "configure" if isinstance(obj_type, bool) else "configure_lib"
            ],
            reply_markup=kb,
        )

    @staticmethod
    def _get_config_obj_type(instance: typing.Any) -> bool | str:
        if isinstance(instance, loader.Library):
            return "library"

        return instance.__origin__.startswith("<core")

    def _resolve_configurable(
        self,
        query: str,
    ) -> tuple[str | None, typing.Any, bool | str | None]:
        if (instance := self.lookup(query)) and hasattr(instance, "config"):
            return query, instance, self._get_config_obj_type(instance)

        fuzzy_name, _ = self._fuzzy_lookup_configurable(query)
        if fuzzy_name and (instance := self.lookup(fuzzy_name)):
            if hasattr(instance, "config") and instance.config:
                return fuzzy_name, instance, self._get_config_obj_type(instance)

        return None, None, None

    @staticmethod
    def _category_option(
        instance: typing.Any,
        category: str,
        option: str,
    ) -> str | None:
        if option in HikkariConfigMod._config_categories(instance).get(category, []):
            return option

        return None

    def _parse_config_update(
        self,
        instance: typing.Any,
        raw: str,
        reply_text: str | None = None,
        first_part: bool = False,
    ) -> tuple[str, str] | None:
        if first_part:
            split = raw.split(maxsplit=3)
            if len(split) >= 4:
                _, category, option, value = split
                if config_opt := self._category_option(instance, category, option):
                    return config_opt, value

            split = raw.split(maxsplit=2)
            if len(split) >= 3 and split[1] in instance.config:
                return split[1], split[2]

            if len(split) == 2 and reply_text and split[1] in instance.config:
                return split[1], reply_text

            return None

        split = raw.split(maxsplit=2)
        if len(split) >= 3:
            category, option, value = split
            if config_opt := self._category_option(instance, category, option):
                return config_opt, value

        split = raw.split(maxsplit=1)
        if len(split) >= 2:
            return split[0], split[1]

        return None

    async def _apply_config_updates(
        self,
        message: Message,
        mod: str,
        instance: typing.Any,
        first_update: tuple[str, str],
        parts: list[str],
    ) -> None:
        updates = []

        for option, value in [first_update]:
            if option not in instance.config:
                await utils.answer(message, self.strings["no_option"])
                return

            try:
                prev = None
                with contextlib.suppress(Exception):
                    prev = instance.config[option]
                instance.config[option] = value
                # If banner option left audio mode → delete old track files
                if self._is_banner_option(str(option)):
                    new_s = str(value or "")
                    if not (
                        new_s.startswith("audio:")
                        or new_s.startswith("audio_ref:")
                        or (
                            isinstance(value, (list, tuple))
                            and any(
                                str(x).startswith(("audio:", "audio_ref:"))
                                for x in value
                            )
                        )
                    ):
                        self._cleanup_audio_banner_files(mod, str(option), prev)
            except loader.validators.ValidationError as e:
                await utils.answer(
                    message, self.strings["validation_error"].format(e.args[0])
                )
                return

            updates.append((option, self._get_value(mod, option)))

        for part in parts:
            update = self._parse_config_update(instance, part)
            if update is None:
                await utils.answer(message, self.strings["args"])
                return

            option, value = update
            if option not in instance.config:
                await utils.answer(message, self.strings["no_option"])
                return

            try:
                instance.config[option] = value
            except loader.validators.ValidationError as e:
                await utils.answer(
                    message, self.strings["validation_error"].format(e.args[0])
                )
                return

            updates.append((option, self._get_value(mod, option)))

        lines = []
        for option, value in updates:
            lines.append(
                self.strings[
                    (
                        "option_saved"
                        if isinstance(instance, loader.Module)
                        else "option_saved_lib"
                    )
                ].format(utils.escape_html(option), utils.escape_html(mod), value)
            )

        await utils.answer(message, "\n".join(lines))


    _BANNER_OPTS = frozenset({
        "banner_url", "banner", "media", "media_url", "photo", "pic",
    })

    @staticmethod
    def _is_banner_option(option: str) -> bool:
        o = (option or "").lower()
        if o in HikkariConfigMod._BANNER_OPTS:
            return True
        return "banner" in o

    @staticmethod
    def _reply_has_audio(reply) -> bool:
        if not reply:
            return False
        # Telethon/hikkaritl convenience props
        if getattr(reply, "audio", None) or getattr(reply, "voice", None):
            return True
        # Any document with audio attribute / mime
        doc = getattr(reply, "document", None)
        if doc:
            for attr in getattr(doc, "attributes", []) or []:
                if "Audio" in type(attr).__name__:
                    return True
            mime = (getattr(doc, "mime_type", None) or "").lower()
            if mime.startswith("audio/"):
                return True
        # File wrapper (message.file)
        f = getattr(reply, "file", None)
        if f is not None:
            mime = (getattr(f, "mime_type", None) or "").lower()
            if mime.startswith("audio/"):
                return True
            name = (getattr(f, "name", None) or "").lower()
            if any(name.endswith(ext) for ext in (".mp3", ".ogg", ".m4a", ".flac", ".wav", ".opus")):
                return True
        # media object
        media = getattr(reply, "media", None)
        if media is not None:
            doc2 = getattr(media, "document", None)
            if doc2:
                for attr in getattr(doc2, "attributes", []) or []:
                    if "Audio" in type(attr).__name__:
                        return True
                mime = (getattr(doc2, "mime_type", None) or "").lower()
                if mime.startswith("audio/"):
                    return True
        return False


    def _cleanup_audio_banner_files(self, mod: str, option: str, prev_value=None) -> None:
        """Delete local audio banner files when track is replaced or cleared."""
        from pathlib import Path as _P
        with contextlib.suppress(Exception):
            try:
                from .. import main as _main
                base = _P(getattr(_main, "BASE_PATH", _P.cwd()))
            except Exception:
                base = _P.cwd()
            dest_dir = base / "assets" / "banners"
            if dest_dir.is_dir():
                safe_mod = re.sub(r"[^\w\-]+", "_", str(mod))[:40]
                safe_opt = re.sub(r"[^\w\-]+", "_", str(option))[:40]
                prefix = f"{safe_mod}_{safe_opt}_"
                for old_f in list(dest_dir.glob(prefix + "*")):
                    with contextlib.suppress(Exception):
                        if old_f.is_file():
                            old_f.unlink()
            # Also remove explicit path from previous audio: value
            if prev_value:
                items = prev_value if isinstance(prev_value, (list, tuple)) else [prev_value]
                for item in items:
                    s = str(item or "")
                    if s.startswith("audio:"):
                        p = _P(s[6:].strip())
                        if p.is_file():
                            with contextlib.suppress(Exception):
                                p.unlink()


    async def _save_reply_audio_banner(self, reply, mod: str, option: str) -> str | None:
        """Download replied track into assets/banners and return absolute path."""
        from pathlib import Path as _P
        try:
            from .. import main as _main
            base = _P(getattr(_main, "BASE_PATH", _P.cwd()))
        except Exception:
            base = _P.cwd()
        dest_dir = base / "assets" / "banners"
        dest_dir.mkdir(parents=True, exist_ok=True)

        ext = ".ogg"
        with contextlib.suppress(Exception):
            if getattr(reply, "file", None) and getattr(reply.file, "ext", None):
                ext = reply.file.ext if reply.file.ext.startswith(".") else f".{reply.file.ext}"
        safe_mod = re.sub(r"[^\w\-]+", "_", str(mod))[:40]
        safe_opt = re.sub(r"[^\w\-]+", "_", str(option))[:40]

        # Drop previous tracks for this module + option
        prefix = f"{safe_mod}_{safe_opt}_"
        for old_f in list(dest_dir.glob(prefix + "*")):
            with contextlib.suppress(Exception):
                if old_f.is_file():
                    old_f.unlink()

        path = dest_dir / f"{safe_mod}_{safe_opt}_{getattr(reply, 'id', 0)}{ext}"
        try:
            await reply.download_media(file=str(path))
        except Exception:
            logger.exception("audio banner download failed")
            return None
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        return str(path.resolve())



    async def _upload_banner_x0(self, reply) -> str | None:
        """Download replied media, reject >20MB, upload to x0.at, return URL."""
        import os
        import aiohttp
        size = 0
        with contextlib.suppress(Exception):
            doc = getattr(reply, "document", None)
            if doc is not None:
                size = int(getattr(doc, "size", 0) or 0)
            if getattr(reply, "video", None) is not None:
                size = int(getattr(reply.video, "size", 0) or size)
            if getattr(reply, "file", None) is not None:
                size = int(getattr(reply.file, "size", 0) or size)
        if size and size > 20 * 1024 * 1024:
            return "__TOO_BIG__"
        path = await reply.download_media()
        if not path:
            return None
        try:
            async with aiohttp.ClientSession() as s:
                with open(path, "rb") as fh:
                    data = aiohttp.FormData()
                    data.add_field("file", fh, filename=os.path.basename(path))
                    async with s.post("https://x0.at", data=data, timeout=aiohttp.ClientTimeout(total=120)) as r:
                        url = (await r.text()).strip()
            if url and url.startswith("http"):
                return url
        except Exception:
            return None
        finally:
            with contextlib.suppress(Exception):
                os.unlink(path)
        return None


    async def _configcmd_impl(self, message: Message):
        raw = utils.get_args_raw(message).strip()
        args_s = raw.split()

        if not args_s:
            await self.inline__choose_category(message)
            return

        mod_name, instance, obj_type = self._resolve_configurable(args_s[0])
        if not mod_name or not instance or obj_type is None:
            await self.inline__choose_category(message)
            return

        parts = [part.strip() for part in raw.split("&&") if part.strip()]
        reply = await message.get_reply_message()
        reply_text = reply.raw_text if reply and reply.raw_text else None

        # Reply to audio/track → set banner_url (or any *banner* option) to that track
        # Usage: reply to music → .fcfg Tester banner_url   (prefix e.g. 1fcfg)
        if reply and len(args_s) >= 2:
            # case-insensitive option match
            opt_arg = args_s[1]

            # Photo / video / document banner → x0.at (max 20MB)
            _opt_l = str(opt_arg).lower()
            if _opt_l in self._BANNER_OPTS or _opt_l == "banner_url":
                has_vis = bool(getattr(reply, "photo", None) or getattr(reply, "video", None) or getattr(reply, "document", None))
                is_audio = bool(getattr(reply, "audio", None) or getattr(reply, "voice", None))
                if has_vis and not is_audio:
                    url = await self._upload_banner_x0(reply)
                    if url == "__TOO_BIG__":
                        await utils.answer(
                            message,
                            "<emoji document_id=5447644880824181073>⚠️</emoji> Баннер <b>&gt; 20 МБ</b>. "
                            "Quote/invert и превью не сработают. Дай файл легче.",
                        )
                        return
                    if not url:
                        await utils.answer(message, "<emoji document_id=5447644880824181073>⚠️</emoji> Не удалось загрузить на x0.at")
                        return
                    mod = None
                    for m in self.allmodules.modules:
                        n = (getattr(m, "strings", {}) or {}).get("name") or type(m).__name__
                        if str(n).lower() == str(args_s[0]).lower() or type(m).__name__.lower() == str(args_s[0]).lower():
                            mod = m
                            break
                    if not mod or not getattr(mod, "config", None):
                        await utils.answer(message, "<emoji document_id=5447644880824181073>⚠️</emoji> Модуль не найден")
                        return
                    try:
                        mod.config[opt_arg] = url
                    except Exception:
                        try:
                            mod.config["banner_url"] = url
                        except Exception as e:
                            await utils.answer(message, f"⚠️ {e}")
                            return
                    with contextlib.suppress(Exception):
                        self._db.save()
                    await utils.answer(
                        message,
                        f"<emoji document_id=5256182535917940722>⤵️</emoji> banner → <code>{utils.escape_html(url)}</code>",
                    )
                    return
            option = next(
                (k for k in instance.config.keys() if str(k).lower() == opt_arg.lower()),
                None,
            )
            if (
                option is not None
                and self._is_banner_option(str(option))
                and self._reply_has_audio(reply)
            ):
                # Instant: store Telegram document ref (no re-upload on ping)
                from ..utils.other import pack_audio_ref_from_message

                ref = pack_audio_ref_from_message(reply)
                # Still download local fallback + delete old files
                path = await self._save_reply_audio_banner(reply, mod_name, str(option))
                value = ref or (f"audio:{path}" if path else None)
                if not value:
                    await utils.answer(
                        message,
                        "<tg-emoji emoji-id=5240241223632954241>🚫</tg-emoji> "
                        "<b>Не удалось сохранить трек</b>\n"
                        "<i>Реплай должен быть на аудио/музыку</i>",
                    )
                    return
                try:
                    instance.config[option] = value
                except Exception:
                    try:
                        instance.config[option] = [value]
                    except Exception as e2:
                        await utils.answer(
                            message,
                            "<tg-emoji emoji-id=5240241223632954241>🚫</tg-emoji> "
                            f"<b>Не сохранено:</b> <code>{utils.escape_html(str(e2))}</code>",
                        )
                        return
                meta = ""
                try:
                    from ..utils.other import unpack_audio_ref
                    d = unpack_audio_ref(value) or {}
                    t = d.get("title") or ""
                    p = d.get("performer") or ""
                    if t or p:
                        meta = f"\n<i>{utils.escape_html(p)} — {utils.escape_html(t)}</i>"
                except Exception:
                    pass
                await utils.answer(
                    message,
                    "<tg-emoji emoji-id=5256182535917940722>✅</tg-emoji> "
                    f"<b>{utils.escape_html(str(option))}</b> → трек как баннер\n"
                    f"<code>{utils.escape_html(mod_name)}</code>"
                    f"{meta}\n"
                    "<i>Отправка без повторной загрузки</i>",
                )
                return

        first_update = self._parse_config_update(
            instance,
            parts[0],
            reply_text=reply_text,
            first_part=True,
        )

        if first_update is not None:
            await self._apply_config_updates(
                message,
                mod_name,
                instance,
                first_update,
                parts[1:],
            )
            return

        if len(args_s) == 1:
            await self._send_initial_config_form(
                message,
                self.inline__configure,
                mod_name,
                obj_type=obj_type,
            )
            return

        if args_s[1] in instance.config.keys():
            await self._send_initial_config_form(
                message,
                self.inline__configure_option,
                mod=mod_name,
                config_opt=args_s[1],
                obj_type=obj_type,
            )
            return

        if args_s[1] in self._config_categories(instance):
            if len(args_s) >= 3 and (
                config_opt := self._category_option(instance, args_s[1], args_s[2])
            ):
                await self._send_initial_config_form(
                    message,
                    self.inline__configure_option,
                    mod=mod_name,
                    config_opt=config_opt,
                    obj_type=obj_type,
                )
                return

            await self._send_initial_config_form(
                message,
                self.inline__configure,
                mod_name,
                obj_type=obj_type,
                category=args_s[1],
            )
            return

        await self.inline__choose_category(message)

    async def configcmd(self, message: Message):
        """Настроить модули / configure modules"""
        await self._configcmd_impl(message)

    @loader.command(alias="fcfg")
    async def cfgcmd(self, message: Message):
        """Настроить модули / configure modules"""
        await self._configcmd_impl(message)



    @loader.command()
    async def uploadcfg(self, message: Message):
        """<module> — экспорт конфига в .txt / export module config"""
        import json
        from io import BytesIO
        name = (utils.get_args_raw(message) or "").strip()
        if not name:
            await utils.answer(
                message,
                f"<emoji document_id=5436113877181941026>❓</emoji> <code>{self.get_prefix()}uploadcfg ModuleName</code>",
            )
            return
        mod = None
        for m in self.allmodules.modules:
            n = (getattr(m, "strings", {}) or {}).get("name") or type(m).__name__
            if str(n).lower() == name.lower() or type(m).__name__.lower() == name.lower():
                mod = m
                break
        if not mod or not getattr(mod, "config", None):
            await utils.answer(message, "<emoji document_id=5447644880824181073>⚠️</emoji> Модуль не найден или без конфига")
            return
        keys = list(getattr(mod.config, "_config", {}) or {})
        if not keys:
            try:
                keys = list(mod.config.keys())
            except Exception:
                keys = []
        options = {}
        for k in keys:
            with contextlib.suppress(Exception):
                options[k] = mod.config[k]
        data = {
            "__hikkari_cfg__": 1,
            "module": (getattr(mod, "strings", {}) or {}).get("name") or type(mod).__name__,
            "options": options,
        }
        raw = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        bio = BytesIO(raw.encode("utf-8"))
        bio.name = f"{data['module']}_config.txt"
        await message.client.send_file(
            message.peer_id,
            bio,
            caption=f"<emoji document_id=5283176512747507510>✨</emoji> cfg · <b>{utils.escape_html(data['module'])}</b>",
        )
        with contextlib.suppress(Exception):
            await message.delete()

    @loader.command()
    async def loadcfg(self, message: Message):
        """reply на .txt — импорт конфига модуля / import config from uploadcfg"""
        import json
        reply = await message.get_reply_message()
        if not reply or not reply.document:
            await utils.answer(
                message,
                "<emoji document_id=5447644880824181073>⚠️</emoji> Reply на .txt от <code>uploadcfg</code>",
            )
            return
        path = await reply.download_media()
        try:
            data = json.loads(open(path, encoding="utf-8").read())
        except Exception:
            await utils.answer(message, "<emoji document_id=5447644880824181073>⚠️</emoji> Не JSON/конфиг")
            return
        if not isinstance(data, dict) or data.get("__hikkari_cfg__") != 1:
            await utils.answer(
                message,
                "<emoji document_id=5447644880824181073>⚠️</emoji> Нет маркера <code>__hikkari_cfg__</code>",
            )
            return
        mod_name = data.get("module")
        opts = data.get("options") or {}
        mod = None
        for m in self.allmodules.modules:
            n = (getattr(m, "strings", {}) or {}).get("name") or type(m).__name__
            if str(n).lower() == str(mod_name).lower():
                mod = m
                break
        if not mod or not getattr(mod, "config", None):
            await utils.answer(
                message,
                f"<emoji document_id=5447644880824181073>⚠️</emoji> Модуль <code>{utils.escape_html(str(mod_name))}</code> не загружен — конфиг не применён",
            )
            return
        applied = 0
        for k, v in opts.items():
            try:
                mod.config[k] = v
                applied += 1
            except Exception:
                continue
        with contextlib.suppress(Exception):
            self._db.save()
        await utils.answer(
            message,
            f"<emoji document_id=5256182535917940722>⤵️</emoji> Конфиг <b>{utils.escape_html(str(mod_name))}</b> применён ({applied} опций)",
        )


    @loader.command()
    async def catcmd(self, message: Message):
        """<module> <option> — показать значение опции / show config value"""
        args = utils.get_args_raw(message) or ""
        parts = args.split(None, 1)
        if len(parts) < 2:
            await utils.answer(
                message,
                "<tg-emoji emoji-id=5210952531676504517>🚫</tg-emoji> "
                "<b>Usage:</b> <code>.cat &lt;module&gt; &lt;option&gt;</code>\n"
                "Example: <code>.cat hikkariinfo custom_message</code>",
            )
            return

        mod_name, option = parts[0].strip(), parts[1].strip()
        mod = self.lookup(mod_name)
        if not mod:
            low = mod_name.lower().replace(" ", "")
            for m in self.allmodules.modules:
                names = {
                    getattr(m, "name", "") or "",
                    m.__class__.__name__,
                    m.__class__.__name__.replace("Mod", ""),
                }
                if any(low == (n or "").lower().replace(" ", "") for n in names):
                    mod = m
                    break
                if any(low in (n or "").lower().replace(" ", "") for n in names if n):
                    mod = m
                    break
        if not mod or not hasattr(mod, "config") or mod.config is None:
            await utils.answer(
                message,
                f"<tg-emoji emoji-id=5210952531676504517>🚫</tg-emoji> "
                f"Module <code>{utils.escape_html(mod_name)}</code> not found or has no config",
            )
            return

        keys = list(mod.config)
        key = next((k for k in keys if str(k).lower() == option.lower()), None)
        if key is None:
            key = next((k for k in keys if option.lower() in str(k).lower()), None)
        if key is None:
            opts = ", ".join(
                f"<code>{utils.escape_html(str(k))}</code>" for k in keys[:25]
            )
            await utils.answer(
                message,
                f"<tg-emoji emoji-id=5210952531676504517>🚫</tg-emoji> "
                f"Option <code>{utils.escape_html(option)}</code> not found.\n"
                f"Available: {opts or '—'}",
            )
            return

        try:
            val = mod.config[key]
        except Exception as e:
            await utils.answer(
                message,
                f"<tg-emoji emoji-id=5210952531676504517>🚫</tg-emoji> "
                f"Read error: <code>{utils.escape_html(str(e))}</code>",
            )
            return

        if val is None:
            text = "None"
        elif isinstance(val, (list, tuple)):
            text = "\n".join(str(x) for x in val)
        else:
            text = str(val)

        header = (
            f"<tg-emoji emoji-id=5283176512747507510>✨</tg-emoji> "
            f"<b>{utils.escape_html(str(getattr(mod, 'name', mod.__class__.__name__)))}</b> · "
            f"<code>{utils.escape_html(str(key))}</code>\n\n"
        )
        LIMIT = 3500
        if len(text) <= LIMIT:
            await utils.answer(
                message, header + f"<pre>{utils.escape_html(text)}</pre>"
            )
            return

        file = io.BytesIO(text.encode("utf-8"))
        safe_mod = re.sub(r"[^\w.-]+", "_", str(getattr(mod, "name", "mod")))[:40]
        safe_opt = re.sub(r"[^\w.-]+", "_", str(key))[:40]
        file.name = f"{safe_mod}_{safe_opt}.txt"
        await utils.answer(
            message,
            header + f"<i>Value is too long ({len(text)} chars) — sent as file.</i>",
            file=file,
        )

