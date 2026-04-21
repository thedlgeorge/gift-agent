"""
tools/keepa_client.py

Fetches price data via the official Keepa Python API.
Requires a KEEPA_API_KEY in .env (~$20/month for full access).

Keepa returns much richer data than CamelCamelCamel scraping:
  - Full daily price history (years of data)
  - All-time low / high with exact dates
  - Real-time current price
  - New, Used, and third-party prices

Keepa API docs: https://keepaapi.readthedocs.io
Get a key:      https://keepa.com/#!api
"""

import os
import logging
from datetime import datetime
from typing import Optional
from tools.db import upsert_price_record

logger = logging.getLogger(__name__)

# Keepa prices are stored in cents. -1 means "not available".
KEEPA_PRICE_UNAVAILABLE = -1
KEEPA_CENTS_DIVISOR = 100.0


def _get_api():
    """Lazy-initialize the Keepa API client. Returns None if no key is set."""
    api_key = os.environ.get("KEEPA_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import keepa
        return keepa.Keepa(api_key)
    except ImportError:
        logger.warning("keepa package not installed. Run: pip install keepa")
        return None
    except Exception as e:
        logger.error(f"Keepa init error: {e}")
        return None


def is_available() -> bool:
    """Return True if Keepa is configured and importable."""
    return _get_api() is not None


def fetch_price_data(asin: str) -> Optional[dict]:
    """
    Fetch current price + 90-day history for an ASIN via Keepa.

    Returns a dict with:
      - asin
      - current_price  (Amazon sold, new)
      - all_time_low
      - all_time_high
      - price_history  (list of {date, price} dicts — last 90 days)
      - fetched_at

    Returns None on failure.
    """
    api = _get_api()
    if api is None:
        return None

    logger.info(f"[{asin}] Fetching via Keepa API...")

    try:
        # stats=90 gives quick access to 90-day min/max/current prices
        # history=True fetches full price timeseries (default)
        products = api.query(asin, stats=90, history=True)
    except Exception as e:
        logger.error(f"[{asin}] Keepa query failed: {e}")
        return None

    if not products:
        logger.warning(f"[{asin}] No data returned from Keepa")
        return None

    product = products[0]
    return _parse_product(asin, product)


def _parse_product(asin: str, product: dict) -> Optional[dict]:
    """Extract the fields we care about from a Keepa product dict."""
    try:
        stats = product.get("stats", {})

        # Current Amazon price (index 0 = AMAZON channel in Keepa)
        current_raw = stats.get("current", [None])[0]
        current_price = _keepa_price(current_raw)

        # All-time low and high across all tracked history
        atl_raw = stats.get("min", [None])[0]
        ath_raw = stats.get("max", [None])[0]
        all_time_low = _keepa_price(atl_raw)
        all_time_high = _keepa_price(ath_raw)

        # 90-day price history from the timeseries data
        price_history = _extract_history(product)

        result = {
            "asin": asin,
            "current_price": current_price,
            "all_time_low": all_time_low,
            "all_time_high": all_time_high,
            "price_history": price_history,
            "fetched_at": datetime.utcnow().isoformat(),
            "source": "keepa",
        }

        if current_price is None:
            logger.warning(f"[{asin}] Keepa returned no current price")
            return None

        # Persist snapshot to SQLite
        upsert_price_record(result)
        logger.info(
            f"[{asin}] Keepa price: ${current_price:.2f} | "
            f"ATL: ${all_time_low} | ATH: ${all_time_high} | "
            f"{len(price_history)} history points"
        )
        return result

    except Exception as e:
        logger.error(f"[{asin}] Keepa parse error: {e}")
        return None


def _keepa_price(raw) -> Optional[float]:
    """Convert Keepa raw price (cents) to USD float. Returns None if unavailable."""
    if raw is None or raw == KEEPA_PRICE_UNAVAILABLE or raw < 0:
        return None
    return round(raw / KEEPA_CENTS_DIVISOR, 2)


def _extract_history(product: dict, days: int = 90) -> list[dict]:
    """
    Extract the last N days of Amazon-sold price history from Keepa timeseries.
    Keepa stores prices as arrays paired with minute-offset timestamps from 2011-01-01.
    """
    try:
        data = product.get("data", {})
        prices = data.get("AMAZON")       # Amazon-sold price series
        times = data.get("AMAZON_time")   # Corresponding timestamps

        if prices is None or times is None:
            return []

        base = datetime(2011, 1, 1)
        now = datetime.utcnow()
        cutoff = (now - base).total_seconds() / 60 - (days * 24 * 60)

        history = []
        for t, p in zip(times, prices):
            if t < cutoff:
                continue
            price = _keepa_price(p)
            if price is None:
                continue
            ts = base.replace(minute=0, second=0, microsecond=0)
            dt = datetime.fromtimestamp(
                (base + __import__("datetime").timedelta(minutes=int(t))).timestamp()
            )
            history.append({"date": dt.strftime("%Y-%m-%d"), "price": price})

        return history

    except Exception as e:
        logger.warning(f"Could not extract Keepa history: {e}")
        return []
