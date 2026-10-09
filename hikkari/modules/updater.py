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
                "beta_users",
                [],
                "Optional LOCAL extra beta IDs. Main list is on GitHub: "
                "assets/beta_users.txt (raw.githubusercontent.com/Wers1xx/Hikkari/master/...). "
                "Does NOT grant .branch beta. Access is ONLY via GitHub assets/beta_users.txt",
                validator=loader.validators.Series(validator=loader.validators.Integer()),
            ),
            loader.ConfigValue(
                "disable_notifications",
                doc=lambda: self.strings["_cfg_doc_disable_notifications"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "notify_owners",
                True,
                "Рассылать уведомления об обновлениях всем owner (не только основной аккаунт)",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "autoupdate",
                False,
                doc=lambda: self.strings["_cfg_doc_autoupdate"],
                validator=loader.validators.Boolean(),
            ),
        )

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
                    logger.debug("Fetching changelog from %s", origin.url)
                    try:
                        subprocess.run(
                            ["git", "fetch", "--quiet", "origin"],
                            cwd=repo.working_dir,
                            timeout=15,
                            capture_output=True,
                            check=False,
                        )
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "git fetch timed out — using local commits for changelog"
                        )
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
                repo.iter_commits(f"origin/{version.branch}", max_count=1)
            ).hexsha
            commits = [*repo.iter_commits(f"HEAD..origin/{version.branch}")]

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
                    repo.iter_commits(f"origin/{version.branch}", max_count=1)
                ).hexsha
        except Exception:
            return ""

    async def client_ready(self):
        # Immediate update check on start (don't wait for first poll interval)
        async def _boot_check():
            await asyncio.sleep(3)  # let inline bot / net settle
            with contextlib.suppress(Exception):
                await self.poller()
        asyncio.ensure_future(_boot_check())


    def _update_notify_recipients(self) -> list[int]:
        """All user IDs that should get update / announcement notifications."""
        ids: set[int] = set()
        # Primary account
        with contextlib.suppress(Exception):
            ids.add(int(self.tg_id))
        # All linked clients
        with contextlib.suppress(Exception):
            for c in getattr(self, "allclients", None) or []:
                with contextlib.suppress(Exception):
                    ids.add(int(c.tg_id))
        # Security owners (if enabled)
        if bool(self.config.get("notify_owners", True)):
            with contextlib.suppress(Exception):
                owners = list(
                    getattr(self._client.dispatcher.security, "owner", None) or []
                )
                for o in owners:
                    with contextlib.suppress(Exception):
                        ids.add(int(o))
            with contextlib.suppress(Exception):
                # db pointer fallback
                from .. import security as _sec
                for o in self._db.get(_sec.__name__, "owner", []) or []:
                    with contextlib.suppress(Exception):
                        ids.add(int(o))
        return sorted(ids)

    async def _broadcast_update_notice(
        self,
        text: str,
        *,
        reply_markup=None,
        disable_web_page_preview: bool = True,
    ) -> int | None:
        """Send notice to every recipient via inline bot, fallback to userbot DM."""
        recipients = self._update_notify_recipients()
        if not recipients:
            recipients = [int(self.tg_id)]

        primary_msg_id = None
        bot = getattr(getattr(self, "inline", None), "bot", None)

        for uid in recipients:
            sent = False
            # 1) Inline bot (preferred — buttons work)
            if bot is not None:
                try:
                    kw = {
                        "disable_web_page_preview": disable_web_page_preview,
                    }
                    if reply_markup is not None:
                        kw["reply_markup"] = reply_markup
                    m = await bot.send_message(uid, text, **kw)
                    if primary_msg_id is None:
                        primary_msg_id = getattr(m, "message_id", None) or getattr(
                            m, "id", None
                        )
                    sent = True
                except Exception as e:
                    logger.debug(
                        "update notify via bot to %s failed: %s", uid, e
                    )
            # 2) Fallback: userbot → Saved Messages / user
            if not sent:
                try:
                    # Prefer main client for own id; otherwise try each client
                    clients = list(getattr(self, "allclients", None) or [self._client])
                    for c in clients:
                        try:
                            await c.send_message(
                                uid,
                                text,
                                link_preview=not disable_web_page_preview,
                            )
                            sent = True
                            break
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug("update notify via client to %s failed: %s", uid, e)
            if not sent:
                logger.warning("Could not deliver update notice to %s", uid)

        return primary_msg_id

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
                            await self._broadcast_update_notice(
                                self.strings["announcement"].format(announcement),
                                reply_markup=None,
                            )
                            self.set("announcement", announcement)
                    case _:
                        pass
            except Exception:
                pass

    @loader.loop(interval=60, autostart=True)
    async def poller(self):
        if NO_GIT:
            return
        try:
            current, self._pending, changelog = self._get_update_state()
        except Exception as e:
            self._log_git_poll_error(e)
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
            # Broadcast to all owners / linked accounts (not only primary tg_id)
            text = self.strings["update_required"].format(
                current[:6],
                '<a href="https://github.com/Wers1xx/Hikkari/compare/{}...{}">{}</a>'.format(
                    current[:12],
                    self._pending[:12],
                    self._pending[:6],
                ),
                changelog,
            )
            msg_id = await self._broadcast_update_notice(
                text,
                reply_markup=self._markup(),
                disable_web_page_preview=True,
            )
            self._notified = self._pending
            self.set("ignore_permanent", False)
            await self._delete_all_upd_messages()
            if msg_id is not None:
                self.set("upd_msg", msg_id)

    async def _delete_all_upd_messages(self):
        for client in self.allclients:
            with contextlib.suppress(Exception):
                await client.loader.inline.bot.delete_message(
                    client.tg_id,
                    client.loader.db.get("Updater", "upd_msg"),
                )

    @loader.callback_handler()
    async def update_call(self, call: InlineCall):
        """Process update buttons clicks"""
        if NO_GIT:
            await call.answer("Git disabled via --no-git.", show_alert=True)
            return
        if call.data not in {"hikkari/update", "hikkari/ignore_upd"}:
            return

        if call.data == "hikkari/ignore_upd":
            self.set("ignore_permanent", self.get_latest())
            await self.inline.bot(call.answer(self.strings["latest_disabled"]))
            return

        await self._delete_all_upd_messages()

        with contextlib.suppress(Exception):
            await call.delete()

        await self.invoke("update", "-f", peer=self.inline.bot_username)

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
                    "<emoji document_id=5283176512747507510>✨</emoji> <b>Changelog is empty</b>",
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
            prefix = f"<emoji document_id=5283176512747507510>✨</emoji> <b>Hikkari</b> <code>v{ver}</code>"
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
        inline_message_id = getattr(msg_obj, "inline_message_id", None)
        self.set(
            "selfupdatemsg",
            (
                self._serialize_inline_message_id(inline_message_id)
                if inline_message_id is not None
                else f"{utils.get_chat_id(msg_obj)}:{msg_obj.id}"
            ),
        )

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
        msg_obj = await utils.answer(
            msg_obj,
            self.strings["restarting_caption"].format(
                utils.get_platform_emoji()
                if self._client.hikkari_me.premium
                else "Hikkari"
            ),
            skip_rich=True,
        )

        await self.process_restart_message(msg_obj)

        self.db.set("Updater", "modules_count", len(self.allmodules.modules))

        self.set("restart_ts", time.time())

        handler = logging.getLogger().handlers[0]
        handler.setLevel(logging.CRITICAL)

        for client in self.allclients:
            # Terminate main loop of all running clients
            # Won't work if not all clients are ready
            if client is not message.client:
                await client.disconnect()

        await message.client.disconnect()
        restart()

    async def download_common(self):
        self._save_pre_update_sha()

        def _sync():
            try:
                with Repo(os.path.dirname(utils.get_base_dir())) as repo:
                    origin = repo.remote("origin")
                    logger.debug("Fetching updates from %s", origin.url)
                    r = origin.pull()
                    new_commit = repo.head.commit
                    for info in r:
                        if info.old_commit:
                            for d in new_commit.diff(info.old_commit):
                                if d.b_path == "requirements.txt":
                                    return True
                return False
            except git.exc.InvalidGitRepositoryError:
                repo = Repo.init(os.path.dirname(utils.get_base_dir()))
                with repo:
                    origin = repo.create_remote("origin", self.config["GIT_ORIGIN_URL"])
                    logger.debug("Fetching initial updates from %s", origin.url)
                    origin.fetch()
                    repo.create_head("master", origin.refs.master)
                    repo.heads.master.set_tracking_branch(origin.refs.master)
                    repo.heads.master.checkout(True)
                return False

        return await asyncio.wait_for(
            asyncio.to_thread(_sync),
            timeout=120,
        )

    @staticmethod
    def req_common():
        # Now we have downloaded new code, install requirements
        logger.debug("Installing new requirements...")
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    os.path.join(
                        os.path.dirname(utils.get_base_dir()),
                        "requirements.txt",
                    ),
                    "--user",
                ],
                check=True,
                timeout=600,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
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
                    repo.iter_commits(f"origin/{version.branch}", max_count=1)
                ).hexsha
            if (
                "-f" in args
                or not self.inline.init_complete
                or not await self.inline.form(
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
            await self.inline_update(message)

    @loader.command()
    async def autoupdate(self, message: Message):
        """Autoupdate is disabled — use .update manually"""
        self.config["autoupdate"] = False
        await utils.answer(
            message,
            "\U0001f6ab <b>Autoupdate is disabled</b>\n"
            "Use <code>.update</code> manually.",
        )

    async def inline_update(
        self,
        msg_obj: InlineCall | Message,
        hard: bool = False,
    ):
        # We don't really care about asyncio at this point, as we are shutting down
        if hard:
            os.system(f"cd {utils.get_base_dir()} && cd .. && git reset --hard HEAD")

        try:
            with contextlib.suppress(Exception):
                msg_obj = await utils.answer(
                    msg_obj, self.strings["downloading"], skip_rich=True
                )

            try:
                req_update = await self.download_common()
                if self._try_auto_rollback():
                    raise RuntimeError("Hikkari update auto-rollback")
            except TimeoutError:
                logger.exception("Timed out while fetching updates from git remote")
                return

            with contextlib.suppress(Exception):
                msg_obj = await utils.answer(
                    msg_obj, self.strings["installing"], skip_rich=True
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
            await utils.answer(message, "<emoji document_id=5237898864433837164>👎</emoji> Use <code>master</code> or <code>beta</code>")
            return
        if args == "main":
            args = "master"

        if args == "beta":
            allowed = await self._can_use_beta(uid, force_refresh=True)
            if not allowed:
                await utils.answer(
                    message,
                    "<emoji document_id=5240241223632954241>🚫</emoji> <b>Нет доступа к ветке beta</b>\n\n"
                    f"ID: <code>{uid}</code>\n"
                    "Переход на beta разрешён только ID из списка на GitHub:\n"
                    "<code>assets/beta_users.txt</code>\n"
                    '<a href="https://github.com/Wers1xx/Hikkari/blob/master/assets/beta_users.txt">'
                    "Открыть список</a>\n\n"
                    "<i>Если тебя нет в файле — beta недоступна.</i>",
                )
                return

        if NO_GIT:
            await utils.answer(message, "<emoji document_id=5237898864433837164>👎</emoji> Git disabled")
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
                        f"<emoji document_id=5237898864433837164>👎</emoji> Remote branch <code>{args}</code> not found on origin\n"
                        f"<i>Проверь:</i> <code>git ls-remote --heads origin</code>",
                    )
                    return

                try:
                    repo.git.checkout("-B", args, f"origin/{args}")
                except Exception:
                    if args in repo.heads:
                        repo.heads[args].checkout()
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
                try:
                    repo.git.pull("origin", args)
                except Exception as pe:
                    logger.debug("pull after branch switch: %s", pe)

            version.branch = args
            await utils.answer(
                message,
                f"<emoji document_id=5256182535917940722>⤵️</emoji> Switched to <code>{args}</code>\n"
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
                f"<emoji document_id=5237898864433837164>👎</emoji> Branch switch failed: <code>{utils.escape_html(str(e))}</code>",
            )


    @loader.command(
        ru_doc="— показать список beta-доступа (GitHub)",
        en_doc="— show beta access list (GitHub)",
    )
    async def betalist(self, message: Message):
        """Show who can use the beta branch (from GitHub)"""
        ids = await self._fetch_github_beta_ids()
        local = []
        try:
            local = [int(x) for x in (self.config.get("beta_users") or [])]
        except Exception:
            pass
        lines = [
            "<b><emoji document_id=5283176512747507510>✨</emoji> Beta access</b>",
            "",
            "<b>GitHub</b> <code>assets/beta_users.txt</code>:",
        ]
        for i in sorted(ids):
            mark = " (creator)" if i == self._BETA_CREATOR_ID else ""
            lines.append(f"• <code>{i}</code>{mark}")
        if local:
            lines.append("")
            lines.append("<b>Local extra</b> (cfg Updater beta_users):")
            for i in local:
                lines.append(f"• <code>{i}</code>")
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
        """Local-only beta grant. Prefer editing GitHub assets/beta_users.txt"""
        args = utils.get_args_raw(message)
        uid = None
        if args and str(args).strip().isdigit():
            uid = int(str(args).strip())
        elif message.is_reply:
            reply = await message.get_reply_message()
            uid = reply.sender_id if reply else None
        if not uid:
            await utils.answer(
                message,
                "<emoji document_id=5237898864433837164>👎</emoji> Reply / ID\n\n"
                "<b>Main list:</b> edit on GitHub\n"
                "<code>assets/beta_users.txt</code>",
            )
            return
        cur = list(self.config.get("beta_users") or [])
        if uid not in [int(x) for x in cur]:
            cur.append(int(uid))
            self.config["beta_users"] = cur
        await utils.answer(
            message,
            f"<emoji document_id=5256182535917940722>⤵️</emoji> Local beta for <code>{uid}</code>\n"
            f"Prefer adding ID to GitHub <code>assets/beta_users.txt</code> "
            f"so all installs see it.",
        )

    @loader.command(
        ru_doc="<id|reply> — убрать локальный beta-доступ",
        en_doc="<id|reply> — revoke local beta access",
    )
    async def betarevoke(self, message: Message):
        """Revoke local beta access (GitHub list unchanged)"""
        args = utils.get_args_raw(message)
        uid = None
        if args and str(args).strip().isdigit():
            uid = int(str(args).strip())
        elif message.is_reply:
            reply = await message.get_reply_message()
            uid = reply.sender_id if reply else None
        if not uid:
            await utils.answer(message, "<emoji document_id=5237898864433837164>👎</emoji> Reply to user or pass numeric ID")
            return
        cur = [int(x) for x in (self.config.get("beta_users") or [])]
        if uid in cur:
            cur.remove(uid)
            self.config["beta_users"] = cur
        await utils.answer(
            message,
            f"<emoji document_id=5256182535917940722>⤵️</emoji> Local beta revoked for <code>{uid}</code>\n"
            f"GitHub list is separate — edit <code>assets/beta_users.txt</code> there.",
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

        self._markup = lambda: self.inline.generate_markup(
            [
                {
                    "text": self.strings["update"],
                    "data": "hikkari/update",
                    "style": "primary",
                },
                {
                    "text": self.strings["ignore"],
                    "data": "hikkari/ignore_upd",
                    "style": "danger",
                },
            ]
        )

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
                await self.inline.bot.send_message(
                    self.tg_id,
                    self.strings.get(
                        "update_auto_rollback",
                        "<emoji document_id=5447644880824181073>⚠️</emoji> <b>Update broke startup and was rolled back</b> to <code>{sha}</code>.",
                    ).format(sha=(old or "?")[:7]),
                )
        else:
            with contextlib.suppress(Exception):
                self._clear_pre_update()

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

    async def update_complete(self):
        logger.debug("Self update successful! Edit message")
        start = self.get("restart_ts")
        try:
            took = round(time.time() - start)
        except Exception:
            took = "n/a"

        msg = self.strings["success"].format(utils.ascii_face(), took)
        ms = self.get("selfupdatemsg")

        if legacy_message_ref := self._parse_legacy_update_message_ref(ms):
            chat_id, message_id = legacy_message_ref
            try:
                await self._client.edit_message(chat_id, message_id, msg)
            except Exception as e:
                # via-bot / InlineBotRequiredError — send new + delete old
                logger.warning("restart edit failed (%s), fallback send", e)
                try:
                    await self._client.send_message(chat_id, msg)
                    await self._client.delete_messages(chat_id, message_id)
                except Exception:
                    logger.debug("restart fallback failed", exc_info=True)
            return

        try:
            await self.inline.bot.edit_message_text(
                inline_message_id=self._deserialize_inline_message_id(str(ms)),
                text=self.inline.sanitise_text(msg),
            )
        except Exception:
            logger.debug("inline restart edit failed", exc_info=True)

    async def full_restart_complete(self, secure_boot: bool = False):
        start = self.get("restart_ts")

        try:
            took = round(time.time() - start)
        except Exception:
            took = "n/a"

        self.set("restart_ts", None)
        ms = self.get("selfupdatemsg")

        modules_count = self.db.get("Updater", "modules_count")
        try:
            modules_count = int(modules_count)
        except Exception:
            modules_count = len(self.allmodules.modules)

        if modules_count <= len(self.allmodules.modules):
            msg = self.strings[
                "secure_boot_complete" if secure_boot else "full_success"
            ].format(utils.ascii_face(), took)
        else:
            fails = modules_count - len(self.allmodules.modules)
            msg = self.strings[
                "secure_boot_fail" if secure_boot else "full_fail"
            ].format(utils.ascii_face(), took, fails)
            # Append names of modules that failed to load (if tracked)
            failed_names = getattr(self.allmodules, "_failed_module_names", None) or []
            if failed_names:
                short = []
                for n in failed_names[:5]:
                    n = str(n)
                    # strip path noise
                    n = n.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                    short.append(f"<code>{utils.escape_html(n)}</code>")
                msg += "\n" + ", ".join(short)
                if len(failed_names) > 5:
                    msg += f" (+{len(failed_names) - 5})"

        if ms is None:
            return

        self.set("selfupdatemsg", None)

        if legacy_message_ref := self._parse_legacy_update_message_ref(ms):
            chat_id, message_id = legacy_message_ref
            try:
                await self._client.edit_message(chat_id, message_id, msg)
            except Exception as e:
                logger.warning("full_restart edit failed (%s), fallback", e)
                try:
                    await self._client.send_message(chat_id, msg)
                except Exception:
                    pass
            try:
                await asyncio.sleep(60)
                await self._client.delete_messages(chat_id, message_id)
            except Exception:
                pass
            return

        try:
            await self.inline.bot.edit_message_text(
                inline_message_id=self._deserialize_inline_message_id(str(ms)),
                text=self.inline.sanitise_text(msg),
            )
        except Exception:
            logger.debug("inline full_restart edit failed", exc_info=True)

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
                        f"<emoji document_id=5240241223632954241>🚫</emoji> <b>Version</b> <code>{args}</code> <b>not found in git history</b>",
                    ),
                )
                return
            target = ("sha", sha, args)
            confirm = self.strings.get(
                "rollback_confirm_ver",
                "<emoji document_id=5447644880824181073>⚠️</emoji> <b>Rollback to version</b> <code>{ver}</code> (<code>{sha}</code>)?",
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
                        "text": "⤵️",
                        "callback": self.rollback_confirm,
                        "args": [target[0], target[1], target[2]],
                        "style": "success",
                    }
                ],
                [{"text": "👎", "action": "close", "style": "danger"}],
            ],
        )

    async def rollback_confirm(self, call: InlineCall, mode: str, value, label: str):
        await utils.answer(
            call,
            self.strings.get("rollback_process", "<emoji document_id=5386367538735104399>⌛</emoji> Rollback…").format(num=label),
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
                        "text": "⤵️",
                        "callback": self.ubstop_func,
                        "style": "primary",
                    },
                ],
                [{"text": "👎", "action": "close", "style": "primary"}],
            ],
            silent=True,
        )
