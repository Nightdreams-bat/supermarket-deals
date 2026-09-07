"""Long-polling Telegram bot for the interactive per-store filter buttons.

Separate always-on process (see ADR-006). `run.py` sends the daily digest with an
inline keyboard and records the message reference in `data/last_digest.json`; this
bot answers button taps by re-ranking `data/deals.json` for the tapped store and
editing that message in place.

    python bot.py            # poll forever
    python bot.py --once     # process one batch of updates and exit (testing)
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import store
from notify import (FILTER_PREFIX, build_keyboard, edit_message,
                    render_view, resolve_filter_token, save_last_digest, send)
from rank import load_watchlist
from run import load_config

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAST_DIGEST_FILE = DATA_DIR / "last_digest.json"
OFFSET_FILE = DATA_DIR / "bot_offset.json"
API_URL = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT = 30
MAX_BACKOFF = 60


def _log(msg: str) -> None:
    print(f"[bot] {msg}", flush=True)


def _api(method: str, token: str, params: dict, timeout: int) -> dict:
    url = API_URL.format(token=token, method=method)
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _safe_api(method: str, token: str, params: dict) -> None:
    try:
        _api(method, token, params, 20)
    except Exception as exc:  # noqa: BLE001 - best effort (e.g. answerCallbackQuery)
        _log(f"{method} failed: {exc}")


# --- small on-disk state -----------------------------------------------------

def _read_offset() -> int | None:
    try:
        return json.loads(OFFSET_FILE.read_text(encoding="utf-8"))["offset"]
    except (OSError, ValueError, KeyError):
        return None


def _write_offset(offset: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def _read_last_digest() -> dict | None:
    try:
        return json.loads(LAST_DIGEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_offers() -> list:
    return [offer for offer, _ in store.load_rolling()]


# --- update handlers -------------------------------------------------------

def handle_callback(cb: dict, token: str) -> None:
    ack = {"callback_query_id": cb.get("id")}
    data = cb.get("data") or ""
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    if chat_id is None or message_id is None:  # fallback for a stale message ref
        last = _read_last_digest() or {}
        chat_id = chat_id or last.get("chat_id")
        message_id = message_id or last.get("message_id")

    slug = data[len(FILTER_PREFIX):] if data.startswith(FILTER_PREFIX) else ""
    label = resolve_filter_token(slug)
    known = slug == "all" or label is not None
    if not known or chat_id is None or message_id is None:
        _safe_api("answerCallbackQuery", token, ack)
        return

    text = render_view(_load_offers(), load_watchlist(), date.today(), label)
    keyboard = build_keyboard(active_token=None if slug == "all" else slug)
    resp = edit_message(text, token, chat_id, message_id, keyboard)
    if not resp.get("ok"):
        err = str(resp.get("description") or resp.get("error") or resp)
        if "not modified" not in err.lower():
            _log(f"editMessageText failed: {err}")
    _safe_api("answerCallbackQuery", token, ack)


def handle_message(m: dict, token: str) -> None:
    if not (m.get("text") or "").strip().startswith("/start"):
        return
    chat_id = (m.get("chat") or {}).get("id")
    if chat_id is None:
        return
    text = render_view(_load_offers(), load_watchlist(), date.today(), None)
    resp = send(text, token, str(chat_id), build_keyboard())
    result = resp.get("result") or {}
    if resp.get("ok") and result:
        save_last_digest(LAST_DIGEST_FILE,
                         (result.get("chat") or {}).get("id"),
                         result.get("message_id"))
    else:
        _log(f"/start reply failed: {resp}")


def process_updates(updates: list, token: str) -> None:
    for up in updates:
        try:
            if "callback_query" in up:
                handle_callback(up["callback_query"], token)
            elif "message" in up:
                handle_message(up["message"], token)
        except Exception as exc:  # noqa: BLE001 - one bad update must not kill the loop
            _log(f"update {up.get('update_id')} failed: {exc}")


# --- poll loop -------------------------------------------------------------

def _is_conflict(resp: dict) -> bool:
    return resp.get("error_code") == 409 or "conflict" in str(
        resp.get("description") or "").lower()


def run(once: bool = False) -> int:
    cfg = load_config(require_telegram=True)
    token = cfg["telegram"]["token"]
    offset = _read_offset()
    _log("single batch" if once else "polling started")
    backoff = 1
    while True:
        params = {"timeout": POLL_TIMEOUT}
        if offset is not None:
            params["offset"] = offset
        try:
            resp = _api("getUpdates", token, params, POLL_TIMEOUT + 15)
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                _log("409 conflict: another poller is running - exiting")
                return 1
            _log(f"getUpdates HTTP {exc.code}; retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue
        except Exception as exc:  # noqa: BLE001 - network flakiness, back off
            _log(f"getUpdates error: {exc}; retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)
            continue

        if not resp.get("ok"):
            if _is_conflict(resp):
                _log("409 conflict: another poller is running - exiting")
                return 1
            _log(f"getUpdates not ok: {resp}")
            if once:
                return 1
            time.sleep(5)
            continue

        backoff = 1
        updates = resp.get("result") or []
        if updates:
            process_updates(updates, token)
            offset = updates[-1]["update_id"] + 1
            _write_offset(offset)
        if once:
            _log(f"processed {len(updates)} update(s)")
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Telegram store-filter bot for the daily deals digest")
    parser.add_argument("--once", action="store_true",
                        help="process one batch of updates and exit")
    args = parser.parse_args()
    return run(once=args.once)


if __name__ == "__main__":
    sys.exit(main())
