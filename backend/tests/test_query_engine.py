"""Tests for the query engine components."""

import pandas as pd
import duckdb
import pytest

from src.query.intent import _fallback_classify
from src.query.rag_engine import build_rag_context
from src.visualization.charts import generate_chart, _detect_chart_type
from src.semantic.resolver import resolve_metric, get_all_metric_names, load_semantic_layer


class TestFallbackIntentClassifier:
    """Test rule-based intent classification."""

    def test_greeting(self):
        result = _fallback_classify("hello")
        assert result["intent"] == "greeting"

    def test_change_intent(self):
        result = _fallback_classify("Why did revenue drop last month?")
        assert result["intent"] == "change"

    def test_compare_intent(self):
        result = _fallback_classify("Compare region A vs region B")
        assert result["intent"] == "compare"

    def test_breakdown_intent(self):
        result = _fallback_classify("Show breakdown by category")
        assert result["intent"] == "breakdown"

    def test_summarize_intent(self):
        result = _fallback_classify("Give me a summary of this data")
        assert result["intent"] == "summarize"

    def test_image_intent(self):
        result = _fallback_classify("What does the diagram show?")
        assert result["intent"] == "image_query"
        assert result["needs_vision"] is True

    def test_followup(self):
        result = _fallback_classify("why?")
        assert result["is_followup"] is True


class TestRAGContext:
    """Test RAG context building."""

    def test_empty_chunks(self):
        result = build_rag_context([])
        assert "No relevant" in result

    def test_with_chunks(self):
        chunks = [
            {"text": "Revenue was $1M in Q1", "source": "report.pdf", "page": 3},
            {"text": "Costs increased by 15%", "source": "report.pdf", "page": 5},
        ]
        result = build_rag_context(chunks)
        assert "Revenue was $1M" in result
        assert "report.pdf" in result
        assert "page 3" in result


class TestSemanticResolver:
    """Test metric resolution."""

    def test_resolve_by_name(self):
        result = resolve_metric("revenue")
        assert result is not None
        assert result["key"] == "revenue"

    def test_resolve_by_alias(self):
        result = resolve_metric("total sales")
        assert result is not None
        assert result["key"] == "revenue"

    def test_resolve_unknown(self):
        result = resolve_metric("xyzzy_metric")
        assert result is None

    def test_get_all_names(self):
        names = get_all_metric_names()
        assert len(names) > 0
        assert "Revenue" in names


class TestChartDetection:
    """Test automatic chart type selection."""

    def test_bar_chart(self):
        df = pd.DataFrame({"region": ["North", "South"], "revenue": [100, 200]})
        chart_type = _detect_chart_type(df)
        assert chart_type in ("bar", "pie")

    def test_line_chart(self):
        df = pd.DataFrame({"date": ["2024-01", "2024-02"], "revenue": [100, 200]})
        chart_type = _detect_chart_type(df)
        assert chart_type == "line"

    def test_single_value(self):
        df = pd.DataFrame({"total_revenue": [50000]})
        chart_type = _detect_chart_type(df)
        assert chart_type == "metric"

    def test_generate_bar_chart(self):
        df = pd.DataFrame({"region": ["North", "South", "East"], "revenue": [100, 200, 150]})
        fig = generate_chart(df, intent="breakdown")
        assert fig is not None

    def test_generate_empty(self):
        df = pd.DataFrame()
        fig = generate_chart(df)
        assert fig is None
