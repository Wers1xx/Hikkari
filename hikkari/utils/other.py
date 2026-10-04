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
import sys
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
    """Ensure the active asyncio policy can spawn subprocesses."""
    if sys.platform == "win32" or sys.version_info >= (3, 14):
        return

    with warnings.catch_warnings():
        # get_child_watcher() is deprecated on 3.12/3.13; we use it knowingly.
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            asyncio.get_event_loop_policy().get_child_watcher()
            return
        except NotImplementedError:
            pass

        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        with contextlib.suppress(RuntimeError):
            asyncio.set_event_loop(asyncio.get_running_loop())

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
        raise RuntimeError(
            f"Can't invite inline bot to old asset chat, which is required by module: {e}"
        )

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


def ensure_builtin_asset(name: str):
    """Find local asset or download once into BASE_PATH/assets."""
    name = (name or "").strip().lstrip("/")
    if not name or ".." in name or "/" in name or "\\" in name:
        return None

    for d in _asset_search_dirs():
        p = d / name
        if p.is_file() and p.stat().st_size > 100:
            return p

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
        data = urllib.request.urlopen(url, timeout=60).read()
        if len(data) < 100:
            return None
        dest.write_bytes(data)
        return dest
    except Exception:
        __import__("logging").getLogger(__name__).exception("asset download %s", name)
        return None


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
