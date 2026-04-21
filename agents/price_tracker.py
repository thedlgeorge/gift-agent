"""
agents/price_tracker.py

Iterates over all ASINs in recipients.json and fetches
fresh price data from CamelCamelCamel, storing results in SQLite.

Designed to run once per day (via scheduler or cron).
"""

import json
import logging
from pathlib import Path
from tools.price_fetcher import fetch, fetch_batch, active_source
from tools.db import init_db

logger = logging.getLogger(__name__)

RECIPIENTS_FILE = Path(__file__).parent.parent / "data" / "recipients.json"


def load_all_asins() -> list[dict]:
    """Return a flat list of {asin, name, recipient} dicts from recipients.json."""
    with open(RECIPIENTS_FILE) as f:
        recipients = json.load(f)

    items = []
    for recipient in recipients:
        for item in recipient.get("wishlist", []):
            items.append({
                "asin": item["asin"],
                "name": item["name"],
                "recipient": recipient["name"],
            })
    return items


def run_price_tracker(force: bool = False):
    """
    Fetch price data for every tracked ASIN.
    Skips ASINs fetched within the last 24h unless force=True.
    """
    init_db()
    items = load_all_asins()

    logger.info(f"Tracking {len(items)} products | Source: {active_source()}")

    asins = [item["asin"] for item in items]
    asin_to_item = {item["asin"]: item for item in items}

    results = fetch_batch(asins, force=force)

    successes = 0
    skipped = 0
    failures = 0

    for asin, result in results.items():
        item = asin_to_item.get(asin, {})
        if result is None:
            skipped += 1
        elif result.get("current_price"):
            successes += 1
            logger.info(
                f"  ✓ {item.get('name', asin)} ({item.get('recipient', '?')}) "
                f"— ${result['current_price']:.2f} [{result.get('source', '?')}]"
            )
        else:
            failures += 1
            logger.warning(f"  ✗ {item.get('name', asin)} — fetch returned no price")

    logger.info(
        f"Price tracking complete: {successes} fetched, {skipped} skipped (cached), {failures} failed"
    )
    return {"fetched": successes, "skipped": skipped, "failed": failures}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_price_tracker()
