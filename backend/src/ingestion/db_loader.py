"""Load SQLite database files by attaching them to DuckDB."""

import os
import re
import sqlite3
import pandas as pd


def load_database(file_path: str, file_name: str, duckdb_conn) -> dict:
    """Load a SQLite database by importing its tables into DuckDB."""
    try:
        prefix = re.sub(r"[^a-zA-Z0-9_]", "_", os.path.splitext(file_name)[0]).lower()

        # Read tables from SQLite
        sqlite_conn = sqlite3.connect(file_path)
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        imported_tables = []
        total_rows = 0

        for table in tables:
            try:
                df = pd.read_sql(f"SELECT * FROM [{table}]", sqlite_conn)
                duckdb_table = f"{prefix}_{table}".lower()
                duckdb_table = re.sub(r"[^a-zA-Z0-9_]", "_", duckdb_table)
                duckdb_conn.execute(f"DROP TABLE IF EXISTS {duckdb_table}")
                duckdb_conn.execute(f"CREATE TABLE {duckdb_table} AS SELECT * FROM df")

                imported_tables.append({
                    "original_name": table,
                    "duckdb_name": duckdb_table,
                    "row_count": len(df),
                    "columns": list(df.columns),
                })
                total_rows += len(df)
            except Exception:
                continue

        sqlite_conn.close()

        return {
            "source_name": file_name,
            "source_type": "database",
            "tables": imported_tables,
            "table_count": len(imported_tables),
            "total_rows": total_rows,
        }

    except Exception as e:
        return {"source_name": file_name, "source_type": "database", "error": str(e)}
