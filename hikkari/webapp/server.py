# ©️ Wers1xx, 2025-2026
# Hikkari WebApp server

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
import secrets
import time
import re
from pathlib import Path
from typing import Any, Callable, Optional

from aiohttp import web

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type="application/json",
    )



class WebAppMessage:
    """In-memory message shim: run commands without posting to Saved Messages."""

    def __init__(self, client, text: str, chat_id: int):
        from hikkaritl.tl.types import PeerUser

        self.client = client
        self._client = client
        self.message = text
        self.raw_text = text
        self.text = text
        self.out = True
        self.id = int(time.time() * 1000) % 2_000_000_000
        self.chat_id = chat_id
        self.sender_id = getattr(client, "tg_id", chat_id)
        self.is_private = True
        self.is_channel = False
        self.is_group = False
        self.media = None
        self.entities = None
        self.via_bot_id = None
        self.reply_to = None
        self.fwd_from = None
        self.file = None
        self.sticker = None
        self.video = None
        self.photo = None
        self.document = None
        self.voice = None
        self.audio = None
        self.web_preview = None
        self.peer_id = PeerUser(int(chat_id))
        self.to_id = self.peer_id
        self._responses: list[str] = []

    async def get_reply_message(self):
        return None

    async def get_chat(self):
        return None

    async def get_sender(self):
        return getattr(self.client, "hikkari_me", None)

    async def edit(self, text=None, *args, **kwargs):
        if text is not None:
            s = text if isinstance(text, str) else str(text)
            self._responses.append(s)
            self.message = s
            self.text = s
            self.raw_text = s
        return self

    async def respond(self, text=None, *args, **kwargs):
        if text is not None:
            s = text if isinstance(text, str) else str(text)
            self._responses.append(s)
        return self

    async def reply(self, text=None, *args, **kwargs):
        return await self.respond(text, *args, **kwargs)

    async def delete(self, *args, **kwargs):
        return None

    def __str__(self):
        return self.message or ""


class WebAppState:
    def __init__(self, module: Any):
        self.module = module
        self.token = module._web_token  # admin
        self.view_token = module._web_view_token  # read-only
        self.started = time.time()

    @property
    def client(self):
        return self.module._client

    @property
    def db(self):
        return self.module._db

    @property
    def allmodules(self):
        return self.module.allmodules

    def role_for_token(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            if self.token and secrets.compare_digest(str(token), str(self.token)):
                return "admin"
            if self.view_token and secrets.compare_digest(
                str(token), str(self.view_token)
            ):
                return "view"
        except Exception:
            return None
        return None


def _extract_token(request: web.Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    token = request.query.get("token") or request.cookies.get("hikkari_token")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    return token or None


def require_auth(handler: Callable):
    """Any valid token (admin or view)."""

    async def wrapper(request: web.Request):
        state: WebAppState = request.app["state"]
        role = state.role_for_token(_extract_token(request))
        if not role:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        request["hikkari_role"] = role
        return await handler(request)

    return wrapper


def require_admin(handler: Callable):
    """Only admin token (owner / co-owner issued)."""

    async def wrapper(request: web.Request):
        state: WebAppState = request.app["state"]
        role = state.role_for_token(_extract_token(request))
        if role != "admin":
            return _json(
                {"ok": False, "error": "forbidden", "role": role or "none"},
                403,
            )
        request["hikkari_role"] = "admin"
        return await handler(request)

    return wrapper


def create_app(module: Any) -> web.Application:
    app = web.Application(client_max_size=32 * 1024 * 1024)
    app["state"] = WebAppState(module)

    async def index(_request: web.Request) -> web.Response:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        return web.Response(text=html, content_type="text/html")

    async def static_file(request: web.Request) -> web.Response:
        name = request.match_info["path"]
        path = (STATIC / name).resolve()
        if not str(path).startswith(str(STATIC.resolve())) or not path.is_file():
            return web.Response(status=404, text="not found")
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return web.Response(body=path.read_bytes(), content_type=ctype)

    @require_auth
    async def api_status(request: web.Request) -> web.Response:
        st: WebAppState = request.app["state"]
        me = getattr(st.client, "hikkari_me", None) or getattr(st.client, "_me", None)
        from .. import version

        role = request.get("hikkari_role") or "view"
        mods = list(st.allmodules.modules)
        payload = {
            "ok": True,
            "version": ".".join(map(str, version.__version__)),
            "uptime": int(time.time() - st.started),
            "role": role,
            "user": {
                "id": getattr(me, "id", None),
                "name": getattr(me, "first_name", None),
                "username": getattr(me, "username", None),
            },
        }
        # Full stats only for admin; viewers get overview without module inventory
        if role == "admin":
            payload["modules"] = len(mods)
        else:
            payload["modules"] = None
        return _json(payload)

    @require_admin
    async def api_modules(request: web.Request) -> web.Response:
        st: WebAppState = request.app["state"]
        out = []
        for mod in st.allmodules.modules:
            name = mod.__class__.__name__
            strings_name = None
            try:
                strings_name = mod.strings.get("name") if hasattr(mod, "strings") else None
            except Exception:
                pass
            cmds = sorted(getattr(mod, "hikkari_commands", {}).keys())
            has_cfg = bool(getattr(mod, "config", None))
            origin = getattr(mod, "__origin__", "core")
            is_core = "core" in str(origin).lower() or origin == "<core>"
            out.append(
                {
                    "class": name,
                    "name": strings_name or name,
                    "commands": cmds,
                    "has_config": has_cfg,
                    "core": is_core,
                    "origin": str(origin)[:80],
                }
            )
        out.sort(key=lambda x: (not x["core"], x["name"].lower()))
        return _json({"ok": True, "modules": out})

    def _mod_by_name(st: WebAppState, name: str):
        for mod in st.allmodules.modules:
            if mod.__class__.__name__ == name:
                return mod
            try:
                if hasattr(mod, "strings") and mod.strings.get("name") == name:
                    return mod
            except Exception:
                pass
        return None

    @require_admin
    async def api_module_config(request: web.Request) -> web.Response:
        st: WebAppState = request.app["state"]
        name = request.match_info["name"]
        mod = _mod_by_name(st, name)
        if not mod or not getattr(mod, "config", None):
            return _json({"ok": False, "error": "no config"}, 404)
        opts = []
        cfg = mod.config
        for key in list(cfg._config.keys()) if hasattr(cfg, "_config") else list(cfg.keys()):
            try:
                val = cfg[key]
            except Exception:
                val = None
            meta = cfg._config.get(key) if hasattr(cfg, "_config") else None
            doc = ""
            if meta is not None:
                doc = getattr(meta, "doc", "") or ""
                if callable(doc):
                    try:
                        doc = doc()
                    except Exception:
                        doc = str(doc)
            validator = None
            if meta is not None and getattr(meta, "validator", None):
                validator = getattr(meta.validator, "internal_id", None) or type(
                    meta.validator
                ).__name__
            opts.append(
                {
                    "key": key,
                    "value": val,
                    "doc": str(doc)[:500],
                    "validator": validator,
                }
            )
        return _json({"ok": True, "module": name, "options": opts})

    @require_admin
    async def api_module_config_set(request: web.Request) -> web.Response:
        st: WebAppState = request.app["state"]
        name = request.match_info["name"]
        mod = _mod_by_name(st, name)
        if not mod or not getattr(mod, "config", None):
            return _json({"ok": False, "error": "no config"}, 404)
        try:
            body = await request.json()
        except Exception:
            return _json({"ok": False, "error": "invalid json"}, 400)
        key = body.get("key")
        value = body.get("value")
        if not key or key not in getattr(mod.config, "_config", {}):
            # try plain keys
            if key not in mod.config:
                return _json({"ok": False, "error": "unknown option"}, 400)
        try:
            # parse strings that look like json
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception:
                    pass
            mod.config[key] = value
        except Exception as e:
            return _json({"ok": False, "error": str(e)}, 400)
        return _json({"ok": True, "key": key, "value": mod.config[key]})

    @require_admin
    async def api_run_command(request: web.Request) -> web.Response:
        st: WebAppState = request.app["state"]
        try:
            body = await request.json()
        except Exception:
            return _json({"ok": False, "error": "invalid json"}, 400)

        cmd = (body.get("command") or "").strip()
        # strip any accidental prefix characters
        while cmd and cmd[0] in ".!/":
            cmd = cmd[1:].strip()
        args = (body.get("args") or "").strip()
        if not cmd:
            return _json({"ok": False, "error": "empty command"}, 400)

        # Resolve alias / command name like the dispatcher does
        commands = getattr(st.allmodules, "commands", {}) or {}
        resolved = cmd.lower()
        func = commands.get(resolved)
        if not func:
            # try find_alias
            with contextlib.suppress(Exception):
                alias = st.allmodules.find_alias(resolved, include_legacy=True)
                if alias:
                    resolved = alias
                    func = commands.get(resolved)
        if not func:
            return _json(
                {"ok": False, "error": f"command not found: {cmd}"},
                404,
            )

        try:
            from .. import main as hmain

            prefix = st.db.get(hmain.__name__, "command_prefix", ".") or "."
        except Exception:
            prefix = "."
        if not isinstance(prefix, str) or not prefix:
            prefix = "."

        text = f"{prefix}{resolved}"
        if args:
            text = f"{text} {args}"

        chat_id = int(getattr(st.client, "tg_id", 0) or 0)
        message = WebAppMessage(st.client, text, chat_id)

        try:
            await func(message)
        except Exception as e:
            logger.exception("WebApp command %s failed", resolved)
            # still return captured output if any
            out = "\n\n".join(message._responses) if message._responses else ""
            return _json(
                {
                    "ok": False,
                    "error": str(e),
                    "command": resolved,
                    "output": out,
                },
                500,
            )

        output = "\n\n".join(message._responses) if message._responses else (
            message.text if message.text != text else ""
        )
        return _json(
            {
                "ok": True,
                "command": resolved,
                "args": args,
                "output": output,
            }
        )


    @require_admin
    @require_admin
    async def api_upload(request: web.Request) -> web.Response:
        """Upload media to x0.at and return public URL for config."""
        st = request.app["state"]
        reader = await request.multipart()
        field = await reader.next()
        if field is None:
            return _json({"ok": False, "error": "no file"}, 400)
        filename = field.filename or f"upload_{int(time.time())}"
        data = await field.read()
        if not data:
            return _json({"ok": False, "error": "empty file"}, 400)

        uploads = Path(st.module.get("upload_dir") or (Path.home() / "Hikkari" / "downloads"))
        uploads.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(filename).name)[:120]
        dest = uploads / safe
        dest.write_bytes(data)

        x0_url = None
        err = None
        try:
            import aiohttp
            form = aiohttp.FormData()
            form.add_field(
                "file",
                data,
                filename=safe,
                content_type=field.headers.get("Content-Type", "application/octet-stream"),
            )
            async with aiohttp.ClientSession() as session:
                async with session.post("https://x0.at/", data=form, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    text = (await resp.text()).strip()
                    if resp.status < 400 and text.startswith("http"):
                        x0_url = text.split()[0].strip()
                    else:
                        err = f"x0.at HTTP {resp.status}: {text[:200]}"
        except Exception as e:
            logger.exception("x0.at upload failed")
            err = str(e)[:200]

        # Optional: also send to Saved Messages for convenience
        with contextlib.suppress(Exception):
            cap = f"WebApp upload: {safe}"
            if x0_url:
                cap += f"\n{x0_url}"
            await st.client.send_file("me", str(dest), caption=cap)

        if not x0_url:
            return _json({"ok": False, "error": err or "x0.at failed", "local": str(dest)}, 502)
        return _json(
            {
                "ok": True,
                "url": x0_url,
                "filename": safe,
                "local": str(dest),
                "hint": "Скопируй url в конфиг",
            }
        )


    async def api_db_get(request: web.Request) -> web.Response:
        st: WebAppState = request.app["state"]
        owner = request.query.get("owner") or "hikkari.main"
        key = request.query.get("key")
        if key:
            return _json({"ok": True, "value": st.db.get(owner, key)})
        # limited dump of owner keys
        try:
            data = dict(st.db.get(owner, None) or {})
            if data is None:
                data = {}
        except Exception:
            data = {}
        # if structure is module->keys
        try:
            raw = st.db[owner] if owner in st.db else {}
            data = dict(raw) if isinstance(raw, dict) else {}
        except Exception:
            data = {}
        return _json({"ok": True, "owner": owner, "data": data})

    app.router.add_get("/", index)
    app.router.add_get("/static/{path:.*}", static_file)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/modules", api_modules)
    app.router.add_get("/api/modules/{name}/config", api_module_config)
    app.router.add_post("/api/modules/{name}/config", api_module_config_set)
    app.router.add_post("/api/command", api_run_command)
    app.router.add_post("/api/upload", api_upload)
    app.router.add_get("/api/db", api_db_get)
    return app


async def start_webapp(module: Any, host: str, port: int) -> web.AppRunner:
    app = create_app(module)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Hikkari WebApp listening on http://%s:%s", host, port)
    return runner
