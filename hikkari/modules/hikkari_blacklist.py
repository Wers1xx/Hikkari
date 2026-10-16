# ©️ Wers1xx, 2025-2026
# Project blacklist enforcement (assets/BlackList.txt on GitHub)

import asyncio
import contextlib
import logging
import os
import sys

from .. import loader
from ..blacklist import enforce_blacklist, is_locally_blocked, notify_blocked

logger = logging.getLogger(__name__)


@loader.tds
class HikkariBlacklistMod(loader.Module):
    """Enforces Hikkari project blacklist from GitHub"""

    strings = {"name": "HikkariBlacklist"}

    async def client_ready(self):
        await self._check_and_kill()
        self._task = asyncio.ensure_future(self._loop())

    async def on_unload(self):
        task = getattr(self, "_task", None)
        if task:
            task.cancel()

    async def _loop(self):
        while True:
            try:
                await asyncio.sleep(120)
                await self._check_and_kill()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("blacklist loop error")

    async def _check_and_kill(self):
        try:
            blocked = await enforce_blacklist(
                self._client, self._db, user_id=int(self.tg_id)
            )
        except Exception:
            logger.exception("blacklist check failed")
            return
        if not blocked and not is_locally_blocked(self._db):
            return

        logger.critical(
            "Account %s is on Hikkari project blacklist — shutting down",
            self.tg_id,
        )
        with contextlib.suppress(Exception):
            await notify_blocked(self._client, int(self.tg_id))
        await asyncio.sleep(1.5)
        with contextlib.suppress(Exception):
            os._exit(1)
        sys.exit(1)
