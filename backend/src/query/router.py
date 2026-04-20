"""Source routing — decides which uploaded source(s) a user question targets.

With multiple files loaded (e.g. a CSV dataset + a research paper PDF + a
brief PDF), naive RAG retrieves chunks from all of them and mixes the
answers. This module uses a fast LLM call to classify, up front, which
source(s) the question is about, so:

- RAG retrieval is restricted to those sources via ChromaDB's `where` filter.
- SQL generation is skipped when the question is about a document, even if
  the query happens to contain a generic keyword like "total" or "number".
- The response LLM is told which source the answer came from, so citations
  are accurate.

Falls back to a safe heuristic (include every source) if the LLM call fails
or returns unparseable JSON — so routing never silently drops an answer.
"""

from __future__ import annotations

import json
import re

from groq import Groq

from src.config import GROQ_API_KEY, GROQ_MODEL_FAST


_ROUTING_PROMPT = """You route a user's question to the one or more data sources that are likely to contain the answer. You are NOT answering the question — only deciding which file(s) to open.

AVAILABLE SOURCES:
{sources_block}

USER QUESTION: {question}

REPLY with JSON only, no prose:
{{
  "sources": ["exact_source_name", ...],
  "needs_structured": true | false,
  "needs_unstructured": true | false,
  "reasoning": "one short sentence"
}}

RULES:
- Only include a source that is DIRECTLY relevant — never "all of them" just because they're available.
- If the question names a file by title, topic, or content (e.g. "the research paper", "the heart dataset", "the hackathon brief"), choose only that source.
- `needs_structured` = true only when the question needs SQL / aggregation / counts / comparisons over tabular data AND a structured source is present.
- `needs_unstructured` = true only when the answer is likely in a document / report / webpage (titles, explanations, discussion, methodology).
- "How many columns / features / attributes / fields" is ALWAYS structured when a table is present — that is schema, answerable from DESCRIBE, not from a paper.
- If genuinely unclear, pick the single most likely source — not all.
"""


_JSON_RE = re.compile(r"\{[\s\S]*\}")


def _fallback_route(available_sources: list[dict], needs_structured_guess: bool = True, needs_unstructured_guess: bool = True) -> dict:
    """Safe fallback when the LLM routing call fails: include everything."""
    return {
        "sources": [s["source_name"] for s in available_sources],
        "needs_structured": needs_structured_guess,
        "needs_unstructured": needs_unstructured_guess,
        "reasoning": "fallback: routing call failed — included all sources",
    }


def _describe_sources(available_sources: list[dict]) -> str:
    lines: list[str] = []
    for s in available_sources:
        name = s.get("source_name", "?")
        kind = s.get("source_type", "?")
        bits: list[str] = []
        if kind == "structured":
            cols = [c.get("name") for c in (s.get("columns") or []) if isinstance(c, dict)]
            bits.append(f"table with {s.get('row_count', 0)} rows, {len(cols)} columns: {', '.join(cols[:12])}")
        elif kind == "document":
            bits.append(f"document · {s.get('page_count', '?')} pages · {s.get('chunk_count', 0)} text chunks")
        elif kind == "url":
            bits.append(f"crawled website · {s.get('pages_crawled', 0)} pages · {s.get('chunks', 0)} chunks")
        elif kind == "log":
            bits.append(f"log file · {s.get('line_count', 0)} lines")
        elif kind == "database":
            tables = s.get("tables") or []
            bits.append(f"sqlite · {len(tables)} tables")
        elif kind == "image":
            bits.append("image")
        lines.append(f"- {name}  [{kind}]  — {'; '.join(bits) if bits else ''}")
    return "\n".join(lines) if lines else "(no sources)"


def route(
    user_query: str,
    available_sources: list[dict],
) -> dict:
    """Return {sources, needs_structured, needs_unstructured, reasoning}.

    If only 0 or 1 source exists, the router is a no-op — we don't waste a
    model call when there's nothing to disambiguate.
    """
    if not available_sources:
        return {"sources": [], "needs_structured": False, "needs_unstructured": False, "reasoning": "no sources"}

    if len(available_sources) == 1:
        s = available_sources[0]
        kind = s.get("source_type", "")
        return {
            "sources": [s["source_name"]],
            "needs_structured": kind in ("structured", "database", "log"),
            "needs_unstructured": kind in ("document", "log", "url"),
            "reasoning": "single source — routing skipped",
        }

    if not GROQ_API_KEY:
        return _fallback_route(available_sources)

    prompt = _ROUTING_PROMPT.format(
        sources_block=_describe_sources(available_sources),
        question=user_query.strip(),
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model=GROQ_MODEL_FAST,
            messages=[
                {"role": "system", "content": "You route questions to data sources. Reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=250,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception:
        return _fallback_route(available_sources)

    m = _JSON_RE.search(raw)
    if not m:
        return _fallback_route(available_sources)
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return _fallback_route(available_sources)

    # Validate the names against what's actually loaded. Drop stray names.
    known = {s["source_name"] for s in available_sources}
    picked = [n for n in (parsed.get("sources") or []) if n in known]
    if not picked:
        # The model hallucinated names — fall back to all.
        return _fallback_route(available_sources)

    return {
        "sources": picked,
        "needs_structured": bool(parsed.get("needs_structured")),
        "needs_unstructured": bool(parsed.get("needs_unstructured")),
        "reasoning": str(parsed.get("reasoning", ""))[:200],
    }
