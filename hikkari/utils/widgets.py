# Hikkari — Telegram Bot API 10.4 HTML widgets helpers
# Docs: https://core.telegram.org/bots/api-changelog#november-9-2026
#       https://core.telegram.org/bots/widgets

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

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


def split_commits(commits: list[Any], limit: int = 24) -> dict[str, list[str]]:
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
        display = msg
        for pref in (
            "feat:",
            "fix:",
            "chore:",
            "refactor:",
            "docs:",
            "perf:",
            "style:",
            "test:",
            "build:",
            "ci:",
            "revert:",
            "feat(",
            "fix(",
            "chore(",
            "refactor(",
        ):
            if display.lower().startswith(pref):
                if "(" in pref and ")" in display[:40]:
                    display = (
                        display.split("):", 1)[-1].strip()
                        if "):" in display
                        else display
                    )
                else:
                    display = display.split(":", 1)[-1].strip()
                break
        out[bucket].append(f"{sha} {display[:72]}")
    return out


def build_changelog_widget_html(
    *,
    current: str,
    pending: str,
    commits: dict[str, list[str]],
    branch: str = "master",
    lang: str = "ru",
) -> str:
    """Readable changelog widget. Simple HTML + light JS tabs. Under size limits."""

    def esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    _ru = (lang or "ru").lower().startswith("ru")
    labels = {
        "added": "Добавлено" if _ru else "Added",
        "changed": "Изменено" if _ru else "Changed",
        "fixed": "Исправлено" if _ru else "Fixed",
        "removed": "Удалено" if _ru else "Removed",
        "docs": "Документация" if _ru else "Docs",
        "other": "Прочее" if _ru else "Other",
    }
    title = "Обновление Hikkari" if _ru else "Hikkari Update"
    empty = "Пока пусто" if _ru else "Empty"
    hint = "Нажми вкладку, чтобы посмотреть изменения" if _ru else "Tap a tab to view changes"

    cur = esc((current or "")[:7])
    pend = esc((pending or "")[:7])
    br = esc(branch or "master")

    data: dict[str, list[str]] = {}
    for k in ("added", "changed", "fixed", "removed", "docs", "other"):
        data[k] = [str(x)[:90] for x in (commits.get(k) or [])[:15]]

    payload = json.dumps(data, ensure_ascii=False)
    labels_json = json.dumps(labels, ensure_ascii=False)

    # Compact, mobile-friendly, no overflow, explicit scroll
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:var(--tg-theme-bg-color,#1c1c1e);color:var(--tg-theme-text-color,#fff);
font:14px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif}}
body{{padding:12px;display:flex;flex-direction:column;gap:8px}}
.head{{display:flex;align-items:center;justify-content:space-between}}
.head h1{{font-size:16px;font-weight:700}}
.badge{{font-size:11px;font-weight:600;padding:3px 8px;border-radius:999px;
background:var(--tg-theme-button-color,#2aabee);color:var(--tg-theme-button-text-color,#fff)}}
.meta{{font-size:12px;color:var(--tg-theme-hint-color,#8e8e93)}}
.meta b{{color:var(--tg-theme-link-color,#2aabee)}}
.tabs{{display:flex;flex-wrap:wrap;gap:6px}}
.tabs button{{border:0;border-radius:10px;padding:6px 10px;font-size:12px;font-weight:600;
background:var(--tg-theme-secondary-bg-color,#2c2c2e);color:var(--tg-theme-text-color,#fff)}}
.tabs button.on{{background:var(--tg-theme-button-color,#2aabee);color:var(--tg-theme-button-text-color,#fff)}}
.list{{flex:1;overflow:auto;-webkit-overflow-scrolling:touch;min-height:120px;
border-radius:12px;background:var(--tg-theme-secondary-bg-color,#2c2c2e);padding:8px 10px}}
.row{{display:flex;gap:8px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.06);font-size:13px}}
.row:last-child{{border-bottom:0}}
.sha{{flex:0 0 auto;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;
color:var(--tg-theme-link-color,#2aabee)}}
.msg{{flex:1;word-break:break-word}}
.empty{{color:var(--tg-theme-hint-color,#8e8e93);text-align:center;padding:24px 8px}}
.foot{{font-size:11px;color:var(--tg-theme-hint-color,#8e8e93)}}
</style></head><body>
<div class="head"><h1>{title}</h1><span class="badge">NEW</span></div>
<div class="meta"><b>{cur}</b> → <b>{pend}</b> · {br}</div>
<div class="tabs" id="tabs"></div>
<div class="list" id="list"><div class="empty">{hint}</div></div>
<div class="foot" id="foot"></div>
<script>
var D={payload};
var L={labels_json};
var order=["added","changed","fixed","removed","docs","other"];
var cur="";
function first(){{
  for(var i=0;i<order.length;i++){{ if((D[order[i]]||[]).length){{cur=order[i];return}}}}
  cur="added";
}}
function render(){{
  var tabs=document.getElementById("tabs");
  var list=document.getElementById("list");
  var foot=document.getElementById("foot");
  tabs.innerHTML="";
  for(var i=0;i<order.length;i++){{
    var k=order[i], n=(D[k]||[]).length;
    if(!n) continue;
    var b=document.createElement("button");
    b.textContent=(L[k]||k)+" "+n;
    if(k===cur) b.className="on";
    b.onclick=(function(key){{return function(){{cur=key;render();}}}})(k);
    tabs.appendChild(b);
  }}
  var items=D[cur]||[];
  if(!items.length){{
    list.innerHTML='<div class="empty">{empty}</div>';
  }} else {{
    var html="";
    for(var j=0;j<items.length;j++){{
      var s=String(items[j]), sp=s.indexOf(" ");
      var sha=sp>0?s.slice(0,sp):s;
      var msg=sp>0?s.slice(sp+1):s;
      html+='<div class="row"><span class="sha">'+sha+'</span><span class="msg">'+msg+'</span></div>';
    }}
    list.innerHTML=html;
  }}
  var total=0; for(var k in D) total+=(D[k]||[]).length;
  foot.textContent=items.length+" / "+total;
}}
first(); render();
try{{TelegramWidget.ready()}}catch(e){{}}
</script>
</body></html>"""



async def send_widget(
    token: str,
    chat_id: int | str,
    html: str,
    *,
    caption: str | None = None,
    width: int = 0,
    height: int = 0,
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
    }
    # Prefer larger readable area; 0 = let client auto-size when supported
    if width and int(width) > 0:
        payload["width"] = int(width)
    else:
        payload["width"] = 360
    if height and int(height) > 0:
        payload["height"] = int(height)
    else:
        payload["height"] = 420
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
