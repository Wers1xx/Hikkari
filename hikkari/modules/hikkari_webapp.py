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
        "link_admin": (
            "✨ <a href=\"{url}\">WebApp Hikkari</a>\n\n"
            "🔑 Админ-доступ (owner / co-owner)\n"
            "<code>{token}</code>"
        ),
        "link_view": (
            "✨ <a href=\"{url}\">WebApp Hikkari</a>\n\n"
            "👁 Только обзор (без конфигов и команд)\n"
            "<code>{token}</code>"
        ),
        "denied": "🚫 Только owner или co-owner может получить полный WebApp.",
        "stopped": "🛑 WebApp остановлен",
        "not_running": "WebApp не запущен",
        "info": (
            "✨ <b>WebApp Hikkari</b>\n"
            "• owner / co-owner — полный доступ\n"
            "• остальные — только обзор (view-токен)\n\n"
            "<code>.webapp</code> — ссылка\n"
            "<code>.webapp view</code> — публичный обзор\n"
            "<code>.webapp stop</code> / <code>restart</code>"
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
        self._web_view_token = None

    async def client_ready(self):
        self._web_token = self.get("token")
        if not self._web_token:
            self._web_token = secrets.token_urlsafe(24)
            self.set("token", self._web_token)
        self._web_view_token = self.get("view_token")
        if not self._web_view_token:
            self._web_view_token = secrets.token_urlsafe(24)
            self.set("view_token", self._web_view_token)

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

    def _url(self, *, admin: bool = True) -> str:
        tok = self._web_token if admin else self._web_view_token
        return (
            f"http://{self._public_host()}:{int(self.config['port'])}/?token={tok}"
        )

    def _is_admin_user(self, user_id: int) -> bool:
        if user_id == self.tg_id:
            return True
        try:
            owners = list(self._client.dispatcher.security.owner or [])
        except Exception:
            owners = []
        return int(user_id) in {int(x) for x in owners}

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
        """WebApp Hikkari — clickable link; admin for owners only"""
        args = (utils.get_args_raw(message) or "").strip().lower()
        uid = message.sender_id or self.tg_id
        is_admin = self._is_admin_user(uid)

        if args in {"help", "?"}:
            await utils.answer(message, self.strings["info"])
            return

        if args in {"stop", "off", "disable"}:
            if not is_admin:
                await utils.answer(message, self.strings["denied"])
                return
            if not self._runner:
                await utils.answer(message, self.strings["not_running"])
                return
            await self._stop_server()
            await utils.answer(message, self.strings["stopped"])
            return

        if args in {"restart", "reboot"}:
            if not is_admin:
                await utils.answer(message, self.strings["denied"])
                return
            await self._stop_server()
            await asyncio.sleep(0.3)
            await self._ensure_server()

        if args in {"newtoken", "token"}:
            if not is_admin:
                await utils.answer(message, self.strings["denied"])
                return
            self._web_token = secrets.token_urlsafe(24)
            self.set("token", self._web_token)
            self._web_view_token = secrets.token_urlsafe(24)
            self.set("view_token", self._web_view_token)
            if self._runner:
                await self._stop_server()
                await self._ensure_server()

        want_view = args in {"view", "public", "readonly"}
        if not is_admin:
            want_view = True  # guests only get overview link

        try:
            if not self._runner:
                await self._ensure_server()
        except Exception as e:
            await utils.answer(
                message,
                f"WebApp error: <code>{utils.escape_html(str(e))}</code>",
            )
            return

        if want_view or not is_admin:
            url = self._url(admin=False)
            await utils.answer(
                message,
                self.strings["link_view"].format(url=url, token=self._web_view_token),
            )
        else:
            url = self._url(admin=True)
            await utils.answer(
                message,
                self.strings["link_admin"].format(url=url, token=self._web_token),
            )

