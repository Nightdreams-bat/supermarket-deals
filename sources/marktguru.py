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

# The API is search-only (an empty or single-letter q returns nothing), so a
# store's full offer set is approximated by sweeping a broad staple keyword list
# and deduping by offer id. allowedRetailers is ignored by the backend, so
# retailers are filtered client-side on advertiser uniqueName.
KEYWORDS = [
    "milch", "butter", "kaffee", "tee", "eier", "kaese", "joghurt", "topfen",
    "sahne", "brot", "gebaeck", "semmel", "toast", "wurst", "schinken", "speck",
    "huhn", "haehnchen", "pute", "schwein", "rind", "faschiertes", "fisch",
    "lachs", "thunfisch", "apfel", "banane", "orange", "trauben", "beeren",
    "tomate", "gurke", "paprika", "kartoffel", "zwiebel", "karotte", "salat",
    "champignon", "nudeln", "pasta", "reis", "mehl", "zucker", "oel", "olivenoel",
    "essig", "salz", "konserve", "suppe", "sauce", "ketchup", "senf", "muesli",
    "cornflakes", "keks", "schokolade", "praline", "chips", "snack", "nuesse",
    "eis", "tiefkuehl", "pizza", "pommes", "bier", "wein", "sekt", "spirituose",
    "wasser", "limonade", "cola", "saft", "energy", "waschmittel", "weichspueler",
    "spuelmittel", "putzmittel", "klopapier", "toilettenpapier", "kuechenrolle",
    "taschentuch", "shampoo", "duschgel", "seife", "zahnpasta", "deo",
    "windel", "katzenfutter", "hundefutter", "kaffeekapsel", "mineralwasser",
]

RETAILERS = {"norma", "hofer", "lidl", "eurospar"}
RETAILER_LABELS = {
    "norma": "Norma", "hofer": "Hofer", "lidl": "Lidl", "eurospar": "Eurospar",
}


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

    def _search(self, term: str, keys: dict) -> list[dict]:
        results: list[dict] = []
        offset = 0
        while True:
            params = urllib.parse.urlencode({
                "as": "web", "q": term, "zipCode": self.zip_code,
                "limit": 1000, "offset": offset,
            })
            url = f"{SEARCH_URL}?{params}"
            try:
                raw = self._get(url, keys)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    keys = self._keys_dict(force=True)
                    raw = self._get(url, keys)
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

    def fetch_offers(self) -> list[Offer]:
        keys = self._keys_dict()
        seen: dict[int, Offer] = {}
        for term in KEYWORDS:
            try:
                rows = self._search(term, keys)
            except Exception as exc:  # keep sweeping other terms
                print(f"  marktguru: term '{term}' failed: {exc}")
                time.sleep(self.sleep)
                continue
            for raw in rows:
                oid = raw.get("id")
                if oid in seen:
                    continue
                offer = self._to_offer(raw)
                if offer:
                    seen[oid] = offer
            time.sleep(self.sleep)
        return list(seen.values())
