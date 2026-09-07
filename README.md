# Supermarket Deals (Linz)

Scrapes daily supermarket promotions for Linz, Austria (zip 4020) from
marktguru.at, stores them as JSON, appends a dated section to an Obsidian vault
note, and sends a daily Telegram digest with the best prices and how many days
each deal still has left.

Tracked stores: **Norma, Spar/Eurospar, Lidl, Hofer**. (Interspar is a separate
hypermarket leaflet — not tracked; add `"interspar"` to `RETAILERS` if you shop
the PlusCity / Wiener Straße store.)

## How it works

1. `sources/marktguru.py` scrapes the marktguru.at API keys from the homepage,
   runs one `offers/search` query per tracked banner (the banner name is itself
   a valid query returning that banner's full offer set), dedupes by offer id,
   filters to the tracked banners client-side, and normalizes each hit to an
   `Offer`. Falls back to a keyword sweep only for a banner that returns nothing.
2. `store.py` writes a rolling `data/deals.json` (deduped by
   `retailer|product|valid_to`; expired offers dropped, undated offers aged out
   after 28 days) plus a raw daily snapshot `data/deals-<date>.json`.
3. `rank.py` drops offers that are expired or not yet started, matches the rest
   against `watchlist.txt`, and picks the top 10 by discount for everything else.
4. `notify.py` sends the Telegram message; `vault.py` appends the same content
   to the vault note.
5. `run.py` orchestrates all of the above.

## One-time setup

```powershell
pip install -r requirements.txt   # no third-party deps, just a no-op check
copy config.example.ini config.ini   # then fill in the real bot token + chat id
notepad watchlist.txt                 # add your regular products (see file header)
powershell -ExecutionPolicy Bypass -File install-task.ps1
```

`config.ini` and `.keys.json` are gitignored. Never commit them.

## Running manually

```powershell
python run.py --dry-run     # print message + per-retailer counts, write/send nothing
python run.py               # full run: store + vault + Telegram
python run.py --no-telegram # store + vault only
python run.py --no-vault    # store + Telegram only
```

Exit code is non-zero on hard failure (all sources returned 0 offers, or the
Telegram API rejected the message).

## Changing stores or zip code

- Zip: edit the `zip_code="4020"` argument in `run.py` (`fetch_all`).
- Stores: edit `RETAILERS` / `RETAILER_LABELS` in `sources/marktguru.py`. Use the
  marktguru advertiser `uniqueName` (e.g. `lidl`, `hofer`, `norma`, `eurospar`,
  `spar`, `interspar`, `penny`, `billa`, `billa-plus`).

## The vault note

`D:\V A U L T\Brain\Deals\supermarket-deals.md` — the folder and file are created
on first run. Re-running on the same day replaces that day's section instead of
duplicating it.

## Troubleshooting

- **Key scrape fails** (`could not locate API keys on marktguru.at`): the
  homepage layout changed. Delete `.keys.json`, open
  <https://www.marktguru.at/> source, search for `"apiKey"` / `"clientKey"` in
  the inline `application/json` config block, and adjust the regex in
  `sources/marktguru.py::_scrape_keys`. The app auto-re-scrapes on HTTP 401/403.
- **0 offers**: usually a transient network problem to `api.marktguru.at`
  (per-banner failures are tolerated and printed, then a keyword fallback runs).
  Re-run. If it persists, check the API is reachable and delete `.keys.json`.
- **Telegram 400**: bad token/chat id in `config.ini`, or HTML in a product name
  broke `parse_mode=HTML`. Check the printed `telegram error:` payload.
- The scheduled task only runs while the PC is on and awake (task is set to
  start as soon as possible if a run was missed).

## marktguru.at API notes

See the top of `sources/marktguru.py`. Endpoint:
`GET https://api.marktguru.at/api/v1/offers/search?as=web&q=<term>&zipCode=4020&limit=1000&offset=0`
with headers `X-ApiKey` / `X-ClientKey`. `q` is mandatory (empty / `*` / single
letters return nothing) but the banner name itself (`q=lidl`) is a valid query
that returns that banner's entire offer set, so we query one term per banner.
`allowedRetailers` is ignored by the backend, so retailers are still filtered
client-side on `advertisers[].uniqueName`.
