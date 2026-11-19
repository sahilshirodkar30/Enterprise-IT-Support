import hashlib
import time

import logfire

from app.config import get_settings
from services.embedding import embed_queries
from services.pinecone_store import get_index

NAMESPACE = "cache"
# Pinecone caps metadata at 40 KB per vector. Stay under it with margin.
MAX_PAYLOAD_BYTES = 35_000


def _vector_id(question: str) -> str:
    normalized = " ".join(question.lower().split())
    return "cache-" + hashlib.sha256(normalized.encode()).hexdigest()[:32]


def cache_get(question: str) -> str | None:
    """Return the stored payload for a similar question, or None. Never raises."""
    s = get_settings()
    try:
        vector = embed_queries([question])[0]
        res = get_index().query(
            vector=vector,
            top_k=1,
            namespace=NAMESPACE,
            include_metadata=True,
            filter={"ts": {"$gte": time.time() - s.CACHE_TTL_SECONDS}},
        )
    except Exception:
        logfire.exception("cache lookup failed; continuing without cache")
        return None

    if not res.matches:
        return None

    top = res.matches[0]
    if top.score < s.CACHE_SIMILARITY:
        return None

    return (top.metadata or {}).get("payload")


def cache_put(question: str, payload: str) -> None:
    """Store a payload for a question. Never raises: a failed write must not fail the answer."""
    if len(payload.encode()) > MAX_PAYLOAD_BYTES:
        logfire.info("cache skipped, payload too large")
        return

    try:
        get_index().upsert(
            vectors=[{
                "id": _vector_id(question),
                "values": embed_queries([question])[0],
                "metadata": {"payload": payload, "ts": time.time()},
            }],
            namespace=NAMESPACE,
        )
    except Exception:
        logfire.exception("cache write failed")

def cache_clear() -> None:
    """Drop every cached answer. Call after the corpus changes."""
    get_index().delete(delete_all=True, namespace=NAMESPACE)