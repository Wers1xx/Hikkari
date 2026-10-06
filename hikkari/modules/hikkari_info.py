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

import time
import re
import psutil
import logging
import hikkaritl

from hikkaritl.errors import WebpageMediaEmptyError
from hikkaritl.types import InputMediaWebPage
from hikkaritl.tl.types import Message
from hikkaritl.utils import get_display_name
from .. import loader, utils, version
import platform as lib_platform
import getpass

logger = logging.getLogger(__name__)


@loader.tds
class HikkariInfoMod(loader.Module):
    """Show userbot info"""

    strings = {"name": "HikkariInfo"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "custom_message",
                doc=lambda: self.strings["_cfg_cst_msg"]
                + "\nPlaceholders: {ping}, {uptime}, {version}, {build}, {owner}, …",
                validator=loader.validators.String(max_len=4096),
            ),
            loader.ConfigValue(
                "rich_buttons",
                "Support|https://t.me/Hikkari_talks, Channel|https://t.me/Hikkari_Channel",
                lambda: "Rich URL buttons: Text|url, Text2|url2",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "banner_url",
                [
                    "local:hikkari-info.jpg",
                    "local:hikkari-started.jpg",
                ],
                lambda: self.strings.get("_cfg_banner", self.strings.get("banner_url", "Banner URL(s)")),
                validator=loader.validators.RandomLink(),
            ),
            loader.ConfigValue(
                "ping_emoji",
                "<emoji document_id=5283176512747507510>✨</emoji>",
                lambda: self.strings["ping_emoji"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "quote_media",
                True,
                "Switch preview media to quote",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "invert_media",
                True,
                "Switch preview invert media",
                validator=loader.validators.Boolean(),
            ),
        )

    def _get_os_name(self):
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME"):
                        return line.split("=")[1].strip().strip('"')
        except FileNotFoundError:
            return self.strings["non_detectable"]

    async def _render_info(self, start: float) -> str:
        try:
            up_to_date = utils.is_up_to_date()
            if up_to_date:
                upd = self.strings["up-to-date"]
            else:
                upd = self.strings["update_required"].format(prefix=self.get_prefix())
        except Exception:
            upd = ""

        me = (
            '<b><a href="tg://user?id={}">{}</a></b>'.format(
                self._client.hikkari_me.id,
                utils.escape_html(get_display_name(self._client.hikkari_me)),
            )
            .replace("{", "")
            .replace("}", "")
        )
        build = utils.get_commit_url()
        _version = f'<i>{".".join(list(map(str, list(version.__version__))))}</i>'
        prefix = f"«<code>{utils.escape_html(self.get_prefix())}</code>»"

        platform = utils.get_named_platform()
        platform_emoji = utils.get_named_platform_emoji()

        for emoji, icon in [
            ("🍊", '<tg-emoji emoji-id="5449599833973203438">🧡</tg-emoji>'),
            ("🍇", '<tg-emoji emoji-id="5449468596952507859">💜</tg-emoji>'),
            ("😶‍🌫️", '<tg-emoji emoji-id="5370547013815376328">😶‍🌫️</tg-emoji>'),
            ("❓", '<tg-emoji emoji-id="5407025283456835913">📱</tg-emoji>'),
            ("🍀", '<tg-emoji emoji-id="5395325195542078574">🍀</tg-emoji>'),
            ("🦾", '<tg-emoji emoji-id="5386766919154016047">🦾</tg-emoji>'),
            ("🚂", '<tg-emoji emoji-id="5359595190807962128">🚂</tg-emoji>'),
            ("🐳", '<tg-emoji emoji-id="5431815452437257407">🐳</tg-emoji>'),
            ("🕶", '<tg-emoji emoji-id="5407025283456835913">📱</tg-emoji>'),
            ("🐈‍⬛", '<tg-emoji emoji-id="6334750507294262724">🐈‍⬛</tg-emoji>'),
            ("✌️", '<tg-emoji emoji-id="5469986291380657759">✌️</tg-emoji>'),
            ("💎", '<tg-emoji emoji-id="5471952986970267163">💎</tg-emoji>'),
            ("🛡", '<tg-emoji emoji-id="5282731554135615450">🌩</tg-emoji>'),
            ("🌼", '<tg-emoji emoji-id="5224219153077914783">❤️</tg-emoji>'),
            ("🎡", '<tg-emoji emoji-id="5226711870492126219">🎡</tg-emoji>'),
            ("🐧", '<tg-emoji emoji-id="5361541227604878624">🐧</tg-emoji>'),
            ("🧃", '<tg-emoji emoji-id="5422884965593397853">🧃</tg-emoji>'),
            ("🦅", '<tg-emoji emoji-id="5427286516797831670">🦅</tg-emoji>'),
            ("💻", '<tg-emoji emoji-id="5469825590884310445">💻</tg-emoji>'),
            ("🍏", '<tg-emoji emoji-id="5372908412604525258">🍏</tg-emoji>'),
        ]:
            platform_emoji = platform_emoji.replace(emoji, icon)
        data = {
            "me": me,
            "version": _version,
            "build": build,
            "prefix": prefix,
            "platform": platform,
            "platform_emoji": platform_emoji,
            "upd": upd,
            "python_ver": lib_platform.python_version(),
            "uptime": utils.formatted_uptime(),
            "cpu_usage": utils.get_cpu_usage(),
            "ram_usage": f"{utils.get_ram_usage()} MB",
            "branch": version.branch,
            "hostname": lib_platform.node(),
            "user": getpass.getuser(),
            "os": self._get_os_name() or self.strings["non_detectable"],
            "kernel": lib_platform.release(),
            "cpu": f"{psutil.cpu_count(logical=False)} ({psutil.cpu_count()}) core(-s); {psutil.cpu_percent()}% total",
            "ping": round((time.perf_counter_ns() - start) / 10**6, 3),
            "htl_ver": hikkaritl.__version__,
            "git_status": utils.get_git_status(),
        }
        data = await utils.get_placeholders(data, self.config["custom_message"])
        if self.config["custom_message"]:
            try:
                return self.config["custom_message"].format(**data)
            except KeyError:
                logger.exception("Missing placeholder in custom_message")
                return (
                    "<tg-emoji emoji-id=5210952531676504517>🚫</tg-emoji>"
                )

        # Rich mode: Heroku-style tree cards (works in normal messages).
        # Real <table> Rich Messages only via Bot API sendRichMessage in infocmd.
        try:
            from ..utils.rich import is_rich_enabled
            if is_rich_enabled(getattr(self, "_db", None)):
                star = '<tg-emoji emoji-id="5283176512747507510">✨</tg-emoji>'
                ver = data.get("version", "—")
                bld = data.get("build", "—")
                return (
                    f"{star} <b>Hikkari Userbot</b>\n"
                    f"<blockquote>┌\n"
                    f"├  【{star}】 <b>Owner</b>: {data.get('me', '—')}\n"
                    f"├  【{star}】 <b>Version</b>: {ver}\n"
                    f"└</blockquote>\n"
                    f"<blockquote>┌\n"
                    f"├  【{star}】 <b>Prefix</b>: {data.get('prefix', '—')}\n"
                    f"├  【{star}】 <b>Uptime</b>: {data.get('uptime', '—')}\n"
                    f"├  【{star}】 <b>Branch</b>: {data.get('branch', '—')}\n"
                    f"└</blockquote>\n"
                    f"<blockquote>┌\n"
                    f"├  【{star}】 <b>CPU</b>: {data.get('cpu_usage', '—')}\n"
                    f"├  【{star}】 <b>RAM</b>: {data.get('ram_usage', '—')}\n"
                    f"├  【{star}】 <b>Ping</b>: {data.get('ping', '—')} ms\n"
                    f"└</blockquote>\n"
                    f"<blockquote>┌\n"
                    f"├  【{star}】 <b>Update</b>: {data.get('upd', '—')}\n"
                    f"├  【{star}】 <b>Host</b>: {data.get('platform', '—')}\n"
                    f"├  【{star}】 <b>OS</b>: {data.get('os', '—')}\n"
                    f"├  【{star}】 <b>Python</b>: {data.get('python_ver', '—')}\n"
                    f"├  【{star}】 <b>Build</b>: {bld}\n"
                    f"├  【{star}】 <b>Hikkari TL</b>: {data.get('htl_ver', '—')}\n"
                    f"├  【{star}】 <b>Developers</b>: "
                    f'<a href="https://t.me/Wers1xx">@Wers1xx</a>\n'
                    f"└</blockquote>\n"
                    f"{star} <b>You are a happy owner of Hikkari!</b>"
                )
        except Exception:
            logger.debug("rich info tree fallback", exc_info=True)

        return self.strings["info_message"].format(
                (
                    utils.get_platform_emoji()
                    if self._client.hikkari_me.premium
                    else "✨ Hikkari"
                ),
                me=me,
                version=_version,
                prefix=prefix,
                uptime=utils.formatted_uptime(),
                branch=version.branch,
                cpu_usage=utils.get_cpu_usage(),
                ram_usage=f"{utils.get_ram_usage()} MB",
                ping=round((time.perf_counter_ns() - start) / 10**6, 3),
                upd=upd,
                platform=platform,
                os=self._get_os_name() or self.strings["non_detectable"],
                python_ver=lib_platform.python_version(),
            )


    @loader.command()
    async def infocmd(self, message: Message):
        """Show userbot info (Heroku-compatible quote_media)"""
        start = time.perf_counter_ns()
        from .. import main as _main

        banner = self.config["banner_url"]
        media = utils.resolve_banner_media(banner)
        # Rich mode → prefer quote/invert like Heroku info card

        # Rich via @bot (Premium + rich_mode)
        try:
            from ..utils.rich import can_use_rich
            from ..utils.rich_api import build_info_html, pick_banner_url
            if can_use_rich(self._client, getattr(self, "_db", None)) and getattr(
                self, "inline", None
            ):
                banner_url = pick_banner_url(self.config.get("banner_url"))
                custom = self.config.get("custom_message")
                if custom:
                    # User-authored Rich HTML (custom_message) + placeholders
                    data = await self._info_placeholders(start)
                    try:
                        html = str(custom).format(**data)
                    except Exception:
                        logger.exception("custom_message format failed")
                        html = str(custom)
                    if banner_url and "<figure" not in html.lower():
                        html = (
                            f'<figure><img src="{banner_url}"/></figure>\n'
                            + html
                        )
                else:
                    rows = [
                        ("Owner", utils.escape_html(get_display_name(self._client.hikkari_me))),
                        ("Version", ".".join(map(str, version.__version__))),
                        ("Build", str(utils.get_commit_url()) if hasattr(utils, "get_commit_url") else "—"),
                        ("Hikkari TL", str(getattr(hikkaritl, "__version__", "?"))),
                        ("Prefix", utils.escape_html(self.get_prefix())),
                        ("Uptime", utils.formatted_uptime()),
                        ("Ping", f"{round((time.perf_counter_ns() - start) / 10**6, 3)} ms"),
                        ("Platform", str(utils.get_named_platform()) if hasattr(utils, "get_named_platform") else "—"),
                        ("Python", lib_platform.python_version()),
                        ("Developers", "@Wers1xx"),
                    ]
                    html = build_info_html(
                        title="Hikkari Userbot",
                        rows=rows,
                        footer="You are a happy owner of Hikkari!",
                        banner_url=banner_url,
                    )
                from ..utils.rich_api import parse_rich_url_buttons, to_rich_compatible
                html = to_rich_compatible(html)
                # Official Rich buttons (Bot API 10.3) inside message body
                btn_html = parse_rich_url_buttons(
                    str(self.config.get("rich_buttons") or "")
                )
                if btn_html:
                    html = html + "\n" + btn_html
                m = await self.inline.rich(
                    message,
                    html,
                    title="Hikkari Info",
                    description="Rich info",
                    thumbnail_url=banner_url,
                )
                if m:
                    return
                try:
                    from ..utils.rich_api import try_send_rich
                    chat = utils.get_chat_id(message)
                    if await try_send_rich(self._client, chat, html):
                        with contextlib.suppress(Exception):
                            if getattr(message, "out", False):
                                await message.delete()
                        return
                except Exception:
                    logger.debug("info sendRichMessage fallback failed", exc_info=True)
                logger.warning("inline.rich failed → classic tree")
        except Exception:
            logger.warning("rich via inline failed", exc_info=True)

        try:
            match True:
                case _ if self.config["custom_message"] is None:
                    await utils.answer(
                        message,
                        await self._render_info(start),
                        file=media,
                        reply_to=getattr(message, "reply_to_msg_id", None),
                        invert_media=self.config["invert_media"],
                    )
                case _:
                    if "{ping}" in (self.config["custom_message"] or ""):
                        message = await utils.answer(message, self.config["ping_emoji"])
                    await utils.answer(
                        message,
                        await self._render_info(start),
                        file=media,
                        reply_to=getattr(message, "reply_to_msg_id", None),
                        invert_media=self.config["invert_media"],
                    )
        except WebpageMediaEmptyError:
            await utils.answer(
                message,
                self.strings["no_banner"].format(
                    link=self.config["banner_url"],
                ),
                reply_to=getattr(message, "reply_to_msg_id", None),
            )

    @loader.command()
    async def ubinfo(self, message: Message):
        await utils.answer(message, self.strings["desc"])
