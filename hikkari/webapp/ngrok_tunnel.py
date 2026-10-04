# ©️ Wers1xx, 2025-2026
# ngrok helper — file log + stderr, quiet retries

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

        logger.debug("Downloading ngrok linux-%s …", arch)
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


def _write_config(token: str) -> Path:
    token = token.strip().strip('"').strip("'")
    cfg_dir = Path.home() / ".config" / "ngrok"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "ngrok.yml"
    # ngrok agent 3.x prefers version 3; keep authtoken at top level too
    cfg.write_text(
        "version: \"3\"\n"
        "agent:\n"
        f"  authtoken: {token}\n",
        encoding="utf-8",
    )
    os.environ["NGROK_AUTHTOKEN"] = token
    return cfg


def _find_url(text: str) -> Optional[str]:
    if not text:
        return None
    m = _URL_RE.search(text)
    if m:
        return m.group(0)
    m2 = re.search(r'"public_url"\s*:\s*"(https://[^"]+)"', text)
    if m2 and "ngrok" in m2.group(1):
        return m2.group(1)
    m3 = re.search(r"url=(https://\S*ngrok\S*)", text, re.I)
    if m3:
        return m3.group(1).strip().rstrip('",')
    return None


async def _api_url() -> Optional[str]:
    def fetch():
        req = urllib.request.Request(
            "http://127.0.0.1:4040/api/tunnels",
            headers={"User-Agent": "hikkari"},
        )
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            return json.loads(resp.read().decode())

    try:
        data = await asyncio.get_event_loop().run_in_executor(None, fetch)
    except Exception:
        return None
    for tun in data.get("tunnels") or []:
        pub = (tun.get("public_url") or "").rstrip("/")
        if pub.startswith("https://"):
            return pub
        if pub.startswith("http://") and "ngrok" in pub:
            return pub.replace("http://", "https://", 1)
    return None


def _run_once(binary: str, port: int, token: str, cfg: Path) -> tuple[Optional[str], Optional[subprocess.Popen], str]:
    """Blocking attempt; returns (url, proc, err)."""
    log_dir = Path(tempfile.gettempdir()) / "hikkari_ngrok"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"ngrok_{port}.log"
    err_file = log_dir / f"ngrok_{port}.err"
    with contextlib.suppress(Exception):
        log_file.unlink(missing_ok=True)
        err_file.unlink(missing_ok=True)

    env = os.environ.copy()
    env["NGROK_AUTHTOKEN"] = token

    # Try several argv variants — some agents dislike --config path form
    variants = [
        [
            binary, "http", str(port),
            "--log", str(log_file), "--log-format", "json", "--log-level", "debug",
            f"--config={cfg}",
        ],
        [
            binary, "http", f"127.0.0.1:{port}",
            "--log", str(log_file), "--log-format", "logfmt", "--log-level", "debug",
            "--config", str(cfg),
        ],
        [
            binary, "http", str(port),
            "--log", "stdout", "--log-format", "logfmt", "--log-level", "info",
        ],
    ]

    last = "no variant"
    for cmd in variants:
        try:
            with open(err_file, "w", encoding="utf-8") as ef:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=ef,
                    text=True,
                    env=env,
                    start_new_session=True,
                )
        except Exception as e:
            last = f"popen: {e}"
            continue

        deadline = time.time() + 25
        url = None
        while time.time() < deadline:
            if proc.poll() is not None:
                out = ""
                with contextlib.suppress(Exception):
                    out = (proc.stdout.read() if proc.stdout else "") or ""
                logt = ""
                with contextlib.suppress(Exception):
                    logt = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.is_file() else ""
                errt = ""
                with contextlib.suppress(Exception):
                    errt = err_file.read_text(encoding="utf-8", errors="ignore") if err_file.is_file() else ""
                blob = "\n".join([out, logt, errt])
                # extract useful ERR_ lines
                err_lines = [
                    ln for ln in blob.splitlines()
                    if any(x in ln.lower() for x in ("err", "error", "fail", "invalid", "auth", "limit", "session"))
                ]
                snippet = " | ".join(err_lines[-8:] or blob.splitlines()[-6:] or ["(empty)"])
                last = f"exit={proc.returncode} {snippet[:500]}"
                break

            # poll log + api
            for src in (log_file,):
                if src.is_file():
                    url = _find_url(src.read_text(encoding="utf-8", errors="ignore"))
                    if url:
                        return url, proc, ""
            try:
                # sync api check
                req = urllib.request.Request(
                    "http://127.0.0.1:4040/api/tunnels",
                    headers={"User-Agent": "hikkari"},
                )
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    data = json.loads(resp.read().decode())
                for tun in data.get("tunnels") or []:
                    pub = (tun.get("public_url") or "").rstrip("/")
                    if pub.startswith("https://"):
                        return pub, proc, ""
            except Exception:
                pass
            time.sleep(0.3)
        else:
            # still running — one more API check
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:4040/api/tunnels",
                    headers={"User-Agent": "hikkari"},
                )
                with urllib.request.urlopen(req, timeout=1) as resp:
                    data = json.loads(resp.read().decode())
                for tun in data.get("tunnels") or []:
                    pub = (tun.get("public_url") or "").rstrip("/")
                    if pub.startswith("https://"):
                        return pub, proc, ""
            except Exception:
                pass
            with contextlib.suppress(Exception):
                proc.terminate()
            last = "timeout"
            continue

        # process died — try next variant
        continue

    return None, None, last


async def start_ngrok(
    port: int,
    token: str,
    retries: int = 2,
) -> tuple[Optional[str], Optional[subprocess.Popen], str]:
    token = (token or "").strip().strip('"').strip("'")
    if not token:
        return None, None, "empty authtoken"

    binary = ensure_ngrok()
    if not binary:
        return None, None, "ngrok binary missing"

    cfg = _write_config(token)

    # add-authtoken once (quiet)
    with contextlib.suppress(Exception):
        subprocess.run(
            [binary, "config", "add-authtoken", token],
            capture_output=True,
            text=True,
            timeout=20,
        )

    last_err = "unknown"
    for attempt in range(1, max(1, retries) + 1):
        # run blocking attempt in thread so we don't block loop hard
        url, proc, err = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _run_once(binary, int(port), token, cfg)
        )
        if url:
            logger.debug("ngrok up: %s", url)
            return url.rstrip("/"), proc, ""
        last_err = err
        # only one warning total, not per attempt spam
        if attempt == max(1, retries):
            logger.warning("ngrok failed: %s", last_err)
        else:
            logger.debug("ngrok attempt %s: %s", attempt, last_err)
        await asyncio.sleep(0.5)

    return None, None, last_err
