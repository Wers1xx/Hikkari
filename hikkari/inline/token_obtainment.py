import asyncio
import logging
import os
import random
import re
import typing

from herokutl.errors.rpcerrorlist import YouBlockedUserError
from herokutl.tl.functions.contacts import UnblockRequest

from .. import utils
from .._internal import fw_protect
from .types import InlineUnit

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager

logger = logging.getLogger(__name__)
BOT_BASE_PATTERN = re.compile(r"(\w*)_[0-9a-zA-Z]{6}_bot")


class TokenObtainment(InlineUnit):
    async def _create_bot(self: "InlineManager"):
        logger.info("User doesn't have bot, attempting creating new one")
        async with self._client.conversation("@BotFather", exclusive=False) as conv:
            await fw_protect()
            m = await conv.send_message("/newbot")
            r = await conv.get_response()

            logger.debug(">> %s", m.raw_text)
            logger.debug("<< %s", r.raw_text)

            if "20" in r.raw_text:
                return False

            await fw_protect()

            await m.delete()
            await r.delete()

            from .. import main

            if self._db.get("hikkari.inline", "custom_bot", False):
                username = self._db.get("hikkari.inline", "custom_bot").strip("@")
                username = f"@{username}"
                try:
                    await self._client.get_entity(username)
                except ValueError:
                    pass
                else:
                    uid = utils.rand(6)
                    genran = "".join(random.choice(main.LATIN_MOCK))
                    username = f"@{genran}_{uid}_bot"
            else:
                uid = utils.rand(6)
                genran = "".join(random.choice(main.LATIN_MOCK))
                username = f"@{genran}_{uid}_bot"

            for msg in [
                "🪐 Hikkari userbot"[:64],
                username,
                "/setuserpic",
                username,
            ]:
                await fw_protect()
                m = await conv.send_message(msg)
                r = await conv.get_response()

                logger.debug(">> %s", m.raw_text)
                logger.debug("<< %s", r.raw_text)

                await fw_protect()
                await m.delete()
                await r.delete()

            try:
                await fw_protect()
                from .. import main

                if "DOCKER" in os.environ:
                    m = await conv.send_file(
                        "https://raw.githubusercontent.com/Wers1xx/Hikkari/refs/heads/master/assets/hikkari-ava.png"
                    )
                else:
                    m = await conv.send_file(
                        main.BASE_PATH / "assets" / "hikkari-ava.png"
                    )
                r = await conv.get_response()

                logger.debug(">> <Photo>")
                logger.debug("<< %s", r.raw_text)
            except Exception:
                await fw_protect()
                m = await conv.send_message("/cancel")
                r = await conv.get_response()

                logger.debug(">> %s", m.raw_text)
                logger.debug("<< %s", r.raw_text)

            await fw_protect()

            await m.delete()
            await r.delete()

        return await self._assert_token(create_new_if_needed=False)

    async def _prompt_inline_setup(self: "InlineManager") -> None:
        """Ask user in Saved Messages whether to create / attach an inline bot."""
        if self._db.get("hikkari.inline", "setup_prompted", False):
            return
        prefix = self._db.get("hikkari.main", "command_prefix", False) or "."
        text = (
            "🪐 <b>Hikkari — Inline bot setup</b>\n\n"
            "Нужен инлайн-бот для форм, галерей и логов.\n\n"
            f"• <code>{prefix}yesbot</code> — создать нового бота через @BotFather\n"
            f"• <code>{prefix}nobot</code> — пропустить (без инлайна)\n"
            f"• <code>{prefix}ch_bot_token &lt;token&gt;</code> — свой токен "
            f"(например <code>{prefix}ch_bot_token 123456:ABC...</code>)\n\n"
            "<i>После выбора выполни</i> <code>{}restart -f</code>"
        ).format(prefix)
        try:
            await self._client.send_message("me", text)
        except Exception:
            logger.exception("Failed to send inline setup prompt to Saved Messages")
        self._db.set("hikkari.inline", "setup_prompted", True)

    async def _assert_token(
        self: "InlineManager",
        create_new_if_needed: bool = True,
        revoke_token: bool = False,
    ) -> bool:
        if self._token:
            return True

        # User chose to skip inline
        if self._db.get("hikkari.inline", "skip_inline", False):
            logger.info("Inline bot skipped by user (nobot)")
            return False

        # First run: do NOT auto-create — ask in Saved Messages
        if not self._db.get("hikkari.inline", "allow_auto_create", False):
            logger.info("No bot token — prompting user for yesbot/nobot/ch_bot_token")
            await self._prompt_inline_setup()
            return False

        logger.info("Bot token not found in db, attempting search in BotFather")

        if not self._db.get(__name__, "no_mute", False):
            await utils.dnd(
                self._client,
                await self._client.get_entity("@BotFather"),
                True,
            )
            self._db.set(__name__, "no_mute", True)

        async with self._client.conversation("@BotFather", exclusive=False) as conv:
            try:
                await fw_protect()
                m = await conv.send_message("/token")
            except YouBlockedUserError:
                await self._client(UnblockRequest(id="@BotFather"))
                await fw_protect()
                m = await conv.send_message("/token")

            r = await conv.get_response()

            logger.debug(">> %s", m.raw_text)
            logger.debug("<< %s", r.raw_text)

            await fw_protect()

            await m.delete()
            await r.delete()

            if not hasattr(r, "reply_markup") or not hasattr(r.reply_markup, "rows"):
                await conv.cancel_all()

                return await self._create_bot() if create_new_if_needed else False

            from .. import main

            for row in r.reply_markup.rows:
                for button in row.buttons:
                    btn_text = button.text.strip("@")

                    if self._db.get("hikkari.inline", "custom_bot", False) and (
                        self._db.get("hikkari.inline", "custom_bot", False) != btn_text
                    ):
                        continue

                    if not self._db.get("hikkari.inline", "custom_bot", False) and not (
                        (match := BOT_BASE_PATTERN.fullmatch(btn_text))
                        and match.group(1) in main.LATIN_MOCK
                    ):
                        continue

                    await fw_protect()

                    m = await conv.send_message(button.text)
                    r = await conv.get_response()

                    logger.debug(">> %s", m.raw_text)
                    logger.debug("<< %s", r.raw_text)

                    if revoke_token:
                        await fw_protect()
                        await m.delete()
                        await r.delete()

                        await fw_protect()

                        m = await conv.send_message("/revoke")
                        r = await conv.get_response()

                        logger.debug(">> %s", m.raw_text)
                        logger.debug("<< %s", r.raw_text)

                        await fw_protect()

                        await m.delete()
                        await r.delete()

                        await fw_protect()

                        m = await conv.send_message(button.text)
                        r = await conv.get_response()

                        logger.debug(">> %s", m.raw_text)
                        logger.debug("<< %s", r.raw_text)

                    token = r.raw_text.splitlines()[1]

                    self._db.set("hikkari.inline", "bot_token", token)
                    self._token = token

                    await fw_protect()

                    await m.delete()
                    await r.delete()

                    for msg in [
                        "/setinline",
                        button.text,
                        "user@hikkari:~$",
                        "/setinlinefeedback",
                        button.text,
                        "Enabled",
                        "/setuserpic",
                        button.text,
                    ]:
                        await fw_protect()
                        m = await conv.send_message(msg)
                        r = await conv.get_response()

                        logger.debug(">> %s", m.raw_text)
                        logger.debug("<< %s", r.raw_text)

                        await fw_protect()

                        await m.delete()
                        await r.delete()

                    try:
                        await fw_protect()
                        from .. import main

                        m = await conv.send_file(
                            main.BASE_PATH / "assets" / "hikkari-ava.png"
                        )
                        r = await conv.get_response()

                        logger.debug(">> <Photo>")
                        logger.debug("<< %s", r.raw_text)
                    except Exception:
                        await fw_protect()
                        m = await conv.send_message("/cancel")
                        r = await conv.get_response()

                        logger.debug(">> %s", m.raw_text)
                        logger.debug("<< %s", r.raw_text)

                    await fw_protect()

                    await m.delete()
                    await r.delete()

                    # TODO: add bot commands setup
                    return True

        return await self._create_bot() if create_new_if_needed else False

    async def _reassert_token(self: "InlineManager"):
        is_token_asserted = await self._assert_token(revoke_token=True)
        if not is_token_asserted:
            self.init_complete = False
        else:
            await self.register_manager(ignore_token_checks=True)

    async def _dp_revoke_token(self: "InlineManager", already_initialised: bool = True):
        if already_initialised:
            await self._stop()
            logger.error("Got polling conflict. Attempting token revocation...")

        self._db.set("hikkari.inline", "bot_token", None)
        self._token = None
        if already_initialised:
            asyncio.ensure_future(self._reassert_token())
        else:
            return await self._reassert_token()

    async def _check_bot(self: "InlineManager", username: str):
        username = username.strip("@")
        async with self._client.conversation("@BotFather", exclusive=False) as conv:
            try:
                m = await conv.send_message("/token")
            except YouBlockedUserError:
                await self._client(UnblockRequest(id="@BotFather"))
                m = await conv.send_message("/token")

            r = await conv.get_response()

            await m.delete()
            await r.delete()

            if not hasattr(r, "reply_markup") or not hasattr(r.reply_markup, "rows"):
                return False

            for row in r.reply_markup.rows:
                for button in row.buttons:
                    if username != button.text.strip("@"):
                        continue

                    m = await conv.send_message("/cancel")
                    r = await conv.get_response()

                    await m.delete()
                    await r.delete()

                    return True
