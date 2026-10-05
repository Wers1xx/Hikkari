# ©️ Wers1xx, 2025-2026
# Built-in module search (Limoka-inspired, Hikkari-native)
# 🌐 https://github.com/Wers1xx/Hikkari

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import aiohttp
from hikkaritl.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)


@loader.tds
class HikkariFindMod(loader.Module):
    """Search modules in configured repos (like Limoka, for Hikkari)"""

    strings = {
        "name": "HikkariFind",
        "usage": "🔍 <b>Usage:</b> <code>{prefix}find &lt;query&gt;</code>",
        "searching": "🔍 <b>Searching</b> <code>{q}</code>…",
        "nothing": "🚫 <b>Nothing found for</b> <code>{q}</code>",
        "result": (
            "📦 <b>{name}</b>\n"
            "🔗 <code>{url}</code>\n"
            "{desc}\n"
            "· · ·"
        ),
        "header": "✨ <b>HikkariFind</b> — {n} result(s) for <code>{q}</code>:\n\n{body}",
        "install_btn": "⬇️ Install",
        "close_btn": "🔻 Close",
        "installing": "⏳ Installing <code>{name}</code>…",
        "installed": "✅ Installed <code>{name}</code>",
        "failed": "🚫 Failed to install <code>{name}</code>",
    }

    strings_ru = {
        "usage": "🔍 <b>Использование:</b> <code>{prefix}find &lt;запрос&gt;</code>",
        "searching": "🔍 <b>Ищу</b> <code>{q}</code>…",
        "nothing": "🚫 <b>Ничего не найдено по</b> <code>{q}</code>",
        "result": (
            "📦 <b>{name}</b>\n"
            "🔗 <code>{url}</code>\n"
            "{desc}\n"
            "· · ·"
        ),
        "header": "✨ <b>HikkariFind</b> — {n} результат(ов) по <code>{q}</code>:\n\n{body}",
        "install_btn": "⬇️ Установить",
        "close_btn": "🔻 Закрыть",
        "installing": "⏳ Устанавливаю <code>{name}</code>…",
        "installed": "✅ Установлен <code>{name}</code>",
        "failed": "🚫 Не удалось установить <code>{name}</code>",
    }

    def __init__(self):
        self._cache: dict[str, list[str]] = {}
        self._cache_ts: float = 0

    async def _repo_modules(self) -> list[tuple[str, str]]:
        """Return list of (name, raw_url) from Loader repos."""
        loader_mod = self.lookup("Loader")
        if not loader_mod:
            return []
        links = []
        try:
            for repo, mapping in (await loader_mod.get_repo_list()).items():
                for _k, url in mapping.items():
                    name = url.rsplit("/", 1)[-1].replace(".py", "")
                    links.append((name, url))
        except Exception:
            logger.exception("repo list")
        return links

    async def _fetch_desc(self, session: aiohttp.ClientSession, url: str) -> str:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200:
                    return ""
                text = await r.text()
            # first docstring or # meta developer
            m = re.search(r'"""(.+?)"""', text, re.S)
            if m:
                return utils.escape_html(m.group(1).strip().splitlines()[0][:120])
            m = re.search(r"# ?meta developer: ?(.+)", text)
            if m:
                return "dev: " + utils.escape_html(m.group(1).strip())
        except Exception:
            pass
        return ""

    @loader.command(alias="fmod")
    async def find(self, message: Message):
        """<query> — search modules in repos"""
        q = (utils.get_args_raw(message) or "").strip()
        if not q:
            await utils.answer(
                message, self.strings["usage"].format(prefix=self.get_prefix())
            )
            return

        status = await utils.answer(
            message, self.strings["searching"].format(q=utils.escape_html(q))
        )
        modules = await self._repo_modules()
        ql = q.lower()
        matched = [(n, u) for n, u in modules if ql in n.lower()]
        # also fuzzy: all tokens in name
        if not matched:
            tokens = [t for t in re.split(r"\s+", ql) if t]
            matched = [
                (n, u)
                for n, u in modules
                if all(t in n.lower() for t in tokens)
            ]

        if not matched:
            await utils.answer(
                status, self.strings["nothing"].format(q=utils.escape_html(q))
            )
            return

        matched = matched[:15]
        descs = {}
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_desc(session, u) for _, u in matched]
            results = await asyncio.gather(*tasks)
            for (n, u), d in zip(matched, results):
                descs[n] = d or "<i>no description</i>"

        body = "\n".join(
            self.strings["result"].format(
                name=utils.escape_html(n),
                url=utils.escape_html(u),
                desc=descs.get(n, ""),
            )
            for n, u in matched
        )
        text = self.strings["header"].format(
            n=len(matched), q=utils.escape_html(q), body=body
        )

        # Buttons: install top results
        rows = [
            [
                {
                    "text": f"⬇️ {n[:18]}",
                    "callback": self._install,
                    "args": (u, n),
                }
            ]
            for n, u in matched[:8]
        ]
        rows.append([{"text": self.strings["close_btn"], "action": "close"}])

        await self.inline.form(text, message=status, reply_markup=rows, silent=True)

    async def _install(self, call: InlineCall, url: str, name: str):
        await call.edit(self.strings["installing"].format(name=utils.escape_html(name)))
        loader_mod = self.lookup("Loader")
        if not loader_mod:
            await call.edit(self.strings["failed"].format(name=utils.escape_html(name)))
            return
        try:
            result = await loader_mod.download_and_install(url, None)
            # MODULE_LOADING_SUCCESS == 1 typically
            ok = result == 1 or result is True
        except Exception:
            logger.exception("find install")
            ok = False
        await call.edit(
            (self.strings["installed"] if ok else self.strings["failed"]).format(
                name=utils.escape_html(name)
            )
        )
