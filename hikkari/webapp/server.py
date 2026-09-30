# ©️ Wers1xx, 2025-2026
# Hikkari WebApp server

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import secrets
import time
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

        mods = list(st.allmodules.modules)
        return _json(
            {
                "ok": True,
                "version": ".".join(map(str, version.__version__)),
                "uptime": int(time.time() - st.started),
                "modules": len(mods),
                "role": request.get("hikkari_role") or "view",
                "user": {
                    "id": getattr(me, "id", None),
                    "name": getattr(me, "first_name", None),
                    "username": getattr(me, "username", None),
                },
            }
        )

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
        cmd = (body.get("command") or "").strip().lstrip(".")
        args = body.get("args") or ""
        if not cmd:
            return _json({"ok": False, "error": "empty command"}, 400)
        # Send as message to Saved Messages so full dispatcher handles it
        prefix = st.db.get("hikkari", "command_prefix", st.db.get(__import__("hikkari.main", fromlist=["main"]).__name__ if False else "hikkari.main", "command_prefix", "."))
        text = f"{prefix}{cmd}"
        if args:
            text = f"{text} {args}"
        try:
            await st.client.send_message("me", text)
        except Exception as e:
            return _json({"ok": False, "error": str(e)}, 500)
        return _json({"ok": True, "sent": text})

    @require_admin
    async def api_upload(request: web.Request) -> web.Response:
        st: WebAppState = request.app["state"]
        reader = await request.multipart()
        field = await reader.next()
        if field is None:
            return _json({"ok": False, "error": "no file"}, 400)
        filename = field.filename or f"upload_{int(time.time())}"
        data = await field.read()
        uploads = Path(st.module.get("upload_dir") or (Path.home() / "Hikkari" / "downloads"))
        uploads.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in filename if c.isalnum() or c in "._-")[:120] or "file"
        dest = uploads / safe
        dest.write_bytes(data)
        # also try send to Saved Messages
        try:
            await st.client.send_file("me", str(dest), caption=f"WebApp upload: {safe}")
        except Exception as e:
            logger.warning("upload send failed: %s", e)
        return _json({"ok": True, "path": str(dest), "size": len(data)})

    @require_admin
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
