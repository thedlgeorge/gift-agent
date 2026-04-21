---
name: gift-agent-optimizer
description: >
  Use this skill whenever the user wants to run the AI gift recommendation engine, generate
  purchase suggestions for recipients, or understand how the Claude agentic loop works in
  the gift agent project. Triggers include: "run the optimizer", "get gift recommendations",
  "what should I buy for [person]", "analyze price history for gifts", "optimize my gift
  budget", or any request to have Claude reason about which products to buy given a budget.
  Also use when adding new tools to the optimizer, changing the optimization strategy
  (value vs quantity), modifying the system prompt, or debugging why a recommendation
  was made. This skill covers the full agentic tool-use loop inside gift_optimizer.py.
---

# Gift Agent — Optimizer Skill

The AI reasoning core of the gift agent. Uses **Claude with tool use** in an agentic loop
to analyze price history, apply budget constraints, and recommend the best gifts per recipient.

---

## Quick Reference

| Task | Command |
|------|---------|
| Run optimizer for all recipients | `python main.py optimize` |
| Run full pipeline (track → notify → optimize) | `python main.py run` |
| Add a tool Claude can call | Add to `TOOLS` list + `execute_tool()` in `gift_optimizer.py` |
| Change optimization strategy | Edit `priority` field in `data/recipients.json` |
| Change Claude's reasoning behavior | Edit `build_system_prompt()` |

---

## How the Agentic Loop Works

```
User message (recipient + wishlist JSON)
        ↓
  Claude reasons → decides which tool to call
        ↓
  execute_tool() runs the tool locally
        ↓
  Result returned to Claude as tool_result
        ↓
  Claude reasons again → calls more tools or stops
        ↓
  stop_reason == "end_turn" → return final summary
```

This loop runs in `run_optimizer()` in `agents/gift_optimizer.py`.
Claude drives the entire process — it decides which ASINs to check and in what order.

---

## Available Tools (what Claude can call)

| Tool | What it does |
|------|-------------|
| `get_price_history` | Returns stored DB snapshots for an ASIN (last N days) + source metadata |
| `get_latest_price` | Returns the most recent price snapshot for an ASIN |
| `record_recommendation` | Logs a final purchase recommendation to `purchase_log` table |

To add a new tool: add an entry to `TOOLS` (Anthropic tool schema format) and a matching
branch in `execute_tool()`. See `references/optimizer-code.md` for the full pattern.

---

## Optimization Strategies

Set per-recipient in `data/recipients.json` via the `"priority"` field:

| Value | Behavior |
|-------|----------|
| `"value"` | Prioritize highest-priority items; spend more on fewer excellent gifts |
| `"quantity"` | Spread budget across as many items as possible above priority 1 |

Claude receives this strategy in the user message and applies it during reasoning.
The system prompt reinforces conservative buying: only recommend when price is at or
near target, or within 15% of the all-time low.

---

## Buy Signal Logic (in system prompt)

Claude recommends purchasing when **at least one** condition is met:
1. `current_price <= target_price` (ideal)
2. `current_price <= all_time_low * 1.15` (within 15% of ATL)
3. Price trend is stable and item is priority 1

Hard constraints Claude always respects:
- Never recommend above `max_price`
- Never exceed recipient's total `budget`

---

## Key Files

| File | Role |
|------|------|
| `agents/gift_optimizer.py` | Full agentic loop, tool definitions, system prompt |
| `tools/db.py` | `get_price_history`, `get_latest_price`, `log_purchase_decision` |
| `data/recipients.json` | Recipients, budgets, wishlists, strategies |

See `references/optimizer-code.md` for full annotated source.

---

## recipients.json Schema

```json
{
  "id":       "mom",             // unique key, used in DB logs
  "name":     "Mom",
  "budget":   150.00,            // total spend ceiling in USD
  "priority": "value",           // "value" or "quantity"
  "notes":    "Prefers practical gifts",  // passed to Claude for context
  "wishlist": [
    {
      "asin":         "B08N5WRWNW",
      "name":         "Echo Dot (4th Gen)",
      "target_price": 35.00,     // ideal price
      "max_price":    50.00,     // hard ceiling
      "priority":     1          // 1 = buy first
    }
  ]
}
```

---

## Common Issues

**Claude keeps recommending items above target price**
→ Strengthen the system prompt constraint in `build_system_prompt()`. Add: "If current price
exceeds target_price by more than 20%, do NOT recommend unless it is the only priority-1 item."

**Agent loop runs too many tool calls**
→ Claude may be over-checking history. Add a note to the system prompt: "Check each ASIN
at most once with get_price_history and once with get_latest_price."

**`record_recommendation` not being called**
→ Claude may have concluded nothing meets the buy signal. Check the summary text — it will
explain why items were skipped. Lower `target_price` or widen the 15% ATL threshold.

**`stop_reason` is not `end_turn` or `tool_use`**
→ May be a `max_tokens` limit hit. Increase `max_tokens` in the `client.messages.create()` call.
