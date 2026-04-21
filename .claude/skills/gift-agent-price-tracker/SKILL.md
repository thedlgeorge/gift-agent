---
name: gift-agent-price-tracker
description: >
  Use this skill whenever the user wants to fetch, update, or store Amazon product price data
  for the gift agent project. Triggers include: "track prices", "update price history",
  "fetch ASIN prices", "run the price tracker", "refresh product data", or any request to
  pull current pricing from CamelCamelCamel or Keepa for a list of ASINs. Also use when
  the user wants to add new products to track, check what prices are cached in the database,
  or diagnose why a price fetch failed. Always use this skill before running the optimizer
  — fresh price data is required for accurate recommendations.
---

# Gift Agent — Price Tracker Skill

Fetches current Amazon product prices for all ASINs in `data/recipients.json` and stores
snapshots in the local SQLite database. Automatically selects the best available source:
**Keepa API** (if `KEEPA_API_KEY` is set) or **CamelCamelCamel scraping** (free fallback).

---

## Quick Reference

| Task | Command |
|------|---------|
| Fetch all prices (respects 24h cache) | `python main.py track` |
| Force re-fetch ignoring cache | Call `run_price_tracker(force=True)` directly |
| Check what's in the DB | Query `price_history` table in `data/gift_agent.db` |
| Add products to track | Edit `data/recipients.json` — see schema below |

---

## How It Works

1. Loads all ASINs from `data/recipients.json`
2. Calls `tools/price_fetcher.py` → auto-routes to Keepa or CCC
3. Stores price snapshots in SQLite (`price_history` table)
4. Skips ASINs fetched within the last 24 hours (unless `force=True`)

### Source Selection Logic (`tools/price_fetcher.py`)

```
KEEPA_API_KEY set in .env?
    YES → tools/keepa_client.py  (real API, batch queries, years of history)
    NO  → tools/camel_scraper.py (HTML scraping, 1 req/product/day, 4–8s delay)
```

The active source is logged at startup:
```
Price source: Keepa API ✓
# or
Price source: CamelCamelCamel (scraper) — add KEEPA_API_KEY to upgrade
```

---

## Key Files

| File | Role |
|------|------|
| `agents/price_tracker.py` | Entry point — iterates ASINs, calls fetch_batch |
| `tools/price_fetcher.py` | Unified interface, source selection |
| `tools/keepa_client.py` | Keepa API integration |
| `tools/camel_scraper.py` | CamelCamelCamel HTML parser |
| `tools/db.py` | SQLite layer — `upsert_price_record`, `get_last_fetched` |

See `references/price-tracker-code.md` for full annotated source.

---

## Normalized Price Dict (both sources return this shape)

```python
{
    "asin":          str,           # e.g. "B08N5WRWNW"
    "current_price": float | None,  # Amazon-sold price in USD
    "all_time_low":  float | None,
    "all_time_high": float | None,
    "fetched_at":    str,           # ISO 8601 UTC
    "source":        str,           # "keepa" or "camelcamelcamel"
}
```

---

## Adding Products to Track

Edit `data/recipients.json`. Each wishlist item needs:

```json
{
  "asin":         "B08N5WRWNW",   // from amazon.com/dp/{ASIN}
  "name":         "Echo Dot",
  "target_price": 35.00,          // ideal price — triggers alert
  "max_price":    50.00,          // ceiling — never recommend above this
  "priority":     1               // 1 = highest
}
```

---

## Common Issues

**CCC fetch returns `None`**
→ CamelCamelCamel's HTML layout may have changed. Check `tools/camel_scraper.py` → `_parse_page()` selectors. The JSON-LD fallback in `_parse_jsonld_fallback()` may still work.

**Keepa returns no current price**
→ Product may be sold by third-party only (no Amazon-direct listing). Check `stats["current"][0]` — Keepa returns `-1` for unavailable.

**Rate limit / CAPTCHA on CCC**
→ Increase `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS` in `camel_scraper.py`. The 24h cache means this should only happen once per product per day.

---

## Extending the Scraper

If CamelCamelCamel changes their layout, update `_parse_page()` in `tools/camel_scraper.py`.
The function looks for `.product-price` blocks with `.price-label` and `.price-value` children.
Always keep `_parse_jsonld_fallback()` as a safety net — structured data changes less often than CSS.
