# ©️ Wers1xx, 2025-2026
# HikkariFind — module search + reliable install
# 🌐 https://github.com/Wers1xx/Hikkari

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time

import aiohttp
from hikkaritl.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

LIMOKA_INDEX = (
    "https://raw.githubusercontent.com/MuRuLOSE/limoka/main/modules.json"
)
EXTRA_FULL = [
    "https://raw.githubusercontent.com/Wersixx/Wers1xx/main/full.txt",
]


def _url_candidates(key: str, meta: dict | None = None) -> list[str]:
    """Build possible raw.githubusercontent URLs for a limoka key / meta."""
    meta = meta or {}
    out: list[str] = []
    for k in ("url", "link", "raw", "download"):
        v = meta.get(k)
        if isinstance(v, str) and v.startswith("http"):
            out.append(v.replace("/blob/", "/raw/").replace("github.com/", "raw.githubusercontent.com/").replace("/raw/raw/", "/raw/"))

    key = str(key).replace("\\", "/").lstrip("/")
    parts = key.split("/")
    if key.endswith(".py") and len(parts) >= 3:
        user, repo, path = parts[0], parts[1], "/".join(parts[2:])
        for branch in ("main", "master"):
            out.append(f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}")
    elif key.endswith(".py") and len(parts) == 2:
        user, fname = parts
        for repo in ("modules", "Hikkamods", "hikka-mods", user):
            for branch in ("main", "master"):
                out.append(
                    f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{fname}"
                )

    # dedupe preserve order
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


@loader.tds
class HikkariFindMod(loader.Module):
    """Search modules across Limoka catalog + Hikkari repos"""

    strings = {
        "name": "HikkariFind",
        "usage": "🔍 <b>Usage:</b> <code>{prefix}find &lt;query&gt;</code>",
        "searching": "🔍 <b>Searching</b> <code>{q}</code>…",
        "nothing": "🚫 <b>Nothing found for</b> <code>{q}</code>",
        "header": "✨ <b>HikkariFind</b> — {n} result(s) for <code>{q}</code>:\n\n{body}",
        "item": "📦 <b>{name}</b>\n📝 {desc}\n🔗 <code>{url}</code>\n",
        "install_btn": "⬇️ {name}",
        "close_btn": "🔻 Close",
        "installing": "⏳ Installing <code>{name}</code>…",
        "installed": "✅ Installed <code>{name}</code>",
        "failed": "🚫 Failed to install <code>{name}</code>\n<code>{err}</code>",
        "timeout": "⏱ Timeout while installing <code>{name}</code>",
        "no_url": "🚫 No working download URL for <code>{name}</code>",
    }

    strings_ru = {
        "usage": "🔍 <b>Использование:</b> <code>{prefix}find &lt;запрос&gt;</code>",
        "searching": "🔍 <b>Ищу</b> <code>{q}</code>…",
        "nothing": "🚫 <b>Ничего не найдено по</b> <code>{q}</code>",
        "header": "✨ <b>HikkariFind</b> — {n} результат(ов) по <code>{q}</code>:\n\n{body}",
        "item": "📦 <b>{name}</b>\n📝 {desc}\n🔗 <code>{url}</code>\n",
        "install_btn": "⬇️ {name}",
        "close_btn": "🔻 Закрыть",
        "installing": "⏳ Устанавливаю <code>{name}</code>…",
        "installed": "✅ Установлен <code>{name}</code>",
        "failed": "🚫 Не удалось установить <code>{name}</code>\n<code>{err}</code>",
        "timeout": "⏱ Таймаут при установке <code>{name}</code>",
        "no_url": "🚫 Нет рабочей ссылки для <code>{name}</code>",
    }

    def __init__(self):
        self._index: list[dict] = []
        self._index_ts: float = 0.0
        self._install_lock = asyncio.Lock()

    async def _load_index(self, force: bool = False) -> list[dict]:
        if self._index and not force and time.time() - self._index_ts < 300:
            return self._index

        entries: list[dict] = []
        seen: set[str] = set()

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    LIMOKA_INDEX, timeout=aiohttp.ClientTimeout(total=25)
                ) as r:
                    if r.status == 200:
                        data = await r.json(content_type=None)
                        mods = data.get("modules", data) if isinstance(data, dict) else {}
                        if isinstance(mods, dict):
                            for key, meta in mods.items():
                                if not isinstance(meta, dict):
                                    meta = {"name": str(key)}
                                name = str(
                                    meta.get("name")
                                    or str(key).split("/")[-1].replace(".py", "")
                                )
                                desc = meta.get("description") or meta.get("cls_doc") or ""
                                if isinstance(desc, dict):
                                    desc = (
                                        desc.get("ru")
                                        or desc.get("en")
                                        or next(iter(desc.values()), "")
                                    )
                                cmds = meta.get("commands") or []
                                cmd_blob = (
                                    " ".join(str(c) for c in cmds)
                                    if isinstance(cmds, list)
                                    else str(cmds)
                                )
                                cands = _url_candidates(str(key), meta)
                                url = cands[0] if cands else str(key)
                                # unique by name+first path segment
                                uid = f"{name}|{url}"
                                if uid in seen:
                                    continue
                                seen.add(uid)
                                entries.append(
                                    {
                                        "name": name,
                                        "desc": str(desc)[:160],
                                        "url": url,
                                        "urls": cands,
                                        "blob": f"{name} {desc} {cmd_blob} {key}".lower(),
                                    }
                                )
            except Exception:
                logger.exception("limoka index")

            repos = list(EXTRA_FULL)
            loader_mod = self.lookup("Loader")
            if loader_mod:
                try:
                    main_repo = str(
                        loader_mod.config.get("MODULES_REPO")
                        or "https://raw.githubusercontent.com/Wersixx/Wers1xx/main"
                    ).rstrip("/")
                    repos.insert(0, f"{main_repo}/full.txt")
                    for extra in loader_mod.config.get("ADDITIONAL_REPOS") or []:
                        repos.append(f"{str(extra).rstrip('/')}/full.txt")
                except Exception:
                    pass

            for full_url in repos:
                try:
                    base = full_url.rsplit("/", 1)[0]
                    async with session.get(
                        full_url, timeout=aiohttp.ClientTimeout(total=15)
                    ) as r:
                        if r.status != 200:
                            continue
                        text = await r.text()
                    for raw in text.splitlines():
                        name = raw.strip().lstrip("\ufeff")
                        if not name or name.startswith("#"):
                            continue
                        if name.endswith(".py"):
                            name = name[:-3]
                        if "/" in name or "\\" in name:
                            continue
                        url = f"{base}/{name}.py"
                        if url in seen:
                            continue
                        seen.add(url)
                        entries.append(
                            {
                                "name": name,
                                "desc": "",
                                "url": url,
                                "urls": [url],
                                "blob": name.lower(),
                            }
                        )
                except Exception:
                    logger.debug("full.txt fail %s", full_url, exc_info=True)

            if loader_mod:
                try:
                    for _repo, mapping in (await loader_mod.get_repo_list()).items():
                        for _k, url in mapping.items():
                            name = url.rsplit("/", 1)[-1].replace(".py", "")
                            if url in seen:
                                continue
                            seen.add(url)
                            entries.append(
                                {
                                    "name": name,
                                    "desc": "",
                                    "url": url,
                                    "urls": [url],
                                    "blob": name.lower(),
                                }
                            )
                except Exception:
                    logger.exception("loader repo list")

        self._index = entries
        self._index_ts = time.time()
        logger.info("HikkariFind index: %s modules", len(entries))
        return entries

    def _score(self, entry: dict, q: str) -> int:
        blob = entry.get("blob") or ""
        name = (entry.get("name") or "").lower()
        ql = q.lower().strip()
        if not ql:
            return 0
        score = 0
        if name == ql or name == ql.replace(" ", ""):
            score += 100
        if ql in name:
            score += 50
        compact_name = re.sub(r"[^a-z0-9]", "", name)
        compact_q = re.sub(r"[^a-z0-9]", "", ql)
        if compact_q and compact_q in compact_name:
            score += 40
        for tok in re.split(r"\s+", ql):
            if tok and tok in blob:
                score += 10
        if ql in blob:
            score += 15
        return score

    async def _resolve_working_url(self, urls: list[str]) -> str | None:
        if not urls:
            return None
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in urls[:8]:
                try:
                    async with session.get(url) as r:
                        if r.status == 200:
                            text = await r.text()
                            # must look like python module
                            if "class " in text or "loader.Module" in text or "@loader" in text:
                                return url
                except Exception:
                    continue
        return None

    @loader.command(alias="fmod")
    async def find(self, message: Message):
        """<query> — search modules (catalog + repos)"""
        q = (utils.get_args_raw(message) or "").strip()
        if not q:
            await utils.answer(
                message, self.strings["usage"].format(prefix=self.get_prefix())
            )
            return

        status = await utils.answer(
            message, self.strings["searching"].format(q=utils.escape_html(q))
        )

        try:
            index = await asyncio.wait_for(self._load_index(), timeout=45)
        except asyncio.TimeoutError:
            await utils.answer(
                status, self.strings["nothing"].format(q=utils.escape_html(q))
            )
            return

        scored = [(self._score(e, q), e) for e in index]
        scored = [(s, e) for s, e in scored if s > 0]
        scored.sort(key=lambda x: (-x[0], x[1]["name"].lower()))
        matched = [e for _, e in scored[:20]]

        if not matched:
            await utils.answer(
                status, self.strings["nothing"].format(q=utils.escape_html(q))
            )
            return

        body = "\n".join(
            self.strings["item"].format(
                name=utils.escape_html(e["name"]),
                desc=utils.escape_html(e["desc"] or "—"),
                url=utils.escape_html(e["url"]),
            )
            for e in matched[:12]
        )
        text = self.strings["header"].format(
            n=len(matched), q=utils.escape_html(q), body=body
        )

        rows = [
            [
                {
                    "text": self.strings["install_btn"].format(name=e["name"][:18]),
                    "callback": self._install,
                    "args": (
                        e.get("urls") or [e["url"]],
                        e["name"],
                    ),
                }
            ]
            for e in matched[:8]
        ]
        rows.append([{"text": self.strings["close_btn"], "action": "close"}])

        await self.inline.form(text, message=status, reply_markup=rows, silent=True)

    async def _install(self, call: InlineCall, urls, name: str):
        """Reliable install: answer → resolve URL → timeout-bounded load."""
        with contextlib.suppress(Exception):
            await call.answer()

        try:
            await call.edit(
                self.strings["installing"].format(name=utils.escape_html(name))
            )
        except Exception:
            logger.debug("install edit failed", exc_info=True)

        if isinstance(urls, str):
            urls = [urls]

        loader_mod = self.lookup("Loader")
        if not loader_mod:
            with contextlib.suppress(Exception):
                await call.edit(
                    self.strings["failed"].format(
                        name=utils.escape_html(name), err="Loader missing"
                    )
                )
            return

        async with self._install_lock:
            try:
                url = await asyncio.wait_for(
                    self._resolve_working_url(list(urls)), timeout=20
                )
            except asyncio.TimeoutError:
                url = None

            if not url:
                with contextlib.suppress(Exception):
                    await call.edit(
                        self.strings["no_url"].format(name=utils.escape_html(name))
                    )
                return

            try:
                result = await asyncio.wait_for(
                    loader_mod.download_and_install(url, None),
                    timeout=90,
                )
                ok = result == 1 or result is True
                err = "" if ok else f"code={result}"
            except asyncio.TimeoutError:
                with contextlib.suppress(Exception):
                    await call.edit(
                        self.strings["timeout"].format(name=utils.escape_html(name))
                    )
                return
            except Exception as e:
                logger.exception("HikkariFind install %s", name)
                ok = False
                err = type(e).__name__

        with contextlib.suppress(Exception):
            if ok:
                await call.edit(
                    self.strings["installed"].format(name=utils.escape_html(name))
                )
            else:
                await call.edit(
                    self.strings["failed"].format(
                        name=utils.escape_html(name),
                        err=utils.escape_html(err or "unknown"),
                    )
                )
