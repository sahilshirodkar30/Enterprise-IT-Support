import time
import logfire
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.nodes.planner import planner_node
from app.cache.semantic_cache import cache_get, cache_put
from app.agents.nodes.responder import respond_node
from app.agents.nodes.guards import input_guard_node, output_guard_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.state import ChatState

MAX_QUESTION_CHARS = 1000


def reset_turn(state: ChatState) -> dict:
    """Clear per-turn fields. Never touch `question` or `messages`."""
    return {
        "search_query": "",
        "route": "",
        "chunks": [],
        "answer": "",
        "blocked": False,
        "degraded": False,
        "finalized": False,
    }


def input_route(state: ChatState) -> Literal["cache", "remember"]:
    return "remember" if state.get("route") == "blocked" else "cache"


def cache_route(state: ChatState) -> Literal["hit", "miss"]:
    route = "hit" if state.get("cached") else "miss"
    logfire.debug("route after cache", route=route)
    return route


def planner_route(state: ChatState) -> Literal["retrieve", "respond"]:
    return "retrieve" if state.get("route") == "technical" else "respond"


def cache_node(state: ChatState) -> dict:
    # Cached answers ignore earlier turns, so skip the cache for follow-up questions
    if state.get("has_history"):
        logfire.info("cache skipped, follow-up question")
        return {"cached": False}

    start = time.perf_counter()
    with logfire.span("node.cache", question=state["question"]) as span:
        hit = cache_get(state["question"])
        span.set_attribute("hit", bool(hit))
        span.set_attribute("duration_ms", round((time.perf_counter() - start) * 1000, 1))

    if hit:
        logfire.info("cache hit, skipping LLM", answer_chars=len(hit))
        return {"answer": hit, "cached": True}

    logfire.info("cache miss")
    return {"cached": False}


def remember_node(state: ChatState) -> dict:
    """Store this turn's answer in the thread history. Every path ends here."""
    return {"messages": [AIMessage(content=state.get("answer", ""))]}


def build_graph(checkpointer=None):
    g = StateGraph(ChatState)

    g.add_node("reset_turn", reset_turn)
    g.add_node("input_guard", input_guard_node)
    g.add_node("cache", cache_node)
    g.add_node("planner", planner_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("respond", respond_node)
    g.add_node("output_guard", output_guard_node)
    g.add_node("remember", remember_node)

    g.add_edge(START, "reset_turn")
    g.add_edge("reset_turn", "input_guard")
    g.add_conditional_edges("input_guard", input_route,
                            {"cache": "cache", "remember": "remember"})
    g.add_conditional_edges("cache", cache_route,
                            {"hit": "output_guard", "miss": "planner"})
    g.add_conditional_edges("planner", planner_route,
                            {"retrieve": "retrieve", "respond": "respond"})
    g.add_edge("retrieve", "respond")
    g.add_edge("respond", "output_guard")
    g.add_edge("output_guard", "remember")
    g.add_edge("remember", END)

    return g.compile(checkpointer=checkpointer)


# Checkpointer is required for thread history (get_state / messages).
# Swap MemorySaver for a persistent checkpointer (e.g. Postgres) in production.
graph = build_graph(MemorySaver())


def _result(answer: str, sources: list[str] | None = None, blocked: bool = False,
            history_count: int = 0) -> dict:
    return {
        "answer": answer,
        "sources": sources or [],
        "blocked": blocked,
        "history_count": history_count,
    }


def get_history_count(thread_id: str) -> int:
    """Number of earlier questions in this thread (each turn is one question and one answer)."""
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    messages = snapshot.values.get("messages", []) if snapshot.values else []
    return len(messages) // 2


def handle_question(user_id: str, question: str, thread_id: str) -> dict:
    started = time.perf_counter()
    log = logfire.with_tags("Chat")

    question = question.strip()
    if not question:
        return _result("Please enter a question.")

    if len(question) > MAX_QUESTION_CHARS:
        log.warn("question too long", length=len(question), limit=MAX_QUESTION_CHARS)
        return _result(f"Please keep your question shorter than {MAX_QUESTION_CHARS} characters.")

    config = {"configurable": {"thread_id": thread_id}}
    previous = get_history_count(thread_id)

    turn_input = {
        "question": question,
        "messages": [HumanMessage(content=question)],
        "has_history": previous > 0,
        "cached": False,
        "blocked": False,
        "degraded": False,
        "chunks": [],
        "answer": "",
    }

    with logfire.span("chat.graph", user_id=user_id) as span:
        out = graph.invoke(turn_input, config=config)
        span.set_attribute("cached", bool(out.get("cached")))
        span.set_attribute("blocked", bool(out.get("blocked")))

    answer = out.get("answer") or "Sorry, I couldn't prepare an answer. Please try again."
    if not out.get("answer"):
        log.error("graph finished without an answer", state_keys=sorted(out.keys()))

    blocked = bool(out.get("blocked"))
    sources = [] if blocked else sorted({c["source"] for c in out.get("chunks", [])})

    cacheable = (
        out.get("chunks")
        and not out.get("cached")
        and not out.get("degraded")
        and not blocked
        and previous == 0
    )
    if cacheable:
        cache_put(question, answer)
        log.info("answer cached", answer_chars=len(answer))

    history_count = get_history_count(thread_id)
    log.info(
        "question finished",
        user_id=user_id,
        total_ms=round((time.perf_counter() - started) * 1000, 1),
        from_cache=bool(out.get("cached")),
        blocked=blocked,
        history_count=history_count,
        sources=sources,
        answer_preview=answer,
    )

    return _result(answer, sources, blocked, history_count)