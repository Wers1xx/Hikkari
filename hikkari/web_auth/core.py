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
            "<meta name='theme-color' content='#000000'/>"
            "<title>Hikkari — Login</title>"
            "<style>"
            ":root{--bg:#050508;--card:rgba(14,14,20,.92);--line:rgba(255,255,255,.08);"
            "--text:#f4f4f7;--muted:#8b8b9a;--accent:#fff}"
            "*{box-sizing:border-box}"
            "html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);"
            "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}"
            ".bg{position:fixed;inset:0;background:"
            "radial-gradient(ellipse 80% 50% at 50% -10%,rgba(60,60,80,.45),transparent 55%),"
            "radial-gradient(ellipse at center,transparent 40%,#000 100%);z-index:0}"
            ".wrap{position:relative;z-index:1;min-height:100vh;display:grid;"
            "place-items:center;padding:24px}"
            ".card{width:min(420px,100%);background:var(--card);"
            "border:1px solid var(--line);border-radius:28px;padding:36px 28px;"
            "text-align:center;backdrop-filter:blur(16px);"
            "box-shadow:0 30px 90px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.03) inset}"
            ".logo{width:96px;height:96px;border-radius:50%;object-fit:cover;"
            "box-shadow:0 0 48px rgba(255,255,255,.28);margin:0 auto 14px;display:block}"
            "h1{margin:6px 0 4px;font-size:1.55rem;font-weight:700;letter-spacing:-.02em}"
            ".sub{color:var(--muted);font-size:14px;margin:0 0 20px;line-height:1.45}"
            "label{display:block;text-align:left;font-size:11px;font-weight:600;"
            "letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}"
            "input{width:100%;padding:13px 14px;border-radius:14px;"
            "border:1px solid var(--line);background:#0a0a0e;color:#fff;font-size:15px;"
            "margin:0 0 12px;outline:none}"
            "input:focus{border-color:rgba(255,255,255,.28);"
            "box-shadow:0 0 0 3px rgba(255,255,255,.06)}"
            "button{width:100%;padding:13px;border:0;border-radius:14px;font-weight:700;"
            "font-size:15px;cursor:pointer;color:#0a0a0c;"
            "background:linear-gradient(180deg,#f7f7f9,#c9c9d2);"
            "box-shadow:0 8px 28px rgba(255,255,255,.12)}"
            "button:active{transform:scale(.98)}"
            ".err{color:#fb7185;min-height:1.2em;font-size:13px;margin:10px 0 0}"
            ".ok{color:#6ee7b7}"
            ".foot{margin-top:18px;font-size:11px;color:#5a5a68;letter-spacing:.04em}"
            "</style></head><body><div class='bg'></div><div class='wrap'>"
            "<div class='card'>"
            "<img class='logo' src='/static/logo-star.jpg' alt='Hikkari'/>"
            f"{body}"
            "<div class='foot'>Hikkari Userbot · WebUI</div>"
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
        """Public URL for WebUI — like Hikka: prefer cloudflared, then SSH tunnels.

        Never return admin.localhost.run (login wall).
        """
        # 1) Cloudflare quick tunnel (best free option, no account)
        url = await self._tunnel_cloudflared()
        if url:
            self.public_url = self._with_token(url)
            return self.public_url

        # 2) SSH reverse tunnels (serveo / localhost.run) — filter admin pages
        for host in ("serveo.net", "nokey@localhost.run"):
            url = await self._tunnel_ssh(host)
            if url:
                self.public_url = self._with_token(url)
                return self.public_url

        return None

    def _with_token(self, base: str) -> str:
        base = base.rstrip("/")
        sep = "&" if "?" in base else "?"
        # if already has token leave as is
        if "token=" in base:
            return base
        return f"{base}/?token={self.token}"

    def _is_bad_tunnel_url(self, url: str) -> bool:
        u = (url or "").lower()
        bad = (
            "admin.localhost.run",
            "login.localhost.run",
            "accounts.google",
            "localhost.run/login",
            "localhost.run/admin",
        )
        return any(b in u for b in bad)

    async def _tunnel_cloudflared(self) -> Optional[str]:
        cmds = [
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{self.port}"],
            ["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
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
                logger.info("cloudflared not installed — trying SSH tunnels")
                return None
            except Exception:
                logger.exception("cloudflared start failed")
                continue

            url = await self._wait_tunnel_url(
                timeout=35,
                extra_patterns=(
                    r"https://[a-zA-Z0-9-]+\.trycloudflare\.com",
                    r"https://[a-zA-Z0-9-]+\.cfargotunnel\.com",
                ),
            )
            if url and not self._is_bad_tunnel_url(url):
                logger.info("cloudflared tunnel: %s", url)
                return url.rstrip("/")
            try:
                self._tunnel_proc.terminate()
            except Exception:
                pass
            self._tunnel_proc = None
        return None

    async def _tunnel_ssh(self, host: str) -> Optional[str]:
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "LogLevel=ERROR",
            "-R",
            f"80:127.0.0.1:{self.port}",
            host,
        ]
        try:
            self._tunnel_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            logger.warning("ssh not found")
            return None
        except Exception:
            logger.exception("ssh tunnel failed for %s", host)
            return None

        url = await self._wait_tunnel_url(timeout=25)
        if url and not self._is_bad_tunnel_url(url):
            return url.rstrip("/")
        # localhost.run often prints a good URL then redirects browser to admin —
        # prefer *.lhr.life if present
        if url and self._is_bad_tunnel_url(url):
            logger.warning("Rejected tunnel URL (admin/login wall): %s", url)
        try:
            self._tunnel_proc.terminate()
        except Exception:
            pass
        self._tunnel_proc = None
        return None

    async def _wait_tunnel_url(
        self,
        timeout: float = 25,
        extra_patterns: tuple = (),
    ) -> Optional[str]:
        if not self._tunnel_proc or not self._tunnel_proc.stdout:
            return None
        patterns = [
            re.compile(p)
            for p in extra_patterns
            + (
                r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com",
                r"https://[a-zA-Z0-9.-]+\.lhr\.life",
                r"https://[a-zA-Z0-9.-]+\.serveo\.net",
                r"https://[a-zA-Z0-9.-]+\.localhost\.run",
                r"https?://[a-zA-Z0-9.-]+\.(localhost\.run|serveo\.net|lhr\.life)[^\s]*",
            )
        ]
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        found_candidates = []

        def read_line():
            return self._tunnel_proc.stdout.readline()

        while loop.time() < deadline:
            if self._tunnel_proc.poll() is not None:
                break
            line = await loop.run_in_executor(None, read_line)
            if not line:
                await asyncio.sleep(0.15)
                continue
            logger.debug("tunnel: %s", line.strip())
            for pat in patterns:
                m = pat.search(line)
                if not m:
                    continue
                url = m.group(0).rstrip("./")
                if self._is_bad_tunnel_url(url):
                    continue
                # Prefer non-admin URLs immediately
                if "trycloudflare.com" in url or "lhr.life" in url or "serveo.net" in url:
                    return url
                found_candidates.append(url)
        for url in found_candidates:
            if not self._is_bad_tunnel_url(url):
                return url
        return None

    async def run_until_login(self, timeout: float = 600) -> Any:
        """Start server (+tunnel), wait for login, return connected client or None."""
        await self.start_server()
        public = None
        try:
            public = await self.start_tunnel()
        except Exception:
            logger.exception("tunnel error")

        print("\n" + "=" * 48)
        print("  Hikkari WebUI login")
        print("=" * 48)
        print(f"  Local:  {self.local_url}")
        if public:
            print(f"  Public: {public}")
            print("  Open Public URL in browser on any device.")
        else:
            print("  Tunnel not available.")
            print("  Install cloudflared for public link:")
            print("    https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
            print("  Or open Local URL on this same device.")
        print("  Waiting for login (phone -> code -> 2FA)...")
        print("=" * 48 + "\n")

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
