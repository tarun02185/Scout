"""Input-side PII tokenization.

Before sensitive data reaches the LLM (either as sample rows in the SQL prompt,
query result rows in the response-generation prompt, or retrieved RAG chunks),
this module replaces PII values with opaque, deterministic tokens such as
`[PII_EMAIL_a1b2c3d4]`. The LLM therefore never sees raw sensitive values and
cannot leak them, regardless of how the user phrases their question.

Tokens are deterministic (hash of the value) so grouping / equality semantics
are preserved — "how many rows share the same email" still works even though
the email itself is hidden.
"""

import hashlib
import re
from typing import Iterable

import pandas as pd

from src.guardrails.pii import PII_PATTERNS, PII_COLUMN_NAMES, check_columns_for_pii


_SESSION_VAULTS: dict[str, dict[str, str]] = {}


def _vault(session_id: str | None) -> dict[str, str]:
    key = session_id or "__global__"
    return _SESSION_VAULTS.setdefault(key, {})


def _token_for(value: str, pii_type: str, session_id: str | None) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:8]
    token = f"[PII_{pii_type.upper()}_{digest}]"
    _vault(session_id)[token] = value
    return token


def tokenize_text(text: str, session_id: str | None = None) -> str:
    """Replace every PII occurrence in a free-text string with an opaque token."""
    if not text:
        return text
    for pii_type, pattern in PII_PATTERNS.items():
        text = pattern.sub(
            lambda m, t=pii_type: _token_for(m.group(), t, session_id),
            text,
        )
    return text


def tokenize_dataframe(
    df: pd.DataFrame,
    session_id: str | None = None,
    extra_pii_columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return a copy of the DataFrame with sensitive values replaced by tokens.

    A column is tokenised if either (a) its name matches a known PII column name
    or (b) any cell value matches a PII regex. Every string cell is additionally
    scanned for embedded PII (e.g. an address column containing a phone number).
    """
    if df is None or df.empty:
        return df

    out = df.copy()
    columns = list(out.columns)

    pii_cols = set(check_columns_for_pii(columns))
    if extra_pii_columns:
        pii_cols.update(extra_pii_columns)

    for col in columns:
        if out[col].dtype != object:
            continue
        col_key = col.lower().strip()
        pii_type = col_key if col_key in PII_COLUMN_NAMES else None
        if col in pii_cols:
            out[col] = out[col].astype(str).map(
                lambda v, t=(pii_type or "value"): _token_for(v, t, session_id)
            )
        else:
            out[col] = out[col].astype(str).map(
                lambda v: tokenize_text(v, session_id)
            )
    return out


def tokenize_rag_chunks(
    chunks: list[dict],
    session_id: str | None = None,
) -> list[dict]:
    """Tokenise the `text` field of each RAG chunk in place-safe manner."""
    out = []
    for c in chunks:
        cc = dict(c)
        cc["text"] = tokenize_text(cc.get("text", ""), session_id)
        out.append(cc)
    return out


def clear_vault(session_id: str | None = None) -> None:
    if session_id is None:
        _SESSION_VAULTS.clear()
    else:
        _SESSION_VAULTS.pop(session_id, None)


TOKEN_PATTERN = re.compile(r"\[PII_[A-Z_]+_[a-f0-9]{8}\]")


def contains_token(text: str) -> bool:
    return bool(TOKEN_PATTERN.search(text or ""))
