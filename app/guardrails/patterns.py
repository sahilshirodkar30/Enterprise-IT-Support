"""Deterministic security checks. One source of truth for every guard."""

import re
import unicodedata

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
]

_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
# 13 to 19 digits, optionally separated by spaces or hyphens.
_CARD_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_SECRET_RE = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(
        r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*\S{8,}",
        re.IGNORECASE,
    ),
]


def normalise(text: str) -> str:
    """Fold look-alike characters and strip invisible ones before matching."""
    return _INVISIBLE_RE.sub("", unicodedata.normalize("NFKC", text))


def has_injection(text: str) -> bool:
    t = normalise(text)
    return any(p.search(t) for p in _INJECTION_RE)


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _is_card(candidate: str) -> bool:
    digits = re.sub(r"\D", "", candidate)
    return 13 <= len(digits) <= 19 and luhn_ok(digits)


def contains_card(text: str) -> bool:
    return any(_is_card(m.group()) for m in _CARD_RE.finditer(text))


def redact_cards(text: str) -> str:
    return _CARD_RE.sub(
        lambda m: "[card number removed]" if _is_card(m.group()) else m.group(),
        text,
    )


def contains_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_RE)