---
name: gift-agent-notifier
description: >
  Use this skill whenever the user wants to set up, run, or debug price drop alerts for
  the gift agent project. Triggers include: "check for price drops", "send alerts",
  "run the notifier", "why didn't I get an email", "set up email notifications",
  "configure SendGrid", "test the alert system", or any request related to being notified
  when a product hits its target price. Also use when the user wants to change alert
  thresholds, add new notification channels (SMS, Slack), or understand how the notifier
  decides what to flag. Use before checking the optimizer if you want to verify alerts
  fire correctly on known price data.
---

# Gift Agent — Notifier Skill

Checks all tracked products against their `target_price` and sends email alerts via
SendGrid when a price drops to or below the target.

---

## Quick Reference

| Task | Command |
|------|---------|
| Check targets, send real emails | `python main.py notify` |
| Check targets, log only (no email) | Call `check_and_notify(dry_run=True)` |
| Test without any email config | `python agents/notifier.py` (runs dry_run=True) |
| Check what triggered | Look at notifier log output or `data/agent.log` |

---

## How It Works

1. Loads all recipients + wishlists from `data/recipients.json`
2. Calls `tools/db.get_latest_price(asin)` for each item
3. If `current_price <= target_price` → fires alert
4. Alert includes product name, current price, target, ATL, and direct Amazon + CCC links
5. Sends via SendGrid (if configured) or logs to console

---

## Alert Trigger Condition

```python
if current_price <= item["target_price"]:
    # fire alert
```

Only `target_price` is checked — not `max_price`. To add more nuanced triggers
(e.g., "within 10% of ATL"), modify `check_and_notify()` in `agents/notifier.py`.

---

## Email Setup (SendGrid)

Add to `.env`:
```
SENDGRID_API_KEY=SG....
ALERT_FROM_EMAIL=you@example.com
ALERT_TO_EMAIL=you@example.com
```

Install if not already present:
```bash
pip install sendgrid
```

Without these env vars, `_send_email_alert()` logs a warning and skips silently.
Alerts are still returned from `check_and_notify()` — only the send is skipped.

---

## Alert Email Content

Each alert email includes:
- Product name + recipient name
- Current price vs target price vs max budget
- All-time low (for context)
- Savings vs max budget
- Direct Amazon buy link: `amazon.com/dp/{ASIN}`
- Price history link: `camelcamelcamel.com/product/{ASIN}`

---

## Key Files

| File | Role |
|------|------|
| `agents/notifier.py` | Main logic — `check_and_notify()`, `_send_email_alert()` |
| `tools/db.py` | `get_latest_price()` — reads latest price snapshot |
| `data/recipients.json` | Source of truth for target prices |

---

## Adding Notification Channels

The notifier is designed for easy extension. `check_and_notify()` returns a list of
alert dicts — you can add any channel by processing that list:

```python
alerts = check_and_notify(dry_run=True)   # get alerts without sending email
for alert in alerts:
    send_sms(alert)     # Twilio
    post_to_slack(alert)  # Slack webhook
    push_to_phone(alert)  # Pushover / ntfy.sh
```

### SMS via Twilio (example)
```python
from twilio.rest import Client
client = Client(os.environ["TWILIO_SID"], os.environ["TWILIO_TOKEN"])
client.messages.create(
    body=f"🎁 {alert['product']} is ${alert['current_price']:.2f}!",
    from_=os.environ["TWILIO_FROM"],
    to=os.environ["ALERT_PHONE"],
)
```

---

## Common Issues

**No alerts firing even though price is below target**
→ `get_latest_price()` returns `None` — run `python main.py track` first to populate
the DB with price snapshots.

**Emails not sending**
→ Check `SENDGRID_API_KEY`, `ALERT_FROM_EMAIL`, `ALERT_TO_EMAIL` are all set in `.env`.
Run with `dry_run=True` to confirm alerts are triggering — the email step is separate.

**Want to alert on ATL proximity instead of target price**
→ Modify the condition in `check_and_notify()`:
```python
atl = latest.get("all_time_low")
if atl and current <= atl * 1.10:   # within 10% of all-time low
    # fire alert
```
