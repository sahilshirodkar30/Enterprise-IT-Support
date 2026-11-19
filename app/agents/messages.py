NOT_FOUND = (
    "I couldn't find this in the IT support documentation. "
    "Please contact the IT Service Desk for help."
)
OUT_OF_SCOPE = "Sorry, I can only help with NovaRetail IT support questions."
INPUT_REFUSAL = "I couldn't process that message. Please rephrase your IT support question."
UNVERIFIED = (
    "I couldn't verify an answer to that from the IT documentation. "
    "Please contact the IT Service Desk."
)
DEGRADED = (
    "The IT support assistant is temporarily unavailable. "
    "Please try again shortly or contact the IT Service Desk."
)
CREDENTIAL_WARNING = (
    "For your security, don't share passwords or codes here. "
    "The IT Service Desk will never ask for them."
)
# Replies that were not generated from retrieved content. Never cache or cite these.
FALLBACK_REPLIES = frozenset({
    NOT_FOUND, OUT_OF_SCOPE, INPUT_REFUSAL, UNVERIFIED, DEGRADED, CREDENTIAL_WARNING,
})


def final_reply(text: str, *, blocked: bool = False, degraded: bool = False) -> dict:
    """Terminal state update. remember_node writes the AIMessage to history."""
    return {
        "answer": text,
        "blocked": blocked,
        "degraded": degraded,
        "finalized": True,
    }