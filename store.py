import json
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from sources.base import Offer

DATA_DIR = Path(__file__).resolve().parent / "data"

# An offer with no valid_to is dropped once it has been in the rolling file for
# this many days, so undated offers can't accumulate forever.
UNDATED_MAX_AGE = timedelta(days=28)


def _serialize(offer: Offer, first_seen: date) -> dict:
    row = asdict(offer)
    for field in ("valid_from", "valid_to"):
        row[field] = row[field].isoformat() if row[field] else None
    row["first_seen"] = first_seen.isoformat()
    return row


def _deserialize(row: dict) -> tuple[Offer, date]:
    row = dict(row)
    first_seen = date.fromisoformat(row.pop("first_seen")) if row.get(
        "first_seen") else date.today()
    for field in ("valid_from", "valid_to"):
        row[field] = date.fromisoformat(row[field]) if row.get(field) else None
    return Offer(**row), first_seen


def load_rolling() -> list[tuple[Offer, date]]:
    path = DATA_DIR / "deals.json"
    if not path.exists():
        return []
    return [_deserialize(r) for r in json.loads(path.read_text(encoding="utf-8"))]


def dedupe(offers: list[Offer], today: date | None = None) -> list[Offer]:
    """Collapse duplicate offers and drop expired ones (no disk I/O)."""
    today = today or date.today()
    merged: dict[str, Offer] = {}
    for offer in offers:
        if offer.valid_to and offer.valid_to < today:
            continue
        merged[offer.key()] = offer
    return list(merged.values())


def save(offers: list[Offer], today: date | None = None) -> list[Offer]:
    today = today or date.today()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    merged: dict[str, tuple[Offer, date]] = {}
    for offer, first_seen in load_rolling():
        merged[offer.key()] = (offer, first_seen)
    for offer in offers:
        prev = merged.get(offer.key())
        merged[offer.key()] = (offer, prev[1] if prev else today)

    kept: dict[str, tuple[Offer, date]] = {}
    for key, (offer, first_seen) in merged.items():
        if offer.valid_to and offer.valid_to < today:
            continue
        if not offer.valid_to and today - first_seen > UNDATED_MAX_AGE:
            continue
        kept[key] = (offer, first_seen)

    (DATA_DIR / "deals.json").write_text(
        json.dumps([_serialize(o, fs) for o, fs in kept.values()],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    # Daily snapshot: the raw fetch, before dedupe/expiry, as an archive.
    (DATA_DIR / f"deals-{today.isoformat()}.json").write_text(
        json.dumps([_serialize(o, today) for o in offers],
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return [o for o, _ in kept.values()]
