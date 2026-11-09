# Hikkari — Telegram Bot API 10.4 HTML widgets helpers
# Docs: https://core.telegram.org/bots/api-changelog#november-9-2026
#       https://core.telegram.org/bots/widgets

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

# Production: widgets only in private chats; protected content auto-applied
BOT_API = "https://api.telegram.org"


def _api_url(token: str, method: str) -> str:
    return f"{BOT_API}/bot{token}/{method}"


def classify_commit(msg: str) -> str:
    m = (msg or "").strip().lower()
    if m.startswith(("feat", "add", "new")):
        return "added"
    if m.startswith(("fix", "bug", "hotfix", "patch")):
        return "fixed"
    if m.startswith(("refactor", "chore", "style", "perf", "opt")):
        return "changed"
    if m.startswith(("remove", "del", "drop", "deprecate")):
        return "removed"
    if m.startswith(("docs", "doc")):
        return "docs"
    return "other"


def split_commits(commits: list[Any], limit: int = 20) -> dict[str, list[str]]:
    out = {
        "added": [],
        "fixed": [],
        "changed": [],
        "removed": [],
        "docs": [],
        "other": [],
    }
    for c in commits[:limit]:
        try:
            msg = c.message.split("\n", 1)[0].strip()
            sha = c.hexsha[:7]
        except Exception:
            continue
        if not msg:
            continue
        bucket = classify_commit(msg)
        # strip conventional prefix for display
        display = msg
        for pref in (
            "feat:", "fix:", "chore:", "refactor:", "docs:", "perf:",
            "style:", "test:", "build:", "ci:", "revert:",
            "feat(", "fix(", "chore(", "refactor(",
        ):
            if display.lower().startswith(pref):
                # drop type until ): or :
                if "(" in pref and ")" in display[:40]:
                    display = display.split("):", 1)[-1].strip() if "):" in display else display
                else:
                    display = display.split(":", 1)[-1].strip()
                break
        out[bucket].append(f"{sha} {display[:80]}")
    return out


def build_changelog_widget_html(
    *,
    current: str,
    pending: str,
    commits: dict[str, list[str]],
    branch: str = "master",
) -> str:
    """Self-contained HTML for sendWidget (≤32KB). No external assets."""

    def esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def section(title: str, color: str, items: list[str]) -> str:
        if not items:
            return ""
        rows = "".join(
            f'<div class="row"><span class="sha">{esc(i.split(" ",1)[0])}</span>'
            f'<span class="msg">{esc(i.split(" ",1)[-1] if " " in i else i)}</span></div>'
            for i in items[:12]
        )
        return (
            f'<div class="sec">'
            f'<div class="htag" style="color:{color}">{esc(title)} · {len(items)}</div>'
            f"{rows}</div>"
        )

    body = ""
    body += section("✨ Added", "#3dd68c", commits.get("added") or [])
    body += section("🔧 Changed", "#6cb6ff", commits.get("changed") or [])
    body += section("🐛 Fixed", "#ff7b72", commits.get("fixed") or [])
    body += section("🗑 Removed", "#ffa657", commits.get("removed") or [])
    body += section("📝 Docs", "#d2a8ff", commits.get("docs") or [])
    body += section("• Other", "#8b949e", commits.get("other") or [])
    if not body:
        body = '<div class="empty">No detailed commits — open GitHub compare.</div>'

    cur = esc((current or "")[:7])
    pend = esc((pending or "")[:7])
    br = esc(branch or "master")

    # Keep HTML compact for 4KB compressed limit
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font:13px/1.35 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;
color:#e6edf3;background:linear-gradient(160deg,#0d1117 0%,#161b22 100%);
padding:10px 12px;width:100%;height:100%}}
.head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.title{{font-weight:700;font-size:15px;letter-spacing:.2px}}
.badge{{background:#238636;color:#fff;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:600}}
.meta{{color:#8b949e;font-size:11px;margin-bottom:10px}}
.meta b{{color:#58a6ff}}
.sec{{margin-bottom:8px}}
.htag{{font-weight:600;font-size:12px;margin-bottom:4px}}
.row{{display:flex;gap:6px;padding:3px 0;border-bottom:1px solid #21262d}}
.sha{{color:#58a6ff;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;flex:0 0 auto}}
.msg{{color:#c9d1d9;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.empty{{color:#8b949e;font-size:12px;padding:8px 0}}
.foot{{margin-top:8px;font-size:10px;color:#484f58;text-align:center}}
</style></head><body>
<div class="head"><div class="title">Hikkari Update</div><div class="badge">NEW</div></div>
<div class="meta"><b>{cur}</b> → <b>{pend}</b> · {br}</div>
{body}
<div class="foot">Bot API 10.4 widget · tap Update below</div>
</body></html>"""
    return html


async def send_widget(
    token: str,
    chat_id: int | str,
    html: str,
    *,
    caption: str | None = None,
    width: int = 360,
    height: int = 420,
    public_data: str | None = None,
    chat_data: str | None = None,
    allow_queries: bool = False,
    is_shared: bool = False,
    reply_markup: dict | None = None,
    parse_mode: str | None = "HTML",
    disable_notification: bool = False,
) -> Optional[dict]:
    """Bot API sendWidget. Returns message dict or None on failure."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "html": html,
        "width": int(width),
        "height": int(height),
    }
    if caption:
        payload["caption"] = caption[:1024]
        if parse_mode:
            payload["parse_mode"] = parse_mode
    if public_data is not None:
        payload["public_data"] = public_data[:1024]
    if chat_data is not None:
        payload["chat_data"] = chat_data[:1024]
    if allow_queries:
        payload["allow_queries"] = True
    if is_shared:
        payload["is_shared"] = True
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if disable_notification:
        payload["disable_notification"] = True

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _api_url(token, "sendWidget"),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                data = await resp.json(content_type=None)
                if not data.get("ok"):
                    logger.warning(
                        "sendWidget failed: %s",
                        data.get("description") or data,
                    )
                    return None
                return data.get("result")
    except Exception:
        logger.exception("sendWidget request error")
        return None


async def edit_message_widget_data(
    token: str,
    *,
    chat_id: int | str | None = None,
    message_id: int | None = None,
    inline_message_id: str | None = None,
    public_data: str | None = None,
    chat_data: str | None = None,
) -> bool:
    payload: dict[str, Any] = {}
    if inline_message_id:
        payload["inline_message_id"] = inline_message_id
    else:
        payload["chat_id"] = chat_id
        payload["message_id"] = message_id
    if public_data is not None:
        payload["public_data"] = public_data[:1024]
    if chat_data is not None:
        payload["chat_data"] = chat_data[:1024]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _api_url(token, "editMessageWidgetData"),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json(content_type=None)
                return bool(data.get("ok"))
    except Exception:
        logger.debug("editMessageWidgetData failed", exc_info=True)
        return False
