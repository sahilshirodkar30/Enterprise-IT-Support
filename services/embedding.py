from app.config import get_settings
from services.pinecone_store import get_pinecone_client

# Check the documented per-request input limit for your hosted model.
BATCH_SIZE = 96


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    if not texts:
        return []

    s = get_settings()
    client = get_pinecone_client()
    vectors: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        res = client.inference.embed(
            model=s.EMBEDDING_MODEL_NAME,
            inputs=texts[i:i + BATCH_SIZE],
            parameters={"input_type": input_type, "truncate": "END"},
        )
        vectors.extend(list(e.values) for e in res)

    if len(vectors) != len(texts):
        raise RuntimeError("embedding count does not match input count")
    bad = [v for v in vectors if len(v) != s.EMBEDDING_MODEL_DIMENSION]
    if bad:
        raise RuntimeError("embedding dimension does not match settings")
    return vectors


def embed_passages(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "passage")


def embed_queries(texts: list[str]) -> list[list[float]]:
    return _embed(texts, "query")