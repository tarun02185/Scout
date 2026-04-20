"""File type detection and routing to appropriate loaders."""

import os
from pathlib import Path

from src.config import SUPPORTED_EXTENSIONS


def detect_file_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    for category, extensions in SUPPORTED_EXTENSIONS.items():
        if ext in extensions:
            return category
    return "unknown"


def get_file_extension(file_path: str) -> str:
    return Path(file_path).suffix.lower()


def route_file(file_path: str, session_id: str, duckdb_conn, chroma_collection, original_name: str | None = None):
    """Route a file to the appropriate loader.

    Args:
        original_name: The user's original filename (not the temp name).
    """
    from src.ingestion.csv_loader import load_structured_file
    from src.ingestion.pdf_loader import load_pdf
    from src.ingestion.image_loader import load_image
    from src.ingestion.log_loader import load_log_file
    from src.ingestion.db_loader import load_database

    file_type = detect_file_type(file_path)
    # Use original name if provided, otherwise fall back to basename
    file_name = original_name or os.path.basename(file_path)
    ext = get_file_extension(file_path)

    if file_type == "structured":
        return load_structured_file(file_path, file_name, duckdb_conn)
    elif file_type == "document":
        if ext == ".pdf":
            return load_pdf(file_path, file_name, chroma_collection, duckdb_conn)
        elif ext == ".log":
            return load_log_file(file_path, file_name, duckdb_conn, chroma_collection)
        else:
            return load_pdf(file_path, file_name, chroma_collection, duckdb_conn)
    elif file_type == "image":
        return load_image(file_path, file_name, chroma_collection)
    elif file_type == "database":
        return load_database(file_path, file_name, duckdb_conn)
    else:
        return {"source_name": file_name, "source_type": "unknown", "error": f"Unsupported: {ext}"}
