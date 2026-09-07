import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from sources.base import Offer

DATA_DIR = Path(__file__).resolve().parent / "data"


def _serialize(offer: Offer) -> dict:
    row = asdict(offer)
    for field in ("valid_from", "valid_to"):
        row[field] = row[field].isoformat() if row[field] else None
    return row


def _deserialize(row: dict) -> Offer:
    row = dict(row)
    for field in ("valid_from", "valid_to"):
        row[field] = date.fromisoformat(row[field]) if row.get(field) else None
    return Offer(**row)


def load_rolling() -> list[Offer]:
    path = DATA_DIR / "deals.json"
    if not path.exists():
        return []
    return [_deserialize(r) for r in json.loads(path.read_text(encoding="utf-8"))]


def save(offers: list[Offer], today: date | None = None) -> list[Offer]:
    today = today or date.today()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    merged: dict[str, Offer] = {}
    for offer in load_rolling() + list(offers):
        if offer.valid_to and offer.valid_to < today:
            continue
        merged[offer.key()] = offer
    combined = list(merged.values())

    rows = [_serialize(o) for o in combined]
    (DATA_DIR / "deals.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA_DIR / f"deals-{today.isoformat()}.json").write_text(
        json.dumps([_serialize(o) for o in offers], ensure_ascii=False, indent=1),
        encoding="utf-8")
    return combined
