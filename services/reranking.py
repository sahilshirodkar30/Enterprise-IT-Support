import os
from functools import lru_cache

import logfire
from flashrank import Ranker, RerankRequest

MODEL_NAME = "ms-marco-MiniLM-L-12-v2"
CACHE_DIR = os.getenv("FLASHRANK_CACHE", ".cache/flashrank")


@lru_cache(maxsize=1)
def _ranker() -> Ranker:
    logfire.info("loading flashrank model", model=MODEL_NAME)
    return Ranker(model_name=MODEL_NAME, cache_dir=CACHE_DIR)


def rerank(query: str, chunks: list[dict], top_n: int = 4) -> list[dict]:
    if not chunks:
        return []

    passages = [{"id": i, "text": c["text"]} for i, c in enumerate(chunks)]
    try:
        with logfire.span("rerank", candidates=len(chunks)):
            results = _ranker().rerank(RerankRequest(query=query, passages=passages))
    except Exception:
        logfire.exception("rerank failed; falling back to vector order")
        return [{**c, "rerank_score": None} for c in chunks[:top_n]]

    return [
        {**chunks[int(r["id"])], "rerank_score": float(r["score"])}
        for r in results[:top_n]
    ]