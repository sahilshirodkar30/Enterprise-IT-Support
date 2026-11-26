import json
import time
import logfire
from typing import Literal
import hashlib
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.messages import DEGRADED, FALLBACK_REPLIES
from app.agents.nodes.guards import input_guard_node, output_guard_node
from app.agents.nodes.planner import planner_node
from app.agents.nodes.responder import respond_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.state import ChatState
from app.cache.semantic_cache import cache_get, cache_put
from app.security.rate_limiter import limiter

MAX_QUESTION_CHARS = 1000

def _hash_user(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]

def reset_turn(state: ChatState) -> dict:
    """Clear per-turn fields. Never touch question or messages."""
    return {
        "search_query": "",
        "route": "conversational",
        "chunks": [],
        "sources": [],
        "answer": "",
        "validated_answer": "",
        "blocked": False,
        "degraded": False,
        "finalized": False,
        "cached": False,
    }

def input_route(state: ChatState) -> Literal["cache", "remember"]:
    blocked = state.get("blocked") or state.get("route") == "blocked"
    return "remember" if blocked else "cache"


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
    with logfire.span("node.cache") as span:
        raw = cache_get(state["question"])
        span.set_attribute("hit", bool(raw))
        span.set_attribute("duration_ms", round((time.perf_counter() - start) * 1000, 1))

    
    if not raw:
        logfire.info("cache miss")
        return {"cached": False}

    try:
        payload = json.loads(raw)
        answer = payload["answer"]
        sources = payload.get("sources", [])
        chunks = payload.get("chunks", [])
    except (ValueError, KeyError, TypeError):
        logfire.warn("unreadable cache entry, ignoring")
        return {"cached": False}

    # Restore route and chunks so output_guard validates against the same context as the original answer
    logfire.info("cache hit, skipping LLM", answer_chars=len(answer))
    return {
        "answer": answer,
        "sources": sources,
        "chunks": chunks,
        "route": "technical",
        "cached": True,
    }



def remember_node(state: ChatState) -> dict:
    """Single place that writes this turn to thread history, cache, and sources."""
    answer = state.get("answer", "")
    validated = state.get("validated_answer") or answer
    blocked = bool(state.get("blocked"))
    cached = bool(state.get("cached"))
    is_fallback = blocked or answer in FALLBACK_REPLIES

    print("\n\n\n Remenber layer: ",answer)

    if is_fallback:
        sources: list[str] = []
    elif cached:
        sources = state.get("sources", [])
    else:
        sources = sorted({
            chunk["source"]
            for chunk in state.get("chunks", [])
            if chunk.get("source")
        })

    cacheable = (
        not cached
        and not blocked
        and not state.get("degraded")
        and not state.get("has_history")
        and bool(state.get("chunks"))
        and not is_fallback
    )
    if cacheable:
        payload = {
            "answer": validated,
            "sources": sources,
            "chunks": state.get("chunks", []),
        }
        cache_put(state["question"], json.dumps(payload))
        logfire.info("answer cached", answer_chars=len(validated))

    update: dict = {
        "sources": sources,
        "messages": [AIMessage(content=answer)],
        "finalized": True,
    }

    if blocked:
        human = next(
            (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
            None,
        )
        if human is not None and human.id:
            update["messages"] = [RemoveMessage(id=human.id), AIMessage(content=answer)]

    return update

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


# MemorySaver is in-process only. Use a persistent checkpointer (e.g. Postgres) in production.
graph = build_graph(MemorySaver())


def _result(answer: str, sources: list[str] | None = None, blocked: bool = False,
            history_count: int = 0) -> dict:
    return {
        "answer": answer,
        "sources": sources or [],
        "blocked": blocked,
        "history_count": history_count,
    }


def get_history_count(thread_key: str) -> int:
    """Number of earlier questions in this thread."""
    snapshot = graph.get_state({"configurable": {"thread_id": thread_key}})
    messages = (snapshot.values or {}).get("messages", [])
    return sum(isinstance(message, HumanMessage) for message in messages)


def handle_question(user_id: str, question: str, thread_id: str) -> dict:
    started = time.perf_counter()
    log = logfire.with_tags("Chat")

    question = question.strip()
    if not question:
        return _result("Please enter a question.")

    if len(question) > MAX_QUESTION_CHARS:
        log.warn("question too long", length=len(question), limit=MAX_QUESTION_CHARS)
        return _result(f"Please keep your question shorter than {MAX_QUESTION_CHARS} characters.")

    if not limiter.allow(user_id):
        log.warn("rate limited", user_id=user_id)
        return _result("You're asking too fast. Please wait a minute.")
    
    # Bind the thread to the authenticated user so a client can't write into someone else's history.
    # user_id must come from auth, not from the request body.
    thread_key = f"{user_id}:{thread_id}"
    config = {"configurable": {"thread_id": thread_key}}

    try:
        previous = get_history_count(thread_key)

        turn_input = {
            "question": question,
            "messages": [HumanMessage(content=question)],
            "has_history": previous > 0,
            "cached": False,
            "blocked": False,
            "degraded": False,
            "chunks": [],
            "sources": [],
            "answer": "",
        }

        with logfire.span("chat.graph", user_hash=_hash_user(user_id)) as span:
            out = graph.invoke(turn_input, config=config)
            span.set_attribute("cached", bool(out.get("cached")))
            span.set_attribute("blocked", bool(out.get("blocked")))
    except Exception:
        logfire.exception("chat graph failed", user_id=user_id)
        return _result(DEGRADED)

    answer = out.get("answer") or "Sorry, I couldn't prepare an answer. Please try again."
    if not out.get("answer"):
        log.error("graph finished without an answer", state_keys=sorted(out.keys()))

    blocked = bool(out.get("blocked"))
    sources = out.get("sources", [])
    history_count = sum(isinstance(m, HumanMessage) for m in out.get("messages", []))

    log.info(
        "question finished",
        user_id=user_id,
        total_ms=round((time.perf_counter() - started) * 1000, 1),
        from_cache=bool(out.get("cached")),
        blocked=blocked,
        history_count=history_count,
        sources=sources,
        answer_chars=len(answer),
    )

    return _result(answer, sources, blocked, history_count)