# meta developer: @Hikkari
# ©️ Wers1xx, 2025-2026
# Module presets: group loaded modules and share as one archive

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

import orjson
from hikkaritl.tl.types import Message

from .. import loader, utils

logger = logging.getLogger(__name__)

_REQUIRES_RE = re.compile(
    r"(?im)^(?:\s*#\s*(?:meta\s+)?requires\s*:\s*|\s*#\s*requires\s*:\s*)(.+)$"
)


def _reqs_from_text(text: str) -> set[str]:
    out: set[str] = set()
    for m in _REQUIRES_RE.finditer(text or ""):
        for part in re.split(r"[,;\s]+", m.group(1).strip()):
            part = part.strip().strip("'\"")
            if part and not part.startswith("http") and "/" not in part:
                out.add(part)
    return out


@loader.tds
class HikkariPresetsMod(loader.Module):
    """Group loaded modules into shareable presets (one archive)."""

    strings = {
        "name": "HikkariPresets",
        "usage": (
            "<b>Presets</b>\n"
            "<code>{p}presetlist</code> — list\n"
            "<code>{p}presetadd name ModA ModB</code> — create/update\n"
            "<code>{p}presetrm name</code> — delete\n"
            "<code>{p}presetexport name</code> — send zip\n"
            "<code>{p}presetimport</code> — reply to preset zip"
        ),
        "empty": "❌ No presets yet",
        "list": "<b>Presets:</b>\n{}",
        "added": "✅ Preset <code>{}</code>: {}",
        "removed": "🗑 Removed <code>{}</code>",
        "no_preset": "❌ Preset <code>{}</code> not found",
        "no_mods": "❌ No matching loaded modules",
        "exported": "✅ Preset <code>{}</code> — {} module(s)",
        "imported": "✅ Imported preset <code>{}</code> — {} module(s). Restart recommended.",
        "need_reply": "❌ Reply to a preset .zip",
        "bad_zip": "❌ Invalid preset archive",
    }

    def _presets(self) -> dict:
        data = self.get("presets", {})
        return data if isinstance(data, dict) else {}

    def _save_presets(self, data: dict):
        self.set("presets", data)

    def _mod_files_map(self) -> dict[str, Path]:
        """classname (lower) -> path on disk for this account."""
        out = {}
        root = Path(loader.LOADED_MODULES_DIR)
        if not root.is_dir():
            return out
        suffix = f"_{self.tg_id}.py"
        for p in root.glob(f"*{suffix}"):
            name = p.name[: -len(suffix)]
            out[name.lower()] = p
        return out

    def _resolve_mods(self, names: list[str]) -> list[Path]:
        amap = self._mod_files_map()
        found = []
        for n in names:
            key = n.strip().removesuffix(".py").lower()
            if key in amap:
                found.append(amap[key])
                continue
            # partial match
            for k, path in amap.items():
                if key in k or k in key:
                    found.append(path)
                    break
        # unique by path
        seen = set()
        uniq = []
        for p in found:
            if str(p) not in seen:
                seen.add(str(p))
                uniq.append(p)
        return uniq

    @loader.command()
    async def presetlist(self, message: Message):
        """List module presets"""
        data = self._presets()
        if not data:
            await utils.answer(message, self.strings["empty"])
            return
        lines = []
        for name, mods in data.items():
            mods = mods if isinstance(mods, list) else []
            lines.append(f"• <code>{utils.escape_html(name)}</code>: {', '.join(map(str, mods)) or '—'}")
        await utils.answer(message, self.strings["list"].format("\n".join(lines)))

    @loader.command()
    async def presetadd(self, message: Message):
        """<name> <ModuleA> [ModuleB…] — create/update preset"""
        args = utils.get_args_raw(message).strip().split()
        if len(args) < 2:
            await utils.answer(
                message, self.strings["usage"].format(p=self.get_prefix())
            )
            return
        name, *mods = args
        name = name.strip().lower()
        data = self._presets()
        data[name] = [m.removesuffix(".py") for m in mods]
        self._save_presets(data)
        await utils.answer(
            message,
            self.strings["added"].format(
                utils.escape_html(name),
                ", ".join(data[name]),
            ),
        )

    @loader.command()
    async def presetrm(self, message: Message):
        """<name> — delete preset"""
        name = (utils.get_args_raw(message) or "").strip().lower()
        if not name:
            await utils.answer(
                message, self.strings["usage"].format(p=self.get_prefix())
            )
            return
        data = self._presets()
        if name not in data:
            await utils.answer(message, self.strings["no_preset"].format(name))
            return
        data.pop(name, None)
        self._save_presets(data)
        await utils.answer(message, self.strings["removed"].format(name))

    @loader.command()
    async def presetexport(self, message: Message):
        """<name> | <name> ModA ModB — export preset as zip"""
        args = utils.get_args_raw(message).strip().split()
        if not args:
            await utils.answer(
                message, self.strings["usage"].format(p=self.get_prefix())
            )
            return
        name = args[0].strip().lower()
        data = self._presets()
        if len(args) >= 2:
            # ad-hoc: export these modules under name
            mod_names = [m.removesuffix(".py") for m in args[1:]]
        else:
            mod_names = data.get(name) or []
        if not mod_names:
            await utils.answer(message, self.strings["no_preset"].format(name))
            return
        paths = self._resolve_mods(mod_names)
        if not paths:
            await utils.answer(message, self.strings["no_mods"])
            return

        reqs: set[str] = set()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            meta = {
                "name": name,
                "modules": [p.name for p in paths],
                "format": "hikkari-preset-v1",
            }
            zf.writestr("preset.json", orjson.dumps(meta, option=orjson.OPT_INDENT_2))
            for p in paths:
                try:
                    raw = p.read_bytes()
                    zf.writestr(f"modules/{p.name}", raw)
                    reqs |= _reqs_from_text(raw.decode("utf-8", errors="replace"))
                except Exception:
                    logger.exception("preset export read %s", p)
            if reqs:
                zf.writestr(
                    "requirements.txt",
                    "# from preset modules\n" + "\n".join(sorted(reqs)) + "\n",
                )
        buf.seek(0)
        buf.name = f"preset-{name}.zip"
        await message.client.send_file(
            message.peer_id,
            buf,
            caption=self.strings["exported"].format(
                utils.escape_html(name), len(paths)
            ),
            reply_to=getattr(message, "id", None),
        )
        with contextlib.suppress(Exception):
            await message.delete()

    @loader.command()
    async def presetimport(self, message: Message):
        """Reply to preset .zip — install modules (+ pip reqs)"""
        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, self.strings["need_reply"])
            return
        data = await reply.download_media(bytes)
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except Exception:
            await utils.answer(message, self.strings["bad_zip"])
            return

        names = set(zf.namelist())
        meta = {}
        if "preset.json" in names:
            with contextlib.suppress(Exception):
                meta = orjson.loads(zf.read("preset.json"))
        installed = 0
        for name in names:
            base = Path(name).name
            if not base.endswith(".py"):
                continue
            # rewrite suffix to current tg_id
            stem = base
            if "_" in base:
                # ClassName_userid.py
                parts = base.rsplit("_", 1)
                if parts[-1].endswith(".py") and parts[-1][:-3].isdigit():
                    stem = f"{parts[0]}_{self.tg_id}.py"
            dest = Path(loader.LOADED_MODULES_DIR) / stem
            dest.write_bytes(zf.read(name))
            installed += 1

        pip_log = ""
        if "requirements.txt" in names:
            req = zf.read("requirements.txt").decode(errors="replace")
            lines = [
                ln.strip()
                for ln in req.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            if lines:
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".txt", delete=False, encoding="utf-8"
                ) as tf:
                    tf.write("\n".join(lines) + "\n")
                    req_path = tf.name
                try:
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "-q",
                        "-r",
                        req_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
                    pip_log = (out or b"").decode(errors="replace")[-400:]
                    logger.info("presetimport pip: %s", pip_log)
                except Exception as e:
                    logger.warning("presetimport pip failed: %s", e)
                finally:
                    with contextlib.suppress(Exception):
                        Path(req_path).unlink()

        zf.close()
        pname = meta.get("name") if isinstance(meta, dict) else "import"
        await utils.answer(
            message,
            self.strings["imported"].format(
                utils.escape_html(str(pname)), installed
            ),
        )
