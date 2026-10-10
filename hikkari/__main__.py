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

"""Entry point. Checks for user and starts main script"""

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*Python version.*end of life.*")

import getpass
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ._internal import restart

if "--no-git" in sys.argv:
    os.environ["HIKKARI_NO_GIT"] = "1"


def get_data_root():
    for index, arg in enumerate(sys.argv):
        if arg == "--data-root" and index + 1 < len(sys.argv):
            return Path(sys.argv[index + 1]).expanduser()

        if arg.startswith("--data-root="):
            return Path(arg.split("=", maxsplit=1)[1]).expanduser()

    return Path(
        "/data"
        if "DOCKER" in os.environ
        else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    )


def wipe_data():
    if not {"-w", "--wipe"} & set(sys.argv):
        return

    print(
        "Are you sure you want to completely delete all session files, "
        "their databases and modules? This action is irreversible [y/N]"
    )
    if input("> ").strip().lower() not in {"yes", "y"}:
        print("Cancelled")
        sys.exit(0)

    data_root = get_data_root()
    patterns = (
        "config.json",
        "config-*.json",
        "*.session",
        "*.session-journal",
        "api_token.txt",
    )
    dirs = ("loaded_modules", "sessions")
    removed = 0

    for pattern in patterns:
        for path in data_root.glob(pattern):
            if not path.is_file():
                continue

            path.unlink()
            removed += 1

    for dirname in dirs:
        path = data_root / dirname
        if not path.is_dir():
            continue

        shutil.rmtree(path)
        removed += 1

    print(f"Removed files: {removed}")
    sys.exit(0)


wipe_data()


def get_file_hash(filename):
    hasher = hashlib.sha256()
    try:
        with open(filename, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()
    except FileNotFoundError:
        return None


def deps():
    # Full hikkaritl from GitHub (public). If private, use token URL once.
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "hikkaritl>=1.1.2",
        ],
        check=False,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "-q",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--prefer-binary",
            "-r",
            "requirements.txt",
        ],
        check=False,
        timeout=600,
        capture_output=True,
    )
    with open(".requirements_hash", "w") as f:
        f.write(get_file_hash("requirements.txt"))


if (
    getpass.getuser() == "root"
    and "--root" not in " ".join(sys.argv)
    and not {"-h", "--help"} & set(sys.argv)
    and all(trigger not in os.environ for trigger in {"DOCKER", "NO_SUDO"})
):
    print("\U0001f6ab" * 15)
    print("You attempted to run Hikkari on behalf of root user")
    print("Please, create a new user and restart script")
    print("If this action was intentional, pass --root argument instead")
    print("\U0001f6ab" * 15)
    print()
    print("Type force_insecure to ignore this warning")
    print("Type no_sudo if your system has no sudo (Debian vibes)")
    inp = input("> ").lower()
    if inp != "force_insecure":
        sys.exit(1)
    elif inp == "no_sudo":
        os.environ["NO_SUDO"] = "1"
        print("Added NO_SUDO in your environment variables")
        restart()

if sys.version_info < (3, 10, 0):
    print("\U0001f6ab Error: you must use at least Python version 3.10.0")
elif __package__ != "hikkari":
    print(
        "\U0001f6ab Error: you cannot run this as a script; you must execute as a package"
    )
else:
    try:
        import hikkaritl

        # Full library must expose .tl (thin wrapper does not)
        if not hasattr(hikkaritl, "tl"):
            raise ImportError("hikkaritl missing .tl")
    except Exception:
        print("\U0001f504 Installing dependencies...")
        try:
            deps()
        except Exception as e:
            print(f"requirements.txt install failed: {e}")
            print("Trying hikkaritl from GitHub...")
            import subprocess as _sp

            _sp.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--force-reinstall",
                    "hikkaritl>=1.1.2",
                ],
                check=False,
            )
            _sp.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "-q",
                    "--disable-pip-version-check",
                    "-r",
                    "requirements.txt",
                ],
                check=False,
            )
        restart()

    try:
        os.environ.pop('HIKKARI_DO_NOT_RESTART', None)
        os.environ.pop('HIKKARI_DO_NOT_RESTART2', None)
        os.environ.pop('HEROKU_DO_NOT_RESTART', None)
        os.environ.pop('HEROKU_DO_NOT_RESTART2', None)
        from . import log

        log.init()
        from . import main
    except ImportError as e:
        print(
            f"{str(e)}\n\U0001f504 Attempting dependencies installation... Just wait ⏱"
        )
        deps()
        restart()

    if "HEROKU_DO_NOT_RESTART" in os.environ:
        del os.environ["HEROKU_DO_NOT_RESTART"]
    if "HEROKU_DO_NOT_RESTART2" in os.environ:
        del os.environ["HEROKU_DO_NOT_RESTART2"]

    prev_hash = None
    if os.path.exists(".requirements_hash"):
        with open(".requirements_hash") as f:
            prev_hash = f.read().strip()

    if prev_hash != get_file_hash("requirements.txt"):
        print(
            "\U0001f504 Detected changes in requirements.txt, updating dependencies..."
        )
        deps()
        restart()

    main.hikkari.main()
