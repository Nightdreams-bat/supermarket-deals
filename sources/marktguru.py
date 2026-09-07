import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

from .base import Offer, Source

HOMEPAGE = "https://www.marktguru.at/"
SEARCH_URL = "https://api.marktguru.at/api/v1/offers/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
KEYS_FILE = Path(__file__).resolve().parent.parent / ".keys.json"

# The API is search-only (an empty or single-letter q returns nothing), but the
# banner name itself is a valid query that returns that banner's entire offer
# set in one paginated call (filters.retailers confirms the count). We query one
# term per tracked banner and still filter client-side on advertiser uniqueName,
# because a text query for "lidl" also text-matches the odd "penny"/"dm" row.
# allowedRetailers is ignored by the backend, hence the client-side filter.
FALLBACK_KEYWORDS = [
    "milch", "butter", "kaffee", "brot", "kaese", "wurst", "huhn", "apfel",
    "kartoffel", "nudeln", "reis", "mehl", "oel", "schokolade", "bier", "wasser",
    "waschmittel", "toilettenpapier", "shampoo", "windel",
]

# uniqueName -> display label. SPAR splits its weekly Flugblatt across the "spar"
# and "eurospar" banners (mostly disjoint products, same in-store prices), so
# both are tracked and shown as one shop.
RETAILER_LABELS = {
    "norma": "Norma",
    "hofer": "Hofer",
    "lidl": "Lidl",
    "spar": "Spar/Eurospar",
    "eurospar": "Spar/Eurospar",
    "interspar": "Interspar",
}
RETAILERS = {"norma", "hofer", "lidl", "spar", "eurospar"}


class MarktguruSource(Source):
    name = "marktguru"

    def __init__(self, zip_code: str = "4020", retailers: set[str] | None = None,
                 sleep: float = 0.6):
        self.zip_code = zip_code
        self.retailers = retailers or RETAILERS
        self.sleep = sleep
        self._keys: dict | None = None

    # --- key handling -------------------------------------------------------
    def _load_cached_keys(self) -> dict | None:
        if KEYS_FILE.exists():
            try:
                return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            except ValueError:
                return None
        return None

    def _scrape_keys(self) -> dict:
        html = self._get(HOMEPAGE)
        api_key = re.search(r'"apiKey"\s*:\s*"([^"]+)"', html)
        client_key = re.search(r'"clientKey"\s*:\s*"([^"]+)"', html)
        if not api_key or not client_key:
            raise RuntimeError("could not locate API keys on marktguru.at")
        keys = {"apiKey": api_key.group(1), "clientKey": client_key.group(1)}
        KEYS_FILE.write_text(json.dumps(keys), encoding="utf-8")
        return keys

    def _keys_dict(self, force: bool = False) -> dict:
        if force:
            self._keys = self._scrape_keys()
        elif self._keys is None:
            self._keys = self._load_cached_keys() or self._scrape_keys()
        return self._keys

    # --- http -------------------------------------------------------------
    def _get(self, url: str, keys: dict | None = None) -> str:
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if keys:
            headers["X-ApiKey"] = keys["apiKey"]
            headers["X-ClientKey"] = keys["clientKey"]
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.read().decode("utf-8", "ignore")

    def _search(self, term: str) -> list[dict]:
        results: list[dict] = []
        offset = 0
        while True:
            params = urllib.parse.urlencode({
                "as": "web", "q": term, "zipCode": self.zip_code,
                "limit": 1000, "offset": offset,
            })
            url = f"{SEARCH_URL}?{params}"
            try:
                raw = self._get(url, self._keys_dict())
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raw = self._get(url, self._keys_dict(force=True))
                else:
                    raise
            data = json.loads(raw)
            batch = data.get("results") or []
            results.extend(batch)
            total = data.get("totalResults") or 0
            offset += len(batch)
            if not batch or offset >= total:
                break
            time.sleep(self.sleep)
        return results

    # --- normalization ---------------------------------------------------
    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    def _to_offer(self, raw: dict) -> Offer | None:
        advertisers = raw.get("advertisers") or []
        unique = next((a.get("uniqueName") for a in advertisers
                       if a.get("uniqueName") in self.retailers), None)
        if not unique:
            return None

        brand = (raw.get("brand") or {}).get("name")
        name = ((raw.get("product") or {}).get("name") or "").strip()
        descr = (raw.get("description") or "").strip()
        product = name or descr
        if not product:
            return None
        if len(product) > 80:
            product = product[:77].rstrip() + "..."

        price = raw.get("price")
        old_price = raw.get("oldPrice")
        discount = raw.get("discount")
        if discount is None and price is not None and old_price:
            try:
                discount = round((old_price - price) / old_price * 100, 1)
            except ZeroDivisionError:
                discount = None
        if discount is not None:
            discount = round(float(discount), 1)

        validity = (raw.get("validityDates") or [{}])[0]
        offer_id = raw.get("id")
        url = f"https://www.marktguru.at/offer/{offer_id}" if offer_id else None

        return Offer(
            retailer=RETAILER_LABELS.get(unique, unique.title()),
            product=product,
            brand=brand,
            price=float(price) if price is not None else None,
            old_price=float(old_price) if old_price is not None else None,
            discount_pct=discount,
            valid_from=self._parse_date(validity.get("from")),
            valid_to=self._parse_date(validity.get("to")),
            url=url,
        )

    def _collect(self, terms) -> dict:
        seen: dict = {}
        for term in terms:
            try:
                rows = self._search(term)
            except Exception as exc:  # keep going with the other terms
                print(f"  marktguru: query '{term}' failed: {exc}")
                time.sleep(self.sleep)
                continue
            for raw in rows:
                oid = raw.get("id")
                dedup = oid if oid is not None else (
                    "x", raw.get("description"), raw.get("price"))
                if dedup in seen:
                    continue
                offer = self._to_offer(raw)
                if offer:
                    seen[dedup] = offer
            time.sleep(self.sleep)
        return seen

    def fetch_offers(self) -> list[Offer]:
        # One query per banner returns that banner's full offer set; fall back to
        # a keyword sweep only for a banner that comes back empty.
        seen = self._collect(sorted(self.retailers))
        got = {o.retailer for o in seen.values()}
        missing = {RETAILER_LABELS.get(r, r) for r in self.retailers} - got
        if missing:
            print(f"  marktguru: no offers via banner query for {missing}; "
                  f"trying keyword fallback")
            seen.update(self._collect(FALLBACK_KEYWORDS))
        return list(seen.values())
