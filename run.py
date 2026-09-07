import argparse
import configparser
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import store
import vault
from notify import build_message, send
from rank import load_watchlist, rank
from sources.marktguru import MarktguruSource

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.ini"


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg


def fetch_all() -> list:
    sources = [MarktguruSource(zip_code="4020")]
    offers = []
    for src in sources:
        print(f"fetching: {src.name}")
        offers.extend(src.fetch_offers())
    return offers


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily Linz supermarket deals")
    parser.add_argument("--dry-run", action="store_true",
                        help="print message + counts, write/send nothing")
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--no-vault", action="store_true")
    args = parser.parse_args()

    today = date.today()
    cfg = load_config()

    offers = fetch_all()
    counts = Counter(o.retailer for o in offers)
    print("\nper-retailer offer counts:")
    for retailer in ("Norma", "Eurospar", "Lidl", "Hofer"):
        print(f"  {retailer}: {counts.get(retailer, 0)}")

    if not offers:
        print("ERROR: all sources returned 0 offers", file=sys.stderr)
        return 1

    if args.dry_run:
        ranked = offers
    else:
        ranked = store.save(offers, today)
        print(f"\nstored {len(ranked)} live offers -> data/deals.json")

    watchlist = load_watchlist()
    hits, top = rank(ranked, watchlist)
    message = build_message(hits, top, today)

    print("\n" + "=" * 60)
    print(message)
    print("=" * 60 + "\n")

    if args.dry_run:
        print("dry-run: nothing written or sent")
        return 0

    if not args.no_vault:
        path = vault.append(hits, top, today)
        print(f"vault updated: {path}")

    if not args.no_telegram:
        tg = cfg["telegram"]
        resp = send(message, tg["token"], tg["chat_id"])
        print(f"telegram: ok={resp.get('ok')}")
        if not resp.get("ok"):
            print(f"telegram error: {resp}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
