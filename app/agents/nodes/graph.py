from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.nodes.guards import input_guard_node, output_guard_node
from app.agents.nodes.planner import planner_node
from app.agents.nodes.responder import respond_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.state import ChatState

# Per-turn fields are cleared at the start of every turn. The checkpointer
# keeps the whole state between turns, so without this a previous turn's
# chunks, answer, or finalized flag could leak into the next one.
TURN_RESET = {
    "question": "",
    "search_query": "",
    "route": "",
    "chunks": [],
    "answer": "",
    "blocked": False,
    "degraded": False,
    "finalized": False,
}


def reset_turn(state: ChatState) -> dict:
    return dict(TURN_RESET)


def _after_input(state: ChatState) -> Literal["planner", "end"]:
    return "end" if state.get("route") == "blocked" else "planner"


def _after_planner(state: ChatState) -> Literal["retrieve", "respond"]:
    return "retrieve" if state.get("route") == "technical" else "respond"


def build_graph(checkpointer=None):
    g = StateGraph(ChatState)

    g.add_node("reset_turn", reset_turn)
    g.add_node("input_guard", input_guard_node)
    g.add_node("planner", planner_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("respond", respond_node)
    g.add_node("output_guard", output_guard_node)

    g.add_edge(START, "reset_turn")
    g.add_edge("reset_turn", "input_guard")

    g.add_conditional_edges(
        "input_guard",
        _after_input,
        {"planner": "planner", "end": END},
    )
    g.add_conditional_edges(
        "planner",
        _after_planner,
        {"retrieve": "retrieve", "respond": "respond"},
    )
    g.add_edge("retrieve", "respond")
    g.add_edge("respond", "output_guard")
    g.add_edge("output_guard", END)

    return g.compile(checkpointer=checkpointer)


# In-process memory is lost on restart and is not shared between workers.
# For production, replace with a shared checkpointer (for example Postgres).
_checkpointer = MemorySaver()
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph(checkpointer=_checkpointer)
    return _graph