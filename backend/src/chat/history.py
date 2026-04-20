"""Conversation history utilities — context management for follow-up queries."""


def build_conversation_context(messages: list[dict], max_messages: int = 10) -> list[dict]:
    """Build a trimmed conversation context for LLM consumption.

    Keeps the most recent messages within token budget.
    """
    if not messages:
        return []

    # Take last N messages
    recent = messages[-max_messages:]

    # Format for LLM
    context = []
    for msg in recent:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        # Trim very long messages to save tokens
        if len(content) > 500:
            content = content[:500] + "..."
        context.append({"role": role, "content": content})

    return context


def extract_last_topic(messages: list[dict]) -> dict:
    """Extract the last discussed topic for follow-up context.

    Returns dict with keys: metric, time_period, filters, entities.
    """
    topic = {
        "metric": None,
        "time_period": None,
        "filters": [],
        "entities": [],
        "last_query": None,
        "last_response_summary": None,
    }

    if not messages:
        return topic

    # Find last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            topic["last_query"] = msg["content"]
            break

    # Find last assistant response
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg["content"]
            topic["last_response_summary"] = content[:200] if content else None
            break

    # Extract metadata from last message if available
    for msg in reversed(messages):
        metadata = msg.get("metadata", {})
        if metadata:
            if metadata.get("sql_used"):
                topic["last_sql"] = metadata["sql_used"]
            if metadata.get("sources_used"):
                topic["last_sources"] = metadata["sources_used"]
            break

    return topic


def format_history_for_display(messages: list[dict]) -> list[dict]:
    """Format message history for Streamlit chat display."""
    display_messages = []
    for msg in messages:
        display_msg = {
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
        }
        # Include metadata for expandable sections
        metadata = msg.get("metadata", {})
        if metadata:
            display_msg["sql"] = metadata.get("sql_used")
            display_msg["sources"] = metadata.get("sources_used", [])
            display_msg["chart_data"] = metadata.get("has_chart", False)
        display_messages.append(display_msg)
    return display_messages
