# ©️ Wers1xx, 2025-2026
# Hikkari WebUI login + optional public tunnel (random local port)

from __future__ import annotations

import asyncio
import logging
import random
import re
import secrets
import socket
import subprocess
from pathlib import Path
from typing import Any, Optional

from aiohttp import web
from hikkaritl.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from hikkaritl.sessions import MemorySession

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def _free_port(prefer_min: int = 16000, prefer_max: int = 32000) -> int:
    """Pick a free TCP port (random each run to avoid bind conflicts)."""
    for _ in range(40):
        port = random.randint(prefer_min, prefer_max)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return int(s.getsockname()[1])


class WebAuth:
    """Browser login for Hikkari (phone / code / 2FA)."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        *,
        proxy: Any = None,
        connection: Any = None,
        device_model: str = "Hikkari",
        app_version: str = "1.0",
    ):
        self.api_id = int(api_id)
        self.api_hash = str(api_hash)
        self.proxy = proxy
        self.connection = connection
        self.device_model = device_model
        self.app_version = app_version

        self.port = _free_port()
        self.token = secrets.token_urlsafe(16)
        self.client = None
        self.phone: Optional[str] = None
        self.phone_code_hash: Optional[str] = None
        self.done = asyncio.Event()
        self.success = False
        self.error: Optional[str] = None
        self._runner: Optional[web.AppRunner] = None
        self._tunnel_proc: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.local_url = f"http://127.0.0.1:{self.port}/?token={self.token}"
        self.stage = "phone"  # phone | code | 2fa | done

    async def _ensure_client(self):
        if self.client is not None:
            return self.client
        from ..tl_cache import CustomTelegramClient

        kwargs = dict(
            session=MemorySession(),
            api_id=self.api_id,
            api_hash=self.api_hash,
            device_model=self.device_model,
            system_version="WebUI",
            app_version=self.app_version,
            lang_code="en",
            system_lang_code="en-US",
        )
        if self.connection is not None:
            kwargs["connection"] = self.connection
        if self.proxy is not None:
            kwargs["proxy"] = self.proxy
        self.client = CustomTelegramClient(**kwargs)
        await self.client.connect()
        return self.client

    def _html_page(self, body: str) -> str:
        return (
            "<!DOCTYPE html><html lang='ru'><head>"
            "<meta charset='utf-8'/>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
            "<title>Hikkari Login</title>"
            "<style>"
            "html,body{margin:0;height:100%;background:#000;color:#f2f2f5;"
            "font-family:system-ui,sans-serif}"
            ".wrap{min-height:100%;display:grid;place-items:center;padding:24px;"
            "background:radial-gradient(ellipse at 50% 0%,#1a1a22 0%,#000 55%)}"
            ".card{width:min(400px,100%);background:rgba(16,16,22,.85);"
            "border:1px solid rgba(255,255,255,.08);border-radius:24px;"
            "padding:32px 24px;text-align:center;"
            "box-shadow:0 24px 80px rgba(0,0,0,.5)}"
            ".logo{width:88px;height:88px;border-radius:50%;object-fit:cover;"
            "box-shadow:0 0 40px rgba(255,255,255,.25);margin-bottom:12px}"
            "h1{margin:8px 0 4px;font-size:1.5rem}"
            "p{color:#8a8a9a;font-size:14px;margin:0 0 18px}"
            "input{width:100%;padding:12px 14px;border-radius:12px;"
            "border:1px solid rgba(255,255,255,.1);background:#0a0a0e;color:#fff;"
            "font-size:15px;margin:8px 0;box-sizing:border-box}"
            "button{width:100%;padding:12px;border:0;border-radius:12px;"
            "font-weight:600;font-size:15px;"
            "background:linear-gradient(180deg,#f5f5f7,#c8c8d0);color:#111;"
            "cursor:pointer;margin-top:8px}"
            ".err{color:#fb7185;min-height:1.2em;font-size:13px}"
            ".ok{color:#6ee7b7}"
            "</style></head><body><div class='wrap'><div class='card'>"
            "<img class='logo' src='/static/logo-star.jpg' alt='Hikkari'/>"
            f"{body}"
            "</div></div></body></html>"
        )

    async def index(self, request: web.Request) -> web.Response:
        tok = request.query.get("token", "")
        if not tok or not secrets.compare_digest(str(tok), self.token):
            return web.Response(
                text=self._html_page("<h1>403</h1><p>Invalid or missing token</p>"),
                content_type="text/html",
                status=403,
            )
        err = self.error or ""
        if self.stage == "done" and self.success:
            body = (
                '<h1 class="ok">Done</h1>'
                "<p>Logged in successfully. You can close this tab.</p>"
            )
        elif self.stage == "2fa":
            body = (
                "<h1>2FA</h1><p>Enter your two-factor password</p>"
                f"<form method='post' action='/api/2fa?token={self.token}'>"
                "<input name='password' type='password' "
                "placeholder='2FA password' required autofocus/>"
                "<button type='submit'>Sign in</button></form>"
                f'<p class="err">{err}</p>'
            )
        elif self.stage == "code":
            body = (
                f"<h1>Code</h1><p>Code sent to <b>{self.phone}</b></p>"
                f"<form method='post' action='/api/code?token={self.token}'>"
                "<input name='code' inputmode='numeric' "
                "placeholder='12345' required autofocus/>"
                "<button type='submit'>Confirm</button></form>"
                f'<p class="err">{err}</p>'
            )
        else:
            body = (
                "<h1>Hikkari</h1><p>Sign in via WebUI</p>"
                f"<form method='post' action='/api/phone?token={self.token}'>"
                "<input name='phone' placeholder='+79001234567' required autofocus/>"
                "<button type='submit'>Get code</button></form>"
                f'<p class="err">{err}</p>'
            )
        return web.Response(text=self._html_page(body), content_type="text/html")

    async def static(self, request: web.Request) -> web.Response:
        name = request.match_info["path"]
        path = (STATIC / name).resolve()
        if not str(path).startswith(str(STATIC.resolve())) or not path.is_file():
            return web.Response(status=404)
        return web.FileResponse(path)

    def _tok_ok(self, request: web.Request) -> bool:
        tok = request.query.get("token") or ""
        return bool(tok) and secrets.compare_digest(str(tok), self.token)

    async def api_phone(self, request: web.Request) -> web.Response:
        if not self._tok_ok(request):
            return web.Response(status=403, text="forbidden")
        data = await request.post()
        phone = str(data.get("phone", "")).strip()
        self.error = None
        try:
            client = await self._ensure_client()
            result = await client.send_code_request(phone)
            self.phone = phone
            self.phone_code_hash = result.phone_code_hash
            self.stage = "code"
        except PhoneNumberInvalidError:
            self.error = "Invalid phone number"
        except FloodWaitError as e:
            self.error = f"FloodWait: wait {e.seconds}s"
        except Exception as e:
            logger.exception("phone")
            self.error = str(e)
        raise web.HTTPFound(f"/?token={self.token}")

    async def api_code(self, request: web.Request) -> web.Response:
        if not self._tok_ok(request):
            return web.Response(status=403, text="forbidden")
        data = await request.post()
        code = str(data.get("code", "")).strip().replace(" ", "")
        self.error = None
        try:
            client = await self._ensure_client()
            await client.sign_in(
                self.phone, code, phone_code_hash=self.phone_code_hash
            )
            self.stage = "done"
            self.success = True
            self.done.set()
        except SessionPasswordNeededError:
            self.stage = "2fa"
        except PhoneCodeInvalidError:
            self.error = "Invalid code"
        except PhoneCodeExpiredError:
            self.error = "Code expired — request again"
            self.stage = "phone"
        except FloodWaitError as e:
            self.error = f"FloodWait: {e.seconds}s"
        except Exception as e:
            logger.exception("code")
            self.error = str(e)
        raise web.HTTPFound(f"/?token={self.token}")

    async def api_2fa(self, request: web.Request) -> web.Response:
        if not self._tok_ok(request):
            return web.Response(status=403, text="forbidden")
        data = await request.post()
        password = str(data.get("password", ""))
        self.error = None
        try:
            client = await self._ensure_client()
            await client.sign_in(password=password)
            self.stage = "done"
            self.success = True
            self.done.set()
        except PasswordHashInvalidError:
            self.error = "Invalid 2FA password"
        except FloodWaitError as e:
            self.error = f"FloodWait: {e.seconds}s"
        except Exception as e:
            logger.exception("2fa")
            self.error = str(e)
        raise web.HTTPFound(f"/?token={self.token}")

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self.index)
        app.router.add_get("/static/{path:.*}", self.static)
        app.router.add_post("/api/phone", self.api_phone)
        app.router.add_post("/api/code", self.api_code)
        app.router.add_post("/api/2fa", self.api_2fa)
        return app

    async def start_server(self):
        app = self._build_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info("WebUI auth on port %s", self.port)

    async def stop(self):
        if self._tunnel_proc and self._tunnel_proc.poll() is None:
            try:
                self._tunnel_proc.terminate()
            except Exception:
                pass
            self._tunnel_proc = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def start_tunnel(self) -> Optional[str]:
        """Expose local port via SSH reverse tunnel; parse public URL."""
        cmds = [
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ExitOnForwardFailure=yes",
                "-R",
                f"80:127.0.0.1:{self.port}",
                "nokey@localhost.run",
            ],
            [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "ServerAliveInterval=30",
                "-R",
                f"80:127.0.0.1:{self.port}",
                "serveo.net",
            ],
        ]
        for cmd in cmds:
            try:
                self._tunnel_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except FileNotFoundError:
                logger.warning("ssh not found — tunnel skipped")
                return None
            except Exception:
                logger.exception("tunnel start failed")
                continue

            url = await self._wait_tunnel_url(timeout=25)
            if url:
                self.public_url = url.rstrip("/") + f"/?token={self.token}"
                return self.public_url
            try:
                self._tunnel_proc.terminate()
            except Exception:
                pass
            self._tunnel_proc = None
        return None

    async def _wait_tunnel_url(self, timeout: float = 25) -> Optional[str]:
        if not self._tunnel_proc or not self._tunnel_proc.stdout:
            return None
        pattern = re.compile(
            r"https?://[a-zA-Z0-9.-]+\.(localhost\.run|serveo\.net|lhr\.life)[^\s]*"
        )
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout

        def read_line():
            return self._tunnel_proc.stdout.readline()

        while loop.time() < deadline:
            if self._tunnel_proc.poll() is not None:
                return None
            line = await loop.run_in_executor(None, read_line)
            if not line:
                await asyncio.sleep(0.2)
                continue
            logger.debug("tunnel: %s", line.strip())
            m = pattern.search(line)
            if m:
                return m.group(0).rstrip("./")
        return None

    async def run_until_login(self, timeout: float = 600) -> Any:
        """Start server (+tunnel), wait for login, return connected client or None."""
        await self.start_server()
        public = None
        try:
            public = await self.start_tunnel()
        except Exception:
            logger.exception("tunnel error")

        print("\nHikkari WebUI login")
        print(f"  Local:  {self.local_url}")
        if public:
            print(f"  Public: {public}")
        else:
            print("  (tunnel unavailable — open Local URL on this device)")
        print("  Waiting for browser login...\n")

        try:
            await asyncio.wait_for(self.done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.error = "timeout"
            await self.stop()
            return None

        if not self.success or self.client is None:
            await self.stop()
            return None

        await self.stop()
        return self.client
