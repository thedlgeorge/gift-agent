"""
agents/notifier.py

Checks all wishlist items against their target_price and sends
an email alert when a product drops to or below the target.

Uses SendGrid for email (free tier is plenty).
Configure SENDGRID_API_KEY in .env
"""

import json
import logging
import os
from pathlib import Path
from tools.db import get_latest_price

logger = logging.getLogger(__name__)

RECIPIENTS_FILE = Path(__file__).parent.parent / "data" / "recipients.json"


def check_and_notify(dry_run: bool = False) -> list[dict]:
    """
    Check all tracked items for price drops below target_price.
    Sends email alerts for matches. Returns list of triggered alerts.

    Set dry_run=True to log alerts without sending emails.
    """
    with open(RECIPIENTS_FILE) as f:
        recipients = json.load(f)

    alerts = []

    for recipient in recipients:
        for item in recipient.get("wishlist", []):
            latest = get_latest_price(item["asin"])
            if not latest or latest["price"] is None:
                continue

            current = latest["price"]
            target = item["target_price"]
            max_price = item["max_price"]

            if current <= target:
                alert = {
                    "recipient": recipient["name"],
                    "product": item["name"],
                    "asin": item["asin"],
                    "current_price": current,
                    "target_price": target,
                    "max_price": max_price,
                    "all_time_low": latest.get("all_time_low"),
                    "savings_vs_max": round(max_price - current, 2),
                }
                alerts.append(alert)
                logger.info(
                    f"🎯 ALERT: {item['name']} for {recipient['name']} "
                    f"— ${current:.2f} (target ${target:.2f})"
                )

                if not dry_run:
                    _send_email_alert(alert)

    if not alerts:
        logger.info("No price targets hit — no alerts sent.")

    return alerts


def _send_email_alert(alert: dict):
    """Send email via SendGrid. Requires SENDGRID_API_KEY in environment."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=os.environ["SENDGRID_API_KEY"])
        from_email = os.environ.get("ALERT_FROM_EMAIL", "agent@gift-agent.local")
        to_email = os.environ.get("ALERT_TO_EMAIL", from_email)

        body = f"""
🎁 Gift Price Alert

Product: {alert['product']}
Recipient: {alert['recipient']}

Current Price: ${alert['current_price']:.2f}
Your Target:   ${alert['target_price']:.2f}
Max Budget:    ${alert['max_price']:.2f}
All-Time Low:  ${alert.get('all_time_low') or 'N/A'}

You're saving ${alert['savings_vs_max']:.2f} vs your max budget!

Buy it on Amazon:
https://www.amazon.com/dp/{alert['asin']}

View price history:
https://camelcamelcamel.com/product/{alert['asin']}

---
Sent by your Gift Agent 🤖
        """.strip()

        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=f"🎁 Price Drop: {alert['product']} is now ${alert['current_price']:.2f}",
            plain_text_content=body,
        )
        sg.send(message)
        logger.info(f"Email sent for {alert['product']}")

    except ImportError:
        logger.warning("sendgrid not installed — skipping email. Run: pip install sendgrid")
    except KeyError as e:
        logger.warning(f"Missing env var for email: {e} — skipping send")
    except Exception as e:
        logger.error(f"Email send failed: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    triggered = check_and_notify(dry_run=True)
    print(f"\n{len(triggered)} alert(s) triggered.")
