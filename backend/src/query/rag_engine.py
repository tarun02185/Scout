"""RAG engine — retrieves relevant text chunks from ChromaDB for unstructured queries.

Three safeguards against hallucination and cross-source contamination:

1. **Per-source filtering.** When the orchestrator has routed the question to
   one or more sources, we filter the vector search to those sources only.
   This stops the embedding search from pulling chunks from unrelated files.

2. **Distance threshold.** If the top chunk's cosine distance exceeds
   `weak_match_threshold`, the context is flagged weak. The response LLM
   then says "I couldn't find that in your file" instead of confabulating.

3. **First-chunk guarantee for metadata queries.** Questions like "what is
   the title?", "who wrote this?", "summarize the paper" need the first
   page of a document. Naïve embedding search often misses it. We detect
   these queries by keyword and always prepend chunk-index-0 of every
   targeted source.
"""


# Keywords that indicate the user is asking about document metadata (title,
# author, abstract, summary) — for these, we always include the first chunk
# of each source regardless of embedding rank.
_METADATA_KEYWORDS = (
    "title", "titled", "name of the paper", "name of this paper",
    "name of the document", "author", "authors", "written by",
    "who wrote", "what is this paper", "what is this document",
    "what is this about", "summary", "summarize", "summarise", "abstract",
    "what does this paper", "what does the document", "tldr", "tl;dr",
    "overview of the paper", "overview of the document",
)


def is_metadata_query(query: str) -> bool:
    q = (query or "").lower().strip()
    return any(kw in q for kw in _METADATA_KEYWORDS)


def _chroma_where(sources: list[str] | None):
    """Build a Chroma `where` clause that filters to one or more sources."""
    if not sources:
        return None
    if len(sources) == 1:
        return {"source": sources[0]}
    return {"source": {"$in": list(sources)}}


def search_documents(
    query: str,
    chroma_collection,
    n_results: int = 5,
    source_filter: str | None = None,
    sources: list[str] | None = None,
) -> list[dict]:
    """Search ChromaDB for relevant chunks, optionally restricted by source.

    Args:
        source_filter: single source name (kept for back-compat).
        sources: list of source names — preferred over `source_filter`.
    """
    if chroma_collection is None:
        return []

    target_sources = sources or ([source_filter] if source_filter else None)

    try:
        count = chroma_collection.count()
        if count == 0:
            return []

        where = _chroma_where(target_sources)
        results = chroma_collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
            where=where,
        )

        chunks: list[dict] = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                chunks.append({
                    "text": doc,
                    "source": metadata.get("source", "unknown"),
                    "page": metadata.get("page"),
                    "chunk_index": metadata.get("chunk_index"),
                    "type": metadata.get("type", "text"),
                    "distance": distance,
                })

        return chunks
    except Exception:
        return []


def fetch_first_chunks(
    chroma_collection,
    sources: list[str],
    per_source: int = 2,
) -> list[dict]:
    """Return the first `per_source` chunks (by chunk_index) of each source.

    Used for metadata queries where a paper's title / abstract is almost
    always in chunk 0, but the embedding search may not surface it.
    """
    if chroma_collection is None or not sources:
        return []
    collected: list[dict] = []
    for src in sources:
        try:
            res = chroma_collection.get(
                where={"source": src},
                include=["documents", "metadatas"],
            )
        except Exception:
            continue
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        # Sort by chunk_index ascending, pick first N.
        rows = sorted(
            zip(docs, metas),
            key=lambda r: (r[1] or {}).get("chunk_index", 10**9),
        )
        for doc, meta in rows[:per_source]:
            collected.append({
                "text": doc,
                "source": (meta or {}).get("source", src),
                "page": (meta or {}).get("page"),
                "chunk_index": (meta or {}).get("chunk_index"),
                "type": (meta or {}).get("type", "text"),
                "distance": 0.0,  # synthetic — not from ranking
            })
    return collected


def retrieve_relevant(
    query: str,
    chroma_collection,
    sources: list[str] | None = None,
    n_results: int = 5,
    weak_match_threshold: float = 0.55,
) -> tuple[list[dict], bool]:
    """High-level retrieval used by the orchestrator.

    Returns (chunks, is_weak_match). A weak match means the top embedding
    distance exceeds the threshold AND no metadata-query fallback was
    applied — the caller should ask the LLM to refuse rather than confabulate.
    """
    use_metadata_fallback = is_metadata_query(query) and bool(sources)

    chunks = search_documents(
        query,
        chroma_collection,
        n_results=n_results,
        sources=sources,
    )

    # Prepend first chunks of each targeted source when the query looks
    # like it's asking about document metadata (title, author, summary…).
    if use_metadata_fallback:
        first = fetch_first_chunks(chroma_collection, sources or [], per_source=2)
        # De-dupe: drop any retrieved chunk that matches one we prepended.
        first_keys = {(c["source"], c["chunk_index"]) for c in first}
        chunks = first + [c for c in chunks if (c["source"], c["chunk_index"]) not in first_keys]

    # Weak-match detection: no metadata fallback AND top distance is high.
    is_weak = False
    if not use_metadata_fallback:
        if not chunks:
            is_weak = True
        else:
            top = min(c.get("distance", 1.0) or 1.0 for c in chunks)
            if top > weak_match_threshold:
                is_weak = True

    return chunks, is_weak


def build_rag_context(chunks: list[dict]) -> str:
    """Build a context string from retrieved chunks for LLM consumption."""
    if not chunks:
        return "No relevant document content found."

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source", "unknown")
        page = chunk.get("page")
        page_info = f" (page {page})" if page else ""
        context_parts.append(
            f"[Source {i}: {source}{page_info}]\n{chunk['text']}"
        )

    return "\n\n---\n\n".join(context_parts)
