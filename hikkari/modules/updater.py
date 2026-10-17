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

    def _strip_btn_emoji(self, text: str) -> str:
        """Remove leading unicode emoji so only premium icon_custom_emoji shows."""
        import re as _re
        if not text:
            return text
        # strip leading emoji + spaces
        return _re.sub(
            r"^[\s\W]*?(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]+\s*)+",
            "",
            str(text),
            count=1,
        ).strip() or str(text)

    def _update_markup_rows(self, *, for_bot_api: bool = False):
        """Update/Ignore buttons with premium emoji (no unicode in text)."""
        defs = getattr(self, "_upd_btn_defs", None)
        if not defs:
            defs = [
                {
                    "text": "Обновить",
                    "data": "hikkari/update",
                    "style": "primary",
                    "emoji_id": 5258382512656253510,
                },
                {
                    "text": "Игнорировать",
                    "data": "hikkari/ignore_upd",
                    "style": "danger",
                    "emoji_id": 5255949705740843980,
                },
            ]
        rows = []
        row = []
        for d in defs:
            text = self._strip_btn_emoji(
                d.get("text") or self.strings.get("update", "Update")
            )
            # Prefer strings if present but still strip unicode
            if d.get("data") == "hikkari/update":
                text = self._strip_btn_emoji(self.strings.get("update", text)) or "Обновить"
            elif d.get("data") == "hikkari/ignore_upd":
                text = self._strip_btn_emoji(self.strings.get("ignore", text)) or "Игнорировать"
            eid = d.get("emoji_id") or d.get("icon_custom_emoji_id") or d.get("icon")
            if for_bot_api:
                item = {
                    "text": text,
                    "callback_data": d.get("data") or d.get("callback_data") or "noop",
                }
                if eid:
                    item["icon_custom_emoji_id"] = str(eid)
                # style via Bot API not standard; omit
                row.append(item)
            else:
                item = {
                    "text": text,
                    "data": d.get("data"),
                    "style": d.get("style"),
                }
                if eid:
                    item["emoji_id"] = int(eid) if str(eid).isdigit() else eid
                row.append(item)
        return [row]

    async def _notify_owner(self, text: str, reply_markup=None, **kwargs):
        """Send update notice via inline bot if available, else user client to Saved Messages."""
        disable_preview = kwargs.pop("disable_web_page_preview", True)
        if callable(reply_markup):
            reply_markup = reply_markup()
        if self._inline_bot_ok():
            # 1) Prefer HTTP Bot API — real icon_custom_emoji_id on buttons
            try:
                token = None
                with contextlib.suppress(Exception):
                    token = getattr(self.inline, "token", None) or getattr(
                        self.inline, "_token", None
                    )
                if not token:
                    with contextlib.suppress(Exception):
                        token = self._db.get("hikka.inline", "bot_token") or self._db.get(
                            "hikkari.inline", "bot_token"
                        )
                if token:
                    import aiohttp
                    bot_rows = self._update_markup_rows(for_bot_api=True)
                    payload = {
                        "chat_id": int(self.tg_id),
                        "text": self._for_bot_api_html(text),
                        "parse_mode": "HTML",
                        "disable_web_page_preview": bool(disable_preview),
                        "reply_markup": {"inline_keyboard": bot_rows},
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=20),
                        ) as resp:
                            data = await resp.json()
                            if data.get("ok"):
                                return data.get("result")
                            logger.warning("Bot API notify failed: %s", data)
            except Exception:
                logger.debug("Bot API notify path failed", exc_info=True)

            try:
                # TelethonBot expects list-of-rows of dicts / Button
                if reply_markup is None:
                    reply_markup = self._update_markup_rows(for_bot_api=False)
                elif isinstance(reply_markup, dict) and "inline_keyboard" in reply_markup:
                    reply_markup = reply_markup.get("inline_keyboard") or self._update_markup_rows()
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
            # User-client fallback: no bot buttons
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

        # Pin bot-PM notification message for status chain
        mid = getattr(call, "message_id", None) or getattr(
            getattr(call, "message", None), "message_id", None
        ) or getattr(getattr(call, "message", None), "id", None)
        if mid is not None:
            self.set("selfupdatemsg", f"bot:{int(self.tg_id)}:{int(mid)}")
        # Pre-seed capture so installing/restart edits hit this card
        try:
            self._status_seed = {
                "chat_id": int(self.tg_id),
                "message_id": int(mid) if mid is not None else None,
                "inline_message_id": getattr(call, "inline_message_id", None),
                "via_bot": True,
            }
        except Exception:
            self._status_seed = None

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
        """Parse chat:mid | msg:chat:mid | bot:chat:mid → (chat_id, message_id)."""
        if not isinstance(message_ref, str):
            return None
        s = message_ref.strip()
        if s.startswith("imid:"):
            return None
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
            if len(parts) == 3 and parts[0] in {"msg", "bot"}:
                return int(parts[1]), int(parts[2])
        except ValueError:
            return None
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
        _status_target: dict | None = None,
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

        # Always show restart caption on the SAME status message (chat form or bot PM)
        caption = self.strings["restarting_caption"].format(
            utils.get_platform_emoji()
            if getattr(self._client, "hikkari_me", None)
            and getattr(self._client.hikkari_me, "premium", False)
            else "Hikkari"
        )
        target = _status_target or self._capture_status_target(msg_obj)
        try:
            await self._edit_update_status(msg_obj, caption, target=target)
        except Exception:
            logger.exception("restart caption edit failed")

        # ALWAYS also pin a bot-PM status message we can edit after boot (HTTP)
        owner = int(self.tg_id)
        bot_mid = None
        # Prefer editing existing bot: ref
        ref_now = None
        with contextlib.suppress(Exception):
            if target.get("via_bot") and target.get("chat_id") and target.get("message_id"):
                if int(target["chat_id"]) == owner:
                    ok = await self._http_bot_edit(owner, int(target["message_id"]), caption)
                    if ok:
                        bot_mid = int(target["message_id"])
        if bot_mid is None:
            # try load previous
            old_ref = self._load_status_ref()
            if isinstance(old_ref, str) and old_ref.startswith("bot:"):
                with contextlib.suppress(Exception):
                    _, c, m = old_ref.split(":", 2)
                    if int(c) == owner:
                        ok = await self._http_bot_edit(owner, int(m), caption)
                        if ok:
                            bot_mid = int(m)
        if bot_mid is None:
            bot_mid = await self._http_bot_send(owner, caption)
        if bot_mid is not None:
            target = {
                "chat_id": owner,
                "message_id": int(bot_mid),
                "via_bot": True,
                "inline_message_id": None,
            }
        self._persist_status_target(target)
        await asyncio.sleep(0.4)

        self.db.set("Updater", "modules_count", len(self.allmodules.modules))
        ts = time.time()
        self.set("restart_ts", ts)
        with contextlib.suppress(Exception):
            self._db.set("Updater", "restart_ts", ts)
            self._db.set("UpdaterMod", "restart_ts", ts)
        with contextlib.suppress(Exception):
            self._db.save()
        with contextlib.suppress(Exception):
            import time as _t
            _t.sleep(0.05)
            self._db.save()

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

    def _capture_status_target(self, msg_obj) -> dict:
        """Resolve chat/message/inline ids for reliable status edits."""
        seed = getattr(self, "_status_seed", None)
        if isinstance(seed, dict) and (seed.get("message_id") or seed.get("inline_message_id")):
            self._status_seed = None
            return dict(seed)
        target = {"chat_id": None, "message_id": None, "inline_message_id": None, "via_bot": False}
        try:
            # Bot API callback (notification in bot PM / inline)
            imid = getattr(msg_obj, "inline_message_id", None)
            if imid:
                target["inline_message_id"] = str(imid)
                target["via_bot"] = True
            # form unit message
            form = getattr(msg_obj, "form", None)
            if isinstance(form, dict) and form.get("uid") and getattr(self, "inline", None):
                unit = self.inline._units.get(form["uid"]) or {}
                m = unit.get("message")
                if m is not None:
                    target["chat_id"] = utils.get_chat_id(m)
                    target["message_id"] = getattr(m, "id", None) or getattr(m, "message_id", None)
                if unit.get("inline_message_id"):
                    target["inline_message_id"] = str(unit["inline_message_id"])
                    target["via_bot"] = True
            # plain Message
            from hikkaritl.tl.types import Message as _Msg
            if isinstance(msg_obj, _Msg):
                target["chat_id"] = utils.get_chat_id(msg_obj)
                target["message_id"] = msg_obj.id
            # BotInlineCall / call.message
            call_msg = getattr(msg_obj, "message", None)
            if call_msg is not None and target["message_id"] is None:
                mid = getattr(call_msg, "id", None) or getattr(call_msg, "message_id", None)
                if mid is not None:
                    target["message_id"] = mid
                cid = getattr(call_msg, "chat", None)
                if cid is not None and hasattr(cid, "id"):
                    target["chat_id"] = cid.id
                elif getattr(msg_obj, "chat_id", None):
                    target["chat_id"] = int(msg_obj.chat_id)
            # sender for bot-PM callbacks
            if target["chat_id"] is None:
                for attr in ("chat_id", "from_user", "sender_id"):
                    v = getattr(msg_obj, attr, None)
                    if v is None:
                        continue
                    if attr == "from_user" and hasattr(v, "id"):
                        target["chat_id"] = v.id
                        target["via_bot"] = True
                        break
                    if attr in ("chat_id", "sender_id") and v:
                        target["chat_id"] = int(getattr(v, "id", v))
                        break
            # Prefer explicit user id for bot edits in PM
            if target["via_bot"] and target["chat_id"] is None:
                target["chat_id"] = int(self.tg_id)
        except Exception:
            logger.debug("capture status target failed", exc_info=True)
        return target

    def _restart_status_paths(self) -> list:
        """All durable paths for restart status sidecar."""
        paths = []
        seen = set()
        candidates = []
        with contextlib.suppress(Exception):
            from .. import main as _main
            candidates.append(Path(getattr(_main, "BASE_PATH", Path.cwd())))
            candidates.append(Path(getattr(_main, "BASE_DIR", Path.cwd())))
        with contextlib.suppress(Exception):
            candidates.append(Path(utils.get_base_dir()))
            candidates.append(Path(utils.get_base_dir()).parent)
        candidates.append(Path.cwd())
        candidates.append(Path.home() / ".hikkari")
        for base in candidates:
            try:
                base = Path(base)
                for p in (base / ".hikkari_restart_status.json", base / "data" / ".hikkari_restart_status.json"):
                    s = str(p.resolve()) if p.parent.exists() or True else str(p)
                    if s not in seen:
                        seen.add(s)
                        paths.append(Path(s))
            except Exception:
                continue
        return paths or [Path.cwd() / ".hikkari_restart_status.json"]

    def _restart_status_path(self) -> Path:
        return self._restart_status_paths()[0]

    def _resolve_bot_token(self) -> str | None:
        """Load bot token without requiring inline manager to be ready."""
        for key in ("hikkari.inline", "hikka.inline"):
            with contextlib.suppress(Exception):
                tok = self._db.get(key, "bot_token", None)
                if tok and isinstance(tok, str) and ":" in tok:
                    return tok.strip()
        with contextlib.suppress(Exception):
            tok = getattr(getattr(self, "inline", None), "_token", None) or getattr(
                getattr(self, "inline", None), "token", None
            )
            if tok and isinstance(tok, str) and ":" in tok:
                return tok.strip()
        with contextlib.suppress(Exception):
            from ..inline.token_obtainment import _load_bot_token
            tok = _load_bot_token(self._db, tg_id=getattr(self, "tg_id", None))
            if tok and isinstance(tok, str) and ":" in tok:
                return tok.strip()
        # raw files
        with contextlib.suppress(Exception):
            from ..inline.token_obtainment import _token_backup_paths
            for p in _token_backup_paths(getattr(self, "tg_id", None)):
                if Path(p).is_file():
                    raw = Path(p).read_text(encoding="utf-8").strip()
                    if ":" in raw and len(raw) > 20:
                        return raw.split()[0]
        return None


    @staticmethod
    def _for_bot_api_html(text: str) -> str:
        """Bot API HTML only accepts <tg-emoji emoji-id="N"> not <emoji document_id>.

        Also strips tags Bot API rejects so status edit never 400s.
        """
        if not isinstance(text, str):
            return str(text)
        try:
            from ..utils.emoji_prem import emoji_for_bot_api
            text = emoji_for_bot_api(text)
        except Exception:
            text = re.sub(
                r'<emoji\s+document_id\s*=\s*["\']?(\d+)["\']?\s*>(.*?)</emoji>',
                r'<tg-emoji emoji-id="\1">\2</tg-emoji>',
                text,
                flags=re.I | re.S,
            )
        # normalize tg-emoji without quotes
        text = re.sub(
            r'<tg-emoji\s+emoji-id\s*=\s*(\d+)\s*>',
            r'<tg-emoji emoji-id="\1">',
            text,
            flags=re.I,
        )
        # drop any remaining <emoji ...>
        text = re.sub(r"</?emoji\b[^>]*>", "", text, flags=re.I)
        return text

    @staticmethod
    def _plain_status_text(text: str) -> str:
        """Strip all HTML tags for parse_mode-free Bot API send/edit."""
        if not isinstance(text, str):
            return str(text)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"</p>\s*<p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        import html as _html
        return _html.unescape(text).strip()

    async def _http_bot_edit(self, chat_id: int, message_id: int, text: str) -> bool:
        token = self._resolve_bot_token()
        if not token:
            logger.warning("no bot token for HTTP edit")
            return False
        html = self._for_bot_api_html(text)
        plain = self._plain_status_text(text)
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for payload in (
                    {
                        "chat_id": int(chat_id),
                        "message_id": int(message_id),
                        "text": html,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    {
                        "chat_id": int(chat_id),
                        "message_id": int(message_id),
                        "text": plain,
                        "disable_web_page_preview": True,
                    },
                ):
                    try:
                        async with session.post(
                            f"https://api.telegram.org/bot{token}/editMessageText",
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=20),
                        ) as resp:
                            data = await resp.json()
                            if data.get("ok"):
                                return True
                            desc = str(data.get("description", ""))
                            if "not modified" in desc.lower():
                                return True
                            logger.warning("HTTP editMessageText: %s", data)
                    except Exception:
                        logger.debug("HTTP edit try failed", exc_info=True)
        except Exception:
            logger.exception("HTTP editMessageText exception")
        return False

    async def _http_bot_send(self, chat_id: int, text: str) -> int | None:
        token = self._resolve_bot_token()
        if not token:
            return None
        html = self._for_bot_api_html(text)
        plain = self._plain_status_text(text)
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for payload in (
                    {
                        "chat_id": int(chat_id),
                        "text": html,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    {
                        "chat_id": int(chat_id),
                        "text": plain,
                        "disable_web_page_preview": True,
                    },
                ):
                    try:
                        async with session.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=20),
                        ) as resp:
                            data = await resp.json()
                            if data.get("ok"):
                                return int(data["result"]["message_id"])
                            logger.warning("HTTP sendMessage: %s", data)
                    except Exception:
                        logger.debug("HTTP send try failed", exc_info=True)
        except Exception:
            logger.exception("HTTP sendMessage exception")
        return None

    async def _http_bot_delete(self, chat_id: int, message_id: int) -> bool:
        token = self._resolve_bot_token()
        if not token:
            return False
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.telegram.org/bot{token}/deleteMessage",
                    json={"chat_id": int(chat_id), "message_id": int(message_id)},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    data = await resp.json()
                    return bool(data.get("ok"))
        except Exception:
            logger.debug("HTTP delete failed", exc_info=True)
        return False

    def _persist_status_target(self, target: dict) -> None:
        """Save restart message ref to DB + all sidecar paths."""
        ref = None
        try:
            if target.get("inline_message_id"):
                ref = f"imid:{target['inline_message_id']}"
            elif target.get("chat_id") and target.get("message_id"):
                if target.get("via_bot"):
                    ref = f"bot:{int(target['chat_id'])}:{int(target['message_id'])}"
                else:
                    ref = f"{int(target['chat_id'])}:{int(target['message_id'])}"
            if not ref:
                return
            self.set("selfupdatemsg", ref)
            with contextlib.suppress(Exception):
                self._db.set("Updater", "selfupdatemsg", ref)
            with contextlib.suppress(Exception):
                self._db.set("UpdaterMod", "selfupdatemsg", ref)
            import json as _json
            payload = _json.dumps(
                {
                    "ref": ref,
                    "ts": time.time(),
                    "via_bot": bool(target.get("via_bot")),
                    "chat_id": target.get("chat_id"),
                    "message_id": target.get("message_id"),
                    "inline_message_id": target.get("inline_message_id"),
                    "owner_id": int(getattr(self, "tg_id", 0) or 0),
                }
            )
            for p in self._restart_status_paths():
                with contextlib.suppress(Exception):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(payload, encoding="utf-8")
        except Exception:
            logger.exception("persist status target failed")

    def _load_status_ref(self) -> str | None:
        for getter in (
            lambda: self.get("selfupdatemsg"),
            lambda: self._db.get("Updater", "selfupdatemsg", None),
            lambda: self._db.get("UpdaterMod", "selfupdatemsg", None),
        ):
            with contextlib.suppress(Exception):
                v = getter()
                if v:
                    return str(v)
        import json as _json
        for p in self._restart_status_paths():
            with contextlib.suppress(Exception):
                if p.is_file():
                    data = _json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("ref"):
                        return str(data["ref"])
                    if isinstance(data, dict) and data.get("chat_id") and data.get("message_id"):
                        if data.get("via_bot"):
                            return f"bot:{int(data['chat_id'])}:{int(data['message_id'])}"
                        return f"{int(data['chat_id'])}:{int(data['message_id'])}"
        return None

    def _clear_status_ref(self) -> None:
        with contextlib.suppress(Exception):
            self.set("selfupdatemsg", None)
        with contextlib.suppress(Exception):
            self._db.set("Updater", "selfupdatemsg", None)
        with contextlib.suppress(Exception):
            self._db.set("UpdaterMod", "selfupdatemsg", None)
        for p in self._restart_status_paths():
            with contextlib.suppress(Exception):
                p.unlink(missing_ok=True)


    async def _edit_update_status(self, msg_obj, text: str, target: dict | None = None):
        """Always try: call.edit → bot API → client edit. Never silent-fail the UI."""
        if getattr(self, "inline", None):
            with contextlib.suppress(Exception):
                text = self.inline.sanitise_text(text)

        if target is None:
            target = self._capture_status_target(msg_obj)
            self._persist_status_target(target)

        # 1) InlineCall.edit (works for form in any chat)
        if hasattr(msg_obj, "edit") and callable(msg_obj.edit):
            try:
                await msg_obj.edit(text)
                return msg_obj
            except Exception:
                logger.debug("call.edit failed", exc_info=True)

        bot = getattr(getattr(self, "inline", None), "bot", None)

        # 2) Bot API by inline_message_id
        if bot and target.get("inline_message_id"):
            try:
                await bot.edit_message_text(
                    text,
                    inline_message_id=str(target["inline_message_id"]),
                    disable_web_page_preview=True,
                )
                return msg_obj
            except TypeError:
                try:
                    await bot.edit_message_text(
                        inline_message_id=str(target["inline_message_id"]),
                        text=text,
                        disable_web_page_preview=True,
                    )
                    return msg_obj
                except Exception:
                    logger.debug("bot edit imid failed", exc_info=True)
            except Exception:
                logger.debug("bot edit imid failed", exc_info=True)

        # 3) Bot API chat+mid (bot PM notification card)
        if bot and target.get("chat_id") and target.get("message_id"):
            try:
                await bot.edit_message_text(
                    chat_id=int(target["chat_id"]),
                    message_id=int(target["message_id"]),
                    text=text,
                    disable_web_page_preview=True,
                )
                return msg_obj
            except Exception:
                logger.debug("bot edit chat/mid failed", exc_info=True)

        # 4) User client edit
        if target.get("chat_id") and target.get("message_id"):
            try:
                await self._client.edit_message(
                    int(target["chat_id"]), int(target["message_id"]), text
                )
                return msg_obj
            except Exception:
                logger.debug("client edit failed", exc_info=True)

        # 5) Parse selfupdatemsg fallback
        ref = self.get("selfupdatemsg")
        if isinstance(ref, str):
            try:
                if ref.startswith("imid:"):
                    if bot:
                        await bot.edit_message_text(
                            text,
                            inline_message_id=ref[5:],
                            disable_web_page_preview=True,
                        )
                        return msg_obj
                parts = ref.split(":")
                if len(parts) == 3:
                    _, cid, mid = parts
                    cid, mid = int(cid), int(mid)
                    if bot:
                        with contextlib.suppress(Exception):
                            await bot.edit_message_text(
                                chat_id=cid, message_id=mid, text=text,
                                disable_web_page_preview=True,
                            )
                            return msg_obj
                    with contextlib.suppress(Exception):
                        await self._client.edit_message(cid, mid, text)
                        return msg_obj
                elif len(parts) == 2:
                    cid, mid = int(parts[0]), int(parts[1])
                    with contextlib.suppress(Exception):
                        await self._client.edit_message(cid, mid, text)
                        return msg_obj
            except Exception:
                logger.debug("ref fallback edit failed", exc_info=True)

        # 6) NEVER send a new message for status — only edit (avoids stuck duplicates)
        logger.warning("status edit failed for all methods; text=%s", text[:80])
        return msg_obj


    async def inline_update(
        self,
        msg_obj: InlineCall | Message,
        hard: bool = False,
    ):
        # Capture once and reuse — status stays on the SAME message
        target = self._capture_status_target(msg_obj)
        self._persist_status_target(target)

        # Strict order: download → install → show restart → restart()
        if hard:
            os.system(f"cd {utils.get_base_dir()} && cd .. && git reset --hard HEAD")

        try:
            await self._edit_update_status(
                msg_obj, self.strings["downloading"], target=target
            )

            try:
                req_update = await self.download_common()
                if self._try_auto_rollback():
                    raise RuntimeError("Hikkari update auto-rollback")
            except TimeoutError:
                logger.exception("Timed out while fetching updates from git remote")
                with contextlib.suppress(Exception):
                    await self._edit_update_status(
                        msg_obj,
                        "❌ <b>Timeout while downloading update</b>",
                        target=target,
                    )
                return

            await self._edit_update_status(
                msg_obj, self.strings["installing"], target=target
            )

            if req_update:
                try:
                    self.req_common()
                except Exception:
                    logger.exception("req_common failed")

            # Force restart caption BEFORE process dies (was missing → hang on installing)
            caption = self.strings["restarting_caption"].format(
                utils.get_platform_emoji()
                if getattr(self._client, "hikkari_me", None)
                and getattr(self._client.hikkari_me, "premium", False)
                else "Hikkari"
            )
            await self._edit_update_status(msg_obj, caption, target=target)
            # Give Telegram time to deliver the edit
            await asyncio.sleep(0.6)
            # Persist for post-restart success message
            self.set("restart_ts", time.time())
            self._persist_status_target(target)
            with contextlib.suppress(Exception):
                self._db.save()

            await self.restart_common(msg_obj, _status_target=target)
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


    async def source(self, message: Message):
        await utils.answer(
            message,
            self.strings["source"].format(self.config["GIT_ORIGIN_URL"]),
        )

    async def client_ready(self):
        # Do NOT return early if inline bot is not ready — must finish restart status edit
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
                "text": self._strip_btn_emoji(self.strings.get("update", "Обновить")),
                "data": "hikkari/update",
                "style": "primary",
                "emoji_id": 5258382512656253510,
            },
            {
                "text": self._strip_btn_emoji(self.strings.get("ignore", "Игнорировать")),
                "data": "hikkari/ignore_upd",
                "style": "danger",
                "emoji_id": 5255949705740843980,
            },
        ]
        self._markup = self._update_markup_rows

        # Always complete restart UI after boot (DB / sidecar / multi-path)
        async def _finish_restart_ui():
            # Wait briefly so network/token files settle
            for attempt in range(8):
                ref = self._load_status_ref()
                if not ref:
                    await asyncio.sleep(1)
                    continue
                try:
                    await self.update_complete()
                except Exception:
                    logger.exception("update_complete attempt %s failed", attempt)
                await asyncio.sleep(5)
                try:
                    if self._load_status_ref() is not None:
                        await self.full_restart_complete()
                except Exception:
                    logger.exception("full_restart_complete attempt %s failed", attempt)
                # if cleared, done
                if self._load_status_ref() is None:
                    return
                await asyncio.sleep(2)
            logger.warning("restart UI finish gave up; ref=%s", self._load_status_ref())

        if self._load_status_ref() is not None or self.get("restart_ts") or self._db.get("Updater", "restart_ts", None):
            asyncio.ensure_future(_finish_restart_ui())

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
                        await self._http_bot_delete(int(chat_id), int(message_id))
                    with contextlib.suppress(Exception):
                        if getattr(self, "inline", None) and getattr(self.inline, "bot", None):
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
        """Edit restart status after boot. Supports bot:/msg:/imid:/chat:mid."""
        if not ms:
            return False
        text = self.inline.sanitise_text(msg) if getattr(self, "inline", None) else msg
        bot = getattr(getattr(self, "inline", None), "bot", None)
        ok = False
        chat_id = message_id = None
        via_bot = False

        # imid:...
        if isinstance(ms, str) and ms.startswith("imid:"):
            imid = ms[5:]
            if bot:
                try:
                    await bot.edit_message_text(
                        text,
                        inline_message_id=self._deserialize_inline_message_id(imid),
                        disable_web_page_preview=True,
                    )
                    ok = True
                except TypeError:
                    try:
                        await bot.edit_message_text(
                            inline_message_id=self._deserialize_inline_message_id(imid),
                            text=text,
                            disable_web_page_preview=True,
                        )
                        ok = True
                    except Exception as e:
                        logger.warning("imid status edit failed (%s)", e)
                except Exception as e:
                    logger.warning("imid status edit failed (%s)", e)
            if ok and delete_after:
                await self._schedule_delete_status(ms=ms, delay=delete_after)
            return ok

        # bot:chat:mid — bot PM (HTTP first — works even if inline not ready)
        if isinstance(ms, str) and ms.startswith("bot:"):
            via_bot = True
            try:
                _, chat_s, msg_s = ms.split(":", 2)
                chat_id, message_id = int(chat_s), int(msg_s)
            except Exception:
                return False
            ok = await self._http_bot_edit(chat_id, message_id, text)
            if not ok and bot:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        disable_web_page_preview=True,
                    )
                    ok = True
                except Exception as e:
                    logger.warning("bot PM status edit failed (%s)", e)
            if ok and delete_after:
                await self._schedule_delete_status(
                    chat_id=chat_id,
                    message_id=message_id,
                    delay=delete_after,
                    via_bot=True,
                )
            return ok

        # msg:chat:mid or chat:mid — user-visible message (via@ form or .restart)
        legacy = self._parse_legacy_update_message_ref(ms)
        if legacy:
            chat_id, message_id = legacy
            # Prefer user client (via@ forms live as user messages)
            try:
                await self._client.edit_message(chat_id, message_id, text)
                ok = True
            except Exception as e:
                logger.debug("client status edit failed (%s)", e)
                if bot:
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=text,
                            disable_web_page_preview=True,
                        )
                        ok = True
                        via_bot = True
                    except Exception as e2:
                        logger.warning("status edit failed client+bot (%s / %s)", e, e2)
            if ok and delete_after:
                await self._schedule_delete_status(
                    chat_id=chat_id,
                    message_id=message_id,
                    delay=delete_after,
                    via_bot=via_bot,
                )
            return ok

        # raw inline_message_id JSON / string
        if bot:
            try:
                await bot.edit_message_text(
                    inline_message_id=self._deserialize_inline_message_id(str(ms)),
                    text=text,
                    disable_web_page_preview=True,
                )
                if delete_after:
                    await self._schedule_delete_status(ms=str(ms), delay=delete_after)
                return True
            except Exception:
                logger.debug("inline_message_id status edit failed", exc_info=True)
        return False

    async def update_complete(self):
        logger.info("Self update successful — editing restart status")
        start = self.get("restart_ts") or self._db.get("Updater", "restart_ts", None)
        try:
            took = round(time.time() - float(start))
        except Exception:
            took = "n/a"

        msg = self.strings["success"].format(utils.ascii_face(), took)
        ms = self._load_status_ref()
        if not ms:
            logger.warning("update_complete: no selfupdatemsg ref found")
            return
        # Keep ref for full_restart_complete
        ok = await self._edit_restart_status(ms, msg)
        if not ok:
            # retry a few times (bot/client may not be fully up)
            for delay in (2, 4, 6):
                await asyncio.sleep(delay)
                ok = await self._edit_restart_status(ms, msg)
                if ok:
                    break
            if not ok:
                logger.warning("update_complete: failed to edit status after retries (%s)", ms)

    async def full_restart_complete(self, secure_boot: bool = False):
        start = self.get("restart_ts")

        try:
            took = round(time.time() - start)
        except Exception:
            took = "n/a"

        self.set("restart_ts", None)
        with contextlib.suppress(Exception):
            self._db.set("Updater", "restart_ts", None)
        ms = self._load_status_ref()

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

        if not ms:
            logger.warning("full_restart_complete: no status ref")
            return

        # Keep modules_count in sync so next restart does not false-fail
        with contextlib.suppress(Exception):
            self.db.set("Updater", "modules_count", len(self.allmodules.modules))

        # Edit success then auto-delete; clear ref only after successful edit attempt
        ok = await self._edit_restart_status(ms, msg, delete_after=60)
        if not ok:
            for delay in (2, 4):
                await asyncio.sleep(delay)
                ok = await self._edit_restart_status(ms, msg, delete_after=60)
                if ok:
                    break
        self._clear_status_ref()

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
