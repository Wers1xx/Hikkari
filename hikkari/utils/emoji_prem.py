# ©️ Wers1xx, 2025-2026
# Premium emoji helpers for Hikkari
# Message body → HTML <emoji document_id=…>
# Buttons / reply_markup text → plain fallback (Bot API buttons can't parse HTML)

from __future__ import annotations

import re
from typing import Optional

# unicode (or alias) → (document_id, fallback_char)
PREMIUM_MAP: dict[str, tuple[int, str]] = {
    # success / error / warn
    "✅": (5256182535917940722, "⤵️"),
    "✔️": (5256182535917940722, "⤵️"),
    "✔": (5256182535917940722, "⤵️"),
    "❌": (5237898864433837164, "👎"),
    "✖": (5985346521103604145, "❌"),
    "×": (5985346521103604145, "❌"),
    "⚠": (5447644880824181073, "⚠️"),
    "⚠️": (5447644880824181073, "⚠️"),
    "🚫": (5240241223632954241, "🚫"),
    # status / wait
    "✨": (5283176512747507510, "✨"),
    "🔄": (5258200195589504369, "🔄"),
    "⏳": (5386367538735104399, "⌛"),
    "⌛": (5386367538735104399, "⌛"),
    "⏱": (5382194935057372936, "⏱"),
    "⏱️": (5382194935057372936, "⏱"),
    # nav / buttons
    "▶️": (5256039517801975973, "▶️"),
    "▶": (5256039517801975973, "▶️"),
    "◀️": (5255999157994297240, "◀️"),
    "◀": (5255999157994297240, "◀️"),
    "⬇️": (5406745015365943482, "⬇️"),
    "⬇": (5406745015365943482, "⬇️"),
    "🔻": (5406745015365943482, "⬇️"),
    # help / eval / logs
    "🛡": (5778423822940114949, "🛡"),
    "🛡️": (5778423822940114949, "🛡"),
    "💻": (5282843764451195532, "🖥"),
    "🖥": (5282843764451195532, "🖥"),
    "📦": (5256094480498436162, "📦"),
    "💡": (5422439311196834318, "💡"),
    "❓": (5436113877181941026, "❓"),
    # find / loader / config
    "🔍": (5348282577662778261, "🔍"),
    "📝": (5395730077814116850, "📝"),
    "🔗": (5271604874419647061, "🔗"),
    "📁": (5877332341331857066, "📁"),
    "📂": (6017174676898321263, "📂"),
    # help / inline
    "🤖": (5985780596268339498, "🤖"),
    "🧑": (5994521125298638350, "🧑‍🎄"),
    "👁": (5294271804842469571, "👁"),
    "👁️": (5294271804842469571, "👁"),
    "🛑": (5980953710157632545, "❌"),
    # misc
    "💬": (5891243564309942507, "💬"),
    "💫": (5294430452344434288, "😵‍💫"),
    "⭐": (5438496463044752972, "⭐️"),
    "⭐️": (5438496463044752972, "⭐️"),
    "⚡": (5456140674028019486, "⚡️"),
    "⚡️": (5456140674028019486, "⚡️"),
    "🔥": (5424972470023104089, "🔥"),
    "🚀": (5145427681680032825, "🚀"),
    "ℹ": (5334544901428229844, "ℹ️"),
    "ℹ️": (5334544901428229844, "ℹ️"),
    "☑": (5256182535917940722, "⤵️"),
    # platforms / info
    "🐧": (5361541227604878624, "🐧"),
    "🐳": (5431815452437257407, "🐳"),
    "🍏": (5935989710420709120, "🍎"),
    "🍎": (5935989710420709120, "🍎"),
    "🍊": (5242197817459494910, "🍊"),
    "🍇": (5346099823743346885, "🍇"),
    "🍀": (5794422138031055619, "🍀"),
    "💎": (5427168083074628963, "💎"),
    "🌼": (5370731117588523522, "🌼"),
    "🥟": (5381973718471828203, "😄"),
    "❄": (5449449325434266744, "❄️"),
    "❄️": (5449449325434266744, "❄️"),
    "🎓": (5296631769112525274, "🎩"),
}

# Longest keys first for replace
_SORTED_KEYS = sorted(PREMIUM_MAP.keys(), key=len, reverse=True)
_PATTERN = re.compile("|".join(re.escape(k) for k in _SORTED_KEYS))

# Already premium HTML / tg-emoji — leave alone
_ALREADY = re.compile(
    r"(?:<emoji\b[^>]*>.*?</emoji>|<tg-emoji\b[^>]*>.*?</tg-emoji>)",
    re.I | re.S,
)


def prem(char: str, fallback: Optional[str] = None) -> str:
    """Single premium emoji as HTML for message / caption body."""
    if char in PREMIUM_MAP:
        did, fb = PREMIUM_MAP[char]
        return f"<emoji document_id={did}>{fallback or fb}</emoji>"
    return fallback or char


def prem_btn(char: str) -> str:
    """Fallback unicode for inline/keyboard button text (no HTML)."""
    if char in PREMIUM_MAP:
        return PREMIUM_MAP[char][1]
    return char


def prem_text(text: str) -> str:
    """Replace bare mapped emoji in text with premium HTML. Skips existing tags."""
    if not text or not isinstance(text, str):
        return text

    parts: list[str] = []
    last = 0
    for m in _ALREADY.finditer(text):
        parts.append(_upgrade_chunk(text[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_upgrade_chunk(text[last:]))
    return "".join(parts)


def _upgrade_chunk(chunk: str) -> str:
    if not chunk:
        return chunk

    def repl(m: re.Match) -> str:
        ch = m.group(0)
        did, fb = PREMIUM_MAP[ch]
        return f"<emoji document_id={did}>{fb}</emoji>"

    return _PATTERN.sub(repl, chunk)


def prem_btn_text(text: str) -> str:
    """Strip to button-safe text: premium HTML → fallback, bare emoji → fallback."""
    if not text or not isinstance(text, str):
        return text

    def _tag_to_fb(m: re.Match) -> str:
        inner = m.group(1) or ""
        return inner

    t = re.sub(
        r"<emoji\b[^>]*>(.*?)</emoji>|<tg-emoji\b[^>]*>(.*?)</tg-emoji>",
        lambda m: m.group(1) if m.group(1) is not None else (m.group(2) or ""),
        text,
        flags=re.I | re.S,
    )

    def repl(m: re.Match) -> str:
        ch = m.group(0)
        return PREMIUM_MAP[ch][1] if ch in PREMIUM_MAP else ch

    return _PATTERN.sub(repl, t)


def button_icon_id(char: str) -> Optional[int]:
    """document_id for Bot API icon_custom_emoji_id if supported by the client stack."""
    if char in PREMIUM_MAP:
        return PREMIUM_MAP[char][0]
    return None
