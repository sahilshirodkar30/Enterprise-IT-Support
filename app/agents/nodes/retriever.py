import logfire

from app.agents.state import ChatState
from app.config import get_settings
from app.guardrails.document_guard import sanitize_chunks
from services.embedding import embed_queries
from services.pinecone_store import get_index
from services.reranking import rerank


def retrieve_node(state: ChatState) -> dict:
    s = get_settings()
    query = state.get("search_query") or state["question"]

    try:
        vector = embed_queries([query])[0]
        result = get_index().query(
            vector=vector,
            top_k=s.RETRIEVAL_CANDIDATES,
            namespace=s.PINECONE_NAMESPACE,
            include_metadata=True,
        )
    except Exception:
        logfire.exception("vector search failed")
        return {"chunks": [], "degraded": True}

    candidates = []
    for m in result.matches:
        md = m.metadata or {}
        candidates.append({
            "text": md.get("text", ""),
            "source": md.get("source", "unknown"),
            "section": md.get("section"),
            "page": md.get("page"),
            "updated_at": md.get("updated_at"),
            "score": m.score,
        })

    chunks = rerank(query, candidates, top_n=s.RETRIEVAL_KEEP)

    if s.RERANK_MIN_SCORE is not None:
        chunks = [
            c for c in chunks
            if c.get("rerank_score") is None or c["rerank_score"] >= s.RERANK_MIN_SCORE
        ]

    return {"chunks": sanitize_chunks(chunks), "degraded": False}