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
import contextlib
import io
import json
import logging
import random
import time

from hikkaritl.tl import functions
from hikkaritl.tl.tlobject import TLRequest
from hikkaritl.tl.types import Message
from hikkaritl.utils import is_list_like

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

GROUPS = [
    "auth",
    "account",
    "users",
    "contacts",
    "messages",
    "updates",
    "photos",
    "upload",
    "help",
    "channels",
    "bots",
    "payments",
    "stickers",
    "phone",
    "langpack",
    "folders",
    "stats",
]


CONSTRUCTORS = {
    (entity_name[0].lower() + entity_name[1:]).rsplit("Request", 1)[0]: getattr(
        cur_entity, "CONSTRUCTOR_ID"
    )
    for group in GROUPS
    for entity_name in dir(getattr(functions, group))
    if hasattr(
        (cur_entity := getattr(getattr(functions, group), entity_name)), "__bases__"
    )
    and TLRequest in cur_entity.__bases__
    and hasattr(cur_entity, "CONSTRUCTOR_ID")
}


@loader.tds
class APIRatelimiterMod(loader.Module):
    """Helps userbot avoid spamming Telegram API"""

    strings = {"name": "APILimiter"}

    def __init__(self):
        self._ratelimiter: list[tuple] = []
        self._suspend_until = 0
        self._lock = False
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "time_sample",
                15,
                lambda: self.strings["_cfg_time_sample"],
                validator=loader.validators.Integer(minimum=1),
            ),
            loader.ConfigValue(
                "threshold",
                120,
                lambda: self.strings["_cfg_threshold"],
                validator=loader.validators.Integer(minimum=10),
            ),
            loader.ConfigValue(
                "local_floodwait",
                30,
                lambda: self.strings["_cfg_local_floodwait"],
                validator=loader.validators.Integer(minimum=10, maximum=3600),
            ),
            loader.ConfigValue(
                "read_weight",
                0.35,
                lambda: "Weight of bulk-read requests (ReadHistory/ReadMentions/GetChannels) toward freeze threshold",
                validator=loader.validators.Float(minimum=0.05, maximum=1.0),
            ),
            loader.ConfigValue(
                "soft_throttle_ms",
                40,
                lambda: "Soft delay (ms) between bulk-read requests when approaching limit",
                validator=loader.validators.Integer(minimum=0, maximum=2000),
            ),
            loader.ConfigValue(
                "forbidden_methods",
                ["joinChannel", "importChatInvite"],
                lambda: self.strings["_cfg_forbidden_methods"],
                validator=loader.validators.MultiChoice(
                    [
                        "sendReaction",
                        "joinChannel",
                        "importChatInvite",
                    ]
                ),
                on_change=self.on_forbidden_methods_update,
            ),
        )

    async def client_ready(self):
        asyncio.ensure_future(self._install_protection())

    async def on_forbidden_methods_update(self):
        self._client.forbid_constructors(
            list(
                map(
                    lambda x: CONSTRUCTORS[x],
                    self.config["forbidden_methods"],
                )
            )
        )

    async def _install_protection(self):
        await asyncio.sleep(8)  # Restart lock (was 30; faster ready on weak hosts)
        if hasattr(self._client._call, "_old_call_rewritten"):
            raise loader.SelfUnload("Already installed")

        old_call = self._client._call

        # Bulk-read TL methods often flood when InstantRead / dialogs sync runs
        _READ_BULK = {
            "ReadMentionsRequest",
            "ReadHistoryRequest",
            "GetChannelsRequest",
            "GetFullChannelRequest",
            "GetDialogsRequest",
            "GetPeerDialogsRequest",
            "GetParticipantRequest",
            "GetParticipantsRequest",
        }

        async def new_call(
            sender: "MTProtoSender",  # type: ignore  # noqa: F821
            request: TLRequest,
            ordered: bool = False,
            flood_sleep_threshold: int = None,
        ):
            await asyncio.sleep(random.randint(0, 2) / 1000)
            req = (request,) if not is_list_like(request) else request
            for r in req:
                if (
                    time.perf_counter() > self._suspend_until
                    and not self.get(
                        "disable_protection",
                        True,
                    )
                    and (
                        r.__module__.rsplit(".", maxsplit=1)[1]
                        in {"messages", "account", "channels"}
                    )
                ):
                    request_name = type(r).__name__
                    now = time.perf_counter()
                    is_read = request_name in _READ_BULK
                    weight = float(self.config.get("read_weight", 0.35)) if is_read else 1.0

                    self._ratelimiter += [(request_name, now, weight)]

                    sample = int(self.config["time_sample"])
                    self._ratelimiter = [
                        x
                        for x in self._ratelimiter
                        if now - x[1] < sample
                    ]

                    # Weighted score: bulk-reads count less toward hard freeze
                    score = sum(x[2] if len(x) > 2 else 1.0 for x in self._ratelimiter)
                    threshold = float(self.config["threshold"])

                    # Soft throttle when mostly bulk-reads and approaching limit
                    if is_read and score > threshold * 0.45:
                        delay_ms = int(self.config.get("soft_throttle_ms", 80) or 0)
                        if delay_ms > 0:
                            await asyncio.sleep(delay_ms / 1000)

                    if score > threshold and not self._lock:
                        self._lock = True
                        # Strip weights for report compatibility
                        report_data = [
                            [name, ts] for name, ts, *_ in (
                                (x[0], x[1], x[2] if len(x) > 2 else 1.0) for x in self._ratelimiter
                            )
                        ]
                        report_bytes = json.dumps(report_data, indent=4).encode()
                        report = io.BytesIO(report_bytes)
                        report.name = "local_fw_report.json"

                        with contextlib.suppress(Exception):
                            await self.inline.bot.send_document(
                                self.tg_id,
                                report,
                                caption=self.inline.sanitise_text(
                                    self.strings["warning"].format(
                                        self.config["local_floodwait"],
                                        prefix=utils.escape_html(self.get_prefix()),
                                    )
                                ),
                            )

                        # Non-blocking freeze: wait without freezing the whole process
                        await asyncio.sleep(int(self.config["local_floodwait"]))
                        self._ratelimiter.clear()
                        self._lock = False

            # While locked, wait a bit so callers don't pile up more requests
            while self._lock and time.perf_counter() > self._suspend_until:
                await asyncio.sleep(0.2)

            return await old_call(sender, request, ordered, flood_sleep_threshold)

        self._client._call = new_call
        self._client._old_call_rewritten = old_call
        self._client._call._hikkari_overwritten = True
        logger.debug("Successfully installed ratelimiter")

    async def on_unload(self):
        if hasattr(self._client, "_old_call_rewritten"):
            self._client._call = self._client._old_call_rewritten
            delattr(self._client, "_old_call_rewritten")
            logger.debug("Successfully uninstalled ratelimiter")

    @loader.command()
    async def suspend_api_protect(self, message: Message):
        if not (args := utils.get_args_raw(message)) or not args.isdigit():
            await utils.answer(message, self.strings["args_invalid"])
            return

        self._suspend_until = time.perf_counter() + int(args)
        await utils.answer(message, self.strings["suspended_for"].format(args))

    @loader.command()
    async def api_fw_protection(self, message: Message):
        await self.inline.form(
            message=message,
            text=self.strings["u_sure"],
            reply_markup=[
                {"text": self.strings["btn_no"], "action": "close"},
                {"text": self.strings["btn_yes"], "callback": self._finish},
            ],
        )

    async def _finish(self, call: InlineCall):
        state = self.get("disable_protection", True)
        self.set("disable_protection", not state)
        await call.edit(self.strings["on" if state else "off"])
