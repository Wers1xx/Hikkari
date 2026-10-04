# ©️ Wers1xx, 2025-2026
# Robust ngrok v3 tunnel helper

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"https://[a-z0-9][a-z0-9-]*\.ngrok(?:-free)?\.(?:app|io|dev)",
    re.I,
)


def ensure_ngrok() -> Optional[str]:
    found = shutil.which("ngrok")
    if found and os.path.isfile(found) and os.access(found, os.X_OK):
        return found
    try:
        from .. import main as _main
        base = Path(getattr(_main, "BASE_PATH", Path.cwd()))
    except Exception:
        base = Path.cwd()
    bin_dir = base / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "ngrok"
    if target.is_file() and os.access(target, os.X_OK) and target.stat().st_size > 500_000:
        return str(target)

    machine = platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif machine.startswith("arm"):
        arch = "arm"
    else:
        arch = "amd64"
    url = f"https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-{arch}.zip"
    try:
        import io
        import zipfile
        logger.info("Downloading ngrok (%s)…", arch)
        data = urllib.request.urlopen(url, timeout=180).read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            member = next((n for n in names if n.rstrip("/").endswith("ngrok")), names[0])
            target.write_bytes(zf.read(member))
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(target)
    except Exception:
        logger.exception("ngrok download failed")
        return None


def write_authtoken(token: str) -> Optional[Path]:
    """Write ngrok.yml with authtoken — most reliable way."""
    token = (token or "").strip()
    if not token:
        return None
    # Prefer XDG / home
    candidates = []
    home = Path.home()
    candidates.append(home / ".config" / "ngrok" / "ngrok.yml")
    candidates.append(home / ".ngrok2" / "ngrok.yml")
    # Also project-local (ngrok supports NGROK_CONFIG)
    try:
        from .. import main as _main
        candidates.insert(0, Path(getattr(_main, "BASE_PATH", Path.cwd())) / "ngrok.yml")
    except Exception:
        pass

    cfg = candidates[0]
    cfg.parent.mkdir(parents=True, exist_ok=True)
    content = f"version: \"2\"\nauthtoken: {token}\n"
    cfg.write_text(content, encoding="utf-8")
    os.environ["NGROK_AUTHTOKEN"] = token
    os.environ["NGROK_CONFIG"] = str(cfg)
    logger.info("ngrok config written: %s", cfg)
    return cfg


async def start_ngrok(
    port: int,
    token: str,
    retries: int = 3,
) -> tuple[Optional[str], Optional[subprocess.Popen], str]:
    """
    Start ngrok http tunnel.
    Returns (public_url, process, error_detail).
    """
    token = (token or "").strip()
    if not token:
        return None, None, "empty authtoken"

    binary = ensure_ngrok()
    if not binary:
        return None, None, "ngrok binary missing (download failed)"

    cfg = write_authtoken(token)
    # also try official CLI
    with contextlib.suppress(Exception):
        subprocess.run(
            [binary, "config", "add-authtoken", token],
            capture_output=True,
            timeout=20,
            check=False,
            env={**os.environ},
        )

    last_err = "unknown"
    for attempt in range(1, retries + 1):
        # free default inspect port if possible
        with contextlib.suppress(Exception):
            subprocess.run(["pkill", "-f", f"{binary} http"], capture_output=True, timeout=5)

        inspect_port = 4040 + (attempt - 1)  # 4040, 4041, …
        env = {**os.environ, "NGROK_AUTHTOKEN": token}
        if cfg:
            env["NGROK_CONFIG"] = str(cfg)

        cmd = [
            binary,
            "http",
            str(int(port)),
            "--log=stdout",
            "--log-format=term",
            f"--web-addr=127.0.0.1:{inspect_port}",
        ]
        logger.info("ngrok cmd (try %s): %s", attempt, " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except Exception as e:
            last_err = f"popen: {e}"
            continue

        url = await _wait_for_url(proc, inspect_port, timeout=40)
        if url:
            return url.rstrip("/"), proc, ""

        # collect last lines for diagnostics
        dump = []
        try:
            if proc.poll() is not None and proc.stdout:
                rest = proc.stdout.read() or ""
                dump = [ln.strip() for ln in rest.splitlines() if ln.strip()][-12:]
        except Exception:
            pass
        with contextlib.suppress(Exception):
            proc.terminate()
            proc.wait(timeout=3)
        last_err = " | ".join(dump) if dump else f"no URL (inspect={inspect_port})"
        logger.warning("ngrok attempt %s failed: %s", attempt, last_err)
        await asyncio.sleep(1.0)

    return None, None, last_err


async def _wait_for_url(
    proc: subprocess.Popen,
    inspect_port: int,
    timeout: float = 40,
) -> Optional[str]:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    api = f"http://127.0.0.1:{inspect_port}/api/tunnels"

    def readline_nb():
        if not proc.stdout:
            return ""
        return proc.stdout.readline()

    while loop.time() < deadline:
        if proc.poll() is not None:
            # process exited — read remaining and search URL
            try:
                rest = proc.stdout.read() if proc.stdout else ""
            except Exception:
                rest = ""
            m = _URL_RE.search(rest or "")
            if m:
                return m.group(0)
            logger.warning("ngrok exited early: %s", (rest or "")[-500:])
            return None

        # 1) local API
        try:
            def fetch(api=api):
                req = urllib.request.Request(api, headers={"User-Agent": "hikkari"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    return json.loads(resp.read().decode())
            data = await loop.run_in_executor(None, fetch)
            for tun in data.get("tunnels") or []:
                pub = (tun.get("public_url") or "").rstrip("/")
                if pub.startswith("https://"):
                    return pub
                if pub.startswith("http://") and "ngrok" in pub:
                    # prefer https twin
                    https = pub.replace("http://", "https://", 1)
                    return https
        except Exception:
            pass

        # 2) stdout line
        try:
            line = await loop.run_in_executor(None, readline_nb)
        except Exception:
            line = ""
        if line:
            line = line.strip()
            logger.debug("ngrok: %s", line)
            m = _URL_RE.search(line)
            if m:
                return m.group(0)
            # classic "Forwarding  https://..."
            if "http" in line.lower() and "ngrok" in line.lower():
                m2 = re.search(r"https?://[^\s]+", line)
                if m2:
                    return m2.group(0).rstrip("/")

        await asyncio.sleep(0.25)
    return None
