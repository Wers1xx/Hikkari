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

import functools
import logging
import re
from pathlib import Path

from herokutl.sessions import SQLiteSession

from ..tl_cache import CustomTelegramClient
from .customtl import ConnectionTcpFull, MTProtoState


def patch(client: CustomTelegramClient, session: SQLiteSession):
    session_id = re.findall(r"\d+", session.filename)[-1]
    client._sender._state = MTProtoState(session.auth_key, client._sender._loggers)
    client._connection = ConnectionTcpFull

    socket_path = (
        Path(__file__).parent.parent.parent / f"hikkari-{session_id}-proxy.sock"
    )
    client.connect = functools.partial(client.connect, unix_socket_path=socket_path)

    logging.warning("Patched mtprotostate")
