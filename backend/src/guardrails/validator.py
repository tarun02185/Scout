"""SQL validation — prevents dangerous queries and injection attacks.

Two layers of SQL safety:
- Structural safety (`validate_sql`): only SELECT/WITH, no DDL/DML, no
  multi-statement piggybacking, no SQL comments.
- Column-level PII safety (`validate_sql_columns`): even a well-formed SELECT
  is rejected if it pulls raw values out of columns that hold personal data.
  Aggregates (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`) over those columns are
  allowed because they don't reveal individual values.
"""

import re

from src.guardrails.pii import PII_COLUMN_NAMES

# Forbidden SQL operations
FORBIDDEN_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bTRUNCATE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bUNION\s+ALL\s+SELECT\b",  # SQL injection pattern
    r";\s*SELECT\b",  # Piggyback queries
    r"--",  # SQL comments (potential injection)
    r"/\*",  # Block comments (potential injection)
    r"\bxp_\w+",  # Extended stored procedures
    r"\bSHUTDOWN\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bCOPY\b",
    r"\bLOAD\b",
    r"\bIMPORT\b",
    r"\bEXPORT\b",
]

# Only allow SELECT queries
ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def validate_sql(sql: str) -> tuple[bool, str]:
    """Validate SQL query for safety.

    Returns (is_safe, reason).
    """
    if not sql or not sql.strip():
        return False, "Empty query"

    sql_clean = sql.strip()

    # Must start with SELECT or WITH (CTE)
    if not ALLOWED_START.match(sql_clean):
        return False, "Only SELECT queries are allowed"

    # Check forbidden patterns
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql_clean, re.IGNORECASE):
            keyword = re.search(pattern, sql_clean, re.IGNORECASE).group()
            return False, f"Forbidden operation detected: {keyword}"

    # Check for multiple statements
    # Remove string literals first to avoid false positives
    sql_no_strings = re.sub(r"'[^']*'", "", sql_clean)
    sql_no_strings = re.sub(r'"[^"]*"', "", sql_no_strings)
    if ";" in sql_no_strings.rstrip(";"):
        return False, "Multiple SQL statements are not allowed"

    return True, "OK"


# ── Column-level PII blocklist ──────────────────────────────────────────────

_AGGREGATE_FUNCS = ("COUNT", "SUM", "AVG", "MIN", "MAX", "STDDEV", "VARIANCE")
_STAR_SELECT = re.compile(r"\bSELECT\s+(?:DISTINCT\s+)?\*", re.IGNORECASE)


def _strip_strings(sql: str) -> str:
    """Remove string literals so identifiers aren't confused with data."""
    sql = re.sub(r"'[^']*'", "''", sql)
    sql = re.sub(r'"([^"]*)"', r"\1", sql)  # keep quoted identifiers readable
    return sql


def _select_projection(sql: str) -> str:
    """Return the projection clause (text between SELECT and the matching FROM)."""
    sql_u = sql.upper()
    select_idx = sql_u.find("SELECT")
    if select_idx < 0:
        return ""
    # Find FROM at the same nesting depth as the SELECT.
    depth = 0
    i = select_idx + len("SELECT")
    from_idx = -1
    while i < len(sql):
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and sql_u[i:i + 4] == "FROM" and (i == 0 or not sql[i - 1].isalnum()):
            from_idx = i
            break
        i += 1
    if from_idx < 0:
        return sql[select_idx + len("SELECT"):]
    return sql[select_idx + len("SELECT"):from_idx]


def _column_used_in_aggregate(projection: str, col: str) -> bool:
    """Check if every occurrence of `col` in the projection is inside an aggregate."""
    pattern = re.compile(rf"\b{re.escape(col)}\b", re.IGNORECASE)
    matches = list(pattern.finditer(projection))
    if not matches:
        return True  # not present at all → safe
    for m in matches:
        # Walk backwards to find whether we're inside AGG(...) at this position.
        depth = 0
        inside_agg = False
        for j in range(m.start() - 1, -1, -1):
            ch = projection[j]
            if ch == ")":
                depth += 1
            elif ch == "(":
                if depth == 0:
                    # Look at the word immediately before this paren.
                    before = projection[:j].rstrip()
                    word_match = re.search(r"(\w+)\s*$", before)
                    if word_match and word_match.group(1).upper() in _AGGREGATE_FUNCS:
                        inside_agg = True
                    break
                depth -= 1
        if not inside_agg:
            return False
    return True


def is_pii_column(col_name: str) -> bool:
    """Heuristic: does this column name suggest sensitive personal data?

    Matches if either the exact name is in the PII list, or a PII keyword is a
    substring of the column name (e.g. "customer_email" -> match on "email").
    Does NOT match in the reverse direction ("date" would otherwise match
    "date_of_birth", which is too aggressive).
    """
    name = col_name.lower().strip()
    if name in PII_COLUMN_NAMES:
        return True
    for pii_name in PII_COLUMN_NAMES:
        if pii_name in name:
            return True
    return False


def validate_sql_columns(
    sql: str,
    all_columns: list[str] | None = None,
    pii_columns: list[str] | None = None,
) -> tuple[bool, str]:
    """Block raw SELECT on PII columns.

    Rules:
    - `SELECT *` on a table that has any PII column is rejected.
    - A PII column in the projection must be wrapped in an aggregate function.
    - PII columns in WHERE / GROUP BY / ORDER BY are allowed (they don't leak
      values through the result set, only through row selection, which the
      downstream tokenizer handles).

    Either `pii_columns` is given explicitly, or `all_columns` is provided and
    we derive the PII subset via the column-name heuristic.
    """
    if not sql or not sql.strip():
        return False, "Empty query"

    if pii_columns is None:
        if not all_columns:
            return True, "OK"
        pii_columns = [c for c in all_columns if is_pii_column(c)]

    if not pii_columns:
        return True, "OK"

    clean = _strip_strings(sql)

    # Block SELECT * when PII columns exist.
    if _STAR_SELECT.search(clean):
        return (
            False,
            f"SELECT * is not allowed because the data contains sensitive columns "
            f"({', '.join(pii_columns)}). Select specific non-sensitive columns or use aggregates.",
        )

    projection = _select_projection(clean)
    for col in pii_columns:
        if not _column_used_in_aggregate(projection, col):
            return (
                False,
                f"Column '{col}' holds sensitive personal data and cannot be selected directly. "
                f"Wrap it in an aggregate (e.g. COUNT({col}), COUNT(DISTINCT {col})) or omit it.",
            )

    return True, "OK"
