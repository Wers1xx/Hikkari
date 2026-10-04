# ©️ Wers1xx, 2025-2026
# Simple reliable ngrok helper (v3 agent)

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import platform
import queue
import re
import shutil
import stat
import subprocess
import threading
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
        import io, zipfile
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
    token = token.strip()
    # Official path
    cfg_dir = Path.home() / ".config" / "ngrok"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "ngrok.yml"
    # ngrok agent v3 format
    cfg.write_text(
        f'version: "2"\nauthtoken: {token}\n',
        encoding="utf-8",
    )
    os.environ["NGROK_AUTHTOKEN"] = token
    # Do NOT force NGROK_CONFIG to project path — use default home config
    os.environ.pop("NGROK_CONFIG", None)
    return cfg


def _kill_old_ngrok(binary: str) -> None:
    with contextlib.suppress(Exception):
        subprocess.run(["pkill", "-f", "ngrok http"], capture_output=True, timeout=5)
    with contextlib.suppress(Exception):
        subprocess.run(["killall", "ngrok"], capture_output=True, timeout=5)
    time.sleep(0.6)


def _reader_thread(proc: subprocess.Popen, q: queue.Queue) -> None:
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            q.put(line)
    except Exception:
        pass
    finally:
        q.put(None)


async def start_ngrok(
    port: int,
    token: str,
    retries: int = 3,
) -> tuple[Optional[str], Optional[subprocess.Popen], str]:
    token = (token or "").strip()
    if not token:
        return None, None, "empty authtoken"

    binary = ensure_ngrok()
    if not binary:
        return None, None, "ngrok binary not found / download failed"

    _prepare_token(token)

    # Also register via CLI (best-effort)
    with contextlib.suppress(Exception):
        r = subprocess.run(
            [binary, "config", "add-authtoken", token],
            capture_output=True,
            text=True,
            timeout=25,
        )
        logger.info("add-authtoken rc=%s out=%s err=%s", r.returncode, (r.stdout or "")[:120], (r.stderr or "")[:120])

    # version for logs
    with contextlib.suppress(Exception):
        ver = subprocess.run([binary, "version"], capture_output=True, text=True, timeout=10)
        logger.info("ngrok version: %s", (ver.stdout or ver.stderr or "").strip())

    last_err = "unknown"
    for attempt in range(1, retries + 1):
        _kill_old_ngrok(binary)

        # Point at localhost explicitly — works on UserLand / Docker
        target = f"127.0.0.1:{int(port)}"
        env = os.environ.copy()
        env["NGROK_AUTHTOKEN"] = token

        # Default web interface 4040 — no custom --web-addr
        cmd = [binary, "http", target, "--log=stdout", "--log-format=logfmt"]
        logger.info("ngrok try %s: %s", attempt, " ".join(cmd))

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
            last_err = f"popen failed: {e}"
            continue

        q: queue.Queue = queue.Queue()
        threading.Thread(target=_reader_thread, args=(proc, q), daemon=True).start()

        url = await _wait(proc, q, timeout=45)
        if url:
            logger.info("ngrok public URL: %s", url)
            return url.rstrip("/"), proc, ""

        # Dump what we saw
        lines = []
        while True:
            try:
                line = q.get_nowait()
            except queue.Empty:
                break
            if line is None:
                break
            lines.append(line.strip())

        rc = proc.poll()
        with contextlib.suppress(Exception):
            proc.terminate()
            proc.wait(timeout=3)

        tail = " | ".join(lines[-20:]) if lines else "(no output)"
        last_err = f"exit={rc} log={tail[:500]}"
        logger.error("ngrok attempt %s failed: %s", attempt, last_err)
        await asyncio.sleep(1.2)

    return None, None, last_err


async def _wait(proc: subprocess.Popen, q: queue.Queue, timeout: float = 45) -> Optional[str]:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    collected = []

    while loop.time() < deadline:
        # stdout lines
        try:
            while True:
                line = q.get_nowait()
                if line is None:
                    break
                line = line.strip()
                collected.append(line)
                logger.debug("ngrok: %s", line)
                m = _URL_RE.search(line)
                if m:
                    return m.group(0)
                # url=https://... in logfmt
                m2 = re.search(r"url=(https://[^\s]+)", line)
                if m2 and "ngrok" in m2.group(1):
                    return m2.group(1).rstrip("\"'")
        except queue.Empty:
            pass

        if proc.poll() is not None:
            # drain queue
            await asyncio.sleep(0.2)
            try:
                while True:
                    line = q.get_nowait()
                    if line is None:
                        break
                    collected.append(line.strip())
                    m = _URL_RE.search(line)
                    if m:
                        return m.group(0)
            except queue.Empty:
                pass
            logger.warning("ngrok died. log: %s", " | ".join(collected[-15:]))
            return None

        # API on default 4040
        try:
            def fetch():
                req = urllib.request.Request(
                    "http://127.0.0.1:4040/api/tunnels",
                    headers={"User-Agent": "hikkari"},
                )
                with urllib.request.urlopen(req, timeout=1.2) as resp:
                    return json.loads(resp.read().decode())
            data = await loop.run_in_executor(None, fetch)
            for tun in data.get("tunnels") or []:
                pub = (tun.get("public_url") or "").rstrip("/")
                if pub.startswith("https://"):
                    return pub
                if pub.startswith("http://") and "ngrok" in pub:
                    return pub.replace("http://", "https://", 1)
        except Exception:
            pass

        await asyncio.sleep(0.3)

    logger.warning("ngrok timeout. log: %s", " | ".join(collected[-20:]))
    return None
