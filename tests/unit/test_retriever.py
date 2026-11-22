
from types import SimpleNamespace

import pytest

from app.agents.nodes import retriever


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def create_state(question="My VPN is not working", search_query=None):
    return {
        "question": question,
        "search_query": search_query,
    }


def create_match(
    text="VPN connection troubleshooting",
    source="vpn_guide.pdf",
    section="VPN Support",
    page=2,
    updated_at="2026-01-01",
    score=0.95,
):
    return SimpleNamespace(
        metadata={
            "text": text,
            "source": source,
            "section": section,
            "page": page,
            "updated_at": updated_at,
        },
        score=score,
    )


def create_settings(
    candidates=10,
    keep=5,
    min_score=None,
):
    return SimpleNamespace(
        RETRIEVAL_CANDIDATES=candidates,
        RETRIEVAL_KEEP=keep,
        RERANK_MIN_SCORE=min_score,
        PINECONE_NAMESPACE="test-namespace",
    )


def mock_dependencies(monkeypatch, matches=None, chunks=None):
    """Mock settings, embeddings, Pinecone, reranking and sanitization."""

    if matches is None:
        matches = [create_match()]

    if chunks is None:
        chunks = [
            {
                "text": "VPN troubleshooting instructions",
                "source": "vpn_guide.pdf",
                "rerank_score": 0.95,
            }
        ]

    settings = create_settings()

    index = SimpleNamespace(
        query=lambda **kwargs: SimpleNamespace(matches=matches)
    )

    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: settings,
    )

    monkeypatch.setattr(
        retriever,
        "embed_queries",
        lambda queries: [[0.1, 0.2, 0.3]],
    )

    monkeypatch.setattr(
        retriever,
        "get_index",
        lambda: index,
    )

    monkeypatch.setattr(
        retriever,
        "rerank",
        lambda query, candidates, top_n: chunks,
    )

    monkeypatch.setattr(
        retriever,
        "sanitize_chunks",
        lambda chunks: chunks,
    )

    return settings, index


# --------------------------------------------------
# 1. Successful retrieval
# --------------------------------------------------

def test_retrieve_success(monkeypatch):
    mock_dependencies(monkeypatch)

    state = create_state()

    result = retriever.retrieve_node(state)

    assert result["degraded"] is False
    assert len(result["chunks"]) == 1
    assert result["chunks"][0]["source"] == "vpn_guide.pdf"


# --------------------------------------------------
# 2. Use search_query instead of question
# --------------------------------------------------

def test_retrieve_uses_search_query(monkeypatch):
    captured = {}

    def mock_embed(queries):
        captured["query"] = queries[0]
        return [[0.1, 0.2, 0.3]]

    mock_dependencies(monkeypatch)

    monkeypatch.setattr(
        retriever,
        "embed_queries",
        mock_embed,
    )

    state = create_state(
        question="Yes, it shows an authentication error",
        search_query="VPN authentication failure",
    )

    retriever.retrieve_node(state)

    assert captured["query"] == "VPN authentication failure"


# --------------------------------------------------
# 3. Fallback to original question
# --------------------------------------------------

def test_retrieve_uses_original_question(monkeypatch):
    captured = {}

    def mock_embed(queries):
        captured["query"] = queries[0]
        return [[0.1, 0.2, 0.3]]

    mock_dependencies(monkeypatch)

    monkeypatch.setattr(
        retriever,
        "embed_queries",
        mock_embed,
    )

    state = create_state(
        question="My VPN is not working",
        search_query="",
    )

    retriever.retrieve_node(state)

    assert captured["query"] == "My VPN is not working"


# --------------------------------------------------
# 4. Embedding failure
# --------------------------------------------------

def test_retrieve_embedding_failure(monkeypatch):
    mock_dependencies(monkeypatch)

    def mock_embed(queries):
        raise Exception("Embedding service unavailable")

    monkeypatch.setattr(
        retriever,
        "embed_queries",
        mock_embed,
    )

    result = retriever.retrieve_node(create_state())

    assert result["chunks"] == []
    assert result["degraded"] is True


# --------------------------------------------------
# 5. Pinecone query failure
# --------------------------------------------------

def test_retrieve_pinecone_failure(monkeypatch):
    mock_dependencies(monkeypatch)

    class MockIndex:
        def query(self, **kwargs):
            raise Exception("Pinecone unavailable")

    monkeypatch.setattr(
        retriever,
        "get_index",
        lambda: MockIndex(),
    )

    result = retriever.retrieve_node(create_state())

    assert result["chunks"] == []
    assert result["degraded"] is True


# --------------------------------------------------
# 6. No matching candidates
# --------------------------------------------------

def test_retrieve_no_candidates(monkeypatch):
    mock_dependencies(
        monkeypatch,
        matches=[],
    )

    result = retriever.retrieve_node(create_state())

    assert result["chunks"] == []
    assert result["degraded"] is False


# --------------------------------------------------
# 7. Reranking success
# --------------------------------------------------

def test_retrieve_rerank_success(monkeypatch):
    expected_chunks = [
        {
            "text": "VPN troubleshooting instructions",
            "source": "vpn_guide.pdf",
            "rerank_score": 0.95,
        }
    ]

    mock_dependencies(
        monkeypatch,
        chunks=expected_chunks,
    )

    result = retriever.retrieve_node(create_state())

    assert result["chunks"] == expected_chunks
    assert result["degraded"] is False


# --------------------------------------------------
# 8. Reranking failure
# --------------------------------------------------

def test_retrieve_rerank_failure(monkeypatch):
    mock_dependencies(monkeypatch)

    def mock_rerank(query, candidates, top_n):
        raise Exception("Reranking service unavailable")

    monkeypatch.setattr(
        retriever,
        "rerank",
        mock_rerank,
    )

    result = retriever.retrieve_node(create_state())

    assert result["chunks"] == []
    assert result["degraded"] is True


# --------------------------------------------------
# 9. Minimum rerank score filtering
# --------------------------------------------------

def test_retrieve_minimum_score_filter(monkeypatch):
    chunks = [
        {
            "text": "High score chunk",
            "source": "vpn.pdf",
            "rerank_score": 0.95,
        },
        {
            "text": "Low score chunk",
            "source": "vpn.pdf",
            "rerank_score": 0.30,
        },
        {
            "text": "No rerank score chunk",
            "source": "vpn.pdf",
            "rerank_score": None,
        },
    ]

    mock_dependencies(
        monkeypatch,
        chunks=chunks,
    )

    # Configure minimum rerank score.
    settings = retriever.get_settings()
    settings.RERANK_MIN_SCORE = 0.70

    result = retriever.retrieve_node(create_state())

    assert len(result["chunks"]) == 2

    scores = [
        chunk["rerank_score"]
        for chunk in result["chunks"]
    ]

    assert 0.95 in scores
    assert None in scores
    assert 0.30 not in scores


# --------------------------------------------------
# 10. Missing metadata handling
# --------------------------------------------------

def test_retrieve_missing_metadata(monkeypatch):
    match = SimpleNamespace(
        metadata=None,
        score=0.80,
    )

    captured = {}

    def mock_rerank(query, candidates, top_n):
        captured["candidates"] = candidates
        return []

    mock_dependencies(
        monkeypatch,
        matches=[match],
    )

    monkeypatch.setattr(
        retriever,
        "rerank",
        mock_rerank,
    )

    result = retriever.retrieve_node(create_state())

    candidate = captured["candidates"][0]

    assert candidate["text"] == ""
    assert candidate["source"] == "unknown"
    assert candidate["section"] is None
    assert candidate["page"] is None
    assert candidate["updated_at"] is None
    assert candidate["score"] == 0.80

    assert result["degraded"] is False


# --------------------------------------------------
# 11. Verify Pinecone query configuration
# --------------------------------------------------

def test_retrieve_pinecone_query_parameters(monkeypatch):
    captured = {}

    class MockIndex:
        def query(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(matches=[])

    settings = create_settings(
        candidates=15,
        keep=5,
    )

    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: settings,
    )

    monkeypatch.setattr(
        retriever,
        "embed_queries",
        lambda queries: [[0.1, 0.2, 0.3]],
    )

    monkeypatch.setattr(
        retriever,
        "get_index",
        lambda: MockIndex(),
    )

    result = retriever.retrieve_node(create_state())

    assert captured["vector"] == [0.1, 0.2, 0.3]
    assert captured["top_k"] == 15
    assert captured["namespace"] == "test-namespace"
    assert captured["include_metadata"] is True

    assert result["degraded"] is False


# --------------------------------------------------
# 12. Verify reranking parameters
# --------------------------------------------------

def test_retrieve_rerank_parameters(monkeypatch):
    captured = {}

    def mock_rerank(query, candidates, top_n):
        captured["query"] = query
        captured["candidates"] = candidates
        captured["top_n"] = top_n
        return []

    mock_dependencies(monkeypatch)

    monkeypatch.setattr(
        retriever,
        "rerank",
        mock_rerank,
    )

    state = create_state(
        search_query="VPN authentication troubleshooting"
    )

    retriever.retrieve_node(state)

    assert captured["query"] == "VPN authentication troubleshooting"
    assert captured["top_n"] == 5
    assert len(captured["candidates"]) == 1


# --------------------------------------------------
# 13. Verify chunk sanitization
# --------------------------------------------------

def test_retrieve_sanitizes_chunks(monkeypatch):
    chunks = [
        {
            "text": "VPN troubleshooting",
            "source": "vpn.pdf",
            "rerank_score": 0.95,
        }
    ]

    sanitized_chunks = [
        {
            "text": "Clean VPN troubleshooting",
            "source": "vpn.pdf",
        }
    ]

    captured = {}

    def mock_sanitize(input_chunks):
        captured["chunks"] = input_chunks
        return sanitized_chunks

    mock_dependencies(
        monkeypatch,
        chunks=chunks,
    )

    monkeypatch.setattr(
        retriever,
        "sanitize_chunks",
        mock_sanitize,
    )

    result = retriever.retrieve_node(create_state())

    assert captured["chunks"] == chunks
    assert result["chunks"] == sanitized_chunks
    assert result["degraded"] is False
