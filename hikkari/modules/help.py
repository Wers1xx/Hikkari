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

    strings = {"name": "Help"}

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
        )

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

    def _get_module_developer(self, module) -> str | None:
        """Extract developer only from explicit # meta developer (never from license ©️)."""
        # Built-in / core modules: never show a developer line
        origin = str(getattr(module, "__origin__", "") or "")
        if origin.startswith("<core"):
            return None
        source = getattr(module, "__source__", None) or ""
        if not source:
            with contextlib.suppress(Exception):
                source = inspect.getsource(module.__class__)
        if not source:
            return None
        # Only official module meta — license headers (# ©️ ...) are NOT developers
        m = re.search(r"# ?meta developer: ?(.+)", source, flags=re.I)
        if m:
            dev = m.group(1).strip().strip('"').strip("'")
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
                "\n".join([f"<emoji document_id=5294271804842469571>👁</emoji>‍🗨 <i>{m}</i>" for m in hidden]),
                "\n".join([f"<emoji document_id=5294271804842469571>👁</emoji> <i>{m}</i>" for m in shown]),
            ),
        )

    def find_aliases(self, command: str) -> list:
        """Find aliases for command"""
        aliases = []
        _command = self.allmodules.commands[command]
        if getattr(_command, "alias", None) and not (
            aliases := getattr(_command, "aliases", None)
        ):
            aliases = [_command.alias]

        return aliases or []

    async def modhelp(self, message: Message, args: str):
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
        # Core modules: no Developer at all (license is not author meta)
        is_core = str(getattr(module, "__origin__", "") or "").startswith("<core")
        dev_text = None
        if not is_core:
            developer = re.search(
                r"# ?meta developer: ?(.+)",
                getattr(module, "__source__", None) or "",
            )
            dev_text = developer.group(1).strip() if developer else None
            if not dev_text:
                dev_text = self._get_module_developer(module)
        placeholders = "\n".join(
            utils.help_placeholders(module.__class__.__name__, self)
        )

        banner_kwargs = {}
        if self.config["show_preview_in_help"]:
            try:
                source = getattr(module, "__source__", None)
                if source:
                    banner_url = self._get_banner_url(source)
                    if banner_url:
                        banner_kwargs = {
                            "file": InputMediaWebPage(banner_url, optional=True),
                            "invert_media": True,
                        }
            except Exception:
                pass


        # Prefer meta developer if regex missed (external modules only)
        if not is_core and not dev_text:
            dev_text = self._get_module_developer(module)

        # Rich single-module help (commands in <details>)
        try:
            from ..utils.rich import can_use_rich
            from ..utils.rich_api import html_table, pick_banner_url, inject_banner_html
            import html as html_mod

            if can_use_rich(self._client, self._db) and getattr(
                self.inline, "init_complete", False
            ):
                undoc = self._plain_doc(self.strings.get("undoc"), "—")
                rows = []
                for name, fun in commands.items():
                    doc = self._plain_doc(inspect.getdoc(fun), undoc)[:120]
                    rows.append(
                        (
                            html_mod.escape(
                                f"{self.get_prefix()}{name}"
                            ),
                            html_mod.escape(doc),
                        )
                    )
                if hasattr(module, "inline_handlers"):
                    for name, fun in module.inline_handlers.items():
                        doc = self._plain_doc(inspect.getdoc(fun), undoc)[:120]
                        rows.append(
                            (
                                html_mod.escape(
                                    f"@{self.inline.bot_username} {name}"
                                ),
                                html_mod.escape(doc),
                            )
                        )
                parts = [f"<h2>{html_mod.escape(str(_name))}</h2>"]
                if module.__doc__:
                    mdoc = self._plain_doc(inspect.getdoc(module), "")[:400]
                    if mdoc:
                        parts.append(f"<p><i>{html_mod.escape(mdoc)}</i></p>")
                if rows:
                    table = html_table(rows, header=("Command", "Description"))
                    parts.append(
                        f"<details open><summary><b>Commands</b> ({len(rows)})</summary>\n"
                        f"{table}\n</details>"
                    )
                if placeholders:
                    ph = self._plain_doc(placeholders, "")
                    if ph:
                        parts.append(
                            f"<details><summary>Placeholders</summary>"
                            f"<p>{html_mod.escape(ph)}</p></details>"
                        )
                if dev_text:
                    # plain developer line (no nested broken HTML)
                    parts.append(
                        f"<p><emoji document_id=5994521125298638350>🧑‍🎄</emoji>‍<emoji document_id=5282843764451195532>🖥</emoji> <b>Developer:</b> "
                        f"<code>{html_mod.escape(str(dev_text))}</code></p>"
                    )
                if getattr(module, "__origin__", "").startswith("<core"):
                    core_n = self._plain_doc(
                        self.strings.get("core_notice"),
                        "Built-in module",
                    )
                    parts.append(f"<p><emoji document_id=5778423822940114949>🛡</emoji> {html_mod.escape(core_n)}</p>")

                # Meta banner of THIS module first, then Help config banner
                meta_b = None
                with contextlib.suppress(Exception):
                    meta_b = self._get_banner_url(
                        getattr(module, "__source__", None) or ""
                    )
                burl = meta_b or pick_banner_url(self.config.get("banner_url"))
                html = "\n".join(parts)
                html = inject_banner_html(html, burl, force=True)
                m = await self.inline.rich(
                    message,
                    html,
                    title=str(_name)[:64],
                    description=self._plain_doc(inspect.getdoc(module), "Module help")[
                        :80
                    ],
                    thumbnail_url=burl,
                    silent=True,
                )
                if m:
                    return
        except Exception:
            logger.debug("module help rich failed", exc_info=True)

        await utils.answer(
            message,
            f"{reply}<blockquote expandable>{cmds}{inline_cmd}</blockquote>"
            + (
                f"<blockquote expandable>\n{placeholders}</blockquote>"
                if placeholders
                else ""
            )
            + (f"\n\n{self.strings['developer']}".format(dev_text) if dev_text else "")
            + (f"\n\n{self.strings['not_exact']}" if not exact else "")
            + (
                f"\n{self.strings['core_notice']}"
                if module.__origin__.startswith("<core")
                else ""
            ),
            skip_rich=True,
            **banner_kwargs,
        )

    @loader.command(
        ru_doc="[args] | Помощь с вашими модулями!",
        ua_doc="[args] | допоможіть з вашими модулями!",
        de_doc="[args] | Hilfe mit deinen Modulen!",
    )
    async def help(self, message: Message):
        """[args] | help with your modules!"""

        args = utils.get_args_raw(message)

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
            if self.config["media_quote"] is True or (
                self.client.hikkari_me.premium is False
            ):
                banner = InputMediaWebPage(banner_url_str)
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
        hidden_count = (
            0
            if force
            else sum(
                module.__class__.__name__ in hidden
                for module in self.allmodules.modules
            )
        )
        # Header filled AFTER lists are built so counts match Core+Loaded
        reply = None
        shown_warn = False

        plain_ = []
        core_ = []
        no_commands_ = []

        for mod in self.allmodules.modules:
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

            tmp += "\n{} <code>{}</code>".format(
                ("<tg-emoji emoji-id=5778423822940114949>🛡</tg-emoji>" if core else "<tg-emoji emoji-id=5931409969613116639>🛡</tg-emoji>"), name
            )
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
                                if not message.out
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
                    tmp += f": ( <emoji document_id=5985780596268339498>🤖</emoji> {cmd}"
                    first = False
                else:
                    tmp += f" | <emoji document_id=5985780596268339498>🤖</emoji> {cmd}"

            for placeholder in placeholders:
                if first:
                    tmp += f": ( {{{placeholder}}}"
                    first = False
                else:
                    tmp += f" | {{{placeholder}}}"

            if commands or icommands or placeholders:
                tmp += " )"
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

        # What is actually shown in help (same as sections below)
        shown_loaded = plain_ + (no_commands_ if force else [])
        shown_total = len(core_) + len(shown_loaded)
        reply = self.strings["all_header"].format(shown_total, hidden_count)

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
                    table = html_table(rows, header=("Module", "Commands"))
                    # closed by default (no open attribute)
                    return (
                        f"<details>"
                        f"<summary><b>{title}</b> ({len(rows)})</summary>\n"
                        f"{table}\n"
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
                    if pages_total and pages_total > 1 and page is not None:
                        head += (
                            f"<p><i>{page + 1}/{pages_total} · {total_mods} modules</i></p>"
                        )
                    else:
                        head += f"<p><i>{total_mods} modules</i></p>"
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
                return bool(m)
            except Exception:
                logger.debug("help rich failed", exc_info=True)
                return False


        async def _send_help_pages(text_header: str, sections: list[tuple[str, list[str]]]) -> bool:
            """Paginated form for large module lists. sections: (title, list of line html)"""
            try:
                # flatten entries as (section, line)
                entries = []
                for sec, lines in sections:
                    for ln in lines:
                        if ln.strip():
                            entries.append((sec, ln.strip()))
                if not entries:
                    return False
                per_page = 12
                total_pages = max(1, (len(entries) + per_page - 1) // per_page)

                def page_text(page: int) -> str:
                    page = max(0, min(page, total_pages - 1))
                    chunk = entries[page * per_page : (page + 1) * per_page]
                    body = "\n".join(ln for _, ln in chunk)
                    return (
                        f"{text_header}\n"
                        f"<i>стр. {page + 1}/{total_pages}</i>\n"
                        f"<blockquote expandable>{body}</blockquote>"
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
                    btns.append([{"text": "⬇️ Close", "action": "close"}])
                    await call.edit(page_text(page), reply_markup=btns)

                # Always prefer official Rich (tables + <details> + <tg-button-row> nav)
                if await _send_help_rich(
                    text_header,
                    [(s, "\n".join(ls)) for s, ls in sections],
                ):
                    return True

                # Rich unavailable → classic form with nav
                first_btns = []
                nav = [{"text": f"1/{total_pages}", "data": "noop"}]
                if total_pages > 1:
                    nav.append({"text": "▶️", "callback": goto, "args": (1,)})
                first_btns.append(nav)
                first_btns.append([{"text": "⬇️ Close", "action": "close"}])
                await self.inline.form(
                    page_text(0),
                    message=message if message.out else utils.get_chat_id(message),
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
                        + " {}\n <blockquote expandable>{}</blockquote><blockquote expandable>{}</blockquote>"
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
                        + " {}\n <blockquote expandable>{}</blockquote><blockquote expandable>{}</blockquote>"
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
                        + " {}\n <blockquote expandable>{}</blockquote><blockquote expandable>{}</blockquote><blockquote expandable>{}</blockquote>"
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
