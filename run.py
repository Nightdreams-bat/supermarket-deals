import argparse
import configparser
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import store
import vault
from notify import build_keyboard, build_message, save_last_digest, send
from rank import hots, load_watchlist, rank
from sources.marktguru import MarktguruSource

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.ini"
LAST_DIGEST_FILE = ROOT / "data" / "last_digest.json"


def load_config(require_telegram: bool) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding="utf-8")
    if require_telegram:
        if not cfg.has_option("telegram", "token") or \
           not cfg.has_option("telegram", "chat_id"):
            raise SystemExit(
                f"config error: {CONFIG_FILE} needs a [telegram] section with "
                f"token and chat_id (copy config.example.ini)")
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
    cfg = load_config(require_telegram=not (args.dry_run or args.no_telegram))

    offers = fetch_all()
    counts = Counter(o.retailer for o in offers)
    print("\nper-retailer offer counts:")
    for retailer in sorted(counts):
        print(f"  {retailer}: {counts[retailer]}")

    if not offers:
        print("ERROR: all sources returned 0 offers", file=sys.stderr)
        return 1

    if args.dry_run:
        ranked = store.dedupe(offers, today)
    else:
        ranked = store.save(offers, today)
        print(f"\nstored {len(ranked)} live offers -> data/deals.json")

    watchlist = load_watchlist()
    hits, top = rank(ranked, watchlist, today=today)
    hot = hots(ranked, today=today)
    message = build_message(hits, top, today, hot)

    print("\n" + "=" * 60)
    print(message)
    print("=" * 60 + "\n")

    if args.dry_run:
        print("dry-run: nothing written or sent")
        return 0

    if not args.no_vault:
        path = vault.append(hits, top, today, hots=hot)
        print(f"vault updated: {path}")

    if not args.no_telegram:
        tg = cfg["telegram"]
        resp = send(message, tg["token"], tg["chat_id"], build_keyboard())
        print(f"telegram: ok={resp.get('ok')}")
        if not resp.get("ok"):
            print(f"telegram error: {resp}", file=sys.stderr)
            return 1
        result = resp.get("result") or {}
        save_last_digest(LAST_DIGEST_FILE,
                         (result.get("chat") or {}).get("id"),
                         result.get("message_id"), today)
        print(f"telegram: digest message_id={result.get('message_id')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
