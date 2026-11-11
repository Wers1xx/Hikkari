import re
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

import asyncio
import difflib
import inspect
import contextlib
import logging
import re

from hikkaritl.tl.types import Message
from hikkaritl.types import InputMediaWebPage


from .. import loader, utils

logger = logging.getLogger(__name__)


@loader.tds
class Help(loader.Module):
    """Shows help for modules and commands"""

    strings = {"close_btn": "🔻 Закрыть",
        "name": "Help"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "core_emoji",
                "<tg-emoji emoji-id=5778423822940114949>🛡</tg-emoji>",
                lambda: "Core module bullet",
            ),
            loader.ConfigValue(
                "plain_emoji",
                "<tg-emoji emoji-id=5931409969613116639>🛡</tg-emoji>",
                lambda: "Plain module bullet",
            ),
            loader.ConfigValue(
                "empty_emoji",
                "<tg-emoji emoji-id=5100652175172830068>🟠</tg-emoji>",
                lambda: "Empty modules bullet",
            ),
            loader.ConfigValue(
                "desc_icon",
                "<tg-emoji emoji-id=5438496463044752972>⭐️</tg-emoji>",
                lambda: "Desc emoji",
            ),
            loader.ConfigValue(
                "command_emoji",
                "<tg-emoji emoji-id=5197195523794157505>▫️</tg-emoji>",
                lambda: "Emoji for command",
            ),
            loader.ConfigValue(
                "banner_url",
                None,
                lambda: "Banner for .help",
                validator=loader.validators.Union(
                    loader.validators.String(),
                    loader.validators.NoneType(),
                ),
            ),
            loader.ConfigValue(
                "media_quote",
                "False",
                lambda: "quote a banner in help",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "invert_media",
                "False",
                lambda: "invert banner",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "show_preview_in_help",
                True,
                lambda: self.strings["show_preview_in_help"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "rich_mode",
                True,
                lambda: "Use Telegram Rich messages for .help (Premium)",
                validator=loader.validators.Boolean(),
            ),
        )


    @staticmethod
    def _is_out(message) -> bool:
        """True if outgoing Message; False for InlineCall/BotInlineCall/incoming."""
        return bool(getattr(message, "out", False))


    async def _help_form(
        self,
        text: str,
        message,
        reply_markup=None,
        *,
        rich_html: str | None = None,
        banner_url: str | None = None,
    ):
        """Same edit model as HikkariConfig._cfg_form: reuse unit, register buttons, edit in place."""
        import contextlib
        from ..inline.types import InlineCall, InlineMessage, BotInlineCall

        markup = reply_markup or []
        html = rich_html if rich_html is not None else str(text or "")

        with contextlib.suppress(Exception):
            from ..utils.rich_api import to_rich_compatible
            html = to_rich_compatible(html)

        banner_kw = {}
        if banner_url and str(banner_url).startswith(("http://", "https://")):
            banner_kw["photo"] = str(banner_url)

        is_nav = isinstance(message, (InlineCall, InlineMessage, BotInlineCall))

        if is_nav:
            unit_id = getattr(message, "unit_id", None)

            # Update existing unit buttons so callbacks work (like config)
            if unit_id and unit_id in getattr(self.inline, "_units", {}):
                self.inline._units[unit_id]["buttons"] = markup
                self.inline._units[unit_id]["text"] = text
                with contextlib.suppress(Exception):
                    self.inline.generate_markup(unit_id)
                markup = self.inline._units[unit_id].get("buttons") or markup

                full = html
                with contextlib.suppress(Exception):
                    from ..utils.rich_api import markup_to_tg_rows
                    btn_html = markup_to_tg_rows(markup, unit_id) or ""
                    if btn_html:
                        full = f"{html}\n{btn_html}"
                self.inline._units[unit_id]["rich_message"] = full
                self.inline._units[unit_id]["rich_html"] = full

                mid = getattr(message, "inline_message_id", None)
                if mid is None:
                    mid = self.inline._units[unit_id].get("inline_message_id")

                if mid and hasattr(getattr(self.inline, "bot", None), "edit_rich_message"):
                    try:
                        await self.inline.bot.edit_rich_message(
                            html=full,
                            inline_message_id=mid,
                            reply_markup=None,
                        )
                        return True
                    except Exception as e:
                        logger.debug("help edit_rich_message: %s", e)

                try:
                    ok = await message.edit(
                        text,
                        reply_markup=markup,
                        rich_message=full,
                    )
                    if ok is not False:
                        return ok
                except Exception as e:
                    logger.debug("help message.edit: %s", e)

            # No unit / edit failed → form creates unit (buttons registered)
            with contextlib.suppress(Exception):
                m = await self.inline.form(
                    text=str(text)[:200] or "Help",
                    message=message,
                    reply_markup=markup,
                    rich_message=html,
                    silent=True,
                    **banner_kw,
                )
                if m:
                    return m
            with contextlib.suppress(Exception):
                return await self.inline.form(
                    text=str(text)[:200] or "Help",
                    message=message,
                    reply_markup=markup,
                    silent=True,
                    **banner_kw,
                )
            return False

        # Fresh send
        with contextlib.suppress(Exception):
            m = await self.inline.form(
                text=str(text)[:200] or "Help",
                message=message,
                reply_markup=markup,
                rich_message=html,
                silent=True,
                **banner_kw,
            )
            if m:
                return m
        with contextlib.suppress(Exception):
            return await self.inline.form(
                text=str(text)[:200] or "Help",
                message=message,
                reply_markup=markup,
                silent=True,
                **banner_kw,
            )
        return False


    async def client_ready(self):
        # Overwrite stale Help config from old installs (▪️ / 🪐)
        with contextlib.suppress(Exception):
            self.config["core_emoji"] = "<tg-emoji emoji-id=5778423822940114949>🛡</tg-emoji>"
            self.config["plain_emoji"] = "<tg-emoji emoji-id=5931409969613116639>🛡</tg-emoji>"
            self.config["desc_icon"] = "<tg-emoji emoji-id=5438496463044752972>⭐️</tg-emoji>"

    def _get_banner_url(self, doc: str):
        if not doc:
            return None
        match = re.search(r"# ?meta banner: ?(.+)", doc)
        return match.group(1).strip() if match else None


    @staticmethod
    def _linkify_dev(dev: str) -> str:
        import html as html_mod
        import re as _re
        s = (dev or "").strip()
        m = _re.fullmatch(r"@([A-Za-z0-9_]{4,})", s)
        if m:
            u = m.group(1)
            return f'<a href="https://t.me/{u}">@{html_mod.escape(u)}</a>'
        m = _re.fullmatch(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})/?", s, flags=_re.I)
        if m:
            u = m.group(1)
            return f'<a href="https://t.me/{u}">@{html_mod.escape(u)}</a>'
        def repl(mm):
            u = mm.group(1)
            return f'<a href="https://t.me/{u}">@{html_mod.escape(u)}</a>'
        linked = _re.sub(r"@([A-Za-z0-9_]{4,})", repl, s)
        return linked if linked != s else html_mod.escape(s)

    def _get_module_developer(self, module) -> str | None:
        """Extract developer/author from module source meta comments."""
        source = getattr(module, "__source__", None) or ""
        if not source:
            with contextlib.suppress(Exception):
                source = inspect.getsource(module.__class__)
        if not source:
            return None
        for pattern in (
            r"# ?meta developer: ?(.+)",
            r"# ?Author: ?(.+)",
            r"# ?author: ?(.+)",
        ):
            m = re.search(pattern, source, flags=re.I)
            if m:
                dev = m.group(1).strip().strip('"').strip("'")
                # drop trailing year ranges like 2025-2026 for ©️ lines
                if pattern.startswith(r"# ?©️"):
                    dev = re.sub(r",?\s*\d{4}.*$", "", dev).strip()
                if dev:
                    return dev
        return None

    @staticmethod
    def _plain_doc(text: str | None, fallback: str = "") -> str:
        """Strip HTML/emoji tags for Rich table cells; keep readable text."""
        import html as html_mod

        if not text:
            return fallback or ""
        s = str(text)
        # <tg-emoji …>X</tg-emoji> / <emoji …>X</emoji> → X
        s = re.sub(
            r"<tg-emoji\b[^>]*>(.*?)</tg-emoji>",
            r"\1",
            s,
            flags=re.I | re.S,
        )
        s = re.sub(
            r"<emoji\b[^>]*>(.*?)</emoji>",
            r"\1",
            s,
            flags=re.I | re.S,
        )
        # drop remaining tags
        s = re.sub(r"<[^>]+>", "", s)
        s = html_mod.unescape(s)
        # collapse whitespace
        s = re.sub(r"[ \t]+", " ", s).strip()
        return s or (fallback or "")

    @loader.command(
        ru_doc="[args] | Спрячет ваши модули",
        ua_doc="[args] | Сховає ваші модулі",
        de_doc="[args] | Versteckt Ihre Module",
    )
    async def helphide(self, message: Message):
        """[args] | hide your modules"""
        if not (modules := utils.get_args(message)):
            await utils.answer(message, self.strings["no_mod"])
            return

        currently_hidden = self.get("hide", [])
        hidden, shown = [], []
        for module in filter(lambda module: self.lookup(module), modules):
            module = self.lookup(module)
            module = module.__class__.__name__
            if module in currently_hidden:
                currently_hidden.remove(module)
                shown += [module]
            else:
                currently_hidden += [module]
                hidden += [module]

        self.set("hide", currently_hidden)

        await utils.answer(
            message,
            self.strings["hidden_shown"].format(
                len(hidden),
                len(shown),
                "\n".join([f"👁‍🗨 <i>{m}</i>" for m in hidden]),
                "\n".join([f"👁 <i>{m}</i>" for m in shown]),
            ),
        )

    def find_aliases(self, command: str) -> list:
        """Find aliases for command (decorator + user .addalias)."""
        aliases: list[str] = []
        cmd = (command or "").lower().strip()
        if not cmd:
            return []

        func = self.allmodules.commands.get(cmd) or self.allmodules.commands.get(
            command
        )
        if func is not None:
            if getattr(func, "aliases", None):
                aliases.extend(list(func.aliases))
            elif getattr(func, "alias", None):
                aliases.append(func.alias)

        for alias, target in (getattr(self.allmodules, "aliases", None) or {}).items():
            if not alias or not target:
                continue
            target_cmd = str(target).split()[0].lower().strip()
            if target_cmd == cmd and alias.lower() != cmd:
                aliases.append(alias)

        seen: set[str] = set()
        out: list[str] = []
        for a in aliases:
            a = str(a).strip()
            if not a or a.lower() in seen or a.lower() == cmd:
                continue
            seen.add(a.lower())
            out.append(a)
        return out

    def _cmd_label(self, name: str, *, with_prefix: bool = True) -> str:
        """Heroku-style: backupall (backup)."""
        prefix = self.get_prefix() if with_prefix else ""
        al = self.find_aliases(name)
        base = f"{prefix}{name}"
        if not al:
            return base
        return f"{base} ({', '.join(al)})"

    async def modhelp(self, message: Message, args: str, from_list: bool = False):
        if not from_list:
            self._help_nav_from_list = False
        else:
            self._help_nav_from_list = True
        exact = True
        if not (module := self.lookup(args)):
            if method := self.allmodules.dispatch(
                args.lower().strip(self.get_prefix())
            )[1]:
                module = method.__self__
            else:
                module = self.lookup(
                    next(
                        (
                            reversed(
                                sorted(
                                    [
                                        module.strings["name"]
                                        for module in self.allmodules.modules
                                    ],
                                    key=lambda x: difflib.SequenceMatcher(
                                        None,
                                        args.lower(),
                                        x,
                                    ).ratio(),
                                )
                            )
                        ),
                        None,
                    )
                )

                exact = False

        try:
            name = module.strings("name")
        except (KeyError, AttributeError):
            name = getattr(module, "name", "ERROR")

        _name = (
            "{} (v{})".format(
                utils.escape_html(name), ".".join(map(str, module.__version__))
            )
            if hasattr(module, "__version__")
            else utils.escape_html(name)
        )

        reply = "{} <b>{}</b>:".format(
            "<tg-emoji emoji-id=5283176512747507510>✨</tg-emoji>",
            _name,
        )
        inline_cmd = ""
        cmds = ""
        if module.__doc__:
            reply += (
                "\n<i><tg-emoji emoji-id=5879813604068298387>ℹ️</tg-emoji> "
                + utils.escape_html(inspect.getdoc(module))
                + "\n</i>"
            )

        if isinstance(self.lookup(args), loader.Library):
            return await utils.answer(message, self.strings["help_lib"].format(name))

        commands = {
            name: func
            for name, func in module.commands.items()
            if await self.allmodules.check_security(message, func)
        }

        if hasattr(module, "inline_handlers"):
            for name, fun in module.inline_handlers.items():
                inline_cmd += (
                    "\n<tg-emoji emoji-id=5372981976804366741>🤖</tg-emoji>"
                    " <code>{}</code> {}".format(
                        f"@{self.inline.bot_username} {name}",
                        (
                            utils.escape_html(inspect.getdoc(fun))
                            if fun.__doc__
                            else self.strings["undoc"]
                        ),
                    )
                )

        lines = []
        for name, fun in commands.items():
            lines.append(
                f'{self.config["command_emoji"]}'
                " <code>{}{}</code>{} {}".format(
                    utils.escape_html(self.get_prefix()),
                    name,
                    (
                        " ({})".format(
                            ", ".join(
                                "<code>{}{}</code>".format(
                                    utils.escape_html(self.get_prefix()),
                                    alias,
                                )
                                for alias in self.find_aliases(name)
                            )
                        )
                        if self.find_aliases(name)
                        else ""
                    ),
                    (
                        utils.escape_html(inspect.getdoc(fun))
                        if fun.__doc__
                        else self.strings["undoc"]
                    ),
                )
            )
        cmds = "\n".join(lines)
        developer = re.search(
            r"# ?meta developer: ?(.+)", getattr(module, "__source__", None) or ""
        )
        dev_text = developer.group(1).strip() if developer else None
        if not dev_text:
            dev_text = self._get_module_developer(module)
        # never show author from license on built-in modules
        if str(getattr(module, "__origin__", "") or "").startswith("<core"):
            dev_text = None
        placeholders = "\n".join(
            utils.help_placeholders(module.__class__.__name__, self)
        )

        banner_kwargs = {}
        if self.config["show_preview_in_help"]:
            try:
                source = getattr(module, "__source__", None) or ""
                if not source or "# meta banner" not in source.lower():
                    with contextlib.suppress(Exception):
                        from pathlib import Path as _P
                        for attr in ("__file__", "_file"):
                            fp = getattr(module, attr, None)
                            if fp and _P(str(fp)).is_file():
                                source = _P(str(fp)).read_text(
                                    encoding="utf-8", errors="ignore"
                                )
                                break
                banner_url = self._get_banner_url(source) if source else None
                # Module attrs / strings before Help config banner
                if not banner_url and module is not None:
                    for attr in ("banner", "banner_url", "meta_banner", "__banner__"):
                        with contextlib.suppress(Exception):
                            v = getattr(module, attr, None)
                            if isinstance(v, str) and v.startswith(("http://", "https://")):
                                banner_url = v.strip()
                                break
                    if not banner_url:
                        with contextlib.suppress(Exception):
                            for sk in ("banner", "banner_url", "meta_banner"):
                                v = module.strings.get(sk) if hasattr(module, "strings") else None
                                if isinstance(v, str) and v.startswith(("http://", "https://")):
                                    banner_url = v.strip()
                                    break
                    if not banner_url:
                        with contextlib.suppress(Exception):
                            cfg = getattr(module, "config", None)
                            if cfg is not None:
                                for ck in ("banner", "banner_url", "meta_banner"):
                                    try:
                                        v = cfg[ck]
                                    except Exception:
                                        v = None
                                    if isinstance(v, str) and v.startswith(("http://", "https://")):
                                        banner_url = v.strip()
                                        break
                if not banner_url:
                    banner_url = str(self.config.get("banner_url") or "").strip() or None
                if banner_url and str(banner_url).startswith(("http://", "https://")):
                    banner_kwargs = {
                        "file": InputMediaWebPage(banner_url, optional=True),
                        "invert_media": True,
                    }
            except Exception:
                pass


        # Prefer meta developer if regex missed
        if not dev_text:
            dev_text = self._get_module_developer(module)

        # Built-in modules never show developer/author from license headers
        if getattr(module, "__origin__", "").startswith("<core"):
            dev_text = None

        # Rich single-module help (same card as loader)
        try:
            from ..utils.rich import can_use_rich
            from ..utils.rich_api import (
                html_table,
                pick_banner_url,
                inject_banner_html,
                to_rich_compatible,
                try_send_rich,
                markup_to_tg_rows,
            )
            import html as html_mod

            if can_use_rich(self._client, self._db):
                undoc = self._plain_doc(self.strings.get("undoc"), "—")
                rows = []
                for name, fun in list(commands.items())[:50]:
                    try:
                        doc = self._plain_doc(inspect.getdoc(fun), undoc)[:120]
                        rows.append(
                            (
                                html_mod.escape(
                                    self._cmd_label(name, with_prefix=True)
                                ),
                                html_mod.escape(doc),
                            )
                        )
                    except Exception:
                        continue
                if hasattr(module, "inline_handlers"):
                    for name, fun in list(module.inline_handlers.items())[:20]:
                        try:
                            doc = self._plain_doc(inspect.getdoc(fun), undoc)[:120]
                            rows.append(
                                (
                                    html_mod.escape(
                                        f"@{self.inline.bot_username} {name}"
                                    ),
                                    html_mod.escape(doc),
                                )
                            )
                        except Exception:
                            continue
                parts = [f"<h2>{html_mod.escape(str(_name))}</h2>"]
                if module.__doc__:
                    mdoc = self._plain_doc(inspect.getdoc(module), "")[:400]
                    if mdoc:
                        parts.append(f"<p><i>{html_mod.escape(mdoc)}</i></p>")
                if rows:
                    table = html_table(rows, header=("Command", "Description"))
                    parts.append(
                        f"<details>\n<summary><b>Commands</b> ({len(rows)})</summary>\n"
                        f"{table}\n"
                        f"</details>"
                    )
                if placeholders:
                    ph = self._plain_doc(placeholders, "")
                    if ph:
                        parts.append(
                            f"<b>Placeholders</b>\n"
                            f"<p>{html_mod.escape(ph[:500])}</p>"
                        )
                if dev_text:
                    parts.append(
                        f"<p>\u2764\ufe0f Developer: "
                        f"{self._linkify_dev(str(dev_text))}</p>"
                    )
                html = "\n".join(parts)
                with contextlib.suppress(Exception):
                    html = to_rich_compatible(html)

                # Module banner (# meta banner:) first; else help config banner
                meta_b = None
                with contextlib.suppress(Exception):
                    origin = getattr(module, "__origin__", "") or ""
                    src_head = ""
                    if origin and not str(origin).startswith("<"):
                        from pathlib import Path as _P
                        pth = _P(str(origin))
                        if pth.is_file():
                            # only first 8KB — enough for # meta banner, not full module
                            with open(pth, "r", encoding="utf-8", errors="ignore") as _bf:
                                src_head = _bf.read(8192)
                    if not src_head:
                        with contextlib.suppress(Exception):
                            src_head = (inspect.getdoc(module) or "")[:4000]
                    if src_head:
                        loader_mod = self.lookup("Loader") or self.lookup("LoaderMod")
                        if loader_mod and hasattr(loader_mod, "_get_banner_url"):
                            meta_b = loader_mod._get_banner_url(src_head)
                        if not meta_b:
                            import re as _re
                            _m = _re.search(r"#\s*meta\s+banner:\s*(\S+)", src_head, _re.I)
                            if _m:
                                meta_b = _m.group(1).strip()
                burl = meta_b or pick_banner_url(self.config.get("banner_url"))
                if burl:
                    html = inject_banner_html(html, burl, force=True)

                _mod_key = module.strings.get("name", module.__class__.__name__)
                # from_list: explicit flag from hmod callback (not type-guess)
                _from_list = bool(from_list) or bool(getattr(self, "_help_nav_from_list", False))
                _row = []
                if _from_list:
                    _row.append({
                        "text": "◀️ Назад",
                        "callback": self.inline__help_show_list,
                        "_callback_data": "hhelp|list",
                    })
                # Config only when module actually has configurable options
                _has_cfg = False
                with contextlib.suppress(Exception):
                    _mc = getattr(module, "config", None)
                    if _mc is not None:
                        try:
                            _has_cfg = len(list(_mc)) > 0
                        except Exception:
                            _has_cfg = bool(_mc)
                if _has_cfg:
                    _row.append({
                        "text": "⚙️ Config",
                        "callback": self.inline__help_open_cfg,
                        "args": (_mod_key,),
                        "_callback_data": ("hcfgmod|" + str(_mod_key))[:64],
                    })
                _row.append({
                    "text": "🔻 Закрыть",
                    "action": "close",
                    "_callback_data": "hhelp|close",
                })
                close_mk = [_row]
                # Rich shows tg-buttons in HTML; classic also gets reply_markup
                with contextlib.suppress(Exception):
                    from ..utils.rich_api import markup_to_tg_rows
                    _tb = markup_to_tg_rows(close_mk, "") or ""
                    if _tb:
                        html = f"{html}\n{_tb}"

                if getattr(self.inline, "init_complete", False):
                    try:
                        m = await self._help_form(
                            str(_name)[:120] or "Help",
                            message,
                            reply_markup=close_mk,
                            rich_html=html,
                            banner_url=locals().get("banner_url"),
                        )
                        if m:
                            return
                    except Exception as e:
                        logger.debug("help form rich failed: %s", e)
                    # fallback rich without form unit
                    with contextlib.suppress(Exception):
                        m = await self.inline.rich(
                            message,
                            html,
                            title=str(_name)[:64],
                            reply_markup=close_mk,
                            silent=True,
                        )
                        if m:
                            return
        except Exception:
            logger.debug("module help rich failed", exc_info=True)

        await utils.answer(
            message,
            f"{reply}<blockquote>{cmds}{inline_cmd}</blockquote>"
            + (
                f"<blockquote>\n{placeholders}</blockquote>"
                if placeholders
                else ""
            )
            + (f"\n\n{self.strings['developer']}".format(self._linkify_dev(str(dev_text))) if (dev_text and not getattr(module, "__origin__", "").startswith("<core")) else "")
            + (f"\n\n{self.strings['not_exact']}" if not exact else "")
            + (
                f"\n{self.strings['core_notice']}"
                if module.__origin__.startswith("<core")
                else ""
            ),
            skip_rich=True,
            **banner_kwargs,
        )

    async def inline__help_show_list(self, call):
        """Back → modules list. Always EDIT current form, never send a new one."""
        with contextlib.suppress(Exception):
            await call.answer()
        self._help_nav_from_list = False
        try:
            await self.help(call)
        except Exception as e:
            logger.exception("inline__help_show_list: %s", e)
            with contextlib.suppress(Exception):
                await call.answer("Back failed", show_alert=True)

    async def inline__help_back_from_cfg(self, call, mod_name: str = ""):
        try:
            # Do NOT treat as list-nav unless we came from list originally
            fl = bool(getattr(self, "_help_nav_from_list", False))
            await self.modhelp(call, mod_name or "", from_list=fl)
        except Exception as e:
            logger.debug("help back from cfg: %s", e)

    async def inline__help_open_cfg(self, call, mod_name: str = ""):
        """Open config for a module (from help). Always edit current form."""
        with contextlib.suppress(Exception):
            await call.answer()
        try:
            cfg = (
                self.lookup("HikkariConfig")
                or self.lookup("HikkariConfigMod")
                or self.lookup("ConfigMod")
                or self.lookup("config")
            )
            if cfg is None:
                for m in list(getattr(self.allmodules, "modules", []) or []):
                    if hasattr(m, "inline__configure"):
                        cfg = m
                        break
            if cfg is None or not hasattr(cfg, "inline__configure"):
                with contextlib.suppress(Exception):
                    await call.answer("Config unavailable", show_alert=True)
                return

            key = (mod_name or "").strip()
            mod = None
            if key:
                mod = self.lookup(key)
                if mod is None:
                    # fuzzy: class name / strings name
                    for m in list(getattr(self.allmodules, "modules", []) or []):
                        names = {
                            m.__class__.__name__,
                            getattr(m, "name", None),
                        }
                        with contextlib.suppress(Exception):
                            names.add(str(m.strings.get("name", "")))
                        names = {str(x) for x in names if x}
                        if key in names or key.lower() in {x.lower() for x in names}:
                            mod = m
                            break
            if mod is None:
                with contextlib.suppress(Exception):
                    await call.answer("Module not found", show_alert=True)
                return
            if not getattr(mod, "config", None):
                with contextlib.suppress(Exception):
                    await call.answer("No config", show_alert=True)
                return

            # Prefer strings name then class name for configure lookup
            key = mod.__class__.__name__
            with contextlib.suppress(Exception):
                key = str(mod.strings.get("name", key)) or key

            with contextlib.suppress(Exception):
                cfg._help_return_mod = key
                cfg._help_return_help = self
                cfg._help_from_list = bool(getattr(self, "_help_nav_from_list", False))

            await cfg.inline__configure(call, str(key))
        except Exception as e:
            logger.exception("help open cfg: %s", e)
            with contextlib.suppress(Exception):
                await call.answer(str(e)[:80], show_alert=True)

    @loader.command(
        ru_doc="[args] | Помощь с вашими модулями!",
        ua_doc="[args] | допоможіть з вашими модулями!",
        de_doc="[args] | Hilfe mit deinen Modulen!",
    )
    async def help(self, message: Message):
        """[args] | help with your modules!"""

        # Form callbacks pass InlineCall — body text is NOT command args
        _tn = type(message).__name__
        if _tn in ("InlineCall", "BotInlineCall") or getattr(message, "inline_message_id", None):
            args = ""
        else:
            try:
                args = utils.get_args_raw(message) or ""
            except Exception:
                args = ""
            if args is False:
                args = ""
        _is_form_edit = _tn in ("InlineCall", "BotInlineCall") or bool(
            getattr(message, "inline_message_id", None)
        )

        raw_banner = str(self.config["banner_url"] or "").strip()
        # Reject garbage saved from broken inline input (transfer msg, etc.)
        def _valid_banner(u: str) -> bool:
            if not u:
                return False
            if "Transferring value" in u or "will be deleted automatically" in u:
                return False
            if u.startswith(("http://", "https://")):
                return True
            try:
                from pathlib import Path as _P
                return _P(u).is_file()
            except Exception:
                return False

        if raw_banner and not _valid_banner(raw_banner):
            # Auto-heal corrupted config
            with contextlib.suppress(Exception):
                self.config["banner_url"] = None
            raw_banner = ""

        banner_url_str = raw_banner or None
        banner = None
        if banner_url_str:
            # Local path / file → send as file (supports large video >20MB)
            local_path = None
            try:
                from pathlib import Path as _P
                p = _P(banner_url_str)
                if p.is_file():
                    local_path = str(p)
            except Exception:
                pass
            if local_path:
                banner = local_path
                banner_url_str = local_path
            elif banner_url_str.startswith(("http://", "https://")):
                if self.config["media_quote"] is True or (
                    getattr(self.client, "hikkari_me", None)
                    and self.client.hikkari_me.premium is False
                ):
                    banner = InputMediaWebPage(banner_url_str)
                else:
                    banner = banner_url_str
            else:
                banner = banner_url_str

        force = False
        if "-f" in args:
            args = args.replace(" -f", "").replace("-f", "")
            force = True

        only_core = False
        if "-c" in args:
            args = args.replace(" -c", "").replace("-c", "")
            only_core = True
            force = True

        only_loaded = False
        if "-l" in args:
            args = args.replace(" -l", "").replace("-l", "")
            only_loaded = True
            force = True

        if args:
            await self.modhelp(message, args)
            return

        hidden = self.get("hide", [])
        shown_warn = False

        plain_ = []
        core_ = []
        no_commands_ = []

        # Deduplicate by class name — prevents phantom double modules in help
        seen_cls: set[str] = set()
        mods_iter = []
        for mod in self.allmodules.modules:
            cls = mod.__class__.__name__
            if cls in seen_cls:
                continue
            seen_cls.add(cls)
            mods_iter.append(mod)

        for mod in mods_iter:
            if not hasattr(mod, "commands"):
                logger.debug("Module %s is not inited yet", mod.__class__.__name__)
                continue

            if mod.__class__.__name__ in self.get("hide", []) and not force:
                continue

            tmp = ""

            try:
                name = mod.strings["name"]
            except KeyError:
                name = getattr(mod, "name", "ERROR")

            placeholders = utils.module_placeholders(mod.__class__.__name__)

            if (
                not getattr(mod, "commands", None)
                and not getattr(mod, "inline_handlers", None)
                and not getattr(mod, "callback_handlers", None)
                and not placeholders
            ):
                no_commands_ += [
                    "\n{} <code>{}</code>".format(self.config["empty_emoji"], name)
                ]
                continue

            core = mod.__origin__.startswith("<core")

            emoji = (
                "<tg-emoji emoji-id=5778423822940114949>🛡</tg-emoji>"
                if core
                else "<tg-emoji emoji-id=5931409969613116639>🛡</tg-emoji>"
            )
            tmp += f"\n{emoji} <code>{name}</code>"
            first = True

            commands = [
                name
                for name, func in mod.commands.items()
                if await self.allmodules.check_security(message, func) or force
            ]

            for cmd in commands:
                if first:
                    tmp += f": ( {cmd}"
                    first = False
                else:
                    tmp += f" | {cmd}"

            icommands = []

            if force:
                icommands.extend([*mod.inline_handlers.keys()])
            else:
                results = await asyncio.gather(
                    *(
                        self.inline.check_inline_security(
                            func=func,
                            user=(
                                message.sender_id
                                if not self._is_out(message)
                                else self._client.tg_id
                            ),
                        )
                        for func in mod.inline_handlers.values()
                    )
                )

                icommands = [
                    name
                    for name, passed in zip(mod.inline_handlers.keys(), results)
                    if passed is True
                ]

            for cmd in icommands:
                if first:
                    tmp += f": ( 🤖 {cmd}"
                    first = False
                else:
                    tmp += f" | 🤖 {cmd}"

            for placeholder in placeholders:
                if first:
                    tmp += f": ( {{{placeholder}}}"
                    first = False
                else:
                    tmp += f" | {{{placeholder}}}"

            if commands or icommands or placeholders:
                tmp += " )"
                try:
                    from ..utils.rich_api import tg_button as _tg_btn
                    _hb = _tg_btn(
                        "Help",
                        type="callback_data",
                        data=("hmod|" + str(name))[:64],
                        style="primary",
                    )
                    tmp += " " + _hb
                except Exception:
                    pass
                if core:
                    core_ += [tmp]
                else:
                    plain_ += [tmp]
            elif not shown_warn and (mod.commands or mod.inline_handlers):
                reply = (
                    "<i>You have permissions to execute only these"
                    f" commands</i>\n{reply}"
                )
                shown_warn = True

        plain_.sort(key=str.lower)
        core_.sort(key=str.lower)
        no_commands_.sort(key=str.lower)

        shown_count = len(core_) + len(plain_) + (len(no_commands_) if force else 0)
        hidden_count = 0 if force else sum(
            1 for m in mods_iter if m.__class__.__name__ in hidden
        )
        reply = self.strings["all_header"].format(shown_count, hidden_count)

        # === Heroku 2.2 native Rich help (details sections) ===
        if self.config.get("rich_mode", True):
            try:
                from .. import utils as _u
                from .._internal import normalize_rich_html

                banner_html = ""
                bu = banner_url_str if "banner_url_str" in dir() else None
                try:
                    bu = str(self.config.get("banner_url") or "").strip() or None
                except Exception:
                    bu = None
                if bu and str(bu).startswith(("http://", "https://")):
                    _ext = str(bu).split("?", 1)[0].lower()
                    if _ext.endswith((".mp4", ".webm", ".mov")):
                        banner_html = f'<figure><video src="{bu}"/></figure>'
                    else:
                        banner_html = f'<figure><img src="{bu}"/></figure>'

                icon = self.config.get("desc_icon") or ""
                rich_message = banner_html + f"<p>{icon} {reply}</p>"
                rich_core = "".join(f"<p>{item.strip()}</p>" for item in core_)
                rich_modules = "".join(
                    f"<p>{item.strip()}</p>"
                    for item in plain_ + (no_commands_ if force else [])
                )
                if only_core:
                    sections = [("Встроенные модули", rich_core)]
                elif only_loaded:
                    sections = [("Модули", rich_modules)]
                else:
                    sections = [("Встроенные модули", rich_core), ("Модули", rich_modules)]
                # closed by default (no open attr)
                rich_message += "".join(
                    f"<details>\n<summary>{title}</summary>\n{content}\n</details>"
                    for title, content in sections
                    if content
                )
                loader_mod = self.lookup("Loader") or self.lookup("LoaderMod")
                if loader_mod and not getattr(loader_mod, "fully_loaded", True):
                    rich_message += f"<p>{self.strings.get('partial_load', '')}</p>"
                # via@ form with close when inline ready; native fallback without button
                rich_message = normalize_rich_html(rich_message)
                # Close via classic keyboard only — avoids empty/broken tg-button under list
                close_mk = [[{"text": "🔻 Закрыть", "action": "close"}]]
                sent = False
                if getattr(self.inline, "init_complete", False):
                    with contextlib.suppress(Exception):
                        from ..utils.rich_api import to_rich_compatible
                        html = to_rich_compatible(rich_message)
                        m = await self._help_form(
                            str(reply)[:200] or "Hikkari Help",
                            message,
                            reply_markup=close_mk,
                            rich_html=html,
                        )
                        sent = bool(m)
                    if not sent:
                        # Back/list from existing form: never open a second message
                        if _is_form_edit:
                            with contextlib.suppress(Exception):
                                from ..utils.rich_api import to_rich_compatible
                                html2 = to_rich_compatible(rich_message)
                                if hasattr(message, "edit"):
                                    await message.edit(
                                        text=str(reply)[:200] or "Hikkari Help",
                                        reply_markup=close_mk,
                                    )
                                    sent = True
                            if sent:
                                return
                        with contextlib.suppress(Exception):
                            m = await self.inline.rich(
                                message,
                                rich_message,
                                title="Hikkari Help",
                                description=str(reply)[:80],
                                reply_markup=close_mk,
                                silent=True,
                            )
                            sent = bool(m)
                if not sent:
                    await _u.answer_with_media_fallback(
                        message, rich_message=rich_message
                    )
                return
            except Exception:
                logger.exception("Heroku-style rich help failed, fallback")

        async def _send_help_rich(text_header: str, sections: list[tuple[str, str]]) -> bool:
            """
            One Rich message: Core block + Loaded block (details closed).
            Pagination ONLY if total HTML exceeds Telegram Rich limit (~28k).
            Nav buttons only on multi-page; they edit the same message.
            """
            try:
                from ..utils.rich import can_use_rich
                from ..utils.rich_api import pick_banner_url, inject_banner_html, html_table
                if not can_use_rich(self._client, self._db):
                    logger.info("help rich skipped: rich_mode off or no Premium")
                    return False
                if not getattr(self.inline, "init_complete", False):
                    logger.info("help rich skipped: inline bot not ready")
                    return False

                banner_url = pick_banner_url(self.config.get("banner_url"))
                RICH_LIMIT = 28000  # under Bot API rich max 32768

                def _rows_from_joined(joined: str) -> list[tuple[str, str]]:
                    rows: list[tuple[str, str]] = []
                    if not joined or not str(joined).strip():
                        return rows
                    for raw in str(joined).split("\n"):
                        raw = raw.strip()
                        if not raw:
                            continue
                        m = re.search(r"<code>([^<]+)</code>", raw)
                        name = m.group(1) if m else re.sub(r"<[^>]+>", "", raw)[:48]
                        cmds = "—"
                        if ":" in raw:
                            after = raw.split(":", 1)[1]
                            after = re.sub(r"<[^>]+>", "", after).strip().strip(" ()")
                            if after:
                                cmds = after
                        rows.append((name, cmds))
                    return rows

                def _details_block(title: str, rows: list[tuple[str, str]]) -> str:
                    if not rows:
                        return ""
                    body = "\n".join(f"{name} {cmds}" for name, cmds in rows)
                    return (
                        f"<details>"
                        f"<summary>{title}</summary>"
                        f"{body}"
                        f"</details>"
                    )

                # Keep section order: typically Core then Loaded
                section_rows: list[tuple[str, list[tuple[str, str]]]] = []
                for sec_title, joined in sections:
                    rows = _rows_from_joined(joined)
                    if rows:
                        section_rows.append((sec_title, rows))
                if not section_rows:
                    return False

                total_mods = sum(len(r) for _, r in section_rows)

                def _build_html(
                    chunks: list[tuple[str, list[tuple[str, str]]]],
                    *,
                    page: int | None = None,
                    pages_total: int | None = None,
                    with_banner: bool = True,
                ) -> str:
                    parts: list[str] = []
                    if with_banner and banner_url:
                        parts.append(f'<figure><img src="{banner_url}"/></figure>')
                    head = f"<h2>{text_header}</h2>"
                    # Header already has module count — only show page when multi-page
                    if pages_total and pages_total > 1 and page is not None:
                        head += f"<p><i>{page + 1}/{pages_total}</i></p>"
                    parts.append(head)
                    for title, rows in chunks:
                        blk = _details_block(title, rows)
                        if blk:
                            parts.append(blk)
                    return "\n".join(parts)

                full_html = _build_html(section_rows, with_banner=True)

                # Under limit → ONE message, no nav buttons at all
                if len(full_html) <= RICH_LIMIT:
                    m = await self.inline.rich(
                        message,
                        full_html,
                        title="Hikkari Help",
                        description=text_header[:80],
                        thumbnail_url=banner_url,
                        reply_markup=[[{"text": "Закрыть", "action": "close", "_callback_data": "hhelp|close"}]],
                        silent=True,
                        pages=None,
                    )
                    return bool(m)


                # Over limit → split into pages that each stay under RICH_LIMIT
                flat: list[tuple[str, str, str]] = []
                for title, rows in section_rows:
                    for name, cmds in rows:
                        flat.append((title, name, cmds))

                pages: list[str] = []
                idx = 0
                n = len(flat)
                while idx < n:
                    lo, hi = 1, n - idx
                    best = 1
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        by: dict[str, list] = {}
                        for title, name, cmds in flat[idx : idx + mid]:
                            by.setdefault(title, []).append((name, cmds))
                        trial = _build_html(
                            list(by.items()),
                            page=len(pages),
                            pages_total=99,
                            with_banner=(len(pages) == 0),
                        )
                        if len(trial) <= RICH_LIMIT:
                            best = mid
                            lo = mid + 1
                        else:
                            hi = mid - 1
                    by = {}
                    for title, name, cmds in flat[idx : idx + best]:
                        by.setdefault(title, []).append((name, cmds))
                    pages.append(
                        _build_html(
                            list(by.items()),
                            page=len(pages),
                            pages_total=99,
                            with_banner=(len(pages) == 0),
                        )
                    )
                    idx += best

                real_total = max(1, len(pages))
                if real_total > 1:
                    pages = [
                        re.sub(r"\d+/99", f"{pi + 1}/{real_total}", html, count=1)
                        for pi, html in enumerate(pages)
                    ]

                # Always put config banner into first page (random local/http works)
                if banner_url:
                    pages[0] = inject_banner_html(pages[0], banner_url, force=True)
                    if real_total > 1:
                        pages = list(pages)
                        pages[0] = inject_banner_html(pages[0], banner_url, force=True)
                m = await self.inline.rich(
                    message,
                    pages[0],
                    title="Hikkari Help",
                    description=text_header[:80],
                    thumbnail_url=banner_url,
                    silent=True,
                    pages=pages if real_total > 1 else None,
                    page=0,
                )
                # Large video banner can break Rich → retry without media
                if not m and banner_url:
                    plain_html = pages[0]
                    if plain_html.lower().startswith("<figure"):
                        import re as _re
                        plain_html = _re.sub(
                            r"<figure\b[^>]*>.*?</figure>\s*",
                            "",
                            plain_html,
                            count=1,
                            flags=_re.I | _re.S,
                        )
                    m = await self.inline.rich(
                        message,
                        plain_html,
                        title="Hikkari Help",
                        description=text_header[:80],
                        thumbnail_url=None,
                        reply_markup=[[{"text": "Закрыть", "action": "close", "_callback_data": "hhelp|close"}]],
                        silent=True,
                        pages=None,
                        page=0,
                    )
                return bool(m)
            except Exception:
                logger.debug("help rich failed", exc_info=True)
                return False


        async def _send_help_pages(text_header: str, sections: list[tuple[str, list[str]]]) -> bool:
            """
            Rich (if on) or classic message.
            Inline pagination ONLY when classic text would exceed Telegram ~4096 limit.
            """
            try:
                entries = []
                for sec, lines in sections:
                    for ln in lines:
                        if ln.strip():
                            entries.append((sec, ln.strip()))
                if not entries:
                    return False

                # Prefer Rich when enabled (own limit ~28k; nav only if multi-page inside rich)
                if await _send_help_rich(
                    text_header,
                    [(s, "\n".join(ls)) for s, ls in sections],
                ):
                    return True

                # Build full classic body (same structure as utils.answer fallback)
                bodies = []
                for sec, lines in sections:
                    joined = "".join(lines)
                    if joined.strip():
                        bodies.append(joined)
                # Approximate plain length (strip tags for limit check)
                raw_html = text_header + "\n" + "\n".join(bodies)
                plain_approx = re.sub(r"<[^>]+>", "", raw_html)
                TG_LIMIT = 4000  # leave margin under 4096

                # Under limit → let caller send normal message (no inline, no fake pages)
                if len(plain_approx) <= TG_LIMIT:
                    return False

                # Over limit → paginated inline form
                per_page = 12
                total_pages = max(1, (len(entries) + per_page - 1) // per_page)

                def page_text(page: int) -> str:
                    page = max(0, min(page, total_pages - 1))
                    chunk = entries[page * per_page : (page + 1) * per_page]
                    body = "\n".join(ln for _, ln in chunk)
                    return (
                        f"{text_header}\n"
                        f"<i>{page + 1}/{total_pages}</i>\n"
                        f"<blockquote>{body}</blockquote>"
                    )

                async def goto(call, page: int):
                    page = max(0, min(page, total_pages - 1))
                    btns = []
                    nav = []
                    if page > 0:
                        nav.append({"text": "◀️", "callback": goto, "args": (page - 1,)})
                    nav.append({"text": f"{page + 1}/{total_pages}", "data": "noop"})
                    if page < total_pages - 1:
                        nav.append({"text": "▶️", "callback": goto, "args": (page + 1,)})
                    btns.append(nav)
                    btns.append([{"text": "🔻 Close", "action": "close"}])
                    await call.edit(page_text(page), reply_markup=btns)

                if not getattr(self.inline, "init_complete", False):
                    return False

                first_btns = []
                nav = [{"text": f"1/{total_pages}", "data": "noop"}]
                if total_pages > 1:
                    nav.append({"text": "▶️", "callback": goto, "args": (1,)})
                first_btns.append(nav)
                first_btns.append([{"text": "🔻 Close", "action": "close"}])
                await self.inline.form(
                    page_text(0),
                    message=message if self._is_out(message) else utils.get_chat_id(message),
                    reply_markup=first_btns,
                    silent=True,
                )
                return True
            except Exception:
                logger.debug("help pages failed", exc_info=True)
                return False



        match True:
            case _ if only_core:
                if await _send_help_pages(reply, [("Core", core_)]):
                    return
                await utils.answer(
                    message,
                    (
                        "<tg-emoji emoji-id=5438496463044752972>⭐️</tg-emoji>"
                        + " {}\n <blockquote>{}</blockquote><blockquote>{}</blockquote>"
                    ).format(
                        reply,
                        "".join(core_),
                        (
                            ""
                            if self.lookup("LoaderMod").fully_loaded
                            else f"\n\n{self.strings['partial_load']}"
                        ),
                    ),
                    file=banner,
                    invert_media=self.config["invert_media"],
                    photo=banner_url_str,
                    skip_rich=True,
                )
            case _ if only_loaded:
                if await _send_help_pages(reply, [("Loaded", plain_ + (no_commands_ if force else []))]):
                    return
                await utils.answer(
                    message,
                    (
                        "<tg-emoji emoji-id=5438496463044752972>⭐️</tg-emoji>"
                        + " {}\n <blockquote>{}</blockquote><blockquote>{}</blockquote>"
                    ).format(
                        reply,
                        "".join(plain_ + (no_commands_ if force else [])),
                        (
                            ""
                            if self.lookup("LoaderMod").fully_loaded
                            else f"\n\n{self.strings['partial_load']}"
                        ),
                    ),
                    file=banner,
                    invert_media=self.config["invert_media"],
                    photo=banner_url_str,
                    skip_rich=True,
                )
            case _:
                if await _send_help_pages(reply, [("Core", core_), ("Loaded", plain_ + (no_commands_ if force else []))]):
                    return
                await utils.answer(
                    message,
                    (
                        "<tg-emoji emoji-id=5438496463044752972>⭐️</tg-emoji>"
                        + " {}\n <blockquote>{}</blockquote><blockquote>{}</blockquote><blockquote>{}</blockquote>"
                    ).format(
                        reply,
                        "".join(core_),
                        "".join(plain_ + (no_commands_ if force else [])),
                        (
                            ""
                            if self.lookup("LoaderMod").fully_loaded
                            else f"\n\n{self.strings['partial_load']}"
                        ),
                    ),
                    file=banner,
                    invert_media=self.config["invert_media"],
                    photo=banner_url_str,
                    skip_rich=True,
                )

    @loader.command(
        ru_doc="| Ссылка на чат помощи",
        ua_doc="| посилання для чату служби підтримки",
        de_doc="| Link zum Support-Chat",
    )
    async def support(self, message):
        """| link for support chat"""

        await utils.answer(
            message,
            self.strings["offchats"],
        )
