# Supermarket Deals Tracker — Decisions (ask-build, 2026-09-07)

## ADR-001 — Location & stores
**Decision:** Linz, Austria (zip 4020). Track: **Norma, Spar/Eurospar, Lidl, Hofer**.
(Revised 2026-09-07: user's actual nearby stores. Billa/Penny dropped.)
- Post-review: added the `spar` banner alongside `eurospar` — marktguru splits the
  SPAR weekly Flugblatt across both banners (mostly disjoint products, same prices
  valid in a EUROSPAR store). Shown as one shop "Spar/Eurospar".
- **OPEN:** Interspar (separate hypermarket leaflet, ~530 offers) not tracked —
  awaiting user confirmation whether they shop the PlusCity/Wiener Straße store.

## ADR-002 — Promo data source  (REVISED ×2)
**Original:** scrape Aktionsfinder.at.
**Problem:** Aktionsfinder.at permanently shut down (maintenance notice, offline since May 2026).
**Decision:** Use **marktguru.at**'s JSON backend as the data source, behind a
pluggable `Source` interface so a per-chain leaflet fallback can be added later
without a rewrite.

**2026-09-07 revision (post-review):**
- Query one term per banner (`q=lidl` etc.) instead of a 90-keyword sweep — the
  banner name returns that banner's full offer set. Coverage went from ~45% to
  ~100% per store (Lidl 217→464, Hofer 86→194, Spar group 60→360). Keyword sweep
  kept only as a fallback for a banner that returns 0.
- Render path (`rank.py`) now drops offers that are expired OR not-yet-started
  (`valid_from > today`) — 40% of raw offers were future-dated leaflet previews.
- API: `https://api.marktguru.at/api/v1/offers/search`
- Auth: `x-apikey` / `x-clientkey` scraped from marktguru.at boot scripts at runtime, cached.
- Params: `as=web`, `q=<term>`, `zipCode=4020`, `limit`, `offset`, `allowedRetailers[]`.
- Retailer unique-names: `norma`, `eurospar` (verify), `lidl`, `hofer`. Confirmed on
  marktguru.at: /r/lidl, /r/norma, /r/hofer, /r/eurospar all exist.
- Fields per offer: product name, brand, price, unit price, `validityDates` (from/to),
  advertiser. Discount % computed if not present.
**Risk:** unofficial API; keys rotate (handled by re-scrape). Norma offers on marktguru
looked infrequently updated — accept.

## ADR-003 — Storage & notification
**Decision:** Deals stored as JSON (`data/deals-YYYY-MM-DD.json` + rolling `deals.json`,
deduped by retailer+product+valid-until). A dated section appended to the Obsidian
vault (note path set in `config.ini`). Daily Telegram message: watchlist hits + top-10 by
discount %, each line = product · store · deal price (was X) · "N days left".

## ADR-004 — Ranking
**Decision:** `watchlist.txt` (user's regular products) always flagged when discounted,
PLUS a daily "top 10 by discount %" fallback across everything else.

## ADR-005 — Daily runner
**Decision:** Local Python script, Windows Task Scheduler, ~08:00 daily. Runs only
when PC is on — acceptable.

## ADR-006 — Interactive Telegram store filter
**Status:** Accepted (2026-09-07)

**Context:** The daily digest mixes all four stores. The user wants to tap a
button to see just one store's deals, re-ranked, without a new message each time.
A webhook needs a public HTTPS URL; the daily pipeline runs only when the PC is on
and must not gain a dependency on a bot process.

**Decision:**
1. **Long-poll, not webhook.** `bot.py` loops `getUpdates` (~30s timeout, `offset`
   ack). No public URL, no TLS.
2. **Separate process.** `run.py`'s daily behavior is unchanged except it now
   attaches the inline keyboard to the digest send and writes
   `data/last_digest.json`. `run.py` never depends on `bot.py` being up.
3. **Re-render source = `data/deals.json`.** A button tap loads the rolling deals
   file, filters offers to the tapped retailer label, runs the SAME `rank()` /
   `hots()` the digest uses, and calls `editMessageText`. Deserialization reuses
   `store.load_rolling()` (no duplicated date parsing).
4. **State.** Stateless w.r.t. Telegram: `callback_data` = `flt:<slug>` (e.g.
   `flt:lidl`, `flt:all`), well under the 64-byte cap. The message to edit comes
   from `callback_query.message` primarily; `data/last_digest.json`
   (`{chat_id, message_id, date}`) is the fallback so a tap or `/start` after a
   restart still works. `bot.py` also persists its `offset` in
   `data/bot_offset.json`.
5. **Buttons.** One per DISTINCT display label in `RETAILER_LABELS` restricted to
   `RETAILERS` (Norma, Hofer, Lidl, Spar/Eurospar - the spar/eurospar collision
   folded to one), plus "All". <=3 buttons per row. The active view's button is
   prefixed with "• "; "All" is the unfiltered `build_message` output.
6. **Filtered view rendering.** Reuse `build_message` with the store's
   filtered `hits`/`top`/`hots`; same HTML/link formatting; a `<b>Filtered:
   Lidl</b>` header line. "All" recomputes from the full `deals.json` with the
   watchlist from `load_watchlist()`.
7. **Config / creds.** `bot.py` loads `config.ini` via `run.load_config`. The
   token is never logged. `getUpdates` errors back off (sleep, no crash-loop). A
   409 "conflict" (another poller) is logged clearly and exits non-zero.
8. **Encoding.** `bot.py` does the same `sys.stdout.reconfigure(encoding="utf-8")`
   guard as `run.py`.

**Consequences:** A second always-on process ("SupermarketDealsBot" task, at
logon, restarts 3x). Both processes are down while the PC is off - acceptable, as
with the daily task. Filter views reflect the last stored `deals.json`, not a live
fetch. Only one poller may run at a time (409 guard).

## Telegram (setup complete 2026-09-07)
- Bot: "Linz Deals" (@lin_deals_bot)
- Token + chat ID (6622932923) → stored in `config.ini` (gitignored). Delivery tested OK.
