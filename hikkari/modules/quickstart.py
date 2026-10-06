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

import logging

from .. import loader, translations, utils
from ..inline.types import BotInlineCall

logger = logging.getLogger(__name__)


@loader.tds
class Quickstart(loader.Module):
    """Notifies user about userbot installation"""

    strings = {"name": "Quickstart"}

    async def client_ready(self):
        if not getattr(self, "inline", None) or not getattr(self.inline, "bot", None):
            return
        self.text = lambda: self.strings["base"].format(
            utils.get_platform_emoji()
            if self.client.hikkari_me.premium is True
            else "Hikkari"
        )

        try:
            content_channel = None
            existing_channel_id = self.db.get("hikkari.forums", "channel_id", None)

            if existing_channel_id:
                try:
                    content_channel = await self.client.get_entity(existing_channel_id)
                    logger.debug(
                        "Found existing content channel with ID %s",
                        existing_channel_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Saved channel ID %s not found or inaccessible: %s",
                        existing_channel_id,
                        e,
                    )
                    content_channel = None
                    self.db.set(
                        "hikkari.forums", "forums_cache", {"hikkari-userbot": {}}
                    )

            if not content_channel:
                async for dialog in self.client.iter_dialogs():
                    if dialog.title and "hikkari-userbot" in dialog.title.lower():
                        content_channel = dialog.entity
                        logger.debug(
                            "Found existing channel '%s' with ID %s",
                            dialog.title,
                            dialog.entity.id,
                        )
                        self.db.set(
                            "hikkari.forums", "channel_id", int(dialog.entity.id)
                        )
                        break

            if not content_channel:
                content_channel = await self.db.ensure_content_channel()

            if not content_channel:
                logger.warning(
                    "Content channel unavailable (spam ban / restricted). "
                    "Assets/logs/backups channel features limited. "
                    "Use .ch_bot_token for inline if needed."
                )
            else:
                forum_entity = None
                existing_forum_id = self.db.get("hikkari.forums", "forum_id", None)

                if existing_forum_id:
                    try:
                        forum_entity = await self.client.get_entity(existing_forum_id)
                    except Exception:
                        forum_entity = None

                if not forum_entity:
                    try:
                        if not (
                            hasattr(content_channel, "forum")
                            or not content_channel.forum
                        ):
                            from hikkaritl.tl.functions.channels import ToggleForumRequest

                            try:
                                await self.client(
                                    ToggleForumRequest(
                                        channel=content_channel,
                                        enabled=True,
                                    )
                                )
                            except Exception as e:
                                logger.debug(
                                    "Channel might already be a forum or conversion failed: %s",
                                    e,
                                )

                        forum_entity = content_channel
                        self.db.set(
                            "hikkari.forums", "forum_id", int(content_channel.id)
                        )
                    except Exception:
                        forum_entity = content_channel

                required_topics = [
                    (
                        "Assets",
                        "🌆 Your Hikkari assets will be stored here",
                        5877307202888273539,
                    ),
                    (
                        "Backups",
                        "💾 Your Hikkari backups will be stored here",
                        5877307202888273539,
                    ),
                ]

                for topic_title, topic_desc, emoji_id in required_topics:
                    try:
                        await utils.asset_forum_topic(
                            client=self.client,
                            db=self.db,
                            peer=forum_entity.id
                            if forum_entity
                            else content_channel.id,
                            title=topic_title,
                            description=topic_desc,
                            icon_emoji_id=emoji_id,
                        )
                        logger.debug("Created or verified topic '%s'", topic_title)
                    except Exception:
                        logger.exception(
                            "Failed to create/verify topic '%s'", topic_title
                        )

                try:
                    await utils.invite_inline_bot(self.client, content_channel)
                except Exception:
                    logger.warning(
                        "invite_inline_bot failed (non-fatal)", exc_info=True
                    )

        except Exception:
            logger.exception(
                "Can't find and/or create content channel "
                "(spam ban / restricted). Userbot continues; "
                "use .ch_bot_token for inline bot."
            )

        await self.request_join(
            "hikkari_talks",
            "Hikkari news and updates. By joining you agree to community rules.",
        )

        self.mark = lambda: [
            [
                {
                    "text": self.strings["btn_support"],
                    "url": "https://t.me/Hikkari_talks",
                }
            ],
        ] + utils.chunks(
            [
                {
                    "text": self.strings.get("language", lang),
                    "data": f"hikkari/lang/{lang}",
                }
                for lang in translations.SUPPORTED_LANGUAGES
            ],
            3,
        )

        if self.get("no_msg"):
            return

        await self.inline.bot.send_message(
            self._client.tg_id,
            self.text(),
            reply_markup=self.inline.generate_markup(self.mark()),
            disable_web_page_preview=True,
        )

        self.set("no_msg", True)

    @loader.callback_handler()
    async def lang(self, call: BotInlineCall):
        if not call.data.startswith("hikkari/lang/"):
            return

        lang = call.data.split("/")[2]

        self._db.set(translations.__name__, "lang", lang)
        await self.allmodules.reload_translations()

        await self.inline.bot(call.answer(self.strings["language_saved"]))
        await call.edit(text=self.text(), reply_markup=self.mark())
