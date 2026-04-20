"""Auto chart generation — picks the right chart type and generates Plotly figures."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _detect_chart_type(df: pd.DataFrame, intent: str = "") -> str:
    """Detect the best chart type based on data shape and intent."""
    if df.empty:
        return "none"

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower() or "month" in c.lower() or "year" in c.lower()]

    n_rows = len(df)
    n_num = len(num_cols)
    n_cat = len(cat_cols)

    # Intent-based overrides
    if intent in ("compare", "change"):
        if date_cols:
            return "line"
        elif n_cat >= 1 and n_num >= 1:
            return "grouped_bar"
        return "bar"

    if intent == "breakdown":
        if n_rows <= 8:
            return "pie"
        return "bar"

    if intent == "summarize":
        if date_cols and n_num >= 1:
            return "line"
        return "bar"

    # Data-shape heuristics
    if date_cols and n_num >= 1:
        return "line"
    elif n_cat == 1 and n_num == 1:
        if n_rows <= 8:
            return "pie"
        return "bar"
    elif n_cat >= 1 and n_num >= 1:
        return "bar"
    elif n_num >= 2:
        return "scatter"
    elif n_rows == 1:
        return "metric"

    return "table"


def _make_title_descriptive(df: pd.DataFrame, intent: str) -> str:
    """Generate a story-telling chart title."""
    cols = list(df.columns)
    num_cols = df.select_dtypes(include="number").columns.tolist()

    if intent == "compare" and len(cols) >= 2:
        return f"{cols[-1]} Comparison by {cols[0]}"
    elif intent == "breakdown" and num_cols:
        return f"What Makes Up {num_cols[0].replace('_', ' ').title()}"
    elif intent == "change" and num_cols:
        return f"How {num_cols[0].replace('_', ' ').title()} Changed Over Time"
    elif intent == "summarize":
        return "Key Metrics Overview"

    if len(cols) >= 2:
        return f"{cols[-1].replace('_', ' ').title()} by {cols[0].replace('_', ' ').title()}"
    return "Data Overview"


def generate_chart(df: pd.DataFrame, intent: str = "", title: str = "") -> go.Figure | None:
    """Generate an appropriate Plotly chart from a DataFrame.

    Returns a Plotly figure or None if no chart is appropriate.
    """
    if df is None or df.empty:
        return None

    chart_type = _detect_chart_type(df, intent)
    if chart_type == "none":
        return None

    if not title:
        title = _make_title_descriptive(df, intent)

    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()
                 or "month" in c.lower() or "year" in c.lower() or "week" in c.lower()]

    # Color scheme
    colors = ["#5B2C8E", "#8B5CF6", "#A78BFA", "#C4B5FD", "#7C3AED", "#6D28D9", "#4C1D95"]

    try:
        if chart_type == "line":
            x_col = date_cols[0] if date_cols else cat_cols[0] if cat_cols else df.columns[0]
            y_col = num_cols[0] if num_cols else df.columns[-1]
            color_col = cat_cols[0] if cat_cols and cat_cols[0] != x_col else None
            fig = px.line(
                df, x=x_col, y=y_col, color=color_col, title=title,
                color_discrete_sequence=colors, markers=True,
            )

        elif chart_type == "bar":
            x_col = cat_cols[0] if cat_cols else df.columns[0]
            y_col = num_cols[0] if num_cols else df.columns[-1]
            fig = px.bar(
                df, x=x_col, y=y_col, title=title,
                color_discrete_sequence=colors,
            )
            fig.update_layout(xaxis_tickangle=-45)

        elif chart_type == "grouped_bar":
            x_col = cat_cols[0] if cat_cols else df.columns[0]
            y_col = num_cols[0] if num_cols else df.columns[-1]
            color_col = cat_cols[1] if len(cat_cols) > 1 else None
            fig = px.bar(
                df, x=x_col, y=y_col, color=color_col, barmode="group",
                title=title, color_discrete_sequence=colors,
            )

        elif chart_type == "pie":
            name_col = cat_cols[0] if cat_cols else df.columns[0]
            value_col = num_cols[0] if num_cols else df.columns[-1]
            fig = px.pie(
                df, names=name_col, values=value_col, title=title,
                color_discrete_sequence=colors,
            )

        elif chart_type == "scatter":
            x_col = num_cols[0]
            y_col = num_cols[1] if len(num_cols) > 1 else num_cols[0]
            color_col = cat_cols[0] if cat_cols else None
            fig = px.scatter(
                df, x=x_col, y=y_col, color=color_col, title=title,
                color_discrete_sequence=colors,
            )

        elif chart_type == "metric":
            # Single value display as indicator
            fig = go.Figure()
            for i, col in enumerate(num_cols[:4]):
                fig.add_trace(go.Indicator(
                    mode="number",
                    value=df[col].iloc[0],
                    title={"text": col.replace("_", " ").title()},
                    domain={"x": [i / min(len(num_cols), 4), (i + 1) / min(len(num_cols), 4)], "y": [0, 1]},
                ))
            fig.update_layout(title=title)

        else:
            return None

        # Style the chart
        fig.update_layout(
            template="plotly_white",
            font=dict(family="Inter, sans-serif", size=13),
            title_font_size=16,
            margin=dict(t=60, b=40, l=40, r=20),
            height=400,
        )

        return fig

    except Exception:
        return None
