
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.nodes import planner

def mock_llm_response(response):
    """Create a mock LLM whose invoke() returns the given response."""
    class MockLLM:
        def invoke(self, messages):
            return SimpleNamespace(content=response)

    return MockLLM()

def create_state(question, messages=None):
    """Create a minimal ChatState for planner_node."""
    if messages is None:
        messages = [HumanMessage(content=question)]

    return {
        "question": question,
        "messages": messages,
    }

# --------------------------------------------------
# 1. Conversational question
# --------------------------------------------------

def test_planner_conversational(monkeypatch):
    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response("CONVERSATIONAL"),
    )

    state = create_state("Hello")

    result = planner.planner_node(state)

    assert result["route"] == "conversational"
    assert result["search_query"] == ""

# --------------------------------------------------
# 2. Out-of-scope question
# --------------------------------------------------

def test_planner_out_of_scope(monkeypatch):
    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response("OUT_OF_SCOPE"),
    )

    state = create_state("What is the capital of France?")

    result = planner.planner_node(state)

    assert result["route"] == "out_of_scope"
    assert result["search_query"] == ""

# --------------------------------------------------
# 3. Technical search query
# --------------------------------------------------

def test_planner_technical_search(monkeypatch):
    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response(
            "SEARCH: VPN connection troubleshooting"
        ),
    )

    state = create_state("My VPN is not working")

    result = planner.planner_node(state)

    assert result["route"] == "technical"
    assert result["search_query"] == "VPN connection troubleshooting"

# --------------------------------------------------
# 4. Search query with extra whitespace
# --------------------------------------------------

def test_planner_search_strips_whitespace(monkeypatch):
    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response(
            "SEARCH:   VPN authentication issue   "
        ),
    )

    state = create_state("VPN authentication failed")

    result = planner.planner_node(state)

    assert result["route"] == "technical"
    assert result["search_query"] == "VPN authentication issue"

# --------------------------------------------------
# 5. Empty search query fallback
# --------------------------------------------------

def test_planner_empty_search_query(monkeypatch):
    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response("SEARCH:"),
    )

    question = "My VPN is not working"
    state = create_state(question)

    result = planner.planner_node(state)

    assert result["route"] == "technical"
    assert result["search_query"] == question

# --------------------------------------------------
# 6. Unexpected LLM response
# --------------------------------------------------

def test_planner_unexpected_response(monkeypatch):
    
    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response("I think this is a VPN issue"),
    )

    question = "My VPN is not working"
    state = create_state(question)

    result = planner.planner_node(state)

    assert result["route"] == "technical"
    assert result["search_query"] == question

# --------------------------------------------------
# 7. LLM exception fallback
# --------------------------------------------------

def test_planner_llm_exception(monkeypatch):
    class MockLLM:
        def invoke(self, messages):
            raise Exception("LLM API unavailable")

    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: MockLLM(),
    )

    question = "My VPN is not working"
    state = create_state(question)

    result = planner.planner_node(state)

    assert result["route"] == "technical"
    assert result["search_query"] == question[:planner.MAX_QUERY_CHARS]

# --------------------------------------------------
# 8. Search query maximum length
# --------------------------------------------------

def test_planner_query_length_limit(monkeypatch):
    long_query = "A" * 300

    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response(f"SEARCH: {long_query}"),
    )

    state = create_state("Search for VPN troubleshooting")

    result = planner.planner_node(state)

    assert result["route"] == "technical"
    assert len(result["search_query"]) == planner.MAX_QUERY_CHARS

# --------------------------------------------------
# 9. Original question maximum length on fallback
# --------------------------------------------------

def test_planner_fallback_query_length(monkeypatch):
    monkeypatch.setattr(
        planner,
        "_llm",
        lambda: mock_llm_response("INVALID RESPONSE"),
    )

    question = "A" * 300
    state = create_state(question)

    result = planner.planner_node(state)

    assert result["route"] == "technical"
    assert len(result["search_query"]) == planner.MAX_QUERY_CHARS

# --------------------------------------------------
# 10. History formatting
# --------------------------------------------------

def test_history_text():
    messages = [
        HumanMessage(content="My VPN is not working"),
        AIMessage(content="Are you getting an error?"),
        HumanMessage(content="Yes, authentication failed"),
    ]

    result = planner._history_text(messages)

    # The latest message is excluded.
    assert "User: My VPN is not working" in result
    assert "Assistant: Are you getting an error?" in result
    assert "Yes, authentication failed" not in result

# --------------------------------------------------
# 11. History turn limit
# --------------------------------------------------

def test_history_turn_limit():
    messages = []

    for i in range(10):
        messages.append(
            HumanMessage(content=f"Question {i}")
        )

    result = planner._history_text(messages)

    # Latest message is excluded.
    assert "Question 9" not in result

    # Only the last six previous messages are retained.
    assert "Question 3" in result
    assert "Question 8" in result
    assert "Question 2" not in result

# --------------------------------------------------
# 12. History character limit
# --------------------------------------------------

def test_history_character_limit():
    long_message = "A" * 600

    messages = [
        HumanMessage(content=long_message),
        HumanMessage(content="Latest question"),
    ]

    result = planner._history_text(messages)

    assert len(result.split(": ", 1)[1]) == planner.HISTORY_CHARS

# --------------------------------------------------
# 13. Empty history
# --------------------------------------------------

def test_empty_history():
    result = planner._history_text([])

    assert result == "(none)"