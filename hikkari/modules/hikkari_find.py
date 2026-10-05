# ©️ Wers1xx, 2025-2026
# HikkariFind — module search (Limoka-style index + configured repos)
# 🌐 https://github.com/Wers1xx/Hikkari

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import aiohttp
from hikkaritl.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

# Community catalog (same data Limoka uses)
LIMOKA_INDEX = (
    "https://raw.githubusercontent.com/MuRuLOSE/limoka/main/modules.json"
)
# Official / team lists
EXTRA_FULL = [
    "https://raw.githubusercontent.com/Wersixx/Wers1xx/main/full.txt",
]


def _raw_url_from_key(key: str) -> str:
    """coddrago/modules/foo.py → raw.githubusercontent.com/..."""
    key = key.lstrip("/")
    parts = key.split("/")
    if len(parts) >= 2 and key.endswith(".py"):
        # user/repo/path... or user/path
        user = parts[0]
        # common patterns: user/modules/file.py, user/repo/file.py
        rest = "/".join(parts[1:])
        # try main branch
        return f"https://raw.githubusercontent.com/{user}/{parts[1]}/main/{'/'.join(parts[2:])}" if len(parts) > 2 else f"https://raw.githubusercontent.com/{user}/main/{rest}"
    return f"https://raw.githubusercontent.com/{key}"


def _normalize_raw(key: str, meta: dict) -> str:
    for k in ("url", "link", "raw", "download"):
        v = meta.get(k) if isinstance(meta, dict) else None
        if isinstance(v, str) and v.startswith("http"):
            return v.replace("/blob/", "/raw/")
    # key like "Author/Repo/path/Mod.py"
    parts = key.replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[-1].endswith(".py"):
        user, repo = parts[0], parts[1]
        path = "/".join(parts[2:])
        return f"https://raw.githubusercontent.com/{user}/{repo}/main/{path}"
    if len(parts) == 2 and parts[-1].endswith(".py"):
        return f"https://raw.githubusercontent.com/{parts[0]}/modules/main/{parts[1]}"
    # fallback limoka mirror style
    return f"https://raw.githubusercontent.com/{key}" if "/" in key else key


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
        "failed": "🚫 Failed to install <code>{name}</code>",
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
        "failed": "🚫 Не удалось установить <code>{name}</code>",
    }

    def __init__(self):
        self._index: list[dict[str, str]] = []
        self._index_ts: float = 0.0

    async def _load_index(self, force: bool = False) -> list[dict[str, str]]:
        if self._index and not force and time.time() - self._index_ts < 600:
            return self._index

        entries: list[dict[str, str]] = []
        seen: set[str] = set()

        async with aiohttp.ClientSession() as session:
            # 1) Limoka catalog
            try:
                async with session.get(
                    LIMOKA_INDEX, timeout=aiohttp.ClientTimeout(total=20)
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
                                    or key.split("/")[-1].replace(".py", "")
                                )
                                desc = str(
                                    meta.get("description")
                                    or meta.get("cls_doc")
                                    or ""
                                )
                                if isinstance(desc, dict):
                                    desc = desc.get("ru") or desc.get("en") or next(
                                        iter(desc.values()), ""
                                    )
                                cmds = meta.get("commands") or []
                                cmd_blob = " ".join(
                                    str(c) for c in cmds
                                ) if isinstance(cmds, list) else str(cmds)
                                url = _normalize_raw(str(key), meta)
                                blob = f"{name} {desc} {cmd_blob} {key}".lower()
                                if url not in seen:
                                    seen.add(url)
                                    entries.append(
                                        {
                                            "name": name,
                                            "desc": (desc or "")[:160],
                                            "url": url,
                                            "blob": blob,
                                        }
                                    )
            except Exception:
                logger.exception("limoka index")

            # 2) full.txt lists → build raw urls from MODULES_REPO style
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
                                "blob": name.lower(),
                            }
                        )
                except Exception:
                    logger.debug("full.txt fail %s", full_url, exc_info=True)

            # 3) Loader in-memory repo list
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
                                    "blob": name.lower(),
                                }
                            )
                except Exception:
                    logger.exception("loader repo list")

        self._index = entries
        self._index_ts = time.time()
        logger.info("HikkariFind index: %s modules", len(entries))
        return entries

    def _score(self, entry: dict[str, str], q: str) -> int:
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
        # camelCase / ServerInfo ↔ serverinfo
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

        index = await self._load_index()
        scored = []
        for e in index:
            sc = self._score(e, q)
            if sc > 0:
                scored.append((sc, e))
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
                    "args": (e["url"], e["name"]),
                }
            ]
            for e in matched[:8]
        ]
        rows.append([{"text": self.strings["close_btn"], "action": "close"}])

        await self.inline.form(text, message=status, reply_markup=rows, silent=True)

    async def _install(self, call: InlineCall, url: str, name: str):
        await call.edit(
            self.strings["installing"].format(name=utils.escape_html(name))
        )
        loader_mod = self.lookup("Loader")
        if not loader_mod:
            await call.edit(
                self.strings["failed"].format(name=utils.escape_html(name))
            )
            return
        try:
            result = await loader_mod.download_and_install(url, None)
            ok = result == 1 or result is True
        except Exception:
            logger.exception("HikkariFind install")
            ok = False
        await call.edit(
            (self.strings["installed"] if ok else self.strings["failed"]).format(
                name=utils.escape_html(name)
            )
        )
