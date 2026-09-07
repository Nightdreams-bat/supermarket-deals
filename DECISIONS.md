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
vault at `D:\V A U L T\Brain`. Daily Telegram message: watchlist hits + top-10 by
discount %, each line = product · store · deal price (was X) · "N days left".

## ADR-004 — Ranking
**Decision:** `watchlist.txt` (user's regular products) always flagged when discounted,
PLUS a daily "top 10 by discount %" fallback across everything else.

## ADR-005 — Daily runner
**Decision:** Local Python script, Windows Task Scheduler, ~08:00 daily. Runs only
when PC is on — acceptable.

## Telegram (setup complete 2026-09-07)
- Bot: "Linz Deals" (@lin_deals_bot)
- Token + chat ID (6622932923) → stored in `config.ini` (gitignored). Delivery tested OK.
