import re
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
import re
import hikkaritl

from hikkaritl.errors import WebpageMediaEmptyError
from hikkaritl.types import InputMediaWebPage
from hikkaritl.tl.types import Message
from hikkaritl.utils import get_display_name
from .. import loader, utils
from ..utils.placeholders import apply_placeholders
from .. import version
import platform as lib_platform
import getpass


logger = logging.getLogger(__name__)


def _format_info_template(template: str, data: dict) -> str:
    """Fill {placeholders}; ignore empty {} and unknown keys (Heroku-safe)."""
    if not template:
        return ""
    text = str(template).replace("{}", "")
    # Normalize double-braces leftovers
    safe = {str(k): str(v) for k, v in (data or {}).items()}

    def repl(m):
        key = m.group(1)
        return safe.get(key, "")

    text = re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", repl, text)
    return text.strip()



@loader.tds
class HikkariInfoMod(loader.Module):
    """Show userbot info"""

    strings = {"name": "HikkariInfo"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "rich_mode",
                False,
                lambda: "Show .info as Rich message (Premium) — off by default (classic Heroku-style)",
                validator=loader.validators.Boolean(),
            ),

            loader.ConfigValue(
                "custom_message",
                doc=lambda: self.strings["_cfg_cst_msg"]
                + "\nPlaceholders: {ping}, {uptime}, {version}, {build}, {owner}, …",
                validator=loader.validators.String(max_len=32000),
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
            "cpu": f"{psutil.cpu_count(logical=False)} ({psutil.cpu_count()}) core(-s); {psutil.cpu_percent(interval=0)}% total",
            "ping": round((time.perf_counter_ns() - start) / 10**6, 3),
            "htl_ver": hikkaritl.__version__,
            "git_status": utils.get_git_status(),
        }
        data = await utils.get_placeholders(data, self.config["custom_message"])
        if self.config["custom_message"]:
            try:
                return apply_placeholders(self.config["custom_message"], data)
            except KeyError:
                logger.exception("Missing placeholder in custom_message")
                return (
                    "<tg-emoji emoji-id=5210952531676504517>🚫</tg-emoji>"
                )
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



    async def _info_placeholders(self, start: float) -> dict:
        """All placeholders for custom_message (classic + Rich)."""
        try:
            up_to_date = utils.is_up_to_date()
            upd = (
                self.strings["up-to-date"]
                if up_to_date
                else self.strings["update_required"].format(prefix=self.get_prefix())
            )
        except Exception:
            upd = "—"
        upd = re.sub(r"<[^>]+>", "", str(upd)).strip() or "—"
        me_name = utils.escape_html(get_display_name(self._client.hikkari_me))
        me = f'<a href="tg://user?id={self._client.hikkari_me.id}">{me_name}</a>'
        build = utils.get_commit_url() if hasattr(utils, "get_commit_url") else "—"
        build_plain = re.sub(r"<[^>]+>", "", str(build))[:48] or "—"
        _version = ".".join(map(str, list(version.__version__)))
        prefix = utils.escape_html(self.get_prefix())
        data = {
            "ping": round((time.perf_counter_ns() - start) / 10**6, 3),
            "uptime": utils.formatted_uptime(),
            "version": _version,
            "build": build,
            "build_plain": build_plain,
            "owner": me,
            "me": me,
            "me_plain": me_name,
            "prefix": prefix,
            "platform": (
                utils.get_named_platform()
                if hasattr(utils, "get_named_platform")
                else utils.get_platform_name()
            ),
            "upd": upd,
            "cpu_usage": utils.get_cpu_usage(),
            "ram_usage": f"{utils.get_ram_usage()} MB",
            "branch": getattr(version, "branch", "master"),
            "hostname": lib_platform.node(),
            "user": getpass.getuser(),
            "os": self._get_os_name() or self.strings.get("non_detectable", "—"),
            "kernel": lib_platform.release(),
            "cpu": f"{psutil.cpu_count(logical=False)} ({psutil.cpu_count()}) cores",
            "python_ver": lib_platform.python_version(),
            "htl_ver": getattr(hikkaritl, "__version__", "?"),
            "git_status": (
                utils.get_git_status() if hasattr(utils, "get_git_status") else ""
            ),
            "time": __import__("datetime").datetime.now().strftime("%H:%M:%S"),
            "date": __import__("datetime").datetime.now().strftime("%d.%m.%Y"),
            "fortune": "",
        }
        try:
            data = await utils.get_placeholders(
                data, self.config.get("custom_message") or ""
            )
        except Exception:
            pass
        # Ensure every {token} in custom_message has a key (empty if unknown)
        try:
            import re as _re
            custom = str(self.config.get("custom_message") or "")
            for tok in _re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", custom):
                data.setdefault(tok, "")
        except Exception:
            pass
        return data

    def _bot_ready_for_rich(self) -> bool:
        try:
            inline = getattr(self, "inline", None)
            if not inline or not getattr(inline, "init_complete", False):
                return False
            if getattr(inline, "bot", None) is None:
                return False
            return True
        except Exception:
            return False

    async def infocmd(self, message: Message):
        """Show userbot info. Classic by default; Rich only if rich_mode is on."""
        start = time.perf_counter_ns()
        data = await self._info_placeholders(start)

        class _Safe(dict):
            def __missing__(self, key):
                return ""

        safe = _Safe({k: str(v) for k, v in data.items()})

        # --- Rich path (explicit opt-in only) ---
        if self.config.get("rich_mode", False):
            try:
                from .._internal import normalize_rich_html
                from ..utils.rich import can_use_rich

                if can_use_rich(self._client, getattr(self, "_db", None)):
                    tmpl = None
                    for key in ("rich_info_message", "info_message"):
                        with contextlib.suppress(Exception):
                            raw = self.strings.get(key)
                            if raw and not str(raw).startswith("Unknown strings"):
                                tmpl = raw
                                break
                    custom = self.config.get("custom_message")
                    if custom and str(custom).strip() and any(
                        x in str(custom) for x in ("<details", "<table", "<figure")
                    ):
                        html = str(custom)
                    elif tmpl:
                        html = str(tmpl)
                    else:
                        html = (
                            "<p><b>Owner</b>: {me}</p>"
                            "<p><b>Version</b>: {version}</p>"
                            "<p><b>Prefix</b>: {prefix}</p>"
                            "<p><b>Uptime</b>: {uptime}</p>"
                            "<p><b>Ping</b>: {ping}</p>"
                        )
                    html = _format_info_template(html, data)
                    banner = self.config.get("banner_url")
                    if isinstance(banner, list) and banner:
                        import random as _r
                        banner = _r.choice(banner)
                    banner = str(banner or "").strip()
                    if banner.startswith("local:"):
                        banner = (
                            "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/"
                            + banner[6:].lstrip("/")
                        )
                    if not banner.startswith(("http://", "https://")):
                        banner = "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-info.jpg"
                    if "<figure" not in html.lower() and not banner.lower().endswith(
                        (".mp4", ".webm", ".gif", ".mov")
                    ):
                        html = f'<figure><img src="{banner}"/></figure>' + html
                    html = normalize_rich_html(html)
                    await utils.answer_with_media_fallback(message, rich_message=html)
                    return
            except Exception:
                logger.exception("rich info failed, classic fallback")

        # --- Classic single message (Heroku-style default) ---
        tmpl = None
        with contextlib.suppress(Exception):
            raw = self.strings.get("info_message")
            if raw and not str(raw).startswith("Unknown strings"):
                tmpl = raw
        custom = self.config.get("custom_message")
        if custom and str(custom).strip() and not any(
            x in str(custom) for x in ("<details", "<table", "<figure")
        ):
            text = str(custom)
        elif tmpl:
            text = str(tmpl)
        else:
            text = (
                "<b>Owner</b>: {me}\n"
                "<b>Version</b>: {version}\n"
                "<b>Prefix</b>: {prefix}\n"
                "<b>Uptime</b>: {uptime}\n"
                "<b>Branch</b>: {branch}\n"
                "<b>CPU</b>: {cpu_usage}\n"
                "<b>RAM</b>: {ram_usage}\n"
                "<b>Ping</b>: {ping}\n"
                "<b>Update</b>: {upd}\n"
                "<b>Host</b>: {platform}\n"
                "<b>OS</b>: {os}\n"
                "<b>Python</b>: {python_ver}"
            )
        text = _format_info_template(text, data)

        banner = self.config.get("banner_url")
        media = utils.resolve_banner_media(banner) if banner else None
        # resolve_banner_media returns path / URL / InputMediaWebPage — not a dict
        if media is None:
            await utils.answer(message, text)
        elif isinstance(media, str) and media.startswith("audio_ref:"):
            await utils.answer(message, text)
        else:
            await utils.answer(message, text, file=media)


    async def ubinfo(self, message: Message):
        await utils.answer(message, self.strings["desc"])
