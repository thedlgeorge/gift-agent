# 🎁 Gift Agent

An AI-powered gift purchasing agent that tracks Amazon product prices via CamelCamelCamel, analyzes price trends, and recommends optimal gifts per recipient using Claude as the reasoning layer.

---

## The Problem

Buying gifts for family and friends is time-consuming. Prices fluctuate constantly on Amazon — the same item can vary 30–50% across the year. Without tracking, you either overpay or miss deals entirely.

## The Solution

A multi-agent system that:
1. **Tracks** price history for every product on your wishlists (via CamelCamelCamel)
2. **Analyzes** trends and buy signals using Claude + tool use
3. **Optimizes** gift selections per recipient based on budget and strategy (maximize value vs. maximize quantity)
4. **Alerts** you via email when a target price is hit

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│           CLI + APScheduler (runs daily at 8am)             │
└────────────┬──────────────┬──────────────┬──────────────────┘
             │              │              │
     ┌───────▼──────┐ ┌─────▼──────┐ ┌────▼──────────┐
     │ price_tracker│ │  notifier  │ │ gift_optimizer│
     │   agent      │ │   agent    │ │    agent      │
     └───────┬──────┘ └─────┬──────┘ └────┬──────────┘
             │              │              │
     ┌───────▼──────────────▼──────┐       │ Claude API
     │       price_fetcher.py      │       │ (tool use loop)
     │   Auto-selects best source  │       │
     └───────┬─────────────────────┘       │
             │                             │
     ┌───────▼──────────────────────┐      │
     │  Source Priority:            │      │
     │  1. Keepa API  (if key set)  │      │
     │  2. CamelCamelCamel (free)   │      │
     └───────┬──────────────────────┘      │
             │                             │
     ┌───────▼─────────────────────────────▼──┐
     │           SQLite (db.py)                │
     │   price_history | purchase_log          │
     └────────────────────────────────────────┘
```

### Agent Breakdown

| Agent | Role |
|-------|------|
| `price_tracker` | Iterates all ASINs, fetches prices via `price_fetcher`, stores in SQLite |
| `notifier` | Compares current prices to target prices; sends SendGrid email alerts |
| `gift_optimizer` | Claude-powered agentic loop — calls tools to analyze history, recommends best buys per recipient |

### Price Data Sources

| Source | Cost | Reliability | History Depth | Setup |
|--------|------|-------------|--------------|-------|
| **Keepa API** | ~$20/mo | ⭐⭐⭐⭐⭐ Real API | Years, daily | Add `KEEPA_API_KEY` to `.env` |
| **CamelCamelCamel** | Free | ⭐⭐⭐ HTML scraping | Snapshots only | None — works out of the box |

The agent **automatically uses Keepa if `KEEPA_API_KEY` is present**, and falls back to CamelCamelCamel if not. No code changes needed to switch — just add or remove the key from `.env`.

---

## Key Design Decisions

**Dual price source with automatic fallback**
The `price_fetcher.py` module checks for `KEEPA_API_KEY` at runtime. If present, it uses the official Keepa Python library — a real API with batch queries, years of daily price history, and structured data. If not, it falls back to scraping CamelCamelCamel at a respectful rate (once/product/day, randomized 4–8s delays). This makes the project work out of the box for free, while offering a clear upgrade path for production use.

**Why not just use Keepa from the start?**
Keepa costs ~$20/month. For a portfolio project you're building and demoing, the free CCC fallback means anyone can clone and run it without a credit card. The two sources share a common return schema, so the rest of the codebase doesn't care which one is active.

**Why Claude with tool use?**
The optimizer needs to reason about multiple products, multiple recipients, budgets, price trends, and optimization strategies simultaneously. This is exactly the kind of multi-step reasoning that benefits from an agentic loop — Claude decides which tools to call, interprets the results, and builds recommendations.

**Why SQLite?**
Zero setup, zero cost, version-controllable schema, and more than sufficient for personal/family-scale tracking. Easy to inspect with any SQLite browser.

---

## Quickstart

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/gift-agent.git
cd gift-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY at minimum
```

### 3. Set up your wishlists

Edit `data/recipients.json` with your family/friends, their budgets, and Amazon ASINs:

```json
[
  {
    "id": "mom",
    "name": "Mom",
    "budget": 150.00,
    "priority": "value",
    "notes": "Prefers practical gifts",
    "wishlist": [
      {
        "asin": "B08N5WRWNW",
        "name": "Echo Dot (4th Gen)",
        "target_price": 35.00,
        "max_price": 50.00,
        "priority": 1
      }
    ]
  }
]
```

**Finding ASINs:** On any Amazon product page, the ASIN is in the URL: `amazon.com/dp/B08N5WRWNW`

### 4. Run

```bash
# Fetch latest prices for all tracked products
python main.py track

# Check if any prices hit targets (sends email if configured)
python main.py notify

# Run AI optimizer — get gift recommendations per recipient
python main.py optimize

# Run everything at once
python main.py run

# Start daily scheduler (runs at 8am every day)
python main.py schedule
```

---

## Configuration Reference

### `recipients.json` schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (used in DB logs) |
| `name` | string | Display name |
| `budget` | float | Total gift budget in USD |
| `priority` | `"value"` \| `"quantity"` | Optimization strategy |
| `notes` | string | Context for Claude's reasoning |
| `wishlist[].asin` | string | Amazon ASIN |
| `wishlist[].target_price` | float | Price you'd love to pay |
| `wishlist[].max_price` | float | Absolute price ceiling |
| `wishlist[].priority` | int | 1 = highest priority |

### `.env` variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Your Anthropic API key |
| `SENDGRID_API_KEY` | Optional | For email alerts |
| `ALERT_FROM_EMAIL` | Optional | Sender address |
| `ALERT_TO_EMAIL` | Optional | Your email for alerts |

---

## Project Structure

```
gift-agent/
├── .claude/
│   └── skills/                          # Claude Code skills (auto-loaded)
│       ├── gift-agent-price-tracker/    # Skill: fetching & storing prices
│       │   ├── SKILL.md
│       │   └── references/price-tracker-code.md
│       ├── gift-agent-optimizer/        # Skill: Claude agentic loop
│       │   ├── SKILL.md
│       │   └── references/optimizer-code.md
│       └── gift-agent-notifier/         # Skill: alerts & notifications
│           └── SKILL.md
├── agents/
│   ├── price_tracker.py    # Fetches & stores prices daily
│   ├── gift_optimizer.py   # Claude agentic loop for recommendations
│   └── notifier.py         # Email alerts on price drops
├── tools/
│   ├── price_fetcher.py    # ★ Unified source selector (Keepa → CCC fallback)
│   ├── keepa_client.py     # Keepa API client (used if KEEPA_API_KEY is set)
│   ├── camel_scraper.py    # CamelCamelCamel HTML parser (free fallback)
│   └── db.py               # SQLite data layer
├── data/
│   ├── recipients.json     # Your wishlists (edit this)
│   └── gift_agent.db       # Auto-created SQLite database
├── main.py                 # CLI entrypoint + scheduler
├── requirements.txt
├── .env.example
└── .gitignore
```

### Claude Code Skills

The `.claude/skills/` directory is automatically picked up by Claude Code when you open this project. Each skill teaches Claude how this codebase works — no need to re-explain the architecture in every session.

| Skill | Auto-triggers when you ask about... |
|-------|-------------------------------------|
| `gift-agent-price-tracker` | fetching prices, ASIN tracking, CCC/Keepa, DB snapshots |
| `gift-agent-optimizer` | recommendations, Claude tool-use loop, buy signals, budgets |
| `gift-agent-notifier` | email alerts, price drop triggers, SendGrid, notification channels |

---

## Roadmap

- [ ] Web UI dashboard (price charts per ASIN)
- [ ] Multi-country support (amazon.co.uk, amazon.ca)
- [ ] Seasonal price prediction (Black Friday patterns)
- [ ] SMS alerts via Twilio
- [ ] GitHub Actions workflow for daily cloud runs

---

## Ethics & ToS note

When using the CamelCamelCamel fallback, this agent scrapes at a respectful rate (max 1 request per product per 24 hours, with randomized delays). It does **not** scrape Amazon directly. The Keepa API path uses their official, licensed service. Purchase decisions are surfaced as recommendations — the human always confirms before buying.

---

## License

MIT
