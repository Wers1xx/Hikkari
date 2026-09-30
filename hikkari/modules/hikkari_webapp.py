# ©️ Wers1xx, 2025-2026
# This file is a part of Hikkari Userbot
# 🌐 https://github.com/Wers1xx/Hikkari
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

import asyncio
import contextlib
import logging
import secrets
import socket
from pathlib import Path

from hikkaritl.tl.types import Message

from .. import loader, utils
from ..webapp.server import start_webapp

logger = logging.getLogger(__name__)


@loader.tds
class HikkariWebAppMod(loader.Module):
    """Always-on WebApp: configs, modules, media, commands"""

    strings = {
        "name": "HikkariWebApp",
        "started": (
            "✨ <b>Hikkari WebApp</b>\n\n"
            "🔗 <code>{url}</code>\n"
            "🔑 <code>{token}</code>\n\n"
            "Открой ссылку в браузере и вставь токен (или открой URL с ?token=…)."
        ),
        "already": "✨ WebApp уже запущен:\n<code>{url}</code>\n🔑 <code>{token}</code>",
        "stopped": "🛑 WebApp остановлен",
        "not_running": "WebApp не запущен",
        "info": (
            "✨ <b>WebApp</b> — панель управления юзерботом\n"
            "• конфиги core и внешних модулей\n"
            "• запуск команд\n"
            "• загрузка медиа\n"
            "• работает, пока жив юзербот\n\n"
            "<code>.webapp</code> — ссылка и токен\n"
            "<code>.webapp stop</code> — остановить\n"
            "<code>.webapp restart</code> — перезапуск"
        ),
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "host",
                "0.0.0.0",
                lambda: "Bind host",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "port",
                9268,
                lambda: "Bind port",
                validator=loader.validators.Integer(minimum=1, maximum=65535),
            ),
            loader.ConfigValue(
                "autostart",
                True,
                lambda: "Start WebApp with userbot",
                validator=loader.validators.Boolean(),
            ),
        )
        self._runner = None
        self._web_token = None

    async def client_ready(self):
        self._web_token = self.get("token")
        if not self._web_token:
            self._web_token = secrets.token_urlsafe(24)
            self.set("token", self._web_token)

        if self.config["autostart"]:
            await self._ensure_server()

    async def on_unload(self):
        await self._stop_server()

    def _public_host(self) -> str:
        host = self.config["host"]
        if host in {"0.0.0.0", "::"}:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"
        return host

    def _url(self) -> str:
        return f"http://{self._public_host()}:{int(self.config['port'])}/?token={self._web_token}"

    async def _ensure_server(self):
        if self._runner is not None:
            return
        try:
            self._runner = await start_webapp(
                self,
                str(self.config["host"]),
                int(self.config["port"]),
            )
            logger.info("WebApp up at %s", self._url())
        except OSError as e:
            logger.exception("WebApp bind failed: %s", e)
            self._runner = None
            raise

    async def _stop_server(self):
        if self._runner is None:
            return
        with contextlib.suppress(Exception):
            await self._runner.cleanup()
        self._runner = None

    @loader.command()
    async def webapp(self, message: Message):
        """WebApp panel: link, stop, restart"""
        args = (utils.get_args_raw(message) or "").strip().lower()

        if args in {"help", "?"}:
            await utils.answer(message, self.strings["info"])
            return

        if args in {"stop", "off", "disable"}:
            if not self._runner:
                await utils.answer(message, self.strings["not_running"])
                return
            await self._stop_server()
            await utils.answer(message, self.strings["stopped"])
            return

        if args in {"restart", "reboot"}:
            await self._stop_server()
            await asyncio.sleep(0.3)
            await self._ensure_server()
            await utils.answer(
                message,
                self.strings["started"].format(url=self._url(), token=self._web_token),
            )
            return

        if args in {"newtoken", "token"}:
            self._web_token = secrets.token_urlsafe(24)
            self.set("token", self._web_token)
            if self._runner:
                await self._stop_server()
                await self._ensure_server()

        try:
            if not self._runner:
                await self._ensure_server()
                await utils.answer(
                    message,
                    self.strings["started"].format(
                        url=self._url(), token=self._web_token
                    ),
                )
            else:
                await utils.answer(
                    message,
                    self.strings["already"].format(
                        url=self._url(), token=self._web_token
                    ),
                )
        except Exception as e:
            await utils.answer(message, f"WebApp error: <code>{utils.escape_html(str(e))}</code>")


