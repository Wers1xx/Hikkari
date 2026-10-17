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

import asyncio
import atexit
import logging
import os
import random
import signal
import sys
import subprocess
from collections.abc import Callable


async def fw_protect():
    # Shorter pause after restart / when fast-start is set
    if os.environ.get("HIKKARI_FAST_START") or os.environ.get("HIKKARI_DO_NOT_RESTART"):
        await asyncio.sleep(0.02)
    else:
        await asyncio.sleep(0.05)


def get_startup_callback() -> Callable:
    return lambda *_: os.execl(
        sys.executable,
        sys.executable,
        "-m",
        os.path.relpath(os.path.abspath(os.path.dirname(os.path.abspath(__file__)))),
        *sys.argv[1:],
    )


def die():
    """Platform-dependent way to kill the current process group"""
    match True:
        case _ if "DOCKER" in os.environ:
            sys.exit(0)
        case _ if sys.platform == "win32":
            sys.exit(0)
        case _:
            os.killpg(os.getpgid(os.getpid()), signal.SIGTERM)


def restart():
    if "--sandbox" in " ".join(sys.argv):
        exit(0)

    if "HIKKARI_DO_NOT_RESTART2" in os.environ:
        print(
            "hikkaritl is required. Run: pip install -U hikkaritl"
        )
        sys.exit(0)

    logging.getLogger().setLevel(logging.CRITICAL)

    print("🔄 Restarting...")

    # Fast-path flags for the next process
    os.environ["HIKKARI_FAST_START"] = "1"
    if "HIKKARI_DO_NOT_RESTART" not in os.environ:
        os.environ["HIKKARI_DO_NOT_RESTART"] = "1"
    else:
        os.environ["HIKKARI_DO_NOT_RESTART2"] = "1"

    if "DOCKER" in os.environ or sys.platform == "win32":
        atexit.register(get_startup_callback())
    else:
        signal.signal(signal.SIGTERM, get_startup_callback())
    die()


def print_banner(banner: str):
    print("\033[2J\033[3;1f")
    with open(
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "assets",
                banner,
            )
        ),
    ) as f:
        print(f.read())


def check_commit_ancestor(repo, branch):
    """Check if commit is ancestor of origin/master"""
    try:
        commit = repo.commit(branch).hexsha
        repo_path = repo.working_tree_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )

        proc = subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                commit,
                "refs/remotes/origin/master",
            ],
            cwd=repo_path,
            capture_output=True,
            timeout=5,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def get_branch_name(repo_path):
    """Get the current branch name using multiple methods (gitpython, HEAD, git cmd)"""
    branch_name = None

    try:
        import git

        with git.Repo(path=repo_path) as repo:
            branch_name = repo.active_branch.name
    except Exception:
        pass

    if not branch_name:
        try:
            head_path = os.path.join(repo_path, ".git", "HEAD")
            with open(head_path, encoding="utf-8") as f:
                content = f.read().strip()
            if content.startswith("ref:"):
                branch_name = content.split("/")[-1]
        except Exception:
            pass

    if not branch_name:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                candidate = proc.stdout.strip()
                if candidate:
                    branch_name = candidate
        except (subprocess.TimeoutExpired, Exception):
            pass

    if isinstance(branch_name, str):
        branch_name = branch_name.strip().lstrip("refs/heads/")

    return branch_name


def reset_to_master(repo_path):
    """Reset repository to master (or preferred branch if stored). Never silently drop beta."""
    target = "master"
    # Prefer last user-chosen branch if recorded next to the repo
    for candidate in (
        os.path.join(repo_path, ".hikkari_branch"),
        os.path.join(repo_path, "data", ".hikkari_branch"),
    ):
        try:
            with open(candidate, encoding="utf-8") as f:
                name = f.read().strip()
            if name in ("master", "beta", "dev"):
                target = name
                break
        except Exception:
            pass
    try:
        import git

        with git.Repo(path=repo_path) as repo:
            repo.head.reset(index=True, working_tree=True)
            if target in repo.heads:
                repo.heads[target].checkout(force=True)
            elif "master" in repo.heads:
                repo.heads.master.checkout(force=True)
    except Exception:
        try:
            subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                ["git", "checkout", target, "-f"],
                cwd=repo_path,
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, Exception):
            pass


def restore_worktree(repo_path):
    """Restore working tree for allowed users. Try `git restore .`, fallback to `git reset --hard`.

    Returns True if an operation succeeded, False otherwise.
    """

    try:
        proc = subprocess.run(
            ["git", "restore", "."], cwd=repo_path, capture_output=True, timeout=5
        )
        if proc.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, Exception):
        pass

    try:
        proc = subprocess.run(
            ["git", "reset", "--hard"], cwd=repo_path, capture_output=True, timeout=5
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


import re as _re_rich

_EMOJI_OPEN = _re_rich.compile(
    r"<emoji\s+document_id\s*=\s*[\"']?(\d+)[\"']?\s*>", _re_rich.IGNORECASE
)


def normalize_rich_html(html_text):
    """Map legacy <emoji document_id> to <tg-emoji emoji-id> for native Rich API."""
    if not isinstance(html_text, str):
        return html_text
    html_text = _EMOJI_OPEN.sub(r'<tg-emoji emoji-id="\1">', html_text)
    return _re_rich.sub(r"</emoji\s*>", "</tg-emoji>", html_text, flags=_re_rich.IGNORECASE)


# --- Heroku 2.2: token / secret redaction ---
import re as _re

_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    if value and isinstance(value, str) and len(value) >= 8:
        _secrets.add(value)


def redact(text) -> str:
    """Hide tokens, keys, passwords in logs and error text."""
    text = str(text)
    for secret in sorted(_secrets.copy(), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = _re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        text,
        flags=_re.S,
    )
    text = _re.sub(r"\b\d{5,16}:[A-Za-z0-9_-]{30,}\b", "[REDACTED]", text)
    text = _re.sub(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{16,}\b", "[REDACTED]", text)
    text = _re.sub(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9+/_.=-]+", r"\1 [REDACTED]", text)
    text = _re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = _re.sub(
        r"(?i)([\"']?(?:[\w.-]*(?:token|password|passwd|secret|api_key|api_hash|"
        r"auth_key|session_string|basic_auth))[\"']?\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s&,;<>]+)",
        r"\1[REDACTED]",
        text,
    )
    return text
