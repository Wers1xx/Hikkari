import logging
import gc
import os
import sys
import threading
import asyncio
logger = logging.getLogger(__name__)
from pathlib import Path
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

import contextlib
import hikkaritl
from hikkaritl.tl.types import Message, User

from .. import loader, main, utils, version
from ..inline.types import InlineCall


@loader.tds
class CoreMod(loader.Module):
    """Control core userbot settings"""

    strings = {
        "name": "Settings",
                "richhelp": (
            "<tg-emoji emoji-id=5343785308817236494>✨</tg-emoji> <b>Hikkari Rich Messages</b>\n\n"
            "<b>Status:</b> <code>{status}</code>\n\n"
            "<blockquote expandable><b>1. What is Rich</b>\n"
            "Native Telegram messages (Bot API 10.1+): tables, headings, "
            "<code>&lt;details&gt;</code> collapsible blocks, banners, lists.\n"
            "Shown as <b>via @bot</b>. Needs <b>Telegram Premium</b> on owner.\n"
            "Config UI stays classic forms.</blockquote>\n\n"
            "<blockquote expandable><b>2. Enable</b>\n"
            "<code>{prefix}cfg Settings rich_mode true</code>\n"
            "Without Premium it is forced off.</blockquote>\n\n"
            "<blockquote expandable><b>3. Built-in</b>\n"
            "• info / help / ping — tables + banner + details\n"
            "• other answer() texts when rich_mode on\n"
            "• cfg — not converted</blockquote>\n\n"
            "<blockquote expandable><b>4. Custom text (custom_message)</b>\n"
            "In HikkariInfo → <code>custom_message</code> put <b>Rich HTML</b>.\n"
            "With rich_mode ON it is sent as real Rich Message via @bot.\n"
            "Placeholders still work: <code>{{me}}</code> <code>{{version}}</code> "
            "<code>{{build}}</code> <code>{{ping}}</code> <code>{{uptime}}</code> "
            "<code>{{prefix}}</code> <code>{{platform}}</code> …</blockquote>\n\n"
            "<blockquote expandable><b>5. Core tags</b>\n"
            "<code>&lt;h1&gt;…&lt;h6&gt;</code> — headings\n"
            "<code>&lt;p&gt;…&lt;/p&gt;</code> — paragraph\n"
            "<code>&lt;b&gt; &lt;i&gt; &lt;u&gt; &lt;s&gt; &lt;code&gt; &lt;mark&gt;</code>\n"
            "<code>&lt;tg-spoiler&gt;</code> — spoiler\n"
            "<code>&lt;tg-emoji emoji-id=ID&gt;✨&lt;/tg-emoji&gt;</code>\n"
            "<code>&lt;blockquote&gt;</code> / expandable attribute\n"
            "<code>&lt;hr/&gt;</code> — divider</blockquote>\n\n"
            "<blockquote expandable><b>6. Table</b>\n"
            "<pre>&lt;table bordered striped&gt;\n"
            "&lt;tr&gt;&lt;th&gt;A&lt;/th&gt;&lt;th&gt;B&lt;/th&gt;&lt;/tr&gt;\n"
            "&lt;tr&gt;&lt;td&gt;1&lt;/td&gt;&lt;td&gt;2&lt;/td&gt;&lt;/tr&gt;\n"
            "&lt;/table&gt;</pre>\n"
            "Attrs: <code>bordered</code> <code>striped</code> <code>compact</code>\n"
            "Cell: <code>align=left|center|right</code> <code>colspan</code></blockquote>\n\n"
            "<blockquote expandable><b>7. Collapsible details</b>\n"
            "<pre>&lt;details&gt;\n"
            "&lt;summary&gt;Title&lt;/summary&gt;\n"
            "&lt;p&gt;Hidden content&lt;/p&gt;\n"
            "&lt;/details&gt;</pre>\n"
            "Add <code>open</code> to expand by default.</blockquote>\n\n"
            "<blockquote expandable><b>8. Banner / media</b>\n"
            "<pre>&lt;figure&gt;\n"
            "&lt;img src=\"https://x0.at/xxx.jpg\"/&gt;\n"
            "&lt;figcaption&gt;Caption&lt;/figcaption&gt;\n"
            "&lt;/figure&gt;</pre>\n"
            "Or set <code>banner_url</code> in module config.</blockquote>\n\n"
            "<blockquote expandable><b>9. Example custom_message</b>\n"
            "<pre>&lt;h2&gt;My Hikkari&lt;/h2&gt;\n"
            "&lt;table bordered striped&gt;\n"
            "&lt;tr&gt;&lt;th&gt;Field&lt;/th&gt;&lt;th&gt;Value&lt;/th&gt;&lt;/tr&gt;\n"
            "&lt;tr&gt;&lt;td&gt;Owner&lt;/td&gt;&lt;td&gt;{{me}}&lt;/td&gt;&lt;/tr&gt;\n"
            "&lt;tr&gt;&lt;td&gt;Ping&lt;/td&gt;&lt;td&gt;{{ping}}&lt;/td&gt;&lt;/tr&gt;\n"
            "&lt;/table&gt;\n"
            "&lt;details&gt;&lt;summary&gt;More&lt;/summary&gt;\n"
            "&lt;p&gt;Uptime {{uptime}} · {{version}}&lt;/p&gt;\n"
            "&lt;/details&gt;</pre></blockquote>\n\n"
            "<blockquote expandable><b>10. Template</b>\n"
            "<code>{prefix}cfg Settings rich_template</code>\n"
            "{{text}} = body, {{star}} = star emoji</blockquote>\n\n"
            "<blockquote expandable><b>11. Tips</b>\n"
            "• Only works as Rich path (via @bot), not classic sendMessage\n"
            "• /start the inline bot\n"
            "• Max ~32k chars, tables up to 20 columns\n"
            "• Test: <code>{prefix}info</code> <code>{prefix}help</code></blockquote>"
        ),
        "rich_status_on": "ON ✨",
        "rich_status_off": "OFF",

        "ubproc_title": "<emoji document_id=5282843764451195532>🖥</emoji> <b>Hikkari · Processes</b>",
        "ubproc_choose": "Choose a section:",
        "ubproc_pid": "<b>PID</b>: <code>{}</code>",
        "ubproc_rss": "<b>RSS</b>: <code>{}</code>",
        "ubproc_cpu": "<b>CPU</b>: <code>{}</code>",
        "ubproc_threads": "<b>Threads</b>: <code>{}</code>",
        "ubproc_tasks": "<b>Async tasks</b>: <code>{}</code>",
        "ubproc_modules": "<b>Modules</b>: <code>{}</code>",
        "ubproc_children": "<b>Children</b>: <code>{}</code>",
        "ubproc_btn_global": "🌐 Global analysis",
        "ubproc_btn_threads": "🧵 Threads",
        "ubproc_btn_tasks": "⚡ Tasks",
        "ubproc_btn_modules": "📦 Modules",
        "ubproc_btn_memory": "🧠 Memory",
        "ubproc_btn_children": "👶 Children",
        "ubproc_btn_gc": "🗑 GC / garbage",
        "ubproc_btn_refresh": "🔄 Refresh",
        "ubproc_btn_close": "❌ Close",
        "ubproc_btn_menu": "◀️ Menu",
        "ubproc_btn_gc_run": "♻️ Run gc.collect()",
        "ubproc_btn_gc_back": "🗑 Back to GC",
        "ubproc_global_title": "<emoji document_id=5282843764451195532>🖥</emoji> <b>Global analysis</b>",
        "ubproc_line_rss": "• Process RSS: <code>{}</code>",
        "ubproc_line_vms": "• Process VMS: <code>{}</code>",
        "ubproc_line_cpu": "• CPU: <code>{}</code>",
        "ubproc_line_os_threads": "• OS threads: <code>{}</code>",
        "ubproc_line_py_threads": "• Python threads: <code>{}</code>",
        "ubproc_line_async": "• Async tasks: <code>{}</code> (alive {})",
        "ubproc_line_mods": "• Modules: <code>{}</code> (core {}, ext {})",
        "ubproc_line_child": "• Child procs: <code>{}</code>",
        "ubproc_line_files": "• Open files: <code>{}</code>",
        "ubproc_line_conns": "• Connections: <code>{}</code>",
        "ubproc_line_sysram": "• System RAM: <code>{}%</code> ({} / {})",
        "ubproc_line_gc": "• GC counts: <code>{}</code>, garbage: <code>{}</code>, objects: <code>{}</code>",
        "ubproc_top_mods": "<b>Top modules by size</b>",
        "ubproc_top_children": "<b>Children (RSS)</b>",
        "ubproc_sec_threads": "🧵 <b>Threads</b> ({})",
        "ubproc_sec_tasks": "⚡ <b>Async tasks</b> ({})",
        "ubproc_sec_modules": "📦 <b>Modules</b> ({}) — by estimated size",
        "ubproc_sec_memory": "🧠 <b>Memory</b>",
        "ubproc_sec_children": "👶 <b>Child processes</b> ({})",
        "ubproc_sec_gc": "🗑 <b>GC / garbage</b>",
        "ubproc_no_children": "<i>No child processes</i>",
        "ubproc_mem_rss": "• RSS: <code>{}</code>",
        "ubproc_mem_vms": "• VMS: <code>{}</code>",
        "ubproc_mem_cpu": "• CPU: <code>{}</code>",
        "ubproc_mem_files": "• Open files: <code>{}</code>",
        "ubproc_mem_conns": "• Connections: <code>{}</code>",
        "ubproc_sys_title": "<b>System</b>",
        "ubproc_sys_used": "• Used: <code>{}</code> / <code>{}</code>",
        "ubproc_sys_free": "• Available: <code>{}</code>",
        "ubproc_sys_load": "• Load: <code>{}%</code>",
        "ubproc_gc_counts": "• counts: <code>{}</code>",
        "ubproc_gc_garbage": "• garbage list: <code>{}</code>",
        "ubproc_gc_objects": "• tracked objects: <code>{}</code>",
        "ubproc_gc_hint": "<i>High object count + RSS growth often means a leak in a module loop.</i>",
        "ubproc_gc_done": "♻️ <b>gc.collect()</b> → freed <code>{}</code> objects",
        "ubproc_page": "📄 {}/{}",
        "ubproc_core": "core",
        "ubproc_ext": "ext",
        "ubproc_daemon": "daemon",
        "ubproc_main_thr": "main",
        "_cmd_doc_ubproc": "Internal processes & resource panel (RAM/CPU, tasks, modules)",
    }

    strings_ru = {
                "richhelp": (
            "<tg-emoji emoji-id=5343785308817236494>✨</tg-emoji> <b>Rich-сообщения Hikkari</b>\n\n"
            "<b>Статус:</b> <code>{status}</code>\n\n"
            "<blockquote expandable><b>1. Что это</b>\n"
            "Нативные сообщения Telegram (Bot API 10.1+): таблицы, заголовки, "
            "раскрывающиеся <code>&lt;details&gt;</code>, баннеры, списки.\n"
            "Показываются как <b>via @бот</b>. Нужен <b>Premium</b> у владельца.\n"
            "Конфиг остаётся обычными формами.</blockquote>\n\n"
            "<blockquote expandable><b>2. Включение</b>\n"
            "<code>{prefix}cfg Settings rich_mode true</code>\n"
            "Без Premium сбрасывается.</blockquote>\n\n"
            "<blockquote expandable><b>3. Встроенное</b>\n"
            "• info / help / ping — таблицы + баннер + details\n"
            "• другие answer() при rich_mode\n"
            "• cfg — не конвертируется</blockquote>\n\n"
            "<blockquote expandable><b>4. Свой текст (custom_message)</b>\n"
            "В HikkariInfo → <code>custom_message</code> пиши <b>Rich HTML</b>.\n"
            "При rich_mode ON уходит как настоящее Rich via @бот.\n"
            "Плейсхолдеры: <code>{{me}}</code> <code>{{version}}</code> "
            "<code>{{build}}</code> <code>{{ping}}</code> <code>{{uptime}}</code> "
            "<code>{{prefix}}</code> <code>{{platform}}</code> и др.</blockquote>\n\n"
            "<blockquote expandable><b>5. Основные теги</b>\n"
            "<code>&lt;h1&gt;…&lt;h6&gt;</code> — заголовки\n"
            "<code>&lt;p&gt;…&lt;/p&gt;</code> — абзац\n"
            "<code>&lt;b&gt; &lt;i&gt; &lt;u&gt; &lt;s&gt; &lt;code&gt; &lt;mark&gt;</code>\n"
            "<code>&lt;tg-spoiler&gt;</code> — спойлер\n"
            "<code>&lt;tg-emoji emoji-id=ID&gt;✨&lt;/tg-emoji&gt;</code>\n"
            "<code>&lt;blockquote&gt;</code> / expandable\n"
            "<code>&lt;hr/&gt;</code> — разделитель</blockquote>\n\n"
            "<blockquote expandable><b>6. Таблица</b>\n"
            "<pre>&lt;table bordered striped&gt;\n"
            "&lt;tr&gt;&lt;th&gt;A&lt;/th&gt;&lt;th&gt;B&lt;/th&gt;&lt;/tr&gt;\n"
            "&lt;tr&gt;&lt;td&gt;1&lt;/td&gt;&lt;td&gt;2&lt;/td&gt;&lt;/tr&gt;\n"
            "&lt;/table&gt;</pre>\n"
            "Атрибуты: <code>bordered</code> <code>striped</code> <code>compact</code>\n"
            "Ячейка: <code>align</code> <code>colspan</code></blockquote>\n\n"
            "<blockquote expandable><b>7. Раскрывающийся блок</b>\n"
            "<pre>&lt;details&gt;\n"
            "&lt;summary&gt;Заголовок&lt;/summary&gt;\n"
            "&lt;p&gt;Скрытый текст&lt;/p&gt;\n"
            "&lt;/details&gt;</pre>\n"
            "Атрибут <code>open</code> — открыт по умолчанию.</blockquote>\n\n"
            "<blockquote expandable><b>8. Баннер / медиа</b>\n"
            "<pre>&lt;figure&gt;\n"
            "&lt;img src=\"https://x0.at/xxx.jpg\"/&gt;\n"
            "&lt;figcaption&gt;Подпись&lt;/figcaption&gt;\n"
            "&lt;/figure&gt;</pre>\n"
            "Или <code>banner_url</code> в конфиге модуля.</blockquote>\n\n"
            "<blockquote expandable><b>9. Пример custom_message</b>\n"
            "<pre>&lt;h2&gt;Мой Hikkari&lt;/h2&gt;\n"
            "&lt;table bordered striped&gt;\n"
            "&lt;tr&gt;&lt;th&gt;Поле&lt;/th&gt;&lt;th&gt;Значение&lt;/th&gt;&lt;/tr&gt;\n"
            "&lt;tr&gt;&lt;td&gt;Владелец&lt;/td&gt;&lt;td&gt;{{me}}&lt;/td&gt;&lt;/tr&gt;\n"
            "&lt;tr&gt;&lt;td&gt;Пинг&lt;/td&gt;&lt;td&gt;{{ping}}&lt;/td&gt;&lt;/tr&gt;\n"
            "&lt;/table&gt;\n"
            "&lt;details&gt;&lt;summary&gt;Ещё&lt;/summary&gt;\n"
            "&lt;p&gt;Аптайм {{uptime}} · {{version}}&lt;/p&gt;\n"
            "&lt;/details&gt;</pre></blockquote>\n\n"
            "<blockquote expandable><b>10. Шаблон</b>\n"
            "<code>{prefix}cfg Settings rich_template</code>\n"
            "{{text}} = текст, {{star}} = звезда</blockquote>\n\n"
            "<blockquote expandable><b>11. Советы</b>\n"
            "• Только путь Rich (via @бот), не обычный sendMessage\n"
            "• /start инлайн-боту\n"
            "• До ~32k символов, таблицы до 20 колонок\n"
            "• Проверка: <code>{prefix}info</code> <code>{prefix}help</code></blockquote>"
        ),
        "rich_status_on": "ВКЛ ✨",
        "rich_status_off": "ВЫКЛ",

        "ubproc_title": "<emoji document_id=5282843764451195532>🖥</emoji> <b>Hikkari · Процессы</b>",
        "ubproc_choose": "Выбери раздел:",
        "ubproc_pid": "<b>PID</b>: <code>{}</code>",
        "ubproc_rss": "<b>RSS</b>: <code>{}</code>",
        "ubproc_cpu": "<b>CPU</b>: <code>{}</code>",
        "ubproc_threads": "<b>Потоки</b>: <code>{}</code>",
        "ubproc_tasks": "<b>Async-задачи</b>: <code>{}</code>",
        "ubproc_modules": "<b>Модули</b>: <code>{}</code>",
        "ubproc_children": "<b>Дочерние</b>: <code>{}</code>",
        "ubproc_btn_global": "🌐 Глобальный анализ",
        "ubproc_btn_threads": "🧵 Потоки",
        "ubproc_btn_tasks": "⚡ Задачи",
        "ubproc_btn_modules": "📦 Модули",
        "ubproc_btn_memory": "🧠 Память",
        "ubproc_btn_children": "👶 Дочерние",
        "ubproc_btn_gc": "🗑 GC / мусор",
        "ubproc_btn_refresh": "🔄 Обновить",
        "ubproc_btn_close": "❌ Закрыть",
        "ubproc_btn_menu": "◀️ Меню",
        "ubproc_btn_gc_run": "♻️ Запустить gc.collect()",
        "ubproc_btn_gc_back": "🗑 Назад к GC",
        "ubproc_global_title": "<emoji document_id=5282843764451195532>🖥</emoji> <b>Глобальный анализ</b>",
        "ubproc_line_rss": "• RSS процесса: <code>{}</code>",
        "ubproc_line_vms": "• VMS процесса: <code>{}</code>",
        "ubproc_line_cpu": "• CPU: <code>{}</code>",
        "ubproc_line_os_threads": "• Потоки ОС: <code>{}</code>",
        "ubproc_line_py_threads": "• Потоки Python: <code>{}</code>",
        "ubproc_line_async": "• Async-задачи: <code>{}</code> (живых {})",
        "ubproc_line_mods": "• Модули: <code>{}</code> (ядро {}, внешние {})",
        "ubproc_line_child": "• Дочерние процессы: <code>{}</code>",
        "ubproc_line_files": "• Открытые файлы: <code>{}</code>",
        "ubproc_line_conns": "• Соединения: <code>{}</code>",
        "ubproc_line_sysram": "• ОЗУ системы: <code>{}%</code> ({} / {})",
        "ubproc_line_gc": "• GC counts: <code>{}</code>, мусор: <code>{}</code>, объекты: <code>{}</code>",
        "ubproc_top_mods": "<b>Топ модулей по размеру</b>",
        "ubproc_top_children": "<b>Дочерние (RSS)</b>",
        "ubproc_sec_threads": "🧵 <b>Потоки</b> ({})",
        "ubproc_sec_tasks": "⚡ <b>Async-задачи</b> ({})",
        "ubproc_sec_modules": "📦 <b>Модули</b> ({}) — по оценке размера",
        "ubproc_sec_memory": "🧠 <b>Память</b>",
        "ubproc_sec_children": "👶 <b>Дочерние процессы</b> ({})",
        "ubproc_sec_gc": "🗑 <b>GC / мусор</b>",
        "ubproc_no_children": "<i>Дочерних процессов нет</i>",
        "ubproc_mem_rss": "• RSS: <code>{}</code>",
        "ubproc_mem_vms": "• VMS: <code>{}</code>",
        "ubproc_mem_cpu": "• CPU: <code>{}</code>",
        "ubproc_mem_files": "• Открытые файлы: <code>{}</code>",
        "ubproc_mem_conns": "• Соединения: <code>{}</code>",
        "ubproc_sys_title": "<b>Система</b>",
        "ubproc_sys_used": "• Занято: <code>{}</code> / <code>{}</code>",
        "ubproc_sys_free": "• Доступно: <code>{}</code>",
        "ubproc_sys_load": "• Нагрузка: <code>{}%</code>",
        "ubproc_gc_counts": "• counts: <code>{}</code>",
        "ubproc_gc_garbage": "• список garbage: <code>{}</code>",
        "ubproc_gc_objects": "• отслеживаемые объекты: <code>{}</code>",
        "ubproc_gc_hint": "<i>Много объектов + рост RSS часто значит утечку в цикле модуля.</i>",
        "ubproc_gc_done": "♻️ <b>gc.collect()</b> → освобождено <code>{}</code> объектов",
        "ubproc_page": "📄 {}/{}",
        "ubproc_core": "ядро",
        "ubproc_ext": "внешн.",
        "ubproc_daemon": "daemon",
        "ubproc_main_thr": "main",
        "_cmd_doc_ubproc": "Панель внутренних процессов и ресурсов (RAM/CPU, задачи, модули)",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "rich_mode",
                False,
                lambda: "Rich mode: premium emoji / blockquotes in built-in texts",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "rich_template",
                "{text}",
                lambda: "Rich template. Placeholders: {text}, {star}. Example: <blockquote>{text}</blockquote>",
                validator=loader.validators.String(),
            ),

            loader.ConfigValue(
                "allow_nonstandart_prefixes",
                False,
                "Allow non-standard prefixes like premium emojis or multi-symbol prefixes",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "alias_emoji",
                "<tg-emoji emoji-id=4974259868996207180>▪️</tg-emoji>",
                "just emoji in .aliases",
            ),
        )

    async def client_ready(self):
        try:
            self._db.set("hikkari.rich", "enabled", bool(self.config["rich_mode"]))
            self._db.set("hikkari.rich", "template", str(self.config["rich_template"] or "{text}"))
        except Exception:
            pass
        self._markup = lambda: utils.chunks(
            [
                {
                    "text": self.strings[platform],
                    "callback": self._inline__choose__installation,
                    "args": (platform,),
                }
                for platform in [
                    "vds",
                    "wsl",
                    "userland",
                    "hikkahost",
                ]
            ],
            2,
        )

    async def blacklistcommon(self, message: Message):
        args = utils.get_args(message)

        if len(args) > 2:
            await utils.answer(message, self.strings["too_many_args"])
            return

        chatid = None
        module = None

        if args:
            try:
                chatid = int(args[0])
            except ValueError:
                module = args[0]

        if len(args) == 2:
            module = args[1]

        if chatid is None:
            chatid = utils.get_chat_id(message)

        module = self.allmodules.get_classname(module)
        return f"{str(chatid)}.{module}" if module else chatid

    @loader.command(
        ru_doc="Информация о Хероку",
        en_doc="Information of Hikkari",
        ua_doc="Інформація про Хероку",
        de_doc="Informationen über Hikkari",
    )
    async def hikkaricmd(self, message: Message):

        branch_text = ""
        if version.branch == "master":
            branch_text = ""
        elif version.branch == "beta" or self.tg_id in [
            1714120111,
            1226061708,
            5717135725,
        ]:
            branch_text = self.strings["happy_beta"].format(version.branch)
        else:
            branch_text = self.strings["unstable"].format(version.branch)

        banner = utils.ensure_builtin_asset("hikkari-cmd.jpg")
        await utils.answer(
            message,
            self.strings["hikkari"].format(
                (
                    utils.get_platform_emoji()
                    if self._client.hikkari_me.premium
                    else "✨ <b>Hikkari userbot</b>"
                ),
                *version.__version__,
                utils.get_commit_url(),
                f"{hikkaritl.__version__} #{hikkaritl.tl.alltlobjects.LAYER}",
            )
            + (branch_text),
            file=str(banner) if banner and Path(banner).is_file() else None,
            reply_to=getattr(message, "reply_to_msg_id", None),
        )

    @loader.command()

    @loader.command(
        ru_doc="Команда разработчиков Hikkari",
        en_doc="Hikkari developers table",
    )
    async def devs(self, message: Message):
        """Таблица разработчиков / дизайнеров / искателей багов"""
        text = (
            "<emoji document_id=5283176512747507510>✨</emoji> <b>Hikkari Team</b>\n\n"
            "<blockquote>"
            "<b>Разработчики</b>\n"
            "• @Wers1xx — founder / core\n"
            "</blockquote>\n"
            "<blockquote>"
            "<b>Дизайнеры</b>\n"
            "• —\n"
            "</blockquote>\n"
            "<blockquote>"
            "<b>Искатели багов</b>\n"
            "• @minhthu\n"
            "</blockquote>\n\n"
            "<i>Based on Hikka · Heroku · built as Hikkari</i>"

        )
        await utils.answer(message, text)

    async def blacklist(self, message: Message):
        chatid = await self.blacklistcommon(message)
        chatid_str = str(chatid)

        if chatid_str.startswith("-100"):
            chatid = chatid_str[4:]

        self._db.set(
            main.__name__,
            "blacklist_chats",
            self._db.get(main.__name__, "blacklist_chats", []) + [chatid],
        )

        await utils.answer(message, self.strings["blacklisted"].format(chatid))

    @loader.command()
    async def unblacklist(self, message: Message):
        chatid = await self.blacklistcommon(message)
        chatid_str = str(chatid)

        if chatid_str.startswith("-100"):
            chatid = chatid_str[4:]

        self._db.set(
            main.__name__,
            "blacklist_chats",
            list(set(self._db.get(main.__name__, "blacklist_chats", [])) - {chatid}),
        )

        await utils.answer(message, self.strings["unblacklisted"].format(chatid))

    async def getuser(self, message: Message):
        try:
            return int(utils.get_args(message)[0])
        except (ValueError, IndexError):
            if reply := await message.get_reply_message():
                return reply.sender_id

            return message.to_id.user_id if message.is_private else False

    @loader.command()
    async def blacklistuser(self, message: Message):
        if not (user := await self.getuser(message)):
            await utils.answer(message, self.strings["who_to_blacklist"])
            return

        self._db.set(
            main.__name__,
            "blacklist_users",
            self._db.get(main.__name__, "blacklist_users", []) + [user],
        )

        await utils.answer(message, self.strings["user_blacklisted"].format(user))

    @loader.command()
    async def unblacklistuser(self, message: Message):
        if not (user := await self.getuser(message)):
            await utils.answer(message, self.strings["who_to_unblacklist"])
            return

        self._db.set(
            main.__name__,
            "blacklist_users",
            list(set(self._db.get(main.__name__, "blacklist_users", [])) - {user}),
        )

        await utils.answer(
            message,
            self.strings["user_unblacklisted"].format(user),
        )

    @loader.command()
    async def setprefix(self, message: Message):
        if not (args := utils.get_args(message)):
            await utils.answer(message, self.strings["what_prefix"])
            return

        if len(args[0]) != 1 and self.config.get("allow_nonstandart_prefixes") is False:
            await utils.answer(message, self.strings["prefix_incorrect"])
            return

        if args[0] == "s":
            await utils.answer(message, self.strings["prefix_incorrect"])
            return

        if len(args) == 2:
            if args[1].isdigit():
                args[1] = int(args[1])
            try:
                entity = await self.client.get_entity(args[1])
            except Exception:
                return await utils.answer(
                    message, self.strings["invalid_id_or_username"]
                )

            if not isinstance(entity, User):
                return await utils.answer(
                    message, self.strings["not_a_user"].format(args[1])
                )

            if entity.id != self.tg_id:
                sgroup_users = []
                for g in self._client.dispatcher.security._sgroups.values():
                    for u in g.users:
                        sgroup_users.append(u)

                tsec_users = [
                    rule["target"]
                    for rule in self._client.dispatcher.security._tsec_user
                ]
                ub_owners = self._client.dispatcher.security.owner.copy()

                all_users = sgroup_users + tsec_users + ub_owners

                if entity.id not in all_users:
                    return await utils.answer(
                        message, self.strings["id_not_found_scgroup"]
                    )

                oldprefix = utils.escape_html(self.get_prefix(entity.id))
                all_prefixes = self._db.get(
                    main.__name__,
                    "command_prefixes",
                    {},
                )

                all_prefixes[str(entity.id)] = args[0]

                self._db.set(
                    main.__name__,
                    "command_prefixes",
                    all_prefixes,
                )
                return await utils.answer(
                    message,
                    self.strings["entity_prefix_set"].format(
                        "<tg-emoji emoji-id=5197474765387864959>👍</tg-emoji>",
                        entity_name=utils.escape_html(entity.first_name),
                        newprefix=utils.escape_html(args[0]),
                        oldprefix=utils.escape_html(oldprefix),
                        entity_id=args[1],
                    ),
                )

        oldprefix = utils.escape_html(self.get_prefix())

        self._db.set(
            main.__name__,
            "command_prefix",
            args[0],
        )
        await utils.answer(
            message,
            self.strings["prefix_set"].format(
                "<tg-emoji emoji-id=5197474765387864959>👍</tg-emoji>",
                newprefix=utils.escape_html(args[0]),
                oldprefix=utils.escape_html(oldprefix),
            ),
        )

    @loader.command()
    async def aliases(self, message: Message):
        await utils.answer(
            message,
            self.strings["aliases"]
            + "<blockquote expandable>"
            + "\n".join(
                [
                    (self.config["alias_emoji"] + f" <code>{i}</code> &lt;- {y}")
                    for i, y in self.allmodules.aliases.items()
                ]
            )
            + "</blockquote>",
        )

    @loader.command()
    async def addalias(self, message: Message):

        args_raw = utils.get_args_raw(message)
        if not args_raw:
            await utils.answer(message, self.strings["alias_args"])
            return

        alias_lines = []
        for line in args_raw.splitlines():
            line = line.strip()
            if not line:
                continue

            if "," in line:
                parts = [part.strip() for part in line.split(",")]
                last = parts[-1].split(maxsplit=1)
                if len(last) < 2:
                    await utils.answer(message, self.strings["alias_args"])
                    return

                aliases = [part.lower() for part in parts[:-1] if part]
                aliases.append(last[0].lower())
                command = last[1]
            else:
                args = line.split(maxsplit=1)
                if len(args) < 2:
                    await utils.answer(message, self.strings["alias_args"])
                    return

                aliases = [args[0].lower()]
                command = args[1]

            command_parts = command.split(maxsplit=1)
            cmd = command_parts[0]
            rest = command_parts[1] if len(command_parts) > 1 else None

            if cmd not in self.allmodules.commands:
                await utils.answer(
                    message,
                    self.strings["no_command"].format(utils.escape_html(cmd)),
                )
                return

            alias_lines.append((aliases, cmd, rest))

        if not alias_lines:
            await utils.answer(message, self.strings["alias_args"])
            return

        added_lines = []
        skipped_lines = []
        planned_aliases = {}
        stored_aliases = {**self.get("aliases", {})}

        for aliases, cmd, rest in alias_lines:
            target = f"{cmd} {rest}" if rest else cmd
            added_aliases = []

            for alias in aliases:
                if alias in self.allmodules.aliases:
                    skipped_lines.append(
                        self.strings["alias_exists"].format(
                            alias=utils.escape_html(alias),
                            command=utils.escape_html(self.allmodules.aliases[alias]),
                        )
                    )
                    continue

                if alias in planned_aliases:
                    skipped_lines.append(
                        self.strings["alias_exists"].format(
                            alias=utils.escape_html(alias),
                            command=utils.escape_html(planned_aliases[alias]),
                        )
                    )
                    continue

                if not self.allmodules.add_alias(alias, cmd, rest):
                    await utils.answer(
                        message,
                        self.strings["no_command"].format(utils.escape_html(cmd)),
                    )
                    return

                stored_aliases[alias] = target
                planned_aliases[alias] = target
                added_aliases.append(alias)

            if added_aliases:
                added_lines.append((added_aliases, target))

        if added_lines:
            self.set("aliases", stored_aliases)

        if len(added_lines) == 1 and len(added_lines[0][0]) == 1 and not skipped_lines:
            await utils.answer(
                message,
                self.strings["alias_created"].format(
                    utils.escape_html(added_lines[0][0][0])
                ),
            )
            return

        added_count = sum(len(aliases) for aliases, _ in added_lines)
        response = []

        if added_lines:
            response.append(
                self.strings["aliases_created"].format(
                    count=added_count,
                    aliases="\n".join(
                        self.strings["aliases_created_line"].format(
                            aliases=utils.escape_html(", ".join(aliases)),
                            command=utils.escape_html(target),
                        )
                        for aliases, target in added_lines
                    ),
                )
            )

        response.extend(skipped_lines)

        await utils.answer(message, "\n\n".join(response))

    @loader.command()
    async def delalias(self, message: Message):
        args_raw = utils.get_args_raw(message)

        if not args_raw:
            await utils.answer(message, self.strings["delalias_args"])
            return

        if args_raw.strip() in {"-c", "--clear"}:
            self.allmodules.aliases.clear()
            self.set("aliases", {})
            await utils.answer(message, self.strings["aliases_cleared"])
            return

        aliases = []
        seen_aliases = set()
        for line in args_raw.splitlines():
            for alias in line.split(","):
                alias = alias.lower().strip()
                if alias and alias not in seen_aliases:
                    aliases.append(alias)
                    seen_aliases.add(alias)

        if not aliases:
            await utils.answer(message, self.strings["delalias_args"])
            return

        current = self.get("aliases", {})
        removed_aliases = []
        missed_aliases = []

        for alias in aliases:
            if not self.allmodules.remove_alias(alias):
                missed_aliases.append(alias)
                continue

            current.pop(alias, None)
            removed_aliases.append(alias)

        if removed_aliases:
            self.set("aliases", current)

        if len(removed_aliases) == 1 and not missed_aliases:
            await utils.answer(
                message,
                self.strings["alias_removed"].format(
                    utils.escape_html(removed_aliases[0])
                ),
            )
            return

        response = []
        if removed_aliases:
            response.append(
                self.strings["aliases_removed"].format(
                    count=len(removed_aliases),
                    aliases=utils.escape_html(", ".join(removed_aliases)),
                )
            )

        response.extend(
            self.strings["no_alias"].format(utils.escape_html(alias))
            for alias in missed_aliases
        )

        await utils.answer(
            message,
            "\n\n".join(response),
        )

    @loader.command()
    async def cleardb(self, message: Message):
        await self.inline.form(
            self.strings["confirm_cleardb"],
            message,
            reply_markup=[
                {
                    "text": self.strings["cleardb_confirm"],
                    "callback": self._inline__cleardb,
                },
                {
                    "text": self.strings["cancel"],
                    "action": "close",
                },
            ],
        )

    async def _inline__cleardb(self, call: InlineCall):
        self._db.clear()
        self._db.save()
        await utils.answer(call, self.strings["db_cleared"])

    @loader.command()
    async def togglecmdcmd(self, message: Message):
        """Toggle disable specific command of a module: togglecmd <module> <command> or togglecmd <command>"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, self.strings["wrong_usage_tcc"])

        if args and len(args) >= 2:
            mod_arg, cmd = args[0], args[1]
            mod_inst = self.allmodules.lookup(mod_arg)
            if not mod_inst:
                await utils.answer(message, self.strings["mod404"].format(mod_arg))

        module_key = mod_inst.__class__.__name__

        disabled_commands = self._db.get(main.__name__, "disabled_commands", {})
        current = [x for x in disabled_commands.get(module_key, [])]

        if cmd.lower() not in [c.lower() for c in mod_inst.hikkari_commands.keys()]:
            await utils.answer(message, self.strings["cmd404"])

        if any(c.lower() == cmd.lower() for c in current):
            current = [c for c in current if c.lower() != cmd.lower()]
            if current:
                disabled_commands[module_key] = current
            else:
                disabled_commands.pop(module_key, None)

            self._db.set(main.__name__, "disabled_commands", disabled_commands)
            try:
                self.allmodules.register_commands(mod_inst)
            except Exception:
                pass

            await utils.answer(
                message, self.strings["cmd_enabled"].format(cmd, module_key)
            )
        else:
            current.append(cmd)
            disabled_commands[module_key] = current
            self._db.set(main.__name__, "disabled_commands", disabled_commands)

            try:
                self.allmodules.commands.pop(cmd.lower(), None)
            except Exception:
                pass

            for alias, target in list(self.allmodules.aliases.items()):
                if target.split()[0].lower() == cmd.lower():
                    self.allmodules.aliases.pop(alias, None)

            await utils.answer(
                message, self.strings["cmd_disabled"].format(cmd, module_key)
            )

    @loader.command()
    async def togglemod(self, message: Message):
        """Toggle disable entire module: togglemod <module>"""
        args = utils.get_args(message)
        if not args:
            await utils.answer(message, self.strings["wrong_usage_tmc"])

        mod_arg = args[0]
        mod_inst = self.allmodules.lookup(mod_arg)
        if not mod_inst:
            await utils.answer(message, self.strings["mod404"].format(mod_arg))

        module_key = mod_inst.__class__.__name__
        disabled = self._db.get(main.__name__, "disabled_modules", [])

        if module_key in disabled:
            disabled = [m for m in disabled if m != module_key]
            self._db.set(main.__name__, "disabled_modules", disabled)
            try:
                self.allmodules.register_commands(mod_inst)
                self.allmodules.register_watchers(mod_inst)
                self.allmodules.register_raw_handlers(mod_inst)
                self.allmodules.register_inline_stuff(mod_inst)
            except Exception:
                pass
            await utils.answer(message, self.strings["mod_enabled"].format(module_key))
        else:
            disabled += [module_key]
            self._db.set(main.__name__, "disabled_modules", disabled)
            try:
                self.allmodules.unregister_commands(mod_inst, "disable")
                self.allmodules.unregister_watchers(mod_inst, "disable")
                self.allmodules.unregister_raw_handlers(mod_inst, "disable")
                self.allmodules.unregister_inline_stuff(mod_inst, "disable")
            except Exception:
                pass
            await utils.answer(message, self.strings["mod_disabled"].format(module_key))

    @loader.command()
    async def clearmodule(self, message: Message):
        """Clear all DB entries for module: clearmodule <module>"""
        args = utils.get_args(message)
        if not args:
            return await utils.answer(message, self.strings["wrong_usage_cmc"])

        mod_arg = args[0]
        mod_inst = self.allmodules.lookup(mod_arg)
        if mod_inst:
            module_key = mod_inst.__class__.__name__
        else:
            module_key = mod_arg

        if module_key in self._db:
            try:
                del self._db[module_key]
                self._db.save()
            except Exception:
                pass

        disabled_commands = self._db.get(main.__name__, "disabled_commands", {})
        disabled_commands.pop(module_key, None)
        self._db.set(main.__name__, "disabled_commands", disabled_commands)

        disabled_modules = self._db.get(main.__name__, "disabled_modules", [])
        if module_key in disabled_modules:
            disabled_modules = [m for m in disabled_modules if m != module_key]
            self._db.set(main.__name__, "disabled_modules", disabled_modules)

        await utils.answer(message, self.strings["cmc_done"].format(mod_arg))

    async def installationcmd(self, message: Message):
        """| Guide of installation"""

        args = utils.get_args_raw(message)

        if (
            not args or args not in {"-vds", "-wsl", "-ul", "-jh", "-hh", "-lh"}
        ) and not (
            await self.inline.form(
                self.strings["choose_installation"],
                message,
                reply_markup=self._markup(),
            )
        ):

            await self.client.send_file(
                message.peer_id,
                "",
                caption=self.strings["vds_install"],
                reply_to=getattr(message, "reply_to_msg_id", None),
            )
        match True:
            case _ if "-vds" in args:
                await utils.answer(message, self.strings["vds_install"])
            case _ if "-wsl" in args:
                await utils.answer(message, self.strings["wsl_install"])
            case _ if "-ul" in args:
                await utils.answer(message, self.strings["userland_install"])
            case _ if "-hh" in args:
                await utils.answer(message, self.strings["hikkahost_install"])

    async def _inline__choose__installation(self, call: InlineCall, platform: str):
        with contextlib.suppress(Exception):
            await utils.answer(
                call,
                self.strings[f"{platform}_install"],
                reply_markup=self._markup(),
            )

    @loader.command(alias="rh")
    async def richhelp(self, message):
        """Show Rich mode help (follows setlang)"""
        prefix = utils.escape_html(self.get_prefix())
        on = bool(self.config.get("rich_mode", True)) if hasattr(self, "config") else True
        status = self.strings["rich_status_on"] if on else self.strings["rich_status_off"]
        text = self.strings["richhelp"].format(status=status, prefix=prefix)
        await utils.answer(message, text)

    async def on_config_change(self, option=None, value=None):
        """Apply rich_mode immediately — no restart required."""
        try:
            enabled = bool(self.config.get("rich_mode"))
            me = getattr(getattr(self, "_client", None), "hikkari_me", None)
            if enabled and me is not None and not getattr(me, "premium", False):
                self.config["rich_mode"] = False
                enabled = False
                logger.warning(
                    "rich_mode disabled: Telegram Premium required for Rich Messages"
                )
            # Write both namespaces so can_use_rich() sees it without restart
            self._db.set("hikkari.rich", "enabled", enabled)
            self._db.set("Settings", "rich_mode", enabled)
            self._db.set(
                "hikkari.rich",
                "template",
                str(self.config.get("rich_template") or "{text}"),
            )
            # Persist config dict used by ModuleConfig
            try:
                conf = self._db.get(self.__class__.__name__, "config", {}) or {}
                if isinstance(conf, dict):
                    conf["rich_mode"] = enabled
                    self._db.set(self.__class__.__name__, "config", conf)
            except Exception:
                pass
            logger.info("rich_mode live → %s", enabled)
        except Exception:
            logger.debug("on_config_change rich_mode failed", exc_info=True)


    # ─── .ubproc — internal process / resource panel ─────────────────────────

    @loader.command(
        ru_doc="Панель внутренних процессов и ресурсов (RAM/CPU, задачи, модули)",
        en_doc="Internal processes & resource panel (RAM/CPU, tasks, modules)",
    )
    async def ubproc(self, message: Message):
        """Internal processes & resource panel (RAM/CPU, tasks, modules)."""
        text, buttons = self._ubproc_menu_payload()
        await self.inline.form(
            text,
            message=message,
            reply_markup=buttons,
            ttl=10 * 60,
        )

    def _ubproc_proc(self):
        try:
            import psutil
            return psutil.Process(os.getpid())
        except Exception:
            return None

    def _ubproc_fmt_bytes(self, n: float) -> str:
        try:
            n = float(n)
        except Exception:
            return "?"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(n) < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} PB"

    def _ubproc_snapshot(self) -> dict:
        """Collect process / modules / tasks snapshot."""
        data = {
            "pid": os.getpid(),
            "rss": 0,
            "vms": 0,
            "cpu": 0.0,
            "threads": 0,
            "open_files": 0,
            "conns": 0,
            "children": [],
            "thr_list": [],
            "tasks": [],
            "modules": [],
            "gc": {},
            "sys_mem": {},
        }
        proc = self._ubproc_proc()
        if proc is not None:
            try:
                with contextlib.suppress(Exception):
                    proc.cpu_percent(interval=None)  # prime
                mi = proc.memory_info()
                data["rss"] = getattr(mi, "rss", 0) or 0
                data["vms"] = getattr(mi, "vms", 0) or 0
                data["cpu"] = float(proc.cpu_percent(interval=0.15) or 0)
                data["threads"] = int(proc.num_threads() or 0)
                with contextlib.suppress(Exception):
                    data["open_files"] = len(proc.open_files() or [])
                with contextlib.suppress(Exception):
                    data["conns"] = len(proc.connections() or [])
                with contextlib.suppress(Exception):
                    for ch in proc.children(recursive=True):
                        try:
                            cmi = ch.memory_info()
                            data["children"].append(
                                {
                                    "pid": ch.pid,
                                    "name": ch.name(),
                                    "rss": getattr(cmi, "rss", 0) or 0,
                                    "cpu": float(ch.cpu_percent(interval=0.0) or 0),
                                    "status": ch.status(),
                                }
                            )
                        except Exception:
                            pass
            except Exception:
                pass

        # threads
        for th in threading.enumerate():
            data["thr_list"].append(
                {
                    "name": th.name,
                    "daemon": th.daemon,
                    "alive": th.is_alive(),
                    "ident": th.ident,
                }
            )

        # asyncio tasks
        try:
            loop = asyncio.get_event_loop()
            for task in asyncio.all_tasks(loop):
                name = task.get_name() if hasattr(task, "get_name") else repr(task)
                coro = ""
                with contextlib.suppress(Exception):
                    c = task.get_coro()
                    coro = getattr(c, "__qualname__", None) or getattr(c, "__name__", "") or str(c)[:80]
                data["tasks"].append(
                    {
                        "name": str(name)[:64],
                        "done": task.done(),
                        "cancelled": task.cancelled(),
                        "coro": str(coro)[:80],
                    }
                )
        except Exception:
            pass

        # modules rough size via sys.getsizeof of instance + source len
        for mod in list(getattr(self.allmodules, "modules", []) or []):
            try:
                cls = mod.__class__.__name__
                origin = str(getattr(mod, "__origin__", ""))[:40]
                src = getattr(mod, "__source__", "") or ""
                size = sys.getsizeof(mod)
                with contextlib.suppress(Exception):
                    size += len(src) if isinstance(src, str) else 0
                data["modules"].append(
                    {
                        "name": getattr(mod, "name", None) or cls,
                        "cls": cls,
                        "origin": origin,
                        "size": size,
                        "core": str(origin).startswith("<core"),
                    }
                )
            except Exception:
                pass
        data["modules"].sort(key=lambda x: x.get("size", 0), reverse=True)

        # gc
        with contextlib.suppress(Exception):
            data["gc"] = {
                "counts": gc.get_count(),
                "garbage": len(gc.garbage),
                "objects": len(gc.get_objects()),
            }

        # system mem
        try:
            import psutil
            vm = psutil.virtual_memory()
            data["sys_mem"] = {
                "total": vm.total,
                "available": vm.available,
                "percent": vm.percent,
                "used": vm.used,
            }
        except Exception:
            pass

        return data


    def _ubproc_menu_payload(self):
        snap = self._ubproc_snapshot()
        s = self.strings
        cpu_s = "{:.1f}%".format(snap["cpu"])
        text = "\n".join(
            [
                s["ubproc_title"],
                "",
                s["ubproc_pid"].format(snap["pid"]),
                s["ubproc_rss"].format(self._ubproc_fmt_bytes(snap["rss"])),
                s["ubproc_cpu"].format(cpu_s),
                s["ubproc_threads"].format(snap["threads"]),
                s["ubproc_tasks"].format(len(snap["tasks"])),
                s["ubproc_modules"].format(len(snap["modules"])),
                s["ubproc_children"].format(len(snap["children"])),
                "",
                s["ubproc_choose"],
            ]
        )
        buttons = [
            [{"text": s["ubproc_btn_global"], "callback": self._ubproc_cb, "args": ("global", 0)}],
            [
                {"text": s["ubproc_btn_threads"], "callback": self._ubproc_cb, "args": ("threads", 0)},
                {"text": s["ubproc_btn_tasks"], "callback": self._ubproc_cb, "args": ("tasks", 0)},
            ],
            [
                {"text": s["ubproc_btn_modules"], "callback": self._ubproc_cb, "args": ("modules", 0)},
                {"text": s["ubproc_btn_memory"], "callback": self._ubproc_cb, "args": ("memory", 0)},
            ],
            [
                {"text": s["ubproc_btn_children"], "callback": self._ubproc_cb, "args": ("children", 0)},
                {"text": s["ubproc_btn_gc"], "callback": self._ubproc_cb, "args": ("gc", 0)},
            ],
            [
                {"text": s["ubproc_btn_refresh"], "callback": self._ubproc_cb, "args": ("menu", 0)},
                {"text": s["ubproc_btn_close"], "action": "close"},
            ],
        ]
        return text, buttons

    def _ubproc_page(self, lines: list, page: int, per: int = 12):
        total = max(1, (len(lines) + per - 1) // per) if lines else 1
        page = max(0, min(page, total - 1))
        chunk = lines[page * per : (page + 1) * per]
        return chunk, page, total

    def _ubproc_section_text(self, section: str, page: int = 0):
        snap = self._ubproc_snapshot()
        s = self.strings

        if section == "menu":
            return self._ubproc_menu_payload()

        if section == "global":
            heavy_mod = snap["modules"][:5]
            lines = [
                f"{s['ubproc_global_title']}\n",
                s["ubproc_line_rss"].format(self._ubproc_fmt_bytes(snap["rss"])),
                s["ubproc_line_vms"].format(self._ubproc_fmt_bytes(snap["vms"])),
                s["ubproc_line_cpu"].format(f"{snap['cpu']:.1f}%"),
                s["ubproc_line_os_threads"].format(snap["threads"]),
                s["ubproc_line_py_threads"].format(len(snap["thr_list"])),
                s["ubproc_line_async"].format(
                    len(snap["tasks"]),
                    sum(1 for t in snap["tasks"] if not t.get("done")),
                ),
                s["ubproc_line_mods"].format(
                    len(snap["modules"]),
                    sum(1 for m in snap["modules"] if m.get("core")),
                    sum(1 for m in snap["modules"] if not m.get("core")),
                ),
                s["ubproc_line_child"].format(len(snap["children"])),
                s["ubproc_line_files"].format(snap["open_files"]),
                s["ubproc_line_conns"].format(snap["conns"]),
            ]
            if snap.get("sys_mem"):
                sm = snap["sys_mem"]
                lines.append(
                    s["ubproc_line_sysram"].format(
                        f"{sm.get('percent', 0):.0f}",
                        self._ubproc_fmt_bytes(sm.get("used", 0)),
                        self._ubproc_fmt_bytes(sm.get("total", 0)),
                    )
                )
            g = snap.get("gc") or {}
            if g:
                lines.append(
                    s["ubproc_line_gc"].format(
                        g.get("counts"), g.get("garbage", 0), g.get("objects", 0)
                    )
                )
            lines.append(f"\n{s['ubproc_top_mods']}")
            for m in heavy_mod:
                lines.append(
                    f"  · <code>{utils.escape_html(str(m['name'])[:32])}</code> "
                    f"— {self._ubproc_fmt_bytes(m['size'])}"
                )
            if snap["children"]:
                lines.append(f"\n{s['ubproc_top_children']}")
                for ch in sorted(snap["children"], key=lambda x: x["rss"], reverse=True)[:5]:
                    lines.append(
                        f"  · pid <code>{ch['pid']}</code> "
                        f"{utils.escape_html(ch['name'][:20])} "
                        f"{self._ubproc_fmt_bytes(ch['rss'])}"
                    )
            text = "\n".join(lines)
            buttons = [
                [{"text": s["ubproc_btn_refresh"], "callback": self._ubproc_cb, "args": ("global", 0)}],
                [
                    {"text": s["ubproc_btn_menu"], "callback": self._ubproc_cb, "args": ("menu", 0)},
                    {"text": s["ubproc_btn_close"], "action": "close"},
                ],
            ]
            return text, buttons

        if section == "threads":
            body = []
            for th in snap["thr_list"]:
                flag = "🟢" if th.get("alive") else "⚪"
                d = s["ubproc_daemon"] if th.get("daemon") else s["ubproc_main_thr"]
                body.append(
                    f"{flag} <code>{utils.escape_html(str(th.get('name', '?'))[:40])}</code> "
                    f"[{d}] id=<code>{th.get('ident')}</code>"
                )
            chunk, page, total = self._ubproc_page(body, page, per=15)
            text = (
                s["ubproc_sec_threads"].format(len(snap["thr_list"]))
                + "\n\n"
                + "\n".join(chunk)
                + f"\n\n{s['ubproc_page'].format(page + 1, total)}"
            )
            return text, self._ubproc_nav_buttons("threads", page, total)

        if section == "tasks":
            body = []
            for t in snap["tasks"]:
                stt = "✅" if t.get("done") else ("🚫" if t.get("cancelled") else "▶️")
                body.append(
                    f"{stt} <code>{utils.escape_html(str(t.get('name', ''))[:36])}</code>\n"
                    f"   <i>{utils.escape_html(str(t.get('coro', ''))[:60])}</i>"
                )
            chunk, page, total = self._ubproc_page(body, page, per=10)
            text = (
                s["ubproc_sec_tasks"].format(len(snap["tasks"]))
                + "\n\n"
                + "\n".join(chunk)
                + f"\n\n{s['ubproc_page'].format(page + 1, total)}"
            )
            return text, self._ubproc_nav_buttons("tasks", page, total)

        if section == "modules":
            body = []
            for m in snap["modules"]:
                tag = s["ubproc_core"] if m.get("core") else s["ubproc_ext"]
                body.append(
                    f"· <code>{utils.escape_html(str(m['name'])[:36])}</code> "
                    f"[{tag}] {self._ubproc_fmt_bytes(m['size'])}"
                )
            chunk, page, total = self._ubproc_page(body, page, per=15)
            text = (
                s["ubproc_sec_modules"].format(len(snap["modules"]))
                + "\n\n"
                + "\n".join(chunk)
                + f"\n\n{s['ubproc_page'].format(page + 1, total)}"
            )
            return text, self._ubproc_nav_buttons("modules", page, total)

        if section == "memory":
            cpu_s = "{:.1f}%".format(snap["cpu"])
            parts = [
                s["ubproc_sec_memory"],
                "",
                s["ubproc_mem_rss"].format(self._ubproc_fmt_bytes(snap["rss"])),
                s["ubproc_mem_vms"].format(self._ubproc_fmt_bytes(snap["vms"])),
                s["ubproc_mem_cpu"].format(cpu_s),
                s["ubproc_mem_files"].format(snap["open_files"]),
                s["ubproc_mem_conns"].format(snap["conns"]),
            ]
            if snap.get("sys_mem"):
                sm = snap["sys_mem"]
                parts.extend(
                    [
                        "",
                        s["ubproc_sys_title"],
                        s["ubproc_sys_used"].format(
                            self._ubproc_fmt_bytes(sm.get("used", 0)),
                            self._ubproc_fmt_bytes(sm.get("total", 0)),
                        ),
                        s["ubproc_sys_free"].format(
                            self._ubproc_fmt_bytes(sm.get("available", 0))
                        ),
                        s["ubproc_sys_load"].format(
                            "{:.1f}".format(sm.get("percent", 0))
                        ),
                    ]
                )
            text = "\n".join(parts)
            buttons = [
                [{"text": s["ubproc_btn_refresh"], "callback": self._ubproc_cb, "args": ("memory", 0)}],
                [
                    {"text": s["ubproc_btn_menu"], "callback": self._ubproc_cb, "args": ("menu", 0)},
                    {"text": s["ubproc_btn_close"], "action": "close"},
                ],
            ]
            return text, buttons

        if section == "children":
            body = []
            if not snap["children"]:
                body.append(s["ubproc_no_children"])
            for ch in sorted(snap["children"], key=lambda x: x["rss"], reverse=True):
                body.append(
                    f"· pid <code>{ch['pid']}</code> "
                    f"<code>{utils.escape_html(ch['name'][:24])}</code> "
                    f"RSS {self._ubproc_fmt_bytes(ch['rss'])} "
                    f"CPU {ch['cpu']:.1f}% [{ch['status']}]"
                )
            chunk, page, total = self._ubproc_page(body, page, per=12)
            text = (
                s["ubproc_sec_children"].format(len(snap["children"]))
                + "\n\n"
                + "\n".join(chunk)
                + f"\n\n{s['ubproc_page'].format(page + 1, total)}"
            )
            return text, self._ubproc_nav_buttons("children", page, total)

        if section == "gc":
            g = snap.get("gc") or {}
            text = (
                f"{s['ubproc_sec_gc']}\n\n"
                f"{s['ubproc_gc_counts'].format(g.get('counts'))}\n"
                f"{s['ubproc_gc_garbage'].format(g.get('garbage', 0))}\n"
                f"{s['ubproc_gc_objects'].format(g.get('objects', 0))}\n\n"
                f"{s['ubproc_gc_hint']}"
            )
            buttons = [
                [{"text": s["ubproc_btn_gc_run"], "callback": self._ubproc_cb, "args": ("gc_run", 0)}],
                [{"text": s["ubproc_btn_refresh"], "callback": self._ubproc_cb, "args": ("gc", 0)}],
                [
                    {"text": s["ubproc_btn_menu"], "callback": self._ubproc_cb, "args": ("menu", 0)},
                    {"text": s["ubproc_btn_close"], "action": "close"},
                ],
            ]
            return text, buttons

        if section == "gc_run":
            n = 0
            with contextlib.suppress(Exception):
                n = gc.collect()
            text = s["ubproc_gc_done"].format(n)
            buttons = [
                [{"text": s["ubproc_btn_gc_back"], "callback": self._ubproc_cb, "args": ("gc", 0)}],
                [{"text": s["ubproc_btn_menu"], "callback": self._ubproc_cb, "args": ("menu", 0)}],
            ]
            return text, buttons

        return self._ubproc_menu_payload()

    def _ubproc_nav_buttons(self, section: str, page: int, total: int):
        s = self.strings
        row = []
        if page > 0:
            row.append({"text": "◀️", "callback": self._ubproc_cb, "args": (section, page - 1)})
        row.append({"text": f"{page + 1}/{total}", "callback": self._ubproc_cb, "args": (section, page)})
        if page < total - 1:
            row.append({"text": "▶️", "callback": self._ubproc_cb, "args": (section, page + 1)})
        return [
            row,
            [
                {"text": s["ubproc_btn_refresh"], "callback": self._ubproc_cb, "args": (section, page)},
                {"text": s["ubproc_btn_menu"], "callback": self._ubproc_cb, "args": ("menu", 0)},
            ],
            [{"text": s["ubproc_btn_close"], "action": "close"}],
        ]

    async def _ubproc_cb(self, call: InlineCall, section: str = "menu", page: int = 0):
        try:
            page = int(page or 0)
        except Exception:
            page = 0
        text, buttons = self._ubproc_section_text(section, page)
        if len(text) > 4000:
            text = text[:3980] + "\n…"
        await call.edit(text, reply_markup=buttons)

