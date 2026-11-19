from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


Route = Literal[
    "conversational",
    "technical",
    "out_of_scope",
    "blocked",
]


class ChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]

    question: str
    search_query: str

    route: Route

    chunks: list[dict]
    sources: list[str]
    answer: str

    blocked: bool
    degraded: bool
    finalized: bool

    # Cache and conversation history
    cached: bool
    has_history: bool
    validated_answer: str 