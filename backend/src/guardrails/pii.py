"""PII detection and masking — protects sensitive data from being exposed in responses."""

import re

# Patterns for common PII types
PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
    "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),  # Indian Aadhaar
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),  # Indian PAN
}

# Column names that likely contain PII
PII_COLUMN_NAMES = {
    "email", "e_mail", "email_address",
    "phone", "phone_number", "mobile", "contact",
    "ssn", "social_security", "social_security_number",
    "credit_card", "card_number", "cc_number",
    "password", "passwd", "pwd",
    "address", "home_address", "street_address",
    "date_of_birth", "dob", "birth_date",
    "aadhaar", "aadhar", "pan", "pan_number",
    "passport", "passport_number",
    "bank_account", "account_number",
}


def detect_pii_in_text(text: str) -> list[dict]:
    """Detect PII patterns in text. Returns list of {type, value, start, end}."""
    findings = []
    for pii_type, pattern in PII_PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append({
                "type": pii_type,
                "value": match.group(),
                "start": match.start(),
                "end": match.end(),
            })
    return findings


_MASK_LABELS = {
    "email": "[EMAIL HIDDEN]",
    "phone": "[PHONE HIDDEN]",
    "ssn": "[SSN HIDDEN]",
    "credit_card": "[CARD HIDDEN]",
    "ip_address": "[IP HIDDEN]",
    "aadhaar": "[AADHAAR HIDDEN]",
    "pan": "[PAN HIDDEN]",
}


def mask_pii_in_text(text: str) -> str:
    """Replace detected PII in text with masked versions."""
    masked, _ = mask_pii_in_text_with_count(text)
    return masked


def mask_pii_in_text_with_count(text: str) -> tuple[str, int]:
    """Same as `mask_pii_in_text`, but also returns the number of replacements."""
    if not text:
        return text, 0
    total = 0
    for pii_type, pattern in PII_PATTERNS.items():
        label = _MASK_LABELS.get(pii_type, f"[{pii_type.upper()} HIDDEN]")
        text, n = pattern.subn(label, text)
        total += n
    return text, total


def check_columns_for_pii(column_names: list[str]) -> list[str]:
    """Check if any column names suggest PII content."""
    flagged = []
    for col in column_names:
        col_lower = col.lower().strip()
        if col_lower in PII_COLUMN_NAMES:
            flagged.append(col)
        # Partial matches
        for pii_name in PII_COLUMN_NAMES:
            if pii_name in col_lower or col_lower in pii_name:
                if col not in flagged:
                    flagged.append(col)
    return flagged
