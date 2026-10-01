# ©️ Wers1xx, 2025-2026
# Hikkari WebUI login — local server + cloudflared only (no serveo/localhost.run)

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import secrets
import socket
import stat
import subprocess
import urllib.request
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


def _free_port(lo: int = 17000, hi: int = 29000) -> int:
    for _ in range(50):
        port = random.randint(lo, hi)
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


def _ensure_cloudflared() -> Optional[str]:
    from shutil import which

    found = which("cloudflared")
    if found:
        return found
    try:
        from .. import main as _main

        bin_dir = Path(_main.BASE_PATH) / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        target = bin_dir / "cloudflared"
        if target.is_file() and os.access(target, os.X_OK):
            return str(target)
        url = (
            "https://github.com/cloudflare/cloudflared/releases/latest/"
            "download/cloudflared-linux-amd64"
        )
        logger.info("Downloading cloudflared…")
        urllib.request.urlretrieve(url, str(target))
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(target)
    except Exception:
        logger.exception("cloudflared auto-install failed")
        return None


class WebAuth:
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
        self.token = secrets.token_urlsafe(18)
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
        self.stage = "phone"

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
            "html,body{margin:0;min-height:100%;background:#000;color:#f2f2f5;"
            "font-family:system-ui,sans-serif}"
            ".wrap{min-height:100vh;display:grid;place-items:center;padding:24px;"
            "background:radial-gradient(ellipse at 50% 0%,rgba(50,50,70,.45),#000 55%)}"
            ".card{width:min(400px,100%);background:rgba(14,14,20,.92);"
            "border:1px solid rgba(255,255,255,.08);border-radius:28px;"
            "padding:36px 26px;text-align:center;box-shadow:0 24px 80px rgba(0,0,0,.55)}"
            ".logo{width:92px;height:92px;border-radius:50%;object-fit:cover;"
            "box-shadow:0 0 40px rgba(255,255,255,.3);margin:0 auto 12px;display:block}"
            "h1{margin:8px 0 4px;font-size:1.5rem}"
            "p{color:#8a8a9a;font-size:14px;margin:0 0 16px}"
            "input{width:100%;padding:13px 14px;border-radius:14px;box-sizing:border-box;"
            "border:1px solid rgba(255,255,255,.1);background:#0a0a0e;color:#fff;"
            "font-size:15px;margin:8px 0}"
            "button{width:100%;padding:13px;border:0;border-radius:14px;font-weight:700;"
            "font-size:15px;background:linear-gradient(180deg,#f5f5f7,#c8c8d0);"
            "color:#111;cursor:pointer;margin-top:6px}"
            ".err{color:#fb7185;font-size:13px;min-height:1.2em}"
            ".ok{color:#6ee7b7}"
            ".foot{margin-top:16px;font-size:11px;color:#555}"
            "</style></head><body><div class='wrap'><div class='card'>"
            "<img class='logo' src='/static/logo-star.jpg' alt='Hikkari'/>"
            f"{body}<div class='foot'>Hikkari · WebUI</div>"
            "</div></div></body></html>"
        )

    def _tok_ok(self, request: web.Request) -> bool:
        tok = request.query.get("token") or ""
        return bool(tok) and secrets.compare_digest(str(tok), self.token)

    async def index(self, request: web.Request) -> web.Response:
        if not self._tok_ok(request):
            return web.Response(
                text=self._html_page("<h1>403</h1><p>Invalid link</p>"),
                content_type="text/html",
                status=403,
            )
        err = self.error or ""
        if self.stage == "done" and self.success:
            body = '<h1 class="ok">Готово</h1><p>Вход выполнен. Закрой вкладку.</p>'
        elif self.stage == "2fa":
            body = (
                "<h1>2FA</h1><p>Пароль двухфакторной защиты</p>"
                f"<form method='post' action='/api/2fa?token={self.token}'>"
                "<input name='password' type='password' placeholder='2FA' required autofocus/>"
                "<button type='submit'>Войти</button></form>"
                f'<p class="err">{err}</p>'
            )
        elif self.stage == "code":
            body = (
                f"<h1>Код</h1><p>Отправлен на <b>{self.phone}</b></p>"
                f"<form method='post' action='/api/code?token={self.token}'>"
                "<input name='code' inputmode='numeric' placeholder='12345' required autofocus/>"
                "<button type='submit'>Далее</button></form>"
                f'<p class="err">{err}</p>'
            )
        else:
            body = (
                "<h1>Hikkari</h1><p>Вход в аккаунт</p>"
                f"<form method='post' action='/api/phone?token={self.token}'>"
                "<input name='phone' placeholder='+79001234567' required autofocus/>"
                "<button type='submit'>Получить код</button></form>"
                f'<p class="err">{err}</p>'
            )
        return web.Response(text=self._html_page(body), content_type="text/html")

    async def static(self, request: web.Request) -> web.Response:
        name = request.match_info["path"]
        path = (STATIC / name).resolve()
        if not str(path).startswith(str(STATIC.resolve())) or not path.is_file():
            return web.Response(status=404)
        return web.FileResponse(path)

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
            self.error = "Неверный номер"
        except FloodWaitError as e:
            self.error = f"FloodWait: {e.seconds}с"
        except Exception as e:
            logger.exception("phone")
            self.error = str(e)[:200]
        raise web.HTTPFound(f"/?token={self.token}")

    async def api_code(self, request: web.Request) -> web.Response:
        if not self._tok_ok(request):
            return web.Response(status=403, text="forbidden")
        data = await request.post()
        code = str(data.get("code", "")).strip().replace(" ", "")
        self.error = None
        try:
            client = await self._ensure_client()
            await client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
            self.stage = "done"
            self.success = True
            self.done.set()
        except SessionPasswordNeededError:
            self.stage = "2fa"
        except PhoneCodeInvalidError:
            self.error = "Неверный код"
        except PhoneCodeExpiredError:
            self.error = "Код истёк"
            self.stage = "phone"
        except FloodWaitError as e:
            self.error = f"FloodWait: {e.seconds}с"
        except Exception as e:
            logger.exception("code")
            self.error = str(e)[:200]
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
            self.error = "Неверный 2FA"
        except FloodWaitError as e:
            self.error = f"FloodWait: {e.seconds}с"
        except Exception as e:
            logger.exception("2fa")
            self.error = str(e)[:200]
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
        self._runner = web.AppRunner(self._build_app())
        await self._runner.setup()
        await web.TCPSite(self._runner, "0.0.0.0", self.port).start()
        logger.info("Hikkari WebUI on 0.0.0.0:%s", self.port)

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
        """Public link via cloudflared only — no serveo / localhost.run."""
        binary = _ensure_cloudflared()
        if not binary:
            return None
        try:
            self._tunnel_proc = subprocess.Popen(
                [
                    binary,
                    "tunnel",
                    "--no-autoupdate",
                    "--url",
                    f"http://127.0.0.1:{self.port}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except Exception:
            logger.exception("cloudflared failed")
            return None
        url = await self._wait_cf_url(40)
        if url:
            self.public_url = f"{url.rstrip('/')}/?token={self.token}"
            return self.public_url
        try:
            self._tunnel_proc.terminate()
        except Exception:
            pass
        self._tunnel_proc = None
        return None

    async def _wait_cf_url(self, timeout: float = 40) -> Optional[str]:
        if not self._tunnel_proc or not self._tunnel_proc.stdout:
            return None
        pat = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout

        def readline():
            return self._tunnel_proc.stdout.readline()

        while loop.time() < deadline:
            if self._tunnel_proc.poll() is not None:
                return None
            line = await loop.run_in_executor(None, readline)
            if not line:
                await asyncio.sleep(0.1)
                continue
            logger.debug("cf: %s", line.strip())
            m = pat.search(line)
            if m:
                return m.group(0)
        return None

    def best_url(self) -> str:
        return self.public_url or self.local_url

    async def run_until_login(self, timeout: float = 900) -> Any:
        await self.start_server()
        public = None
        try:
            public = await self.start_tunnel()
        except Exception:
            logger.exception("tunnel")

        print("\n" + "=" * 50)
        print("  Hikkari WebUI")
        print("=" * 50)
        print(f"  Local:  {self.local_url}")
        if public:
            print(f"  Public: {public}")
        else:
            print("  Public: open Local URL on this device")
        print("  Phone → code → 2FA in browser")
        print("=" * 50 + "\n")

        try:
            await asyncio.wait_for(self.done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            await self.stop()
            return None
        if not self.success or self.client is None:
            await self.stop()
            return None
        await self.stop()
        return self.client
