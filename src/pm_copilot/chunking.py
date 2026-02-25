"""Document chunking — DOCX/MD → Markdown conversion and hierarchical chunking."""

import hashlib
import logging
import re
from pathlib import Path

logger = logging.getLogger("forge.chunking")


class FileConversionError(Exception):
    """Raised when MarkItDown fails to parse a file.

    Caller should catch this, log it, and show st.error to the user.
    The original file is preserved on disk regardless.
    """


def _estimate_tokens(text: str) -> int:
    """Approximate token count. Good enough for chunking decisions."""
    return int(len(text.split()) * 1.3)


def convert_to_markdown(file_path: Path) -> str:
    """Convert DOCX or MD file to clean Markdown.

    Args:
        file_path: Path to .docx or .md file

    Returns:
        Markdown string

    Raises:
        FileConversionError: If MarkItDown fails to parse the file.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".md":
        logger.info("Reading markdown file: %s", file_path.name)
        return file_path.read_text(encoding="utf-8")

    if suffix == ".docx":
        logger.info("Converting DOCX to markdown: %s", file_path.name)
        try:
            from markitdown import MarkItDown

            converter = MarkItDown()
            result = converter.convert(str(file_path))
            return result.text_content
        except Exception as exc:
            logger.error("MarkItDown failed on %s: %s", file_path.name, exc)
            raise FileConversionError(
                f"Failed to convert '{file_path.name}': {exc}"
            ) from exc

    raise FileConversionError(f"Unsupported file type: {suffix}")


def split_markdown_by_headers(
    markdown_text: str,
    source_filename: str,
) -> list[dict]:
    """Split Markdown into hierarchical chunks based on headers.

    Returns list of chunks, each with:
        text:           Chunk content (including the header line itself)
        header_path:    List of ancestor headers, e.g. ["Findings", "Customer Segments"]
        level:          Header depth (1=H1, 2=H2, 3=H3, 0=pre-header content)
        context_header: "[Source: filename > Findings > Customer Segments]"
    """
    header_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    # Find all header positions
    matches = list(header_pattern.finditer(markdown_text))

    if not matches:
        # No headers at all — return the whole text as one chunk
        return [
            {
                "text": markdown_text.strip(),
                "header_path": ["Introduction"],
                "level": 0,
                "context_header": f"[Source: {source_filename}]",
            }
        ]

    chunks = []

    # Content before the first header
    pre_header = markdown_text[: matches[0].start()].strip()
    if pre_header:
        chunks.append(
            {
                "text": pre_header,
                "header_path": ["Introduction"],
                "level": 0,
                "context_header": f"[Source: {source_filename} > Introduction]",
            }
        )

    # Track the current header stack for building header_path
    # Stack entries: (level, title)
    header_stack: list[tuple[int, str]] = []

    for i, match in enumerate(matches):
        hashes = match.group(1)
        title = match.group(2).strip()
        level = len(hashes)

        # Determine text extent: from this header to the next header (or end)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        text = markdown_text[start:end].strip()

        # Update header stack: pop anything at same level or deeper
        while header_stack and header_stack[-1][0] >= level:
            header_stack.pop()
        header_stack.append((level, title))

        header_path = [t for _, t in header_stack]
        path_str = " > ".join(header_path)
        context_header = f"[Source: {source_filename} > {path_str}]"

        chunks.append(
            {
                "text": text,
                "header_path": header_path,
                "level": level,
                "context_header": context_header,
            }
        )

    logger.debug(
        "Split %s into %d header-based chunks", source_filename, len(chunks)
    )
    return chunks


def enforce_chunk_sizes(
    chunks: list[dict],
    min_tokens: int = 100,
    max_tokens: int = 500,
) -> list[dict]:
    """Enforce token size limits on chunks.

    - Chunks > max_tokens: split at paragraph boundaries, then sentence boundaries
    - Chunks < min_tokens: merge with the next chunk at the same level
    - Never split mid-sentence
    """
    result: list[dict] = []

    for chunk in chunks:
        tokens = _estimate_tokens(chunk["text"])
        if tokens > max_tokens:
            result.extend(_split_large_chunk(chunk, max_tokens))
        else:
            result.append(chunk)

    # Second pass: merge undersized chunks with the next sibling
    merged: list[dict] = []
    i = 0
    while i < len(result):
        current = result[i]
        tokens = _estimate_tokens(current["text"])

        # Merge with next chunk if undersized and next chunk exists at same level
        if tokens < min_tokens and i + 1 < len(result):
            next_chunk = result[i + 1]
            if next_chunk["level"] == current["level"]:
                combined_text = current["text"] + "\n\n" + next_chunk["text"]
                merged_chunk = {
                    "text": combined_text,
                    "header_path": current["header_path"],
                    "level": current["level"],
                    "context_header": current["context_header"],
                }
                merged.append(merged_chunk)
                i += 2  # skip the next chunk since we merged it
                continue

        merged.append(current)
        i += 1

    return merged


def _split_large_chunk(chunk: dict, max_tokens: int) -> list[dict]:
    """Split an oversized chunk at paragraph boundaries, then sentence boundaries."""
    text = chunk["text"]

    # Try splitting at double-newline (paragraph) boundaries
    paragraphs = re.split(r"\n\n+", text)
    sub_chunks = _group_segments(paragraphs, max_tokens, separator="\n\n")

    # If any sub-chunk is still too large, split at sentence boundaries
    final = []
    for sc_text in sub_chunks:
        if _estimate_tokens(sc_text) > max_tokens:
            sentences = re.split(r"(?<=\. )", sc_text)
            sentence_groups = _group_segments(sentences, max_tokens, separator="")
            final.extend(sentence_groups)
        else:
            final.append(sc_text)

    # Build chunk dicts for each sub-chunk
    result = []
    for idx, sc_text in enumerate(final):
        suffix = f" (part {idx + 1})" if len(final) > 1 else ""
        result.append(
            {
                "text": sc_text.strip(),
                "header_path": chunk["header_path"],
                "level": chunk["level"],
                "context_header": chunk["context_header"] + suffix,
            }
        )
    return result


def _group_segments(
    segments: list[str], max_tokens: int, separator: str
) -> list[str]:
    """Group text segments into chunks that don't exceed max_tokens."""
    groups: list[str] = []
    current_parts: list[str] = []

    for seg in segments:
        candidate = separator.join(current_parts + [seg]) if current_parts else seg
        if _estimate_tokens(candidate) > max_tokens and current_parts:
            groups.append(separator.join(current_parts))
            current_parts = [seg]
        else:
            current_parts.append(seg)

    if current_parts:
        groups.append(separator.join(current_parts))

    return groups


def create_parent_child_pairs(
    chunks: list[dict],
    parent_max_tokens: int = 2000,
) -> list[dict]:
    """Group leaf chunks into parent chunks.

    Consecutive chunks sharing the same top-level header are grouped into
    a single parent. Each leaf chunk is augmented with:
        parent_text:  Full parent section text
        parent_id:    Hash of parent text (for deduplication in retrieval)
        leaf_index:   Position of this leaf within its parent
    """
    if not chunks:
        return []

    # Group chunks by their top-level header (first element of header_path)
    groups: list[list[dict]] = []
    current_group: list[dict] = [chunks[0]]
    current_top = chunks[0]["header_path"][0] if chunks[0]["header_path"] else ""

    for chunk in chunks[1:]:
        top = chunk["header_path"][0] if chunk["header_path"] else ""
        if top == current_top:
            current_group.append(chunk)
        else:
            groups.append(current_group)
            current_group = [chunk]
            current_top = top
    groups.append(current_group)

    # Build parent-child pairs
    result = []
    for group in groups:
        parent_text = "\n\n".join(c["text"] for c in group)
        parent_tokens = _estimate_tokens(parent_text)

        if parent_tokens <= parent_max_tokens:
            # Single parent for the whole group
            parent_id = hashlib.md5(parent_text.encode()).hexdigest()[:12]
            for idx, chunk in enumerate(group):
                result.append(
                    {
                        **chunk,
                        "parent_text": parent_text,
                        "parent_id": parent_id,
                        "leaf_index": idx,
                    }
                )
        else:
            # Parent too large — split into sub-parents at natural boundaries
            sub_parents = _split_parent_group(group, parent_max_tokens)
            for sub_group in sub_parents:
                sub_text = "\n\n".join(c["text"] for c in sub_group)
                sub_id = hashlib.md5(sub_text.encode()).hexdigest()[:12]
                for idx, chunk in enumerate(sub_group):
                    result.append(
                        {
                            **chunk,
                            "parent_text": sub_text,
                            "parent_id": sub_id,
                            "leaf_index": idx,
                        }
                    )

    return result


def _split_parent_group(
    group: list[dict], max_tokens: int
) -> list[list[dict]]:
    """Split a group of chunks into sub-groups that fit within max_tokens."""
    sub_groups: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = 0

    for chunk in group:
        chunk_tokens = _estimate_tokens(chunk["text"])
        if current and current_tokens + chunk_tokens > max_tokens:
            sub_groups.append(current)
            current = [chunk]
            current_tokens = chunk_tokens
        else:
            current.append(chunk)
            current_tokens += chunk_tokens

    if current:
        sub_groups.append(current)

    return sub_groups


def process_file(file_path: Path) -> list[dict]:
    """Full pipeline: file → markdown → split → size enforce → parent-child pairs.

    Returns list of leaf chunks ready for embedding and storage.
    """
    logger.info("Processing file: %s", file_path.name)

    # Step 1: Convert to markdown
    markdown_text = convert_to_markdown(file_path)

    # Step 2: Split by headers
    chunks = split_markdown_by_headers(markdown_text, file_path.name)

    # Step 3: Enforce size limits
    chunks = enforce_chunk_sizes(chunks)

    # Step 4: Create parent-child pairs
    chunks = create_parent_child_pairs(chunks)

    # Log summary
    if chunks:
        avg_tokens = sum(_estimate_tokens(c["text"]) for c in chunks) // len(chunks)
        logger.info(
            "Chunked %s: %d leaf chunks, avg ~%d tokens each",
            file_path.name,
            len(chunks),
            avg_tokens,
        )
    else:
        logger.warning("No chunks produced from %s", file_path.name)

    return chunks
