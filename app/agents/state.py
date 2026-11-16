from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

Route = Literal["conversational", "technical", "out_of_scope", "blocked"]


class ChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str          # cleaned latest user message
    search_query: str      # planner's query for retrieval (technical only)
    route: Route
    chunks: list[dict]     # sanitized, reranked evidence
    answer: str
    blocked: bool
    degraded: bool
    finalized: bool        # True once the reply is ready to show