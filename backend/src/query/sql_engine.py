"""Text-to-SQL engine — converts natural language to DuckDB SQL and executes it.

Includes automatic retry: if the first SQL attempt fails, the error is fed back
to the LLM so it can self-correct.
"""

import json
import re
import pandas as pd
from groq import Groq

from src.config import GROQ_API_KEY, GROQ_MODEL_FAST, SECURITY_PREAMBLE
from src.semantic.resolver import build_semantic_context
from src.guardrails.validator import validate_sql, validate_sql_columns, is_pii_column
from src.guardrails.tokenizer import tokenize_dataframe
from src.guardrails.audit import log_sql_block


SQL_SYSTEM_PROMPT = SECURITY_PREAMBLE + """You are a SQL expert that converts natural language questions into DuckDB SQL queries.

RULES:
1. Generate ONLY a SELECT query — never INSERT, UPDATE, DELETE, DROP, or ALTER
2. Use the EXACT table and column names provided — do NOT guess column names
3. Look carefully at the sample data to understand what each column contains
4. Apply metric definitions from the semantic layer when available
5. Handle time references using DuckDB date functions
6. Always add ORDER BY for readability
7. LIMIT results to 50 rows unless user asks for more
8. For comparisons, use CTEs or subqueries for clarity
9. Use column aliases that are human-readable (e.g., "Total Revenue" not "sum_rev")
10. When asked to COUNT distinct items, use COUNT(DISTINCT column_name)
11. When unsure which column to use, pick the most relevant one based on sample data
12. SENSITIVE COLUMNS (email, phone, address, ssn, aadhaar, pan, passport, credit_card,
    password, dob, bank_account, and any column whose name contains those words)
    must NEVER appear directly in the SELECT projection. Only aggregates are allowed:
    COUNT(col), COUNT(DISTINCT col), or they may be used in WHERE/GROUP BY/ORDER BY.
    SELECT * is forbidden on any table that contains a sensitive column.

Return a JSON object:
{
  "sql": "the SQL query",
  "explanation": "one-sentence description of what this query does",
  "columns_used": ["list", "of", "columns"],
  "tables_used": ["list", "of", "tables"]
}

Return ONLY valid JSON. No markdown, no extra text.
"""

SQL_RETRY_PROMPT = """The previous SQL query failed with this error:
{error}

The original query was:
{sql}

Please fix the SQL query. Use ONLY the exact column and table names from the schema.
Return the corrected query as a JSON object with the same format.
"""


# Schema cache — avoids re-reading table metadata on every query
_schema_cache: dict[int, str] = {}


def _get_table_schemas(duckdb_conn) -> str:
    """Get schema information for all loaded tables (cached per connection)."""
    conn_id = id(duckdb_conn)

    # Check cache — invalidate if table count changed
    try:
        tables = duckdb_conn.execute("SHOW TABLES").fetchall()
    except Exception:
        return "No tables available."

    cache_key = hash((conn_id, len(tables), tuple(t[0] for t in tables)))
    if cache_key in _schema_cache:
        return _schema_cache[cache_key]

    schemas = []
    for (table_name,) in tables:
        try:
            cols = duckdb_conn.execute(f"DESCRIBE {table_name}").fetchall()
            col_desc = ", ".join([f"{c[0]} ({c[1]})" for c in cols])
            row_count = duckdb_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

            sample = duckdb_conn.execute(f"SELECT * FROM {table_name} LIMIT 3").fetchdf()
            # Tokenise PII values before showing samples to the LLM — the SQL
            # planner only needs to see the shape of the data, not the values.
            sample = tokenize_dataframe(sample)
            sample_text = sample.to_string(index=False, max_colwidth=30)

            pii_cols = [c[0] for c in cols if is_pii_column(c[0])]
            pii_note = ""
            if pii_cols:
                pii_note = (
                    f"\nSENSITIVE COLUMNS (restricted — aggregates only): "
                    f"{', '.join(pii_cols)}"
                )

            schemas.append(
                f"Table: {table_name} ({row_count} rows)\n"
                f"Columns: {col_desc}{pii_note}\n"
                f"Sample:\n{sample_text}"
            )
        except Exception:
            schemas.append(f"Table: {table_name} (could not read schema)")

    result = "\n\n".join(schemas) if schemas else "No tables available."
    _schema_cache[cache_key] = result
    return result


def get_schema_summary(duckdb_conn, table_names: list[str] | None = None) -> str:
    """Return a concise, human-readable schema summary.

    Used by the orchestrator to answer meta-questions about table shape
    ("how many columns?", "what fields does this dataset have?") without
    forcing the SQL generator to produce a DESCRIBE query. Includes the
    column count explicitly so the response LLM can quote it directly.
    """
    try:
        all_tables = duckdb_conn.execute("SHOW TABLES").fetchall()
    except Exception:
        return "No tables available."

    wanted = set(table_names) if table_names else {t[0] for t in all_tables}
    parts: list[str] = []
    for (tbl,) in all_tables:
        if tbl not in wanted:
            continue
        try:
            cols = duckdb_conn.execute(f"DESCRIBE {tbl}").fetchall()
            row_count = duckdb_conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        except Exception:
            continue
        col_list = ", ".join(f"{c[0]} ({c[1]})" for c in cols)
        parts.append(
            f"[SOURCE: {tbl} (tabular schema)]\n"
            f"Rows: {row_count}\n"
            f"Column count: {len(cols)}\n"
            f"Columns: {col_list}"
        )
    return "\n\n".join(parts) if parts else "No matching tables."


# Queries that are answered from schema alone (no SQL needed).
_SCHEMA_QUESTION_KEYWORDS = (
    "how many columns", "how many features", "how many fields",
    "how many attributes", "how many variables",
    "number of columns", "number of features", "number of fields",
    "number of attributes", "number of variables",
    "list of features", "list of columns", "list of fields",
    "what columns", "what features", "what fields", "what attributes",
    "what are the columns", "what are the features",
    "describe the dataset", "describe this dataset", "describe the table",
    "schema", "what is the shape of", "shape of the dataset",
)


def is_schema_only_question(query: str) -> bool:
    q = (query or "").lower().strip()
    return any(kw in q for kw in _SCHEMA_QUESTION_KEYWORDS)


def _parse_llm_response(result_text: str) -> dict:
    """Parse JSON or raw SQL from LLM response."""
    # Try JSON first
    clean = result_text.strip()
    if "```" in clean:
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Try extracting SQL directly
    sql_match = re.search(r"(SELECT\s+.+?)(?:;|$)", result_text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return {"sql": sql_match.group(1).strip(), "explanation": "", "columns_used": [], "tables_used": []}

    return {}


def _call_llm(messages: list[dict]) -> str:
    """Call Groq with fast 8B model for SQL generation.

    SQL is a structured task — the 8B model handles it well
    and responds ~5x faster than 70B, cutting time-to-first-token.
    """
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL_FAST,
        messages=messages,
        temperature=0,
        max_tokens=1000,
    )
    return response.choices[0].message.content.strip()


def generate_and_execute_sql(
    user_query: str,
    duckdb_conn,
    conversation_history: list[dict] | None = None,
    semantic_layer: dict | None = None,
    max_retries: int = 2,
) -> dict:
    """Generate SQL from natural language, validate, execute, and retry on failure."""
    table_schemas = _get_table_schemas(duckdb_conn)
    semantic_context = build_semantic_context(semantic_layer)

    if not GROQ_API_KEY:
        return {"error": "No GROQ_API_KEY configured.", "data": None}

    # Build conversation context for follow-ups
    history_context = ""
    if conversation_history:
        recent = conversation_history[-4:]
        history_context = "\nPrevious conversation:\n"
        for msg in recent:
            history_context += f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}\n"

    messages = [
        {"role": "system", "content": SQL_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Available tables and schemas:\n{table_schemas}\n\n"
                f"{semantic_context}\n\n"
                f"{history_context}\n\n"
                f"User question: {user_query}"
            ),
        },
    ]

    last_error = ""
    last_sql = ""

    for attempt in range(max_retries + 1):
        try:
            # On retry, append the error feedback
            if attempt > 0 and last_error:
                messages.append({
                    "role": "user",
                    "content": SQL_RETRY_PROMPT.format(error=last_error, sql=last_sql),
                })

            result_text = _call_llm(messages)
            result = _parse_llm_response(result_text)
            sql = result.get("sql", "")

            if not sql:
                last_error = "LLM did not return a SQL query"
                continue

            # Validate structural safety
            is_safe, reason = validate_sql(sql)
            if not is_safe:
                last_error = f"Blocked: {reason}"
                last_sql = sql
                log_sql_block(None, sql, reason)
                continue

            # Validate column-level PII safety.
            # Gather every column across every loaded table so the check works
            # regardless of which table the LLM chose.
            try:
                all_cols: list[str] = []
                for (tbl_name,) in tables:
                    try:
                        for row in duckdb_conn.execute(f"DESCRIBE {tbl_name}").fetchall():
                            all_cols.append(row[0])
                    except Exception:
                        pass
                is_col_safe, col_reason = validate_sql_columns(sql, all_columns=all_cols)
            except Exception:
                is_col_safe, col_reason = True, "OK"
            if not is_col_safe:
                last_error = f"Blocked (PII): {col_reason}"
                last_sql = sql
                log_sql_block(None, sql, col_reason)
                continue

            # Execute
            try:
                df = duckdb_conn.execute(sql).fetchdf()
            except Exception as exec_err:
                last_error = str(exec_err)
                last_sql = sql
                continue

            # Success
            return {
                "sql": sql,
                "explanation": result.get("explanation", ""),
                "columns_used": result.get("columns_used", []),
                "tables_used": result.get("tables_used", []),
                "data": df,
                "row_count": len(df),
            }

        except Exception as e:
            last_error = str(e)
            continue

    # All retries failed
    return {
        "error": f"Could not run query after {max_retries + 1} attempts. Last error: {last_error}",
        "sql": last_sql,
        "data": None,
    }
