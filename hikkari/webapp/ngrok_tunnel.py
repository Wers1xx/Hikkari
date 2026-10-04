# ©️ Wers1xx, 2025-2026
# Minimal ngrok tunnel helper for WebApp / WebUI

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def ensure_ngrok() -> Optional[str]:
    from shutil import which
    found = which("ngrok")
    if found:
        return found
    try:
        from .. import main as _main
        bin_dir = Path(_main.BASE_PATH) / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        target = bin_dir / "ngrok"
        if target.is_file() and os.access(target, os.X_OK) and target.stat().st_size > 500_000:
            return str(target)
        import platform, zipfile, io, stat as stmod
        machine = platform.machine().lower()
        arch = "arm64" if machine in ("aarch64", "arm64") else ("arm" if machine.startswith("arm") else "amd64")
        url = f"https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-{arch}.zip"
        data = urllib.request.urlopen(url, timeout=120).read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith("ngrok") or name == "ngrok":
                    target.write_bytes(zf.read(name))
                    break
            else:
                target.write_bytes(zf.read(zf.namelist()[0]))
        target.chmod(target.stat().st_mode | stmod.S_IEXEC | stmod.S_IXGRP | stmod.S_IXOTH)
        return str(target)
    except Exception:
        logger.exception("ngrok download failed")
        return None


def apply_authtoken(binary: str, token: str) -> None:
    with contextlib.suppress(Exception):
        subprocess.run(
            [binary, "config", "add-authtoken", token],
            capture_output=True,
            timeout=15,
            check=False,
        )


async def start_ngrok(port: int, token: str, retries: int = 3) -> tuple[Optional[str], Optional[subprocess.Popen]]:
    """Return (public_https_url, process)."""
    token = (token or "").strip()
    if not token:
        return None, None
    binary = ensure_ngrok()
    if not binary:
        return None, None
    apply_authtoken(binary, token)

    for attempt in range(1, retries + 1):
        with contextlib.suppress(Exception):
            subprocess.run(["pkill", "-f", f"ngrok http {port}"], capture_output=True)
        try:
            proc = subprocess.Popen(
                [binary, "http", str(port), "--log=stdout", "--log-format=logfmt"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception:
            logger.exception("ngrok start")
            continue

        url = await _wait_api(timeout=30)
        if not url:
            url = await _wait_log(proc, timeout=20)
        if url:
            logger.info("ngrok up: %s", url)
            return url.rstrip("/"), proc
        with contextlib.suppress(Exception):
            proc.terminate()
        await asyncio.sleep(1.2)
    return None, None


async def _wait_api(timeout: float = 30) -> Optional[str]:
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
        except Exception:
            pass
        await asyncio.sleep(0.4)
    return None


async def _wait_log(proc: subprocess.Popen, timeout: float = 20) -> Optional[str]:
    if not proc or not proc.stdout:
        return None
    pat = re.compile(r"https://[a-z0-9-]+\.ngrok(?:-free)?\.(?:app|io|dev)", re.I)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout

    def readline():
        return proc.stdout.readline()

    while loop.time() < deadline:
        if proc.poll() is not None:
            return None
        line = await loop.run_in_executor(None, readline)
        if not line:
            await asyncio.sleep(0.1)
            continue
        m = pat.search(line)
        if m:
            return m.group(0).rstrip("/")
    return None
