# ©️ Wers1xx, 2025-2026
# Hikkari proxy helpers — http / https / socks4 / socks5 / mtproxy

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

SUPPORTED = ("http", "https", "socks4", "socks5", "mtproxy", "mtproto")


def _base_dir() -> Path:
    try:
        from . import main as _main
        root = getattr(_main, "BASE_PATH", None) or getattr(_main, "BASE_DIR", None)
        if root:
            return Path(root)
    except Exception:
        pass
    return Path.cwd()


def proxy_file() -> Path:
    return _base_dir() / "proxy.json"


def save_proxy(cfg: dict) -> Path:
    path = proxy_file()
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def clear_proxy() -> bool:
    path = proxy_file()
    if path.is_file():
        path.unlink()
        return True
    return False


def load_proxy_file() -> dict | None:
    path = proxy_file()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("type"):
            return data
    except Exception:
        logger.exception("Failed to read %s", path)
    return None


def parse_proxy_url(url: str) -> dict:
    """
    Parse:
      socks5://user:pass@host:1080
      socks4://host:1080
      http://user:pass@host:8080
      https://host:443
      mtproxy://host:443?secret=...
      host:port:secret  (legacy mtproxy shorthand)
    Returns dict: type, host, port, username?, password?, secret?
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Empty proxy URL")

    # mtproxy shorthand host:port:secret (secret is hex)
    if "://" not in raw and raw.count(":") >= 2:
        parts = raw.split(":")
        if len(parts) >= 3 and parts[1].isdigit():
            host, port, secret = parts[0], int(parts[1]), ":".join(parts[2:])
            return {
                "type": "mtproxy",
                "host": host,
                "port": port,
                "secret": secret,
            }

    if "://" not in raw:
        # host:port → assume socks5
        if ":" in raw:
            host, port_s = raw.rsplit(":", 1)
            if port_s.isdigit():
                return {"type": "socks5", "host": host.strip(), "port": int(port_s)}
        raise ValueError(
            "Use URL like socks5://host:1080 or http://user:pass@host:8080"
        )

    u = urlparse(raw)
    scheme = (u.scheme or "").lower()
    if scheme in ("socks5h",):
        scheme = "socks5"
    if scheme in ("socks4a",):
        scheme = "socks4"
    if scheme in ("mtproto",):
        scheme = "mtproxy"
    if scheme not in SUPPORTED:
        raise ValueError(
            f"Unsupported proxy type '{scheme}'. "
            f"Use: {', '.join(SUPPORTED)}"
        )
    if not u.hostname:
        raise ValueError("Proxy host is missing")
    port = u.port
    if not port:
        port = {"http": 80, "https": 443, "socks4": 1080, "socks5": 1080, "mtproxy": 443}.get(
            scheme, 1080
        )

    cfg: dict[str, Any] = {
        "type": scheme,
        "host": u.hostname,
        "port": int(port),
    }
    if u.username:
        cfg["username"] = unquote(u.username)
    if u.password:
        cfg["password"] = unquote(u.password)

    # secret from query for mtproxy
    if scheme == "mtproxy":
        from urllib.parse import parse_qs
        qs = parse_qs(u.query or "")
        secret = (qs.get("secret") or [None])[0]
        if not secret and u.password:
            secret = u.password
        if not secret:
            raise ValueError("MTProxy requires secret (?secret=... or as password)")
        cfg["secret"] = secret
        cfg.pop("password", None)

    return cfg


def parse_proxy_args(args: str) -> dict:
    """
    Accept either a full URL or:
      <type> <host> <port> [user] [pass]
      <type> <host> <port> <secret>   # mtproxy
    """
    args = (args or "").strip()
    if not args:
        raise ValueError("No proxy specified")

    if "://" in args or (args.count(":") >= 2 and args.split(":")[1].isdigit() and " " not in args):
        return parse_proxy_url(args)

    parts = args.split()
    if len(parts) < 3:
        raise ValueError(
            "Usage: .setproxy socks5://host:port\n"
            "   or: .setproxy socks5 host port [user] [pass]\n"
            "   or: .setproxy mtproxy host port secret"
        )
    ptype = parts[0].lower().lstrip("-")
    if ptype in ("socks5h",):
        ptype = "socks5"
    if ptype in ("mtproto",):
        ptype = "mtproxy"
    if ptype not in SUPPORTED:
        raise ValueError(f"Type must be one of: {', '.join(SUPPORTED)}")
    host = parts[1]
    try:
        port = int(parts[2])
    except ValueError as e:
        raise ValueError("Port must be a number") from e

    cfg: dict[str, Any] = {"type": ptype, "host": host, "port": port}
    if ptype == "mtproxy":
        if len(parts) < 4:
            raise ValueError("MTProxy needs secret: .setproxy mtproxy host port secret")
        cfg["secret"] = parts[3]
    else:
        if len(parts) >= 4:
            cfg["username"] = parts[3]
        if len(parts) >= 5:
            cfg["password"] = parts[4]
    return cfg


def to_telethon_proxy(cfg: dict | None) -> tuple[Any, Any]:
    """
    Returns (proxy, connection_class_name_hint)
    proxy is None | tuple(mtproxy) | dict(socks/http)
    connection: 'mtproxy' | 'full'
    """
    if not cfg:
        return None, "full"

    ptype = str(cfg.get("type") or "").lower()
    host = cfg.get("host")
    port = int(cfg.get("port") or 0)
    if not host or not port:
        return None, "full"

    if ptype in ("mtproxy", "mtproto"):
        secret = cfg.get("secret")
        if not secret:
            raise ValueError("MTProxy secret required")
        return (host, port, secret), "mtproxy"

    # normalize https → http for pysocks (TLS to proxy is rare; Telethon uses HTTP CONNECT)
    if ptype == "https":
        ptype = "http"

    proxy: dict[str, Any] = {
        "proxy_type": ptype,  # socks5 / socks4 / http
        "addr": host,
        "port": port,
        "rdns": True,
    }
    if cfg.get("username"):
        proxy["username"] = cfg["username"]
    if cfg.get("password"):
        proxy["password"] = cfg["password"]
    return proxy, "full"


def mask_proxy(cfg: dict | None) -> str:
    if not cfg:
        return "off"
    ptype = cfg.get("type", "?")
    host = cfg.get("host", "?")
    port = cfg.get("port", "?")
    auth = ""
    if cfg.get("username"):
        auth = f"{cfg['username']}:***@"
    if ptype in ("mtproxy", "mtproto"):
        return f"mtproxy://{host}:{port}?secret=***"
    return f"{ptype}://{auth}{host}:{port}"


def resolve_proxy_config(
    *,
    cli_host=None,
    cli_port=None,
    cli_type=None,
    cli_secret=None,
    cli_url=None,
) -> dict | None:
    """
    Priority: CLI URL / CLI host+port > env HIKKARI_PROXY / PROXY_URL > proxy.json
    """
    if cli_url:
        return parse_proxy_url(cli_url)

    if cli_host and cli_port:
        ptype = (cli_type or "socks5").lower()
        cfg: dict[str, Any] = {
            "type": ptype,
            "host": cli_host,
            "port": int(cli_port),
        }
        if cli_secret:
            cfg["secret"] = cli_secret
            if ptype not in ("mtproxy", "mtproto"):
                cfg["type"] = "mtproxy"
        return cfg

    for env_key in ("HIKKARI_PROXY", "PROXY_URL", "ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        val = (os.environ.get(env_key) or "").strip()
        if val:
            try:
                return parse_proxy_url(val)
            except Exception as e:
                logger.warning("Invalid %s=%s: %s", env_key, val, e)

    return load_proxy_file()
