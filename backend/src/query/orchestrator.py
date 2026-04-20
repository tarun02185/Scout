"""Query orchestrator — coordinates intent, SQL, RAG, and vision engines to produce final answers."""

import json
from collections.abc import Generator
from groq import Groq

from src.config import GROQ_API_KEY, GROQ_MODEL, RESPONSE_STYLE_PROMPT, CLARIFICATION_PROMPT
from src.query.intent import classify_intent
from src.query.sql_engine import (
    generate_and_execute_sql,
    get_schema_summary,
    is_schema_only_question,
)
from src.query.rag_engine import (
    retrieve_relevant,
    build_rag_context,
)
from src.query.router import route as route_query
from src.query.vision_engine import query_image, query_multiple_images, vision_providers_configured
from src.semantic.resolver import build_semantic_context
from src.guardrails.injection import detect_injection, REFUSAL_MESSAGE
from src.guardrails.tokenizer import tokenize_dataframe, tokenize_rag_chunks
from src.guardrails.audit import log_injection_block


VISION_UNAVAILABLE_MESSAGE = (
    "**Image analysis isn't available right now.**\n\n"
    "Both vision providers failed — most likely the Groq vision model has been "
    "rotated or the Gemini API key is out of quota.\n\n"
    "**What you can do:**\n"
    "- Try again in a minute (transient rate limit).\n"
    "- Get a fresh Gemini API key at [aistudio.google.com](https://aistudio.google.com) and update `GOOGLE_API_KEY`.\n"
    "- Or set `GROQ_VISION_MODEL` in your `.env` to a currently-served Groq vision model."
)


def _build_llm_messages(
    user_query: str,
    context_parts: list[str],
    conversation_history: list[dict] | None = None,
    system_prompt: str = RESPONSE_STYLE_PROMPT,
    target_sources: list[str] | None = None,
    context_confidence: str = "NORMAL",
) -> list[dict]:
    """Build the messages array for LLM call.

    `target_sources` is surfaced so the model knows which file(s) the answer
    must come from. `context_confidence` can be "NORMAL", "LOW", or "NONE"
    — the anti-hallucination rules in the system prompt branch on this.
    """
    context = "\n\n---\n\n".join(context_parts) if context_parts else "(no context retrieved)"
    history_msgs = []
    if conversation_history:
        for msg in conversation_history[-4:]:
            history_msgs.append({"role": msg["role"], "content": msg["content"][:200]})

    target_line = (
        f"TARGET SOURCE(S): {', '.join(target_sources)}"
        if target_sources else
        "TARGET SOURCE(S): (not specified — answer only from context below)"
    )

    return [
        {"role": "system", "content": system_prompt},
        *history_msgs,
        {
            "role": "user",
            "content": (
                f"User asked: {user_query}\n\n"
                f"{target_line}\n"
                f"CONTEXT CONFIDENCE: {context_confidence}\n\n"
                f"Context (each block tagged with [SOURCE: filename]):\n\n{context}\n\n"
                f"STRICT RULES FOR THIS ANSWER:\n"
                f"- Answer ONLY from the context above. Do not use general knowledge.\n"
                f"- If the answer is not literally in the context, say so using the exact wording the system prompt specifies (I couldn't find that in …).\n"
                f"- Only use the TARGET SOURCE(S) listed above. Ignore chunks from other sources even if they appear.\n"
                f"- If CONTEXT CONFIDENCE is LOW or NONE, default to 'I couldn't find that' instead of guessing.\n"
                f"- When referencing the answer, cite the exact source name.\n\n"
                f"Respond using the 5-part structure: headline, meaning, details, significance, follow-ups."
            ),
        },
    ]


def _generate_response(
    user_query: str,
    context_parts: list[str],
    conversation_history: list[dict] | None = None,
    intent_info: dict | None = None,
    target_sources: list[str] | None = None,
    context_confidence: str = "NORMAL",
) -> str:
    """Generate a human-friendly response using the LLM (non-streaming)."""
    if not GROQ_API_KEY:
        return "\n\n".join(context_parts) if context_parts else "No data available to answer your question."

    messages = _build_llm_messages(
        user_query, context_parts, conversation_history,
        target_sources=target_sources, context_confidence=context_confidence,
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        joined = "\n".join(context_parts)
        return f"I found some data but had trouble generating a response: {str(e)}\n\nRaw findings:\n{joined}"


def _stream_response(
    user_query: str,
    context_parts: list[str],
    conversation_history: list[dict] | None = None,
    target_sources: list[str] | None = None,
    context_confidence: str = "NORMAL",
) -> Generator[str, None, None]:
    """Stream LLM response token by token."""
    if not GROQ_API_KEY:
        text = "\n\n".join(context_parts) if context_parts else "No data available."
        yield text
        return

    messages = _build_llm_messages(
        user_query, context_parts, conversation_history,
        target_sources=target_sources, context_confidence=context_confidence,
    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        stream = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1000,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except Exception as e:
        yield f"I had trouble generating a response: {str(e)}"


def _generate_clarification(
    user_query: str,
    available_sources: list[dict],
    conversation_history: list[dict] | None = None,
) -> str:
    """Generate a helpful clarification when the query is vague."""
    if not GROQ_API_KEY:
        return "Could you be more specific? Try asking about a particular metric, time period, or comparison."

    source_summary = []
    for s in available_sources:
        if s.get("source_type") == "structured":
            cols = [c["name"] for c in s.get("columns", [])[:10]]
            source_summary.append(f"Table '{s.get('table_name')}' with columns: {', '.join(cols)}")
        elif s.get("source_type") == "document":
            source_summary.append(f"Document '{s['source_name']}' ({s.get('page_count', '?')} pages)")
        elif s.get("source_type") == "image":
            source_summary.append(f"Image '{s['source_name']}'")
        elif s.get("source_type") == "url":
            source_summary.append(f"Website '{s['source_name']}' ({s.get('pages_crawled', '?')} pages)")

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": CLARIFICATION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User asked: '{user_query}'\n\n"
                        f"Available data:\n" + "\n".join(source_summary) + "\n\n"
                        f"Generate 3-4 specific question suggestions the user might mean. "
                        f"Make them clickable-style (start with the exact question). "
                        f"Be warm and helpful."
                    ),
                },
            ],
            temperature=0.5,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "I'd love to help! Could you tell me what specific information you're looking for?"


def _stream_clarification(
    user_query: str,
    available_sources: list[dict],
    conversation_history: list[dict] | None = None,
) -> Generator[str, None, None]:
    """Stream a clarification response."""
    if not GROQ_API_KEY:
        yield "Could you be more specific?"
        return

    source_summary = []
    for s in available_sources:
        if s.get("source_type") == "structured":
            cols = [c["name"] for c in s.get("columns", [])[:10]]
            source_summary.append(f"Table '{s.get('table_name')}' with columns: {', '.join(cols)}")
        elif s.get("source_type") == "document":
            source_summary.append(f"Document '{s['source_name']}' ({s.get('page_count', '?')} pages)")
        elif s.get("source_type") == "image":
            source_summary.append(f"Image '{s['source_name']}'")
        elif s.get("source_type") == "url":
            source_summary.append(f"Website '{s['source_name']}' ({s.get('pages_crawled', '?')} pages)")

    try:
        client = Groq(api_key=GROQ_API_KEY)
        stream = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": CLARIFICATION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"User asked: '{user_query}'\n\n"
                        f"Available data:\n" + "\n".join(source_summary) + "\n\n"
                        f"Generate 3-4 specific question suggestions the user might mean. "
                        f"Be warm and helpful."
                    ),
                },
            ],
            temperature=0.5,
            max_tokens=500,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except Exception:
        yield "I'd love to help! Could you tell me what specific information you're looking for?"


def _generate_greeting(available_sources: list[dict]) -> str:
    """Generate a welcome/greeting response."""
    if not available_sources:
        return (
            "Hey there! I'm DataLens, your data assistant. "
            "Upload some files to get started — I work with CSV, Excel, PDF, images, log files, and databases.\n\n"
            "Once you upload data, you can ask me things like:\n"
            "- \"What are the total sales?\"\n"
            "- \"Compare this month vs last month\"\n"
            "- \"Why did revenue drop?\"\n"
            "- \"Summarize the key findings from this report\"\n\n"
            "What would you like to explore?"
        )

    source_names = [s["source_name"] for s in available_sources]
    return (
        f"Hey! I have access to: **{', '.join(source_names)}**. "
        f"What would you like to know about your data?"
    )


def _gather_context(
    user_query: str,
    intent: dict,
    duckdb_conn,
    chroma_collection,
    available_sources: list[dict],
    conversation_history: list[dict] | None,
    semantic_layer: dict | None,
) -> tuple[list[str], list[str], any, str | None, bool, list[str], str]:
    """Gather data context from SQL, RAG, and Vision — scoped by the router.

    Returns:
        (context_parts, sources_used, chart_data, sql_used, vision_failed,
         target_sources, context_confidence).

    The router decides, up front, which source(s) the question is about.
    Retrieval is then scoped to those sources so an unrelated file's chunks
    can't contaminate the answer. `context_confidence` is "NORMAL" | "LOW" |
    "NONE" and is surfaced to the response LLM so it can refuse cleanly
    instead of confabulating.
    """
    context_parts: list[str] = []
    sources_used: list[str] = []
    chart_data = None
    sql_used: str | None = None

    # ── Source routing (the key fix) ────────────────────────────────────────
    # Decides which uploaded source(s) this question is actually about, and
    # whether we need SQL / RAG / both. When only 1 source is present the
    # router is a no-op — no extra LLM call.
    routing = route_query(user_query, available_sources)
    target_sources = routing.get("sources") or [s["source_name"] for s in available_sources]

    target_set = set(target_sources)
    targeted = [s for s in available_sources if s.get("source_name") in target_set]

    has_structured = any(
        s.get("source_type") in ("structured", "database", "log") and s.get("table_name")
        for s in targeted
    )
    has_documents = any(
        s.get("source_type") in ("document", "log", "url") for s in targeted
    )

    structured_table_names = [s["table_name"] for s in targeted if s.get("table_name")]
    structured_display_names = [s["source_name"] for s in targeted if s.get("table_name")]
    document_names = [s["source_name"] for s in targeted if s.get("source_type") in ("document", "log", "url")]

    needs_structured = routing.get("needs_structured", intent.get("needs_structured", False))
    needs_unstructured = routing.get("needs_unstructured", intent.get("needs_unstructured", False))

    # ── Schema-only shortcut ────────────────────────────────────────────────
    # "How many columns?", "what features are in the dataset?", etc. — answer
    # directly from DESCRIBE, no LLM-generated SQL, no RAG needed.
    if has_structured and is_schema_only_question(user_query):
        summary = get_schema_summary(duckdb_conn, structured_table_names or None)
        if summary and "No matching tables" not in summary and "No tables available" not in summary:
            context_parts.append(summary)
            sources_used.extend(structured_display_names or structured_table_names)
            return context_parts, sources_used, None, None, False, target_sources, "NORMAL"

    # ── Structured SQL path ─────────────────────────────────────────────────
    if has_structured and needs_structured:
        sql_result = generate_and_execute_sql(
            user_query, duckdb_conn, conversation_history, semantic_layer
        )
        if sql_result.get("data") is not None and not sql_result["data"].empty:
            df = sql_result["data"]
            chart_data = df
            sql_used = sql_result.get("sql")
            tables = sql_result.get("tables_used", [])
            sources_used.extend(tables)
            safe_df = tokenize_dataframe(df.head(10))
            data_str = safe_df.to_string(index=False)
            file_label = ", ".join(structured_display_names) if structured_display_names else "uploaded data"
            context_parts.append(
                f"[SOURCE: {file_label} (structured/tabular data)]\n"
                f"Query: {sql_result.get('explanation', '')}\n"
                f"Result:\n{data_str}"
            )
        # Intentionally do NOT append an "SQL failed" note — that text would
        # leak into the prompt and the response LLM would confabulate around it.

    # ── RAG path — scoped to the routed document sources ────────────────────
    rag_weak = False
    if has_documents and needs_unstructured:
        chunks, rag_weak = retrieve_relevant(
            user_query,
            chroma_collection,
            sources=document_names or None,
            n_results=6,
        )
        if chunks:
            chunks = tokenize_rag_chunks(chunks)
            rag_context = build_rag_context(chunks)
            context_parts.append(
                f"[SOURCE: {', '.join(document_names)} (documents)]\n{rag_context}"
            )
            sources_used.extend(sorted({c["source"] for c in chunks}))

    # ── Vision path ─────────────────────────────────────────────────────────
    vision_failed = False
    if intent.get("needs_vision", False):
        all_images: list[dict] = []
        for s in targeted:
            if s.get("source_type") == "image":
                if s.get("image_bytes"):
                    all_images.append(s)
            elif s.get("has_images") and s.get("images"):
                all_images.extend(s["images"])

        if all_images:
            vision_result = query_multiple_images(user_query, all_images)
            if vision_result:
                context_parts.append(f"Image analysis:\n{vision_result}")
                sources_used.append("images")
            else:
                vision_failed = True

    # ── Fallback: if nothing matched the target, try documents globally ─────
    # (helps when the router's source list was right but the structured query
    #  produced no rows and the question actually needs document text.)
    if not context_parts and has_documents:
        chunks, rag_weak_fb = retrieve_relevant(
            user_query, chroma_collection,
            sources=document_names or None, n_results=5,
        )
        if chunks:
            chunks = tokenize_rag_chunks(chunks)
            rag_context = build_rag_context(chunks)
            context_parts.append(
                f"[SOURCE: {', '.join(document_names)} (documents)]\n{rag_context}"
            )
            sources_used.extend(sorted({c["source"] for c in chunks}))
            rag_weak = rag_weak or rag_weak_fb

    # ── Confidence assessment for the response LLM ──────────────────────────
    if not context_parts:
        context_confidence = "NONE"
    elif rag_weak and sql_used is None and chart_data is None:
        # Only retrieved weak document matches — no structured backup.
        context_confidence = "LOW"
    else:
        context_confidence = "NORMAL"

    report_vision_failed = vision_failed and not context_parts
    return (
        context_parts, sources_used, chart_data, sql_used,
        report_vision_failed, target_sources, context_confidence,
    )


def process_query(
    user_query: str,
    duckdb_conn,
    chroma_collection,
    available_sources: list[dict],
    conversation_history: list[dict] | None = None,
    semantic_layer: dict | None = None,
    session_id: str | None = None,
) -> dict:
    """Process a user query end-to-end (non-streaming)."""
    # Guardrail layer 2 — prompt-injection / extraction-intent filter.
    is_bad, reason = detect_injection(user_query)
    if is_bad:
        log_injection_block(session_id, user_query, reason)
        return {
            "response": REFUSAL_MESSAGE,
            "chart_data": None, "sql_used": None,
            "sources_used": [],
            "intent": {"intent": "blocked", "reason": reason},
            "suggestions": [],
            "blocked": True,
        }

    intent = classify_intent(user_query, available_sources, conversation_history)

    if intent.get("intent") == "greeting":
        return {
            "response": _generate_greeting(available_sources),
            "chart_data": None, "sql_used": None,
            "sources_used": [], "intent": intent, "suggestions": [],
        }

    if not available_sources:
        return {
            "response": "I don't have any data to work with yet. Upload a file using the sidebar!",
            "chart_data": None, "sql_used": None,
            "sources_used": [], "intent": intent, "suggestions": [],
        }

    if intent.get("intent") == "unclear" or intent.get("clarification_needed"):
        return {
            "response": _generate_clarification(user_query, available_sources, conversation_history),
            "chart_data": None, "sql_used": None,
            "sources_used": [], "intent": intent, "suggestions": [],
        }

    (context_parts, sources_used, chart_data, sql_used,
     vision_failed, target_sources, context_confidence) = _gather_context(
        user_query, intent, duckdb_conn, chroma_collection,
        available_sources, conversation_history, semantic_layer,
    )

    if vision_failed:
        return {
            "response": VISION_UNAVAILABLE_MESSAGE,
            "chart_data": None, "sql_used": None,
            "sources_used": [], "intent": intent, "suggestions": [],
        }

    if not context_parts:
        return {
            "response": _generate_clarification(user_query, available_sources, conversation_history),
            "chart_data": None, "sql_used": None,
            "sources_used": [], "intent": intent, "suggestions": [],
        }

    response = _generate_response(
        user_query, context_parts, conversation_history, intent,
        target_sources=target_sources, context_confidence=context_confidence,
    )

    return {
        "response": response, "chart_data": chart_data, "sql_used": sql_used,
        "sources_used": list(set(sources_used)), "intent": intent, "suggestions": [],
    }


def process_query_stream(
    user_query: str,
    duckdb_conn,
    chroma_collection,
    available_sources: list[dict],
    conversation_history: list[dict] | None = None,
    semantic_layer: dict | None = None,
    session_id: str | None = None,
) -> Generator[dict, None, None]:
    """Process a user query with streaming response.

    Yields SSE-compatible dicts:
    - {"type": "metadata", ...}   — intent, chart, sql, sources (sent first)
    - {"type": "token", "content": "..."} — each streamed token
    - {"type": "done"}            — signals stream end
    """
    # Guardrail layer 2 — prompt-injection / extraction-intent filter.
    is_bad, reason = detect_injection(user_query)
    if is_bad:
        log_injection_block(session_id, user_query, reason)
        yield {
            "type": "metadata",
            "intent": {"intent": "blocked", "reason": reason},
            "chart_data": None,
            "sql_used": None,
            "sources_used": [],
            "blocked": True,
        }
        yield {"type": "token", "content": REFUSAL_MESSAGE}
        yield {"type": "done"}
        return

    intent = classify_intent(user_query, available_sources, conversation_history)

    # Greetings / no data — yield full response immediately
    if intent.get("intent") == "greeting":
        text = _generate_greeting(available_sources)
        yield {"type": "metadata", "intent": intent, "chart_data": None, "sql_used": None, "sources_used": []}
        yield {"type": "token", "content": text}
        yield {"type": "done"}
        return

    if not available_sources:
        yield {"type": "metadata", "intent": intent, "chart_data": None, "sql_used": None, "sources_used": []}
        yield {"type": "token", "content": "I don't have any data yet. Upload a file using the sidebar!"}
        yield {"type": "done"}
        return

    if intent.get("intent") == "unclear" or intent.get("clarification_needed"):
        yield {"type": "metadata", "intent": intent, "chart_data": None, "sql_used": None, "sources_used": []}
        for token in _stream_clarification(user_query, available_sources, conversation_history):
            yield {"type": "token", "content": token}
        yield {"type": "done"}
        return

    # Gather context (SQL, RAG, Vision)
    (context_parts, sources_used, chart_data, sql_used,
     vision_failed, target_sources, context_confidence) = _gather_context(
        user_query, intent, duckdb_conn, chroma_collection,
        available_sources, conversation_history, semantic_layer,
    )

    if vision_failed:
        yield {
            "type": "metadata",
            "intent": intent,
            "chart_data": None,
            "sql_used": None,
            "sources_used": [],
        }
        yield {"type": "token", "content": VISION_UNAVAILABLE_MESSAGE}
        yield {"type": "done"}
        return

    # Serialize chart data
    chart_data_json = None
    if chart_data is not None and not chart_data.empty:
        chart_data_json = {
            "columns": list(chart_data.columns),
            "rows": chart_data.to_dict(orient="records"),
            "dtypes": {col: str(dtype) for col, dtype in chart_data.dtypes.items()},
        }

    # Send metadata first (chart, SQL, sources)
    yield {
        "type": "metadata",
        "intent": intent,
        "chart_data": chart_data_json,
        "sql_used": sql_used,
        "sources_used": list(set(sources_used)),
    }

    # If no context found, stream clarification
    if not context_parts:
        for token in _stream_clarification(user_query, available_sources, conversation_history):
            yield {"type": "token", "content": token}
        yield {"type": "done"}
        return

    # Stream the LLM response token by token
    for token in _stream_response(
        user_query, context_parts, conversation_history,
        target_sources=target_sources, context_confidence=context_confidence,
    ):
        yield {"type": "token", "content": token}

    yield {"type": "done"}
