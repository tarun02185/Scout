"""Scout FastAPI Backend — REST API with streaming and Google OAuth."""

import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager

import duckdb
import chromadb
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

from src.ingestion.router import route_file
from src.query.orchestrator import process_query, process_query_stream
from src.chat.session_manager import (
    create_session, list_sessions, get_session_history,
    add_message, delete_session, rename_session, save_session_files,
    remove_session_file,
)
from src.chat.history import build_conversation_context
from src.guardrails.pii import mask_pii_in_text_with_count, check_columns_for_pii
from src.guardrails.audit import log_pii_mask
from src.semantic.resolver import load_semantic_layer
from src.auth import verify_google_token, get_or_create_user, get_current_user


# ── Global state ─────────────────────────────────────────────────────────────
session_stores: dict[str, dict] = {}


def get_or_create_store(session_id: str) -> dict:
    if session_id not in session_stores:
        chroma_client = chromadb.Client()
        session_stores[session_id] = {
            "duckdb_conn": duckdb.connect(":memory:"),
            "chroma_client": chroma_client,
            "chroma_collection": chroma_client.get_or_create_collection(
                name="documents", metadata={"hnsw:space": "cosine"}
            ),
            "sources": [],
            "uploaded_files": set(),
        }
    return session_stores[session_id]


def cleanup_store(session_id: str):
    store = session_stores.pop(session_id, None)
    if store:
        try:
            store["duckdb_conn"].close()
        except Exception:
            pass


# ── App setup ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.semantic_layer = load_semantic_layer()
    except Exception:
        app.state.semantic_layer = None
    yield
    for sid in list(session_stores.keys()):
        cleanup_store(sid)


app = FastAPI(
    title="Scout API",
    description="Talk to your data in plain English",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    session_id: str
    query: str

class RenameRequest(BaseModel):
    title: str

class GoogleLoginRequest(BaseModel):
    credential: str

class UrlUploadRequest(BaseModel):
    url: str
    crawl_multi: bool = True
    max_pages: int | None = None
    max_depth: int | None = None
    path_filter: str | None = None


# ── Auth endpoints ───────────────────────────────────────────────────────────

@app.post("/api/auth/google")
async def google_login(body: GoogleLoginRequest):
    """Verify Google ID token and return user info + session token."""
    user_info = verify_google_token(body.credential)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    user = get_or_create_user(user_info)
    return {
        "user": user,
        "token": user_info["sub"],  # Use Google sub as session token
    }


@app.post("/api/auth/guest")
async def guest_login():
    """Create a guest user — no Google credentials needed."""
    import uuid
    guest_id = f"guest_{uuid.uuid4().hex[:8]}"
    user_info = {
        "sub": guest_id,
        "email": f"{guest_id}@guest.datalens",
        "name": "Guest User",
        "picture": "",
    }
    user = get_or_create_user(user_info)
    return {"user": user, "token": guest_id}


@app.get("/api/auth/me")
async def get_me(user=Depends(get_current_user)):
    """Get current authenticated user."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": user}


# ── Session endpoints ────────────────────────────────────────────────────────

@app.post("/api/sessions")
def create_new_session():
    session_id = create_session()
    return {"session_id": session_id}


@app.get("/api/sessions")
def get_all_sessions():
    return {"sessions": list_sessions()}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    messages = get_session_history(session_id)
    store = session_stores.get(session_id, {})
    sources = [
        {k: v for k, v in s.items() if k not in ("images", "image_bytes")}
        for s in store.get("sources", [])
    ]
    return {"session_id": session_id, "messages": messages, "sources": sources}


@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str):
    delete_session(session_id)
    cleanup_store(session_id)
    return {"status": "deleted"}


@app.patch("/api/sessions/{session_id}")
def update_session_title(session_id: str, body: RenameRequest):
    rename_session(session_id, body.title)
    return {"status": "renamed"}


# ── File upload ──────────────────────────────────────────────────────────────

@app.post("/api/sessions/{session_id}/upload")
async def upload_files(session_id: str, files: list[UploadFile] = File(...)):
    store = get_or_create_store(session_id)
    results = []

    for uploaded_file in files:
        if uploaded_file.filename in store["uploaded_files"]:
            results.append({"file": uploaded_file.filename, "status": "already_uploaded"})
            continue

        suffix = os.path.splitext(uploaded_file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await uploaded_file.read()
            tmp.write(content)
            tmp_path = tmp.name

        metadata = route_file(tmp_path, session_id, store["duckdb_conn"], store["chroma_collection"], original_name=uploaded_file.filename)

        if metadata.get("source_type") != "image":
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if "error" not in metadata:
            store["sources"].append(metadata)
            store["uploaded_files"].add(uploaded_file.filename)
            save_session_files(session_id, uploaded_file.filename, {
                k: v for k, v in metadata.items() if k not in ("images", "image_bytes")
            })

            pii_warnings = []
            if metadata.get("columns"):
                col_names = [c["name"] for c in metadata["columns"]]
                pii_cols = check_columns_for_pii(col_names)
                if pii_cols:
                    pii_warnings = pii_cols

            results.append({
                "file": uploaded_file.filename, "status": "success",
                "metadata": {k: v for k, v in metadata.items() if k not in ("images", "image_bytes")},
                "pii_warnings": pii_warnings,
            })
        else:
            results.append({"file": uploaded_file.filename, "status": "error", "error": metadata["error"]})

    return {"results": results}


# ── Remove a source (file, document, URL, image) from a session ─────────────

@app.delete("/api/sessions/{session_id}/sources/{source_name:path}")
def remove_source(session_id: str, source_name: str):
    """Delete a single source from a session, cleaning up DuckDB + ChromaDB + persisted metadata.

    `source_name` uses `:path` so names like `en.wikipedia.org/wiki/Foo` pass through.
    """
    store = session_stores.get(session_id)
    if not store:
        raise HTTPException(status_code=404, detail="Session not found")

    match = next((s for s in store["sources"] if s.get("source_name") == source_name), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_name}' not found in session")

    # 1. DuckDB: drop the table(s) that this source loaded.
    duck = store["duckdb_conn"]
    tables_to_drop: list[str] = []
    if match.get("table_name"):
        tables_to_drop.append(match["table_name"])
    for t in match.get("tables", []) or []:
        tn = t.get("duckdb_name") if isinstance(t, dict) else None
        if tn:
            tables_to_drop.append(tn)
    for tn in tables_to_drop:
        try:
            duck.execute(f'DROP TABLE IF EXISTS "{tn}"')
        except Exception:
            pass

    # 2. ChromaDB: delete any chunks whose metadata.source matches this source.
    try:
        store["chroma_collection"].delete(where={"source": source_name})
    except Exception:
        pass

    # 3. In-memory session state.
    store["sources"] = [s for s in store["sources"] if s.get("source_name") != source_name]
    store["uploaded_files"].discard(source_name)

    # 4. Persisted metadata row.
    remove_session_file(session_id, source_name)

    return {"status": "removed", "source_name": source_name, "tables_dropped": tables_to_drop}


# ── URL upload (website crawl) ────────────────────────────────────────────────

@app.post("/api/sessions/{session_id}/url")
def upload_url(session_id: str, body: UrlUploadRequest):
    """Crawl a website and index its pages for RAG.

    Runs entirely inside the upload endpoint; the query hot path is untouched.
    """
    from src.ingestion.url_loader import load_url
    from src.config import SCRAPE_MAX_PAGES, SCRAPE_MAX_DEPTH

    store = get_or_create_store(session_id)

    # Derive a short, human-readable source name from the URL.
    import urllib.parse
    parts = urllib.parse.urlsplit(body.url)
    source_name = parts.netloc + (parts.path if len(parts.path) > 1 else "")
    source_name = source_name.rstrip("/")[:80] or body.url[:80]

    if source_name in store["uploaded_files"]:
        return {"file": source_name, "status": "already_uploaded"}

    metadata = load_url(
        url=body.url,
        source_name=source_name,
        chroma_collection=store["chroma_collection"],
        duckdb_conn=store["duckdb_conn"],
        max_pages=min(body.max_pages or SCRAPE_MAX_PAGES, SCRAPE_MAX_PAGES),
        max_depth=min(body.max_depth or SCRAPE_MAX_DEPTH, SCRAPE_MAX_DEPTH),
        path_filter=body.path_filter,
        crawl_multi=body.crawl_multi,
    )

    if "error" in metadata:
        raise HTTPException(status_code=400, detail=metadata["error"])

    store["sources"].append(metadata)
    store["uploaded_files"].add(source_name)
    save_session_files(session_id, source_name, {
        k: v for k, v in metadata.items() if k not in ("images", "image_bytes")
    })

    return {"file": source_name, "status": "success", "metadata": metadata}


# ── Query (non-streaming, kept for compatibility) ────────────────────────────

@app.post("/api/query")
def run_query(body: QueryRequest):
    store = get_or_create_store(body.session_id)
    add_message(body.session_id, "user", body.query)

    history_msgs = get_session_history(body.session_id)
    history = build_conversation_context(history_msgs[:-1])

    result = process_query(
        user_query=body.query,
        duckdb_conn=store["duckdb_conn"],
        chroma_collection=store["chroma_collection"],
        available_sources=store["sources"],
        conversation_history=history,
        semantic_layer=app.state.semantic_layer,
        session_id=body.session_id,
    )

    response_text, mask_count = mask_pii_in_text_with_count(result["response"])
    log_pii_mask(body.session_id, mask_count, where="non_streaming_response")
    chart_data = None
    if result.get("chart_data") is not None and not result["chart_data"].empty:
        df = result["chart_data"]
        chart_data = {
            "columns": list(df.columns),
            "rows": df.to_dict(orient="records"),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        }

    add_message(body.session_id, "assistant", response_text, {
        "sql_used": result.get("sql_used"),
        "sources_used": result.get("sources_used", []),
        "intent": result.get("intent", {}),
        "has_chart": chart_data is not None,
    })

    return {
        "response": response_text, "chart_data": chart_data,
        "sql_used": result.get("sql_used"),
        "sources_used": result.get("sources_used", []),
        "intent": result.get("intent", {}),
    }


# ── Query (streaming via SSE) ────────────────────────────────────────────────

@app.post("/api/query/stream")
def run_query_stream(body: QueryRequest):
    """Stream query response via Server-Sent Events."""
    store = get_or_create_store(body.session_id)
    add_message(body.session_id, "user", body.query)

    history_msgs = get_session_history(body.session_id)
    history = build_conversation_context(history_msgs[:-1])

    def event_generator():
        full_response = ""
        metadata_sent = {}

        for event in process_query_stream(
            user_query=body.query,
            duckdb_conn=store["duckdb_conn"],
            chroma_collection=store["chroma_collection"],
            available_sources=store["sources"],
            conversation_history=history,
            semantic_layer=app.state.semantic_layer,
            session_id=body.session_id,
        ):
            event_type = event.get("type")

            if event_type == "metadata":
                metadata_sent = {
                    "intent": event.get("intent", {}),
                    "chart_data": event.get("chart_data"),
                    "sql_used": event.get("sql_used"),
                    "sources_used": event.get("sources_used", []),
                }
                yield f"data: {json.dumps({'type': 'metadata', **metadata_sent})}\n\n"

            elif event_type == "token":
                token = event.get("content", "")
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            elif event_type == "done":
                # Save full response to DB
                masked, mask_count = mask_pii_in_text_with_count(full_response)
                log_pii_mask(body.session_id, mask_count, where="streaming_response")
                add_message(body.session_id, "assistant", masked, {
                    "sql_used": metadata_sent.get("sql_used"),
                    "sources_used": metadata_sent.get("sources_used", []),
                    "intent": metadata_sent.get("intent", {}),
                    "has_chart": metadata_sent.get("chart_data") is not None,
                })
                yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Scout API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
