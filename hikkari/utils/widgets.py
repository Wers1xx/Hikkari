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
    """Native-looking interactive changelog widget (tabs, theme CSS vars).

    Must stay under 32KB HTML / ~4KB zlib. No external assets, no network.
    """

    def esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def items_json(key: str) -> str:
        arr = commits.get(key) or []
        return json.dumps(arr[:14], ensure_ascii=False)


    _lang = (lang or "ru").lower()
    _ru = _lang.startswith("ru")
    _labels = {
        "added": "Добавлено" if _ru else "Added",
        "changed": "Изменено" if _ru else "Changed",
        "fixed": "Исправлено" if _ru else "Fixed",
        "removed": "Удалено" if _ru else "Removed",
        "docs": "Документация" if _ru else "Docs",
        "other": "Прочее" if _ru else "Other",
    }
    _title = "Обновление Hikkari" if _ru else "Hikkari Update"
    _new = "НОВОЕ" if _ru else "NEW"
    _empty = "Нет записей в этой категории" if _ru else "No entries in this category"
    _cnt_suf = "записей · листай вкладки" if _ru else "items · swipe tabs"

    cur = esc((current or "")[:7])
    pend = esc((pending or "")[:7])
    br = esc(branch or "master")

    data = {
        "added": commits.get("added") or [],
        "changed": commits.get("changed") or [],
        "fixed": commits.get("fixed") or [],
        "removed": commits.get("removed") or [],
        "docs": commits.get("docs") or [],
        "other": commits.get("other") or [],
    }
    # trim for size
    for k in list(data.keys()):
        data[k] = [str(x)[:80] for x in data[k][:12]]

    payload = json.dumps(data, ensure_ascii=False)

    # Native palette via --tg-theme-*; interactive tabs via pure JS
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:transparent;color:var(--tg-theme-text-color,#111)}}
body{{font:13px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:10px 12px 18px}}
.h{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}}
.t{{font-weight:700;font-size:15px}}
.b{{font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;
background:var(--tg-theme-button-color,#2481cc);color:var(--tg-theme-button-text-color,#fff)}}
.m{{font-size:12px;color:var(--tg-theme-hint-color,#888);margin-bottom:8px}}
.m b{{color:var(--tg-theme-link-color,#2481cc);font-weight:600}}
.tabs{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}}
.tabs button{{font-size:12px;padding:5px 10px;border-radius:10px;border:0;
background:var(--tg-theme-secondary-bg-color,rgba(0,0,0,.06));
color:var(--tg-theme-text-color,#111)}}
.tabs button.on{{background:var(--tg-theme-button-color,#2481cc);
color:var(--tg-theme-button-text-color,#fff)}}
.list{{max-height:160px;overflow:auto;-webkit-overflow-scrolling:touch}}
.row{{display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--tg-theme-section-separator-color,rgba(0,0,0,.08))}}
.sha{{flex:0 0 auto;font:11px/1.4 ui-monospace,Menlo,Consolas,monospace;
color:var(--tg-theme-link-color,#2481cc)}}
.msg{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.empty{{color:var(--tg-theme-hint-color,#888);padding:12px 0;text-align:center}}
.cnt{{font-size:11px;color:var(--tg-theme-hint-color,#888);margin-top:6px}}
</style></head><body>
<div class="h"><div class="t">{_title}</div><div class="b">{_new}</div></div>
<div class="m"><b>{cur}</b> → <b>{pend}</b> · {br}</div>
<div class="tabs" id="tabs"></div>
<div class="list" id="list"></div>
<div class="cnt" id="cnt"></div>
<script>
var EMPTY="Нет записей";
var D={payload};
var order=[["added","{_labels["added"]}"],["changed","{_labels["changed"]}"],["fixed","{_labels["fixed"]}"],["removed","{_labels["removed"]}"],["docs","{_labels["docs"]}"],["other","{_labels["other"]}"]];
var cur="added";
function pick(){{
  for(var i=0;i<order.length;i++){{
    var k=order[i][0];
    if((D[k]||[]).length){{cur=k;return}}
  }}
  cur="other";
}}
function render(){{
  var tabs=document.getElementById("tabs");
  var list=document.getElementById("list");
  var cnt=document.getElementById("cnt");
  tabs.innerHTML="";
  for(var i=0;i<order.length;i++){{
    var k=order[i][0], label=order[i][1], n=(D[k]||[]).length;
    if(!n && k!==cur) continue;
    var b=document.createElement("button");
    b.textContent=label+(n?(" "+n):"");
    if(k===cur) b.className="on";
    b.onclick=(function(key){{return function(){{cur=key;render();
      try{{TelegramWidget.HapticFeedback.impactOccurred("light")}}catch(e){{}}
    }}}})(k);
    tabs.appendChild(b);
  }}
  var items=D[cur]||[];
  list.innerHTML="";
  if(!items.length){{
    list.innerHTML='<div class="empty">Нет записей в этой категории</div>';
  }} else {{
    for(var j=0;j<items.length;j++){{
      var s=String(items[j]);
      var sp=s.indexOf(" ");
      var sha=sp>0?s.slice(0,sp):s;
      var msg=sp>0?s.slice(sp+1):"";
      var row=document.createElement("div");
      row.className="row";
      row.innerHTML='<span class="sha">'+sha+'</span><span class="msg">'+msg+'</span>';
      list.appendChild(row);
    }}
  }}
  var total=0; for(var k in D) total+=(D[k]||[]).length;
  cnt.textContent=items.length+" / "+total+" коммитов · листай вкладки";
}}
pick(); render();
try{{TelegramWidget.ready()}}catch(e){{}}
</script>
</body></html>"""
    return html


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
    # 0 = automatic size (docs: omit or 0 for auto)
    payload["width"] = int(width) if width else 300
    payload["height"] = int(height) if height else 260
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
