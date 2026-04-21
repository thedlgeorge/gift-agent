"""
tools/camel_scraper.py

Fetches current price and basic price history from CamelCamelCamel
by ASIN. Respects rate limits — one request per product per day max.

CamelCamelCamel URL pattern:
  https://camelcamelcamel.com/product/{ASIN}
"""

import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Optional
from tools.db import get_last_fetched, upsert_price_record

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_URL = "https://camelcamelcamel.com/product/{asin}"
MIN_DELAY_SECONDS = 4   # Be respectful — never hammer the site
MAX_DELAY_SECONDS = 8


def fetch_price_data(asin: str, force: bool = False) -> Optional[dict]:
    """
    Fetch current price data for an ASIN from CamelCamelCamel.

    Returns a dict with:
      - asin
      - current_price (Amazon sold)
      - all_time_low
      - all_time_high
      - fetched_at (ISO timestamp)

    Returns None if fetch fails or was done recently (unless force=True).
    """
    # Rate limiting: don't re-fetch within 24 hours
    if not force:
        last = get_last_fetched(asin)
        if last and (datetime.utcnow() - last) < timedelta(hours=24):
            logger.info(f"[{asin}] Skipping fetch — cached within 24h")
            return None

    url = BASE_URL.format(asin=asin)
    logger.info(f"[{asin}] Fetching from CamelCamelCamel...")

    # Polite random delay before each request
    delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
    time.sleep(delay)

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"[{asin}] HTTP error: {e}")
        return None

    return _parse_page(asin, response.text)


def _parse_page(asin: str, html: str) -> Optional[dict]:
    """Parse CamelCamelCamel product page HTML for price data."""
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "asin": asin,
        "current_price": None,
        "all_time_low": None,
        "all_time_high": None,
        "fetched_at": datetime.utcnow().isoformat(),
    }

    try:
        # CamelCamelCamel displays price info in a stats table
        # Selectors may need updating if CCC changes their layout
        stat_blocks = soup.select(".product-price")
        for block in stat_blocks:
            label = block.select_one(".price-label")
            value = block.select_one(".price-value")
            if not label or not value:
                continue
            label_text = label.get_text(strip=True).lower()
            price = _parse_price(value.get_text(strip=True))
            if "current" in label_text or "amazon" in label_text:
                result["current_price"] = price
            elif "low" in label_text:
                result["all_time_low"] = price
            elif "high" in label_text:
                result["all_time_high"] = price

        # Fallback: look for JSON-LD structured data
        if result["current_price"] is None:
            result = _parse_jsonld_fallback(soup, result)

    except Exception as e:
        logger.error(f"[{asin}] Parse error: {e}")
        return None

    if result["current_price"] is None:
        logger.warning(f"[{asin}] Could not extract current price — page layout may have changed")
        return None

    # Persist to local DB
    upsert_price_record(result)
    logger.info(f"[{asin}] Price: ${result['current_price']} | ATL: ${result['all_time_low']} | ATH: ${result['all_time_high']}")
    return result


def _parse_price(text: str) -> Optional[float]:
    """Convert '$42.99' or '42.99' string to float."""
    try:
        cleaned = text.replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _parse_jsonld_fallback(soup: BeautifulSoup, result: dict) -> dict:
    """Try to extract price from JSON-LD structured data as fallback."""
    import json
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and "offers" in data:
                price = data["offers"].get("price")
                if price:
                    result["current_price"] = float(price)
                    break
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return result
