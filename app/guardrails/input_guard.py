import logfire

from app.guardrails.exceptions import GuardrailBlocked
from app.guardrails.patterns import has_injection, normalise, redact_cards

MAX_INPUT_CHARS = 4000


def check_user_input(text: object) -> str:
    """Return the cleaned input, or raise GuardrailBlocked. Never logs the text."""
    if not isinstance(text, str):
        raise GuardrailBlocked("invalid_type")

    cleaned = normalise(text).strip()
    if not cleaned:
        raise GuardrailBlocked("empty")
    if len(cleaned) > MAX_INPUT_CHARS:
        raise GuardrailBlocked("too_long")
    if has_injection(cleaned):
        logfire.warn("input withheld", reason="injection_pattern")
        raise GuardrailBlocked("injection_pattern")

    return redact_cards(cleaned)