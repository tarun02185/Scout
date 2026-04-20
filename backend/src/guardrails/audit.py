"""Append-only audit log for guardrail events.

Every blocked query, blocked SQL, tokenisation event, or suspicious input is
written as one JSON line. The log is deliberately minimal — enough for later
review, but not so verbose that it becomes a PII repository itself (we log
*that* something was blocked and the detection tag, never the raw sensitive
value that triggered it).
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()

DEFAULT_LOG_PATH = Path(
    os.getenv(
        "GUARDRAIL_AUDIT_LOG",
        str(Path(__file__).resolve().parent.parent.parent / "audit.log"),
    )
)


def log_event(event_type: str, **details) -> None:
    """Append one JSON event line.

    Never raises — audit logging is best-effort and must not break the hot path.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **details,
    }
    try:
        DEFAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, open(DEFAULT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass


def log_injection_block(session_id: str | None, query: str, reason: str) -> None:
    # Truncate the query so an attacker can't use the audit log as an exfil channel.
    log_event(
        "injection_blocked",
        session_id=session_id,
        reason=reason,
        query_preview=(query or "")[:120],
    )


def log_sql_block(session_id: str | None, sql: str, reason: str) -> None:
    log_event(
        "sql_blocked",
        session_id=session_id,
        reason=reason,
        sql_preview=(sql or "")[:200],
    )


def log_pii_mask(session_id: str | None, count: int, where: str) -> None:
    if count <= 0:
        return
    log_event(
        "pii_masked_in_output",
        session_id=session_id,
        count=count,
        where=where,
    )
