"""Unit-level conftest: mocks for Anthropic, ChromaDB, Voyage, ForgeRAG, MarkItDown."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import _fresh_session_state


# ---------------------------------------------------------------------------
# Anthropic mock helpers
# ---------------------------------------------------------------------------


def _make_anthropic_response(text="", tool_calls=None):
    """Factory for Anthropic API message responses.

    Args:
        text: Text content for the response.
        tool_calls: List of (name, input_dict, id) tuples for tool_use blocks.
    """
    content = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    for name, input_dict, tool_id in (tool_calls or []):
        content.append(
            SimpleNamespace(type="tool_use", name=name, input=input_dict, id=tool_id)
        )
    return SimpleNamespace(
        content=content,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        stop_reason="end_turn" if not tool_calls else "tool_use",
    )


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client with configurable responses."""
    client = MagicMock()
    client.messages.create.return_value = _make_anthropic_response("Default response")
    return client


# ---------------------------------------------------------------------------
# ChromaDB mock helpers
# ---------------------------------------------------------------------------


def _make_chroma_collection():
    """Create a mock ChromaDB collection."""
    collection = MagicMock()
    collection.count.return_value = 0
    collection.get.return_value = {"ids": []}
    collection.query.return_value = {
        "ids": [[]],
        "metadatas": [[]],
        "distances": [[]],
        "documents": [[]],
    }
    return collection


@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB persistent client with doc and conv collections."""
    client = MagicMock()
    doc_collection = _make_chroma_collection()
    conv_collection = _make_chroma_collection()

    def get_or_create(name, **kwargs):
        if name == "documents":
            return doc_collection
        return conv_collection

    client.get_or_create_collection.side_effect = get_or_create
    return client, doc_collection, conv_collection


# ---------------------------------------------------------------------------
# Voyage mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_voyage_client():
    """Mock Voyage AI client returning deterministic embeddings."""
    client = MagicMock()
    dim = 512

    def embed_fn(texts, **kwargs):
        return SimpleNamespace(embeddings=[[0.1] * dim for _ in texts])

    client.embed.side_effect = embed_fn
    return client


# ---------------------------------------------------------------------------
# ForgeRAG with mocked clients
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_forge_rag(mock_chroma_client, mock_voyage_client, tmp_path):
    """Real ForgeRAG instance with mocked ChromaDB + Voyage clients."""
    chroma_client, doc_collection, conv_collection = mock_chroma_client
    from pm_copilot.rag import ForgeRAG

    rag = ForgeRAG(
        project_dir=tmp_path,
        chroma_client=chroma_client,
        voyage_client=mock_voyage_client,
    )
    # Expose collections for test assertions
    rag._test_doc_collection = doc_collection
    rag._test_conv_collection = conv_collection
    return rag


# ---------------------------------------------------------------------------
# MarkItDown mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_markitdown():
    """Patch MarkItDown for docx conversion tests."""
    with patch("pm_copilot.chunking.MarkItDown", create=True) as MockClass:
        instance = MagicMock()
        MockClass.return_value = instance
        yield instance


# ---------------------------------------------------------------------------
# Session state fixture with st patching for tools.py
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_state_for_tools(mock_session_state):
    """MockSessionState patched into pm_copilot.tools.st.session_state."""
    mock_st = MagicMock()
    mock_st.session_state = mock_session_state
    with patch("pm_copilot.tools.st", mock_st):
        yield mock_session_state


# ---------------------------------------------------------------------------
# Session state fixture with st patching for orchestrator.py
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_state_for_orchestrator(mock_session_state):
    """MockSessionState patched into pm_copilot.orchestrator.st.session_state."""
    mock_st = MagicMock()
    mock_st.session_state = mock_session_state
    mock_st.cache_resource = lambda f: f  # passthrough decorator
    with patch("pm_copilot.orchestrator.st", mock_st):
        yield mock_session_state
