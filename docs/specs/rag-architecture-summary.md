# Project Forge — RAG Architecture Summary (Corrected)

> **Version:** 2.1 (post-engineering review + SRE hardening)
> **Status:** ARCHITECTURE FINAL — Ready for spec and build
> **Depends on:** Persistence build complete, Mode 1 + Mode 2 built and working

---

## Why RAG

As conversations accumulate uploaded files and extend past 10+ turns, stuffing everything into the context window becomes unsustainable. The current "send everything" approach bloats Phase B prompts to 15,000-20,000+ tokens by mid-session. RAG enables selective retrieval — only the content relevant to *this specific turn* enters the prompt.

---

## Core Architecture Decisions

### Vector Database: ChromaDB (Embedded)

- **Library:** `chromadb` — embedded, no separate server process
- **Install:** `pip install chromadb` (or `uv add chromadb`)
- **Storage location:** `~/Documents/forge-workspace/projects/<slug>/vectordb/`
- **Per-project structure:** Two separate collections (see below)
- **Why ChromaDB:** Zero infrastructure, auto-creates on first use, persists to disk, clones seamlessly with the repo
- **Client caching:** ChromaDB uses SQLite internally. Streamlit reruns the full script on every interaction — re-initializing `PersistentClient` on each rerun causes SQLite thread-lock errors. The ChromaDB client and Voyage client must be initialized via `@st.cache_resource` as singletons, not stored raw in `st.session_state`.

### Collections (Two Per Project)

| Collection | Contents | Search Target | What's Returned |
|---|---|---|---|
| `documents` | Uploaded file chunks | Leaf chunks (300-500 tokens) | Parent chunks (full section, 1000-2000 tokens) |
| `conversations` | Turn summaries | Summary embeddings | Full turn pair (user message + assistant response) |

**No knowledge base collection.** The 7 probes and 8 domain patterns are static content. Phase A outputs a deterministic probe name (e.g., `next_probe: "Probe 3"`). We use a Python dictionary lookup, not vector search, to inject the active probe definition. This eliminates an entire ChromaDB collection and the absurd overhead of embedding queries against 15 known items.

### Embedding Model: Voyage AI voyage-3.5-lite

- **Cost:** $0.02 per 1M tokens, first 200M tokens free
- **Context window:** 32K tokens (fits parent chunks without truncation)
- **Dimensions:** 512 default
- **Performance:** Outperforms OpenAI text-embedding-3-large by 6.34% at 6.5x lower cost
- **Configuration:** `VOYAGE_API_KEY` in `.env`, model name configurable in `config.py`

- **Rate limiting:** Large file ingestion (30+ page docs) can generate dozens of embedding batches. All Voyage API calls must use exponential backoff via `tenacity` to handle HTTP 429 rate limit errors gracefully, especially on the free/lite tier.

### Retrieval Strategy: Semantic Search + Metadata Filtering

**No hybrid search. No BM25. No Reciprocal Rank Fusion.**

ChromaDB does not natively support sparse keyword search or RRF. We rely on:
1. **Voyage semantic embeddings** for similarity search
2. **ChromaDB metadata filtering** for precision (filter by `active_probe`, `document_name`, `active_mode`, `turn_number`)

This is sufficient for V1. If exact-match queries (acronyms, stakeholder names) prove problematic in practice, we can add keyword search in a future version using a separate index.

### File Formats: DOCX and Markdown Only

No raw PDF support. Users convert PowerPoint → PDF → DOCX or Markdown before upload. This simplifies the ingestion pipeline dramatically.

### Document Parsing: MarkItDown → Markdown Header Splitter

**No custom python-docx AST parsing.** Enterprise Word documents have unreliable heading styles (bold text instead of "Heading 1", nested invisible tables, etc.). Building a custom structural parser is a rabbit hole.

Instead:
1. **MarkItDown** (Microsoft's library) converts DOCX to clean Markdown
2. **MarkdownHeaderTextSplitter** (LangChain-style) splits on `#`, `##`, `###` headers
3. This produces the parent-child chunk hierarchy naturally

All uploaded files normalize to Markdown before any chunking happens.

**Graceful degradation:** Enterprise DOCX files can have corrupted XML, broken macros, or embedded objects that crash MarkItDown. All file conversion is wrapped in try/except. If conversion fails, the file is saved to `uploads/` (so the user doesn't lose it) but skipped for ingestion, and `st.error("File could not be parsed")` is shown to the user. The app never crashes on a bad file.

---

## Chunking Strategy: Hierarchical Parent-Child

### Layer 1: Structural Splitting
After MarkItDown conversion, split Markdown on header boundaries (`#`, `##`, `###`). Each header-delimited section becomes a candidate chunk.

### Layer 2: Size Enforcement
- Oversized sections (>1000 tokens): split at paragraph boundaries, then sentence boundaries
- Undersized sections (<100 tokens): merge with next sibling section
- Never split mid-sentence

### Layer 3: Context Headers
Prepend breadcrumb to every chunk:
```
[Source: campaign-research-q3.docx > Findings > Customer Segments > Enterprise]
```
The embedding captures both content and structural position.

### Layer 4: Parent-Child Storage
- **Leaf chunks** (300-500 tokens): Embedded and searched against. High precision.
- **Parent chunks** (1000-2000 tokens): Full section the leaf belongs to. Stored as metadata, returned to LLM.

Search against leaves → return parents. Precise retrieval + sufficient context.

### File-Level Summaries
One LLM call per file upload generates a 1-paragraph summary. Stored in `project_state.json` manifest (not in vector store). Used by Phase A for routing decisions.

---

## Two-Phase Retrieval (Corrected)

### Phase A (Lightweight Routing)

Phase A reads directly from structured state — no vector retrieval:
- **Formatted context block** (dynamically assembled from `project_state.json`)
  - File manifest summaries (what documents exist, what they cover)
  - Org context string (from priming turn or `update_org_context`)
- **Assumption register summary** (counts by confidence level)
- **Routing context** (which probes fired, which patterns triggered, conversation summary)
- **Total: <2,000 tokens**

Phase A outputs a routing decision: "fire Probe 3: Stakeholder Mapping" or "enter Mode 2" or "time for micro-synthesis."

**Retrieval bypass flag:** Phase A also outputs a boolean `requires_retrieval`. When the user sends a filler response ("yes", "continue", "that makes sense, move on"), Phase A sets this to `false`. The orchestrator skips ChromaDB queries entirely and passes only always-on context to Phase B. This saves 3+ seconds of latency and avoids burning tokens on retrieval that adds no value to simple acknowledgment turns. Estimated 30-40% of turns in a typical session are filler.

### Context Assembly Step (Between Phase A and Phase B)

**Bypass check:** If Phase A's `requires_retrieval` is `false`, skip this step entirely. Phase B gets only always-on context. This handles filler turns efficiently.

When `requires_retrieval` is `true`, assemble context from two sources:

**From ChromaDB (semantic search + metadata filtering):**
1. `documents` collection: Query with user message + probe context → return top 3-4 parent chunks
2. `conversations` collection: Query with user message, filter `turn_number < current_turn - 2` → return 2-3 relevant full turn pairs, sorted chronologically

**From Python dictionary (direct lookup):**
3. Active probe definition + triggered domain patterns → looked up by key from Phase A's `next_probe` output

### Phase B (Execution with Assembled Context)

**Always-on context (fixed floor):**

| Content | Typical Size | Rationale |
|---|---|---|
| Formatted context block (from project_state.json) | 300-500 tokens | Ambient context relevant to every probe |
| Full assumption register | 400-2,000 tokens | Cross-cutting dependencies; retrieval safety net |
| Full document skeleton | 300-800 tokens | Model's working memory; partial skeleton risks rewriting fields |
| Full routing context | 300-500 tokens | Which probes fired; prevents re-asking covered questions |
| Last 2-3 conversation turns | 500-1,500 tokens | Conversational continuity |
| Core behavioral instructions | 500-800 tokens | Question format rules, assumption registration rules, skeleton population rules, completion criteria |
| **Fixed floor** | **~2,000-5,000 tokens** | |

**Retrieved context (selective):**

| Content | Typical Size | Source |
|---|---|---|
| Active probe definition + domain patterns | 500-800 tokens | Dictionary lookup |
| Relevant older conversation turns | 1,000-2,000 tokens | ChromaDB `conversations` collection |
| Uploaded file chunks | 2,000-4,000 tokens | ChromaDB `documents` collection |
| **Retrieved ceiling** | **~4,000-7,000 tokens** | |

**Total Phase B context: ~6,000-12,000 tokens** (vs. current 15,000-20,000+)

---

## Knowledge Base Restructuring

### Current State
`mode1_knowledge.py` and `mode2_knowledge.py` are monolithic strings — probe definitions, domain patterns, behavioral rules, completion criteria — all sent in full every turn.

### New Structure (Two Layers)

**Layer 1: Core behavioral instructions (always-on, 500-800 tokens)**
- Question format rules (2-3 questions per turn, cluster by domain)
- Assumption registration rules (confidence levels, impact ratings, dependency tracking)
- Skeleton population rules (when to update fields, how to structure)
- Completion criteria (how to know when a probe is done)

**Layer 2: Probe-specific content (dictionary-based lookup)**
- Individual probe definitions stored as Python dict entries
- Domain patterns stored as Python dict entries
- Phase A outputs `next_probe: "Probe 3"` → code does `PROBES["Probe 3"]` → injects text into Phase B prompt

**No vector database involved.** This is a code refactor, not a retrieval problem.

---

## Project State Management (Corrected)

### Drop context.md Auto-Regeneration

The original design auto-generated `context.md` via LLM call on every file upload. Problems: LLM drift over time, hallucinated summaries, race conditions in Streamlit.

**New design:** Maintain structured `project_state.json` with two sections:

```json
{
  "file_summaries": [
    {
      "filename": "campaign-research-q3.docx",
      "uploaded_at": "2026-02-22T15:30:00",
      "summary": "Q3 campaign research covering customer segments, ROI analysis, and competitive positioning.",
      "chunk_count": 14
    }
  ],
  "org_context": "84.51° analytics team. Key stakeholders: VP of Media, Brand Partners team..."
}
```

During Phase A and Phase B prompt assembly, Python code formats these JSON fields into a text block:

```python
def format_context_block(project_state: dict) -> str:
    parts = []
    if project_state["org_context"]:
        parts.append(f"## Organization Context\n{project_state['org_context']}")
    if project_state["file_summaries"]:
        parts.append("## Available Documents")
        for f in project_state["file_summaries"]:
            parts.append(f"- **{f['filename']}**: {f['summary']}")
    return "\n\n".join(parts)
```

No LLM rewriting. Deterministic string formatting. Updates instantly when files are added/removed or org context changes.

**Note:** The existing `context.md` file from the persistence spec continues to work as-is for org context. `project_state.json` extends it with file summaries. The org_context field in `project_state.json` is populated from the same source as `context.md` (the `update_org_context` tool).

---

## Conversation History as Retrievable Content

### Current Approach
Last 20 messages always in context. Bloats prompt, includes irrelevant turns.

### New Approach
Last 2-3 turns always present (conversational continuity). Older turns selectively retrieved.

### Turn Summary Generation (Corrected Timing)

**Phase A cannot generate the turn summary** because Phase B hasn't produced the response yet. Phase A only sees the user's message.

Turn summary is generated in `_post_turn_updates()` after Phase B completes:

1. Turn completes normally (Phase A → Context Assembly → Phase B → tool handling)
2. `_post_turn_updates()` runs
3. Fast Haiku/Flash call summarizes the `{user_message + assistant_response}` into 1-2 sentences
4. Embed the summary via Voyage API
5. Store in ChromaDB `conversations` collection with metadata:
   - `turn_number`
   - `active_probe`
   - `active_mode`
   - Full turn pair stored as parent content (user message + assistant response)
6. Auto-save state to disk

### Retrieval at Query Time

Context assembly step builds retrieval query from user's current message + Phase A's routing decision.

Queries `conversations` collection with:
- Semantic search on turn summary embeddings
- Metadata filter: `turn_number < current_turn - 2` (exclude recent turns already in always-on context)
- Optional boost: where `active_probe` matches current probe

Returns 2-3 most relevant turn summaries → injects full turn pairs into Phase B prompt, **chronologically sorted and labeled by turn number**.

```
[Retrieved context — earlier relevant exchanges]

Turn 3 (Probe: Stakeholder Mapping):
User: "The store ops team has been resistant..."
Assistant: "That resistance pattern suggests..."

Turn 7 (Probe: Root Cause):
User: "Actually, I realized the ops team..."
Assistant: "So the initial resistance was about..."

[Recent conversation]
Turn 10: ...
Turn 11: ...
```

---

## File Management: Sidebar Upload + Delete

### UI Components
- Sidebar section: "Project Files"
- Lists currently uploaded files (filename, upload date, summary preview)
- Upload button (drag-and-drop or file picker)
- Delete button (trash icon) per file

### Upload Processing Flow
1. User drops DOCX or MD file
2. Show spinner/progress indicator
3. **MarkItDown** converts DOCX → Markdown (MD files pass through)
4. **MarkdownHeaderTextSplitter** creates hierarchical chunks
5. Generate file-level summary via LLM call (Haiku)
6. Create leaf chunks (300-500 tokens) + parent chunks (full sections)
7. Prepend context headers to all chunks
8. Embed leaf chunks via Voyage API
9. Store in ChromaDB `documents` collection with parent references + metadata
10. Update `project_state.json` with file summary
11. File appears in sidebar list with checkmark
12. Next turn has access to new content

### File Deletion
- Removes chunks from ChromaDB
- Removes entry from `project_state.json`
- Sidebar list updates immediately

---

## Context Assembly Algorithm

```
Input: Phase A routing decision, user message, current turn number
Output: Assembled context for Phase B

1. Always-on context (assembled regardless of retrieval flag):
   - Formatted context block (from project_state.json — org context + file summaries)
   - Full assumption register
   - Full document skeleton
   - Full routing context
   - Last 2-3 conversation turns
   - Core behavioral instructions (from knowledge base Layer 1)

2. CHECK: If phase_a_decision["requires_retrieval"] is false → STOP HERE.
   Return only always-on context + probe definition from dictionary lookup.
   Skip steps 3 and 4.

3. Dictionary lookup (always fast, no API calls):
   - Active probe definition (PROBES[phase_a.next_probe])
   - Triggered domain patterns (PATTERNS[pattern_name] for each)

4. ChromaDB documents collection:
   - Semantic search with user message + probe context
   - Metadata filter by relevant document names if applicable
   - Return top 3-4 leaf matches → deduplicate by parent → inject parent chunks

5. ChromaDB conversations collection:
   - Semantic search with user message
   - Metadata filter: turn_number < current_turn - 2
   - Boost where active_probe matches current probe
   - Return top 2-3 → inject full turn pairs → sort chronologically, label by turn number

6. Assemble Phase B prompt:
   - System instructions
   - Always-on context
   - Looked-up probe/pattern content
   - Retrieved conversation turns (chronologically sorted)
   - Retrieved file chunks
   - Phase A routing decision
   - User's current message
```

---

## Dependencies (Add to pyproject.toml)

```toml
[project.dependencies]
chromadb = ">=0.4"
markitdown = ">=0.1"        # Microsoft's DOCX/PDF → Markdown converter
voyageai = ">=0.3"           # Voyage AI embedding client (or use via LiteLLM)
tenacity = ">=8.0"           # Exponential backoff for Voyage API rate limits
```

Note: `python-docx` is NOT needed — MarkItDown handles DOCX parsing internally.

---

## Files to Create/Modify

### New files:
- `src/pm_copilot/rag.py` — ingestion pipeline, retrieval, context assembly
- `src/pm_copilot/chunking.py` — MarkItDown conversion, header splitting, parent-child model

### Refactored files:
- `src/pm_copilot/mode1_knowledge.py` — decompose from monolithic string into:
  - `MODE1_CORE_INSTRUCTIONS` (always-on behavioral rules)
  - `MODE1_PROBES` dict (probe definitions keyed by probe name)
  - `MODE1_PATTERNS` dict (domain patterns keyed by pattern name)
- `src/pm_copilot/mode2_knowledge.py` — same decomposition

### Modified files:
- `orchestrator.py` — add context assembly step between Phase A and Phase B
- `state.py` — add fields for tracking uploaded files
- `app.py` — add file upload UI to sidebar with delete capability
- `config.py` — add `VOYAGE_API_KEY`, `EMBEDDING_MODEL` settings
- `tools.py` — integrate with `_post_turn_updates()` for turn summary generation

---

## Cost Estimates

**Per project setup (20 files, 15 pages each):**
- File summaries: 20 Haiku calls × ~$0.01 = $0.20
- Embedding: ~2M tokens × $0.02/1M = $0.04
- Total: ~$0.24

**Per conversation turn:**
- Turn summary: 1 Haiku call ≈ $0.002
- Turn embedding: ~100 tokens = negligible
- Retrieval queries: ~50 tokens per collection = negligible

**Monthly at scale (10 projects, 50 turns each):**
- Setup: 10 × $0.24 = $2.40
- Turn summaries: 500 × $0.002 = $1.00
- Total: ~$3.40/month

Voyage's 200M free tokens covers months of usage at this scale.

---

## Key Corrections from Engineering Review

| Original Design | Problem | Corrected Design |
|---|---|---|
| Hybrid search + RRF | ChromaDB doesn't support BM25 natively | Pure semantic search + metadata filtering |
| Knowledge base in ChromaDB | Absurd for 15 static items; Phase A already outputs probe name | Python dictionary lookup |
| Turn summary in Phase A | Phase A runs before Phase B — can't summarize what hasn't happened | Haiku call in `_post_turn_updates()` |
| Auto-regenerated context.md via LLM | LLM drift, hallucination, race conditions | Structured project_state.json with deterministic string formatting |
| Custom python-docx AST parser | Enterprise DOCX formatting is unreliable; days of edge-case work | MarkItDown → Markdown → header splitter |

## Key Corrections from SRE Review

| Original Design | Problem | Corrected Design |
|---|---|---|
| `ForgeRAG` stored raw in `st.session_state` | Streamlit reruns full script on every interaction; re-initializing ChromaDB's SQLite client causes thread-lock errors and memory leaks | ChromaDB `PersistentClient` and Voyage `Client` initialized via `@st.cache_resource` as singletons |
| Batch embedding by token count only | Sequential API batches on large files hit Voyage free-tier rate limits (HTTP 429), crashing the entire upload | `tenacity` library with exponential backoff wrapping all Voyage API calls |
| Context assembly runs on every turn | Filler responses ("yes", "continue") trigger 7,000 tokens of needless retrieval — wasted cost and 3+ seconds latency | Phase A outputs `requires_retrieval` boolean; orchestrator skips ChromaDB when `false` |
| `MarkItDown` called without error handling | Corrupted enterprise DOCX files crash MarkItDown, which crashes Streamlit, which wipes visible chat state | try/except around conversion; file saved to `uploads/` regardless; `st.error()` shown to user; ingestion skipped |

---

*Architecture: FINAL*
*Next step: Implementation spec + Claude Code build prompts*
