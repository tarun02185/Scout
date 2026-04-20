"""Prompt-injection and data-extraction intent detection.

This is a heuristic filter that runs on every incoming user query *before* it
reaches the LLM. It blocks two classes of attack:

1. Prompt injection / jailbreak attempts — phrases that try to override the
   system prompt ("ignore previous instructions", "you are now a...").
2. PII extraction attempts — questions designed to elicit raw personal data
   ("list every email", "show me all phone numbers", "dump the table").

The filter is intentionally conservative: false positives are preferable to
leaking PII. Aggregate questions ("how many unique emails are there") are
allowed because they don't reveal individual values.
"""

import re


INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bignore\s+(?:(?:all|the|every|any|your|previous|above|prior|earlier)\s+)+(?:instructions?|prompts?|rules?|guidelines?|system)", re.IGNORECASE), "ignore-instructions"),
    (re.compile(r"\bforget\s+(?:(?:your|all|the|every|any)\s+)+(?:instructions?|prompts?|rules?|guidelines?)", re.IGNORECASE), "forget-instructions"),
    (re.compile(r"\bdisregard\s+(?:(?:your|all|the|previous|any|every)\s+)+(?:instructions?|prompts?|rules?|guidelines?)", re.IGNORECASE), "disregard-instructions"),
    (re.compile(r"\b(?:reveal|show|print|output|repeat|echo|tell|give)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instructions?|rules?|guidelines?)\b", re.IGNORECASE), "reveal-system-prompt"),
    (re.compile(r"\byou\s+are\s+now\s+(?:a|an|the)?\s*\w+", re.IGNORECASE), "role-override"),
    (re.compile(r"\bact\s+as\s+(?:a|an)\s+(?:different|new|other|unrestricted|uncensored)", re.IGNORECASE), "role-override"),
    (re.compile(r"\bpretend\s+(?:you\s*['']?re|you\s+are|to\s+be)\b", re.IGNORECASE), "role-override"),
    (re.compile(r"\bdeveloper\s+mode\b", re.IGNORECASE), "developer-mode"),
    (re.compile(r"\bDAN\s+mode\b|\bjailbreak\b", re.IGNORECASE), "jailbreak"),
    (re.compile(r"\b(?:print|dump|output|show|return|give|leak)\s+(?:me\s+)?(?:the\s+|your\s+|all\s+)*(?:raw|full|entire|complete)\s+(?:data|rows?|records?|table|dataset|file)", re.IGNORECASE), "raw-data-dump"),
    (re.compile(r"\bdump\s+(?:the\s+|all\s+)?(?:data|database|table|rows?|records?|file)", re.IGNORECASE), "raw-data-dump"),
]


# PII extraction intent — asks for enumerations of sensitive columns.
# Distinguishes from legitimate aggregate questions.
_PII_KEYWORDS = (
    r"emails?|phones?|phone\s+numbers?|addresses?|ssns?|social\s+security|"
    r"aadhaars?|pans?|passports?|credit\s+cards?|card\s+numbers?|passwords?|"
    r"date\s+of\s+births?|dobs?|contact\s+(?:info|details)"
)

EXTRACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"\b(?:list|show|give|print|output|display|reveal|tell\s+me|fetch|retrieve)\b[^.]{{0,40}}\b(?:all\s+|every\s+|each\s+)?(?:{_PII_KEYWORDS})\b", re.IGNORECASE), "pii-enumeration"),
    (re.compile(rf"\bwhat\s+(?:is|are)\s+(?:the\s+)?(?:{_PII_KEYWORDS})\b", re.IGNORECASE), "pii-lookup"),
    (re.compile(rf"\b(?:every|each)\s+(?:person|user|customer|employee|row|record)\s*['']?s?\s+(?:{_PII_KEYWORDS})\b", re.IGNORECASE), "pii-per-entity"),
    (re.compile(rf"\b(?:who|whose)\s+(?:has|is|owns)\s+.*\b(?:{_PII_KEYWORDS})\b", re.IGNORECASE), "pii-identify"),
    (re.compile(r"\b(?:full|complete)\s+(?:list|dump|export)\s+of\b", re.IGNORECASE), "full-export"),
]


# Aggregate safe-list — if the query is clearly an aggregate it's allowed
# even when it mentions PII keywords.
_AGGREGATE_SAFE = re.compile(
    r"\b(?:how\s+many|count|number\s+of|total|sum|average|avg|mean|median|"
    r"unique|distinct|percentage|ratio|distribution)\b",
    re.IGNORECASE,
)


def detect_injection(query: str) -> tuple[bool, str]:
    """Return (is_malicious, reason).

    `is_malicious=True` means the query should be rejected before reaching the
    LLM. `reason` is a short tag suitable for audit logs and user-facing
    messages.
    """
    if not query or not query.strip():
        return False, "ok"

    # Prompt-injection patterns are always blocked — no safe-list.
    for pattern, tag in INJECTION_PATTERNS:
        if pattern.search(query):
            return True, f"prompt_injection:{tag}"

    # Extraction patterns are blocked unless the query is clearly an aggregate.
    is_aggregate = bool(_AGGREGATE_SAFE.search(query))
    for pattern, tag in EXTRACTION_PATTERNS:
        if pattern.search(query) and not is_aggregate:
            return True, f"pii_extraction:{tag}"

    return False, "ok"


REFUSAL_MESSAGE = (
    "I can't share that. To protect privacy, I never reveal individual "
    "sensitive values (emails, phone numbers, addresses, IDs, card numbers, "
    "etc.) — even when asked directly.\n\n"
    "I can still help with **aggregate** questions like:\n"
    "- *How many unique emails are in the file?*\n"
    "- *What's the distribution of records per region?*\n"
    "- *Are there duplicate phone entries?*\n\n"
    "What would you like to explore?"
)
