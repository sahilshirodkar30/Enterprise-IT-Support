
"""Deterministic security checks.
One source of truth for every guard.
"""

import re
import unicodedata


# Common prompt-injection patterns.
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+instructions",
    r"ignore\s+(the\s+)?system\s+prompt",
    r"(reveal|print|show|repeat)\s+(me\s+)?(the\s+|your\s+)?(system\s+prompt|hidden\s+instructions)",
    r"(show|give|send)\s+(me\s+)?(your\s+|the\s+)?api\s+keys?",
    r"override\s+(all\s+)?(instructions|safety|rules)",
    r"bypass\s+(all\s+)?(safety|guardrails?|rules)",
    r"developer\s+mode\s+enabled",
    r"you\s+are\s+now\s+(an?\s+)?unrestricted",
    r"follow\s+these\s+instructions\s+instead",
    # add to INJECTION_PATTERNS
    r"(what|show|print)\s+(are|is)\s+your\s+(system\s+)?(instructions|rules|prompt)",
    r"act\s+as\s+(an?\s+)?(admin|administrator|domain\s+admin)",
]

_INJECTION_RE = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in INJECTION_PATTERNS
]


# Remove invisible and bidirectional formatting characters.
_INVISIBLE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]"
)


# 13 to 19 digits, optionally separated by spaces or hyphens.
_CARD_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")


# Common API keys, credentials and access tokens.
_SECRET_RE = [
    # OpenAI-style secret keys.
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),

    # API keys, passwords and tokens assigned to values.
    re.compile(
        r"\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|"
        r"access[_-]?token|refresh[_-]?token|password|passwd)"
        r"\s*[:=]\s*[\"']?\S{8,}",
        re.IGNORECASE,
    ),

    # Bearer authentication tokens.
    re.compile(
        r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}",
        re.IGNORECASE,
    ),

    # GitHub personal access tokens.
    re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|"
        r"github_pat_[A-Za-z0-9_]{20,})"
    ),
    re.compile(
        r"\b(?:my|the|your)\s+(?:password|passcode|pin|mfa\s+code|otp|one[- ]time\s+code)"
        r"\s+(?:is|=|:)\s*\S{4,}",
        re.IGNORECASE,
    ),

    # Six-digit one-time codes next to a code keyword.
    re.compile(
        r"\b(?:mfa|otp|verification|authenticator)\s+code\D{0,10}\d{6}\b",
        re.IGNORECASE,
    ),
]


def normalise(text: str) -> str:
    """
    Apply Unicode compatibility normalization
    and remove invisible formatting characters.
    """
    normalized = unicodedata.normalize("NFKC", text)
    return _INVISIBLE_RE.sub("", normalized)


def has_injection(text: str) -> bool:
    """Check for known prompt-injection patterns."""

    cleaned = normalise(text)

    return any(
        pattern.search(cleaned)
        for pattern in _INJECTION_RE
    )


def luhn_ok(digits: str) -> bool:
    """Validate a card number using the Luhn algorithm."""

    total = 0

    for i, ch in enumerate(reversed(digits)):
        digit = int(ch)

        if i % 2 == 1:
            digit *= 2

            if digit > 9:
                digit -= 9

        total += digit

    return total % 10 == 0


def _is_card(candidate: str) -> bool:
    """Check whether a candidate is a valid Luhn number."""

    digits = re.sub(r"\D", "", candidate)

    return (
        13 <= len(digits) <= 19
        and luhn_ok(digits)
    )


def contains_card(text: str) -> bool:
    """Detect valid payment card numbers."""

    cleaned = normalise(text)

    return any(
        _is_card(match.group())
        for match in _CARD_RE.finditer(cleaned)
    )


def redact_cards(text: str) -> str:
    """Replace detected payment card numbers."""

    cleaned = normalise(text)

    return _CARD_RE.sub(
        lambda match: (
            "[card number removed]"
            if _is_card(match.group())
            else match.group()
        ),
        cleaned,
    )


def contains_secret(text: str) -> bool:
    """Detect common API keys and credentials."""

    cleaned = normalise(text)

    return any(
        pattern.search(cleaned)
        for pattern in _SECRET_RE
    )
