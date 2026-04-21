"""
agents/gift_optimizer.py

The core AI agent. Uses Claude (via Anthropic API + tool use) to:
  1. Analyze price history per product
  2. Determine the best purchase combination per recipient given budget
  3. Apply the correct optimization strategy (value vs. quantity)
  4. Return structured recommendations with reasoning
"""

import json
import logging
from typing import Any
from anthropic import Anthropic
from tools.db import get_price_history, get_latest_price, log_purchase_decision

logger = logging.getLogger(__name__)

client = Anthropic()

# ── Tool definitions for Claude ────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_price_history",
        "description": (
            "Retrieve the stored price history for an Amazon product by ASIN. "
            "Returns a list of price snapshots (price, all_time_low, all_time_high, fetched_at). "
            "Use this to understand price trends before making a recommendation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asin": {"type": "string", "description": "Amazon Standard Identification Number"},
                "days": {"type": "integer", "description": "Number of days of history to retrieve (default 90)", "default": 90},
            },
            "required": ["asin"],
        },
    },
    {
        "name": "get_latest_price",
        "description": "Get the most recent price snapshot for an Amazon product by ASIN.",
        "input_schema": {
            "type": "object",
            "properties": {
                "asin": {"type": "string", "description": "Amazon Standard Identification Number"},
            },
            "required": ["asin"],
        },
    },
    {
        "name": "record_recommendation",
        "description": (
            "Record a final purchase recommendation for a recipient + product. "
            "Call this once per item you recommend purchasing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recipient_id": {"type": "string"},
                "asin": {"type": "string"},
                "product_name": {"type": "string"},
                "recommended_price": {"type": "number"},
                "reasoning": {"type": "string", "description": "Why this item at this price is a good buy now"},
            },
            "required": ["recipient_id", "asin", "product_name", "recommended_price", "reasoning"],
        },
    },
]

# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "get_price_history":
        # Return stored DB history; also include source metadata
        history = get_price_history(tool_input["asin"], tool_input.get("days", 90))
        latest = get_latest_price(tool_input["asin"])
        return {
            "history": history,
            "source": latest.get("source", "unknown") if latest else "unknown",
            "point_count": len(history),
        }
    elif tool_name == "get_latest_price":
        return get_latest_price(tool_input["asin"])
    elif tool_name == "record_recommendation":
        log_purchase_decision(
            recipient_id=tool_input["recipient_id"],
            asin=tool_input["asin"],
            product_name=tool_input["product_name"],
            purchase_price=tool_input["recommended_price"],
            decision_reason=tool_input["reasoning"],
            status="recommended",
        )
        return {"status": "recorded"}
    else:
        raise ValueError(f"Unknown tool: {tool_name}")


# ── Main agent loop ────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    return """You are a smart gift purchasing agent. Your job is to analyze Amazon product price data
and recommend the best gifts to purchase for each recipient given their budget and preferences.

For each recipient you will receive:
- Their name, total budget, and optimization strategy ("value" = best quality per dollar, "quantity" = maximize number of gifts)
- A wishlist of products with ASINs, target prices, max prices, and priorities

Your workflow for each recipient:
1. Use get_latest_price for each wishlist item to see current prices
2. Use get_price_history to assess price trends (is the price dropping, stable, or rising?)
3. Determine which combination of items fits within budget AND meets at least one of:
   a. Current price is at or below target_price (ideal buy signal)
   b. Current price is within 15% of all-time low (very good deal)
   c. Price trend is stable and item is high priority
4. Apply the optimization strategy:
   - "value": prioritize the highest-priority items, spend more on fewer great gifts
   - "quantity": spread budget across as many items as possible above priority 1
5. Call record_recommendation for each item you recommend buying NOW
6. Return a clean summary to the user

Be conservative: only recommend buying if the price is reasonable relative to history.
Never recommend spending over max_price for any item.
Always respect the total budget ceiling.
"""


def run_optimizer(recipient: dict) -> dict:
    """
    Run the gift optimizer agent for a single recipient.
    Returns a dict with recommendations and a human-readable summary.
    """
    logger.info(f"Running optimizer for: {recipient['name']}")

    user_message = f"""
Please analyze and recommend gifts for this recipient:

{json.dumps(recipient, indent=2)}

Use your tools to check current prices and price history, then make purchase recommendations
that fit within the ${recipient['budget']:.2f} total budget.
Optimization strategy: {recipient.get('priority', 'value')}
Notes: {recipient.get('notes', 'none')}
"""

    messages = [{"role": "user", "content": user_message}]

    # Agentic loop — keeps running until Claude stops using tools
    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            system=build_system_prompt(),
            tools=TOOLS,
            messages=messages,
        )

        # Add assistant response to history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Extract final text summary
            summary = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "No summary generated."
            )
            logger.info(f"Optimizer complete for {recipient['name']}")
            return {"recipient": recipient["name"], "summary": summary}

        if response.stop_reason == "tool_use":
            # Execute all tool calls and return results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"  Tool call: {block.name}({block.input})")
                    try:
                        result = execute_tool(block.name, block.input)
                    except Exception as e:
                        result = {"error": str(e)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
            break

    return {"recipient": recipient["name"], "summary": "Agent loop ended unexpectedly."}
