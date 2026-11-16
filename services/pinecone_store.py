import time
from functools import lru_cache

from pinecone import Pinecone, ServerlessSpec

from app.config import get_settings


@lru_cache(maxsize=1)
def get_pinecone_client() -> Pinecone:
    return Pinecone(api_key=get_settings().PINECONE_API_KEY.get_secret_value())


def ensure_index(timeout_s: float = 120.0) -> None:
    s = get_settings()
    pc = get_pinecone_client()

    if not pc.has_index(s.PINECONE_INDEX_NAME):
        pc.create_index(
            name=s.PINECONE_INDEX_NAME,
            dimension=s.EMBEDDING_MODEL_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=s.PINECONE_CLOUD, region=s.PINECONE_REGION),
        )

    deadline = time.monotonic() + timeout_s
    while True:
        desc = pc.describe_index(s.PINECONE_INDEX_NAME)
        if desc.status["ready"]:
            break
        if time.monotonic() > deadline:
            raise TimeoutError("Pinecone index did not become ready in time")
        time.sleep(2)

    if desc.dimension != s.EMBEDDING_MODEL_DIMENSION:
        raise RuntimeError(
            f"index dimension {desc.dimension} does not match "
            f"EMBEDDING_MODEL_DIMENSION {s.EMBEDDING_MODEL_DIMENSION}"
        )


@lru_cache(maxsize=1)
def get_index():
    ensure_index()
    return get_pinecone_client().Index(get_settings().PINECONE_INDEX_NAME)