import logfire

from app.guardrails.exceptions import GuardrailBlocked
from app.guardrails.patterns import contains_secret, has_injection, normalise, redact_cards

# Single source of truth for the question length limit. graph.py imports this.
MAX_QUESTION_CHARS = 1000


def check_user_input(text: object) -> str:
    """Return the cleaned input, or raise GuardrailBlocked. Never logs the text."""
    if not isinstance(text, str):
        raise GuardrailBlocked("invalid_type")

    cleaned = normalise(text).strip()
    if not cleaned:
        raise GuardrailBlocked("empty")
    if len(cleaned) > MAX_QUESTION_CHARS:
        raise GuardrailBlocked("too_long")
    if has_injection(cleaned):
        logfire.warn("input withheld", reason="injection_pattern")
        raise GuardrailBlocked("injection_pattern")
    if contains_secret(cleaned):
        # Keep credentials out of the LLM, the planner, and thread history.
        logfire.warn("input withheld", reason="credential_in_message")
        raise GuardrailBlocked("credential_in_message")

    return redact_cards(cleaned)