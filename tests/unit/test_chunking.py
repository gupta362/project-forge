"""Unit tests for pm_copilot.chunking — pure functions, no external deps."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pm_copilot.chunking import (
    FileConversionError,
    _estimate_tokens,
    _group_segments,
    _split_large_chunk,
    convert_to_markdown,
    create_parent_child_pairs,
    enforce_chunk_sizes,
    process_file,
    split_markdown_by_headers,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ===================================================================
# _estimate_tokens
# ===================================================================


class TestEstimateTokens:
    def test_basic(self):
        assert _estimate_tokens("hello world") == int(2 * 1.3)

    def test_empty(self):
        assert _estimate_tokens("") == 0

    def test_long_text(self):
        text = " ".join(["word"] * 100)
        assert _estimate_tokens(text) == int(100 * 1.3)

    def test_single_word(self):
        assert _estimate_tokens("hello") == int(1 * 1.3)


# ===================================================================
# convert_to_markdown
# ===================================================================


class TestConvertToMarkdown:
    def test_md_passthrough(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello\nWorld", encoding="utf-8")
        result = convert_to_markdown(md_file)
        assert result == "# Hello\nWorld"

    def test_docx_via_markitdown(self, tmp_path):
        docx_file = tmp_path / "test.docx"
        docx_file.write_bytes(b"fake docx content")
        mock_mid = MagicMock()
        mock_mid.MarkItDown.return_value.convert.return_value = SimpleNamespace(
            text_content="# Converted\nContent"
        )
        with patch.dict("sys.modules", {"markitdown": mock_mid}):
            result = convert_to_markdown(docx_file)
        assert result == "# Converted\nContent"

    def test_unsupported_extension(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        with pytest.raises(FileConversionError, match="Unsupported file type: .txt"):
            convert_to_markdown(txt_file)

    def test_docx_conversion_failure(self, tmp_path):
        docx_file = tmp_path / "bad.docx"
        docx_file.write_bytes(b"corrupt")
        mock_mid = MagicMock()
        mock_mid.MarkItDown.return_value.convert.side_effect = RuntimeError("parse error")
        with patch.dict("sys.modules", {"markitdown": mock_mid}):
            with pytest.raises(FileConversionError, match="Failed to convert 'bad.docx'"):
                convert_to_markdown(docx_file)


# ===================================================================
# split_markdown_by_headers
# ===================================================================


class TestSplitMarkdownByHeaders:
    def test_no_headers_single_chunk(self):
        text = "Just some plain text\nwith no headers at all."
        chunks = split_markdown_by_headers(text, "test.md")
        assert len(chunks) == 1
        assert chunks[0]["header_path"] == ["Introduction"]
        assert chunks[0]["level"] == 0
        assert chunks[0]["context_header"] == "[Source: test.md]"

    def test_single_h1(self):
        text = "# Title\nSome content here."
        chunks = split_markdown_by_headers(text, "doc.md")
        assert len(chunks) == 1
        assert chunks[0]["header_path"] == ["Title"]
        assert chunks[0]["level"] == 1
        assert "Title" in chunks[0]["text"]

    def test_nested_h1_h2_h3_ancestry(self):
        text = "# H1\nIntro\n## H2\nBody\n### H3\nDetail"
        chunks = split_markdown_by_headers(text, "nested.md")
        assert len(chunks) == 3
        assert chunks[0]["header_path"] == ["H1"]
        assert chunks[1]["header_path"] == ["H1", "H2"]
        assert chunks[2]["header_path"] == ["H1", "H2", "H3"]

    def test_pre_header_introduction_chunk(self):
        text = "Some preamble text.\n\n# Actual Header\nContent."
        chunks = split_markdown_by_headers(text, "pre.md")
        assert len(chunks) == 2
        assert chunks[0]["header_path"] == ["Introduction"]
        assert chunks[0]["level"] == 0
        assert chunks[0]["context_header"] == "[Source: pre.md > Introduction]"

    def test_header_stack_pops_on_same_level(self):
        text = "# H1\nA\n## H2a\nB\n## H2b\nC"
        chunks = split_markdown_by_headers(text, "pop.md")
        assert chunks[1]["header_path"] == ["H1", "H2a"]
        assert chunks[2]["header_path"] == ["H1", "H2b"]

    def test_context_header_format(self):
        text = "# Findings\n## Customer Segments\nData here."
        chunks = split_markdown_by_headers(text, "report.md")
        assert chunks[1]["context_header"] == "[Source: report.md > Findings > Customer Segments]"

    def test_h3_under_different_h2s(self):
        text = "# A\n## B\n### C\ntext\n## D\n### E\ntext"
        chunks = split_markdown_by_headers(text, "deep.md")
        # C's path: A > B > C
        assert chunks[2]["header_path"] == ["A", "B", "C"]
        # E's path: A > D > E (B was popped)
        assert chunks[4]["header_path"] == ["A", "D", "E"]

    def test_sample_fixture_file(self):
        text = (FIXTURES_DIR / "sample_document.md").read_text()
        chunks = split_markdown_by_headers(text, "sample_document.md")
        assert len(chunks) > 5
        # All chunks should have non-empty text
        assert all(c["text"].strip() for c in chunks)


# ===================================================================
# enforce_chunk_sizes
# ===================================================================


class TestEnforceChunkSizes:
    def _make_chunk(self, text, level=1, header_path=None):
        return {
            "text": text,
            "level": level,
            "header_path": header_path or ["Test"],
            "context_header": "[Source: test.md > Test]",
        }

    def test_large_split_at_paragraphs(self):
        # Create text large enough to exceed max_tokens
        para1 = " ".join(["word"] * 200)
        para2 = " ".join(["other"] * 200)
        text = para1 + "\n\n" + para2
        chunk = self._make_chunk(text)
        result = enforce_chunk_sizes([chunk], max_tokens=300)
        assert len(result) >= 2

    def test_large_split_at_sentences(self):
        # One giant paragraph that needs sentence splitting
        sentences = ". ".join(["This is a sentence with many words"] * 50)
        chunk = self._make_chunk(sentences)
        result = enforce_chunk_sizes([chunk], max_tokens=100)
        assert len(result) > 1

    def test_small_merged_at_same_level(self):
        c1 = self._make_chunk("tiny", level=1)
        c2 = self._make_chunk("also tiny", level=1)
        result = enforce_chunk_sizes([c1, c2], min_tokens=50)
        assert len(result) == 1
        assert "tiny" in result[0]["text"]
        assert "also tiny" in result[0]["text"]

    def test_small_not_merged_at_different_levels(self):
        c1 = self._make_chunk("tiny", level=1)
        c2 = self._make_chunk("also tiny", level=2)
        result = enforce_chunk_sizes([c1, c2], min_tokens=50)
        assert len(result) == 2

    def test_normal_passthrough(self):
        text = " ".join(["word"] * 50)
        chunk = self._make_chunk(text)
        result = enforce_chunk_sizes([chunk], min_tokens=10, max_tokens=200)
        assert len(result) == 1
        assert result[0]["text"] == text

    def test_empty_input(self):
        result = enforce_chunk_sizes([])
        assert result == []

    def test_split_preserves_metadata(self):
        text = " ".join(["word"] * 400) + "\n\n" + " ".join(["word"] * 400)
        chunk = self._make_chunk(text, level=2, header_path=["A", "B"])
        result = enforce_chunk_sizes([chunk], max_tokens=300)
        for r in result:
            assert r["level"] == 2
            assert r["header_path"] == ["A", "B"]


# ===================================================================
# create_parent_child_pairs
# ===================================================================


class TestCreateParentChildPairs:
    def _make_chunk(self, text, header_path, level=1):
        return {
            "text": text,
            "header_path": header_path,
            "level": level,
            "context_header": f"[Source: test.md > {' > '.join(header_path)}]",
        }

    def test_empty_returns_empty(self):
        assert create_parent_child_pairs([]) == []

    def test_single_chunk(self):
        chunk = self._make_chunk("content", ["H1"])
        result = create_parent_child_pairs([chunk])
        assert len(result) == 1
        assert "parent_text" in result[0]
        assert "parent_id" in result[0]
        assert result[0]["leaf_index"] == 0

    def test_group_by_top_header(self):
        c1 = self._make_chunk("A content", ["H1"])
        c2 = self._make_chunk("B content", ["H1", "H1a"])
        c3 = self._make_chunk("C content", ["H2"])
        result = create_parent_child_pairs([c1, c2, c3])
        # c1 and c2 share top header "H1", c3 is separate
        assert result[0]["parent_id"] == result[1]["parent_id"]
        assert result[2]["parent_id"] != result[0]["parent_id"]

    def test_large_parent_splits(self):
        # Create chunks with distinct text whose combined text exceeds parent_max_tokens
        chunks = [
            self._make_chunk(" ".join([f"word{i}"] * 800), ["Big"])
            for i in range(4)
        ]
        result = create_parent_child_pairs(chunks, parent_max_tokens=2000)
        parent_ids = set(r["parent_id"] for r in result)
        assert len(parent_ids) > 1

    def test_deterministic_parent_id(self):
        c = self._make_chunk("deterministic text", ["H1"])
        result = create_parent_child_pairs([c])
        expected = hashlib.md5("deterministic text".encode()).hexdigest()[:12]
        assert result[0]["parent_id"] == expected

    def test_leaf_index_ordering(self):
        c1 = self._make_chunk("first", ["H1"])
        c2 = self._make_chunk("second", ["H1"])
        c3 = self._make_chunk("third", ["H1"])
        result = create_parent_child_pairs([c1, c2, c3])
        assert [r["leaf_index"] for r in result] == [0, 1, 2]


# ===================================================================
# process_file (full pipeline)
# ===================================================================


class TestProcessFile:
    def test_full_pipeline_md(self):
        result = process_file(FIXTURES_DIR / "sample_document.md")
        assert len(result) > 0
        for chunk in result:
            assert "parent_text" in chunk
            assert "parent_id" in chunk
            assert "text" in chunk
            assert chunk["text"].strip()

    def test_full_pipeline_docx_mocked(self, tmp_path):
        docx_file = tmp_path / "test.docx"
        docx_file.write_bytes(b"fake")
        mock_mid = MagicMock()
        mock_mid.MarkItDown.return_value.convert.return_value = SimpleNamespace(
            text_content="# Section\nSome content here with enough words to be meaningful.\n\n## Sub\nMore details."
        )
        with patch.dict("sys.modules", {"markitdown": mock_mid}):
            result = process_file(docx_file)
        assert len(result) > 0

    def test_empty_file(self, tmp_path):
        empty_md = tmp_path / "empty.md"
        empty_md.write_text("")
        result = process_file(empty_md)
        # Empty text → single empty chunk or no chunks
        # The function should handle this gracefully
        assert isinstance(result, list)

    def test_conversion_error_propagates(self, tmp_path):
        bad_file = tmp_path / "bad.xyz"
        bad_file.write_text("nope")
        with pytest.raises(FileConversionError):
            process_file(bad_file)

    def test_md_with_no_headers(self, tmp_path):
        md = tmp_path / "flat.md"
        md.write_text("Just a paragraph of text.\n\nAnother paragraph.")
        result = process_file(md)
        assert len(result) >= 1
        assert result[0]["header_path"] == ["Introduction"]
