
import logfire
from langchain_core.messages import HumanMessage

from app.agents.messages import (
    DEGRADED,
    INPUT_REFUSAL,
    NOT_FOUND,
    UNVERIFIED,
    CREDENTIAL_WARNING,
    final_reply,
)
from app.agents.state import ChatState
from app.guardrails.exceptions import GuardrailBlocked, GuardrailUnavailable
from app.guardrails.input_guard import check_user_input
from app.guardrails.output_guard import validate_answer
from app.rag.context import sources_footer


def input_guard_node(state: ChatState) -> dict:
    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], HumanMessage):
        logfire.warning("Input guard received invalid message state")
        return {
            "route": "blocked",
            "question": "",
            **final_reply(INPUT_REFUSAL, blocked=True),
        }

    last = messages[-1]

    try:
        clean = check_user_input(last.content)

    except GuardrailBlocked as exc:
        reason = str(exc)
        logfire.info("Input guard blocked", reason=reason)
        text = CREDENTIAL_WARNING if reason == "credential_in_message" else INPUT_REFUSAL
        return {
            "route": "blocked",
            "question": "",
            **final_reply(text, blocked=True),
        }

    except Exception:
        logfire.exception("Unexpected input guard failure")
        return {
            "route": "blocked",
            "question": "",
            **final_reply(INPUT_REFUSAL, blocked=True),
        }

    updates = {
        "question": clean,
        "blocked": False,
    }

    if clean != last.content:
        updates["messages"] = [
            HumanMessage(content=clean, id=last.id)
        ]

    return updates


def output_guard_node(state: ChatState) -> dict:
    if state.get("finalized"):
        return {}

    route = state.get("route")
    chunks = state.get("chunks") or []

    try:
        validated = validate_answer(state.get("answer", ""), route, chunks)

    except GuardrailBlocked as exc:
        logfire.warn("Answer withheld", reason=str(exc), route=route)
        return final_reply(UNVERIFIED, blocked=True)

    except GuardrailUnavailable:
        logfire.exception("Output guard unavailable")
        return final_reply(DEGRADED, degraded=True)

    final = validated
    if route == "technical" and validated != NOT_FOUND:
        footer = sources_footer(validated, chunks)
        if footer:
            final = f"{validated}\n\n{footer}"

    return {**final_reply(final), "validated_answer": validated}