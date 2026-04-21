# Gift Optimizer — Annotated Source Reference

## agents/gift_optimizer.py — Full Agentic Loop

### Tool Definitions (TOOLS list)

Tools are defined in Anthropic's tool schema format. Each tool needs:
- `name` — Python identifier, matched in `execute_tool()`
- `description` — what Claude reads to decide when to call it
- `input_schema` — JSON Schema for the tool's arguments

```python
TOOLS = [
    {
        "name": "get_price_history",
        "description": "Retrieve stored price history for an ASIN...",
        "input_schema": {
            "type": "object",
            "properties": {
                "asin": {"type": "string"},
                "days": {"type": "integer", "default": 90},
            },
            "required": ["asin"],
        },
    },
    # ... get_latest_price, record_recommendation
]
```

### execute_tool() — Local Tool Runner

Routes Claude's tool_use blocks to actual Python functions:

```python
def execute_tool(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "get_price_history":
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
        log_purchase_decision(...)
        return {"status": "recorded"}
```

### run_optimizer() — The Loop

```python
def run_optimizer(recipient: dict) -> dict:
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            system=build_system_prompt(),
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Extract text summary and return
            return {"recipient": ..., "summary": ...}

        if response.stop_reason == "tool_use":
            # Execute all tool calls, collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            # Feed results back to Claude
            messages.append({"role": "user", "content": tool_results})
```

### build_system_prompt()

The system prompt is where you tune Claude's reasoning behavior. Key sections:

1. **Role** — "You are a smart gift purchasing agent..."
2. **Workflow** — numbered steps Claude follows per recipient
3. **Buy signals** — conditions that justify a recommendation
4. **Strategy** — how to apply "value" vs "quantity"
5. **Hard constraints** — never exceed max_price or budget

---

## tools/db.py — Optimizer-Relevant Functions

```python
def get_price_history(asin: str, days: int = 90) -> list[dict]:
    # Returns snapshots from the last N days, ordered ASC by date

def get_latest_price(asin: str) -> Optional[dict]:
    # Returns most recent snapshot: {asin, price, all_time_low, all_time_high, fetched_at}

def log_purchase_decision(
    recipient_id, asin, product_name,
    purchase_price, decision_reason, status="pending_review"
):
    # Inserts into purchase_log table
```

## purchase_log Schema

```sql
CREATE TABLE purchase_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id    TEXT NOT NULL,
    asin            TEXT NOT NULL,
    product_name    TEXT,
    purchase_price  REAL,
    decision_reason TEXT,
    actioned_at     TEXT NOT NULL,
    status          TEXT DEFAULT 'pending_review'
    -- status values: 'pending_review', 'recommended', 'purchased', 'skipped'
);
```

---

## Adding a New Tool

1. Add to `TOOLS` list with name, description, input_schema
2. Add matching branch in `execute_tool()`
3. Optionally mention it in `build_system_prompt()` so Claude knows when to use it

Example — adding a "search_alternative_products" tool:
```python
# In TOOLS:
{
    "name": "search_alternative_products",
    "description": "Search for cheaper alternatives to a product by category keyword",
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string"},
            "max_price": {"type": "number"},
        },
        "required": ["keyword", "max_price"],
    },
}

# In execute_tool():
elif tool_name == "search_alternative_products":
    # your implementation here
    return {"alternatives": [...]}
```
