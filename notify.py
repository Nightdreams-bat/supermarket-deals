import html
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import rank
from sources.base import Offer
from sources.marktguru import RETAILER_LABELS, RETAILERS

API_URL = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_MAX = 4096
MAX_WATCHLIST = 20

# callback_data prefix for the per-store filter buttons (Telegram caps the whole
# field at 64 bytes, so the token after the prefix is a short slug).
FILTER_PREFIX = "flt:"


def _identity(text: str) -> str:
    return text


def _plain_link(text: str, url: str | None) -> str:
    return text


def _html_link(text: str, url: str | None) -> str:
    if not url:
        return text
    return f'<a href="{html.escape(url, quote=True)}">{text}</a>'


def _md_link(text: str, url: str | None) -> str:
    if not url:
        return text
    return f"[{text}]({url})"


def _price(value: float | None) -> str | None:
    return f"€{value:.2f}" if value is not None else None


def _days_left(offer: Offer, today: date) -> str | None:
    if not offer.valid_to:
        return None
    delta = (offer.valid_to - today).days
    if delta < 0:
        return None
    if delta == 0:
        return "last day"
    return f"{delta} day{'s' if delta != 1 else ''} left"


def watchlist_line(offer: Offer, today: date, esc=_identity,
                   link=_plain_link) -> str:
    name = link(esc(offer.product), offer.url)
    parts = [f"{name} — {esc(offer.retailer)}"]
    price = _price(offer.price)
    if price:
        was = _price(offer.old_price)
        parts.append(f"{price} (was {was})" if was else price)
    days = _days_left(offer, today)
    if days:
        parts.append(days)
    return "• " + " · ".join(parts)


def discount_line(offer: Offer, today: date, esc=_identity,
                  link=_plain_link) -> str:
    name = link(esc(offer.product), offer.url)
    parts = [f"{name} — {esc(offer.retailer)}"]
    price = _price(offer.price)
    was = _price(offer.old_price)
    pct = f"−{offer.discount_pct:g}%" if offer.discount_pct is not None else None
    if price:
        extra = ", ".join(p for p in (f"was {was}" if was else None, pct) if p)
        parts.append(f"{price} ({extra})" if extra else price)
    elif pct:
        parts.append(pct)
    days = _days_left(offer, today)
    if days:
        parts.append(days)
    return "• " + " · ".join(parts)


def build_message(watchlist_hits: list[Offer], top_discounts: list[Offer],
                  today: date | None = None,
                  hots: list[Offer] | None = None) -> str:
    today = today or date.today()
    esc = html.escape
    link = _html_link
    hots = hots or []
    lines = [f"<b>🛒 Supermarket Deals — {today.isoformat()}</b>", ""]

    if hots:
        hot_ids = {id(o) for o in hots}
        top_discounts = [o for o in top_discounts if id(o) not in hot_ids]
        lines.append("<b>🔥 This week's hots</b>")
        lines += [discount_line(o, today, esc, link) for o in hots]
        lines.append("")

    if watchlist_hits:
        shown = watchlist_hits[:MAX_WATCHLIST]
        lines.append("<b>⭐ On your watchlist</b>")
        lines += [watchlist_line(o, today, esc, link) for o in shown]
        extra = len(watchlist_hits) - len(shown)
        if extra:
            lines.append(f"• …and {extra} more")
        lines.append("")

    lines.append("<b>🔥 Biggest discounts</b>")
    lines += [discount_line(o, today, esc, link) for o in top_discounts]

    dropped = False
    while len("\n".join(lines)) > TELEGRAM_MAX - 2 and len(lines) > 1:
        lines.pop()
        dropped = True
    message = "\n".join(lines).strip()
    if dropped:
        message += "\n…"
    return message


# --- interactive filter buttons ------------------------------------------------

def tracked_stores() -> list[tuple[str, str]]:
    """(slug, display label) for each DISTINCT tracked store, ordered by label.

    The spar/eurospar banner collision is folded into one "Spar/Eurospar" entry.
    The slug is the callback token used in ``FILTER_PREFIX + slug``.
    """
    seen: dict[str, str] = {}
    for unique in RETAILERS:
        label = RETAILER_LABELS.get(unique, unique.title())
        seen.setdefault(label.split("/")[0].lower(), label)
    return sorted(seen.items(), key=lambda kv: kv[1])


def resolve_filter_token(slug: str) -> str | None:
    """Slug -> store display label. ``None`` means "All" (or an unknown slug)."""
    if slug == "all":
        return None
    for token, label in tracked_stores():
        if token == slug:
            return label
    return None


def build_keyboard(active_token: str | None = None) -> dict:
    """Inline keyboard: one button per tracked store + "All", <=3 per row.

    ``active_token`` (a store slug, or ``None`` for the unfiltered view) gets a
    "• " marker so the current view is visible.
    """
    buttons = []
    for token, label in tracked_stores():
        text = f"• {label}" if token == active_token else label
        buttons.append({"text": text, "callback_data": FILTER_PREFIX + token})
    buttons.append({
        "text": "All" if active_token else "• All",
        "callback_data": FILTER_PREFIX + "all",
    })
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return {"inline_keyboard": rows}


def render_view(offers: list[Offer], watchlist: list[str], today: date,
                label: str | None = None) -> str:
    """Digest text for the full set (``label=None``) or one store's offers.

    Uses the SAME ranking as the daily digest so a filtered view is just a
    re-ranked slice.
    """
    pool = offers if label is None else [o for o in offers if o.retailer == label]
    hits, top = rank.rank(pool, watchlist, today=today)
    hot = rank.hots(pool, today=today)
    text = build_message(hits, top, today, hot)
    if label is not None:
        text = f"<b>Filtered: {html.escape(label)}</b>\n\n" + text
    return text


def save_last_digest(path, chat_id, message_id, day: date | None = None) -> None:
    """Persist the sent digest's message reference for later ``editMessageText``."""
    day = day or date.today()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "chat_id": chat_id,
        "message_id": message_id,
        "date": day.isoformat(),
    }), encoding="utf-8")


# --- telegram HTTP -----------------------------------------------------------

def _post(method: str, token: str, fields: dict) -> dict:
    payload = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        API_URL.format(token=token, method=method), data=payload)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except (ValueError, OSError):
            return {"ok": False, "error": f"HTTP {exc.code}"}
    except Exception as exc:  # URLError, timeout, non-JSON body
        return {"ok": False, "error": str(exc)}


def send(message: str, token: str, chat_id: str,
         reply_markup: dict | None = None) -> dict:
    """POST sendMessage. Returns the parsed Telegram response; on success the
    sent message is in ``resp["result"]`` (``message_id`` / ``chat``)."""
    fields = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if reply_markup is not None:
        fields["reply_markup"] = json.dumps(reply_markup)
    return _post("sendMessage", token, fields)


def edit_message(message: str, token: str, chat_id, message_id,
                 reply_markup: dict | None = None) -> dict:
    """POST editMessageText on an already-sent digest message."""
    fields = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if reply_markup is not None:
        fields["reply_markup"] = json.dumps(reply_markup)
    return _post("editMessageText", token, fields)
