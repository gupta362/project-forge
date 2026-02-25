# Project Forge — RAG Implementation Spec (HOME)

> **Purpose:** This is the build specification for Claude Code. It defines every file, function, data structure, and integration point.
> **Environment:** HOME — Direct Anthropic API, standard model names, single pyproject.toml
> **Depends on:** Persistence build complete, Mode 1 + Mode 2 built and working
> **Architecture reference:** `docs/specs/rag-architecture-summary.md`

---

## 0. What This Adds

**Current state:** Every Phase B call gets the full knowledge base, full conversation history (up to 20 messages), and all org context — bloating prompts to 15,000-20,000+ tokens by mid-session. No support for uploaded files.

**After this build:**
- Users upload DOCX/MD files via the sidebar → files are parsed, chunked, embedded, and searchable
- Phase B gets only the context relevant to the current turn (~6,000-12,000 tokens)
- Knowledge base is decomposed — only the active probe's content enters the prompt
- Older conversation turns are indexed and retrieved by relevance, not dumped wholesale
- Structured project state tracks file summaries without LLM regeneration

**What this does NOT change:**
- Phase A/B loop mechanics (still two-phase)
- Tool definitions or tool handlers (except adding turn summary to `_post_turn_updates`)
- Mode 1 or Mode 2 behavioral logic
- Persistence module (save/load/slugify all unchanged)
- Priming turn flow

---

## 1. New Dependencies

Add to `pyproject.toml`:

```toml
[project.dependencies]
# ... existing deps (streamlit, anthropic, python-dotenv) ...
chromadb = ">=0.4"
markitdown = ">=0.1"
voyageai = ">=0.3"
tenacity = ">=8.0"
```

Run `pip install -e .` or `uv sync` to verify they install without errors.

---

## 2. Configuration (config.py)

Add these settings to the existing `config.py`. Your existing config has `ANTHROPIC_API_KEY` and `MODEL_NAME`. Add the RAG block below:

```python
# --- Existing settings (do not change) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-5-20250929")

# --- RAG / Embedding Settings (ADD THESE) ---
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "voyage-3.5-lite")
EMBEDDING_DIMENSIONS = 512

# Chunking
LEAF_CHUNK_MIN_TOKENS = 100
LEAF_CHUNK_MAX_TOKENS = 500
PARENT_CHUNK_MAX_TOKENS = 2000

# Retrieval
MAX_DOCUMENT_RESULTS = 4      # Parent chunks returned from documents collection
MAX_CONVERSATION_RESULTS = 3  # Turn pairs returned from conversations collection
ALWAYS_ON_TURN_WINDOW = 3     # Last N turns always in context (not retrieved)

# Turn summary model — uses the same Anthropic client as the main model, just Haiku instead of Sonnet
TURN_SUMMARY_MODEL = os.getenv("TURN_SUMMARY_MODEL", "claude-haiku-4-5-20251001")
```

Add to `.env.example`:
```
ANTHROPIC_API_KEY=your-key-here
VOYAGE_API_KEY=your-voyage-key-here
```

---

## 3. Knowledge Base Refactor

### Current structure (monolithic):
```python
# mode1_knowledge.py
MODE1_KNOWLEDGE = """... 4000+ token string with everything ..."""
```

### New structure (decomposed):

**`mode1_knowledge.py`** — refactored into three exports:

```python
# Core behavioral instructions — ALWAYS sent to Phase B
MODE1_CORE_INSTRUCTIONS = """
## Operating Rules for Mode 1

### Question Format
- Ask 2-3 questions per turn maximum
- Cluster questions by domain (don't jump between stakeholder mapping and technical feasibility in the same turn)
- Frame questions to surface specific information, not generic discussion

### Assumption Registration
- When the user states something as fact without evidence, register it as an assumption
- Confidence levels: validated (evidence provided), informed (reasonable inference), guessed (speculation)
- Impact levels: high (blocks decision), medium (influences direction), low (nice to know)
- Track dependencies: if Assumption A depends on Assumption B, record the link
- When an assumption is invalidated, flag all dependents as at-risk

### Skeleton Population
- Update document skeleton fields as information is confirmed, not speculated
- Revise fields when new information contradicts earlier entries
- Leave fields empty rather than filling with uncertain content

### Completion Criteria
- A probe is complete when you have enough signal to populate the relevant skeleton fields with confidence
- "Enough signal" means: the user has provided specific, concrete information (not vague acknowledgment)
- Move to the next probe when the current one is complete or the user explicitly wants to move on
"""

# Probe definitions — looked up by key based on Phase A routing
MODE1_PROBES = {
    "Probe 1": """
## Probe 1: Solution-Problem Separation
**Trigger:** User describes a solution ("we need to build X") without articulating the underlying problem.
**Questions to ask:**
- What specific pain point or unmet need is driving this?
- Who experiences this pain, and how do they cope today?
- What would happen if you did nothing?
**Completion:** User has articulated a problem statement distinct from any proposed solution.
**Skeleton fields:** problem_statement, target_audience
""",
    "Probe 2": """
## Probe 2: Temporal Trigger
**Trigger:** Problem described without clear urgency or forcing function.
**Questions to ask:**
- Why now? What changed recently?
- Is there a deadline, escalating cost, or competitive pressure?
- How long has this been a problem? What kept it from being addressed earlier?
**Completion:** Clear forcing function identified, or confirmed that urgency is low.
**Skeleton fields:** temporal_trigger, urgency_assessment
""",
    "Probe 3": """
## Probe 3: Stakeholder Mapping
**Trigger:** Multiple people or teams are involved, or decision-making authority is unclear.
**Questions to ask:**
- Who has final decision authority?
- Who feels the pain most directly?
- Who benefits from the status quo? (Critical — this is the question most PMs skip)
- Who needs to execute if a solution is chosen?
**Completion:** Clear stakeholder map with roles, incentives, and potential resistance identified.
**Skeleton fields:** stakeholders, decision_maker, status_quo_beneficiary
""",
    "Probe 4": """
## Probe 4: Root Cause Depth
**Trigger:** Problem statement sounds like a symptom rather than a root cause.
**Questions to ask:**
- Why does that happen? (Keep asking until you hit something structural)
- Is this a people problem, process problem, or systems problem?
- Has this been attempted before? What happened?
**Completion:** Root cause identified that is structural, not symptomatic.
**Skeleton fields:** root_cause, contributing_factors
""",
    "Probe 5": """
## Probe 5: Success Criteria Clarity
**Trigger:** User wants to solve a problem but hasn't defined what success looks like.
**Questions to ask:**
- How would you know this worked? What would you measure?
- What's the anti-metric — what should NOT get worse?
- What does "good enough" look like vs. perfection?
**Completion:** Measurable success criteria defined with at least one anti-metric.
**Skeleton fields:** success_metrics, anti_metrics, minimum_viable_outcome
""",
    "Probe 6": """
## Probe 6: Constraint Mapping
**Trigger:** Solution space seems unconstrained, or user hasn't mentioned limitations.
**Questions to ask:**
- What can't change? (Budget, timeline, team size, technology stack)
- What's already been tried or ruled out?
- Are there political or organizational constraints?
**Completion:** Hard constraints identified and distinguished from soft preferences.
**Skeleton fields:** constraints, non_negotiables
""",
    "Probe 7": """
## Probe 7: Evidence Assessment
**Trigger:** Claims about users, market, or impact lack supporting evidence.
**Questions to ask:**
- How do you know that? What evidence supports this?
- Is this based on data, user feedback, stakeholder assertion, or intuition?
- What would change your mind?
**Completion:** Key claims tagged with evidence type and confidence level.
**Skeleton fields:** evidence_base (updates assumption register confidence levels)
""",
}

# Domain patterns — looked up by key when Phase A detects them
MODE1_PATTERNS = {
    "Metrics Mismatch": """...""",
    "Scope Ambiguity": """...""",
    "Hidden Stakeholder Conflict": """...""",
    "Solution Inertia": """...""",
    "Organizational Scar Tissue": """...""",
    "Infrastructure Debt as Feature Requests": """...""",
    "Proxy User Problem": """...""",
    "Premature Scaling": """...""",
}
```

**`mode2_knowledge.py`** — same decomposition:

```python
MODE2_CORE_INSTRUCTIONS = """... always-on behavioral rules for Mode 2 ..."""

MODE2_PROBES = {
    "Problem-Solution Fit": """...""",
    "Implementation Risk": """...""",
    "Organizational Readiness": """...""",
    "Competitive Context": """...""",
    "Sustainability": """...""",
}

# Mode 2 risk dimensions (always included when in Mode 2)
MODE2_RISK_FRAMEWORK = """
## Risk Assessment Framework (Cagan)
Value Risk — Will anyone use it?
Usability Risk — Can users figure it out?
Feasibility Risk — Can we build it?
Viability Risk — Should we build it?
"""
```

**CRITICAL:** Preserve the exact text content of each probe and pattern. This is a structural refactor, not a content rewrite. The text that was in the monolithic string goes into the appropriate dict entry verbatim.

---

## 4. New File: `src/pm_copilot/chunking.py`

Handles DOCX/MD → Markdown conversion and hierarchical chunking.

### Functions:

```python
def convert_to_markdown(file_path: Path) -> str:
    """Convert DOCX or MD file to clean Markdown using MarkItDown.
    
    Args:
        file_path: Path to .docx or .md file
    
    Returns:
        Markdown string
    
    Raises:
        FileConversionError: If MarkItDown fails to parse the file.
            Caller must catch this and handle gracefully (save file 
            to uploads/ but skip ingestion, show st.error to user).
    
    If file is already .md, reads and returns contents directly.
    If file is .docx, uses MarkItDown to convert.
    
    IMPORTANT: Wrap MarkItDown execution in try/except. Enterprise DOCX 
    files can have corrupted XML, broken macros, or embedded objects that 
    crash the parser. Define a custom FileConversionError and raise it 
    with the original exception message so the caller can log and surface it.
    """

def split_markdown_by_headers(
    markdown_text: str,
    source_filename: str,
) -> list[dict]:
    """Split Markdown into hierarchical chunks based on headers.
    
    Returns list of chunks, each with:
    {
        "text": str,              # Chunk content
        "header_path": list[str], # e.g., ["Findings", "Customer Segments", "Enterprise"]
        "level": int,             # Header depth (1=H1, 2=H2, etc.)
        "context_header": str,    # "[Source: filename > Findings > Customer Segments > Enterprise]"
    }
    
    Splitting rules:
    - Split on #, ##, ### headers
    - Each header-delimited section becomes a chunk
    - Preserve header hierarchy for context headers
    """

def enforce_chunk_sizes(
    chunks: list[dict],
    min_tokens: int = 100,
    max_tokens: int = 500,
) -> list[dict]:
    """Enforce token size limits on chunks.
    
    - Chunks > max_tokens: split at paragraph boundaries, then sentence boundaries
    - Chunks < min_tokens: merge with next sibling chunk
    - Never split mid-sentence
    - Updates context_header on merged/split chunks
    
    Returns list of right-sized chunks.
    """

def create_parent_child_pairs(
    chunks: list[dict],
    parent_max_tokens: int = 2000,
) -> list[dict]:
    """Group leaf chunks into parent chunks.
    
    A parent chunk is the full section a leaf belongs to (up to parent_max_tokens).
    If a section was split into multiple leaves during size enforcement,
    all those leaves share the same parent.
    
    Returns list of leaf chunks, each augmented with:
    {
        ...existing fields...,
        "parent_text": str,      # Full parent section text
        "parent_id": str,        # Unique ID for the parent (for deduplication)
        "leaf_index": int,       # Position within the parent
    }
    """

def process_file(file_path: Path) -> list[dict]:
    """Full pipeline: file → markdown → split → size enforce → parent-child pairs.
    
    Returns list of leaf chunks ready for embedding and storage.
    """
```

### Token counting:
Use a simple approximation: `len(text.split()) * 1.3` for token estimation. Don't add tiktoken as a dependency — the approximation is fine for chunking.

---

## 5. New File: `src/pm_copilot/rag.py`

Core RAG module handling embedding, storage, retrieval, and context assembly.

### Initialization:

**CRITICAL — Streamlit Thread Safety:** ChromaDB uses SQLite internally. Streamlit reruns the full Python script on every interaction. If `PersistentClient` or `voyageai.Client` are re-instantiated on each rerun, you get SQLite thread-lock errors ("database is locked") and memory leaks. Both clients MUST be initialized as singletons.

```python
import chromadb
import voyageai
from pathlib import Path

# --- Cached singleton factories (module-level) ---
# These must be decorated with @st.cache_resource in app.py when called.
# The ForgeRAG class itself accepts pre-initialized clients.

def _create_chroma_client(vectordb_path: str) -> chromadb.PersistentClient:
    """Create ChromaDB client. Called via @st.cache_resource in app.py."""
    return chromadb.PersistentClient(path=vectordb_path)

def _create_voyage_client(api_key: str) -> voyageai.Client:
    """Create Voyage AI client. Called via @st.cache_resource in app.py."""
    return voyageai.Client(api_key=api_key)


class ForgeRAG:
    """Manages vector storage and retrieval for a Forge project."""
    
    def __init__(self, project_dir: Path, chroma_client: chromadb.PersistentClient, voyage_client: voyageai.Client):
        """Initialize RAG for a project.
        
        IMPORTANT: Do NOT create ChromaDB or Voyage clients here.
        Clients must be passed in as pre-initialized singletons 
        (cached via @st.cache_resource in app.py) to avoid 
        Streamlit thread-lock issues with SQLite.
        
        Args:
            project_dir: Path to the project directory
            chroma_client: Pre-initialized ChromaDB PersistentClient (singleton)
            voyage_client: Pre-initialized Voyage AI Client (singleton)
        """
        self.project_dir = project_dir
        self.vectordb_path = project_dir / "vectordb"
        self.client = chroma_client
        self.voyage = voyage_client
        
        # Get or create collections
        self.documents = self.client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}
        )
        self.conversations = self.client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"}
        )
```

**In `app.py`, initialize like this:**

```python
import streamlit as st

@st.cache_resource
def get_chroma_client(vectordb_path: str) -> chromadb.PersistentClient:
    return _create_chroma_client(vectordb_path)

@st.cache_resource
def get_voyage_client(api_key: str) -> voyageai.Client:
    return _create_voyage_client(api_key)

# Then when creating ForgeRAG:
chroma = get_chroma_client(str(project_dir / "vectordb"))
voyage = get_voyage_client(config.VOYAGE_API_KEY)
rag = ForgeRAG(project_dir, chroma_client=chroma, voyage_client=voyage)
```

### Embedding:

```python
    from tenacity import retry, wait_exponential, retry_if_exception_type, stop_after_attempt
    import httpx  # or whatever Voyage client raises for HTTP errors
    
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((httpx.HTTPStatusError, Exception)),
        # Retry on 429 Too Many Requests and transient errors
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
        """Embed texts using Voyage AI with batching and rate-limit handling.
        
        Uses config.EMBEDDING_MODEL and config.EMBEDDING_DIMENSIONS.
        Splits texts into batches to stay under Voyage's per-request limits,
        then calls each batch with exponential backoff retry to handle 
        HTTP 429 rate limit errors on the free/lite tier.
        
        Large file ingestion (30+ page docs) can generate 60+ chunks across
        4-5 batches — firing them sequentially without backoff will hit rate limits.
        """
        BATCH_SIZE = 128  # Voyage's max batch size
        all_embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
        return all_embeddings
```

**Note on retry exception type:** Check what exception the `voyageai` client actually raises on HTTP 429. It may be a `voyageai.error.RateLimitError` or similar. Adjust the `retry_if_exception_type` accordingly. The key behavior is: retry on 429 and 5xx, fail fast on 4xx (except 429).

### Document Ingestion:

```python
    def ingest_file(self, file_path: Path, file_summary: str) -> int:
        """Ingest a file into the documents collection.
        
        Args:
            file_path: Path to the uploaded file
            file_summary: LLM-generated summary of the file
        
        Returns:
            Number of chunks stored
        
        Flow:
        1. Call chunking.process_file(file_path) to get leaf chunks
        2. Embed leaf chunk texts (with context headers prepended)
        3. Store in documents collection with metadata:
           - source_filename
           - header_path (as JSON string)
           - context_header
           - parent_text (the full parent section)
           - parent_id
           - leaf_index
        """
    
    def remove_file(self, filename: str) -> int:
        """Remove all chunks for a given filename from documents collection.
        
        Returns number of chunks removed.
        Uses metadata filter: where={"source_filename": filename}
        """
```

### Conversation Indexing:

```python
    def index_turn(
        self,
        turn_number: int,
        user_message: str,
        assistant_response: str,
        turn_summary: str,
        active_probe: str,
        active_mode: str,
    ) -> None:
        """Index a completed conversation turn.
        
        Embeds the turn_summary and stores it with the full turn pair as metadata.
        
        Metadata stored:
        - turn_number: int
        - active_probe: str
        - active_mode: str
        - user_message: str (full text — this is the "parent" content)
        - assistant_response: str (full text — this is the "parent" content)
        """
```

### Retrieval:

```python
    def retrieve_documents(
        self,
        query: str,
        n_results: int = None,
        filename_filter: str = None,
    ) -> list[dict]:
        """Retrieve relevant document chunks.
        
        Args:
            query: Search query (typically user message + probe context)
            n_results: Max results (default: config.MAX_DOCUMENT_RESULTS)
            filename_filter: Optional filename to restrict search to one document
        
        Returns list of dicts:
        [
            {
                "parent_text": str,    # Full parent section (what goes into Phase B)
                "context_header": str, # Source breadcrumb
                "source_filename": str,
                "score": float,        # Similarity score
            }
        ]
        
        Deduplicates by parent_id — if two leaves from the same parent match,
        only return the parent once.
        """
    
    def retrieve_conversations(
        self,
        query: str,
        current_turn: int,
        n_results: int = None,
        probe_filter: str = None,
    ) -> list[dict]:
        """Retrieve relevant older conversation turns.
        
        Args:
            query: Search query
            current_turn: Current turn number (to exclude recent turns)
            n_results: Max results (default: config.MAX_CONVERSATION_RESULTS)
            probe_filter: Optional probe name to boost matches
        
        Returns list of dicts, sorted by turn_number ascending:
        [
            {
                "turn_number": int,
                "active_probe": str,
                "user_message": str,
                "assistant_response": str,
                "score": float,
            }
        ]
        
        Applies metadata filter: turn_number < current_turn - config.ALWAYS_ON_TURN_WINDOW
        Results are sorted chronologically regardless of relevance ranking.
        """
```

### Context Assembly:

```python
    def assemble_context(
        self,
        user_message: str,
        phase_a_decision: dict,
        current_turn: int,
        project_state: dict,
    ) -> dict:
        """Assemble the full context for Phase B.
        
        Args:
            user_message: Current user message
            phase_a_decision: Phase A routing output (contains next_probe, triggered_patterns, etc.)
            current_turn: Current turn number
            project_state: Contents of project_state.json (file_summaries, org_context)
        
        Returns dict with assembled context sections:
        {
            "context_block": str,           # Formatted org context + file summaries
            "probe_content": str,           # Active probe definition (from dictionary lookup)
            "pattern_content": str,         # Triggered domain pattern definitions
            "retrieved_documents": str,     # Formatted document chunks
            "retrieved_conversations": str, # Formatted older turn pairs
        }
        
        Flow:
        1. Format context block from project_state (deterministic string formatting)
        2. Look up active probe: MODE1_PROBES[phase_a_decision["next_probe"]]
        3. Look up triggered patterns: MODE1_PATTERNS[p] for each
        4. Retrieve document chunks from ChromaDB
        5. Retrieve conversation turns from ChromaDB
        6. Format all sections as strings ready for prompt injection
        """

    def assemble_context_minimal(
        self,
        phase_a_decision: dict,
        current_turn: int,
        project_state: dict,
    ) -> dict:
        """Assemble minimal context for filler/bypass turns.
        
        Called when Phase A sets requires_retrieval=false (user said 
        "yes", "continue", "that makes sense", etc.). Skips all 
        ChromaDB queries to save ~3 seconds latency and ~7,000 tokens.
        
        Returns same dict shape as assemble_context() but with empty 
        strings for retrieved_documents and retrieved_conversations.
        
        Still includes:
        - context_block (formatted project state — cheap, deterministic)
        - probe_content (dictionary lookup — instant)
        - pattern_content (dictionary lookup — instant)
        
        Does NOT include:
        - retrieved_documents (skipped)
        - retrieved_conversations (skipped)
        """
```

---

## 6. State Changes

### `state.py` — Add new fields to `init_session_state()`:

```python
st.session_state.rag = None                # ForgeRAG instance (transient, not persisted)
                                           # IMPORTANT: ForgeRAG accepts pre-initialized 
                                           # cached clients, NOT raw — see orchestrator init
st.session_state.project_state = {         # Persisted in project_state.json
    "file_summaries": [],
    "org_context": "",
}
```

### `persistence.py` — Add project_state.json handling:

```python
def save_project_state(project_dir: Path, project_state: dict) -> None:
    """Save project_state.json (file summaries + org context)."""
    state_file = project_dir / "project_state.json"
    temp_file = project_dir / "project_state.json.tmp"
    with open(temp_file, "w") as f:
        json.dump(project_state, f, indent=2)
    temp_file.rename(state_file)

def load_project_state(project_dir: Path) -> dict:
    """Load project_state.json, return default if doesn't exist."""
    state_file = project_dir / "project_state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {"file_summaries": [], "org_context": ""}
```

Add `"project_state"` to `PERSISTED_KEYS` list. Load it during `load_project()`.

---

## 7. Orchestrator Changes

### `orchestrator.py` — Modified `run_turn()` flow:

```python
def run_turn(user_message: str) -> str:
    # 1. Handle __PRIMING_TURN__ (unchanged)
    
    # 2. Increment turn count, append user message (unchanged)
    
    # 3. Re-read context file (unchanged)
    
    # 4. Initialize RAG if needed (uses cached singleton clients — see app.py)
    #    NOTE: Do NOT create ForgeRAG(project_dir) directly here.
    #    The chroma_client and voyage_client must be passed in as 
    #    @st.cache_resource singletons to avoid SQLite thread-lock errors.
    if st.session_state.project_dir and st.session_state.rag is None:
        chroma = get_chroma_client(str(st.session_state.project_dir / "vectordb"))
        voyage = get_voyage_client(config.VOYAGE_API_KEY)
        st.session_state.rag = ForgeRAG(
            st.session_state.project_dir, 
            chroma_client=chroma, 
            voyage_client=voyage
        )
    
    # 5. Phase A — lightweight routing (unchanged, but uses formatted context block)
    #    Phase A now also outputs requires_retrieval boolean
    routing_decision = _run_phase_a(user_message)
    
    # 6. NEW: Context Assembly (with retrieval bypass for filler turns)
    assembled = None
    if st.session_state.rag:
        if routing_decision.get("requires_retrieval", True):
            # Full context assembly — dictionary lookup + ChromaDB queries
            assembled = st.session_state.rag.assemble_context(
                user_message=user_message,
                phase_a_decision=routing_decision,
                current_turn=st.session_state.turn_count,
                project_state=st.session_state.project_state,
            )
        else:
            # Bypass: filler turn — only always-on context + probe definition
            assembled = st.session_state.rag.assemble_context_minimal(
                phase_a_decision=routing_decision,
                current_turn=st.session_state.turn_count,
                project_state=st.session_state.project_state,
            )
    
    # 7. Phase B — execution with assembled context
    response = _run_phase_b(user_message, routing_decision, assembled_context=assembled)
    
    # 8. Tool handling (unchanged)
    
    # 9. Post-turn updates (MODIFIED — now includes turn summary + indexing)
    _post_turn_updates(user_message, response)
    
    # 10. Auto-save (unchanged)
    
    return response
```

### Modified `_run_phase_b()`:

Phase B prompt now uses assembled context instead of dumping everything:

```python
def _run_phase_b(user_message, routing_decision, assembled_context=None):
    # Build prompt with:
    # - Core behavioral instructions (always on)
    # - assembled_context["probe_content"] (instead of full knowledge base)
    # - assembled_context["pattern_content"]
    # - assembled_context["context_block"]
    # - Full assumption register (always on)
    # - Full document skeleton (always on)
    # - Full routing context (always on)
    # - Last ALWAYS_ON_TURN_WINDOW turns (always on)
    # - assembled_context["retrieved_conversations"] (older relevant turns)
    # - assembled_context["retrieved_documents"] (file chunks)
    # - routing_decision
    # - user_message
    
    # If assembled_context is None (no RAG initialized), fall back to current behavior
```

### Modified `_post_turn_updates()`:

```python
def _post_turn_updates(user_message: str, assistant_response: str):
    # ... existing updates (assumption register, skeleton, routing context) ...
    
    # NEW: Generate turn summary and index in ChromaDB
    if st.session_state.rag and st.session_state.turn_count > config.ALWAYS_ON_TURN_WINDOW:
        # Generate summary via fast Haiku call
        summary = _generate_turn_summary(user_message, assistant_response)
        
        # Index in conversations collection
        st.session_state.rag.index_turn(
            turn_number=st.session_state.turn_count,
            user_message=user_message,
            assistant_response=assistant_response,
            turn_summary=summary,
            active_probe=st.session_state.routing_context.get("active_probe", ""),
            active_mode=st.session_state.active_mode,
        )

def _generate_turn_summary(user_message: str, assistant_response: str) -> str:
    """Generate 1-2 sentence summary of a completed turn via Haiku.
    Uses the same `client` object as all other API calls — just points to TURN_SUMMARY_MODEL (Haiku) instead of MODEL_NAME (Sonnet).
    """
    response = client.messages.create(
        model=config.TURN_SUMMARY_MODEL,
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"Summarize this conversation exchange in 1-2 sentences. Focus on what was discussed and any decisions or assumptions made.\n\nUser: {user_message}\n\nAssistant: {assistant_response}"
        }],
    )
    return response.content[0].text
```

---

## 8. App Changes (Sidebar File Upload)

### Add to sidebar in `app.py`:

After the project management section and documentation tabs, before Active Mode:

```python
# --- Project Files ---
if st.session_state.project_dir:
    st.subheader("Project Files")
    
    project_state = st.session_state.project_state
    
    # List existing files
    for i, file_info in enumerate(project_state.get("file_summaries", [])):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(f"📄 {file_info['filename']}")
            st.caption(file_info['summary'][:100] + "...")
        with col2:
            if st.button("🗑️", key=f"delete_file_{i}"):
                _delete_file(file_info['filename'])
                st.rerun()
    
    # Upload button
    uploaded_file = st.file_uploader(
        "Upload document",
        type=["docx", "md"],
        key="file_uploader",
    )
    
    if uploaded_file:
        with st.spinner(f"Processing {uploaded_file.name}..."):
            _process_uploaded_file(uploaded_file)
        st.rerun()
    
    st.divider()
```

### File processing function:

```python
def _process_uploaded_file(uploaded_file):
    """Save uploaded file, ingest into RAG, update project state.
    
    IMPORTANT: File is saved to uploads/ FIRST, before any conversion.
    If MarkItDown fails on a corrupted DOCX, the user's file is preserved 
    but ingestion is skipped. This prevents data loss on bad files.
    """
    project_dir = st.session_state.project_dir
    uploads_dir = project_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    
    # Save file to disk FIRST (before any conversion that might fail)
    file_path = uploads_dir / uploaded_file.name
    file_path.write_bytes(uploaded_file.read())
    
    # Attempt markdown conversion — enterprise DOCX files can be corrupted
    from .chunking import convert_to_markdown, FileConversionError
    try:
        md_text = convert_to_markdown(file_path)
    except FileConversionError as e:
        # File is saved to uploads/ but cannot be parsed for RAG
        logger.warning(f"Failed to parse {uploaded_file.name}: {e}")
        st.error(
            f"⚠️ '{uploaded_file.name}' could not be parsed. "
            f"The file has been saved but won't be searchable. "
            f"Try re-exporting from Word as a clean .docx."
        )
        return  # Exit without ingestion — file preserved on disk
    
    # Generate file summary via LLM
    summary = _generate_file_summary(uploaded_file.name, md_text[:3000])
    
    # Initialize RAG if needed (uses cached singleton clients)
    if st.session_state.rag is None:
        chroma = get_chroma_client(str(project_dir / "vectordb"))
        voyage = get_voyage_client(config.VOYAGE_API_KEY)
        st.session_state.rag = ForgeRAG(
            project_dir, chroma_client=chroma, voyage_client=voyage
        )
    
    # Ingest into ChromaDB
    chunk_count = st.session_state.rag.ingest_file(file_path, summary)
    
    # Update project state
    st.session_state.project_state["file_summaries"].append({
        "filename": uploaded_file.name,
        "uploaded_at": datetime.now().isoformat(),
        "summary": summary,
        "chunk_count": chunk_count,
    })
    
    # Save project state
    from .persistence import save_project_state
    save_project_state(project_dir, st.session_state.project_state)
    
    logger.info(f"Ingested {uploaded_file.name}: {chunk_count} chunks")

def _delete_file(filename: str):
    """Remove file from RAG and project state."""
    if st.session_state.rag:
        st.session_state.rag.remove_file(filename)
    
    # Remove from project state
    st.session_state.project_state["file_summaries"] = [
        f for f in st.session_state.project_state["file_summaries"]
        if f["filename"] != filename
    ]
    
    # Remove physical file
    file_path = st.session_state.project_dir / "uploads" / filename
    if file_path.exists():
        file_path.unlink()
    
    # Save updated project state
    from .persistence import save_project_state
    save_project_state(st.session_state.project_dir, st.session_state.project_state)
    
    logger.info(f"Deleted {filename} from project")

def _generate_file_summary(filename: str, content_preview: str) -> str:
    """Generate 1-paragraph summary of an uploaded file via Haiku."""
    response = client.messages.create(
        model=config.TURN_SUMMARY_MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"Summarize this document in one paragraph (2-3 sentences). Focus on what topics it covers and what kind of information it contains.\n\nFilename: {filename}\n\nContent:\n{content_preview}"
        }],
    )
    return response.content[0].text
```

---

## 9. Updated Project Directory Structure

```
~/Documents/forge-workspace/projects/
└── campaign-roi-analysis/
    ├── state.json              # Session state (existing)
    ├── project_state.json      # NEW: file summaries + org context
    ├── context.md              # Org context (existing)
    ├── artifacts/              # Auto-saved artifacts (existing)
    │   ├── problem_brief.md
    │   └── solution_evaluation.md
    ├── uploads/                # NEW: uploaded source files
    │   ├── campaign-research-q3.docx
    │   └── stakeholder-notes.md
    └── vectordb/               # NEW: ChromaDB persistent storage
        └── chroma.sqlite3      # (ChromaDB manages this internally)
```

---

## 10. Prompt Changes

### Phase A prompt — add formatted context block and requires_retrieval flag:

Replace the current org_context injection with the formatted context block:

```python
# In _run_phase_a():
context_block = format_context_block(st.session_state.project_state)

# Inject into Phase A prompt where org_context currently goes
```

**Add `requires_retrieval` to Phase A's expected output:**

Phase A already outputs structured routing decisions (next_probe, triggered_patterns, etc.). Add a boolean field:

```
requires_retrieval: boolean
- true: User's message contains substantive content that benefits from 
  document retrieval and conversation history search.
- false: User's message is a filler response (e.g., "yes", "continue", 
  "that makes sense", "let's move on", "go ahead"). No retrieval needed.
  Phase B only needs always-on context and the active probe definition.
```

**Update the Phase A prompt template** to include this instruction:

```
Also output a boolean "requires_retrieval". Set this to false if the user 
is simply acknowledging, confirming, or asking to continue (e.g., "yes", 
"sounds good", "next question", "continue"). Set to true if the user is 
providing new information, asking a question, sharing context, or giving 
a substantive response that would benefit from retrieving relevant 
documents or past conversation turns.
```

The `format_context_block()` function:

```python
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
```

### Phase B prompt — use assembled context:

Replace the monolithic knowledge base injection with:

```python
# Instead of:
# knowledge_base=MODE1_KNOWLEDGE  (full monolithic string)

# Use:
# core_instructions=MODE1_CORE_INSTRUCTIONS  (always-on, ~500-800 tokens)
# probe_content=assembled["probe_content"]   (active probe only)
# pattern_content=assembled["pattern_content"] (triggered patterns only)
# retrieved_docs=assembled["retrieved_documents"]
# retrieved_turns=assembled["retrieved_conversations"]
```

Update the Phase B prompt template to accept these new sections.

### Phase B prompt — retrieved context formatting:

```
{core_instructions}

{probe_content}

{pattern_content}

## Retrieved Document Context
{retrieved_documents}

## Earlier Relevant Exchanges
{retrieved_conversations}

## Current State
{assumption_register}
{document_skeleton}
{routing_context}

## Recent Conversation
{last_n_turns}

## Phase A Routing Decision
{routing_decision}

## Current Message
{user_message}
```

---

## 11. File Summary

### New files:
| File | Contents |
|---|---|
| `src/pm_copilot/chunking.py` | `convert_to_markdown` (with `FileConversionError`), `split_markdown_by_headers`, `enforce_chunk_sizes`, `create_parent_child_pairs`, `process_file` |
| `src/pm_copilot/rag.py` | `ForgeRAG` class (accepts cached clients) with `_embed_batch` (tenacity retry), `_embed`, `ingest_file`, `remove_file`, `index_turn`, `retrieve_documents`, `retrieve_conversations`, `assemble_context`, `assemble_context_minimal` |

### Refactored files:
| File | Change |
|---|---|
| `mode1_knowledge.py` | Split into `MODE1_CORE_INSTRUCTIONS`, `MODE1_PROBES` dict, `MODE1_PATTERNS` dict |
| `mode2_knowledge.py` | Split into `MODE2_CORE_INSTRUCTIONS`, `MODE2_PROBES` dict, `MODE2_RISK_FRAMEWORK` |

### Modified files:
| File | Change |
|---|---|
| `config.py` | Add RAG/embedding settings |
| `state.py` | Add `rag` and `project_state` fields |
| `persistence.py` | Add `save_project_state`, `load_project_state` |
| `orchestrator.py` | Add RAG init, context assembly step, modified `_run_phase_b`, modified `_post_turn_updates` |
| `app.py` | Add sidebar file upload/delete UI |
| `prompts.py` | Update Phase A and Phase B prompt templates for assembled context |
| `pyproject.toml` | Add chromadb, markitdown, voyageai, tenacity dependencies |

---

## 12. Testing Checklist

### File upload:
- [ ] Upload a DOCX file → appears in sidebar list with summary
- [ ] Upload an MD file → appears in sidebar list with summary
- [ ] Delete a file → removed from sidebar, chunks removed from ChromaDB
- [ ] Upload mid-session → next turn can retrieve content from the new file
- [ ] Upload a corrupted/malformed DOCX → st.error shown, file saved to uploads/, app does NOT crash, no chunks in ChromaDB

### Retrieval:
- [ ] Ask about something in an uploaded document → relevant chunks appear in Phase B context
- [ ] Reference something from Turn 3 at Turn 10 → Turn 3 exchange retrieved
- [ ] Active probe content appears in Phase B context (from dictionary lookup)
- [ ] Irrelevant turns are NOT in Phase B context

### Retrieval bypass (filler turns):
- [ ] Send "yes, continue" → Phase A outputs `requires_retrieval: false`
- [ ] When requires_retrieval is false → no ChromaDB queries logged, only always-on context in Phase B
- [ ] Send a substantive response → Phase A outputs `requires_retrieval: true` → full retrieval runs

### Knowledge base:
- [ ] Only active probe definition appears in Phase B (not all 7)
- [ ] Core behavioral instructions always present
- [ ] Domain patterns appear only when triggered by Phase A

### Context size:
- [ ] Log total Phase B context tokens — should be 6,000-12,000, not 15,000+
- [ ] Filler turn context tokens should be ~2,000-5,000 (always-on only)
- [ ] No degradation in response quality compared to current "send everything" approach

### Conversation indexing:
- [ ] Turn summaries generated after each turn (check logs)
- [ ] ChromaDB conversations collection grows with each turn
- [ ] Older turns retrievable by relevance

### Streamlit stability:
- [ ] Rapidly click sidebar buttons → no "database is locked" SQLite errors
- [ ] Upload multiple files in quick succession → no thread-lock crashes
- [ ] Long session (20+ turns) → no memory leak from client re-initialization

### Rate limiting:
- [ ] Upload a large document (30+ pages, 60+ chunks) → embedding succeeds with retry backoff
- [ ] Check logs for tenacity retry attempts on 429 errors (if on free tier)

### Integration:
- [ ] App starts without errors when no VOYAGE_API_KEY is set (graceful degradation)
- [ ] Existing projects without vectordb/ directory work (RAG features disabled until first upload)
- [ ] Persistence save/load still works with new project_state.json

---

## 13. Known Limitations (V1)

1. **No hybrid search** — Pure semantic search only. Exact-match queries (acronyms, names) may miss. Revisit if this proves problematic.
2. **No reranking** — Initial retrieval results used as-is. Voyage offers rerank models for future improvement.
3. **Single embedding model** — No fallback if Voyage API is down. Could add local model fallback later.
4. **No file versioning** — Uploading a file with the same name as an existing file should be handled (delete old, ingest new).
5. **Turn summary cost** — One Haiku call per turn for summary generation. At ~$0.002/turn this is negligible but adds latency (~0.5s).
6. **requires_retrieval is LLM-judged** — Phase A decides if retrieval is needed. It may occasionally misjudge a filler turn as substantive or vice versa. Acceptable for V1; monitor in testing.

---

*Spec: COMPLETE — HOME environment*
*Build order: See rag-build-prompts.md (HOME)*
