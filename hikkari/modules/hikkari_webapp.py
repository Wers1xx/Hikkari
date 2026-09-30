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

from hikkaritl.tl.types import Message, PeerUser, User

from .. import loader, utils
from ..inline.types import InlineCall
from ..webapp.server import start_webapp

logger = logging.getLogger(__name__)


@loader.tds
class HikkariWebAppMod(loader.Module):
    """Always-on WebApp: configs, modules, media, commands"""

    strings = {
        "name": "HikkariWebApp",
        "link": '<a href="{url}">WebApp Hikkari</a>',
        "confirm": (
            "✨ <b>Открыть WebApp Hikkari?</b>\n\n"
            "Подтверди, чтобы получить ссылку.\n"
            "Полный доступ — только owner / co-owner."
        ),
        "btn_open": "✅ Открыть",
        "btn_cancel": "🚫 Отмена",
        "cancelled": "🚫 Отменено",
        "denied": "🚫 Нет доступа к управлению WebApp.",
        "stopped": "🛑 WebApp остановлен",
        "not_running": "WebApp не запущен",
        "error": "WebApp error: <code>{}</code>",
        "info": (
            "✨ <b>WebApp Hikkari</b>\n"
            "• В <b>Избранном</b> и <b>ЛС с инлайн-ботом</b> — сразу ссылка\n"
            "• В чатах и ЛС с людьми — сначала подтверждение\n"
            "• Полный доступ: owner / co-owner\n"
            "• Остальные: только обзор\n\n"
            "<code>.webapp</code> · <code>.webapp view</code>\n"
            "<code>.webapp stop</code> · <code>.webapp restart</code>"
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
            with contextlib.suppress(Exception):
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
        return f"http://{self._public_host()}:{int(self.config['port'])}/?token={tok}"

    def _is_admin_user(self, user_id: int) -> bool:
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return False
        if uid == int(self.tg_id):
            return True
        try:
            owners = list(self._client.dispatcher.security.owner or [])
        except Exception:
            owners = []
        try:
            return uid in {int(x) for x in owners}
        except Exception:
            return False

    def _inline_bot_id(self) -> int | None:
        inline = getattr(self, "inline", None)
        if not inline:
            return None
        for attr in ("bot_id", "_bot_id"):
            val = getattr(inline, attr, None)
            if val:
                try:
                    return int(val)
                except Exception:
                    pass
        bot = getattr(inline, "bot", None)
        if bot is not None:
            for attr in ("id", "bot_id"):
                val = getattr(bot, attr, None)
                if val:
                    try:
                        return int(val)
                    except Exception:
                        pass
        me = getattr(inline, "bot_username", None)
        return None

    async def _is_trusted_chat(self, message: Message) -> bool:
        """Saved Messages or PM with inline bot — no confirm form."""
        try:
            chat_id = int(utils.get_chat_id(message))
        except Exception:
            return False

        # Избранное (Saved Messages)
        if chat_id == int(self.tg_id):
            return True

        if not getattr(message, "is_private", False):
            return False

        bot_id = self._inline_bot_id()
        if bot_id and chat_id == bot_id:
            return True

        # fallback: peer is bot user matching inline bot username
        bot_username = getattr(getattr(self, "inline", None), "bot_username", None)
        if bot_username:
            with contextlib.suppress(Exception):
                peer = await message.get_chat()
                if isinstance(peer, User) and getattr(peer, "bot", False):
                    uname = (peer.username or "").lower()
                    if uname == bot_username.lower().lstrip("@"):
                        return True

        return False

    async def _ensure_server(self):
        if self._runner is not None:
            return
        self._runner = await start_webapp(
            self,
            str(self.config["host"]),
            int(self.config["port"]),
        )
        logger.info("WebApp up at %s", self._url(admin=True))

    async def _stop_server(self):
        if self._runner is None:
            return
        with contextlib.suppress(Exception):
            await self._runner.cleanup()
        self._runner = None

    def _link_text(self, *, admin: bool) -> str:
        return self.strings["link"].format(url=self._url(admin=admin))

    async def _deliver_link(self, message: Message | InlineCall, *, admin: bool):
        try:
            if not self._runner:
                await self._ensure_server()
        except Exception as e:
            text = self.strings["error"].format(utils.escape_html(str(e)))
            if isinstance(message, Message):
                await utils.answer(message, text)
            else:
                await message.edit(text)
            return

        text = self._link_text(admin=admin)
        if isinstance(message, Message):
            await utils.answer(message, text)
        else:
            await message.edit(text)

    async def _webapp_confirm(self, call: InlineCall, want_view: bool = False):
        uid = getattr(call, "from_user", None)
        uid = getattr(uid, "id", None) or getattr(call, "from_id", None) or 0
        try:
            uid = int(uid)
        except Exception:
            uid = 0

        is_admin = self._is_admin_user(uid)
        # Non-owners never receive admin token — only overview
        admin = bool(is_admin) and not want_view
        await self._deliver_link(call, admin=admin)

    async def _webapp_cancel(self, call: InlineCall):
        await call.edit(self.strings["cancelled"])

    async def _ask_confirm(self, message: Message, want_view: bool = False):
        await self.inline.form(
            message=message,
            text=self.strings["confirm"],
            force_me=True,  # only the invoker can press
            reply_markup=[
                [
                    {
                        "text": self.strings["btn_open"],
                        "callback": self._webapp_confirm,
                        "args": (want_view,),
                    }
                ],
                [
                    {
                        "text": self.strings["btn_cancel"],
                        "callback": self._webapp_cancel,
                    }
                ],
            ],
        )

    @loader.command()
    async def webapp(self, message: Message):
        """WebApp Hikkari — confirm in chats; direct in Saved / inline-bot PM"""
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
            try:
                await self._ensure_server()
            except Exception as e:
                await utils.answer(
                    message, self.strings["error"].format(utils.escape_html(str(e)))
                )
                return

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
                with contextlib.suppress(Exception):
                    await self._ensure_server()

        want_view = args in {"view", "public", "readonly"}
        # Guests always view-only link
        if not is_admin:
            want_view = True

        trusted = await self._is_trusted_chat(message)
        if trusted:
            await self._deliver_link(message, admin=(is_admin and not want_view))
            return

        # Groups / PM with people → confirmation form
        await self._ask_confirm(message, want_view=want_view)
