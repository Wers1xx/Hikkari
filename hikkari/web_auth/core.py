# ©️ Wers1xx, 2025-2026
# Hikkari WebUI login — local server + cloudflared (public URL required on phone)

from __future__ import annotations

import asyncio
import contextlib
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



def _arch_tag() -> str:
    import platform
    machine = platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        return "arm64"
    if machine in ("armv7l", "armv7", "arm"):
        return "arm"
    return "amd64"


def _bin_dir() -> Path:
    from .. import main as _main
    d = Path(_main.BASE_PATH) / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_ngrok() -> Optional[str]:
    """Install ngrok binary (no account needed for basic quick tunnels on older builds;
    modern ngrok may need token — we still try free agent)."""
    from shutil import which

    found = which("ngrok")
    if found:
        return found
    try:
        target = _bin_dir() / "ngrok"
        if target.is_file() and os.access(target, os.X_OK) and target.stat().st_size > 500_000:
            return str(target)
        arch = _arch_tag()
        # Official ngrok zip for linux
        url = f"https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-{arch}.zip"
        logger.info("Downloading ngrok (%s)…", arch)
        import zipfile
        import io
        data = urllib.request.urlopen(url, timeout=120).read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith("ngrok") or name == "ngrok":
                    target.write_bytes(zf.read(name))
                    break
            else:
                # first file
                target.write_bytes(zf.read(zf.namelist()[0]))
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(target)
    except Exception:
        logger.exception("ngrok download failed")
        return None


def _ngrok_authtoken(override: str | None = None) -> Optional[str]:
    """Token priority: override → env → config.json."""
    if override and str(override).strip():
        return str(override).strip()
    tok = os.environ.get("NGROK_AUTHTOKEN") or os.environ.get("NGROK_TOKEN")
    if tok:
        return tok.strip()
    try:
        from .. import main as _main
        tok = _main.get_config_key("ngrok_token") or _main.get_config_key("ngrok_authtoken")
        if tok:
            return str(tok).strip()
    except Exception:
        pass
    return None


def _is_private_ip(ip: str) -> bool:
    ip = (ip or "").strip()
    if not ip or ip.startswith("127.") or ip == "::1":
        return True
    if ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("169.254."):
        return True
    if ip.startswith("172."):
        try:
            second = int(ip.split(".")[1])
            if 16 <= second <= 31:
                return True
        except Exception:
            pass
    return False


def _detect_public_ip() -> Optional[str]:
    """Best-effort public IPv4 for VPS links."""
    import socket
    # 1) hostname -I style: first non-private from interfaces
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True, timeout=3)
        for part in out.split():
            if not _is_private_ip(part) and ":" not in part:
                return part.strip()
    except Exception:
        pass
    # 2) external services
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                ip = resp.read().decode().strip()
                if ip and not _is_private_ip(ip) and ":" not in ip:
                    return ip
        except Exception:
            continue
    # 3) UDP trick (may still be private behind NAT)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not _is_private_ip(ip):
            return ip
    except Exception:
        pass
    return None


def _ensure_cloudflared() -> Optional[str]:
    from shutil import which
    found = which("cloudflared")
    if found:
        return found
    try:
        target = _bin_dir() / "cloudflared"
        if target.is_file() and os.access(target, os.X_OK) and target.stat().st_size > 1_000_000:
            return str(target)
        arch = _arch_tag()
        asset = {
            "arm64": "cloudflared-linux-arm64",
            "arm": "cloudflared-linux-arm",
            "amd64": "cloudflared-linux-amd64",
        }.get(arch, "cloudflared-linux-amd64")
        url = (
            "https://github.com/cloudflare/cloudflared/releases/latest/download/"
            + asset
        )
        logger.info("Downloading cloudflared (%s)…", asset)
        urllib.request.urlretrieve(url, str(target))
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(target)
    except Exception:
        logger.exception("cloudflared download failed")
        return None



class WebAuth:
    """Browser login: optional API → phone → code → 2FA."""

    def __init__(
        self,
        api_id: int | None = None,
        api_hash: str | None = None,
        *,
        proxy: Any = None,
        connection: Any = None,
        device_model: str = "Hikkari",
        app_version: str = "1.0",
        need_api: bool = False,
    ):
        self.api_id = int(api_id) if api_id else None
        self.api_hash = str(api_hash) if api_hash else None
        self.need_api = need_api or not (self.api_id and self.api_hash)
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
        self.ngrok_token: Optional[str] = None
        self.weburl_mode: str = "auto"  # auto | tunnel | ip
        self.public_host: Optional[str] = None  # manual IP/domain
        self.public_port: int = 0  # 0 = same as local port
        # api | phone | code | 2fa | done
        self.stage = "api" if self.need_api else "phone"

    def _base_from_request(self, request: web.Request) -> str:
        """Keep user on the same host they opened (cloudflare or local)."""
        host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
        if not host:
            host = f"127.0.0.1:{self.port}"
        proto = request.headers.get("X-Forwarded-Proto")
        if not proto:
            if "trycloudflare.com" in host or "cfargotunnel.com" in host:
                proto = "https"
            else:
                proto = "http"
        return f"{proto}://{host}"

    def _redirect(self, request: web.Request, path: str = "/") -> None:
        base = self._base_from_request(request)
        path = path if path.startswith("/") else f"/{path}"
        sep = "&" if "?" in path else "?"
        url = f"{base}{path}{sep}token={self.token}"
        raise web.HTTPFound(url)

    async def _ensure_client(self):
        if self.client is not None:
            return self.client
        if not self.api_id or not self.api_hash:
            raise RuntimeError("API ID/HASH not set")
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
        return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="theme-color" content="#000"/>
<title>Hikkari Login</title>
<style>
:root {{ --bg:#000; --card:rgba(16,16,22,.94); --line:rgba(255,255,255,.09);
  --text:#f4f4f7; --muted:#8a8a9a; --err:#fb7185; --ok:#6ee7b7; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; min-height:100%; background:var(--bg); color:var(--text);
  font-family:system-ui,-apple-system,sans-serif; -webkit-font-smoothing:antialiased; }}
.bg {{ position:fixed; inset:0; pointer-events:none;
  background:radial-gradient(ellipse 80% 50% at 50% -5%,rgba(55,55,80,.5),transparent 55%); }}
.wrap {{ position:relative; z-index:1; min-height:100vh; display:grid;
  place-items:center; padding:24px; }}
.card {{ width:min(400px,100%); background:var(--card); border:1px solid var(--line);
  border-radius:28px; padding:36px 26px; text-align:center;
  box-shadow:0 28px 90px rgba(0,0,0,.55);
  animation:in .45s cubic-bezier(.22,1,.36,1); }}
@keyframes in {{ from {{ opacity:0; transform:translateY(14px) scale(.98); }}
  to {{ opacity:1; transform:none; }} }}
.logo {{ width:92px; height:92px; border-radius:50%; object-fit:cover; display:block;
  margin:0 auto 14px; box-shadow:0 0 42px rgba(255,255,255,.28);
  animation:pulse 4s ease infinite; }}
@keyframes pulse {{ 0%,100% {{ filter:drop-shadow(0 0 12px rgba(255,255,255,.2)); }}
  50% {{ filter:drop-shadow(0 0 28px rgba(255,255,255,.4)); }} }}
h1 {{ margin:6px 0 6px; font-size:1.45rem; font-weight:700; letter-spacing:-.02em; }}
.sub {{ color:var(--muted); font-size:14px; margin:0 0 18px; line-height:1.45; }}
label {{ display:block; text-align:left; font-size:11px; font-weight:600;
  letter-spacing:.07em; text-transform:uppercase; color:var(--muted); margin:0 0 6px; }}
input {{ width:100%; padding:13px 14px; border-radius:14px; border:1px solid var(--line);
  background:#0a0a0e; color:#fff; font-size:15px; margin:0 0 12px; outline:none;
  transition:border-color .2s, box-shadow .2s; }}
input:focus {{ border-color:rgba(255,255,255,.28);
  box-shadow:0 0 0 3px rgba(255,255,255,.06); }}
button {{ width:100%; padding:13px; border:0; border-radius:14px; font-weight:700;
  font-size:15px; cursor:pointer; color:#0a0a0c;
  background:linear-gradient(180deg,#f7f7f9,#c9c9d2);
  box-shadow:0 8px 28px rgba(255,255,255,.12);
  transition:transform .15s, box-shadow .2s; }}
button:active {{ transform:scale(.98); }}
button:disabled {{ opacity:.6; }}
.err {{ color:var(--err); font-size:13px; min-height:1.2em; margin:8px 0 0;
  animation:in .3s ease; }}
.ok {{ color:var(--ok); }}
.steps {{ display:flex; gap:6px; justify-content:center; margin:0 0 18px; }}
.steps span {{ width:8px; height:8px; border-radius:50%; background:rgba(255,255,255,.15); }}
.steps span.on {{ background:#fff; box-shadow:0 0 10px rgba(255,255,255,.45); }}
.foot {{ margin-top:16px; font-size:11px; color:#555; }}
.hint {{ font-size:12px; color:#6a6a78; margin:-6px 0 12px; text-align:left; }}
</style>
<script>
document.addEventListener('submit',function(e){{
  var b=e.target.querySelector('button[type=submit]');
  if(b){{ b.disabled=true; b.textContent='…'; }}
}});
</script>
</head><body>
<div class="bg"></div>
<div class="wrap"><div class="card">
<img class="logo" src="/static/logo-star.jpg" alt="Hikkari"/>
{body}
<div class="foot">Hikkari · WebUI</div>
</div></div>
</body></html>"""

    def _steps(self) -> str:
        order = ["api", "phone", "code", "2fa"] if self.need_api else ["phone", "code", "2fa"]
        # map done to last
        cur = self.stage if self.stage != "done" else order[-1]
        dots = []
        for s in order:
            dots.append(f'<span class="{"on" if s == cur else ""}"></span>')
        return '<div class="steps">' + "".join(dots) + "</div>"

    def _tok_ok(self, request: web.Request) -> bool:
        tok = request.query.get("token") or ""
        return bool(tok) and secrets.compare_digest(str(tok), self.token)

    async def index(self, request: web.Request) -> web.Response:
        if not self._tok_ok(request):
            return web.Response(
                text=self._html_page("<h1>403</h1><p class='sub'>Неверная ссылка</p>"),
                content_type="text/html",
                status=403,
            )
        err = self.error or ""
        steps = self._steps()
        if self.stage == "done" and self.success:
            body = (
                f"{steps}<h1 class='ok'>Готово</h1>"
                "<p class='sub'>Вход выполнен. Можно закрыть вкладку — "
                "юзербот продолжит сам.</p>"
            )
        elif self.stage == "api":
            body = (
                f"{steps}<h1>API</h1>"
                "<p class='sub'>Данные с <b>my.telegram.org</b></p>"
                f"<form method='post' action='/api/api?token={self.token}'>"
                "<label>API ID</label>"
                "<input name='api_id' inputmode='numeric' placeholder='12345678' required autofocus/>"
                "<label>API Hash</label>"
                "<input name='api_hash' placeholder='32 символа' required minlength='32' maxlength='32'/>"
                "<p class='hint'>App → API development tools</p>"
                "<button type='submit'>Далее</button></form>"
                f"<p class='err'>{err}</p>"
            )
        elif self.stage == "2fa":
            body = (
                f"{steps}<h1>2FA</h1>"
                "<p class='sub'>Пароль двухфакторной защиты</p>"
                f"<form method='post' action='/api/2fa?token={self.token}'>"
                "<label>Пароль</label>"
                "<input name='password' type='password' placeholder='••••••' required autofocus/>"
                "<button type='submit'>Войти</button></form>"
                f"<p class='err'>{err}</p>"
            )
        elif self.stage == "code":
            body = (
                f"{steps}<h1>Код</h1>"
                f"<p class='sub'>Отправлен на <b>{self.phone}</b></p>"
                f"<form method='post' action='/api/code?token={self.token}'>"
                "<label>Код из Telegram</label>"
                "<input name='code' inputmode='numeric' placeholder='12345' required autofocus/>"
                "<button type='submit'>Далее</button></form>"
                f"<p class='err'>{err}</p>"
            )
        else:
            body = (
                f"{steps}<h1>Hikkari</h1>"
                "<p class='sub'>Номер телефона аккаунта</p>"
                f"<form method='post' action='/api/phone?token={self.token}'>"
                "<label>Телефон</label>"
                "<input name='phone' placeholder='+79001234567' required autofocus/>"
                "<button type='submit'>Получить код</button></form>"
                f"<p class='err'>{err}</p>"
            )
        return web.Response(text=self._html_page(body), content_type="text/html")

    async def static(self, request: web.Request) -> web.Response:
        name = request.match_info["path"]
        path = (STATIC / name).resolve()
        if not str(path).startswith(str(STATIC.resolve())) or not path.is_file():
            return web.Response(status=404)
        return web.FileResponse(path)

    async def api_api(self, request: web.Request) -> web.Response:
        if not self._tok_ok(request):
            return web.Response(status=403, text="forbidden")
        data = await request.post()
        self.error = None
        api_id = str(data.get("api_id", "")).strip()
        api_hash = str(data.get("api_hash", "")).strip()
        if not api_id.isdigit():
            self.error = "API ID — только цифры"
            return self._redirect(request)
        if len(api_hash) != 32 or any(c not in "0123456789abcdefABCDEF" for c in api_hash):
            self.error = "API Hash — 32 hex-символа"
            return self._redirect(request)
        self.api_id = int(api_id)
        self.api_hash = api_hash
        try:
            from .. import main as _main
            _main.save_config_key("api_id", self.api_id)
            _main.save_config_key("api_hash", self.api_hash)
        except Exception:
            logger.exception("save api config")
        self.stage = "phone"
        self._redirect(request)

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
            self.error = str(e)[:180]
        self._redirect(request)

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
            self.error = "Код истёк — запроси снова"
            self.stage = "phone"
        except FloodWaitError as e:
            self.error = f"FloodWait: {e.seconds}с"
        except Exception as e:
            logger.exception("code")
            self.error = str(e)[:180]
        self._redirect(request)

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
            self.error = str(e)[:180]
        self._redirect(request)

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self.index)
        app.router.add_get("/static/{path:.*}", self.static)
        app.router.add_post("/api/api", self.api_api)
        app.router.add_post("/api/phone", self.api_phone)
        app.router.add_post("/api/code", self.api_code)
        app.router.add_post("/api/2fa", self.api_2fa)
        return app

    async def start_server(self):
        self._runner = web.AppRunner(self._build_app(), access_log=None)
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


    async def start_tunnel(self, retries: int = 3) -> Optional[str]:
        """Shareable public link (no user API keys).

        Priority:
        1) Free cloudflared → https://*.trycloudflare.com (works through firewall)
        2) Manual weburl_public_host → http://host:port (user opened the port)
        3) Auto public IP only as last resort (often blocked by firewall)
        """
        # 1) Cloudflare quick tunnel — works for UserLand and VPS without open ports
        cf = await self._tunnel_cloudflared(retries=max(retries, 3))
        if cf:
            return cf

        logger.warning("cloudflared unavailable — falling back to IP link")

        # 2) Explicit host from config
        if (self.public_host or "").strip():
            url = self._url_from_ip(strict_public=False)
            if url:
                return url

        # 3) Detected public IP (may not be reachable if firewall closed)
        return self._url_from_ip(strict_public=True)

    def _url_from_ip(self, strict_public: bool = False) -> Optional[str]:
        """http://HOST:PORT/?token= for VPS. No ngrok key needed."""
        host = (self.public_host or "").strip()
        if not host:
            host = _detect_public_ip() or ""
        if not host:
            return None
        if strict_public and _is_private_ip(host):
            return None
        port = int(self.public_port) if self.public_port else self.port
        # Always bind was 0.0.0.0 — reachable on VPS
        self.public_url = f"http://{host}:{port}/?token={self.token}"
        logger.info("WebUI public IP URL: %s", self.public_url)
        return self.public_url

    async def _tunnel_ngrok(self, retries: int = 3) -> Optional[str]:
        binary = _ensure_ngrok()
        if not binary:
            return None

        token = _ngrok_authtoken(getattr(self, "ngrok_token", None))
        if token:
            try:
                subprocess.run(
                    [binary, "config", "add-authtoken", token],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
            except Exception:
                logger.debug("ngrok authtoken set failed", exc_info=True)

        for attempt in range(1, retries + 1):
            with contextlib.suppress(Exception):
                if self._tunnel_proc and self._tunnel_proc.poll() is None:
                    self._tunnel_proc.terminate()
            self._tunnel_proc = None

            # Kill leftover ngrok if any
            with contextlib.suppress(Exception):
                subprocess.run(["pkill", "-f", "ngrok http"], capture_output=True)

            try:
                self._tunnel_proc = subprocess.Popen(
                    [
                        binary,
                        "http",
                        str(self.port),
                        "--log=stdout",
                        "--log-format=logfmt",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except Exception:
                logger.exception("ngrok start failed (try %s)", attempt)
                await asyncio.sleep(1)
                continue

            # Prefer local ngrok API for the public URL
            url = await self._wait_ngrok_api(timeout=25)
            if not url:
                url = await self._wait_ngrok_log(timeout=20)
            if url:
                self.public_url = f"{url.rstrip('/')}/?token={self.token}"
                logger.info("ngrok public WebUI: %s", self.public_url)
                return self.public_url

            logger.warning("ngrok no URL (try %s/%s)", attempt, retries)
            with contextlib.suppress(Exception):
                if self._tunnel_proc:
                    self._tunnel_proc.terminate()
            self._tunnel_proc = None
            await asyncio.sleep(1.5)
        return None

    async def _wait_ngrok_api(self, timeout: float = 25) -> Optional[str]:
        """Poll http://127.0.0.1:4040/api/tunnels for public_url."""
        import json
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                def fetch():
                    req = urllib.request.Request(
                        "http://127.0.0.1:4040/api/tunnels",
                        headers={"User-Agent": "hikkari"},
                    )
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        return json.loads(resp.read().decode())

                data = await loop.run_in_executor(None, fetch)
                for tun in data.get("tunnels") or []:
                    pub = tun.get("public_url") or ""
                    if pub.startswith("https://"):
                        return pub.rstrip("/")
                    if pub.startswith("http://") and "ngrok" in pub:
                        # prefer https if only http
                        https = pub.replace("http://", "https://", 1)
                        return https.rstrip("/")
            except Exception:
                pass
            await asyncio.sleep(0.4)
        return None

    async def _wait_ngrok_log(self, timeout: float = 20) -> Optional[str]:
        if not self._tunnel_proc or not self._tunnel_proc.stdout:
            return None
        pat = re.compile(
            r"https://[a-z0-9-]+\.ngrok(?:-free)?\.(?:app|io|dev)[^\s]*",
            re.I,
        )
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
            logger.debug("ngrok: %s", line.strip())
            m = pat.search(line)
            if m:
                return m.group(0).rstrip("/")
        return None

    async def _tunnel_cloudflared(self, retries: int = 2) -> Optional[str]:
        binary = _ensure_cloudflared()
        if not binary:
            return None
        for attempt in range(1, retries + 1):
            with contextlib.suppress(Exception):
                if self._tunnel_proc and self._tunnel_proc.poll() is None:
                    self._tunnel_proc.terminate()
            self._tunnel_proc = None
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
                logger.exception("cloudflared start failed")
                continue
            url = await self._wait_cf_url(70)
            if url:
                self.public_url = f"{url.rstrip('/')}/?token={self.token}"
                return self.public_url
            with contextlib.suppress(Exception):
                if self._tunnel_proc:
                    self._tunnel_proc.terminate()
            self._tunnel_proc = None
            await asyncio.sleep(1)
        return None

    async def _wait_cf_url(self, timeout: float = 45) -> Optional[str]:
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
        if public:
            print(f"  >>> OPEN THIS: {public}")
            print("  (с телефона открывай ТОЛЬКО Public, не 127.0.0.1)")
        else:
            print(f"  Local only: {self.local_url}")
            print("  127.0.0.1 с телефона НЕ работает — нужен cloudflared")
        if self.need_api:
            print("  Steps: API ID/HASH → phone → code → 2FA")
        else:
            print("  Steps: phone → code → 2FA")
        print("=" * 50 + "\n")

        try:
            await asyncio.wait_for(self.done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            await self.stop()
            return None
        if not self.success or self.client is None:
            await self.stop()
            return None
        # keep tunnel until client handed over — stop after
        await self.stop()
        return self.client
