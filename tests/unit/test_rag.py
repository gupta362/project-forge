"""Unit tests for pm_copilot.rag — ForgeRAG with mocked ChromaDB + Voyage."""

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from pm_copilot.rag import ForgeRAG, format_context_block


# ===================================================================
# __init__
# ===================================================================


class TestForgeRAGInit:
    def test_creates_both_collections(self, mock_chroma_client, mock_voyage_client, tmp_path):
        client, doc_col, conv_col = mock_chroma_client
        rag = ForgeRAG(tmp_path, client, mock_voyage_client)
        assert client.get_or_create_collection.call_count == 2
        call_names = [c.kwargs.get("name") or c.args[0]
                      for c in client.get_or_create_collection.call_args_list]
        assert "documents" in call_names
        assert "conversations" in call_names

    def test_disabled_without_voyage(self, mock_chroma_client, tmp_path):
        client, _, _ = mock_chroma_client
        rag = ForgeRAG(tmp_path, client, voyage_client=None)
        assert rag.enabled is False

    def test_enabled_with_voyage(self, mock_forge_rag):
        assert mock_forge_rag.enabled is True


# ===================================================================
# _embed batching
# ===================================================================


class TestEmbedBatching:
    def test_single_batch_under_128(self, mock_forge_rag, mock_voyage_client):
        texts = [f"text {i}" for i in range(50)]
        result = mock_forge_rag._embed(texts)
        assert len(result) == 50
        assert mock_voyage_client.embed.call_count == 1

    def test_multiple_batches_over_128(self, mock_forge_rag, mock_voyage_client):
        texts = [f"text {i}" for i in range(300)]
        result = mock_forge_rag._embed(texts)
        assert len(result) == 300
        # ceil(300/128) = 3 batches
        assert mock_voyage_client.embed.call_count == 3

    def test_exact_128_single_batch(self, mock_forge_rag, mock_voyage_client):
        texts = [f"text {i}" for i in range(128)]
        result = mock_forge_rag._embed(texts)
        assert len(result) == 128
        assert mock_voyage_client.embed.call_count == 1


# ===================================================================
# ingest_file
# ===================================================================


class TestIngestFile:
    @patch("pm_copilot.rag.process_file")
    def test_calls_process_file_and_embed(self, mock_pf, mock_forge_rag):
        mock_pf.return_value = [
            {
                "text": "chunk text",
                "context_header": "[Source: test.md > H1]",
                "header_path": ["H1"],
                "parent_text": "parent chunk text",
                "parent_id": "abc123",
                "leaf_index": 0,
            }
        ]
        count = mock_forge_rag.ingest_file(Path("/fake/test.md"), "A test file")
        assert count == 1
        mock_forge_rag.documents.add.assert_called_once()

    @patch("pm_copilot.rag.process_file")
    def test_zero_chunks_returns_zero(self, mock_pf, mock_forge_rag):
        mock_pf.return_value = []
        count = mock_forge_rag.ingest_file(Path("/fake/empty.md"), "Empty")
        assert count == 0
        mock_forge_rag.documents.add.assert_not_called()

    @patch("pm_copilot.rag.process_file")
    def test_id_format(self, mock_pf, mock_forge_rag):
        mock_pf.return_value = [
            {
                "text": f"chunk {i}", "context_header": "[Source: doc.md]",
                "header_path": ["H1"], "parent_text": "parent",
                "parent_id": "pid", "leaf_index": i,
            }
            for i in range(3)
        ]
        mock_forge_rag.ingest_file(Path("/fake/doc.md"), "Doc")
        add_call = mock_forge_rag.documents.add.call_args
        ids = add_call.kwargs.get("ids") or add_call[1].get("ids")
        assert ids == ["doc.md_chunk_0", "doc.md_chunk_1", "doc.md_chunk_2"]


# ===================================================================
# remove_file
# ===================================================================


class TestRemoveFile:
    def test_deletes_matching(self, mock_forge_rag):
        mock_forge_rag.documents.get.return_value = {
            "ids": ["file_chunk_0", "file_chunk_1"]
        }
        count = mock_forge_rag.remove_file("file.md")
        assert count == 2
        mock_forge_rag.documents.delete.assert_called_once_with(
            ids=["file_chunk_0", "file_chunk_1"]
        )

    def test_no_matches_returns_zero(self, mock_forge_rag):
        mock_forge_rag.documents.get.return_value = {"ids": []}
        count = mock_forge_rag.remove_file("nonexistent.md")
        assert count == 0
        mock_forge_rag.documents.delete.assert_not_called()


# ===================================================================
# index_turn
# ===================================================================


class TestIndexTurn:
    def test_upserts_to_conversations(self, mock_forge_rag):
        mock_forge_rag.index_turn(
            turn_number=5,
            user_message="How do we validate?",
            assistant_response="We should run a painted door test.",
            turn_summary="Discussed validation approach.",
            active_probe="Probe 1",
            active_mode="mode_1",
        )
        mock_forge_rag.conversations.upsert.assert_called_once()
        call_kwargs = mock_forge_rag.conversations.upsert.call_args.kwargs
        assert call_kwargs["ids"] == ["turn_5"]
        assert call_kwargs["metadatas"][0]["turn_number"] == 5
        assert call_kwargs["metadatas"][0]["active_probe"] == "Probe 1"


# ===================================================================
# retrieve_documents
# ===================================================================


class TestRetrieveDocuments:
    def test_disabled_returns_empty(self, mock_chroma_client, tmp_path):
        client, _, _ = mock_chroma_client
        rag = ForgeRAG(tmp_path, client, voyage_client=None)
        assert rag.retrieve_documents("query") == []

    def test_empty_collection_returns_empty(self, mock_forge_rag):
        mock_forge_rag.documents.count.return_value = 0
        assert mock_forge_rag.retrieve_documents("query") == []

    def test_parent_id_deduplication(self, mock_forge_rag):
        """Two results with same parent_id → 1 returned."""
        mock_forge_rag.documents.count.return_value = 10
        mock_forge_rag.documents.query.return_value = {
            "ids": [["chunk_0", "chunk_1"]],
            "metadatas": [[
                {"parent_id": "same", "parent_text": "parent", "context_header": "[Source: a]", "source_filename": "a.md"},
                {"parent_id": "same", "parent_text": "parent", "context_header": "[Source: a]", "source_filename": "a.md"},
            ]],
            "distances": [[0.1, 0.2]],
            "documents": [["doc1", "doc2"]],
        }
        results = mock_forge_rag.retrieve_documents("query")
        assert len(results) == 1
        assert results[0]["score"] == pytest.approx(0.9)

    def test_score_calculation(self, mock_forge_rag):
        mock_forge_rag.documents.count.return_value = 5
        mock_forge_rag.documents.query.return_value = {
            "ids": [["c1"]],
            "metadatas": [[
                {"parent_id": "p1", "parent_text": "text", "context_header": "[S]", "source_filename": "f.md"},
            ]],
            "distances": [[0.3]],
            "documents": [["d"]],
        }
        results = mock_forge_rag.retrieve_documents("query")
        assert results[0]["score"] == pytest.approx(0.7)

    def test_sorted_descending_by_score(self, mock_forge_rag):
        mock_forge_rag.documents.count.return_value = 10
        mock_forge_rag.documents.query.return_value = {
            "ids": [["c1", "c2", "c3"]],
            "metadatas": [[
                {"parent_id": "p1", "parent_text": "t1", "context_header": "[S1]", "source_filename": "a.md"},
                {"parent_id": "p2", "parent_text": "t2", "context_header": "[S2]", "source_filename": "b.md"},
                {"parent_id": "p3", "parent_text": "t3", "context_header": "[S3]", "source_filename": "c.md"},
            ]],
            "distances": [[0.5, 0.1, 0.3]],
            "documents": [["d1", "d2", "d3"]],
        }
        results = mock_forge_rag.retrieve_documents("query")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_filename_filter_uses_where(self, mock_forge_rag):
        mock_forge_rag.documents.count.return_value = 5
        mock_forge_rag.documents.query.return_value = {
            "ids": [[]], "metadatas": [[]], "distances": [[]], "documents": [[]],
        }
        mock_forge_rag.retrieve_documents("query", filename_filter="report.md")
        query_call = mock_forge_rag.documents.query.call_args
        assert query_call.kwargs.get("where") == {"source_filename": "report.md"}

    def test_n_results_cap(self, mock_forge_rag):
        mock_forge_rag.documents.count.return_value = 100
        mock_forge_rag.documents.query.return_value = {
            "ids": [["c1", "c2"]],
            "metadatas": [[
                {"parent_id": "p1", "parent_text": "t", "context_header": "[S]", "source_filename": "a.md"},
                {"parent_id": "p2", "parent_text": "t", "context_header": "[S]", "source_filename": "b.md"},
            ]],
            "distances": [[0.1, 0.2]],
            "documents": [["d1", "d2"]],
        }
        results = mock_forge_rag.retrieve_documents("query", n_results=1)
        assert len(results) <= 1


# ===================================================================
# retrieve_conversations
# ===================================================================


class TestRetrieveConversations:
    def test_disabled_returns_empty(self, mock_chroma_client, tmp_path):
        client, _, _ = mock_chroma_client
        rag = ForgeRAG(tmp_path, client, voyage_client=None)
        assert rag.retrieve_conversations("q", current_turn=10) == []

    def test_empty_returns_empty(self, mock_forge_rag):
        mock_forge_rag.conversations.count.return_value = 0
        assert mock_forge_rag.retrieve_conversations("q", current_turn=10) == []

    def test_turn_window_threshold(self, mock_forge_rag):
        """current_turn within window → returns empty (threshold ≤ 0)."""
        # ALWAYS_ON_TURN_WINDOW = 3, so current_turn=2 → threshold = 2-3 = -1 ≤ 0
        result = mock_forge_rag.retrieve_conversations("q", current_turn=2)
        assert result == []

    def test_sorted_by_turn_number_ascending(self, mock_forge_rag):
        mock_forge_rag.conversations.count.return_value = 10
        mock_forge_rag.conversations.query.return_value = {
            "ids": [["t5", "t2"]],
            "metadatas": [[
                {"turn_number": 5, "active_probe": "", "user_message": "u5", "assistant_response": "a5"},
                {"turn_number": 2, "active_probe": "", "user_message": "u2", "assistant_response": "a2"},
            ]],
            "distances": [[0.1, 0.3]],
            "documents": [["s5", "s2"]],
        }
        results = mock_forge_rag.retrieve_conversations("q", current_turn=10)
        assert results[0]["turn_number"] < results[1]["turn_number"]

    def test_probe_filter(self, mock_forge_rag):
        mock_forge_rag.conversations.count.return_value = 10
        mock_forge_rag.conversations.query.return_value = {
            "ids": [[]], "metadatas": [[]], "distances": [[]], "documents": [[]],
        }
        mock_forge_rag.retrieve_conversations("q", current_turn=10, probe_filter="Probe 1")
        call_kwargs = mock_forge_rag.conversations.query.call_args.kwargs
        where = call_kwargs["where"]
        assert "$and" in where


# ===================================================================
# Integration: _lookup_probe_and_patterns
# ===================================================================


class TestLookupProbeAndPatterns:
    def test_mismatched_key_returns_empty_no_crash(self, mock_forge_rag, caplog):
        """Probe name not in either dict → warning logged, empty string."""
        decision = {"next_probe": "Probe 99 Nonexistent"}
        with caplog.at_level(logging.WARNING, logger="forge.rag"):
            probe, patterns = mock_forge_rag._lookup_probe_and_patterns(decision)
        assert probe == ""
        assert any("Probe lookup miss" in r.message for r in caplog.records)

    def test_valid_mode1_probe(self, mock_forge_rag):
        from pm_copilot.mode1_knowledge import MODE1_PROBES
        decision = {"next_probe": "Probe 1"}
        probe, _ = mock_forge_rag._lookup_probe_and_patterns(decision)
        assert probe == MODE1_PROBES["Probe 1"]
        assert len(probe) > 0

    def test_valid_mode2_probe(self, mock_forge_rag):
        from pm_copilot.mode2_knowledge import MODE2_PROBES
        decision = {"next_probe": "Value Risk"}
        probe, _ = mock_forge_rag._lookup_probe_and_patterns(decision)
        assert probe == MODE2_PROBES["Value Risk"]
        assert len(probe) > 0

    def test_empty_next_probe_no_warning(self, mock_forge_rag, caplog):
        """Empty string → empty result, no warning."""
        decision = {"next_probe": ""}
        with caplog.at_level(logging.WARNING, logger="forge.rag"):
            probe, _ = mock_forge_rag._lookup_probe_and_patterns(decision)
        assert probe == ""
        assert not any("Probe lookup miss" in r.message for r in caplog.records)

    def test_missing_next_probe_key(self, mock_forge_rag, caplog):
        """No next_probe key at all → empty, no warning."""
        decision = {}
        with caplog.at_level(logging.WARNING, logger="forge.rag"):
            probe, _ = mock_forge_rag._lookup_probe_and_patterns(decision)
        assert probe == ""

    def test_triggered_patterns_valid_and_invalid(self, mock_forge_rag, caplog):
        """Mix of valid and invalid pattern names."""
        decision = {
            "next_probe": "",
            "triggered_patterns": [
                "Analytics-Execution Gap",  # valid Mode 1
                "Nonexistent Pattern",       # invalid
                "Build It and They Will Come",  # valid Mode 2
            ],
        }
        with caplog.at_level(logging.WARNING, logger="forge.rag"):
            _, pattern_content = mock_forge_rag._lookup_probe_and_patterns(decision)
        # Valid patterns should be in the result
        assert len(pattern_content) > 0
        # Invalid pattern should trigger a warning
        assert any("Pattern lookup miss" in r.message for r in caplog.records)

    def test_no_triggered_patterns(self, mock_forge_rag):
        decision = {"next_probe": "", "triggered_patterns": []}
        _, patterns = mock_forge_rag._lookup_probe_and_patterns(decision)
        assert patterns == ""


# ===================================================================
# Integration: assemble_context with mismatched probe
# ===================================================================


class TestAssembleContextIntegration:
    def test_mismatched_probe_key_still_succeeds(self, mock_forge_rag, caplog):
        """Phase A outputs probe name not in dict → probe_content empty, rest works."""
        mock_forge_rag.documents.count.return_value = 0
        mock_forge_rag.conversations.count.return_value = 0
        decision = {"next_probe": "Probe 99 Hallucinated", "triggered_patterns": []}
        with caplog.at_level(logging.WARNING, logger="forge.rag"):
            ctx = mock_forge_rag.assemble_context(
                user_message="test",
                phase_a_decision=decision,
                current_turn=1,
                project_state={"file_summaries": [], "org_context": ""},
            )
        assert ctx["probe_content"] == ""
        assert "context_block" in ctx
        assert "retrieved_documents" in ctx


# ===================================================================
# Format helpers
# ===================================================================


class TestFormatHelpers:
    def test_format_retrieved_documents_empty(self):
        assert ForgeRAG._format_retrieved_documents([]) == ""

    def test_format_retrieved_documents_populated(self):
        results = [
            {"context_header": "[Source: doc.md > H1]", "parent_text": "Parent content here"},
        ]
        formatted = ForgeRAG._format_retrieved_documents(results)
        assert "[Source: doc.md > H1]" in formatted
        assert "Parent content here" in formatted

    def test_format_retrieved_conversations_empty(self):
        assert ForgeRAG._format_retrieved_conversations([]) == ""

    def test_format_retrieved_conversations_with_probe(self):
        turns = [
            {
                "turn_number": 3,
                "active_probe": "Probe 1",
                "user_message": "What about users?",
                "assistant_response": "Good question.",
            },
        ]
        formatted = ForgeRAG._format_retrieved_conversations(turns)
        assert "Turn 3" in formatted
        assert "(Probe: Probe 1)" in formatted

    def test_format_retrieved_conversations_no_probe(self):
        turns = [
            {
                "turn_number": 1,
                "active_probe": "",
                "user_message": "Hello",
                "assistant_response": "Hi",
            },
        ]
        formatted = ForgeRAG._format_retrieved_conversations(turns)
        assert "Turn 1" in formatted
        assert "Probe" not in formatted


# ===================================================================
# assemble_context
# ===================================================================


class TestAssembleContext:
    def test_all_sections_returned(self, mock_forge_rag):
        mock_forge_rag.documents.count.return_value = 0
        mock_forge_rag.conversations.count.return_value = 0
        decision = {"next_probe": "Probe 1", "triggered_patterns": []}
        ctx = mock_forge_rag.assemble_context(
            user_message="test",
            phase_a_decision=decision,
            current_turn=1,
            project_state={"file_summaries": [], "org_context": "Acme Corp"},
        )
        assert "context_block" in ctx
        assert "probe_content" in ctx
        assert "pattern_content" in ctx
        assert "retrieved_documents" in ctx
        assert "retrieved_conversations" in ctx
        assert len(ctx["probe_content"]) > 0  # Probe 1 is valid

    def test_probe_appended_to_retrieval_query(self, mock_forge_rag):
        mock_forge_rag.documents.count.return_value = 5
        mock_forge_rag.documents.query.return_value = {
            "ids": [[]], "metadatas": [[]], "distances": [[]], "documents": [[]],
        }
        mock_forge_rag.conversations.count.return_value = 0
        decision = {"next_probe": "Probe 1", "triggered_patterns": []}
        mock_forge_rag.assemble_context(
            user_message="user msg",
            phase_a_decision=decision,
            current_turn=1,
            project_state={"file_summaries": [], "org_context": ""},
        )
        # The query should include both user message and probe name
        embed_call = mock_forge_rag.voyage.embed.call_args_list[-1]
        query_text = embed_call[0][0][0]
        assert "user msg" in query_text
        assert "Probe 1" in query_text


# ===================================================================
# assemble_context_minimal
# ===================================================================


class TestAssembleContextMinimal:
    def test_skips_retrieval_calls(self, mock_forge_rag, mock_voyage_client):
        decision = {"next_probe": "Probe 1", "triggered_patterns": []}
        ctx = mock_forge_rag.assemble_context_minimal(
            phase_a_decision=decision,
            current_turn=1,
            project_state={"file_summaries": [], "org_context": ""},
        )
        assert ctx["retrieved_documents"] == ""
        assert ctx["retrieved_conversations"] == ""
        # Voyage should NOT be called for retrieval (no embed calls for queries)
        mock_voyage_client.embed.assert_not_called()
        # But probe_content should still resolve
        assert len(ctx["probe_content"]) > 0

    def test_returns_same_shape_as_full(self, mock_forge_rag):
        decision = {"next_probe": "", "triggered_patterns": []}
        ctx = mock_forge_rag.assemble_context_minimal(
            phase_a_decision=decision,
            current_turn=1,
            project_state={"file_summaries": [], "org_context": ""},
        )
        expected_keys = {"context_block", "probe_content", "pattern_content",
                         "retrieved_documents", "retrieved_conversations"}
        assert set(ctx.keys()) == expected_keys


# ===================================================================
# format_context_block (module-level helper)
# ===================================================================


class TestFormatContextBlock:
    def test_empty_state(self):
        result = format_context_block({"file_summaries": [], "org_context": ""})
        assert "No project context" in result

    def test_with_org_context(self):
        result = format_context_block({"file_summaries": [], "org_context": "Acme Corp"})
        assert "Acme Corp" in result

    def test_with_file_summaries(self):
        result = format_context_block({
            "file_summaries": [{"filename": "report.md", "summary": "Q3 analysis"}],
            "org_context": "",
        })
        assert "report.md" in result
        assert "Q3 analysis" in result
