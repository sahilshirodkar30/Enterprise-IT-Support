import logfire
from langchain_core.messages import HumanMessage

from app.agents.messages import (
    DEGRADED,
    INPUT_REFUSAL,
    NOT_FOUND,
    UNVERIFIED,
    final_reply,
)
from app.agents.state import ChatState
from app.guardrails.exceptions import GuardrailBlocked, GuardrailUnavailable
from app.guardrails.input_guard import check_user_input
from app.guardrails.output_guard import validate_answer
from app.rag.context import sources_footer


def input_guard_node(state: ChatState) -> dict:
    last = state["messages"][-1]
    try:
        clean = check_user_input(last.content)
    except GuardrailBlocked as exc:
        logfire.info("input guard blocked", reason=str(exc))
        return {"route": "blocked", "question": "", **final_reply(INPUT_REFUSAL, blocked=True)}

    updates: dict = {"question": clean, "blocked": False}
    if clean != last.content:
        # Same id replaces the stored message, so redacted text is what gets remembered.
        updates["messages"] = [HumanMessage(content=clean, id=last.id)]
    return updates


def output_guard_node(state: ChatState) -> dict:
    if state.get("finalized"):
        return {}

    route = state.get("route") or ""
    chunks = state.get("chunks") or []

    try:
        answer = validate_answer(state.get("answer", ""), route, chunks)
    except GuardrailBlocked as exc:
        logfire.warn("answer withheld", reason=str(exc), route=route)
        return final_reply(UNVERIFIED, blocked=True)
    except GuardrailUnavailable:
        logfire.exception("output guard unavailable")
        return final_reply(DEGRADED, degraded=True)

    if route == "technical" and answer != NOT_FOUND:
        footer = sources_footer(answer, chunks)
        if footer:
            answer = f"{answer}\n\n{footer}"

    return final_reply(answer)