import re

import logfire

from app.guardrails.patterns import has_injection, normalise

_CONTEXT_TAG = re.compile(
    r"</?\s*(context|excerpts?|answer|message|evidence)\s*>",
    re.IGNORECASE,
)

def sanitize_chunks(chunks: list[dict]) -> list[dict]:
    """
    Drop empty chunks and chunks with injection-like text, and remove
    delimiter tags that could break the prompt structure.
    Withheld chunks are logged by source so bad documents are visible.
    """
    kept = []
    for c in chunks:
        text = normalise(c.get("text") or "").strip()
        if not text:
            continue
        if has_injection(text):
            logfire.warn(
                "retrieved chunk withheld",
                source=c.get("source", "unknown"),
                reason="injection_pattern",
            )
            continue
        kept.append({**c, "text": _CONTEXT_TAG.sub("", text)})
    return kept