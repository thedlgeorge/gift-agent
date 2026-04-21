"""
tools/price_fetcher.py

Unified interface for fetching Amazon price data.
Automatically selects the best available source:

  Priority 1 → Keepa API (if KEEPA_API_KEY is set)
              • Real API, structured data, full history, no scraping
              • ~$20/month, but significantly more reliable

  Priority 2 → CamelCamelCamel scraper (free, no key required)
              • HTML scraping with respectful rate limits
              • May break if CCC changes their layout

Usage:
    from tools.price_fetcher import fetch, active_source
    data = fetch("B08N5WRWNW")
    print(f"Using: {active_source()}")

Both sources return the same normalized dict shape:
    {
        "asin":          str,
        "current_price": float | None,
        "all_time_low":  float | None,
        "all_time_high": float | None,
        "fetched_at":    str (ISO),
        "source":        "keepa" | "camelcamelcamel"
    }
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy cache of which source is active (set on first call)
_active_source: Optional[str] = None


def active_source() -> str:
    """Return the name of the currently active price data source."""
    _resolve_source()
    return _active_source or "none"


def _resolve_source() -> str:
    """Determine and cache the best available source."""
    global _active_source
    if _active_source:
        return _active_source

    from tools.keepa_client import is_available as keepa_available
    if keepa_available():
        _active_source = "keepa"
        logger.info("Price source: Keepa API ✓")
    else:
        _active_source = "camelcamelcamel"
        logger.info("Price source: CamelCamelCamel (scraper) — add KEEPA_API_KEY to upgrade")

    return _active_source


def fetch(asin: str, force: bool = False) -> Optional[dict]:
    """
    Fetch price data for an ASIN using the best available source.

    Args:
        asin:  Amazon ASIN (10 characters)
        force: If True, bypass the 24h cache and re-fetch

    Returns:
        Normalized price dict, or None on failure / cache hit
    """
    source = _resolve_source()

    if source == "keepa":
        from tools.keepa_client import fetch_price_data
        result = fetch_price_data(asin)
    else:
        from tools.camel_scraper import fetch_price_data
        result = fetch_price_data(asin, force=force)

    if result:
        result["source"] = source

    return result


def fetch_batch(asins: list[str], force: bool = False) -> dict[str, Optional[dict]]:
    """
    Fetch price data for multiple ASINs.
    Keepa supports batch queries natively; CCC falls back to sequential.

    Returns:
        Dict mapping asin → price dict (or None on failure)
    """
    source = _resolve_source()
    results = {}

    if source == "keepa":
        # Keepa can handle a list of ASINs in one API call
        import os
        import keepa
        api_key = os.environ.get("KEEPA_API_KEY", "")
        if api_key:
            try:
                api = keepa.Keepa(api_key)
                products = api.query(asins, stats=90, history=True)
                from tools.keepa_client import _parse_product
                for product in products:
                    asin = product.get("asin", "")
                    if asin:
                        results[asin] = _parse_product(asin, product)
                return results
            except Exception as e:
                logger.error(f"Keepa batch query failed: {e} — falling back to sequential")

    # Sequential fallback
    for asin in asins:
        results[asin] = fetch(asin, force=force)

    return results
