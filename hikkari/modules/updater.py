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

import ast
import asyncio
import re
from pathlib import Path
import contextlib
import errno
import json
import logging
import os
import os
import subprocess
import sys
import time
import typing

import aiohttp
import git
from git import GitCommandError, Repo
from hikkaritl.tl.functions.messages import (
    GetDialogFiltersRequest,
    UpdateDialogFilterRequest,
)
from hikkaritl.tl.types import (
    DialogFilter,
    InputBotInlineMessageID,
    InputBotInlineMessageID64,
    Message,
    TextWithEntities,
)

from .. import loader, utils, version
from .._internal import restart
from ..inline.types import BotInlineCall, InlineCall

logger = logging.getLogger(__name__)
NO_GIT = os.environ.get("HEROKU_NO_GIT") == "1"

os.environ["GIT_TERMINAL_PROMPT"] = "0"
os.environ["GIT_ASKPASS"] = "echo"


@loader.tds
class UpdaterMod(loader.Module):
    """Updates itself, tracks latest Hikkari releases, and notifies you, if update is required"""

    strings = {"name": "Updater"}
    _GIT_FETCH_INTERVAL = 60
    _EMFILE_FETCH_BACKOFF = 900

    def __init__(self):
        self._notified = None
        self._last_emfile_warning = 0.0
        self._last_git_fetch = 0.0
        self._git_fetch_backoff_until = 0.0
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "GIT_ORIGIN_URL",
                "https://github.com/Wers1xx/Hikkari",
                lambda: self.strings["origin_cfg_doc"],
                validator=loader.validators.Link(),
            ),
            loader.ConfigValue(
                "disable_notifications",
                doc=lambda: self.strings["_cfg_doc_disable_notifications"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "autoupdate",
                False,
                doc=lambda: self.strings["_cfg_doc_autoupdate"],
                validator=loader.validators.Boolean(),
            ),
        )


    def _repo_dir(self) -> str:
        return os.path.dirname(utils.get_base_dir())

    def _current_branch(self) -> str:
        """Live branch: git HEAD → preferred_branch in DB → version.branch → master."""
        try:
            from .._internal import get_branch_name
            b = get_branch_name(self._repo_dir())
            if b and b not in ("HEAD", "detached"):
                return b
        except Exception:
            pass
        pref = None
        with contextlib.suppress(Exception):
            pref = self.get("preferred_branch")
        if not pref:
            with contextlib.suppress(Exception):
                pref = self._db.get("Updater", "preferred_branch", None)
        if isinstance(pref, str) and pref.strip():
            return pref.strip()
        return getattr(version, "branch", None) or "master"

    def _persist_branch(self, name: str) -> None:
        name = (name or "master").strip()
        with contextlib.suppress(Exception):
            self.set("preferred_branch", name)
        with contextlib.suppress(Exception):
            self._db.set("Updater", "preferred_branch", name)
        with contextlib.suppress(Exception):
            version.branch = name
        # Survive container recreation / code tree resets
        with contextlib.suppress(Exception):
            marker = os.path.join(self._repo_dir(), ".hikkari_branch")
            with open(marker, "w", encoding="utf-8") as f:
                f.write(name)

    def _fetch_branch(self, branch: str | None = None) -> None:
        """Fetch origin/<branch> explicitly (works with single-branch clones)."""
        branch = branch or self._current_branch()
        repo_dir = self._repo_dir()
        try:
            subprocess.run(
                [
                    "git",
                    "fetch",
                    "--quiet",
                    "origin",
                    f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
                ],
                cwd=repo_dir,
                timeout=30,
                capture_output=True,
                check=False,
            )
        except Exception as e:
            logger.debug("fetch branch %s failed: %s", branch, e)
            try:
                subprocess.run(
                    ["git", "fetch", "--quiet", "origin"],
                    cwd=repo_dir,
                    timeout=30,
                    capture_output=True,
                    check=False,
                )
            except Exception as e2:
                logger.debug("fetch origin failed: %s", e2)

    async def _ensure_preferred_branch(self) -> None:
        """If DB says beta but git is on master — re-checkout and keep it."""
        if NO_GIT:
            return
        pref = None
        with contextlib.suppress(Exception):
            pref = self.get("preferred_branch") or self._db.get(
                "Updater", "preferred_branch", None
            )
        if not isinstance(pref, str) or not pref.strip():
            # adopt current git as preferred so it survives
            cur = self._current_branch()
            self._persist_branch(cur)
            return
        pref = pref.strip()
        cur = self._current_branch()
        if cur == pref:
            self._persist_branch(pref)
            return
        logger.warning(
            "Branch drift: git=%s preferred=%s — restoring preferred", cur, pref
        )
        try:
            self._fetch_branch(pref)
            with git.Repo(self._repo_dir()) as repo:
                try:
                    repo.git.checkout("-B", pref, f"origin/{pref}")
                except Exception:
                    if pref in repo.heads:
                        repo.heads[pref].checkout(force=True)
                    else:
                        raise
                with contextlib.suppress(Exception):
                    repo.heads[pref].set_tracking_branch(
                        repo.remotes.origin.refs[pref]
                    )
            self._persist_branch(pref)
            logger.info("Restored branch %s", pref)
        except Exception:
            logger.exception("Failed to restore preferred branch %s", pref)


    async def _set_autoupdate_state(self, call: BotInlineCall, state: bool):
        self.set("autoupdate_answered", True)
        self.config["autoupdate"] = state

        text = (
            self.strings["autoupdate_on"]
            if state
            else self.strings["autoupdate_off"].format(prefix=self.get_prefix())
        )

        await self.inline.bot(call.answer(text, show_alert=True))
        await call.delete()

    @staticmethod
    def _is_emfile_error(error: BaseException) -> bool:
        current: BaseException | None = error
        while current is not None:
            if isinstance(current, OSError) and current.errno in (errno.EMFILE, errno.EAGAIN):
                return True

            current = current.__cause__ or current.__context__

        return False

    def _log_git_poll_error(self, error: Exception):
        if self._is_emfile_error(error):
            now = time.monotonic()
            self._git_fetch_backoff_until = max(
                self._git_fetch_backoff_until,
                now + self._EMFILE_FETCH_BACKOFF,
            )
            if now - self._last_emfile_warning >= 300:
                logger.warning(
                    "Failed to build changelog: too many open files; "
                    "pausing remote fetch attempts"
                )
                self._last_emfile_warning = now
        else:
            logger.exception("Failed to build changelog")

    def _format_changelog(self, commits: list[typing.Any]) -> str:
        entries = []
        for commit in commits[:10]:
            message = commit.message
            if isinstance(message, bytes):
                message = message.decode(errors="replace")

            title = message.splitlines()[0] if message.splitlines() else commit.hexsha
            entries.append(
                f"<b>{commit.hexsha[:7]}</b>:" f" <i>{utils.escape_html(title)}</i>"
            )

        res = "\n".join(entries)

        if len(commits) > 10:
            res += self.strings["more"].format(len(commits) - 10)

        return res

    def _get_update_state(self) -> tuple[str, str, str | typing.Literal[False]]:
        with git.Repo() as repo:
            origin = repo.remote("origin")
            now = time.monotonic()
            if now >= self._git_fetch_backoff_until:
                # First poll always fetches; then every _GIT_FETCH_INTERVAL seconds
                if os.environ.get("HIKKARI_FAST_START") and self._last_git_fetch == 0.0:
                    # Skip blocking fetch right after restart
                    self._last_git_fetch = now
                elif (
                    self._last_git_fetch == 0.0
                    or now - self._last_git_fetch >= self._GIT_FETCH_INTERVAL
                ):
                    br = self._current_branch()
                    logger.debug("Fetching changelog from %s branch=%s", origin.url, br)
                    try:
                        self._fetch_branch(br)
                    except Exception as e:
                        logger.debug("git fetch skipped: %s", e)
                    self._last_git_fetch = now
            else:
                logger.debug(
                    "Skipping changelog fetch for %.0f more seconds after EMFILE",
                    self._git_fetch_backoff_until - now,
                )

            current = repo.head.commit.hexsha
            latest = next(
                repo.iter_commits(f"origin/{self._current_branch()}", max_count=1)
            ).hexsha
            commits = [*repo.iter_commits(f"HEAD..origin/{self._current_branch()}")]

            return (
                current,
                latest,
                self._format_changelog(commits) if commits else False,
            )

    def get_changelog(self) -> str | typing.Literal[False]:
        if NO_GIT:
            return False
        try:
            return self._get_update_state()[2]
        except Exception as e:
            self._log_git_poll_error(e)
            return False

    def get_latest(self) -> str:
        if NO_GIT:
            return ""
        try:
            with git.Repo() as repo:
                return next(
                    repo.iter_commits(f"origin/{self._current_branch()}", max_count=1)
                ).hexsha
        except Exception:
            return ""


    def _inline_bot_ok(self) -> bool:
        """True if inline bot client is ready (token valid + connected)."""
        try:
            bot = getattr(getattr(self, "inline", None), "bot", None)
            return bot is not None
        except Exception:
            return False

    def _bot_api_update_markup(self):
        """Inline keyboard for Bot API send_message (callback_data + optional premium icon)."""
        defs = getattr(self, "_upd_btn_defs", None) or [
            {
                "text": self.strings.get("update", "Update"),
                "data": "hikkari/update",
                "style": "primary",
                "emoji_id": 5258382512656253510,
            },
            {
                "text": self.strings.get("ignore", "Ignore"),
                "data": "hikkari/ignore_upd",
                "style": "danger",
                "emoji_id": 5255949705740843980,
            },
        ]
        # Prefer shared converter if available
        try:
            kb = self.inline.buttons_to_bot_api_keyboard([defs])
            if kb:
                return {"inline_keyboard": kb}
        except Exception:
            pass
        row = []
        for b in defs:
            item = {
                "text": str(b.get("text") or "•"),
                "callback_data": str(b.get("data") or "hikkari/update"),
            }
            if b.get("emoji_id"):
                item["icon_custom_emoji_id"] = str(b["emoji_id"])
            if b.get("style"):
                item["style"] = b["style"]
            row.append(item)
        return {"inline_keyboard": [row]}

    async def _notify_owner(self, text: str, reply_markup=None, **kwargs):
        """Send update notice via inline bot if available, else user client to Saved Messages."""
        disable_preview = kwargs.pop("disable_web_page_preview", True)
        if self._inline_bot_ok():
            try:
                # Ensure Bot API shape
                if callable(reply_markup):
                    reply_markup = reply_markup()
                if reply_markup is not None and not (
                    isinstance(reply_markup, dict) and "inline_keyboard" in reply_markup
                ):
                    try:
                        kb = self.inline.buttons_to_bot_api_keyboard(reply_markup)
                        if kb:
                            reply_markup = {"inline_keyboard": kb}
                    except Exception:
                        reply_markup = self._bot_api_update_markup()
                return await self.inline.bot.send_message(
                    self.tg_id,
                    text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=disable_preview,
                    **kwargs,
                )
            except Exception:
                logger.exception("inline bot notify failed, fallback to client")
        try:
            return await self._client.send_message(
                self.tg_id,
                text,
                link_preview=not disable_preview,
            )
        except Exception:
            logger.exception("owner notify failed")
            return None

    @loader.loop(interval=60, autostart=True)
    async def poller_announcement(self):
        async with aiohttp.ClientSession() as session:
            try:
                url = "https://api.github.com/repos/Wers1xx/assets/contents/hikkari/announcment.txt"
                r = await session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"Accept": "application/vnd.github.v3.raw"},
                )

                match r.status:
                    case 200:
                        announcement = (await r.text()).strip()
                        previous = self.get("announcement", "")
                        if announcement and announcement != previous:
                            await self._notify_owner(
                                self.strings["announcement"].format(announcement),
                            )
                            self.set("announcement", announcement)
                    case _:
                        pass
            except Exception:
                pass

    async def _poll_once(self):
        if NO_GIT:
            return
        try:
            current, self._pending, changelog = self._get_update_state()
        except Exception as e:
            # origin/<branch> may be missing on single-branch clones — fetch and retry
            with contextlib.suppress(Exception):
                self._fetch_branch()
            try:
                current, self._pending, changelog = self._get_update_state()
            except Exception as e2:
                self._log_git_poll_error(e2)
                return

        if (
            self.config["disable_notifications"] and not self.config["autoupdate"]
        ) or not changelog:
            return

        if (
            self.get("ignore_permanent", False)
            and self.get("ignore_permanent") == self._pending
        ):
            await asyncio.sleep(60)
            return

        if self._pending not in {current, self._notified}:
            # Autoupdate removed: only notify, never auto-pull
            m = await self._notify_owner(
                self.strings["update_required"].format(
                    current[:6],
                    '<a href="https://github.com/Wers1xx/Hikkari/compare/{}...{}">{}</a>'.format(
                        current[:12],
                        self._pending[:12],
                        self._pending[:6],
                    ),
                    changelog,
                ),
                reply_markup=self._markup() if self._inline_bot_ok() else None,
                disable_web_page_preview=True,
            )
            if not m:
                return
            self._notified = self._pending
            self.set("ignore_permanent", False)
            await self._delete_all_upd_messages()
            self.set("upd_msg", m.message_id)

    @loader.loop(interval=60, autostart=True)
    async def poller(self):
        await self._poll_once()

    async def _delete_all_upd_messages(self):
        for client in self.allclients:
            with contextlib.suppress(Exception):
                bot = getattr(getattr(client.loader, "inline", None), "bot", None)
                if bot is not None:
                    await bot.delete_message(
                    client.tg_id,
                    client.loader.db.get("Updater", "upd_msg"),
                )

    @loader.callback_handler()
    async def update_call(self, call: InlineCall):
        """Process update buttons in bot PM: download → install → restart."""
        if NO_GIT:
            await call.answer("Git disabled via --no-git.", show_alert=True)
            return
        if call.data not in {"hikkari/update", "hikkari/ignore_upd"}:
            return

        if call.data == "hikkari/ignore_upd":
            self.set("ignore_permanent", self.get_latest())
            with contextlib.suppress(Exception):
                await call.answer(self.strings["latest_disabled"], show_alert=True)
            return

        # Do NOT show restart first and do NOT delete the card before download
        with contextlib.suppress(Exception):
            await call.answer()

        # Keep bot message id for status edits + post-restart success edit
        mid = getattr(call, "message_id", None) or getattr(
            getattr(call, "message", None), "message_id", None
        ) or getattr(getattr(call, "message", None), "id", None)
        if mid is not None:
            self.set("selfupdatemsg", f"bot:{self.tg_id}:{int(mid)}")

        await self.inline_update(call)

    def _recent_commits_changelog(self, limit: int = 15) -> str:
        """Build changelog text from recent git commits (latest updates/fixes)."""
        if NO_GIT:
            return ""
        try:
            with git.Repo() as repo:
                commits = list(repo.iter_commits(version.branch, max_count=limit))
        except Exception:
            try:
                with git.Repo() as repo:
                    commits = list(repo.iter_commits("HEAD", max_count=limit))
            except Exception:
                return ""

        entries = []
        for commit in commits:
            message = commit.message
            if isinstance(message, bytes):
                message = message.decode(errors="replace")
            lines = [ln.strip() for ln in message.strip().splitlines() if ln.strip()]
            if not lines:
                continue
            title = lines[0]
            body = lines[1:]
            block = f"<b>{commit.hexsha[:7]}</b> · <i>{utils.escape_html(title)}</i>"
            if body:
                details = [
                    utils.escape_html(ln.lstrip("- ").strip())
                    for ln in body
                    if not ln.lower().startswith(
                        ("co-authored", "signed-off", "made-with")
                    )
                ]
                if details:
                    block += "\n" + "\n".join(f"  • {d}" for d in details[:8])
            entries.append(block)

        return "\n\n".join(entries)

    @loader.command()
    async def changelog(self, message: Message):
        """Shows what changed in recent updates and fixes"""
        changelog = self._recent_commits_changelog(15)

        if not changelog:
            try:
                with open("CHANGELOG.md", encoding="utf-8") as f:
                    parts = f.read().split("##")
                if len(parts) > 1:
                    changelog = parts[1].strip()
            except Exception:
                changelog = ""

        if not changelog:
            await utils.answer(
                message,
                self.strings.get(
                    "changelog_empty",
                    "✨ <b>Changelog is empty</b>",
                ),
            )
            return

        try:
            ver = ".".join(map(str, version.__version__))
        except Exception:
            ver = "?"
        try:
            build = utils.get_commit_url()
        except Exception:
            build = ""

        body = self.strings["changelog"].format(changelog)
        if build or ver:
            prefix = f"✨ <b>Hikkari</b> <code>v{ver}</code>"
            if build:
                prefix += f" · {build}"
            body = prefix + "\n" + body

        await utils.answer(message, body)

    @loader.command()
    async def restart(self, message: Message):
        args = utils.get_args_raw(message)
        secure_boot = any(trigger in args for trigger in {"--secure-boot", "-sb"})
        try:
            if (
                "-f" in args
                or not self.inline.init_complete
                or not await self.inline.form(
                    message=message,
                    text=self.strings[
                        "secure_boot_confirm" if secure_boot else "restart_confirm"
                    ],
                    reply_markup=[
                        {
                            "text": self.strings["btn_restart"],
                            "callback": self.inline_restart,
                            "args": (secure_boot,),
                            "style": "primary",
                        },
                        {
                            "text": self.strings["cancel"],
                            "action": "close",
                            "style": "danger",
                        },
                    ],
                )
            ):
                raise
        except Exception:
            await self.restart_common(message, secure_boot)

    async def inline_restart(self, call: InlineCall, secure_boot: bool = False):
        await self.restart_common(call, secure_boot=secure_boot)

    @staticmethod
    def _serialize_inline_message_id(
        inline_message_id: str | InputBotInlineMessageID | InputBotInlineMessageID64,
    ) -> str:
        if isinstance(
            inline_message_id,
            (InputBotInlineMessageID, InputBotInlineMessageID64),
        ):
            return typing.cast(str, inline_message_id.to_json())

        return inline_message_id

    @staticmethod
    def _deserialize_inline_message_id(
        inline_message_id: str,
    ) -> str | InputBotInlineMessageID | InputBotInlineMessageID64:
        try:
            data = json.loads(inline_message_id)
        except (TypeError, ValueError):
            return inline_message_id

        if not isinstance(data, dict):
            return inline_message_id

        if data.get("_") == "InputBotInlineMessageID":
            return InputBotInlineMessageID(
                dc_id=data["dc_id"],
                id=data["id"],
                access_hash=data["access_hash"],
            )

        if data.get("_") == "InputBotInlineMessageID64":
            return InputBotInlineMessageID64(
                dc_id=data["dc_id"],
                owner_id=data["owner_id"],
                id=data["id"],
                access_hash=data["access_hash"],
            )

        return inline_message_id

    @staticmethod
    def _parse_legacy_update_message_ref(
        message_ref: typing.Any,
    ) -> tuple[int, int] | None:
        if not isinstance(message_ref, str):
            return None

        parts = message_ref.split(":")
        if len(parts) != 2:
            return None

        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None

    async def process_restart_message(self, msg_obj: InlineCall | Message):
        # Prefer already stored bot: ref from update_call
        existing = self.get("selfupdatemsg")
        if isinstance(existing, str) and existing.startswith("bot:"):
            return
        inline_message_id = getattr(msg_obj, "inline_message_id", None)
        if inline_message_id is not None:
            self.set(
                "selfupdatemsg",
                self._serialize_inline_message_id(inline_message_id),
            )
            return
        chat_id = getattr(msg_obj, "chat_id", None)
        if chat_id is None:
            with contextlib.suppress(Exception):
                chat_id = utils.get_chat_id(msg_obj)
        msg_id = getattr(msg_obj, "message_id", None) or getattr(msg_obj, "id", None)
        is_bot_call = type(msg_obj).__name__ in (
            "BotInlineCall",
            "InlineCall",
            "BotInlineMessage",
            "ChosenInlineCall",
        )
        if is_bot_call and chat_id is not None and msg_id is not None:
            self.set("selfupdatemsg", f"bot:{int(chat_id)}:{int(msg_id)}")
            return
        if chat_id is not None and msg_id is not None:
            self.set("selfupdatemsg", f"{int(chat_id)}:{int(msg_id)}")

    async def restart_common(
        self,
        msg_obj: InlineCall | Message,
        secure_boot: bool = False,
    ):
        if (
            hasattr(msg_obj, "form")
            and isinstance(msg_obj.form, dict)
            and "uid" in msg_obj.form
            and msg_obj.form["uid"] in self.inline._units
            and "message" in self.inline._units[msg_obj.form["uid"]]
        ):
            message = self.inline._units[msg_obj.form["uid"]]["message"]
        else:
            message = msg_obj

        if secure_boot:
            self._db.set(loader.__name__, "secure_boot", True)

        # Never use Rich for restart status (must be editable by user/bot cleanly)
        caption = self.strings["restarting_caption"].format(
            utils.get_platform_emoji()
            if getattr(self._client, "hikkari_me", None)
            and self._client.hikkari_me.premium
            else "Hikkari"
        )
        existing = self.get("selfupdatemsg")
        is_call = type(msg_obj).__name__ in (
            "InlineCall",
            "BotInlineCall",
            "ChosenInlineCall",
            "BotInlineMessage",
        )
        if isinstance(existing, str) and existing.startswith("bot:"):
            # Legacy bot-ref — convert path no longer used for new updates
            pass
        elif isinstance(existing, str) and ":" in existing and not existing.startswith("{"):
            # Owner status message already posted (update button) — keep it
            pass
        elif is_call:
            # Should not post as bot; send owner status if missing
            if not existing:
                peer = getattr(self.inline, "bot_id", None) or self.tg_id
                with contextlib.suppress(Exception):
                    status_msg = await self._client.send_message(peer, caption)
                    if status_msg is not None:
                        self.set(
                            "selfupdatemsg",
                            f"{utils.get_chat_id(status_msg)}:{status_msg.id}",
                        )
        else:
            # User invoked .restart / .update from a chat — edit THAT message only
            new_msg = None
            try:
                new_msg = await utils.answer(msg_obj, caption, skip_rich=True)
            except Exception as e:
                logger.warning("restart caption edit failed (%s)", e)
            if new_msg is not None:
                msg_obj = new_msg
            with contextlib.suppress(Exception):
                await self.process_restart_message(msg_obj)

        self.db.set("Updater", "modules_count", len(self.allmodules.modules))

        self.set("restart_ts", time.time())

        handler = logging.getLogger().handlers[0]
        handler.setLevel(logging.CRITICAL)

        # Resolve user client: BotInlineCall / InlineCall have no .client
        main_client = self._client
        with contextlib.suppress(Exception):
            if hasattr(message, "client") and message.client is not None:
                main_client = message.client
            elif hasattr(msg_obj, "client") and getattr(msg_obj, "client", None):
                main_client = msg_obj.client

        for client in self.allclients:
            # Terminate main loop of all running clients
            if client is not main_client:
                with contextlib.suppress(Exception):
                    await client.disconnect()

        with contextlib.suppress(Exception):
            await main_client.disconnect()
        restart()

    async def download_common(self):
        self._save_pre_update_sha()
        branch = self._current_branch()

        def _sync():
            try:
                with Repo(os.path.dirname(utils.get_base_dir())) as repo:
                    origin = repo.remote("origin")
                    logger.debug("Fetching updates from %s branch=%s", origin.url, branch)
                    try:
                        origin.fetch(
                            refspec=f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
                        )
                    except Exception:
                        origin.fetch()
                    # Stay on preferred branch — never force master
                    try:
                        if branch not in repo.heads:
                            repo.create_head(branch, f"origin/{branch}")
                        repo.heads[branch].checkout(force=True)
                        with contextlib.suppress(Exception):
                            repo.heads[branch].set_tracking_branch(
                                origin.refs[branch]
                            )
                    except Exception as ce:
                        logger.debug("checkout %s before pull: %s", branch, ce)
                    old = repo.head.commit.hexsha
                    try:
                        r = origin.pull(branch)
                    except Exception:
                        repo.git.pull("origin", branch)
                        r = []
                    new_commit = repo.head.commit
                    if new_commit.hexsha != old:
                        try:
                            for d in new_commit.diff(repo.commit(old)):
                                if d.b_path == "requirements.txt":
                                    return True
                        except Exception:
                            pass
                    for info in r or []:
                        if getattr(info, "old_commit", None):
                            for d in new_commit.diff(info.old_commit):
                                if d.b_path == "requirements.txt":
                                    return True
                return False
            except git.exc.InvalidGitRepositoryError:
                repo = Repo.init(os.path.dirname(utils.get_base_dir()))
                with repo:
                    origin = repo.create_remote("origin", self.config["GIT_ORIGIN_URL"])
                    logger.debug("Fetching initial updates from %s", origin.url)
                    br = branch or "master"
                    try:
                        origin.fetch(
                            refspec=f"+refs/heads/{br}:refs/remotes/origin/{br}"
                        )
                    except Exception:
                        origin.fetch()
                    ref = getattr(origin.refs, br, None) or origin.refs.master
                    if br not in repo.heads:
                        repo.create_head(br, ref)
                    repo.heads[br].set_tracking_branch(ref)
                    repo.heads[br].checkout(True)
                return False

        return await asyncio.wait_for(
            asyncio.to_thread(_sync),
            timeout=120,
        )

    @staticmethod
    def req_common():
        # Now we have downloaded new code, install requirements
        logger.debug("Installing new requirements...")
        is_venv = hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix
        )
        # --user breaks installs inside venv (and Docker with VIRTUAL_ENV)
        use_user = (
            not is_venv
            and "VIRTUAL_ENV" not in os.environ
            and "PIP_TARGET" not in os.environ
        )
        req_path = os.path.join(
            os.path.dirname(utils.get_base_dir()),
            "requirements.txt",
        )
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "-q",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--prefer-binary",
            *([] if not use_user else ["--user"]),
            "-r",
            req_path,
        ]
        try:
            r = subprocess.run(
                cmd,
                check=False,
                timeout=600,
                capture_output=True,
            )
            if r.returncode != 0:
                err = ((r.stderr or r.stdout) or b"").decode(errors="ignore")
                logger.error(
                    "Req install failed (rc=%s): %s",
                    r.returncode,
                    err[-1200:] if err else "<no output>",
                )
                # Soft fallback: try critical packages without full freeze
                for pkg in ("sympy", "mpmath", "meval"):
                    with contextlib.suppress(Exception):
                        subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "pip",
                                "install",
                                "-q",
                                "--prefer-binary",
                                *([] if not use_user else ["--user"]),
                                pkg,
                            ],
                            check=False,
                            timeout=180,
                            capture_output=True,
                        )
        except (subprocess.TimeoutExpired, OSError):
            logger.exception("Req install failed")

    @loader.command()
    async def update(self, message: Message):
        if NO_GIT:
            await utils.answer(
                message,
                "<b>Git disabled via --no-git.</b>",
            )
            return
        try:
            args = utils.get_args_raw(message)
            current = utils.get_git_hash() or ""
            with git.Repo() as repo:
                upcoming = next(
                    repo.iter_commits(f"origin/{self._current_branch()}", max_count=1)
                ).hexsha
            if "-f" in args or not self.inline.init_complete:
                await self.inline_update(message)
                return
            form_ok = await self.inline.form(
                message=message,
                text=(
                    self.strings["update_confirm"].format(
                        current, current[:8], upcoming, upcoming[:8]
                    )
                    if upcoming != current
                    else self.strings["no_update"]
                ),
                reply_markup=[
                    {
                        "text": self.strings["btn_update"],
                        "callback": self.inline_update,
                        "style": "primary",
                        "emoji_id": 5258382512656253510,
                    },
                    {
                        "text": self.strings["cancel"],
                        "action": "close",
                        "style": "danger",
                    },
                ],
            )
            if not form_ok:
                tip = "\n\n<code>.update -f</code>"
                body = (
                    self.strings["update_confirm"].format(
                        current, current[:8], upcoming, upcoming[:8]
                    )
                    if upcoming != current
                    else self.strings["no_update"]
                )
                await utils.answer(message, body + tip)
        except Exception:
            logger.exception("update form failed")
            with contextlib.suppress(Exception):
                await utils.answer(
                    message,
                    "Update form failed. Use <code>.update -f</code>",
                )

    @loader.command()
    async def autoupdate(self, message: Message):
        """Autoupdate is disabled — use .update manually"""
        self.config["autoupdate"] = False
        await utils.answer(
            message,
            "\U0001f6ab <b>Autoupdate is disabled</b>\n"
            "Use <code>.update</code> manually.",
        )

    async def _edit_update_status(self, msg_obj, text: str):
        """Edit progress on bot-PM card or owner message."""
        if getattr(self, "inline", None):
            with contextlib.suppress(Exception):
                text = self.inline.sanitise_text(text)
        # Prefer explicit bot:chat:mid ref
        ref = self.get("selfupdatemsg")
        if isinstance(ref, str) and ref.startswith("bot:"):
            parts = ref.split(":")
            if len(parts) == 3:
                try:
                    chat_id, message_id = int(parts[1]), int(parts[2])
                    await self.inline.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        disable_web_page_preview=True,
                    )
                    return msg_obj
                except Exception:
                    logger.debug("bot status edit failed", exc_info=True)
        mid = getattr(msg_obj, "message_id", None) or getattr(msg_obj, "id", None)
        if mid is None:
            m = getattr(msg_obj, "message", None)
            mid = getattr(m, "message_id", None) or getattr(m, "id", None)
        if mid is not None and getattr(self, "inline", None) and getattr(self.inline, "bot", None):
            try:
                await self.inline.bot.edit_message_text(
                    chat_id=self.tg_id,
                    message_id=int(mid),
                    text=text,
                    disable_web_page_preview=True,
                )
                return msg_obj
            except Exception:
                logger.debug("bot edit by mid failed", exc_info=True)
        with contextlib.suppress(Exception):
            return await utils.answer(msg_obj, text, skip_rich=True)
        return msg_obj

    async def inline_update(
        self,
        msg_obj: InlineCall | Message,
        hard: bool = False,
    ):
        # Strict order: download → install requirements → restart (never restart first)
        if hard:
            os.system(f"cd {utils.get_base_dir()} && cd .. && git reset --hard HEAD")

        try:
            msg_obj = await self._edit_update_status(
                msg_obj, self.strings["downloading"]
            )

            try:
                req_update = await self.download_common()
                if self._try_auto_rollback():
                    raise RuntimeError("Hikkari update auto-rollback")
            except TimeoutError:
                logger.exception("Timed out while fetching updates from git remote")
                with contextlib.suppress(Exception):
                    await self._edit_update_status(
                        msg_obj, "❌ <b>Timeout while downloading update</b>"
                    )
                return

            msg_obj = await self._edit_update_status(
                msg_obj, self.strings["installing"]
            )

            if req_update:
                self.req_common()

            await self.restart_common(msg_obj)
        except GitCommandError:
            if not hard:
                await self.inline_update(msg_obj, True)
                return

            logger.critical("Got update loop. Update manually via .terminal")

    # Official beta access list on GitHub (master branch = source of truth)
    _BETA_LIST_URLS = (
        "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/beta_users.txt",
        "https://cdn.jsdelivr.net/gh/Wers1xx/Hikkari@master/assets/beta_users.txt",
    )
    _BETA_CREATOR_ID = 8798148758
    _beta_list_cache: set | None = None
    _beta_list_cache_at: float = 0.0
    _BETA_LIST_TTL = 300.0  # 5 min

    async def _fetch_github_beta_ids(self) -> set[int]:
        """Load beta user IDs from GitHub assets/beta_users.txt."""
        import time as _time
        import aiohttp

        now = _time.time()
        if (
            self._beta_list_cache is not None
            and now - self._beta_list_cache_at < self._BETA_LIST_TTL
        ):
            return self._beta_list_cache

        ids: set[int] = {self._BETA_CREATOR_ID}
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in self._BETA_LIST_URLS:
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        text = await resp.text()
                        for line in text.splitlines():
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            # allow "123456" or "123456  # comment"
                            part = line.split("#", 1)[0].strip().split()[0]
                            if part.isdigit():
                                ids.add(int(part))
                        self._beta_list_cache = ids
                        self._beta_list_cache_at = now
                        logger.info("beta_users list loaded from GitHub (%s ids)", len(ids))
                        return ids
                except Exception as e:
                    logger.warning("beta list fetch %s failed: %s", url, e)
        if len(ids) <= 1:
            try:
                import requests as _req
                for url in self._BETA_LIST_URLS:
                    try:
                        r = await utils.run_sync(_req.get, url, timeout=12)
                        if getattr(r, "status_code", 0) != 200:
                            continue
                        for line in r.text.splitlines():
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            part = line.split("#", 1)[0].strip().split()[0]
                            if part.isdigit():
                                ids.add(int(part))
                        if len(ids) > 1:
                            break
                    except Exception as e:
                        logger.warning("beta list requests %s failed: %s", url, e)
            except Exception:
                logger.debug("beta list requests fallback failed", exc_info=True)
        self._beta_list_cache = ids
        self._beta_list_cache_at = now
        logger.info("beta_users final list size=%s", len(ids))
        return ids

    async def _can_use_beta(self, uid: int, *, force_refresh: bool = False) -> bool:
        """Beta only if Telegram ID is in GitHub assets/beta_users.txt (or creator)."""
        uid = int(uid)
        if uid == self._BETA_CREATOR_ID:
            return True
        # Owners / local cfg do NOT grant beta — only the GitHub list.
        try:
            if force_refresh:
                self._beta_list_cache = None
                self._beta_list_cache_at = 0.0
            gh = await self._fetch_github_beta_ids()
            if uid in gh:
                return True
            logger.info(
                "beta access denied for %s (github list has %s ids)",
                uid,
                len(gh) if gh else 0,
            )
        except Exception:
            logger.exception("github beta check failed — deny by default")
        return False


    @loader.command(
        ru_doc="<master|beta> — переключить ветку обновлений (beta только с доступом)",
        en_doc="<master|beta> — switch update branch (beta requires access)",
    )
    async def branch(self, message: Message):
        """Switch between master and beta branches"""
        args = (utils.get_args_raw(message) or "").strip().lower()
        try:
            uid = message.sender_id if not message.out else self._client.tg_id
        except Exception:
            uid = getattr(self._client, "tg_id", 0)

        if not args:
            cur = getattr(version, "branch", "master")
            await utils.answer(
                message,
                f"<b>Current branch:</b> <code>{cur}</code>\n"
                f"<i>Usage:</i> <code>{utils.escape_html(self.get_prefix())}branch master</code> "
                f"or <code>beta</code>",
            )
            return

        if args not in ("master", "beta", "main"):
            await utils.answer(message, "❌ Use <code>master</code> or <code>beta</code>")
            return
        if args == "main":
            args = "master"

        if args == "beta":
            allowed = await self._can_use_beta(uid, force_refresh=True)
            if not allowed:
                await utils.answer(
                    message,
                    "🚫 <b>Нет доступа к ветке beta</b>\n\n"
                    f"ID: <code>{uid}</code>\n"
                    "Переход на beta разрешён только ID из списка на GitHub:\n"
                    "<code>assets/beta_users.txt</code>\n"
                    '<a href="https://github.com/Wers1xx/Hikkari/blob/master/assets/beta_users.txt">'
                    "Открыть список</a>\n\n"
                    "<i>Если тебя нет в файле — beta недоступна.</i>",
                )
                return

        if NO_GIT:
            await utils.answer(message, "❌ Git disabled")
            return

        try:
            import git as gitmod
            with gitmod.Repo() as repo:
                try:
                    origin = repo.remote("origin")
                except Exception:
                    origin = repo.create_remote(
                        "origin",
                        self.config.get("GIT_ORIGIN_URL")
                        or "https://github.com/Wers1xx/Hikkari",
                    )
                # Single-branch clones never have origin/beta — fetch it explicitly
                for attempt in (
                    lambda: origin.fetch(
                        refspec=f"+refs/heads/{args}:refs/remotes/origin/{args}"
                    ),
                    lambda: repo.git.fetch(
                        "origin",
                        f"+refs/heads/{args}:refs/remotes/origin/{args}",
                    ),
                    lambda: repo.git.fetch("origin", args),
                    lambda: origin.fetch(),
                ):
                    try:
                        attempt()
                        break
                    except Exception as fe:
                        logger.debug("branch fetch attempt failed: %s", fe)

                remote_has = False
                try:
                    for ref in list(origin.refs):
                        name = str(
                            getattr(ref, "remote_head", None)
                            or getattr(ref, "name", "")
                            or ""
                        )
                        if name == args or name.endswith("/" + args):
                            remote_has = True
                            break
                except Exception:
                    pass
                if not remote_has:
                    try:
                        for r in repo.refs:
                            n = str(getattr(r, "name", "") or "")
                            if n.endswith("/" + args) or n == "origin/" + args:
                                remote_has = True
                                break
                    except Exception:
                        pass
                if not remote_has:
                    try:
                        out = repo.git.ls_remote("--heads", "origin", args)
                        remote_has = bool(out and args in out)
                    except Exception as e:
                        logger.warning("ls-remote failed: %s", e)
                if not remote_has:
                    await utils.answer(
                        message,
                        f"❌ Remote branch <code>{args}</code> not found on origin\n"
                        f"<i>Проверь:</i> <code>git ls-remote --heads origin</code>",
                    )
                    return

                try:
                    repo.git.checkout("-B", args, f"origin/{args}")
                except Exception:
                    if args in repo.heads:
                        repo.heads[args].checkout(force=True)
                    else:
                        target = None
                        for r in repo.refs:
                            n = str(getattr(r, "name", "") or "")
                            if n.endswith("/" + args):
                                target = r
                                break
                        if target is None:
                            raise RuntimeError(
                                f"no local ref for {args} after fetch"
                            )
                        repo.create_head(args, target).checkout()
                # Pin upstream so future pulls/polls stay on this branch
                with contextlib.suppress(Exception):
                    repo.heads[args].set_tracking_branch(
                        repo.remotes.origin.refs[args]
                    )
                try:
                    repo.git.pull("origin", args)
                except Exception as pe:
                    logger.debug("pull after branch switch: %s", pe)

            self._persist_branch(args)
            await utils.answer(
                message,
                f"✅ Switched to <code>{args}</code>\n"
                f"Restarting to apply…",
            )
            try:
                await self.invoke("restart", "-f", peer=utils.get_chat_id(message))
            except Exception:
                from .. import version as _v
                _v.restart()
        except Exception as e:
            logger.exception("branch switch failed")
            await utils.answer(
                message,
                f"❌ Branch switch failed: <code>{utils.escape_html(str(e))}</code>",
            )


    @loader.command(
        ru_doc="— показать список beta-доступа (GitHub)",
        en_doc="— show beta access list (GitHub)",
    )
    async def betalist(self, message: Message):
        """Show who can use the beta branch (from GitHub)"""
        ids = await self._fetch_github_beta_ids()
        lines = [
            "<b>✨ Beta access</b>",
            "",
            "<b>GitHub</b> <code>assets/beta_users.txt</code>:",
        ]
        for i in sorted(ids):
            mark = " (creator)" if i == self._BETA_CREATOR_ID else ""
            lines.append(f"• <code>{i}</code>{mark}")
        lines.append("")
        lines.append(
            '<a href="https://github.com/Wers1xx/Hikkari/blob/master/assets/beta_users.txt">'
            "Edit list on GitHub</a>"
        )
        await utils.answer(message, "\n".join(lines))

    @loader.command(
        ru_doc="<id|reply> — локально добавить beta (основной список на GitHub)",
        en_doc="<id|reply> — local beta grant (main list is on GitHub)",
    )
    async def betagrant(self, message: Message):
        """Beta list is GitHub-only — no local config."""
        await utils.answer(
            message,
            "🚫 <b>Local beta_users config removed</b>\n\n"
            "Edit on GitHub:\n"
            "<code>assets/beta_users.txt</code>\n"
            '<a href="https://github.com/Wers1xx/Hikkari/blob/master/assets/beta_users.txt">'
            "open file</a>",
        )


    async def betarevoke(self, message: Message):
        """Beta list is GitHub-only — no local config."""
        await utils.answer(
            message,
            "🚫 <b>Local beta_users config removed</b>\n\n"
            "Remove ID on GitHub:\n"
            "<code>assets/beta_users.txt</code>",
        )



    async def source(self, message: Message):
        await utils.answer(
            message,
            self.strings["source"].format(self.config["GIT_ORIGIN_URL"]),
        )

    async def client_ready(self):
        if not getattr(self, "inline", None) or not getattr(self.inline, "bot", None):
            return
        try:
            with git.Repo():
                pass
        except Exception as e:
            raise loader.LoadError("Can't load due to repo init error") from e

        if not self.get("autoupdate_answered"):
            self.set("autoupdate_answered", self.get("autoupdate", False))

        # Bot API keyboard (send_message via inline bot). TL generate_markup is wrong here.
        self._upd_btn_defs = [
            {
                "text": self.strings["update"],
                "data": "hikkari/update",
                "style": "primary",
                "emoji_id": 5258382512656253510,
            },
            {
                "text": self.strings["ignore"],
                "data": "hikkari/ignore_upd",
                "style": "danger",
                "emoji_id": 5255949705740843980,
            },
        ]
        self._markup = self._bot_api_update_markup

        if self.get("selfupdatemsg") is not None:
            try:
                await self.update_complete()
            except Exception:
                logger.exception("Failed to complete update!")

        if self.get("do_not_create", False):
            pass
        else:
            try:
                await self._add_folder()
            except Exception:
                logger.exception("Failed to add folder!")

            self.set("do_not_create", True)

        # Autoupdate disabled by design — no startup prompt
        self.config["autoupdate"] = False
        self.set("autoupdate_answered", True)

        rb = Path.cwd() / ".hikkari_update_rolled_back"
        if rb.is_file():
            with contextlib.suppress(Exception):
                old = rb.read_text(encoding="utf-8").strip()
                rb.unlink(missing_ok=True)
                self._clear_pre_update()
                await self._notify_owner(
                    self.strings.get(
                        "update_auto_rollback",
                        "⚠️ <b>Update broke startup and was rolled back</b> to <code>{sha}</code>.",
                    ).format(sha=(old or "?")[:7]),
                )
        else:
            with contextlib.suppress(Exception):
                self._clear_pre_update()

        # Preferred branch + immediate update notify in bot PM
        with contextlib.suppress(Exception):
            await self._ensure_preferred_branch()

        async def _boot_check():
            await asyncio.sleep(4)
            with contextlib.suppress(Exception):
                self._fetch_branch()
            with contextlib.suppress(Exception):
                await self._poll_once()

        asyncio.ensure_future(_boot_check())

    async def _add_folder(self):
        folders = await self._client(GetDialogFiltersRequest())

        try:
            folder_id = (
                max(
                    (folder for folder in folders.filters if hasattr(folder, "id")),
                    key=lambda x: x.id,
                ).id
                + 1
            )
        except ValueError:
            folder_id = 2

        folders = await self._client(GetDialogFiltersRequest())
        filters = getattr(folders, "filters", folders)
        hikkari_f = False

        if filters:

            for folder in filters:
                title = getattr(folder, "title", None)

                if title:
                    raw_title = getattr(title, "text", title)

                    if str(raw_title).strip() == "Hikkari":
                        hikkari_f = True

        if hikkari_f is True:
            return
        else:
            try:
                await self._client(
                    UpdateDialogFilterRequest(
                        folder_id,
                        DialogFilter(
                            folder_id,
                            title=TextWithEntities(text="Hikkari", entities=[]),
                            pinned_peers=(
                                [
                                    await self._client.get_input_entity(
                                        self._client.loader.inline.bot_id
                                    )
                                ]
                                if self._client.loader.inline.init_complete
                                else []
                            ),
                            include_peers=[
                                await self._client.get_input_entity(dialog.entity)
                                async for dialog in self._client.iter_dialogs(
                                    None,
                                    ignore_migrated=True,
                                )
                                if "hikkari" in dialog.name
                                or "Hikkari" in dialog.name
                                and dialog.is_channel
                                or (
                                    self._client.loader.inline.init_complete
                                    and dialog.entity.id
                                    == self._client.loader.inline.bot_id
                                )
                                or dialog.entity.id
                                in [
                                    2445389036,
                                    2341345589,
                                    2410964167,
                                ]  # official hikkari chats
                            ],
                            emoticon="🐱",
                            exclude_peers=[],
                            contacts=False,
                            non_contacts=False,
                            groups=False,
                            broadcasts=False,
                            bots=False,
                            exclude_muted=False,
                            exclude_read=False,
                            exclude_archived=False,
                        ),
                    )
                )
            except Exception:
                logger.critical(
                    "Can't create Hikkari folder. Possible reasons are:\n"
                    "- User reached the limit of folders in Telegram\n"
                    "- User got floodwait\n"
                    "Ignoring error and adding folder addition to ignore list\n",
                    exc_info=True,
                )


    async def _schedule_delete_status(
        self,
        *,
        chat_id: int | None = None,
        message_id: int | None = None,
        ms: str | None = None,
        delay: int = 60,
        via_bot: bool = False,
    ):
        """Delete restart status message after delay (default 60s)."""

        async def _later():
            await asyncio.sleep(max(5, int(delay)))
            try:
                if via_bot and chat_id is not None and message_id is not None:
                    with contextlib.suppress(Exception):
                        await self.inline.bot.delete_message(chat_id, message_id)
                    return
                if chat_id is not None and message_id is not None:
                    with contextlib.suppress(Exception):
                        await self._client.delete_messages(chat_id, message_id)
                    return
                if ms and not str(ms).startswith("bot:"):
                    with contextlib.suppress(Exception):
                        await self.inline.bot.delete_message(
                            inline_message_id=self._deserialize_inline_message_id(str(ms))
                        )
            except Exception:
                logger.debug("status auto-delete failed", exc_info=True)

        with contextlib.suppress(Exception):
            asyncio.ensure_future(_later())

    async def _edit_restart_status(
        self,
        ms,
        msg: str,
        *,
        delete_after: int | None = None,
    ) -> bool:
        """Edit restart status message. bot:chat:id → bot API only (no Saved Messages).

        If delete_after is set (seconds), schedule deletion of that status message.
        """
        if not ms:
            return False
        text = self.inline.sanitise_text(msg) if getattr(self, "inline", None) else msg
        # bot PM message owned by inline bot
        if isinstance(ms, str) and ms.startswith("bot:"):
            try:
                _, chat_s, msg_s = ms.split(":", 2)
                chat_id, message_id = int(chat_s), int(msg_s)
            except Exception:
                return False
            ok = False
            try:
                await self.inline.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                )
                ok = True
            except Exception as e:
                logger.warning("bot PM status edit failed (%s)", e)
                with contextlib.suppress(Exception):
                    sent = await self.inline.bot.send_message(chat_id, text)
                    # if we had to send new, delete that one later
                    if delete_after and sent is not None:
                        mid = getattr(sent, "id", None) or getattr(sent, "message_id", None)
                        if mid is not None:
                            await self._schedule_delete_status(
                                chat_id=chat_id,
                                message_id=int(mid),
                                delay=delete_after,
                                via_bot=True,
                            )
                    return True
            if ok and delete_after:
                await self._schedule_delete_status(
                    chat_id=chat_id,
                    message_id=message_id,
                    delay=delete_after,
                    via_bot=True,
                )
            return ok
        # legacy chat:message from userbot-owned message (e.g. .restart command)
        if legacy := self._parse_legacy_update_message_ref(ms):
            chat_id, message_id = legacy
            try:
                await self._client.edit_message(chat_id, message_id, msg)
                if delete_after:
                    await self._schedule_delete_status(
                        chat_id=chat_id,
                        message_id=message_id,
                        delay=delete_after,
                        via_bot=False,
                    )
                return True
            except Exception as e:
                logger.warning("legacy status edit failed (%s)", e)
                return False
        # inline_message_id JSON / raw
        try:
            await self.inline.bot.edit_message_text(
                inline_message_id=self._deserialize_inline_message_id(str(ms)),
                text=text,
            )
            if delete_after:
                await self._schedule_delete_status(ms=str(ms), delay=delete_after)
            return True
        except Exception:
            logger.debug("inline_message_id status edit failed", exc_info=True)
            return False

    async def update_complete(self):
        logger.debug("Self update successful! Edit message")
        start = self.get("restart_ts")
        try:
            took = round(time.time() - start)
        except Exception:
            took = "n/a"

        msg = self.strings["success"].format(utils.ascii_face(), took)
        ms = self.get("selfupdatemsg")
        # Do NOT clear here — full_restart_complete still needs the same ref
        await self._edit_restart_status(ms, msg)

    async def full_restart_complete(self, secure_boot: bool = False):
        start = self.get("restart_ts")

        try:
            took = round(time.time() - start)
        except Exception:
            took = "n/a"

        self.set("restart_ts", None)
        ms = self.get("selfupdatemsg")

        # Only REAL register_all failures. modules_count delta is a false
        # positive (update, soft client_ready, etc.) and must not show as error.
        failed_names = list(
            getattr(self.allmodules, "_failed_module_names", None) or []
        )
        if failed_names:
            fails = len(failed_names)
            msg = self.strings[
                "secure_boot_fail" if secure_boot else "full_fail"
            ].format(utils.ascii_face(), took, fails)
            short = []
            for n in failed_names[:5]:
                n = str(n).replace("\\", "/").rsplit("/", 1)[-1]
                short.append(f"<code>{utils.escape_html(n)}</code>")
            msg += "\n" + ", ".join(short)
            if len(failed_names) > 5:
                msg += f" (+{len(failed_names) - 5})"
        else:
            msg = self.strings[
                "secure_boot_complete" if secure_boot else "full_success"
            ].format(utils.ascii_face(), took)

        if ms is None:
            return

        self.set("selfupdatemsg", None)
        # Keep modules_count in sync so next restart does not false-fail
        with contextlib.suppress(Exception):
            self.db.set("Updater", "modules_count", len(self.allmodules.modules))

        # ONLY edit the original restart message (bot PM or user .restart msg).
        # Never spam Saved Messages. Auto-delete after 60s (as before).
        await self._edit_restart_status(ms, msg, delete_after=60)

    def _find_commit_for_version(self, ver: str) -> str | None:
        """Find newest commit where version.py matches X.Y.Z"""
        if NO_GIT:
            return None
        try:
            import git as _git
            with _git.Repo() as repo:
                for commit in repo.iter_commits(max_count=400):
                    try:
                        blob = commit.tree / "hikkari" / "version.py"
                        data = blob.data_stream.read().decode("utf-8", errors="ignore")
                        m = re.search(r"__version__\s*=\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)", data)
                        if not m:
                            continue
                        found = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
                        if found == ver:
                            return commit.hexsha
                    except Exception:
                        continue
        except Exception:
            logger.exception("find version commit")
        return None


    def _save_pre_update_sha(self) -> str | None:
        if NO_GIT:
            return None
        try:
            import git as _git
            with _git.Repo() as repo:
                sha = repo.head.commit.hexsha
            marker = Path.cwd() / ".hikkari_pre_update"
            marker.write_text(sha, encoding="utf-8")
            return sha
        except Exception:
            logger.exception("save pre-update sha")
            return None

    def _try_auto_rollback(self) -> bool:
        """If current tree fails import test, reset to .hikkari_pre_update."""
        marker = Path.cwd() / ".hikkari_pre_update"
        if not marker.is_file():
            return False
        try:
            old = marker.read_text(encoding="utf-8").strip()
            if not old:
                return False
            # quick syntax check of core package
            import py_compile, sys
            core = Path.cwd() / "hikkari" / "__main__.py"
            try:
                py_compile.compile(str(core), doraise=True)
                # also version + main
                py_compile.compile(str(Path.cwd() / "hikkari" / "main.py"), doraise=True)
            except Exception as e:
                logger.error("Update broke boot (%s) — rolling back to %s", e, old[:7])
                import subprocess
                subprocess.run(["git", "reset", "--hard", old], check=False)
                fail_flag = Path.cwd() / ".hikkari_update_rolled_back"
                fail_flag.write_text(old, encoding="utf-8")
                return True
        except Exception:
            logger.exception("auto-rollback")
        return False

    def _clear_pre_update(self):
        for name in (".hikkari_pre_update",):
            with contextlib.suppress(Exception):
                (Path.cwd() / name).unlink(missing_ok=True)


    @loader.command()
    async def rollback(self, message: Message):
        """[N | X.Y.Z] — откат на N коммитов назад или к версии X.Y.Z"""
        args = (utils.get_args_raw(message) or "").strip()
        if not args:
            await utils.answer(message, self.strings["invalid_args"])
            return

        target = None  # ("commits", n) or ("sha", sha, label)
        if re.fullmatch(r"\d+\.\d+\.\d+", args):
            sha = self._find_commit_for_version(args)
            if not sha:
                await utils.answer(
                    message,
                    self.strings.get(
                        "rollback_version_not_found",
                        f"🚫 <b>Version</b> <code>{args}</code> <b>not found in git history</b>",
                    ),
                )
                return
            target = ("sha", sha, args)
            confirm = self.strings.get(
                "rollback_confirm_ver",
                "⚠️ <b>Rollback to version</b> <code>{ver}</code> (<code>{sha}</code>)?",
            ).format(ver=args, sha=sha[:7])
        elif args.isdigit():
            n = int(args)
            if n < 1 or n > 50:
                await utils.answer(message, self.strings["rollback_too_far"])
                return
            target = ("commits", n, str(n))
            confirm = self.strings["rollback_confirm"].format(num=n)
        else:
            await utils.answer(message, self.strings["invalid_args"])
            return

        await self.inline.form(
            message=message,
            text=confirm,
            reply_markup=[
                [
                    {
                        "text": "✅",
                        "callback": self.rollback_confirm,
                        "args": [target[0], target[1], target[2]],
                        "style": "success",
                        "emoji_id": 5206607081334906820,
                    }
                ],
                [{"text": "❌", "action": "close", "style": "danger", "emoji_id": 5210952531676504517}],
            ],
        )

    async def rollback_confirm(self, call: InlineCall, mode: str, value, label: str):
        await utils.answer(
            call,
            self.strings.get("rollback_process", "⏳ Rollback…").format(num=label),
        )
        utils.ensure_child_watcher()
        if mode == "commits":
            cmd = f"git reset --hard HEAD~{int(value)}"
        else:
            cmd = f"git reset --hard {value}"
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        await self.restart_common(call)

    async def ubstop_func(self, call: Message | InlineCall):
        await utils.answer(
            call,
            self.strings["ub_stop"].format(emoji=utils.get_platform_emoji()),
        )

        exit()

    @loader.command()
    async def ubstop(self, message: Message):
        """| stops your userbot"""

        args = utils.get_args(message)
        if "-f" in args or "--force" in args:
            await self.ubstop_func(message)
            return

        await self.inline.form(
            message=message,
            text=self.strings["stop_ub_confirm"].format(
                utils.get_platform_emoji()
                if self.client.hikkari_me.premium
                else "Hikkari"
            ),
            reply_markup=[
                [
                    {
                        "text": "✅",
                        "callback": self.ubstop_func,
                        "style": "primary",
                    },
                ],
                [{"text": "❌", "action": "close", "style": "primary"}],
            ],
            silent=True,
        )
