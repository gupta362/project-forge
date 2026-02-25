"""RAG module — embedding, vector storage, retrieval for Forge projects."""

import json
import logging
from pathlib import Path

import chromadb
import voyageai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from voyageai.error import RateLimitError, ServerError

from . import config
from .chunking import process_file
from .mode1_knowledge import MODE1_PROBES, MODE1_PATTERNS
from .mode2_knowledge import MODE2_PROBES, MODE2_PATTERNS

logger = logging.getLogger("forge.rag")


# ---------------------------------------------------------------------------
# Module-level factory functions — wrapped with @st.cache_resource in app.py
# ---------------------------------------------------------------------------

def _create_chroma_client(vectordb_path: str) -> chromadb.PersistentClient:
    """Create ChromaDB client. Called via @st.cache_resource in app.py."""
    return chromadb.PersistentClient(path=vectordb_path)


def _create_voyage_client(api_key: str) -> voyageai.Client:
    """Create Voyage AI client. Called via @st.cache_resource in app.py."""
    return voyageai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_context_block(project_state: dict) -> str:
    """Format project state into a text block for prompt injection."""
    parts = []
    org_ctx = project_state.get("org_context", "")
    if org_ctx:
        parts.append(f"## Organization Context\n{org_ctx}")
    file_summaries = project_state.get("file_summaries", [])
    if file_summaries:
        parts.append("## Available Documents")
        for f in file_summaries:
            parts.append(f"- **{f['filename']}**: {f['summary']}")
    return "\n\n".join(parts) if parts else "No project context available yet."


# ---------------------------------------------------------------------------
# ForgeRAG
# ---------------------------------------------------------------------------

class ForgeRAG:
    """Manages vector storage and retrieval for a Forge project."""

    def __init__(
        self,
        project_dir: Path,
        chroma_client: chromadb.PersistentClient,
        voyage_client: voyageai.Client | None,
    ):
        """Initialize RAG for a project.

        IMPORTANT: Do NOT create ChromaDB or Voyage clients here.
        Clients must be passed in as pre-initialized singletons
        (cached via @st.cache_resource in app.py) to avoid
        Streamlit thread-lock issues with SQLite.
        """
        self.project_dir = project_dir
        self.client = chroma_client
        self.voyage = voyage_client
        self.enabled = voyage_client is not None

        # Get or create collections
        self.documents = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"},
        )
        self.conversations = self.client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"},
        )

        if not self.enabled:
            logger.warning("Voyage client not provided — RAG retrieval disabled")
        else:
            logger.info("ForgeRAG initialized for %s", project_dir)

    # -------------------------------------------------------------------
    # Embedding
    # -------------------------------------------------------------------

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((RateLimitError, ServerError)),
    )
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a single batch with retry/backoff for rate limits."""
        result = self.voyage.embed(
            texts,
            model=config.EMBEDDING_MODEL,
            output_dimension=config.EMBEDDING_DIMENSIONS,
        )
        return result.embeddings

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with batching and rate-limit handling.

        Splits into batches of 128 (Voyage's max) and retries each batch
        with exponential backoff on 429/5xx errors.
        """
        BATCH_SIZE = 128
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
        return all_embeddings

    # -------------------------------------------------------------------
    # Document ingestion
    # -------------------------------------------------------------------

    def ingest_file(self, file_path: Path, file_summary: str) -> int:
        """Ingest a file into the documents collection.

        Returns number of chunks stored.
        """
        chunks = process_file(file_path)
        if not chunks:
            logger.warning("No chunks produced from %s", file_path.name)
            return 0

        source_filename = file_path.name

        # Prepare texts for embedding (context header + chunk text)
        texts = [f"{c['context_header']}\n{c['text']}" for c in chunks]

        # Embed
        embeddings = self._embed(texts)

        # Build ChromaDB add arguments
        ids = [f"{source_filename}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source_filename": source_filename,
                "header_path": json.dumps(c["header_path"]),
                "context_header": c["context_header"],
                "parent_text": c["parent_text"],
                "parent_id": c["parent_id"],
                "leaf_index": c["leaf_index"],
            }
            for c in chunks
        ]

        self.documents.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        logger.info("Ingested %s: %d chunks", source_filename, len(chunks))
        return len(chunks)

    def remove_file(self, filename: str) -> int:
        """Remove all chunks for a given filename from documents collection."""
        # Query to find matching IDs
        results = self.documents.get(
            where={"source_filename": filename},
        )
        ids_to_delete = results["ids"]
        if ids_to_delete:
            self.documents.delete(ids=ids_to_delete)
        count = len(ids_to_delete)
        logger.info("Removed %s: %d chunks deleted", filename, count)
        return count

    # -------------------------------------------------------------------
    # Conversation indexing
    # -------------------------------------------------------------------

    def index_turn(
        self,
        turn_number: int,
        user_message: str,
        assistant_response: str,
        turn_summary: str,
        active_probe: str,
        active_mode: str,
    ) -> None:
        """Index a completed conversation turn."""
        embedding = self._embed([turn_summary])[0]

        self.conversations.upsert(
            ids=[f"turn_{turn_number}"],
            embeddings=[embedding],
            documents=[turn_summary],
            metadatas=[
                {
                    "turn_number": turn_number,
                    "active_probe": active_probe or "",
                    "active_mode": active_mode or "",
                    "user_message": user_message,
                    "assistant_response": assistant_response,
                }
            ],
        )

        logger.info("Indexed turn %d", turn_number)

    # -------------------------------------------------------------------
    # Retrieval
    # -------------------------------------------------------------------

    def retrieve_documents(
        self,
        query: str,
        n_results: int | None = None,
        filename_filter: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant document chunks, deduplicated by parent.

        Returns list of dicts with: parent_text, context_header,
        source_filename, score.
        """
        if not self.enabled:
            return []

        if self.documents.count() == 0:
            return []

        n = n_results or config.MAX_DOCUMENT_RESULTS
        query_embedding = self._embed([query])[0]

        # Build query kwargs
        query_kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(n * 2, self.documents.count()),  # over-fetch for dedup
        }
        if filename_filter:
            query_kwargs["where"] = {"source_filename": filename_filter}

        results = self.documents.query(**query_kwargs)

        # Deduplicate by parent_id — keep the best-scoring leaf per parent
        seen_parents: set[str] = set()
        deduped: list[dict] = []

        if results["ids"] and results["ids"][0]:
            metadatas = results["metadatas"][0]
            distances = results["distances"][0]

            for meta, distance in zip(metadatas, distances):
                parent_id = meta["parent_id"]
                if parent_id in seen_parents:
                    continue
                seen_parents.add(parent_id)
                # ChromaDB returns distances (lower = closer for cosine)
                score = 1.0 - distance
                deduped.append(
                    {
                        "parent_text": meta["parent_text"],
                        "context_header": meta["context_header"],
                        "source_filename": meta["source_filename"],
                        "score": score,
                    }
                )
                if len(deduped) >= n:
                    break

        # Sort by score descending
        deduped.sort(key=lambda x: x["score"], reverse=True)
        return deduped

    def retrieve_conversations(
        self,
        query: str,
        current_turn: int,
        n_results: int | None = None,
        probe_filter: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant older conversation turns.

        Returns list of dicts sorted by turn_number ascending (chronological).
        """
        if not self.enabled:
            return []

        if self.conversations.count() == 0:
            return []

        n = n_results or config.MAX_CONVERSATION_RESULTS
        threshold = current_turn - config.ALWAYS_ON_TURN_WINDOW

        if threshold <= 0:
            return []  # Not enough history to retrieve from

        query_embedding = self._embed([query])[0]

        # Build where filter
        if probe_filter:
            where_filter = {
                "$and": [
                    {"turn_number": {"$lt": threshold}},
                    {"active_probe": probe_filter},
                ]
            }
        else:
            where_filter = {"turn_number": {"$lt": threshold}}

        # Clamp n_results to available count
        available = self.conversations.count()

        results = self.conversations.query(
            query_embeddings=[query_embedding],
            n_results=min(n, available),
            where=where_filter,
        )

        turns: list[dict] = []
        if results["ids"] and results["ids"][0]:
            metadatas = results["metadatas"][0]
            distances = results["distances"][0]

            for meta, distance in zip(metadatas, distances):
                score = 1.0 - distance
                turns.append(
                    {
                        "turn_number": meta["turn_number"],
                        "active_probe": meta["active_probe"],
                        "user_message": meta["user_message"],
                        "assistant_response": meta["assistant_response"],
                        "score": score,
                    }
                )

        # Sort chronologically
        turns.sort(key=lambda x: x["turn_number"])
        return turns

    # -------------------------------------------------------------------
    # Context assembly
    # -------------------------------------------------------------------

    def _lookup_probe_and_patterns(
        self, phase_a_decision: dict
    ) -> tuple[str, str]:
        """Look up probe definition and triggered patterns from knowledge base dicts.

        Returns (probe_content, pattern_content) — both plain strings.
        """
        probe_name = phase_a_decision.get("next_probe", "")
        probe_content = (
            MODE1_PROBES.get(probe_name, "")
            or MODE2_PROBES.get(probe_name, "")
        )

        triggered = phase_a_decision.get("triggered_patterns", [])
        pattern_parts = []
        for p in triggered:
            content = MODE1_PATTERNS.get(p, "") or MODE2_PATTERNS.get(p, "")
            if content:
                pattern_parts.append(content)
        pattern_content = "\n\n".join(pattern_parts)

        return probe_content, pattern_content

    @staticmethod
    def _format_retrieved_documents(results: list[dict]) -> str:
        """Format document retrieval results for prompt injection."""
        if not results:
            return ""
        parts = []
        for r in results:
            parts.append(f"{r['context_header']}\n{r['parent_text']}")
        return "\n\n".join(parts)

    @staticmethod
    def _format_retrieved_conversations(turns: list[dict]) -> str:
        """Format conversation retrieval results for prompt injection."""
        if not turns:
            return ""
        parts = []
        for t in turns:
            probe_label = f" (Probe: {t['active_probe']})" if t["active_probe"] else ""
            parts.append(
                f"Turn {t['turn_number']}{probe_label}:\n"
                f"User: {t['user_message']}\n"
                f"Assistant: {t['assistant_response']}"
            )
        return "\n\n".join(parts)

    def assemble_context(
        self,
        user_message: str,
        phase_a_decision: dict,
        current_turn: int,
        project_state: dict,
    ) -> dict:
        """Assemble the full context for Phase B.

        Performs dictionary lookups for probe/pattern content and
        semantic retrieval from ChromaDB for documents and conversations.

        Returns dict with assembled context sections ready for prompt injection.
        """
        # 1. Format context block (deterministic, no API calls)
        context_block = format_context_block(project_state)

        # 2. Look up active probe and triggered patterns
        probe_content, pattern_content = self._lookup_probe_and_patterns(
            phase_a_decision
        )

        # 3. Retrieve document chunks from ChromaDB
        query = user_message
        if probe_content:
            # Append probe context to improve retrieval relevance
            query = f"{user_message} {phase_a_decision.get('next_probe', '')}"
        doc_results = self.retrieve_documents(query)
        retrieved_documents = self._format_retrieved_documents(doc_results)

        # 4. Retrieve conversation turns from ChromaDB
        conv_results = self.retrieve_conversations(
            user_message, current_turn
        )
        retrieved_conversations = self._format_retrieved_conversations(
            conv_results
        )

        return {
            "context_block": context_block,
            "probe_content": probe_content,
            "pattern_content": pattern_content,
            "retrieved_documents": retrieved_documents,
            "retrieved_conversations": retrieved_conversations,
        }

    def assemble_context_minimal(
        self,
        phase_a_decision: dict,
        current_turn: int,
        project_state: dict,
    ) -> dict:
        """Assemble minimal context for filler/bypass turns.

        Called when Phase A sets requires_retrieval=false. Skips all
        ChromaDB queries to save ~3 seconds latency and ~7,000 tokens.

        Returns same dict shape as assemble_context() but with empty
        strings for retrieved_documents and retrieved_conversations.
        """
        context_block = format_context_block(project_state)
        probe_content, pattern_content = self._lookup_probe_and_patterns(
            phase_a_decision
        )

        return {
            "context_block": context_block,
            "probe_content": probe_content,
            "pattern_content": pattern_content,
            "retrieved_documents": "",
            "retrieved_conversations": "",
        }
