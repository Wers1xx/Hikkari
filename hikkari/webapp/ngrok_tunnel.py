# ©️ Wers1xx, 2025-2026
# Reliable ngrok v3 helper — log file based (works in Docker)

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
import time
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"https://[a-z0-9][a-z0-9\-]*\.ngrok(?:-free)?\.(?:app|io|dev)",
    re.I,
)


def ensure_ngrok() -> Optional[str]:
    found = shutil.which("ngrok")
    if found and os.access(found, os.X_OK):
        return found
    try:
        from .. import main as _main
        base = Path(getattr(_main, "BASE_PATH", Path.cwd()))
    except Exception:
        base = Path.cwd()
    target = base / "bin" / "ngrok"
    target.parent.mkdir(parents=True, exist_ok=True)
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

        logger.info("Downloading ngrok linux-%s …", arch)
        data = urllib.request.urlopen(url, timeout=180).read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            member = next(
                (n for n in zf.namelist() if n.rstrip("/").endswith("ngrok")),
                zf.namelist()[0],
            )
            target.write_bytes(zf.read(member))
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(target)
    except Exception:
        logger.exception("ngrok download failed")
        return None


def _prepare_token(token: str) -> Path:
    token = token.strip().strip('"').strip("'")
    cfg_dir = Path.home() / ".config" / "ngrok"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "ngrok.yml"
    # Both v2-style and agent block for compatibility
    cfg.write_text(
        f'version: "2"\nauthtoken: {token}\n',
        encoding="utf-8",
    )
    os.environ["NGROK_AUTHTOKEN"] = token
    os.environ.pop("NGROK_CONFIG", None)
    return cfg


def _read_tail(path: Path, n: int = 40) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return " | ".join(lines[-n:])
    except Exception:
        return ""


def _find_url_in_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = _URL_RE.search(text)
    if m:
        return m.group(0)
    m2 = re.search(r'"url"\s*:\s*"(https://[^"]+ngrok[^"]+)"', text, re.I)
    if m2:
        return m2.group(1)
    m3 = re.search(r"url=(https://\S*ngrok\S*)", text, re.I)
    if m3:
        return m3.group(1).strip().rstrip('",')
    return None


async def _api_url(web_port: int = 4040) -> Optional[str]:
    loop = asyncio.get_event_loop()

    def fetch():
        req = urllib.request.Request(
            f"http://127.0.0.1:{web_port}/api/tunnels",
            headers={"User-Agent": "hikkari"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode())

    try:
        data = await loop.run_in_executor(None, fetch)
    except Exception:
        return None
    for tun in data.get("tunnels") or []:
        pub = (tun.get("public_url") or "").rstrip("/")
        if pub.startswith("https://"):
            return pub
        if pub.startswith("http://") and "ngrok" in pub:
            return pub.replace("http://", "https://", 1)
    return None


async def start_ngrok(
    port: int,
    token: str,
    retries: int = 3,
) -> tuple[Optional[str], Optional[subprocess.Popen], str]:
    token = (token or "").strip().strip('"').strip("'")
    if not token:
        return None, None, "empty authtoken"

    binary = ensure_ngrok()
    if not binary:
        return None, None, "ngrok binary missing"

    cfg = _prepare_token(token)

    # Diagnose once
    diag = []
    with contextlib.suppress(Exception):
        ver = subprocess.run(
            [binary, "version"], capture_output=True, text=True, timeout=15
        )
        diag.append(f"ver={(ver.stdout or ver.stderr or '').strip()[:80]}")
    with contextlib.suppress(Exception):
        # register token via CLI (ignore result)
        subprocess.run(
            [binary, "config", "add-authtoken", token],
            capture_output=True,
            text=True,
            timeout=25,
        )

    last_err = "unknown"
    log_dir = Path(tempfile.gettempdir()) / "hikkari_ngrok"
    log_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries + 1):
        log_file = log_dir / f"ngrok_{port}_{attempt}.log"
        with contextlib.suppress(Exception):
            if log_file.is_file():
                log_file.unlink()

        # free inspect port if previous zombie held it — do NOT pkill all ngrok mid-run
        env = os.environ.copy()
        env["NGROK_AUTHTOKEN"] = token

        # Explicit --config so Docker/home paths always match
        # Log to file (stdout often empty when daemonized / buffered)
        cmd = [
            binary,
            "http",
            f"127.0.0.1:{int(port)}",
            "--log",
            str(log_file),
            "--log-format",
            "logfmt",
            "--log-level",
            "info",
            f"--config={cfg}",
        ]
        logger.info("ngrok try %s: %s", attempt, " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                start_new_session=True,
            )
        except Exception as e:
            last_err = f"popen: {e}"
            continue

        url = None
        deadline = time.time() + 40
        while time.time() < deadline:
            # died?
            if proc.poll() is not None:
                tail = _read_tail(log_file)
                out = ""
                with contextlib.suppress(Exception):
                    out = (proc.stdout.read() if proc.stdout else "") or ""
                last_err = (
                    f"exit={proc.returncode} log={tail or out or '(empty)'} "
                    f"{' '.join(diag)}"
                )
                logger.error("ngrok attempt %s failed: %s", attempt, last_err)
                break

            # log file
            if log_file.is_file():
                url = _find_url_in_text(log_file.read_text(encoding="utf-8", errors="ignore"))
                if url:
                    break

            # local API
            url = await _api_url(4040)
            if url:
                break

            await asyncio.sleep(0.35)
        else:
            # timeout still running
            url = await _api_url(4040) or _find_url_in_text(_read_tail(log_file, 80))
            if not url:
                with contextlib.suppress(Exception):
                    proc.terminate()
                    proc.wait(timeout=3)
                last_err = f"timeout log={_read_tail(log_file)} {' '.join(diag)}"
                logger.error("ngrok attempt %s timeout: %s", attempt, last_err)
                continue

        if url:
            logger.info("ngrok URL: %s", url)
            return url.rstrip("/"), proc, ""

        await asyncio.sleep(0.8)

    return None, None, last_err
