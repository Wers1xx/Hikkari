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
import json
import logging
import os
import string
import time
from pathlib import Path

from hikkaritl.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from hikkaritl.sessions import MemorySession, SQLiteSession
from hikkaritl.tl.custom import Message
from hikkaritl.tl.types import User
from hikkaritl.utils import parse_phone

from .. import loader, main, security, utils
from ..loader import LOADED_MODULES_PATH
from .._internal import restart
from ..inline.types import InlineCall
from ..tl_cache import CustomTelegramClient
from ..version import __version__

logger = logging.getLogger(__name__)


@loader.tds
class HikkariWebMod(loader.Module):
    """Account management (add / list / remove)"""

    strings = {"name": "HikkariAccounts"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "ngrok_token",
                "",
                lambda: "ngrok Authtoken for .weburl public link",
                validator=loader.validators.Hidden(loader.validators.String()),
            ),
        )

    @loader.command()
    async def addacc(self, message: Message):
        if "JAMHOST" in os.environ:
            await utils.answer(message, self.strings["host_denied"])
            return

        user_id = utils.get_args(message)
        if not user_id:
            reply: Message = await message.get_reply_message()
            user_id = reply.sender_id if reply else None
        else:
            user_id = user_id[0]

        user = None
        if user_id:
            try:
                user_id = int(user_id)
            except ValueError:
                pass

            try:
                user = await self._client.get_entity(user_id)
            except Exception as e:
                logger.error(f"Error while fetching user: {e}")

        if not user or not isinstance(user, User) or user.bot:
            await utils.answer(message, self.strings["invalid_target"])
            return

        if user.id == self.tg_id or "force_insecure" in message.text.lower():
            await self._inline_login(message, user)
            return

        try:
            if not await self.inline.form(
                self.strings["add_user_confirm"].format(
                    utils.escape_html(user.first_name),
                    user.id,
                ),
                message=message,
                reply_markup=[
                    {
                        "text": self.strings["btn_yes"],
                        "callback": self._inline_login,
                        "args": (user,),
                    },
                    {"text": self.strings["btn_no"], "action": "close"},
                ],
            ):
                raise Exception

        except Exception:
            await utils.answer(
                message,
                self.strings["add_user_insecure"].format(
                    utils.escape_html(user.first_name),
                    user.id,
                    utils.escape_html(self.get_prefix()),
                    user.id,
                ),
            )
        return

    async def _inline_login(
        self,
        call: Message | InlineCall,
        user: User,
        after_fail: bool = False,
        is_switch: bool = False,
    ):
        reply_markup = [
            {
                "text": self.strings["enter_number"],
                "input": self.strings["your_phone_number"],
                "handler": self.inline_phone_handler,
                "args": (user, is_switch),
            }
        ]

        fail = self.strings["incorrect_number"] if after_fail else ""

        await utils.answer(
            call,
            fail + self.strings["enter_number_format"],
            reply_markup=reply_markup,
            always_allow=[user.id],
        )

    def _get_client(self) -> CustomTelegramClient:
        return CustomTelegramClient(
            MemorySession(),
            main.hikkari.api_token.ID,
            main.hikkari.api_token.HASH,
            connection=main.hikkari.conn,
            proxy=main.hikkari.proxy,
            connection_retries=None,
            device_model=main.get_app_name(),
            system_version="Windows 10",
            app_version=".".join(map(str, __version__)) + " x64",
            lang_code="en",
            system_lang_code="en-US",
        )

    def _clone_switch_db(self, old_id: int, new_id: int) -> dict:
        data = json.loads(json.dumps(dict(self._db)))

        inline_data = data.setdefault("hikkari.inline", {})
        if isinstance(inline_data, dict):
            inline_data["bot_token"] = None
            inline_data["custom_bot"] = False
            inline_data.pop("bot_id", None)

        security_data = data.setdefault(security.__name__, {})
        for key in ("owner", "all_users"):
            users = security_data.get(key, [])
            if isinstance(users, list):
                users = [user for user in users if user != old_id]
                if new_id not in users:
                    users.append(new_id)
                security_data[key] = users

        return data

    def _archive_identity_file(self, path: Path, suffix: int) -> Path | None:
        if not path.exists():
            return None

        archived = path.with_name(f"{path.name}.bak-switch-{suffix}")
        if archived.exists():
            raise RuntimeError(f"Backup file already exists: {archived.name}")

        path.rename(archived)
        return archived

    def _restore_identity_file(
        self,
        original: Path,
        archived: Path | None,
        created: bool = False,
    ) -> None:
        if archived and archived.exists():
            if original.exists():
                original.unlink()
            archived.rename(original)
        elif created and original.exists():
            original.unlink()

    async def _copy_switch_db(self, new_id: int, data: dict) -> None:
        redis = getattr(self._db, "_redis", None)
        if redis:
            await utils.run_sync(
                lambda: redis.set(str(new_id), json.dumps(data, ensure_ascii=True))
            )

        (Path(main.BASE_PATH) / f"config-{new_id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )

    async def _save_switch_session(
        self,
        client: CustomTelegramClient,
        new_id: int,
    ) -> None:
        session = SQLiteSession(os.path.join(main.SESSIONS_DIR, f"hikkari-{new_id}"))
        session.set_dc(
            client.session.dc_id,
            client.session.server_address,
            client.session.port,
        )
        session.auth_key = client.session.auth_key
        session.save()
        await client.disconnect()

    def _switch_loaded_modules(self, old_id: int, new_id: int, suffix: int) -> list:
        moved = []
        for path in LOADED_MODULES_PATH.glob(f"*_{old_id}.py"):
            target = path.with_name(
                path.name.removesuffix(f"_{old_id}.py") + f"_{new_id}.py"
            )
            backup = None
            if target.exists():
                backup = self._archive_identity_file(target, suffix)

            record = [path, target, backup, False]
            moved.append(record)
            path.rename(target)
            record[3] = True

        return moved

    def _restore_loaded_modules(self, moved: list) -> None:
        for original, target, backup, renamed in reversed(moved):
            if renamed and target.exists() and not original.exists():
                target.rename(original)
            if backup and backup.exists():
                backup.rename(target)

    async def _switch_account(self, client: CustomTelegramClient) -> None:
        old_id = self.tg_id
        me = await client.get_me()
        if not me:
            raise RuntimeError("New session is not authorized")

        new_id = me.id
        if old_id == new_id:
            await main.hikkari.save_client_session(client, delay_restart=False)
            return

        suffix = int(time.time())
        base = Path(main.SESSIONS_DIR)
        old_session = base / f"hikkari-{old_id}.session"
        old_journal = base / f"hikkari-{old_id}.session-journal"
        old_config = Path(main.BASE_PATH) / f"config-{old_id}.json"
        new_session = base / f"hikkari-{new_id}.session"
        new_journal = base / f"hikkari-{new_id}.session-journal"
        new_config = Path(main.BASE_PATH) / f"config-{new_id}.json"
        new_files = {new_session, new_journal, new_config}
        redis = getattr(self._db, "_redis", None)
        redis_backup = None

        db_data = self._clone_switch_db(old_id, new_id)
        archived = []
        moved_modules = []

        try:
            if redis:
                redis_backup = await utils.run_sync(lambda: redis.get(str(new_id)))

            for path in (
                old_session,
                old_journal,
                old_config,
                new_session,
                new_journal,
                new_config,
            ):
                archived.append((path, self._archive_identity_file(path, suffix)))

            await self._copy_switch_db(new_id, db_data)
            await self._save_switch_session(client, new_id)
            moved_modules = self._switch_loaded_modules(old_id, new_id, suffix)
        except Exception:
            logger.exception("Account switch migration failed")
            if redis:
                if redis_backup is None:
                    await utils.run_sync(lambda: redis.delete(str(new_id)))
                else:
                    await utils.run_sync(lambda: redis.set(str(new_id), redis_backup))

            try:
                self._restore_loaded_modules(moved_modules)
            except Exception:
                logger.exception(
                    "Failed to restore loaded modules after switch failure"
                )

            for original, backup in reversed(archived):
                try:
                    self._restore_identity_file(
                        original,
                        backup,
                        original in new_files,
                    )
                except Exception:
                    logger.exception(
                        "Failed to restore %s after switch failure",
                        original,
                    )
            raise

    async def schedule_restart(self, call, client, is_switch: bool = False):
        await utils.answer(call, self.strings["login_successful"])
        # Yeah-yeah, ikr, but it's the only way to restart
        await asyncio.sleep(1)
        try:
            if is_switch:
                await self._switch_account(client)
                restart()
            else:
                await main.hikkari.save_client_session(client, delay_restart=False)
                restart()
        except Exception as e:
            logger.exception("Failed to finish inline login")
            await utils.answer(
                call,
                self.strings["switch_failed"].format(utils.escape_html(str(e))),
                reply_markup={"text": self.strings["btn_no"], "action": "close"},
            )

    async def inline_phone_handler(self, call, data, user, is_switch: bool = False):
        if not (phone := parse_phone(data)):
            await self._inline_login(call, user, after_fail=True, is_switch=is_switch)
            return

        client = self._get_client()

        await client.connect()
        try:
            await client.send_code_request(phone)
        except FloodWaitError as e:
            await utils.answer(
                call,
                self.strings["floodwait_error"].format(e.seconds),
                reply_markup={"text": self.strings["btn_no"], "action": "close"},
            )
            return
        except PhoneNumberInvalidError:
            await self._inline_login(call, user, after_fail=True, is_switch=is_switch)
            return

        reply_markup = {
            "text": self.strings["enter_code"],
            "input": self.strings["login_code"],
            "handler": self.inline_code_handler,
            "args": (
                client,
                phone,
                user,
                is_switch,
            ),
        }

        await utils.answer(
            call,
            self.strings["code_sent"],
            reply_markup=reply_markup,
            always_allow=[user.id],
        )

    async def inline_code_handler(
        self, call, data, client, phone, user, is_switch: bool = False
    ):
        _code_markup = {
            "text": self.strings["enter_code"],
            "input": self.strings["login_code"],
            "handler": self.inline_code_handler,
            "args": (
                client,
                phone,
                user,
                is_switch,
            ),
        }
        if not data or len(data) != 5:
            await utils.answer(
                call,
                self.strings["invalid_code"],
                reply_markup=_code_markup,
                always_allow=[user.id],
            )
            return

        if any(c not in string.digits for c in data):
            await utils.answer(
                call,
                self.strings["invalid_code_digits"],
                reply_markup=_code_markup,
                always_allow=[user.id],
            )
            return

        try:
            await client.sign_in(phone, code=data)
        except SessionPasswordNeededError:
            reply_markup = [
                {
                    "text": self.strings["enter_2fa"],
                    "input": self.strings["your_2fa"],
                    "handler": self.inline_2fa_handler,
                    "args": (
                        client,
                        phone,
                        user,
                        is_switch,
                    ),
                },
            ]
            await utils.answer(
                call,
                self.strings["2fa_enabled"],
                reply_markup=reply_markup,
                always_allow=[user.id],
            )
            return
        except PhoneCodeExpiredError:
            reply_markup = [
                {
                    "text": self.strings["request_code"],
                    "callback": self.inline_phone_handler,
                    "args": (phone, user, is_switch),
                }
            ]
            await utils.answer(
                call,
                self.strings["code_expired"],
                reply_markup=reply_markup,
                always_allow=[user.id],
            )
            return
        except PhoneCodeInvalidError:
            await utils.answer(
                call,
                self.strings["invalid_code"],
                reply_markup=_code_markup,
                always_allow=[user.id],
            )
            return
        except FloodWaitError as e:
            await utils.answer(
                call,
                self.strings["floodwait_error"].format(e.seconds),
                reply_markup={"text": self.strings["btn_no"], "action": "close"},
            )
            return

        asyncio.ensure_future(self.schedule_restart(call, client, is_switch=is_switch))

    @loader.command()
    async def switchacc(self, message: Message):
        if "JAMHOST" in os.environ:
            await utils.answer(message, self.strings["host_denied"])
            return

        user = await self._client.get_entity(self.tg_id)

        if "force_insecure" in message.raw_text.lower():
            await self._inline_login(message, user, is_switch=True)
            return

        try:
            if not await self.inline.form(
                self.strings["switch_confirm"],
                message=message,
                reply_markup=[
                    {
                        "text": self.strings["btn_yes"],
                        "callback": self._inline_login,
                        "args": (user, False, True),
                    },
                    {"text": self.strings["btn_no"], "action": "close"},
                ],
            ):
                raise RuntimeError("Inline form was not created")
        except Exception:
            await utils.answer(
                message,
                self.strings["switch_insecure"].format(
                    utils.escape_html(self.get_prefix())
                ),
            )

    async def inline_2fa_handler(
        self, call, data, client, phone, user, is_switch: bool = False
    ):
        _2fa_markup = {
            "text": self.strings["enter_2fa"],
            "input": self.strings["your_2fa"],
            "handler": self.inline_2fa_handler,
            "args": (
                client,
                phone,
                user,
                is_switch,
            ),
        }
        if not data:
            await utils.answer(
                call,
                self.strings["invalid_password"],
                reply_markup=_2fa_markup,
                always_allow=[user.id],
            )
            return

        try:
            await client.sign_in(phone, password=data)
        except PasswordHashInvalidError:
            await utils.answer(
                call,
                self.strings["invalid_password"],
                reply_markup=_2fa_markup,
                always_allow=[user.id],
            )
            return
        except FloodWaitError as e:
            await utils.answer(
                call,
                self.strings["floodwait_error"].format(e.seconds),
                reply_markup={"text": self.strings["btn_no"], "action": "close"},
            )
            return

        asyncio.ensure_future(self.schedule_restart(call, client, is_switch=is_switch))


    def _owner_only(self, message: Message) -> bool:
        """Only the primary account owner (this client), not co-owners."""
        uid = getattr(message, "sender_id", None) or 0
        return int(uid) == int(self.tg_id)

    def _list_session_ids(self) -> list[int]:
        ids: set[int] = set()
        sessions_dir = Path(main.SESSIONS_DIR)
        if sessions_dir.is_dir():
            for entry in sessions_dir.iterdir():
                name = entry.name
                if not (name.startswith("hikkari-") and name.endswith(".session")):
                    continue
                if name.endswith("-journal") or ".session-journal" in name:
                    continue
                raw = name[len("hikkari-") : -len(".session")]
                if raw.isdigit():
                    ids.add(int(raw))
        # live clients
        for client in getattr(self, "allclients", None) or []:
            with contextlib.suppress(Exception):
                tid = int(getattr(client, "tg_id", 0) or 0)
                if tid:
                    ids.add(tid)
        with contextlib.suppress(Exception):
            ids.add(int(self.tg_id))
        return sorted(ids)

    def _client_by_id(self, uid: int):
        for client in getattr(self, "allclients", None) or []:
            with contextlib.suppress(Exception):
                if int(getattr(client, "tg_id", 0) or 0) == int(uid):
                    return client
        return None

    @loader.command()
    async def acclist(self, message: Message):
        """List accounts connected to this userbot (primary owner only)"""
        if not self._owner_only(message):
            await utils.answer(message, self.strings["owner_only"])
            return

        ids = self._list_session_ids()
        if not ids:
            await utils.answer(message, self.strings["no_accounts"])
            return

        lines = []
        for uid in ids:
            live = self._client_by_id(uid) is not None
            mark = "<emoji document_id=5416081784641168838>🟢</emoji>" if live else "<emoji document_id=5411225014148014586>🔴</emoji>"
            current = " ← current" if uid == int(self.tg_id) else ""
            name = str(uid)
            client = self._client_by_id(uid)
            if client is not None:
                with contextlib.suppress(Exception):
                    me = getattr(client, "hikkari_me", None) or await client.get_me()
                    if me:
                        uname = f"@{me.username}" if getattr(me, "username", None) else ""
                        name = f"{utils.escape_html(me.first_name or '')} {uname}".strip()
            else:
                # try resolve offline
                with contextlib.suppress(Exception):
                    ent = await self._client.get_entity(uid)
                    uname = f"@{ent.username}" if getattr(ent, "username", None) else ""
                    name = f"{utils.escape_html(ent.first_name or '')} {uname}".strip()

            session_path = Path(main.SESSIONS_DIR) / f"hikkari-{uid}.session"
            cfg_path = main.BASE_PATH / f"config-{uid}.json"
            bits = []
            if session_path.exists():
                bits.append("session")
            if cfg_path.exists():
                bits.append("db")
            extra = f" [{', '.join(bits)}]" if bits else ""
            lines.append(
                self.strings["acc_line"].format(
                    mark=mark,
                    name=name or str(uid),
                    uid=uid,
                    current=current,
                    extra=extra,
                )
            )

        await utils.answer(
            message,
            self.strings["acc_list"].format(
                count=len(ids),
                lines="\n".join(lines),
            ),
        )

    @loader.command()
    async def accdel(self, message: Message):
        """Remove userbot from an account: close session, delete files, drop from list"""
        if not self._owner_only(message):
            await utils.answer(message, self.strings["owner_only"])
            return

        args = (utils.get_args_raw(message) or "").strip()
        force = "-f" in args.split() or "--force" in args.split()
        parts = [p for p in args.split() if p not in {"-f", "--force"}]
        if not parts:
            await utils.answer(message, self.strings["accdel_usage"])
            return

        target_raw = parts[0]
        target_id = None
        if target_raw.isdigit():
            target_id = int(target_raw)
        else:
            with contextlib.suppress(Exception):
                ent = await self._client.get_entity(target_raw)
                target_id = int(ent.id)

        if not target_id:
            await utils.answer(message, self.strings["acc_not_found"])
            return

        known = set(self._list_session_ids())
        if target_id not in known and not force:
            await utils.answer(message, self.strings["acc_not_found"])
            return

        if target_id == int(self.tg_id) and not force:
            await utils.answer(message, self.strings["accdel_current"])
            return

        await self.inline.form(
            message=message,
            text=self.strings["accdel_confirm"].format(uid=target_id),
            force_me=True,
            reply_markup=[
                [
                    {
                        "text": self.strings["btn_yes"],
                        "callback": self._accdel_run,
                        "args": (target_id,),
                    }
                ],
                [{"text": self.strings["btn_no"], "action": "close"}],
            ],
        )

    async def _accdel_run(self, call: InlineCall, target_id: int):
        if not self._owner_only(
            type("M", (), {"sender_id": getattr(getattr(call, "from_user", None), "id", self.tg_id)})()
        ):
            # only primary owner
            with contextlib.suppress(Exception):
                from_id = int(getattr(call.from_user, "id", 0))
                if from_id != int(self.tg_id):
                    await call.edit(self.strings["owner_only"])
                    return

        errors = []
        # 1) Disconnect live client
        client = self._client_by_id(target_id)
        if client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()
            # remove from allclients lists
            for holder in (getattr(self, "allclients", None), getattr(main.hikkari, "clients", None)):
                if holder is None:
                    continue
                with contextlib.suppress(Exception):
                    while client in holder:
                        holder.remove(client)
            with contextlib.suppress(Exception):
                sessions = getattr(main.hikkari, "sessions", None)
                if sessions is not None:
                    main.hikkari.sessions = [
                        s
                        for s in sessions
                        if not str(getattr(s, "filename", getattr(s, "_filename", ""))).endswith(
                            f"hikkari-{target_id}.session"
                        )
                        and f"hikkari-{target_id}" not in str(s)
                    ]

        # 2) Delete session files
        base = Path(main.SESSIONS_DIR)
        for path in (
            base / f"hikkari-{target_id}.session",
            base / f"hikkari-{target_id}.session-journal",
        ):
            try:
                if path.exists():
                    path.unlink()
            except Exception as e:
                errors.append(f"{path.name}: {e}")

        # 3) Delete per-account config/db
        cfg = main.BASE_PATH / f"config-{target_id}.json"
        try:
            if cfg.exists():
                cfg.unlink()
        except Exception as e:
            errors.append(f"config: {e}")

        # 4) Cannot fully unload current process account without exit
        if target_id == int(self.tg_id):
            await call.edit(self.strings["accdel_current_done"])
            return

        if errors:
            await call.edit(
                self.strings["accdel_partial"].format(
                    uid=target_id,
                    err=utils.escape_html("; ".join(errors)),
                )
            )
            return

        await call.edit(self.strings["accdel_done"].format(uid=target_id))

    @loader.command()
    async def weburl(self, message: Message):
        """Public WebUI login link via ngrok (owner only)"""
        if not self._owner_only(message):
            await utils.answer(message, self.strings["owner_only"])
            return

        status = await utils.answer(
            message,
            "<emoji document_id=5283176512747507510>✨</emoji> <b>WebUI…</b>\n"
            "Поднимаю ngrok-туннель…",
        )
        try:
            from ..web_auth import WebAuth
            from .._internal import restart
            from ..version import __version__
            import os

            tok = str(self.config.get("ngrok_token") or "").strip().strip('"').strip("'")
            if not tok:
                tok = (os.environ.get("NGROK_AUTHTOKEN") or os.environ.get("NGROK_TOKEN") or "").strip()
            # also from global config.json
            if not tok:
                with contextlib.suppress(Exception):
                    tok = str(main.get_config_key("ngrok_token") or "").strip()
            if not tok:
                await utils.answer(
                    status,
                    "🚫 <b>Нужен ngrok_token</b>\n\n"
                    "<code>.cfg HikkariAccounts</code> → <code>ngrok_token</code>\n"
                    "или <code>export NGROK_AUTHTOKEN=…</code>\n"
                    "https://dashboard.ngrok.com",
                )
                return

            os.environ["NGROK_AUTHTOKEN"] = tok
            web = WebAuth(
                main.hikkari.api_token.ID,
                main.hikkari.api_token.HASH,
                proxy=getattr(main.hikkari, "proxy", None),
                connection=getattr(main.hikkari, "conn", None),
                device_model="Hikkari",
                app_version=".".join(map(str, __version__)),
                need_api=False,
            )
            web.weburl_mode = "ngrok"
            web.ngrok_token = tok
            web.require_token = True
            await web.start_server()
            public = await web.start_tunnel(retries=3)
            if not public:
                await web.stop()
                errs = getattr(web, "_tunnel_errors", []) or []
                await utils.answer(
                    status,
                    "🚫 <b>ngrok не поднялся</b>\n"
                    + ("<code>" + utils.escape_html(" | ".join(errs[:4])) + "</code>" if errs else ""),
                )
                return

            href = utils.escape_html(public)
            await utils.answer(
                status,
                "<emoji document_id=5283176512747507510>✨</emoji> <b>Hikkari WebUI</b>\n\n"
                f'<a href="{href}">✨ WebUI Hikkari</a>\n'
                f"<code>{href}</code>\n\n"
                "<i>ngrok · ~15 мин</i>",
                parse_mode="HTML",
                link_preview=False,
            )

            async def _wait():
                try:
                    await asyncio.wait_for(web.done.wait(), timeout=900)
                except asyncio.TimeoutError:
                    await web.stop()
                    return
                if not web.success or web.client is None:
                    await web.stop()
                    return
                client = web.client
                await web.stop()
                try:
                    me = await client.get_me()
                    client._tg_id = me.id
                    client.tg_id = me.id
                    client.hikka_me = me
                    client.hikkari_me = me
                    await main.hikkari.save_client_session(client, delay_restart=False)
                    await asyncio.sleep(1)
                    restart()
                except Exception:
                    logger.exception("weburl save")

            asyncio.ensure_future(_wait())
        except Exception as e:
            logger.exception("weburl")
            await utils.answer(
                status,
                f"🚫 <b>WebUI error:</b> <code>{utils.escape_html(str(e))}</code>",
            )

