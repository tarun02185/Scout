"""Tests for SQL validation guardrails."""

import pytest
from src.guardrails.validator import validate_sql


class TestValidateSQL:
    """Test SQL safety validation."""

    def test_valid_select(self):
        is_safe, reason = validate_sql("SELECT * FROM users")
        assert is_safe is True

    def test_valid_select_with_where(self):
        is_safe, _ = validate_sql("SELECT name, age FROM users WHERE age > 21")
        assert is_safe is True

    def test_valid_cte(self):
        sql = "WITH cte AS (SELECT * FROM orders) SELECT * FROM cte"
        is_safe, _ = validate_sql(sql)
        assert is_safe is True

    def test_valid_aggregate(self):
        sql = "SELECT region, SUM(revenue) as total FROM sales GROUP BY region ORDER BY total DESC"
        is_safe, _ = validate_sql(sql)
        assert is_safe is True

    def test_reject_drop(self):
        is_safe, reason = validate_sql("DROP TABLE users")
        assert is_safe is False
        assert "SELECT" in reason or "Forbidden" in reason

    def test_reject_delete(self):
        is_safe, reason = validate_sql("DELETE FROM users WHERE id = 1")
        assert is_safe is False

    def test_reject_insert(self):
        is_safe, reason = validate_sql("INSERT INTO users VALUES (1, 'test')")
        assert is_safe is False

    def test_reject_update(self):
        is_safe, reason = validate_sql("UPDATE users SET name = 'hack' WHERE id = 1")
        assert is_safe is False

    def test_reject_multiple_statements(self):
        is_safe, reason = validate_sql("SELECT 1; DROP TABLE users")
        assert is_safe is False

    def test_reject_sql_comment_injection(self):
        is_safe, reason = validate_sql("SELECT * FROM users -- WHERE admin = true")
        assert is_safe is False

    def test_empty_query(self):
        is_safe, reason = validate_sql("")
        assert is_safe is False

    def test_semicolon_at_end_is_ok(self):
        is_safe, _ = validate_sql("SELECT * FROM users;")
        assert is_safe is True
