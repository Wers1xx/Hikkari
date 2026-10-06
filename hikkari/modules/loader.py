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

"""Loads and registers modules"""

import ast
import asyncio
import contextlib
import difflib
import functools
import importlib
import inspect
import io
import logging
import os
import re
import shutil
import sys
import time
import typing
import uuid
from collections import ChainMap
from importlib.machinery import ModuleSpec
from urllib.parse import urlparse

import requests
from hikkaritl.tl.custom import Message
from hikkaritl.errors.common import ScamDetectionError
from hikkaritl.errors.rpcerrorlist import MediaCaptionTooLongError
from hikkaritl.tl.functions.channels import JoinChannelRequest
from hikkaritl.tl.types import Channel, InputMediaWebPage

from .. import loader, main, utils
from .._local_storage import RemoteStorage
from ..inline.types import InlineCall
from ..types import CoreOverwriteError, CoreUnloadError

logger = logging.getLogger(__name__)


class FakeOne:
    def __eq__(self, other):
        return other == -1 or isinstance(other, FakeOne)

    def __bool__(self):
        return False


MODULE_LOADING_FORBIDDEN = FakeOne()
MODULE_LOADING_FAILED = 0
MODULE_LOADING_SUCCESS = 1


class ModuleInstallError(RuntimeError):
    """Raised when an external module install fails after download."""


@loader.tds
class LoaderMod(loader.Module):
    """Loads modules"""

    strings = {
        "name": "Loader",
    }

    def __init__(self):
        self.fully_loaded = False
        self._links_cache = {}
        self._storage: RemoteStorage = None

        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "MODULES_REPO",
                "https://raw.githubusercontent.com/Wersixx/Wers1xx/main",
                lambda: self.strings["repo_config_doc"],
                validator=loader.validators.Link(),
            ),
            loader.ConfigValue(
                "ADDITIONAL_REPOS",
                [],
                lambda: self.strings["add_repo_config_doc"],
                validator=loader.validators.Series(validator=loader.validators.Link()),
            ),
            loader.ConfigValue(
                "share_link",
                doc=lambda: self.strings["share_link_doc"],
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "basic_auth",
                None,
                lambda: self.strings["basic_auth_doc"],
                validator=loader.validators.Hidden(
                    loader.validators.RegExp(r"^.*:.*$")
                ),
            ),
            loader.ConfigValue(
                "command_emoji",
                "<tg-emoji emoji-id=5197195523794157505>▫️</tg-emoji>",
                lambda: "Emoji for command",
            ),
            loader.ConfigValue(
                "show_banner",
                True,
                lambda: self.strings["show_banner_doc"],
                validator=loader.validators.Boolean(),
            ),
        )

    async def _async_init(self):
        modules = list(
            filter(
                lambda x: not x.startswith(
                    "https://raw.githubusercontent.com/Wersixx/Wers1xx/main"
                ),
                utils.array_sum(
                    map(
                        lambda x: list(x.values()),
                        (await self.get_repo_list()).values(),
                    )
                ),
            )
        )
        logger.debug("Modules: %s", modules)
        asyncio.ensure_future(self._storage.preload(modules))

    async def client_ready(self):
        # Force modules repo migration (old Wers1xx/modules → Wersixx/Wers1xx)
        try:
            repo = str(self.config.get("MODULES_REPO") or "")
            if "Wers1xx/modules" in repo or not repo.strip():
                self.config["MODULES_REPO"] = "https://raw.githubusercontent.com/Wersixx/Wers1xx/main"
                self._links_cache.clear()
                logger.info("MODULES_REPO migrated to Wersixx/Wers1xx")
        except Exception:
            logger.exception("MODULES_REPO migrate")

        while not (settings := self.lookup("settings")):
            await asyncio.sleep(0.5)

        self._storage = RemoteStorage(self._client)

        self.allmodules.add_aliases(settings.get("aliases", {}))

        main.hikkari.ready.set()

        asyncio.ensure_future(self._update_modules())
        asyncio.ensure_future(self._async_init())

    @loader.loop(interval=3, wait_before=True, autostart=True)
    async def _config_autosaver(self):
        for mod in self.allmodules.modules:
            if (
                not hasattr(mod, "config")
                or not mod.config
                or not isinstance(mod.config, loader.ModuleConfig)
            ):
                continue

            for option, config in mod.config._config.items():
                if not hasattr(config, "_save_marker"):
                    continue

                delattr(mod.config._config[option], "_save_marker")
                mod.pointer("__config__", {})[option] = config.value

        for lib in self.allmodules.libraries:
            if (
                not hasattr(lib, "config")
                or not lib.config
                or not isinstance(lib.config, loader.ModuleConfig)
            ):
                continue

            for option, config in lib.config._config.items():
                if not hasattr(config, "_save_marker"):
                    continue

                delattr(lib.config._config[option], "_save_marker")
                lib._lib_pointer("__config__", {})[option] = config.value

        self._db.save()

    def update_modules_in_db(self):
        if self.allmodules.secure_boot:
            return

        self.set(
            "loaded_modules",
            {
                **{
                    module.__class__.__name__: module.__origin__
                    for module in self.allmodules.modules
                    if module.__origin__.startswith("http")
                },
            },
        )

    def _get_banner_url(self, doc: str) -> str | None:
        match = re.search(r"# ?meta banner: ?(.+)", doc)
        return match.group(1).strip() if match else None

    def _repo_to_label(self, repo: str) -> str:
        parsed = urlparse(repo)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return repo

    async def _check_pass(self, message: Message | InlineCall) -> bool:
        if self.lookup("LoaderRestrictor").get("passed", False):
            return False

        await utils.answer(
            message,
            self.strings["verify_required"].format(self.inline.bot_username),
        )
        return True


    async def _gather_module_files(self, message: Message) -> list[Message]:
        """Collect all module documents from message or reply (incl. albums)."""
        base = message if getattr(message, "file", None) else await message.get_reply_message()
        if base is None:
            return []
        out: list[Message] = []
        gid = getattr(base, "grouped_id", None)
        if gid:
            try:
                chat = utils.get_chat_id(base)
                # fetch nearby messages in the same album
                ids = list(range(max(1, base.id - 15), base.id + 16))
                msgs = await self._client.get_messages(chat, ids=ids)
                for m in msgs:
                    if (
                        m
                        and getattr(m, "grouped_id", None) == gid
                        and getattr(m, "file", None)
                    ):
                        out.append(m)
            except Exception:
                logger.debug("album gather failed", exc_info=True)
        if not out and getattr(base, "file", None):
            out = [base]
        # de-dupe by id, preserve order
        seen = set()
        uniq = []
        for m in out:
            if m.id not in seen:
                seen.add(m.id)
                uniq.append(m)
        return uniq

    def _module_cmds_rows(self, instance) -> list[tuple[str, str]]:
        rows = []
        prefix = utils.escape_html(self.get_prefix())
        for name, fun in sorted(getattr(instance, "commands", {}).items(), key=lambda x: x[0]):
            doc = utils.escape_html(inspect.getdoc(fun) or self.strings.get("undoc", ""))
            rows.append((f"{prefix}{name}", doc[:120]))
        if self.inline.init_complete:
            for name, fun in sorted(
                getattr(instance, "inline_handlers", {}).items(), key=lambda x: x[0]
            ):
                doc = utils.escape_html(inspect.getdoc(fun) or self.strings.get("undoc", ""))
                rows.append((f"@{self.inline.bot_username} {name}", doc[:120]))
        return rows

    async def _rich_module_loaded(
        self,
        message: Message,
        *,
        modname: str,
        mod_doc: str,
        rows: list[tuple[str, str]],
        subscribe_markup=None,
        origin: str = "",
    ) -> bool:
        """Announce single module install as Rich (details + buttons)."""
        try:
            from ..utils.rich import can_use_rich
            from ..utils.rich_api import html_table
            if not can_use_rich(self._client, self._db):
                return False
            if not getattr(self.inline, "init_complete", False):
                return False
            parts = [f"<h2>{utils.escape_html(modname)}</h2>"]
            if mod_doc:
                plain = re.sub(r"<[^>]+>", "", mod_doc).strip()
                if plain:
                    parts.append(f"<p><i>{utils.escape_html(plain)[:400]}</i></p>")
            if rows:
                table = html_table(rows, header=("Command", "Description"))
                parts.append(
                    f"<details open><summary><b>Commands</b> ({len(rows)})</summary>\n"
                    f"{table}\n</details>"
                )
            if origin and origin not in ("<string>",):
                parts.append(f"<p><code>{utils.escape_html(str(origin)[:120])}</code></p>")
            html = "\n".join(parts)
            m = await self.inline.rich(
                message,
                html,
                title=f"✓ {modname}"[:64],
                description="Module loaded",
                silent=True,
                reply_markup=subscribe_markup,
            )
            return bool(m)
        except Exception:
            logger.debug("loader rich single failed", exc_info=True)
            return False

    async def _rich_batch_loaded(
        self,
        message: Message,
        results: list[dict],
    ) -> bool:
        """Batch install summary as Rich with details per module."""
        try:
            from ..utils.rich import can_use_rich
            from ..utils.rich_api import html_table
            if not can_use_rich(self._client, self._db):
                return False
            if not getattr(self.inline, "init_complete", False):
                return False
            ok = [r for r in results if r.get("ok")]
            fail = [r for r in results if not r.get("ok")]
            parts = [
                f"<h2>Installed {len(ok)}/{len(results)}</h2>",
            ]
            if fail:
                parts.append(
                    "<p>Failed: "
                    + ", ".join(utils.escape_html(r.get("name", "?")) for r in fail)
                    + "</p>"
                )
            for r in ok:
                name = utils.escape_html(r.get("name", "module"))
                rows = r.get("rows") or []
                body = ""
                if rows:
                    body = html_table(rows, header=("Command", "Description"))
                doc = utils.escape_html((r.get("doc") or "")[:200])
                inner = f"<p><i>{doc}</i></p>\n{body}" if doc else body
                parts.append(
                    f"<details><summary><b>{name}</b> ({len(rows)} cmds)</summary>\n"
                    f"{inner}\n</details>"
                )
            html = "\n".join(parts)
            m = await self.inline.rich(
                message,
                html,
                title=f"Loaded {len(ok)} modules",
                description="Batch install",
                silent=True,
            )
            return bool(m)
        except Exception:
            logger.debug("loader rich batch failed", exc_info=True)
            return False


    @loader.command(alias="dlm")
    async def dlmod(self, message: Message, force_pm: bool = False):
        if await self._check_pass(message):
            return

        if args := utils.get_args(message):
            match args:
                case [single]:
                    args = single
                    await utils.answer(message, self.strings["finding_module_in_repos"])
                    if (
                        await self.download_and_install(args, message, force_pm)
                        == MODULE_LOADING_FORBIDDEN
                    ):
                        return

                    if self.fully_loaded:
                        self.update_modules_in_db()
                case _:
                    not_installed = []
                    batch: list[dict] = []
                    await utils.answer(
                        message,
                        f"⏳ Installing <b>{len(args)}</b> modules…",
                        skip_rich=True,
                    )
                    for arg in args:
                        self._last_loaded = None
                        # quiet path via temporary flag
                        self._quiet_install = True
                        try:
                            result = await self.download_and_install(arg)
                        finally:
                            self._quiet_install = False
                        info = getattr(self, "_last_loaded", None) or {}
                        if result in (MODULE_LOADING_FAILED, MODULE_LOADING_FORBIDDEN):
                            not_installed.append(arg)
                            batch.append(
                                {"name": str(arg), "ok": False, "rows": [], "doc": ""}
                            )
                        else:
                            batch.append(
                                {
                                    "name": info.get("name") or str(arg),
                                    "ok": True,
                                    "rows": info.get("rows") or [],
                                    "doc": info.get("doc") or "",
                                }
                            )
                    if not await self._rich_batch_loaded(message, batch):
                        text = (
                            f"✅ Installed <b>{len(args) - len(not_installed)}"
                            f"/{len(args)}</b>"
                        )
                        if not_installed:
                            text += (
                                "\n\n❌ <code>"
                                + "</code>, <code>".join(
                                    utils.escape_html(str(x)) for x in not_installed
                                )
                                + "</code>"
                            )
                        await utils.answer(message, text, skip_rich=True)

                    if self.fully_loaded:
                        self.update_modules_in_db()
        else:
            await self.inline.list(
                message,
                [
                    self.strings["avail_header"]
                    + f"\n☁️ {repo.strip('/')}\n\n"
                    + "\n".join(
                        [
                            " | ".join(chunk)
                            for chunk in utils.chunks(
                                [
                                    f"<code>{i}</code>"
                                    for i in sorted(
                                        [
                                            utils.escape_html(
                                                i.split("/")[-1].split(".")[0]
                                            )
                                            for i in mods.values()
                                        ]
                                    )
                                ],
                                5,
                            )
                        ]
                    )
                    for repo, mods in (await self.get_repo_list()).items()
                ],
            )

    @loader.command()
    async def dlmall(self, message: Message):
        if await self._check_pass(message):
            return

        repos = [self.config["MODULES_REPO"]] + self.config["ADDITIONAL_REPOS"]
        repos = [r for r in repos if r.startswith("http")]
        buttons = [
            [
                {
                    "text": self._repo_to_label(repo),
                    "callback": self._inline__install_all_from_repo,
                    "args": (repo,),
                }
            ]
            for repo in repos
        ]
        buttons.append(
            [
                {
                    "text": "🔻 Close",
                    "action": "close",
                }
            ]
        )
        await self.inline.form(
            self.strings["choose_repo"],
            message,
            reply_markup=buttons,
        )

    async def _inline__install_all_from_repo(
        self,
        call: InlineCall,
        repo: str,
    ):
        await call.edit(self.strings["installing_all_from_repo"])

        links = await self._get_repo(repo)

        if not links:
            await call.edit(self.strings["dlm_all_from_repo_error_nomods"])
            return

        not_installed = []

        for link in links:
            full_url = f"{repo.strip('/')}/{link}.py"
            result = await self.download_and_install(full_url)
            if result != MODULE_LOADING_SUCCESS:
                not_installed.append(link.split("/")[-1])

        installed_count = len(links) - len(not_installed)

        if installed_count == 0:
            await call.edit(self.strings["dlm_all_from_repo_error_nomods"])
        elif not_installed:
            failed_list = "\n".join(not_installed)
            await call.edit(
                self.strings["dlm_all_from_repo_error_somemods"]
                + "<blockquote expandable>"
                + failed_list
                + "</blockquote>"
            )
        else:
            await call.edit(self.strings["installed_all_from_repo"])

        if self.fully_loaded:
            self.update_modules_in_db()

    async def _get_modules_to_load(self):
        todo = self.get("loaded_modules", {})
        logger.debug("Loading modules: %s", todo)
        return todo

    async def _get_repo(self, repo: str) -> list:
        repo = (repo or "").strip().rstrip("/")
        # migrate old default repo
        if "Wers1xx/modules" in repo:
            repo = "https://raw.githubusercontent.com/Wersixx/Wers1xx/main"
            with contextlib.suppress(Exception):
                self.config["MODULES_REPO"] = repo

        if self._links_cache.get(repo, {}).get("exp", 0) >= time.time():
            return self._links_cache[repo]["data"]

        urls = [
            f"{repo}/full.txt",
            f"{repo}/full.txt?raw=1",
        ]
        res = None
        last_code = None
        for url in urls:
            res = await utils.run_sync(
                requests.get,
                url,
                timeout=30,
                auth=(
                    tuple(self.config["basic_auth"].split(":", 1))
                    if self.config["basic_auth"]
                    else None
                ),
            )
            last_code = res.status_code
            if str(res.status_code).startswith("2") and (res.text or "").strip():
                break
        else:
            logger.warning(
                "Can't load repo %s full.txt (HTTP %s)",
                repo,
                last_code,
            )
            return []

        lines = []
        for raw in (res.text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            link = raw.strip().lstrip("\ufeff")
            if not link or link.startswith("#"):
                continue
            # full.txt may list "Name.py" or "Name"
            if link.endswith(".py"):
                link = link[:-3]
            # skip broken names with path traversal
            if "/" in link or "\\" in link or ".." in link:
                # allow subdirs: keep as relative path without .py
                link = link.replace("\\", "/").strip("/")
                if link.endswith(".py"):
                    link = link[:-3]
            lines.append(link)

        logger.info("Repo %s: %s modules from full.txt", repo, len(lines))
        self._links_cache[repo] = {
            "exp": time.time() + 5 * 60,
            "data": lines,
        }
        return lines

    async def get_repo_list(
        self,
        only_primary: bool = False,
    ) -> dict:
        return {
            repo: {
                f"Mod/{repo_id}/{i}": f'{repo.strip("/")}/{link}.py'
                for i, link in enumerate(set(await self._get_repo(repo)))
            }
            for repo_id, repo in enumerate(
                [self.config["MODULES_REPO"]]
                + ([] if only_primary else self.config["ADDITIONAL_REPOS"])
            )
            if repo.startswith("http")
        }

    async def get_links_list(self) -> list[str]:
        links = await self.get_repo_list()
        main_repo = list(links.pop(self.config["MODULES_REPO"]).values())
        return main_repo + list(dict(ChainMap(*list(links.values()))).values())

    async def _find_link(self, module_name: str) -> str | bool:
        return next(
            filter(
                lambda link: link.lower().endswith(f"/{module_name.lower()}.py"),
                await self.get_links_list(),
            ),
            False,
        )

    async def download_and_install(
        self,
        module_name: str,
        message: Message | None = None,
        force_pm: bool = False,
    ) -> int:
        try:
            blob_link = False
            module_name = module_name.strip()
            if urlparse(module_name).netloc:
                url = module_name
                if re.match(
                    r"^(https:\/\/github\.com\/.*?\/.*?\/blob\/.*\.py)|"
                    r"(https:\/\/gitlab\.com\/.*?\/.*?\/-\/blob\/.*\.py)$",
                    url,
                ):
                    url = url.replace("/blob/", "/raw/")
                    blob_link = True
            else:
                url = await self._find_link(module_name)

                if not url:
                    logger.warning(
                        "Module %s was not found in configured repos", module_name
                    )
                    if message is not None:
                        await utils.answer(message, self.strings["no_module"])

                    return MODULE_LOADING_FAILED

            if message and not getattr(self, "_quiet_install", False):
                message = await utils.answer(
                    message,
                    self.strings["installing"].format(module_name),
                    skip_rich=True,
                )

            try:
                r = await self._storage.fetch(url, auth=self.config["basic_auth"])
            except requests.exceptions.HTTPError as e:
                logger.warning(
                    "Failed to download module %s from %s: %s",
                    module_name,
                    url,
                    e,
                )
                if message is not None:
                    await utils.answer(message, self.strings["no_module"])

                return MODULE_LOADING_FAILED

            installed = await self.load_module(
                r,
                message,
                module_name,
                url,
                blob_link=blob_link,
                _raise_install_errors=True,
            )

            if not installed:
                raise ModuleInstallError(f"Module {module_name} was not installed")

            return MODULE_LOADING_SUCCESS
        except Exception:
            logger.exception("Failed to install external module %s", module_name)
            return MODULE_LOADING_FAILED

    async def _inline__load(
        self,
        call: InlineCall,
        doc: str,
        path_: str,
        mode: str,
    ):
        if await self._check_pass(call):
            return

        await self.load_module(doc, call, origin=path_ or "<string>", save_fs=True)

    @loader.command(alias="lm")
    async def loadmod(self, message: Message):
        if await self._check_pass(message):
            return

        files = await self._gather_module_files(message)
        if not files:
            await utils.answer(message, self.strings["provide_module"])
            return

        await utils.answer(
            message,
            self.strings["loading_module_via_file"]
            if len(files) == 1
            else f"⏳ Installing <b>{len(files)}</b> modules…",
            skip_rich=True,
        )

        batch: list[dict] = []
        quiet = len(files) > 1
        for msg in files:
            try:
                raw = await msg.download_media(bytes)
                if raw is None:
                    batch.append({"name": f"id:{msg.id}", "ok": False, "rows": [], "doc": ""})
                    continue
                try:
                    doc = raw.decode()
                except UnicodeDecodeError:
                    batch.append({"name": f"id:{msg.id}", "ok": False, "rows": [], "doc": "bad unicode"})
                    continue
                fname = getattr(getattr(msg, "file", None), "name", None) or f"file_{msg.id}"
                ok = await self.load_module(
                    doc, message, origin=str(fname), save_fs=True, quiet=quiet
                )
                info = getattr(self, "_last_loaded", None) or {}
                batch.append(
                    {
                        "name": info.get("name") or fname,
                        "ok": bool(ok),
                        "rows": info.get("rows") or [],
                        "doc": info.get("doc") or "",
                    }
                )
            except Exception:
                logger.exception("loadmod file failed")
                batch.append({"name": f"id:{msg.id}", "ok": False, "rows": [], "doc": ""})

        if quiet:
            if not await self._rich_batch_loaded(message, batch):
                ok_n = sum(1 for r in batch if r.get("ok"))
                await utils.answer(
                    message,
                    f"✅ Installed <b>{ok_n}/{len(batch)}</b> modules",
                    skip_rich=True,
                )

    async def approve_internal(
        self,
        call: InlineCall,
        channel: "hints.EntityLike",  # type: ignore  # noqa
        event: asyncio.Event,
    ):
        """
        Don't you dare call it externally
        """
        await self._client(JoinChannelRequest(channel))
        event.status = True
        event.set()

        await call.edit(
            (
                "💫 <b>Joined <a"
                f' href="https://t.me/{channel.username}">{utils.escape_html(channel.title)}</a></b>'
            ),
        )

    async def install_requirements(self, requirements: list):
        is_venv = hasattr(sys, "real_prefix") or sys.prefix != getattr(
            sys, "base_prefix", sys.prefix
        )
        need_user_flag = loader.USER_INSTALL and not is_venv

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
            *(["--user"] if need_user_flag else []),
            *requirements,
        ]

        utils.ensure_child_watcher()
        try:
            pip = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            out, err = await pip.communicate()
        except Exception:
            logger.exception("Pip requirements install failed to start: %s", cmd)
            return False

        if pip.returncode != 0:
            logger.error(
                "Pip requirements install failed (%s) with exit code %s: %s",
                " ".join(cmd),
                pip.returncode,
                (err or out).decode(errors="ignore").strip() or "<no output>",
            )
            return False

        return True

    async def install_packages(self, packages: list):
        try:
            is_root = os.geteuid() == 0

            def _which(names):
                for n in names:
                    p = shutil.which(n)
                    if p:
                        return p
                return None

            pm = None
            if _which(["apt", "apt-get"]):
                pm = "apt"
            elif _which(["apk"]):
                pm = "apk"
            elif _which(["dnf"]):
                pm = "dnf"
            elif _which(["yum"]):
                pm = "yum"
            elif _which(["pacman"]):
                pm = "pacman"
            elif _which(["brew"]):
                pm = "brew"

            if not pm:
                logger.error(
                    "Can't install system packages %s: no supported package manager found",
                    packages,
                )
                return False

            cmd = []
            if pm == "apt":
                tool = _which(["apt", "apt-get"])
                cmd = [tool, "install", "-y", *packages]
            elif pm == "apk":
                cmd = ["apk", "add", "--no-cache", *packages]
            elif pm == "dnf":
                cmd = ["dnf", "install", "-y", *packages]
            elif pm == "yum":
                cmd = ["yum", "install", "-y", *packages]
            elif pm == "pacman":
                cmd = ["pacman", "-Syu", "--noconfirm", *packages]
            elif pm == "brew":
                cmd = ["brew", "install", *packages]

            if not is_root and shutil.which("sudo"):
                cmd = ["sudo", *cmd]

            utils.ensure_child_watcher()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            out, err = await proc.communicate()

            if proc.returncode != 0:
                logger.error(
                    "System package install failed (%s) with exit code %s: %s",
                    " ".join(cmd),
                    proc.returncode,
                    err.decode(errors="ignore") if err else out.decode(errors="ignore"),
                )
                return False

            return True
        except Exception:
            logger.exception("install_packages failed")
            return False


    # --- Module safety scanner -------------------------------------------------
    _BLOCK_PATTERNS = [
        (r"\bDeleteAccountRequest\b", "DeleteAccountRequest — удаление аккаунта"),
        (r"\baccount\.DeleteAccount\b", "account.DeleteAccount — удаление аккаунта"),
        (r"\bfunctions\.account\.DeleteAccount\b", "functions.account.DeleteAccount"),
        (r"\bResetAuthorizationsRequest\b", "ResetAuthorizations — снос всех сессий"),
        (r"\bauth\.ResetAuthorizations\b", "auth.ResetAuthorizations — снос сессий"),
        (r"\bfunctions\.auth\.ResetAuthorizations\b", "functions.auth.ResetAuthorizations"),
        (r"\bResetAuthorizationRequest\b", "ResetAuthorization — снос сессии"),
        (r"\bLogOutRequest\b", "LogOutRequest — выход из аккаунта"),
        (r"\bfunctions\.auth\.LogOut\b", "functions.auth.LogOut"),
        (r"\bauth\.LogOut\b", "auth.LogOut"),
        (r"\.log_out\s*\(", "client.log_out() — выход из аккаунта"),
        (r"\bResetLoginEmailRequest\b", "ResetLoginEmail"),
        (r"delete[_ ]account", "Упоминание delete account"),
        (r"unlink\s*\([^)]*\.session", "Удаление .session файла"),
        (r"os\.remove\s*\([^)]*\.session", "os.remove сессии"),
        (r"\.session[\"']\s*\)\.unlink", "Path.unlink сессии"),
        (r"shutil\.rmtree\s*\([^)]*sessions", "rmtree sessions/"),
        (r"DestroySession|destroy_session", "Destroy session"),
    ]

    _WARN_PROFILE = [
        (r"\bUpdateProfileRequest\b", "UpdateProfile — изменение профиля"),
        (r"\baccount\.UpdateProfile\b", "account.UpdateProfile"),
        (r"\bUpdateUsernameRequest\b", "UpdateUsername — смена юзернейма"),
        (r"\baccount\.UpdateUsername\b", "account.UpdateUsername"),
        (r"\bUploadProfilePhotoRequest\b", "UploadProfilePhoto — аватар"),
        (r"\bphotos\.UploadProfilePhoto\b", "photos.UploadProfilePhoto"),
        (r"\bDeletePhotosRequest\b", "DeletePhotos — удаление фото профиля"),
        (r"\bphotos\.DeletePhotos\b", "photos.DeletePhotos"),
        (r"\bUpdatePersonalChannelRequest\b", "UpdatePersonalChannel"),
        (r"UpdatePasswordSettings|edit_2fa", "Изменение 2FA/пароля"),
    ]

    _WARN_CORE = [
        (r"allmodules\.modules", "Доступ к allmodules.modules"),
        (r"unload_module\s*\(", "Вызов unload_module"),
        (r"register_module\s*\(", "Вызов register_module"),
        (r"CoreOverwriteError|core.?overwrite", "Перезапись ядра"),
        (r"sys\.modules\s*\[\s*['\"]hikkari", "Подмена sys.modules hikkari"),
        (r"importlib\.reload\s*\(.*hikkari", "importlib.reload ядра"),
        (r"hikkari/modules/(?:loader|main|dispatcher|security)", "Правка встроенных файлов"),
        (r"open\s*\([^)]*hikkari/modules", "Запись в hikkari/modules"),
        (r"LOADED_MODULES_DIR", "Манипуляции LOADED_MODULES_DIR"),
        (r"__builtins__\s*=", "Подмена __builtins__"),
    ]

    _WARN_SPAM = [
        (r"while\s+True[\s\S]{0,400}send_message\s*\(", "Цикл while True + send_message"),
        (r"for\s+\w+\s+in\s+[\s\S]{0,300}send_message\s*\(", "Цикл for + send_message"),
        (r"async def client_ready[\s\S]{0,1500}(?:send_message|forward_messages)\s*\(", "Автоотправка в client_ready"),
        (r"mass.?send|auto.?spam|flood.?spam|spam.?bot", "Признаки спам-модуля"),
        (r"InviteToChannelRequest[\s\S]{0,200}for\s+", "Массовый инвайт"),
    ]

    def _scan_module_safety(self, doc: str) -> tuple[list, list]:
        """Return (block_reasons, warn_reasons) from static source scan."""
        if not doc:
            return [], []
        # strip strings/comments roughly to reduce false positives on docs
        src = doc
        blocked, warns = [], []
        seen = set()

        def add(lst, reason):
            if reason not in seen:
                seen.add(reason)
                lst.append(reason)

        for pat, reason in self._BLOCK_PATTERNS:
            if re.search(pat, src, re.I | re.M):
                add(blocked, reason)

        for pat, reason in self._WARN_PROFILE:
            if re.search(pat, src, re.I | re.M):
                add(warns, f"Профиль: {reason}")

        for pat, reason in self._WARN_CORE:
            if re.search(pat, src, re.I | re.M):
                add(warns, f"Ядро: {reason}")

        for pat, reason in self._WARN_SPAM:
            if re.search(pat, src, re.I | re.M):
                add(warns, f"Спам: {reason}")

        return blocked, warns

    async def _inline__safety_install(
        self,
        call: InlineCall,
        doc: str,
        name: str | None,
        origin: str,
        save_fs: bool,
        blob_link: bool,
    ):
        await call.edit(self.strings["safety_installing"])
        ok = await self.load_module(
            doc,
            call,
            name=name,
            origin=origin or "<string>",
            save_fs=save_fs,
            blob_link=blob_link,
            _safety_confirmed=True,
        )
        if ok:
            with contextlib.suppress(Exception):
                await call.edit(self.strings["safety_installed_ok"])
        else:
            with contextlib.suppress(Exception):
                await call.edit(self.strings["load_failed"])


    async def load_module(
        self,
        doc: str,
        message: Message,
        name: str | None = None,
        origin: str = "<string>",
        did_requirements: bool = False,
        save_fs: bool = True,
        blob_link: bool = False,
        did_requires: bool = False,
        did_packages: bool = False,
        _raise_install_errors: bool = False,
        _safety_confirmed: bool = False,
        quiet: bool = False,
    ) -> bool:
        module_label = name or origin

        if isinstance(doc, (bytes, bytearray)):
            try:
                doc = doc.decode("utf-8")
            except Exception:
                doc = doc.decode("utf-8", errors="ignore")

        if isinstance(doc, str) and not _safety_confirmed:
            blocked, warns = self._scan_module_safety(doc)
            if blocked:
                logger.warning(
                    "Module %s blocked by safety scanner: %s",
                    module_label,
                    blocked,
                )
                if isinstance(message, Message):
                    await utils.answer(
                        message,
                        self.strings["safety_blocked"].format(
                            name=utils.escape_html(str(module_label)),
                            reasons="\n".join(
                                f"• {utils.escape_html(r)}" for r in blocked
                            ),
                        ),
                    )
                return False
            if warns and isinstance(message, Message):
                await self.inline.form(
                    self.strings["safety_warn"].format(
                        name=utils.escape_html(str(module_label)),
                        reasons="\n".join(
                            f"• {utils.escape_html(r)}" for r in warns
                        ),
                    ),
                    message,
                    reply_markup=[
                        [
                            {
                                "text": self.strings["safety_install_anyway"],
                                "callback": self._inline__safety_install,
                                "args": (doc, name, origin, save_fs, blob_link),
                            }
                        ],
                        [
                            {
                                "text": self.strings["safety_cancel"],
                                "action": "close",
                            }
                        ],
                    ],
                )
                return False

        if any(
            line.replace(" ", "") == "#scope:ffmpeg" for line in doc.splitlines()
        ) and os.system("ffmpeg -version 1>/dev/null 2>/dev/null"):
            logger.error(
                "Module %s requires ffmpeg, but ffmpeg is not installed",
                module_label,
            )
            if isinstance(message, Message):
                await utils.answer(message, self.strings["ffmpeg_required"])
            return False

        if (
            any(line.replace(" ", "") == "#scope:inline" for line in doc.splitlines())
            and not self.inline.init_complete
        ):
            logger.error(
                "Module %s requires inline mode, but inline initialization failed",
                module_label,
            )
            if isinstance(message, Message):
                await utils.answer(message, self.strings["inline_init_failed"])
            return False

        if re.search(r"# ?scope: ?hikkari_min", doc):
            ver = re.search(r"# ?scope: ?hikkari_min ((?:\d+\.){2}\d+)", doc).group(1)
            ver_ = tuple(map(int, ver.split(".")))
            if main.__version__ < ver_:
                logger.error(
                    "Module %s requires Hikkari %s, current version is %s",
                    module_label,
                    ver,
                    ".".join(map(str, main.__version__)),
                )
                if isinstance(message, Message):
                    if getattr(message, "file", None):
                        m = utils.get_chat_id(message)
                        await message.edit("")
                    else:
                        m = message

                    await self.inline.form(
                        self.strings["version_incompatible"].format(ver),
                        m,
                        reply_markup=[
                            {
                                "text": self.lookup("updater").strings("btn_update"),
                                "callback": self.lookup("updater").inline_update,
                            },
                            {
                                "text": self.lookup("updater").strings("cancel"),
                                "action": "close",
                            },
                        ],
                    )
                return False

        developer = re.search(r"# ?meta developer: ?(.+)", doc)
        developer = developer.group(1) if developer else False

        if not did_requires:
            requirements = []
            try:
                requirements = list(
                    filter(
                        lambda x: not x.startswith(("-", "_", ".")),
                        map(
                            str.strip,
                            loader.VALID_PIP_PACKAGES.search(doc)[1].split(),
                        ),
                    )
                )
            except TypeError:
                pass

            if requirements:
                result = await self.install_requirements(requirements)
                if not result:
                    logger.error(
                        "Module %s requirements from #scope:requires failed to install: %s",
                        module_label,
                        requirements,
                    )
                    if message is not None:
                        await utils.answer(message, self.strings["requirements_failed"])

                    return False

                importlib.invalidate_caches()

                kwargs = utils.get_kwargs()
                kwargs["did_requires"] = True

                return await self.load_module(**kwargs)  # Try again

        if not did_packages:
            packages = []
            try:
                packages = list(
                    filter(
                        lambda x: not x.startswith(("-", "_", ".")),
                        map(
                            str.strip,
                            loader.VALID_APT_PACKAGES.search(doc)[1].split(),
                        ),
                    )
                )
            except TypeError:
                pass

            if packages:
                result = await self.install_packages(packages)

                if not result:
                    logger.error(
                        "Module %s system packages from #scope:packages failed to install: %s",
                        module_label,
                        packages,
                    )
                    if message is not None:
                        await utils.answer(message, self.strings["requirements_failed"])
                    return False

                importlib.invalidate_caches()

                kwargs = utils.get_kwargs()
                kwargs["did_packages"] = True

                return await self.load_module(**kwargs)

        blob_link = self.strings["blob_link"] if blob_link else ""

        if name is None:
            try:
                node = ast.parse(doc)
                uid = next(
                    n.name
                    for n in node.body
                    if isinstance(n, ast.ClassDef)
                    and any(
                        isinstance(base, ast.Attribute)
                        and base.value.id == "Module"
                        or isinstance(base, ast.Name)
                        and base.id == "Module"
                        for base in n.bases
                    )
                )
            except Exception:
                logger.debug(
                    "Can't parse classname from code, using legacy uid instead",
                    exc_info=True,
                )
                uid = "__extmod_" + str(uuid.uuid4())
        else:
            if name.startswith(self.config["MODULES_REPO"]):
                name = name.split("/")[-1].split(".py")[0]

            uid = name.replace("%", "%%").replace(".", "%d")

        module_name = f"hikkari.modules.{uid}"

        async def restart_inline(call: InlineCall):
            await call.edit(self.strings["requirements_restarted"])
            await self.invoke("restart", "-f", message=message)

        async def core_overwrite(e: CoreOverwriteError):
            nonlocal message

            with contextlib.suppress(Exception):
                self.allmodules.modules.remove(instance)

            if not message:
                return

            await utils.answer(
                message,
                self.strings[f"overwrite_{e.type}"].format(
                    *(
                        (e.target,)
                        if e.type == "module"
                        else (utils.escape_html(self.get_prefix()), e.target)
                    )
                ),
            )

        try:
            try:
                spec = ModuleSpec(
                    module_name,
                    loader.StringLoader(doc, f"<external {module_name}>"),
                    origin=f"<external {module_name}>",
                )
                instance = await self.allmodules.register_module(
                    spec,
                    module_name,
                    origin,
                    save_fs=save_fs,
                )
            except ImportError as e:
                logger.info(
                    "Module loading failed, attemping dependency installation (%s)",
                    e.name,
                )
                requirements = [loader.IMPORT_PIP_ALIASES.get(e.name.lower(), e.name)]

                if not requirements:
                    raise Exception("Nothing to install") from e

                logger.debug("Installing requirements: %s", requirements)

                if did_requirements:
                    logger.error(
                        "Module %s still requires missing dependency %s after installation",
                        module_label,
                        e.name,
                    )
                    if message is not None:
                        await self.inline.form(
                            message=message,
                            text=self.strings["requirements_restart"].format(e.name),
                            reply_markup=[
                                {"text": "🚀 Restart", "callback": restart_inline}
                            ],
                        )

                    return False

                if message is not None:
                    await utils.answer(
                        message,
                        self.strings["requirements_installing"].format(
                            "\n".join(
                                f"{self.config['command_emoji']}" f" {req}"
                                for req in requirements
                            )
                        ),
                    )

                result = await self.install_requirements(requirements)
                if not result:
                    logger.error(
                        "Module %s dependency installation failed: %s",
                        module_label,
                        requirements,
                    )
                    if message is not None:
                        await utils.answer(message, self.strings["requirements_failed"])

                    return False

                importlib.invalidate_caches()

                kwargs = utils.get_kwargs()
                kwargs["did_requirements"] = True

                return await self.load_module(**kwargs)  # Try again
            except CoreOverwriteError as e:
                logger.error(
                    "Module %s tried to overwrite core %s %s",
                    module_label,
                    e.type,
                    e.target,
                )
                await core_overwrite(e)
                return False
            except (loader.LoadError, ScamDetectionError) as e:
                logger.error("Module %s failed security checks: %s", module_label, e)
                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    if isinstance(e, loader.LoadError):
                        await utils.answer(
                            message,
                            (
                                "<tg-emoji emoji-id=5287372146039861774>❌</tg-emoji>"
                                f" <b>{utils.escape_html(str(e))}</b>"
                            ),
                        )
                    elif isinstance(e, ScamDetectionError):
                        await utils.answer(
                            message,
                            (
                                self.strings["scam_module"].format(
                                    name=instance.__class__.__name__,
                                    prefix=self.get_prefix(),
                                )
                            ),
                        )
                return False
        except Exception as e:
            logger.exception("Loading external module failed due to %s", e)

            if message is not None:
                await utils.answer(message, self.strings["load_failed"])

            return False

        if hasattr(instance, "__version__") and isinstance(instance.__version__, tuple):
            version = (
                "<b><i>"
                f" (v{'.'.join(list(map(str, list(instance.__version__))))})</i></b>"
            )
        else:
            version = ""

        try:
            try:
                self.allmodules.send_config_one(instance)

                async def inner_proxy():
                    nonlocal instance, message
                    while True:
                        if hasattr(instance, "hikkari_wait_channel_approve"):
                            if message:
                                (
                                    module,
                                    channel,
                                    reason,
                                ) = instance.hikkari_wait_channel_approve
                                message = await utils.answer(
                                    message,
                                    self.strings["wait_channel_approve"].format(
                                        module,
                                        channel.username,
                                        utils.escape_html(channel.title),
                                        utils.escape_html(reason),
                                        self.inline.bot_username,
                                    ),
                                )
                                return

                        await asyncio.sleep(0.1)

                task = asyncio.ensure_future(inner_proxy())
                await self.allmodules.send_ready_one(
                    instance,
                    no_self_unload=True,
                    from_dlmod=bool(message),
                )
                task.cancel()
            except CoreOverwriteError as e:
                logger.error(
                    "Module %s tried to overwrite core %s %s during ready stage",
                    module_label,
                    e.type,
                    e.target,
                )
                await core_overwrite(e)
                return False
            except (loader.LoadError, ScamDetectionError) as e:
                logger.error(
                    "Module %s failed during ready security checks: %s",
                    module_label,
                    e,
                )
                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    if isinstance(e, loader.LoadError):
                        await utils.answer(
                            message,
                            (
                                "<tg-emoji emoji-id=5287372146039861774>❌</tg-emoji>"
                                f" <b>{utils.escape_html(str(e))}</b>"
                            ),
                        )
                    elif isinstance(e, ScamDetectionError):
                        await utils.answer(
                            message,
                            (
                                self.strings["scam_module"].format(
                                    name=instance.__class__.__name__,
                                    prefix=self.get_prefix(),
                                )
                            ),
                        )
                return False
            except loader.SelfUnload as e:
                logger.warning(
                    "Module %s unloaded itself during installation: %s",
                    module_label,
                    e,
                )
                with contextlib.suppress(Exception):
                    await self.allmodules.unload_module(instance.__class__.__name__)

                with contextlib.suppress(Exception):
                    self.allmodules.modules.remove(instance)

                if message:
                    await utils.answer(
                        message,
                        (
                            "<tg-emoji emoji-id=5287372146039861774>❌</tg-emoji>"
                            f" <b>{utils.escape_html(str(e))}</b>"
                        ),
                    )
                return False
            except loader.SelfSuspend as e:
                logger.warning(
                    "Module %s suspended itself during installation: %s",
                    module_label,
                    e,
                )
                if message:
                    await utils.answer(
                        message,
                        (
                            "🥶 <b>Module suspended itself\nReason:"
                            f" {utils.escape_html(str(e))}</b>"
                        ),
                    )
                return False
        except Exception as e:
            logger.exception("Module threw because of %s", e)

            if message is not None:
                await utils.answer(message, self.strings["load_failed"])

            return False

        instance.hikkari_meta_pic = next(
            (
                line.replace(" ", "").split("#metapic:", maxsplit=1)[1]
                for line in doc.splitlines()
                if line.replace(" ", "").startswith("#metapic:")
            ),
            None,
        )

        pack_url = next(
            (
                line.replace(" ", "").split("#packurl:", maxsplit=1)[1]
                for line in doc.splitlines()
                if line.replace(" ", "").startswith("#packurl:")
            ),
            None,
        )

        if pack_url and (
            transations := await self.allmodules.translator.load_module_translations(
                pack_url,
                loader.MODULES_LANGPACKS_PATH
                / f"{self.client.tg_id}_{instance.__class__.__name__}.yml",
            )
        ):
            instance.strings.external_strings = transations

        for alias, cmd in self.lookup("settings").get("aliases", {}).items():
            _cmd = cmd.split(maxsplit=1)
            if _cmd[0] in instance.commands:
                self.allmodules.add_alias(alias, *_cmd)

        try:
            modname = instance.strings("name")
        except (KeyError, AttributeError):
            modname = getattr(instance, "name", instance.__class__.__name__)

        try:
            developer_entity = await (
                self._client.force_get_entity
                if (
                    developer in self._client.hikkari_entity_cache
                    and getattr(
                        await self._client.get_entity(developer),
                        "left",
                        True,
                    )
                )
                else self._client.get_entity
            )(developer)
        except Exception:
            developer_entity = None

        if not isinstance(developer_entity, Channel):
            developer_entity = None

        if message is None:
            return True

        modhelp = []
        mod_doc = ""

        if instance.__doc__:
            mod_doc += (
                "<i>\n<tg-emoji emoji-id=5879813604068298387>ℹ️</tg-emoji>"
                f" {utils.escape_html(inspect.getdoc(instance))}</i>\n\n"
            )

        subscribe = ""
        subscribe_markup = None

        depends_from = []
        for key in dir(instance):
            value = getattr(instance, key)
            if isinstance(value, loader.Library):
                depends_from.append(
                    "<tg-emoji emoji-id=5197195523794157505>▫️</tg-emoji>"
                    " <code>{}</code> <b>{}</b> <code>{}</code>".format(
                        value.__class__.__name__,
                        self.strings["by"],
                        (
                            value.developer
                            if isinstance(getattr(value, "developer", None), str)
                            else "Unknown"
                        ),
                    )
                )
        placeholders = utils.help_placeholders(
            getattr(getattr(instance, "__class__"), "__name__"), self
        )

        depends_from = (
            self.strings["depends_from"].format("\n".join(depends_from))
            if depends_from
            else ""
        )

        def loaded_msg(use_subscribe: bool = True):
            nonlocal modname, version, mod_doc, modhelp, placeholders, developer, origin, subscribe, blob_link, depends_from
            return self.strings["loaded"].format(
                modname.strip(),
                version,
                utils.ascii_face(),
                mod_doc if mod_doc else "",
                "<blockquote expandable>{}</blockquote>".format("\n".join(modhelp)),
                "\n<blockquote expandable>{}</blockquote>".format(
                    "\n".join(placeholders)
                ),
                developer if not subscribe or not use_subscribe else "",
                depends_from,
                (
                    self.strings["modlink"].format(origin)
                    if origin != "<string>" and self.config["share_link"]
                    else ""
                ),
                blob_link,
                subscribe if use_subscribe else "",
            )

        if developer:
            if developer.startswith("@") and developer not in self.get(
                "do_not_subscribe", []
            ):
                if (
                    developer_entity
                    and getattr(developer_entity, "left", True)
                    and self._db.get(main.__name__, "suggest_subscribe", True)
                ):
                    subscribe = self.strings["suggest_subscribe"].format(
                        f"@{utils.escape_html(developer_entity.username)}"
                    )
                    subscribe_markup = [
                        {
                            "text": self.strings["subscribe"],
                            "callback": self._inline__subscribe,
                            "args": (
                                developer_entity.id,
                                functools.partial(loaded_msg, use_subscribe=False),
                                True,
                            ),
                        },
                        {
                            "text": self.strings["no_subscribe"],
                            "callback": self._inline__subscribe,
                            "args": (
                                developer,
                                functools.partial(loaded_msg, use_subscribe=False),
                                False,
                            ),
                        },
                    ]

            developer = self.strings["developer"].format(utils.escape_html(developer))
        else:
            developer = ""

        banner_kwargs = {}
        _is_msg = hasattr(message, "document") or hasattr(message, "web_preview")
        if (
            self.config["show_banner"]
            and not subscribe_markup
            and _is_msg
            and (
                not getattr(message, "document", None)
                or getattr(message, "web_preview", None)
            )
        ):
            try:
                banner_url = self._get_banner_url(doc)
                if banner_url:
                    banner_kwargs = {
                        "file": InputMediaWebPage(banner_url, optional=True),
                        "invert_media": True,
                    }
            except Exception:
                pass

        if any(
            line.replace(" ", "") == "#scope:disable_onload_docs"
            for line in doc.splitlines()
        ):
            quiet = bool(quiet) or bool(getattr(self, "_quiet_install", False))
            try:
                rows = self._module_cmds_rows(instance)
                self._last_loaded = {
                    "name": str(modname).strip(),
                    "rows": rows,
                    "doc": (inspect.getdoc(instance) or "")[:300] if instance.__doc__ else "",
                    "ok": True,
                }
            except Exception:
                self._last_loaded = {"name": str(modname), "rows": [], "doc": "", "ok": True}
            if quiet:
                return True
            if await self._rich_module_loaded(
                message,
                modname=str(modname),
                mod_doc=mod_doc or "",
                rows=self._last_loaded.get("rows") or [],
                subscribe_markup=subscribe_markup,
                origin=origin,
            ):
                return True
            await utils.answer(
                message,
                loaded_msg(),
                reply_markup=subscribe_markup,
                skip_rich=True,
                **banner_kwargs,
            )
            return True

        for _name, fun in sorted(
            instance.commands.items(),
            key=lambda x: x[0],
        ):
            modhelp.append(
                "{} <code>{}{}</code> {}".format(
                    f"{self.config['command_emoji']}",
                    utils.escape_html(self.get_prefix()),
                    _name,
                    (
                        utils.escape_html(inspect.getdoc(fun))
                        if fun.__doc__
                        else self.strings["undoc"]
                    ),
                )
            )

        if self.inline.init_complete:
            for _name, fun in sorted(
                instance.inline_handlers.items(),
                key=lambda x: x[0],
            ):
                modhelp.append(
                    self.strings["ihandler"].format(
                        f"@{self.inline.bot_username} {_name}",
                        (
                            utils.escape_html(inspect.getdoc(fun))
                            if fun.__doc__
                            else self.strings["undoc"]
                        ),
                    )
                )

        # Remember for batch installs
        try:
            rows = self._module_cmds_rows(instance)
            plain_doc = ""
            if instance.__doc__:
                plain_doc = (inspect.getdoc(instance) or "")[:300]
            self._last_loaded = {
                "name": modname.strip() if isinstance(modname, str) else str(modname),
                "rows": rows,
                "doc": plain_doc,
                "ok": True,
            }
        except Exception:
            self._last_loaded = {"name": str(modname), "rows": [], "doc": "", "ok": True}

        quiet = bool(quiet) or bool(getattr(self, "_quiet_install", False))
        if quiet:
            return True

        # Rich announcement (commands in <details>)
        # Subscribe callbacks need form units → keep classic form if markup set
        try:
            if not subscribe_markup and await self._rich_module_loaded(
                message,
                modname=str(modname),
                mod_doc=mod_doc or "",
                rows=self._last_loaded.get("rows") or [],
                subscribe_markup=None,
                origin=origin,
            ):
                return True
            if subscribe_markup and await self._rich_module_loaded(
                message,
                modname=str(modname),
                mod_doc=mod_doc or "",
                rows=self._last_loaded.get("rows") or [],
                subscribe_markup=None,
                origin=origin,
            ):
                # Still show subscribe via separate form under rich
                await self.inline.form(
                    self.strings.get("suggest_subscribe", "Subscribe to developer channel?"),
                    message=message if message.out else utils.get_chat_id(message),
                    reply_markup=subscribe_markup,
                    silent=True,
                )
                return True
        except Exception:
            logger.debug("rich announce failed", exc_info=True)

        try:
            await utils.answer(
                message,
                loaded_msg(),
                reply_markup=subscribe_markup,
                skip_rich=True,
                **banner_kwargs,
            )
        except MediaCaptionTooLongError:
            await message.reply(loaded_msg(False))

        return True

    async def _inline__subscribe(
        self,
        call: InlineCall,
        entity: int,
        msg: typing.Callable[[], str],
        subscribe: bool,
    ):
        if not subscribe:
            self.set("do_not_subscribe", self.get("do_not_subscribe", []) + [entity])
            await utils.answer(call, msg())
            await call.answer(self.strings["not_subscribed"])
            return

        await self._client(JoinChannelRequest(entity))
        await utils.answer(call, msg())
        await call.answer(self.strings["subscribed"])

    @loader.command(alias="ulm")
    async def unloadmod(self, message: Message):
        if not (raw_args := utils.get_args_raw(message)):
            await utils.answer(message, self.strings["no_class"])
            return

        args = raw_args
        force = False
        first_line = args.split("\n", 1)[0].strip()
        if first_line == "-f":
            force = True
            rest = args.split("\n", 1)
            args = rest[1].strip() if len(rest) > 1 else ""
        elif args.startswith("-f "):
            force = True
            args = args[3:].strip()

        if not args:
            await utils.answer(message, self.strings["no_class"])
            return

        raw_list = re.split(r"[,\n]", args)
        modules = [m.strip() for m in raw_list if m.strip()]

        if len(modules) == 1:
            if not self.lookup(modules[0]):
                suggestions = self._get_unload_suggestions(modules[0])
                if suggestions:
                    await self.inline.form(
                        self.strings["unload_suggestions"].format(
                            utils.escape_html(modules[0])
                        ),
                        message=message,
                        reply_markup=[
                            [
                                {
                                    "text": label,
                                    "callback": self._inline__unload_suggested,
                                    "args": (classname, force),
                                }
                            ]
                            for classname, label in suggestions
                        ]
                        + [
                            [
                                {
                                    "text": self.strings["cancel"].replace("🚫", "❌"),
                                    "action": "close",
                                }
                            ]
                        ],
                        silent=True,
                    )
                    return

            msg = await self.unload_module(modules[0], force=force)
        else:
            success = []
            errors = []
            msg = ""
            for module in modules:
                status = await self.unload_module(module)
                if "❌" in status or "🚫" in status or "😖" in status:
                    if "💡" in status:
                        status = status.split("<code>")[0]

                    errors.append(f"<code>{module}</code> — {status}")
                else:
                    success.append(f"<code>{module}</code>")

            if success:
                msg += self.strings["modules_unloaded"].format(
                    unloaded_num=len(success), unloaded=", ".join(success)
                )
            if errors:
                msg += "\n" + self.strings["modules_not_unloaded"].format(
                    not_unloaded=len(errors),
                    errors="\n".join(errors),
                )

        await utils.answer(message, msg)

    def _get_unload_suggestions(
        self,
        query: str,
        limit: int = 3,
    ) -> list[tuple[str, str]]:
        query = query.lower()
        scored = []

        for module in self.allmodules.modules:
            if self._is_core_module(module):
                continue

            classname = module.__class__.__name__
            public_name = str(getattr(module, "name", "") or module.strings["name"])
            names = {
                classname,
                classname[:-3] if classname.endswith("Mod") else classname,
                public_name,
            }
            score = max(
                difflib.SequenceMatcher(None, query, name.lower()).ratio()
                for name in names
                if name
            )
            label = public_name
            scored.append((score, classname.lower(), classname, label))

        return [
            (classname, label)
            for _, _, classname, label in sorted(scored, reverse=True)[:limit]
        ]

    def _is_core_module(self, module) -> bool:
        module_name = getattr(module.__class__, "__module__", "")
        if not module_name.startswith("hikkari.modules."):
            return False

        module_file = module_name.rsplit(".", 1)[-1]
        return os.path.isfile(
            os.path.join(utils.get_base_dir(), "modules", f"{module_file}.py")
        )

    async def _inline__unload_suggested(
        self,
        call: InlineCall,
        module: str,
        force: bool = False,
    ):
        await call.edit(await self.unload_module(module, force=force))

    async def unload_module(self, module: str, force: bool = False) -> str:
        instance = self.lookup(module)

        if instance and self._is_core_module(instance):
            return self.strings["unload_core"].format(module)

        if instance and issubclass(instance.__class__, loader.Library):
            return self.strings["cannot_unload_lib"]

        try:
            worked = await self.allmodules.unload_module(module)
        except CoreUnloadError:
            return self.strings["unload_core"].format(module)

        if not self.allmodules.secure_boot:
            self.set(
                "loaded_modules",
                {
                    mod: link
                    for mod, link in self.get("loaded_modules", {}).items()
                    if mod not in worked
                },
            )

        msg = (
            self.strings["unloaded"].format(
                "<tg-emoji emoji-id=5784993237412351403>✅</tg-emoji>",
                ", ".join(
                    [(mod[:-3] if mod.endswith("Mod") else mod) for mod in worked]
                ),
            )
            if worked
            else self.strings["not_unloaded"]
        )
        for mod_name in worked:
            utils.unregister_placeholders(mod_name)

        if force and worked:
            try:
                for key in list(self._db.keys()):
                    if not isinstance(key, str):
                        continue
                    low = key.lower()
                    for mod_name in worked:
                        base = mod_name[:-3] if mod_name.endswith("Mod") else mod_name
                        candidates = {mod_name.lower(), base.lower()}
                        if any(
                            low == c
                            or low.startswith(c + ".")
                            or low.startswith(c + "_")
                            or c in low
                            for c in candidates
                        ):
                            try:
                                del self._db[key]
                            except Exception:
                                pass

                try:
                    self._db.save()
                except Exception:
                    logger.debug(
                        "Failed to save DB after force-unload cleanup", exc_info=True
                    )
            except Exception:
                logger.exception("Failed to cleanup DB for force unload")

        return msg

    @loader.command()
    async def clearmodules(self, message: Message):
        await self.inline.form(
            self.strings["confirm_clearmodules"],
            message,
            reply_markup=[
                {
                    "text": self.strings["clearmodules"],
                    "callback": self._inline__clearmodules,
                },
                {
                    "text": self.strings["cancel"],
                    "action": "close",
                },
            ],
        )

    @loader.command()
    async def addrepo(self, message: Message):
        if not (args := utils.get_args_raw(message)) or (
            not utils.check_url(args) and not utils.check_url(f"https://{args}")
        ):
            await utils.answer(message, self.strings["no_repo"])
            return

        if args.endswith("/"):
            args = args[:-1]

        if not args.startswith("https://") and not args.startswith("http://"):
            args = f"https://{args}"

        try:
            r = await utils.run_sync(
                requests.get,
                f"{args}/full.txt",
                auth=(
                    tuple(self.config["basic_auth"].split(":", 1))
                    if self.config["basic_auth"]
                    else None
                ),
            )
            r.raise_for_status()
            if not r.text.strip():
                raise ValueError
        except Exception:
            await utils.answer(message, self.strings["no_repo"])
            return

        if args in self.config["ADDITIONAL_REPOS"]:
            await utils.answer(message, self.strings["repo_exists"].format(args))
            return

        self.config["ADDITIONAL_REPOS"] += [args]

        await utils.answer(message, self.strings["repo_added"].format(args))

    @loader.command()
    async def delrepo(self, message: Message):
        if not (args := utils.get_args_raw(message)) or not utils.check_url(args):
            await utils.answer(message, self.strings["no_repo"])
            return

        if args.endswith("/"):
            args = args[:-1]

        if args not in self.config["ADDITIONAL_REPOS"]:
            await utils.answer(message, self.strings["repo_not_exists"])
            return

        self.config["ADDITIONAL_REPOS"].remove(args)

        await utils.answer(message, self.strings["repo_deleted"].format(args))

    async def _inline__clearmodules(self, call: InlineCall):
        self.set("loaded_modules", {})

        for file in os.scandir(loader.LOADED_MODULES_DIR):
            try:
                os.remove(file.path)
            except Exception:
                logger.debug("Failed to remove %s", file.path, exc_info=True)

        await utils.answer(call, self.strings["all_modules_deleted"])
        await self.lookup("Updater").restart_common(call)

    async def _update_modules(self):
        todo = await self._get_modules_to_load()

        self._secure_boot = False

        if self._db.get(loader.__name__, "secure_boot", False):
            self._db.set(loader.__name__, "secure_boot", False)
            self._secure_boot = True
        else:
            for mod in todo.values():
                await self.download_and_install(mod)

            self.update_modules_in_db()

            aliases = {
                alias: cmd
                for alias, cmd in self.lookup("settings").get("aliases", {}).items()
                if self.allmodules.add_alias(alias, *cmd.split(maxsplit=1))
            }

            self.lookup("settings").set("aliases", aliases)

        self.fully_loaded = True

        with contextlib.suppress(AttributeError):
            await self.lookup("Updater").full_restart_complete(self._secure_boot)

    def flush_cache(self) -> int:
        """Flush the cache of links to modules"""
        count = sum(map(len, self._links_cache.values()))
        self._links_cache = {}
        return count

    def inspect_cache(self) -> int:
        """Inspect the cache of links to modules"""
        return sum(map(len, self._links_cache.values()))

    async def reload_core(self) -> int:
        """Forcefully reload all core modules"""
        self.fully_loaded = False

        if self._secure_boot:
            self._db.set(loader.__name__, "secure_boot", True)

        if not self._db.get(main.__name__, "remove_core_protection", False):
            for module in self.allmodules.modules:
                if module.__origin__.startswith("<core"):
                    module.__origin__ = "<reload-core>"

        loaded = await self.allmodules.register_all(no_external=True)
        for instance in loaded:
            self.allmodules.send_config_one(instance)
            await self.allmodules.send_ready_one(
                instance,
                no_self_unload=False,
                from_dlmod=False,
            )

        self.fully_loaded = True
        return len(loaded)

    @loader.command()
    async def mlcmd(self, message: Message):
        """| send module via file"""
        if not (args := utils.get_args_raw(message)):
            await utils.answer(message, self.strings["args"])
            return

        await utils.answer(message, self.strings["ml_load_module"])

        exact = True
        if not (
            class_name := next(
                (
                    module.strings("name")
                    for module in self.allmodules.modules
                    if args.lower()
                    in {
                        module.strings("name").lower(),
                        module.__class__.__name__.lower(),
                    }
                ),
                None,
            )
        ):
            if not (
                class_name := next(
                    reversed(
                        sorted(
                            [
                                module.strings["name"].lower()
                                for module in self.allmodules.modules
                            ]
                            + [
                                module.__class__.__name__.lower()
                                for module in self.allmodules.modules
                            ],
                            key=lambda x: difflib.SequenceMatcher(
                                None,
                                args.lower(),
                                x,
                            ).ratio(),
                        )
                    ),
                    None,
                )
            ):
                await utils.answer(message, self.strings["404"])
                return

            exact = False

        try:
            module = self.lookup(class_name)
            sys_module = inspect.getmodule(module)
        except Exception:
            await utils.answer(message, self.strings["404"])
            return

        module_data = sys_module.__loader__.data
        if isinstance(module_data, str):
            module_data = module_data.encode("utf-8")

        module_doc = (
            module_data.decode("utf-8", errors="ignore")
            if isinstance(module_data, (bytes, bytearray))
            else str(module_data)
        )

        if any(
            line.replace(" ", "") == "#scope:no_ml" for line in module_doc.splitlines()
        ):
            await utils.answer(
                message,
                self.strings["no_ml"].format(utils.escape_html(class_name)),
            )
            return

        link = module.__origin__

        text = (
            f"<b>🧳 {utils.escape_html(class_name)}</b>"
            if not utils.check_url(link)
            else (
                f'📼 <b><a href="{link}">Link</a> for'
                f" {utils.escape_html(class_name)}:</b>"
                f' <code>{link}</code>\n\n{self.strings["not_exact"] if not exact else ""}'
            )
        )

        text = (
            self.strings["link"].format(
                class_name=utils.escape_html(class_name),
                url=link,
                not_exact=self.strings["not_exact"] if not exact else "",
                prefix=utils.escape_html(self.get_prefix()),
            )
            if utils.check_url(link)
            else self.strings["file"].format(
                class_name=utils.escape_html(class_name),
                not_exact=self.strings["not_exact"] if not exact else "",
                prefix=utils.escape_html(self.get_prefix()),
            )
        )

        file = io.BytesIO(module_data)
        file.name = f"{class_name}.py"
        file.seek(0)

        await utils.answer(
            message,
            text,
            file=file,
            reply_to=getattr(message, "reply_to_msg_id", None),
        )

    def _format_result(
        self,
        result: dict,
        query: str,
        no_translate: bool = False,
    ) -> str:
        commands = "\n".join(
            [
                f"▫️ <code>{utils.escape_html(self.get_prefix())}{utils.escape_html(cmd)}</code>:"
                f" <b>{utils.escape_html(cmd_doc)}</b>"
                for cmd, cmd_doc in result["module"]["commands"].items()
            ]
        )

        kwargs = {
            "name": utils.escape_html(result["module"]["name"]),
            "dev": utils.escape_html(result["module"]["dev"]),
            "commands": commands,
            "cls_doc": utils.escape_html(result["module"]["cls_doc"]),
            "mhash": result["module"]["hash"],
            "query": utils.escape_html(query),
            "prefix": utils.escape_html(self.get_prefix()),
        }

        strings = (
            self.strings.get("result", "en")
            if self.config["translate"] and not no_translate
            else self.strings["result"]
        )

        text = strings.format(**kwargs)

        if len(text) > 1980:
            kwargs["commands"] = "..."
            text = strings.format(**kwargs)

        return text
