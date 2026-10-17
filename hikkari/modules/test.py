from ..utils.placeholders import apply_placeholders
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

import getpass
import inspect
import logging
import contextlib
logger = logging.getLogger(__name__)
import os
import platform as lib_platform
import random
import time
import asyncio
from io import BytesIO

from hikkaritl.tl.types import Message
from hikkaritl.types import InputMediaWebPage

from .. import loader, main, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

DEBUG_MODS_DIR = os.path.join(utils.get_base_dir(), "debug_modules")

if not os.path.isdir(DEBUG_MODS_DIR):
    os.mkdir(DEBUG_MODS_DIR, mode=0o755)

for mod in os.scandir(DEBUG_MODS_DIR):
    os.remove(mod.path)


@loader.tds
class TestMod(loader.Module):
    """Perform operations based on userbot self-testing"""

    strings = {
        "name": "Tester",
    }

    def __init__(self):
        self._memory = {}
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "force_send_all",
                False,
                (
                    "⚠️ Do not touch, if you don't know what it does!\nBy default, "
                    " Hikkari will try to determine, which client caused logs. E.g. there"
                    " is a module TestModule installed on Client1 and TestModule2 on"
                    " Client2. By default, Client2 will get logs from TestModule2, and"
                    " Client1 will get logs from TestModule. If this option is enabled,"
                    " Hikkari will send all logs to Client1 and Client2, even if it is"
                    " not the one that caused the log."
                ),
                validator=loader.validators.Boolean(),
                on_change=self._pass_config_to_logger,
            ),
            loader.ConfigValue(
                "tglog_level",
                "ERROR",
                (
                    "⚠️ Do not touch, if you don't know what it does!\n"
                    "Minimal loglevel for records to be sent in Telegram."
                ),
                validator=loader.validators.Choice(
                    ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "DISABLE"]
                ),
                on_change=self._pass_config_to_logger,
            ),
            loader.ConfigValue(
                "ignore_common",
                True,
                "Ignore common errors (e.g. 'TypeError' in telethon)",
                validator=loader.validators.Boolean(),
                on_change=self._pass_config_to_logger,
            ),
            loader.ConfigValue(
                "disable_internet_warn",
                False,
                "Ignore all internet errors",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "custom_message",
                '<blockquote><emoji document_id=5325547803936572038>✨</emoji> <code>Ping</code>: {ping}</blockquote>\n<blockquote><emoji document_id=5255971360965930740>🕔</emoji> <code>Uptime</code>: {uptime}</blockquote>\n<blockquote><emoji document_id=5341715473882955310>⚙️</emoji> <code>Version</code>: {version} {build}</blockquote>',
                lambda: (
                    self.strings["configping"]
                    + (
                        "\n"
                        + self.strings["configpingph"].format(
                            "\n" + utils.config_placeholders()
                        )
                        if utils.config_placeholders()
                        else ""
                    )
                ),
                validator=loader.validators.String(max_len=32000),
            ),
            loader.ConfigValue(
                "hint",
                None,
                lambda: self.strings["hint"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "ping_emoji",
                "✨",
                lambda: self.strings["ping_emoji"],
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "rich_mode",
                True,
                lambda: "Show .ping as Rich message (Premium)",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "banner_url",
                [
                    "local:hikkari-started.jpg",
                    "local:hikkari-info.jpg",
                ],
                lambda: self.strings["banner_url"],
                validator=loader.validators.RandomLink(),
            ),
            loader.ConfigValue(
                "quote_media",
                False,
                "Switch preview media to quote in ping",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "invert_media",
                False,
                "Switch preview invert media in ping",
                validator=loader.validators.Boolean(),
            ),
        )

    def _pass_config_to_logger(self):
        logging.getLogger().handlers[0].force_send_all = self.config["force_send_all"]
        logging.getLogger().handlers[0].tg_level = {
            "ALL": 0,
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40,
            "CRITICAL": 50,
            "DISABLE": 50000,
        }[self.config["tglog_level"]]
        logging.getLogger().handlers[0].ignore_common = self.config["ignore_common"]

    @loader.command()
    async def clearlogs(self, message: Message):
        for handler in logging.getLogger().handlers:
            handler.buffer = []
            handler.handledbuffer = []
            handler.tg_buff = ""

        await utils.answer(message, self.strings["logs_cleared"])

    @loader.command()
    async def logs(
        self,
        message: Message | InlineCall,
        force: bool = False,
        lvl: int | None = None,
    ):
        raw_args = utils.get_args_raw(message) if isinstance(message, Message) else ""
        args = raw_args.split()
        if "-f" in args or "--force" in args:
            force = True
            args = [arg for arg in args if arg not in {"-f", "--force"}]

        if not isinstance(lvl, int):
            if args:
                try:
                    try:
                        lvl = int(args[0])
                    except ValueError:
                        lvl = getattr(logging, args[0].upper(), None)
                except IndexError:
                    lvl = None
            else:
                lvl = None

        if not isinstance(lvl, int):
            if force:
                await utils.answer(message, self.strings["set_loglevel"])
                return

            try:
                if self.inline.init_complete:
                    await utils.answer(
                        message,
                        self.strings["choose_loglevel"],
                        reply_markup=utils.chunks(
                            [
                                {
                                    "text": name,
                                    "callback": self.logs,
                                    "args": (False, level),
                                    "emoji_id": eid,
                                }
                                for name, level, eid in [
                                    ("Critical", 60, 5240241223632954241),
                                    ("Error", 40, 5240241223632954241),
                                    ("Warning", 30, 5447644880824181073),
                                    ("Info", 20, 5334544901428229844),
                                    ("Debug", 10, 5447644880824181073),
                                    ("All", 0, 5447410659077661506),
                                ]
                            ],
                            2,
                        )
                        + [[{"text": self.strings["cancel"], "action": "close"}]],
                    )
                else:
                    raise
            except Exception as e:
                await utils.answer(message, self.strings["set_loglevel"] + f"\n{e}")

            return

        logs = "\n\n".join(
            [
                "\n".join(
                    handler.dumps(lvl, client_id=self._client.tg_id)
                    if "client_id" in inspect.signature(handler.dumps).parameters
                    else handler.dumps(lvl)
                )
                for handler in logging.getLogger().handlers
            ]
        )

        named_lvl = (
            lvl
            if lvl not in logging._levelToName
            else logging._levelToName[lvl]  # skipcq: PYL-W0212
        )

        if lvl < logging.WARNING and not force:
            try:
                if not self.inline.init_complete:
                    raise

                cfg = {
                    "text": self.strings["confidential"].format(named_lvl),
                    "reply_markup": [
                        {
                            "text": self.strings["send_anyway"],
                            "callback": self.logs,
                            "args": [True, lvl],
                        },
                        {"text": self.strings["cancel"], "action": "close"},
                    ],
                }
                if isinstance(message, Message):
                    if not await self.inline.form(**cfg, message=message):
                        raise
                else:
                    await message.edit(**cfg)
            except Exception:
                await utils.answer(
                    message,
                    self.strings["confidential_text"].format(named_lvl),
                )

            return

        if len(logs) <= 2:
            await utils.answer(
                message,
                self.strings["no_logs"].format(named_lvl),
                **(
                    {}
                    if force
                    else {
                        "reply_markup": {
                            "text": self.strings["back"],
                            "callback": self.logs,
                        },
                    }
                ),
            )
            return

        logs = self.lookup("evaluator").censor(logs)

        logs = BytesIO(logs.encode("utf-8"))
        logs.name = "hikkari-logs.txt"

        ghash = utils.get_git_hash()

        other = (
            *main.__version__,
            (
                " <a"
                f' href="https://github.com/Wers1xx/Hikkari/commit/{ghash}">@{ghash[:8]}</a>'
                if ghash
                else ""
            ),
        )

        caption = self.strings["logs_caption"].format(named_lvl, *other)

        if isinstance(message, Message):
            await utils.answer(
                message,
                caption,
                file=logs,
            )
        else:
            await self._client.send_file(
                message.form["chat"],
                logs,
                caption=caption,
                reply_to=message.form["top_msg_id"],
            )

    @loader.command()
    async def suspend(self, message: Message):
        try:
            time_sleep = float(utils.get_args_raw(message))
            if time_sleep > 86400 * 365 * 100:
                await utils.answer(message, self.strings["suspend_invalid_time"])
            else:
                await utils.answer(
                    message,
                    self.strings["suspended"].format(time_sleep),
                )
                time.sleep(time_sleep)
        except ValueError:
            await utils.answer(message, self.strings["suspend_invalid_time"])

    @loader.command()
    async def ping(self, message: Message):
        """Heroku-style Rich ping with banner + full placeholders."""
        import contextlib
        import getpass
        import psutil
        import platform as lib_platform
        from .. import version as _ver
        from .._internal import normalize_rich_html

        start = time.perf_counter_ns()
        # measure against a quick no-op answer then replace with rich
        probe = await utils.answer(message, self.config.get("ping_emoji") or "✨")
        ping_ms = round((time.perf_counter_ns() - start) / 10**6, 3)

        me_name = ""
        with contextlib.suppress(Exception):
            me_name = utils.get_display_name(self._client.hikkari_me) or ""

        class _Safe(dict):
            def __missing__(self, key):
                return ""

        data = _Safe(
            ping=ping_ms,
            uptime=utils.formatted_uptime(),
            ping_hint="",
            version=".".join(map(str, getattr(_ver, "__version__", (0, 0, 0)))),
            build=str(utils.get_commit_url()) if hasattr(utils, "get_commit_url") else "",
            branch=getattr(_ver, "branch", "master"),
            me=me_name,
            owner=me_name,
            me_plain=me_name,
            prefix=self.get_prefix(),
            platform=utils.get_named_platform() if hasattr(utils, "get_named_platform") else utils.get_platform_name(),
            ram_usage=f"{utils.get_ram_usage()} MB",
            cpu_usage=str(utils.get_cpu_usage()),
            hostname=lib_platform.node(),
            kernel=lib_platform.release(),
            user=getpass.getuser(),
            os=lib_platform.system(),
            python_ver=lib_platform.python_version(),
            upd="",
            time=__import__("datetime").datetime.now().strftime("%H:%M:%S"),
            date=__import__("datetime").datetime.now().strftime("%d.%m.%Y"),
        )
        with contextlib.suppress(Exception):
            if self.config.get("hint") and random.choice([0, 0, 1]) == 1:
                data["ping_hint"] = str(self.config["hint"])

        template = self.config.get("custom_message")
        if isinstance(template, str) and template.strip():
            text = template.format_map(data)
        else:
            text = (
                f"<p><tg-emoji emoji-id=5920515922505765329>⚡️</tg-emoji> "
                f"<b>Ping:</b> <code>{ping_ms}</code> ms</p>"
                f"<p><tg-emoji emoji-id=5900104897885376843>🕓</tg-emoji> "
                f"<b>Uptime:</b> <code>{data['uptime']}</code></p>"
            )

        if self.config.get("rich_mode", True):
            rich = text.replace("\r\n", "<br>").replace("\n", "<br>")
            if "<p>" not in rich and "<details>" not in rich:
                rich = "".join(f"<p>{ln}</p>" for ln in rich.split("<br>") if ln.strip())
            # banner
            banner = self.config.get("banner_url")
            if isinstance(banner, list) and banner:
                banner = random.choice(banner)
            banner = str(banner or "").strip()
            if banner.startswith("local:"):
                banner = (
                    "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/"
                    + banner[6:].lstrip("/")
                )
            if banner and not banner.startswith("http"):
                banner = (
                    "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/"
                    + banner.lstrip("/")
                )
            if not banner.startswith("http"):
                banner = "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-started.jpg"
            if not banner.lower().endswith((".mp4", ".webm", ".gif", ".mov")):
                if "<figure" not in rich.lower():
                    rich = f'<figure><img src="{banner}"/></figure>' + rich
            rich = normalize_rich_html(rich)
            try:
                # Prefer native send into same chat (Heroku path)
                chat = utils.get_chat_id(probe) if probe else utils.get_chat_id(message)
                with contextlib.suppress(Exception):
                    if probe and getattr(probe, "out", False):
                        await probe.delete()
                sent = await self._client.send_rich_message(chat, rich)
                if sent:
                    return
            except Exception:
                logger.exception("native rich ping failed")
            await utils.answer_with_media_fallback(message, rich_message=rich)
            return

        await utils.answer(probe or message, text)


    async def usinfo(self, message: Message):
        """Detailed host / process resource usage"""
        import os
        import psutil
        import platform as lib_platform
        from ..utils.rich import can_use_rich
        from ..utils.rich_api import build_info_html, to_rich_compatible, try_send_rich, pick_banner_url

        proc = psutil.Process(os.getpid())
        with contextlib.suppress(Exception):
            proc.cpu_percent(interval=None)  # prime
        await asyncio.sleep(0.15)

        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        disk = psutil.disk_usage("/")
        try:
            load1, load5, load15 = psutil.getloadavg()
            load_s = f"{load1:.2f} / {load5:.2f} / {load15:.2f}"
        except Exception:
            load_s = "—"

        try:
            cpu_freq = psutil.cpu_freq()
            freq_s = f"{cpu_freq.current:.0f} MHz" if cpu_freq else "—"
        except Exception:
            freq_s = "—"

        rss = proc.memory_info().rss
        pcpu = proc.cpu_percent(interval=0.2)
        pmem = proc.memory_percent()
        threads = proc.num_threads()
        try:
            open_files = len(proc.open_files())
        except Exception:
            open_files = "—"
        try:
            conns = len(proc.net_connections() if hasattr(proc, 'net_connections') else proc.connections())
        except Exception:
            conns = "—"

        def _mb(n: float) -> str:
            return f"{n / 1024 / 1024:.1f} MB"

        def _gb(n: float) -> str:
            return f"{n / 1024 / 1024 / 1024:.2f} GB"

        rows = [
            ("Host", lib_platform.node()),
            ("OS", f"{lib_platform.system()} {lib_platform.release()}"),
            ("Arch", lib_platform.machine()),
            ("Python", lib_platform.python_version()),
            ("CPU cores", f"{psutil.cpu_count(logical=False) or '?'} phys / {psutil.cpu_count() or '?'} log"),
            ("CPU total", f"{psutil.cpu_percent(interval=0.2):.1f}%"),
            ("CPU freq", freq_s),
            ("Load avg", load_s),
            ("RAM total", _gb(vm.total)),
            ("RAM used", f"{_gb(vm.used)} ({vm.percent:.1f}%)"),
            ("RAM free", _gb(vm.available)),
            ("Swap", f"{_gb(sm.used)} / {_gb(sm.total)} ({sm.percent:.1f}%)"),
            ("Disk /", f"{_gb(disk.used)} / {_gb(disk.total)} ({disk.percent:.1f}%)"),
            ("UB PID", str(os.getpid())),
            ("UB RAM (RSS)", f"{_mb(rss)} ({pmem:.1f}%)"),
            ("UB CPU", f"{pcpu:.1f}%"),
            ("UB threads", str(threads)),
            ("UB open files", str(open_files)),
            ("UB connections", str(conns)),
            ("UB uptime", utils.formatted_uptime()),
        ]

        # Classic text
        lines = [
            f"<tg-emoji emoji-id=5283176512747507510>✨</tg-emoji> <b>Hikkari usinfo</b>",
            "",
            f"<b>Host</b>: <code>{utils.escape_html(lib_platform.node())}</code>",
            f"<b>OS</b>: <code>{utils.escape_html(lib_platform.system() + ' ' + lib_platform.release())}</code>",
            f"<b>CPU</b>: <code>{psutil.cpu_percent(interval=None):.1f}%</code> · cores <code>{psutil.cpu_count(logical=False)}/{psutil.cpu_count()}</code>",
            f"<b>RAM</b>: <code>{_mb(vm.used)}</code> / <code>{_mb(vm.total)}</code> (<code>{vm.percent:.1f}%</code>)",
            f"<b>Swap</b>: <code>{_mb(sm.used)}</code> / <code>{_mb(sm.total)}</code>",
            f"<b>Disk</b>: <code>{_gb(disk.used)}</code> / <code>{_gb(disk.total)}</code> (<code>{disk.percent:.1f}%</code>)",
            "",
            f"<b>Userbot process</b>",
            f"├ PID <code>{os.getpid()}</code>",
            f"├ RAM <code>{_mb(rss)}</code> (<code>{pmem:.1f}%</code>)",
            f"├ CPU <code>{pcpu:.1f}%</code>",
            f"├ threads <code>{threads}</code>",
            f"├ files <code>{open_files}</code> · conn <code>{conns}</code>",
            f"└ uptime <code>{utils.formatted_uptime()}</code>",
        ]
        text = "\n".join(lines)

        try:
            if can_use_rich(self._client, self._db) and getattr(
                self.inline, "init_complete", False
            ):
                burl = pick_banner_url(self.config.get("banner_url"))
                html = build_info_html(
                    title="Hikkari usinfo",
                    rows=rows,
                    footer="Process = this userbot instance",
                    banner_url=burl,
                )
                html = to_rich_compatible(html)
                from ..utils.rich_api import inject_banner_html as _inj
                html = _inj(html, burl, force=True)
                m = await self.inline.rich(
                    message,
                    html,
                    title="Hikkari usinfo",
                    description=f"RAM {_mb(rss)} · CPU {pcpu:.1f}%",
                    thumbnail_url=burl,
                    silent=True,
                )
                if m:
                    return
                chat = utils.get_chat_id(message)
                if await try_send_rich(self._client, chat, html):
                    with contextlib.suppress(Exception):
                        if getattr(message, "out", False):
                            await message.delete()
                    return
        except Exception:
            logger.warning("usinfo rich failed", exc_info=True)

        await utils.answer(message, text, skip_rich=True)

    async def client_ready(self):
        self._content_channel_id = await utils.wait_for_content_channel(self._db)
        if not self._content_channel_id:
            logger.warning("No content channel — log channel unavailable")
            self.logchat = None
            return

        self.logchat = int(f"-100{self._content_channel_id}")
        try:
            logging.getLogger().handlers[0].install_tg_log(self)
            logger.debug("Bot logging installed for %s", self.logchat)
        except Exception:
            logger.exception("install_tg_log failed (non-fatal)")

        self._pass_config_to_logger()
