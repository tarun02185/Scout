"""Resolve user terms to consistent metric definitions from the semantic layer."""

import os
import yaml


_METRICS_PATH = os.path.join(os.path.dirname(__file__), "metrics.yaml")


def load_semantic_layer() -> dict:
    """Load the metrics dictionary from YAML."""
    with open(_METRICS_PATH, "r") as f:
        return yaml.safe_load(f)


def resolve_metric(user_term: str, semantic_layer: dict | None = None) -> dict | None:
    """Find a metric definition matching the user's term.

    Returns the metric dict if found, None otherwise.
    """
    if semantic_layer is None:
        semantic_layer = load_semantic_layer()

    user_term_lower = user_term.lower().strip()
    metrics = semantic_layer.get("metrics", {})

    for key, metric in metrics.items():
        # Check exact name match
        if user_term_lower == key or user_term_lower == metric.get("display_name", "").lower():
            return {**metric, "key": key}
        # Check aliases
        aliases = [a.lower() for a in metric.get("aliases", [])]
        if user_term_lower in aliases:
            return {**metric, "key": key}

    return None


def get_all_metric_names(semantic_layer: dict | None = None) -> list[str]:
    """Get all known metric names and aliases for prompt context."""
    if semantic_layer is None:
        semantic_layer = load_semantic_layer()

    names = []
    for key, metric in semantic_layer.get("metrics", {}).items():
        names.append(metric.get("display_name", key))
        names.extend(metric.get("aliases", []))
    return names


def build_semantic_context(semantic_layer: dict | None = None) -> str:
    """Build a text block describing all metrics for LLM context."""
    if semantic_layer is None:
        semantic_layer = load_semantic_layer()

    lines = ["### Metric Definitions (use these consistently):\n"]
    for key, metric in semantic_layer.get("metrics", {}).items():
        display = metric.get("display_name", key)
        desc = metric.get("description", "")
        formula = metric.get("formula", "")
        aliases = ", ".join(metric.get("aliases", []))
        lines.append(f"- **{display}**: {desc}")
        if formula:
            lines.append(f"  SQL: `{formula}`")
        if aliases:
            lines.append(f"  Also known as: {aliases}")
        lines.append("")

    # Time and category dimensions
    time_dims = semantic_layer.get("time_dimensions", [])
    cat_dims = semantic_layer.get("category_dimensions", [])
    if time_dims:
        lines.append(f"### Time columns to look for: {', '.join(time_dims)}")
    if cat_dims:
        lines.append(f"### Category columns for breakdowns: {', '.join(cat_dims)}")

    return "\n".join(lines)
