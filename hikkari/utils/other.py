# ©️ Dan Gazizullin (hikariatama), 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
#
# ©️ Codrago, 2024-2030
# This file is a part of Heroku Userbot
# 🌐 https://github.com/coddrago/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
#
# ©️ Wers1xx, 2025-2026
# This file is a part of Hikkari Userbot
# 🌐 https://github.com/Wers1xx/Hikkari
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from pathlib import Path
import asyncio
import atexit as _atexit
import contextlib
import functools
import logging
import random
import signal
import os
import sys
import time
import typing
import warnings

import hikkaritl
from hikkaritl import hints
from hikkaritl.tl.functions.channels import (
    EditAdminRequest,
    InviteToChannelRequest,
)
from hikkaritl.tl.types import (
    ChatAdminRights,
)

from ..tl_cache import CustomTelegramClient
from ..types import ListLike

parser = hikkaritl.utils.sanitize_parse_mode("html")
logger = logging.getLogger(__name__)


def ensure_child_watcher():
    """Ensure the active asyncio policy can spawn subprocesses (no zombies)."""
    if sys.platform == "win32":
        return

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            policy = asyncio.get_event_loop_policy()
            # Prefer threaded watcher — reaps children even when loop is busy
            if hasattr(asyncio, "ThreadedChildWatcher"):
                try:
                    watcher = policy.get_child_watcher()
                    if type(watcher).__name__ not in (
                        "ThreadedChildWatcher",
                        "PidfdChildWatcher",
                    ):
                        with contextlib.suppress(Exception):
                            policy.set_child_watcher(asyncio.ThreadedChildWatcher())
                except NotImplementedError:
                    with contextlib.suppress(Exception):
                        policy.set_child_watcher(asyncio.ThreadedChildWatcher())
            else:
                with contextlib.suppress(Exception):
                    policy.get_child_watcher()
        except Exception:
            with contextlib.suppress(Exception):
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


def reap_zombies() -> int:
    """Non-blocking waitpid on all exited children. Returns number reaped."""
    if sys.platform == "win32":
        return 0
    n = 0
    try:
        while True:
            try:
                pid, _status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            except OSError:
                break
            if pid <= 0:
                break
            n += 1
    except Exception:
        pass
    return n


_sigchld_installed = False


def install_sigchld_reaper() -> None:
    """Install SIGCHLD handler that reaps zombies (Linux/Unix)."""
    global _sigchld_installed
    if _sigchld_installed or sys.platform == "win32":
        return
    try:
        import signal

        def _handler(signum, frame):  # noqa: ARG001
            reap_zombies()

        # SA_NOCLDSTOP would be ideal but pure Python signal.signal is enough
        signal.signal(signal.SIGCHLD, _handler)
        _sigchld_installed = True
    except Exception:
        pass

custom_placeholders = {}


def rand(size: int, /) -> str:
    """
    Return random string of len `size`
    :param size: Length of string
    :return: Random string
    """
    return "".join(
        [random.choice("abcdefghijklmnopqrstuvwxyz1234567890") for _ in range(size)]
    )


async def invite_inline_bot(
    client: CustomTelegramClient,
    peer: hints.EntityLike,
) -> None:
    """
    Invites inline bot to a chat
    :param client: Client to use
    :param peer: Peer to invite bot to
    :return: None
    :raise RuntimeError: If error occurred while inviting bot
    """
    bot = getattr(getattr(client, "loader", None), "inline", None)
    bot_username = getattr(bot, "bot_username", None) if bot else None
    if not bot_username:
        # No inline bot yet (yesbot/nobot pending) — skip, do not crash
        return

    try:
        await client(InviteToChannelRequest(peer, [bot_username]))
    except Exception as e:
        logger.warning(
            "Can't invite inline bot to asset chat (non-fatal): %s", e
        )
        return

    with contextlib.suppress(Exception):
        await client(
            EditAdminRequest(
                channel=peer,
                user_id=bot_username,
                admin_rights=ChatAdminRights(ban_users=True),
                rank="Hikkari",
            )
        )


def run_sync(func, *args, **kwargs):
    """
    Run a non-async function in a new thread and return an awaitable
    :param func: Sync-only function to execute
    :return: Awaitable coroutine
    """
    return asyncio.get_event_loop().run_in_executor(
        None,
        functools.partial(func, *args, **kwargs),
    )


def run_async(loop: asyncio.AbstractEventLoop, coro: typing.Awaitable) -> typing.Any:
    """
    Run an async function as a non-async function, blocking till it's done
    :param loop: Event loop to run the coroutine in
    :param coro: Coroutine to run
    :return: Result of the coroutine
    """
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def merge(
    a: dict,
    b: dict,
    /,
    *,
    deep: bool = True,
) -> dict:
    """
    Merge with replace dictionary a to dictionary b
    :param a: Dictionary to merge
    :param b: Dictionary to merge to
    :return: Merged dictionary
    """
    for key, a_value in a.items():
        b_value = b.get(key)

        match (
            key not in b,
            isinstance(a_value, dict) and isinstance(b_value, dict) and deep,
            isinstance(a_value, list) and isinstance(b_value, list),
        ):
            case (True, _, _):
                b[key] = a_value
            case (False, True, _):
                b[key] = merge(a_value, b_value, deep=deep)
            case (False, False, True):
                b[key] = list(dict.fromkeys(b_value + a_value))
            case _:
                b[key] = a_value

    return b


def chunks(_list: ListLike, n: int, /) -> list[list[typing.Any]]:
    """
    Split provided `_list` into chunks of `n`
    :param _list: List to split
    :param n: Chunk size
    :return: List of chunks
    """
    return [_list[i : i + n] for i in range(0, len(_list), n)]


def atexit(
    func: typing.Callable,
    use_signal: int | None = None,
    *args,
    **kwargs,
) -> None:
    """
    Calls function on exit
    :param func: Function to call
    :param use_signal: If passed, `signal` will be used instead of `atexit`
    :param args: Arguments to pass to function
    :param kwargs: Keyword arguments to pass to function
    :return: None
    """
    if use_signal:
        signal.signal(use_signal, lambda *_: func(*args, **kwargs))
        return

    _atexit.register(functools.partial(func, *args, **kwargs))


def _copy_tl(o, **kwargs):
    d = o.to_dict()
    del d["_"]
    d.update(kwargs)
    return o.__class__(**d)


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable format
    :param size_bytes: Size in bytes
    :return: Formatted string (e.g., '1.5 MB')
    """
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return ".1f"


def is_url(string: str) -> bool:
    """
    Check if string is a valid URL
    :param string: String to check
    :return: True if valid URL, False otherwise
    """
    import re

    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return url_pattern.match(string) is not None


def get_iso_time() -> str:
    """
    Get current time in ISO format
    :return: ISO formatted time string
    """
    from datetime import datetime

    return datetime.utcnow().isoformat() + "Z"


def safe_getattr(obj, attr, default=None):
    """
    Safely get attribute from object, returning default if not found
    :param obj: Object to get attribute from
    :param attr: Attribute name
    :param default: Default value if attribute not found
    :return: Attribute value or default
    """
    try:
        return getattr(obj, attr, default)
    except AttributeError:
        return default


def _asset_search_dirs():
    """All places where built-in media may live."""
    dirs = []
    try:
        from .. import main as _main
        base = Path(getattr(_main, "BASE_PATH", Path.cwd()))
        dirs.append(base / "assets")
        dirs.append(base / "hikkari" / "assets")
    except Exception:
        pass
    here = Path(__file__).resolve()
    # hikkari/utils/other.py → hikkari/assets, repo assets
    dirs.append(here.parents[1] / "assets")  # hikkari/assets
    dirs.append(here.parents[2] / "assets")  # repo/assets
    dirs.append(Path.cwd() / "assets")
    dirs.append(Path.cwd() / "hikkari" / "assets")
    # unique preserve order
    seen = set()
    out = []
    for d in dirs:
        try:
            key = str(d.resolve())
        except Exception:
            key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


_ASSET_URLS = {
    "hikkari-info.jpg": "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-info.jpg",
    "hikkari-started.jpg": "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-started.jpg",
    "hikkari-config.jpg": "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-config.jpg",
    "hikkari-cmd.jpg": "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-cmd.jpg",
    "hikkari-ava.png": "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-ava.png",
    "bot_avatar.png": "https://raw.githubusercontent.com/Wers1xx/Hikkari/master/assets/hikkari-ava.png",
}


# Asset names whose download failed recently: name -> monotonic time of failure.
# Prevents blocking the event loop on every call when GitHub is unreachable.
_ASSET_FAIL_TTL = 600
_asset_failed: dict = {}

# Media URLs Telegram refused to fetch (WEBPAGE_CURL_FAILED and friends).
_bad_media_urls: set = set()


def mark_bad_media(url: str) -> None:
    """Remember a media URL that Telegram rejected, so it is not retried."""
    if url:
        _bad_media_urls.add(str(url).strip())


def is_bad_media(url: str) -> bool:
    """True if this media URL was rejected by Telegram earlier in this run."""
    return str(url or "").strip() in _bad_media_urls


def ensure_builtin_asset(name: str):
    """Find local asset or download once into BASE_PATH/assets."""
    name = (name or "").strip().lstrip("/")
    if not name or ".." in name or "/" in name or "\\" in name:
        return None

    for d in _asset_search_dirs():
        p = d / name
        if p.is_file() and p.stat().st_size > 100:
            return p

    failed_at = _asset_failed.get(name)
    if failed_at is not None and time.monotonic() - failed_at < _ASSET_FAIL_TTL:
        return None

    # Download into primary assets dir
    try:
        from .. import main as _main
        dest_dir = Path(getattr(_main, "BASE_PATH", Path.cwd())) / "assets"
    except Exception:
        dest_dir = Path.cwd() / "assets"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name

    url = _ASSET_URLS.get(name)
    if not url:
        return None
    try:
        import urllib.request
        logger = __import__("logging").getLogger(__name__)
        logger.info("Downloading builtin asset %s …", name)
        data = urllib.request.urlopen(url, timeout=10).read()
        if len(data) < 100:
            _asset_failed[name] = time.monotonic()
            return None
        dest.write_bytes(data)
        return dest
    except Exception:
        _asset_failed[name] = time.monotonic()
        __import__("logging").getLogger(__name__).warning(
            "asset download %s failed, will retry in %ss", name, _ASSET_FAIL_TTL
        )
        return None



def is_audio_banner(banner) -> bool:
    """True if banner config points to an audio track."""
    if not banner:
        return False
    if isinstance(banner, (list, tuple)) and banner:
        import random
        try:
            banner = random.choice(list(banner))
        except Exception:
            return False
    s = str(banner).strip()
    if s.startswith(("audio:", "audio_ref:", "audio_msg:")):
        return True
    p = Path(s)
    return p.suffix.lower() in {".mp3", ".ogg", ".m4a", ".flac", ".wav", ".opus"}


def _pick_banner_item(banner):
    if isinstance(banner, (list, tuple)) and banner:
        import random
        try:
            return random.choice(list(banner))
        except Exception:
            return banner[0] if banner else None
    return banner


def pack_audio_ref_from_message(message) -> str | None:
    """
    Build instant-send audio banner value from a replied music message.
    Prefer Telegram document reference (no re-upload) + title/performer.
    Format: audio_ref:<base64-json>
    """
    import base64
    import json

    if not message:
        return None
    doc = getattr(message, "document", None)
    if doc is None and getattr(message, "media", None) is not None:
        doc = getattr(message.media, "document", None)
    if doc is None and getattr(message, "audio", None) is not None:
        # audio prop may already be the document
        aud = message.audio
        doc = getattr(aud, "document", None) or aud

    title = ""
    performer = ""
    duration = 0
    voice = False
    attrs = list(getattr(doc, "attributes", None) or [])
    for attr in attrs:
        if "Audio" in type(attr).__name__:
            title = getattr(attr, "title", None) or ""
            performer = getattr(attr, "performer", None) or ""
            duration = int(getattr(attr, "duration", 0) or 0)
            voice = bool(getattr(attr, "voice", False))
            break

    payload = {
        "title": title or "",
        "performer": performer or "",
        "duration": duration,
        "voice": voice,
        "mime": getattr(doc, "mime_type", None) or "audio/mpeg",
        "size": int(getattr(doc, "size", 0) or 0),
    }

    if doc is not None and getattr(doc, "id", None) is not None:
        fr = getattr(doc, "file_reference", b"") or b""
        if isinstance(fr, str):
            fr = fr.encode("utf-8", errors="ignore")
        payload.update(
            {
                "id": int(doc.id),
                "access_hash": int(getattr(doc, "access_hash", 0) or 0),
                "file_reference": base64.b64encode(fr).decode("ascii"),
                "dc_id": int(getattr(doc, "dc_id", 0) or 0),
            }
        )
        # also keep source message for copy fallback
        try:
            payload["chat_id"] = int(
                getattr(message, "chat_id", None)
                or getattr(getattr(message, "peer_id", None), "channel_id", 0)
                or 0
            )
            payload["msg_id"] = int(getattr(message, "id", 0) or 0)
        except Exception:
            pass
        raw = base64.urlsafe_b64encode(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        return f"audio_ref:{raw}"

    return None


def unpack_audio_ref(value: str) -> dict | None:
    import base64
    import json

    s = str(value or "").strip()
    if s.startswith("audio_ref:"):
        s = s[len("audio_ref:") :]
    else:
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8"))
        if isinstance(data, dict) and data.get("id") is not None:
            return data
    except Exception:
        return None
    return None


def audio_banner_send_kwargs(banner) -> dict:
    """
    kwargs for client.send_file / utils.answer to send audio banner instantly.
    Returns {} if not an audio_ref banner.
    """
    item = _pick_banner_item(banner)
    data = unpack_audio_ref(str(item or ""))
    if not data:
        return {}
    try:
        from hikkaritl.tl.types import (
            InputDocument,
            DocumentAttributeAudio,
            DocumentAttributeFilename,
        )
        import base64

        fr = base64.b64decode(data.get("file_reference") or "")
        doc = InputDocument(
            id=int(data["id"]),
            access_hash=int(data.get("access_hash") or 0),
            file_reference=fr,
        )
        title = data.get("title") or "Track"
        performer = data.get("performer") or ""
        duration = int(data.get("duration") or 0)
        attrs = [
            DocumentAttributeAudio(
                duration=duration,
                title=title,
                performer=performer,
                voice=bool(data.get("voice")),
            ),
        ]
        fname = f"{performer + ' - ' if performer else ''}{title}.m4a"
        attrs.append(DocumentAttributeFilename(file_name=fname[:64]))
        return {
            "file": doc,
            "attributes": attrs,
            "voice_note": False,
        }
    except Exception:
        return {}


def resolve_banner_media(banner):
    """Resolve config banner → local file path or remote webpage media."""
    if not banner:
        return None
    try:
        from hikkaritl.tl.types import InputMediaWebPage
    except Exception:
        InputMediaWebPage = None

    if isinstance(banner, (list, tuple)) and banner:
        import random
        banner = random.choice(list(banner))

    s = str(banner).strip()
    if not s:
        return None

    # Instant audio ref — handled by audio_banner_send_kwargs (not a file path)
    if s.startswith("audio_ref:"):
        return s
    # Audio track saved via .fcfg reply to music (local fallback)
    if s.startswith("audio:"):
        path = Path(s[6:].strip())
        return str(path) if path.is_file() else None
    if Path(s).is_file() and Path(s).suffix.lower() in {
        ".mp3", ".ogg", ".m4a", ".flac", ".wav", ".opus",
    }:
        return s

    if s.startswith("local:"):
        name = s[6:].strip()
        path = ensure_builtin_asset(name)
        return str(path) if path else None

    # bare filename
    if not s.startswith(("http://", "https://")) and ("." in s) and ("/" not in s):
        path = ensure_builtin_asset(s)
        if path:
            return str(path)

    # try as path under assets
    path = ensure_builtin_asset(Path(s).name) if not s.startswith("http") else None
    if path:
        return str(path)

    if s.startswith(("http://", "https://")):
        # Prefer local mirror if we know the filename
        name = s.rsplit("/", 1)[-1].split("?", 1)[0]
        if name in _ASSET_URLS:
            local = ensure_builtin_asset(name)
            if local:
                return str(local)
        if InputMediaWebPage is not None:
            return InputMediaWebPage(s, optional=True)
        return s

    return s
