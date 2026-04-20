"""Load structured files (CSV, Excel, JSON, Parquet) into DuckDB."""

import os
import re
import pandas as pd


def _sanitize_table_name(name: str) -> str:
    """Convert filename to a safe DuckDB table name."""
    name = os.path.splitext(name)[0]
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_").lower()
    if name and name[0].isdigit():
        name = "t_" + name
    return name or "uploaded_table"


def _sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean column names for SQL compatibility."""
    new_cols = []
    for col in df.columns:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", str(col))
        clean = re.sub(r"_+", "_", clean).strip("_").lower()
        if clean and clean[0].isdigit():
            clean = "col_" + clean
        if not clean:
            clean = "column"
        # Handle duplicates
        base = clean
        counter = 1
        while clean in new_cols:
            clean = f"{base}_{counter}"
            counter += 1
        new_cols.append(clean)
    df.columns = new_cols
    return df


def load_structured_file(file_path: str, file_name: str, duckdb_conn) -> dict:
    """Load a structured file into DuckDB and return metadata."""
    ext = os.path.splitext(file_name)[1].lower()
    table_name = _sanitize_table_name(file_name)

    try:
        if ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        elif ext == ".json":
            df = pd.read_json(file_path)
        elif ext == ".parquet":
            df = pd.read_parquet(file_path)
        else:
            return {"source_name": file_name, "source_type": "structured", "error": f"Unsupported: {ext}"}

        df = _sanitize_columns(df)

        # Register in DuckDB
        duckdb_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        duckdb_conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")

        # Gather metadata
        row_count = len(df)
        columns = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            sample_values = df[col].dropna().head(3).tolist()
            columns.append({
                "name": col,
                "type": dtype,
                "sample_values": sample_values,
                "null_count": int(df[col].isnull().sum()),
            })

        return {
            "source_name": file_name,
            "source_type": "structured",
            "table_name": table_name,
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
        }

    except Exception as e:
        return {"source_name": file_name, "source_type": "structured", "error": str(e)}
