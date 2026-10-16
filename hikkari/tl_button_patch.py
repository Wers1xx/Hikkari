# ©️ Wers1xx — Hikkari
# Runtime patch: hikkaritl lacks KeyboardInlineButton (Heroku/herokutl LAYER 230).
# Without it, style.icon (premium emoji on buttons) is ignored by Telegram.
from __future__ import annotations

import logging
import struct
from typing import Optional

logger = logging.getLogger(__name__)
_applied = False


def apply_keyboard_inline_button_patch() -> bool:
    """Inject KeyboardInlineButton + patch Button.inline/url/switch_inline like herokutl."""
    global _applied
    if _applied:
        return True
    try:
        from hikkaritl.tl import types, alltlobjects
        from hikkaritl.tl.tlobject import TLObject
        from hikkaritl.tl.custom.button import Button
    except Exception:
        logger.exception("button patch: hikkaritl import failed")
        return False

    if getattr(types, "KeyboardInlineButton", None) is not None and getattr(
        types, "InlineButtonTypeCallback", None
    ) is not None:
        # types exist — still ensure Button uses them
        pass
    else:
        # Minimal TL constructors (from herokutl 2.2.0)
        class InlineButtonTypeCallback(TLObject):
            CONSTRUCTOR_ID = 0x2955BC38
            SUBCLASS_OF_ID = 0xBD13CCC4

            def __init__(self, data: bytes, requires_password: Optional[bool] = None):
                self.data = data
                self.requires_password = requires_password
                super().__init__()

            def to_dict(self):
                return {
                    "_": "InlineButtonTypeCallback",
                    "data": self.data,
                    "requires_password": self.requires_password,
                }

            def _bytes(self):
                self._assert_no_forbidden_constructors()
                return b"".join(
                    (
                        b"8\xbcU)",
                        struct.pack(
                            "<I",
                            (
                                0
                                if self.requires_password is None
                                or self.requires_password is False
                                else 1
                            ),
                        ),
                        self.serialize_bytes(self.data),
                    )
                )

            @classmethod
            def from_reader(cls, reader):
                flags = reader.read_int()
                _requires_password = bool(flags & 1)
                _data = reader.tgread_bytes()
                return cls(data=_data, requires_password=_requires_password)

        class InlineButtonTypeUrl(TLObject):
            CONSTRUCTOR_ID = 0xECA4F8D4
            SUBCLASS_OF_ID = 0xBD13CCC4

            def __init__(self, url: str):
                self.url = url
                super().__init__()

            def to_dict(self):
                return {"_": "InlineButtonTypeUrl", "url": self.url}

            def _bytes(self):
                self._assert_no_forbidden_constructors()
                return b"".join((b"\xd4\xf8\xa4\xec", self.serialize_bytes(self.url)))

            @classmethod
            def from_reader(cls, reader):
                return cls(url=reader.tgread_string())

        class InlineButtonTypeSwitchInline(TLObject):
            CONSTRUCTOR_ID = 0x93773FF5
            SUBCLASS_OF_ID = 0xBD13CCC4

            def __init__(
                self,
                query: str,
                same_peer: Optional[bool] = None,
                peer_types: Optional[list] = None,
            ):
                self.query = query
                self.same_peer = same_peer
                self.peer_types = peer_types
                super().__init__()

            def to_dict(self):
                return {
                    "_": "InlineButtonTypeSwitchInline",
                    "query": self.query,
                    "same_peer": self.same_peer,
                    "peer_types": []
                    if self.peer_types is None
                    else [
                        x.to_dict() if isinstance(x, TLObject) else x
                        for x in self.peer_types
                    ],
                }

            def _bytes(self):
                self._assert_no_forbidden_constructors()
                return b"".join(
                    (
                        b"\xf5?w\x93",
                        struct.pack(
                            "<I",
                            (
                                0
                                if self.same_peer is None or self.same_peer is False
                                else 1
                            )
                            | (
                                0
                                if self.peer_types is None or self.peer_types is False
                                else 2
                            ),
                        ),
                        self.serialize_bytes(self.query),
                        b""
                        if self.peer_types is None or self.peer_types is False
                        else b"".join(
                            (
                                b"\x15\xc4\xb5\x1c",
                                struct.pack("<i", len(self.peer_types)),
                                b"".join(x._bytes() for x in self.peer_types),
                            )
                        ),
                    )
                )

            @classmethod
            def from_reader(cls, reader):
                flags = reader.read_int()
                _same_peer = bool(flags & 1)
                _query = reader.tgread_string()
                if flags & 2:
                    reader.read_int()
                    _peer_types = [
                        reader.tgread_object() for _ in range(reader.read_int())
                    ]
                else:
                    _peer_types = None
                return cls(
                    query=_query, same_peer=_same_peer, peer_types=_peer_types
                )

        class KeyboardInlineButton(TLObject):
            CONSTRUCTOR_ID = 0x11C1A322
            SUBCLASS_OF_ID = 0x463A75A2

            def __init__(self, text: str, type, style=None):
                self.text = text
                self.type = type
                self.style = style
                super().__init__()

            def to_dict(self):
                return {
                    "_": "KeyboardInlineButton",
                    "text": self.text,
                    "type": self.type.to_dict()
                    if isinstance(self.type, TLObject)
                    else self.type,
                    "style": self.style.to_dict()
                    if isinstance(self.style, TLObject)
                    else self.style,
                }

            def _bytes(self):
                self._assert_no_forbidden_constructors()
                return b"".join(
                    (
                        b'"\xa3\xc1\x11',
                        struct.pack(
                            "<I",
                            0
                            if self.style is None or self.style is False
                            else 1024,
                        ),
                        b""
                        if self.style is None or self.style is False
                        else self.style._bytes(),
                        self.serialize_bytes(self.text),
                        self.type._bytes(),
                    )
                )

            @classmethod
            def from_reader(cls, reader):
                flags = reader.read_int()
                _style = reader.tgread_object() if flags & 1024 else None
                _text = reader.tgread_string()
                _type = reader.tgread_object()
                return cls(text=_text, type=_type, style=_style)

        types.InlineButtonTypeCallback = InlineButtonTypeCallback
        types.InlineButtonTypeUrl = InlineButtonTypeUrl
        types.InlineButtonTypeSwitchInline = InlineButtonTypeSwitchInline
        types.KeyboardInlineButton = KeyboardInlineButton

        # Register for deserialization
        tl = getattr(alltlobjects, "tlobjects", None) or getattr(
            alltlobjects, "LAYER", None
        )
        mapping = None
        for attr in ("tlobjects", "tl_objects", "objs"):
            if hasattr(alltlobjects, attr) and isinstance(
                getattr(alltlobjects, attr), dict
            ):
                mapping = getattr(alltlobjects, attr)
                break
        if mapping is None:
            # scan module for the big dict
            for name, val in vars(alltlobjects).items():
                if isinstance(val, dict) and 0x4FDD3430 in val:
                    mapping = val
                    break
        if mapping is not None:
            mapping[0x11C1A322] = types.KeyboardInlineButton
            mapping[0x2955BC38] = types.InlineButtonTypeCallback
            mapping[0xECA4F8D4] = types.InlineButtonTypeUrl
            mapping[0x93773FF5] = types.InlineButtonTypeSwitchInline

        # Prefer higher layer when negotiating (icons need recent layers)
        if hasattr(alltlobjects, "LAYER") and alltlobjects.LAYER < 230:
            alltlobjects.LAYER = 230

    def _icon_int(icon):
        if icon is None:
            return None
        try:
            return int(str(icon).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def inline(text, data=None, style=None, icon=None):
        if not data:
            data = text.encode("utf-8")
        elif not isinstance(data, (bytes, bytearray, memoryview)):
            data = str(data).encode("utf-8")
        if len(data) > 64:
            raise ValueError("Too many bytes for the data")
        icon = _icon_int(icon)
        return types.KeyboardInlineButton(
            text,
            types.InlineButtonTypeCallback(data),
            style=Button._get_style(style, icon),
        )

    @staticmethod
    def url(text, url=None, style=None, icon=None):
        if url is None:
            url = text
        icon = _icon_int(icon)
        return types.KeyboardInlineButton(
            text,
            types.InlineButtonTypeUrl(url),
            style=Button._get_style(style, icon),
        )

    @staticmethod
    def switch_inline(text, query="", same_peer=False, style=None, icon=None):
        icon = _icon_int(icon)
        return types.KeyboardInlineButton(
            text,
            types.InlineButtonTypeSwitchInline(query, same_peer=same_peer),
            style=Button._get_style(style, icon),
        )

    Button.inline = inline
    Button.url = url
    Button.switch_inline = switch_inline
    _applied = True
    logger.info(
        "Applied KeyboardInlineButton patch (premium button icons, Heroku-compatible)"
    )
    return True
