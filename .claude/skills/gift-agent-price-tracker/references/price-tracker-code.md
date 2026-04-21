# Price Tracker — Annotated Source Reference

## agents/price_tracker.py

Entry point. Loads all ASINs, calls `fetch_batch`, logs results.

```python
def run_price_tracker(force: bool = False):
    init_db()                          # ensures tables exist
    items = load_all_asins()           # reads recipients.json → flat ASIN list
    asins = [item["asin"] for item in items]
    results = fetch_batch(asins, force=force)  # unified fetcher (see below)
    # logs success/skip/failure per ASIN
```

Key: `force=True` bypasses the 24h cache — use when testing or after a layout fix.

---

## tools/price_fetcher.py

Auto-selects source on first call, caches the choice for the session.

```python
def _resolve_source() -> str:
    from tools.keepa_client import is_available as keepa_available
    if keepa_available():           # checks KEEPA_API_KEY env var
        _active_source = "keepa"
    else:
        _active_source = "camelcamelcamel"

def fetch_batch(asins, force=False):
    if source == "keepa":
        # Single Keepa API call for all ASINs (efficient)
        products = api.query(asins, stats=90, history=True)
    else:
        # Sequential CCC fetches (rate-limited)
        for asin in asins:
            results[asin] = fetch(asin, force=force)
```

---

## tools/keepa_client.py

Wraps the `keepa` Python library. Key conversion: Keepa stores prices in **cents** as integers, with `-1` meaning "unavailable".

```python
KEEPA_CENTS_DIVISOR = 100.0

def _keepa_price(raw) -> Optional[float]:
    if raw is None or raw == -1 or raw < 0:
        return None
    return round(raw / KEEPA_CENTS_DIVISOR, 2)
```

Price history is extracted from `product["data"]["AMAZON"]` (Amazon-sold price series) and `product["data"]["AMAZON_time"]` (minute offsets from 2011-01-01).

Stats dict from `api.query(asin, stats=90)`:
- `stats["current"][0]` → current Amazon price (cents)
- `stats["min"][0]` → all-time low
- `stats["max"][0]` → all-time high

---

## tools/camel_scraper.py

Scrapes `camelcamelcamel.com/product/{ASIN}` with respectful delays.

```python
MIN_DELAY_SECONDS = 4
MAX_DELAY_SECONDS = 8

def fetch_price_data(asin, force=False):
    # Check 24h cache first (tools/db.get_last_fetched)
    # Random sleep before request
    # GET camelcamelcamel.com/product/{asin}
    # Parse with _parse_page() → _parse_jsonld_fallback() on miss
```

The parser looks for:
1. `.product-price` blocks with `.price-label` / `.price-value` children
2. JSON-LD `<script type="application/ld+json">` as fallback

---

## tools/db.py — Price History Schema

```sql
CREATE TABLE price_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asin          TEXT NOT NULL,
    price         REAL,
    all_time_low  REAL,
    all_time_high REAL,
    fetched_at    TEXT NOT NULL    -- ISO 8601 UTC
);
```

Key functions:
- `upsert_price_record(data)` — inserts a new snapshot
- `get_last_fetched(asin)` → `datetime | None` — used for 24h cache check
- `get_price_history(asin, days=90)` → list of snapshots
- `get_latest_price(asin)` → most recent snapshot dict
