"""Load log files — parse into structured format + store raw in vector DB."""

import os
import re
import pandas as pd

from src.config import CHUNK_SIZE, CHUNK_OVERLAP


# Common log patterns
LOG_PATTERNS = {
    "apache_combined": re.compile(
        r'(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+) \S+" (?P<status>\d+) (?P<size>\S+)'
    ),
    "syslog": re.compile(
        r"(?P<timestamp>\w{3}\s+\d+\s+\d+:\d+:\d+)\s+(?P<host>\S+)\s+(?P<process>\S+?):\s+(?P<message>.*)"
    ),
    "generic_timestamp": re.compile(
        r"(?P<timestamp>\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2}[^\s]*)\s+\[?(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\]?\s+(?P<message>.*)"
    ),
    "simple": re.compile(
        r"\[?(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)\]?\s*[-:]\s*(?P<message>.*)"
    ),
}


def _detect_log_pattern(lines: list[str]) -> str | None:
    """Try each pattern against the first few lines to detect format."""
    sample = lines[:20]
    best_pattern = None
    best_count = 0

    for name, pattern in LOG_PATTERNS.items():
        matches = sum(1 for line in sample if pattern.match(line.strip()))
        if matches > best_count:
            best_count = matches
            best_pattern = name

    return best_pattern if best_count >= 3 else None


def _parse_log_to_dataframe(lines: list[str], pattern_name: str) -> pd.DataFrame:
    """Parse log lines using detected pattern into a DataFrame."""
    pattern = LOG_PATTERNS[pattern_name]
    records = []
    for line in lines:
        match = pattern.match(line.strip())
        if match:
            records.append(match.groupdict())
        elif records:
            # Append to previous message (multi-line log entry)
            records[-1]["message"] = records[-1].get("message", "") + " " + line.strip()

    return pd.DataFrame(records) if records else pd.DataFrame()


def load_log_file(file_path: str, file_name: str, duckdb_conn, chroma_collection) -> dict:
    """Load a log file — parse structured data + store raw text for RAG."""
    try:
        with open(file_path, "r", errors="ignore") as f:
            content = f.read()
        lines = content.splitlines()

        if not lines:
            return {"source_name": file_name, "source_type": "log", "error": "Empty file"}

        # Try structured parsing
        pattern_name = _detect_log_pattern(lines)
        table_name = None
        row_count = 0

        if pattern_name:
            df = _parse_log_to_dataframe(lines, pattern_name)
            if not df.empty:
                table_name = re.sub(r"[^a-zA-Z0-9_]", "_", os.path.splitext(file_name)[0]).lower()
                table_name = f"log_{table_name}"
                duckdb_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                duckdb_conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
                row_count = len(df)

        # Also store raw content in vector DB for text search
        chunks = []
        for i in range(0, len(content), CHUNK_SIZE - CHUNK_OVERLAP):
            chunk = content[i : i + CHUNK_SIZE].strip()
            if chunk:
                chunks.append(chunk)

        if chunks and chroma_collection is not None:
            ids = [f"{file_name}_log_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"source": file_name, "type": "log", "chunk_index": i} for i in range(len(chunks))]
            chroma_collection.add(ids=ids, documents=chunks, metadatas=metadatas)

        return {
            "source_name": file_name,
            "source_type": "log",
            "table_name": table_name,
            "row_count": row_count,
            "line_count": len(lines),
            "chunk_count": len(chunks),
            "pattern_detected": pattern_name,
        }

    except Exception as e:
        return {"source_name": file_name, "source_type": "log", "error": str(e)}
