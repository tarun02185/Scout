"""Tests for the ingestion engine."""

import os
import tempfile

import duckdb
import pandas as pd
import pytest

from src.ingestion.csv_loader import load_structured_file, _sanitize_table_name, _sanitize_columns
from src.ingestion.router import detect_file_type


class TestFileTypeDetection:
    """Test file type routing."""

    def test_csv(self):
        assert detect_file_type("data.csv") == "structured"

    def test_xlsx(self):
        assert detect_file_type("report.xlsx") == "structured"

    def test_json(self):
        assert detect_file_type("config.json") == "structured"

    def test_pdf(self):
        assert detect_file_type("report.pdf") == "document"

    def test_txt(self):
        assert detect_file_type("notes.txt") == "document"

    def test_log(self):
        assert detect_file_type("server.log") == "document"

    def test_png(self):
        assert detect_file_type("diagram.png") == "image"

    def test_jpg(self):
        assert detect_file_type("photo.jpg") == "image"

    def test_sqlite(self):
        assert detect_file_type("app.db") == "database"

    def test_unknown(self):
        assert detect_file_type("file.xyz") == "unknown"


class TestSanitizeTableName:
    """Test table name sanitization."""

    def test_simple(self):
        assert _sanitize_table_name("sales.csv") == "sales"

    def test_spaces(self):
        assert _sanitize_table_name("my data file.csv") == "my_data_file"

    def test_starts_with_number(self):
        result = _sanitize_table_name("2024_data.csv")
        assert result.startswith("t_")

    def test_special_chars(self):
        result = _sanitize_table_name("data@#$.csv")
        assert all(c.isalnum() or c == "_" for c in result)


class TestCSVLoader:
    """Test CSV loading into DuckDB."""

    def test_load_csv(self):
        # Create a temp CSV
        df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25], "revenue": [1000, 2000]})
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            df.to_csv(f, index=False)
            tmp_path = f.name

        conn = duckdb.connect(":memory:")
        result = load_structured_file(tmp_path, "test_data.csv", conn)

        assert result["source_type"] == "structured"
        assert result["row_count"] == 2
        assert result["column_count"] == 3
        assert "error" not in result

        # Verify data is in DuckDB
        queried = conn.execute(f"SELECT COUNT(*) FROM {result['table_name']}").fetchone()[0]
        assert queried == 2

        conn.close()
        os.unlink(tmp_path)

    def test_sanitize_columns(self):
        df = pd.DataFrame({"Column With Spaces": [1], "123start": [2], "normal": [3]})
        result = _sanitize_columns(df)
        for col in result.columns:
            assert all(c.isalnum() or c == "_" for c in col)


class TestPIIDetection:
    """Test PII detection and masking."""

    def test_detect_email(self):
        from src.guardrails.pii import detect_pii_in_text
        findings = detect_pii_in_text("Contact john@example.com for details")
        assert any(f["type"] == "email" for f in findings)

    def test_detect_phone(self):
        from src.guardrails.pii import detect_pii_in_text
        findings = detect_pii_in_text("Call 555-123-4567 now")
        assert any(f["type"] == "phone" for f in findings)

    def test_mask_email(self):
        from src.guardrails.pii import mask_pii_in_text
        result = mask_pii_in_text("Email: user@test.com")
        assert "user@test.com" not in result
        assert "[EMAIL HIDDEN]" in result

    def test_pii_column_check(self):
        from src.guardrails.pii import check_columns_for_pii
        flagged = check_columns_for_pii(["name", "email", "revenue", "phone_number"])
        assert "email" in flagged
        assert "phone_number" in flagged
        assert "revenue" not in flagged
