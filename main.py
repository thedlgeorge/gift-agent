"""
main.py

Entry point for the Gift Agent.

Modes:
  python main.py track     — Fetch latest prices for all tracked products
  python main.py optimize  — Run AI optimizer for all recipients
  python main.py notify    — Check targets and send alerts
  python main.py run       — Run all three in sequence
  python main.py schedule  — Start the daily scheduler (runs continuously)
"""

import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/agent.log"),
    ],
)
logger = logging.getLogger("gift-agent")

RECIPIENTS_FILE = Path("data/recipients.json")


def cmd_track():
    from agents.price_tracker import run_price_tracker
    logger.info("=== PRICE TRACKER ===")
    result = run_price_tracker()
    print(f"\nDone: {result['fetched']} fetched, {result['skipped']} skipped, {result['failed']} failed")


def cmd_optimize():
    from agents.gift_optimizer import run_optimizer
    with open(RECIPIENTS_FILE) as f:
        recipients = json.load(f)

    logger.info("=== GIFT OPTIMIZER ===")
    for recipient in recipients:
        result = run_optimizer(recipient)
        print(f"\n{'='*60}")
        print(f"Recommendations for {result['recipient']}:")
        print(result["summary"])


def cmd_notify(dry_run: bool = False):
    from agents.notifier import check_and_notify
    logger.info("=== NOTIFIER ===")
    alerts = check_and_notify(dry_run=dry_run)
    print(f"\n{len(alerts)} price target(s) hit.")


def cmd_run():
    cmd_track()
    cmd_notify(dry_run=False)
    cmd_optimize()


def cmd_schedule():
    """Run the full pipeline daily at 8am using APScheduler."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler()
    scheduler.add_job(cmd_run, "cron", hour=8, minute=0, id="daily_run")
    logger.info("Scheduler started — will run daily at 8:00 AM.")
    print("Scheduler running. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")


COMMANDS = {
    "track": cmd_track,
    "optimize": cmd_optimize,
    "notify": lambda: cmd_notify(dry_run=False),
    "run": cmd_run,
    "schedule": cmd_schedule,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd]()
