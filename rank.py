from datetime import date
from pathlib import Path

from sources.base import Offer

WATCHLIST_FILE = Path(__file__).resolve().parent / "watchlist.txt"


def is_active(offer: Offer, today: date) -> bool:
    if offer.valid_from and offer.valid_from > today:
        return False
    if offer.valid_to and offer.valid_to < today:
        return False
    return True


def load_watchlist(path: Path | None = None) -> list[str]:
    path = path or WATCHLIST_FILE
    if not path.exists():
        return []
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            terms.append(line.lower())
    return terms


def _haystack(offer: Offer) -> str:
    return f"{offer.product} {offer.brand or ''}".lower()


def _discount_sort_key(offer: Offer):
    return (
        -(offer.discount_pct if offer.discount_pct is not None else -1.0),
        offer.price if offer.price is not None else float("inf"),
    )


def rank(offers: list[Offer], watchlist: list[str], top_n: int = 10,
         today: date | None = None) -> tuple[list[Offer], list[Offer]]:
    today = today or date.today()
    offers = [o for o in offers if is_active(o, today)]
    hits = []
    hit_ids = set()
    for offer in offers:
        hay = _haystack(offer)
        if any(term in hay for term in watchlist):
            hits.append(offer)
            hit_ids.add(id(offer))
    hits.sort(key=_discount_sort_key)

    rest = [o for o in offers if id(o) not in hit_ids]
    rest.sort(key=_discount_sort_key)
    return hits, rest[:top_n]
