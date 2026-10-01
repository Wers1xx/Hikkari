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
import logging
import os
import random
import re
import typing

from hikkaritl.errors.rpcerrorlist import YouBlockedUserError
from hikkaritl.tl.functions.contacts import UnblockRequest

from .. import utils
from .._internal import fw_protect
from .types import InlineUnit

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager

logger = logging.getLogger(__name__)
BOT_BASE_PATTERN = re.compile(r"(\w*)_[0-9a-zA-Z]{6}_bot")

def _token_backup_paths(tg_id: int | None = None) -> list:
    """All places we may store the bot token (never lose it)."""
    from pathlib import Path
    from .. import main as _main
    base = Path(_main.BASE_PATH)
    paths = [
        base / "inline_bot.token",
        base / "data" / "inline_bot.token",
    ]
    if tg_id:
        paths.insert(0, base / f"inline_bot-{tg_id}.token")
        paths.append(base / "sessions" / f"inline_bot-{tg_id}.token")
    # unique keep order
    seen = set()
    out = []
    for p in paths:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)
    return out


def _token_backup_path() -> "Path":
    return _token_backup_paths()[0]


def _persist_bot_token(db, token: str, username: str | None = None, tg_id: int | None = None) -> None:
    """Save token to DB + multiple durable files. Never drop credentials on error."""
    if not token or not isinstance(token, str):
        return
    token = token.strip()
    if ":" not in token or len(token) < 20:
        logger.warning("Refuse to persist invalid-looking bot token")
        return
    try:
        db.set("hikkari.inline", "bot_token", token)
        db.set("hikkari.inline", "skip_inline", False)
        if username:
            db.set("hikkari.inline", "bot_username", str(username).lstrip("@"))
        try:
            db.save()
        except Exception:
            logger.exception("db.save after token persist failed")
    except Exception:
        logger.exception("DB token persist failed")

    if tg_id is None:
        try:
            tg_id = int(db.get("hikkari.inline", "owner_id", 0) or 0) or None
        except Exception:
            tg_id = None

    for path in _token_backup_paths(tg_id):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(token + "\n", encoding="utf-8")
            with contextlib.suppress(Exception):
                path.chmod(0o600)
        except Exception:
            logger.debug("token backup write failed: %s", path, exc_info=True)

    logger.info("Inline bot token persisted (DB + %s backup file(s))", len(_token_backup_paths(tg_id)))


def _load_bot_token(db, tg_id: int | None = None) -> str | None:
    """Load token from DB and every backup location. Re-persist if restored from file."""
    candidates = []
    for key_mod, key_name in (
        ("hikkari.inline", "bot_token"),
        ("heroku.inline", "bot_token"),
        ("hikka.inline", "bot_token"),
    ):
        with contextlib.suppress(Exception):
            val = db.get(key_mod, key_name, None)
            if val and isinstance(val, str) and ":" in val.strip():
                candidates.append(val.strip())

    if not tg_id:
        with contextlib.suppress(Exception):
            tg_id = int(db.get("hikkari.inline", "owner_id", 0) or 0) or None

    for path in _token_backup_paths(tg_id):
        try:
            if path.is_file():
                raw = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
                if raw and ":" in raw and len(raw) > 20:
                    candidates.append(raw)
        except Exception:
            logger.debug("read backup failed: %s", path, exc_info=True)

    # dedupe keep first
    seen = set()
    ordered = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)

    if not ordered:
        return None

    token = ordered[0]
    # Always re-sync into canonical storage so next restart finds it
    try:
        current = db.get("hikkari.inline", "bot_token", None)
        if current != token:
            logger.warning("Restored inline bot token from backup/source")
            _persist_bot_token(db, token, tg_id=tg_id)
        else:
            # still refresh files
            _persist_bot_token(db, token, tg_id=tg_id)
    except Exception:
        logger.exception("re-persist after load failed")
    return token


class TokenObtainment(InlineUnit):
    async def _create_bot(self: "InlineManager"):
        logger.info("User doesn't have bot, attempting creating new one")
        async with self._client.conversation("@BotFather", exclusive=False) as conv:
            await fw_protect()
            m = await conv.send_message("/newbot")
            r = await conv.get_response()

            logger.debug(">> %s", m.raw_text)
            logger.debug("<< %s", r.raw_text)

            raw = (r.raw_text or "").lower()
            # BotFather limits / spam ban / flood
            spam_markers = (
                "sorry",
                "too many",
                "spam",
                "limited",
                "restrict",
                "can't create",
                "cannot create",
                "не могу",
                "слишком много",
                "ограничен",
            )
            if any(m in raw for m in spam_markers) or ("too many" in raw and "bot" in raw):
                logger.warning("BotFather refused /newbot (spam/limit): %s", r.raw_text)
                await fw_protect()
                with contextlib.suppress(Exception):
                    await m.delete()
                    await r.delete()
                # Do not crash — ask user for token, keep userbot running
                self._db.set("hikkari.inline", "allow_auto_create", False)
                self._db.set("hikkari.inline", "setup_prompted", False)
                prefix = self._db.get("hikkari.main", "command_prefix", False) or "."
                try:
                    await self._client.send_message(
                        "me",
                        "⚠️ <b>Не удалось создать бота через @BotFather</b>\n"
                        "(часто из‑за SpamBan / лимита на создание ботов).\n\n"
                        "Юзербот продолжит работу <b>без инлайна</b>.\n"
                        f"Укажи токен существующего бота:\n"
                        f"<code>{prefix}ch_bot_token &lt;token&gt;</code>\n\n"
                        f"Или пропусти: <code>{prefix}nobot</code>",
                        link_preview=False,
                    )
                except Exception:
                    logger.exception("Failed to notify about BotFather refusal")
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

            token = None
            # 1) display name  2) username (BotFather returns token here)
            for msg in [
                "✨ Hikkari userbot"[:64],
                username,
            ]:
                await fw_protect()
                m = await conv.send_message(msg)
                r = await conv.get_response()
                logger.debug(">> %s", m.raw_text)
                logger.debug("<< %s", r.raw_text)
                # Token looks like 123456789:AAH...
                found = re.search(r"([0-9]{8,12}:[A-Za-z0-9_-]{30,})", r.raw_text or "")
                if found:
                    token = found.group(1)
                await fw_protect()
                await m.delete()
                await r.delete()

            if not token:
                logger.error("Bot created but token not found in BotFather response")
                try:
                    await self._client.send_message(
                        "me",
                        (
                            "⚠️ Бот создан, но токен не найден в ответе BotFather.\n"
                            "Открой @BotFather → /token и укажи:\n"
                            "<code>.ch_bot_token &lt;token&gt;</code>"
                        ),
                        link_preview=False,
                    )
                except Exception:
                    pass
                return False

            _persist_bot_token(self._db, token, username)
            self._token = token
            logger.info("Inline bot created, token saved (+backup)")

            # Enable inline mode + feedback + avatar
            for msg in [
                "/setinline",
                username,
                "user@hikkari:~$",
                "/setinlinefeedback",
                username,
                "Enabled",
                "/setuserpic",
                username,
            ]:
                try:
                    await fw_protect()
                    m = await conv.send_message(msg)
                    r = await conv.get_response()
                    logger.debug(">> %s", m.raw_text)
                    logger.debug("<< %s", r.raw_text)
                    await fw_protect()
                    await m.delete()
                    await r.delete()
                except Exception:
                    logger.exception("BotFather step failed: %s", msg)

            try:
                await fw_protect()
                from .. import main
                ava = main.BASE_PATH / "assets" / "hikkari-ava.png"
                if "DOCKER" in os.environ:
                    m = await conv.send_file(
                        "https://raw.githubusercontent.com/Wers1xx/Hikkari/refs/heads/master/assets/hikkari-ava.png"
                    )
                elif ava.is_file():
                    m = await conv.send_file(str(ava))
                else:
                    m = None
                if m is not None:
                    r = await conv.get_response()
                    logger.debug(">> <Photo>")
                    logger.debug("<< %s", r.raw_text)
                    await fw_protect()
                    await m.delete()
                    await r.delete()
            except Exception:
                logger.exception("Failed to set bot avatar")
                with contextlib.suppress(Exception):
                    await fw_protect()
                    m = await conv.send_message("/cancel")
                    r = await conv.get_response()
                    await m.delete()
                    await r.delete()

            try:
                await self._client.send_message(
                    "me",
                    (
                        f"✨ <b>Инлайн-бот создан:</b> {username}\n"
                        "Токен сохранён. После рестарта инлайн будет активен."
                    ),
                    link_preview=False,
                )
            except Exception:
                pass

            return True

    async def _prompt_inline_setup(self: "InlineManager") -> None:
        """Ask user in Saved Messages whether to create / attach an inline bot."""
        if self._db.get("hikkari.inline", "setup_prompted", False):
            return
        prefix = self._db.get("hikkari.main", "command_prefix", False) or "."
        text = (
            "✨ <b>Hikkari — Inline bot setup</b>\n\n"
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
        # Always try hard to recover token before giving up
        if not self._token:
            try:
                tg = getattr(self._client, "tg_id", None)
                recovered = _load_bot_token(self._db, tg_id=tg)
                if recovered:
                    self._token = recovered
                    logger.info("Inline token recovered before assert")
            except Exception:
                logger.exception("token recovery in _assert_token")

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

                    _persist_bot_token(self._db, token)
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
        """Retry inline manager with existing token. Never revoke at BotFather."""
        token = _load_bot_token(self._db)
        if token:
            self._token = token
            try:
                await self.register_manager(ignore_token_checks=True)
                return True
            except Exception:
                logger.exception("Reassert with existing token failed")
                self.init_complete = False
                return False
        # No token at all — do not revoke anything; just prompt / create path
        is_token_asserted = await self._assert_token(revoke_token=False)
        if not is_token_asserted:
            self.init_complete = False
            return False
        await self.register_manager(ignore_token_checks=True)
        return True

    async def _dp_revoke_token(self: "InlineManager", already_initialised: bool = True):
        """Handle bot auth failure WITHOUT deleting the stored token.

        Losing the token forces painful re-setup. Keep it in DB + backup file;
        only drop the in-memory client and retry with the same token / session.
        """
        logger.error(
            "Inline bot auth issue (polling/token). "
            "Token is KEPT — will retry with same credentials."
        )
        # Drop only runtime state
        self._token = self._db.get("hikkari.inline", "bot_token", None) or self._token
        self.init_complete = False

        # Corrupt bot session is a common cause of AccessTokenInvalid — remove it
        try:
            from .. import main as _main
            import pathlib
            me = getattr(self, "_me", None) or getattr(self._client, "tg_id", None)
            if self._token and me:
                bot_uid = str(self._token).split(":", 1)[0]
                sess = pathlib.Path(_main.SESSIONS_DIR) / f"hikkari-{me}-bot-{bot_uid}"
                for path in (
                    sess,
                    pathlib.Path(str(sess) + ".session"),
                    pathlib.Path(str(sess) + ".session-journal"),
                ):
                    if path.exists():
                        path.unlink(missing_ok=True)
                        logger.info("Removed stale bot session: %s", path)
        except Exception:
            logger.exception("Failed to cleanup bot session files")

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
