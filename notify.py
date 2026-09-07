import html
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from sources.base import Offer

TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_MAX = 4096
MAX_WATCHLIST = 20


def _identity(text: str) -> str:
    return text


def _price(value: float | None) -> str | None:
    return f"€{value:.2f}" if value is not None else None


def _days_left(offer: Offer, today: date) -> str | None:
    if not offer.valid_to:
        return None
    delta = (offer.valid_to - today).days
    if delta <= 0:
        return "last day"
    return f"{delta} days left"


def watchlist_line(offer: Offer, today: date, esc=_identity) -> str:
    parts = [esc(f"{offer.product} — {offer.retailer}")]
    price = _price(offer.price)
    if price:
        was = _price(offer.old_price)
        parts.append(f"{price} (was {was})" if was else price)
    days = _days_left(offer, today)
    if days:
        parts.append(days)
    return "• " + " · ".join(parts)


def discount_line(offer: Offer, today: date, esc=_identity) -> str:
    parts = [esc(f"{offer.product} — {offer.retailer}")]
    price = _price(offer.price)
    if price:
        if offer.discount_pct is not None:
            parts.append(f"{price} (−{offer.discount_pct:g}%)")
        else:
            parts.append(price)
    elif offer.discount_pct is not None:
        parts.append(f"−{offer.discount_pct:g}%")
    days = _days_left(offer, today)
    if days:
        parts.append(days)
    return "• " + " · ".join(parts)


def build_message(watchlist_hits: list[Offer], top_discounts: list[Offer],
                  today: date | None = None) -> str:
    today = today or date.today()
    esc = html.escape
    lines = [f"<b>🛒 Supermarket Deals — {today.isoformat()}</b>", ""]

    if watchlist_hits:
        shown = watchlist_hits[:MAX_WATCHLIST]
        lines.append("<b>⭐ On your watchlist</b>")
        lines += [watchlist_line(o, today, esc) for o in shown]
        extra = len(watchlist_hits) - len(shown)
        if extra:
            lines.append(f"• …and {extra} more")
        lines.append("")

    lines.append("<b>🔥 Biggest discounts</b>")
    lines += [discount_line(o, today, esc) for o in top_discounts]

    message = "\n".join(lines).strip()
    if len(message) > TELEGRAM_MAX:
        message = message[:TELEGRAM_MAX - 1].rstrip() + "…"
    return message


def send(message: str, token: str, chat_id: str) -> dict:
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(TELEGRAM_URL.format(token=token), data=payload)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read())
