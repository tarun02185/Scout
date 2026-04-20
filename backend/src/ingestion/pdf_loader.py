"""Load PDF and text documents — extract text, tables, and images."""

import os
import re
import fitz  # PyMuPDF
import pandas as pd
from src.config import CHUNK_SIZE, CHUNK_OVERLAP


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Split text into overlapping chunks with metadata."""
    # Clean the text
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    if len(text) <= chunk_size:
        return [{"text": text.strip(), "chunk_index": 0}] if text.strip() else []

    chunks = []
    start = 0
    chunk_index = 0
    while start < len(text):
        end = start + chunk_size
        # Try to break at sentence boundary
        if end < len(text):
            last_period = text.rfind(".", start, end)
            last_newline = text.rfind("\n", start, end)
            break_point = max(last_period, last_newline)
            if break_point > start + chunk_size // 2:
                end = break_point + 1

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"text": chunk_text, "chunk_index": chunk_index})
            chunk_index += 1
        start = end - overlap

    return chunks


def _extract_images_from_pdf(doc: fitz.Document, file_name: str) -> list[dict]:
    """Extract images from PDF pages and return as metadata."""
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                images.append({
                    "page": page_num + 1,
                    "image_index": img_index,
                    "image_bytes": image_bytes,
                    "image_ext": image_ext,
                    "source_file": file_name,
                })
            except Exception:
                continue
    return images


def _extract_tables_from_pdf(file_path: str) -> list[pd.DataFrame]:
    """Try to extract tables from PDF using pdfplumber."""
    tables = []
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                for table in page_tables:
                    if table and len(table) > 1:
                        df = pd.DataFrame(table[1:], columns=table[0])
                        df = df.dropna(how="all")
                        if not df.empty:
                            tables.append(df)
    except Exception:
        pass
    return tables


def load_pdf(file_path: str, file_name: str, chroma_collection, duckdb_conn) -> dict:
    """Load a PDF/text file: extract text chunks, images, and tables."""
    ext = os.path.splitext(file_name)[1].lower()

    try:
        # Extract text
        if ext == ".pdf":
            doc = fitz.open(file_path)
            full_text = ""
            page_texts = []
            for page_num in range(len(doc)):
                page_text = doc[page_num].get_text()
                page_texts.append({"page": page_num + 1, "text": page_text})
                full_text += f"\n--- Page {page_num + 1} ---\n{page_text}"

            # Extract images
            images = _extract_images_from_pdf(doc, file_name)
            doc.close()

            # Extract tables and load into DuckDB
            tables = _extract_tables_from_pdf(file_path)
        else:
            # Plain text files (.txt, .md)
            with open(file_path, "r", errors="ignore") as f:
                full_text = f.read()
            page_texts = [{"page": 1, "text": full_text}]
            images = []
            tables = []

        # Chunk the text
        chunks = _chunk_text(full_text)

        # Store chunks in ChromaDB
        if chunks and chroma_collection is not None:
            ids = [f"{file_name}_chunk_{c['chunk_index']}" for c in chunks]
            documents = [c["text"] for c in chunks]
            metadatas = [{"source": file_name, "chunk_index": c["chunk_index"]} for c in chunks]

            # Find which page each chunk belongs to
            for i, chunk in enumerate(chunks):
                for pt in page_texts:
                    if chunk["text"][:100] in pt["text"]:
                        metadatas[i]["page"] = pt["page"]
                        break

            chroma_collection.add(ids=ids, documents=documents, metadatas=metadatas)

        # Load extracted tables into DuckDB
        table_names = []
        for idx, df in enumerate(tables):
            table_name = re.sub(r"[^a-zA-Z0-9_]", "_", os.path.splitext(file_name)[0]).lower()
            table_name = f"{table_name}_table_{idx}"
            # Clean column names
            df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).lower().strip("_") or f"col_{i}"
                          for i, c in enumerate(df.columns)]
            try:
                duckdb_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                duckdb_conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")
                table_names.append(table_name)
            except Exception:
                continue

        return {
            "source_name": file_name,
            "source_type": "document",
            "chunk_count": len(chunks),
            "page_count": len(page_texts),
            "image_count": len(images),
            "table_count": len(tables),
            "extracted_table_names": table_names,
            "has_images": len(images) > 0,
            "images": images,  # kept in memory for vision queries
        }

    except Exception as e:
        return {"source_name": file_name, "source_type": "document", "error": str(e)}
