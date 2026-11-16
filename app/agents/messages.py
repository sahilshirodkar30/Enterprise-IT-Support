from langchain_core.messages import AIMessage

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


def final_reply(text: str, *, blocked: bool = False, degraded: bool = False) -> dict:
    """A terminal state update. Downstream guards skip finalized replies."""
    return {
        "answer": text,
        "messages": [AIMessage(content=text)],
        "blocked": blocked,
        "degraded": degraded,
        "finalized": True,
    }