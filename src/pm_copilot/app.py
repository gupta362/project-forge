import csv
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import streamlit as st
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

from pm_copilot import config
from pm_copilot.state import init_session_state
from pm_copilot.persistence import (
    slugify_project_name, save_project, load_project, ensure_workspace_exists,
    save_project_state, load_project_state,
)
from pm_copilot.rag import ForgeRAG, _create_chroma_client, _create_voyage_client
from pm_copilot.chunking import convert_to_markdown, FileConversionError

logger = logging.getLogger("forge.app")
from pm_copilot.orchestrator import run_turn

_anthropic_client = Anthropic()


@st.cache_resource
def get_chroma_client(vectordb_path: str):
    """Cached ChromaDB client singleton — avoids SQLite thread-lock errors."""
    return _create_chroma_client(vectordb_path)


@st.cache_resource
def get_voyage_client(api_key: str):
    """Cached Voyage AI client singleton."""
    return _create_voyage_client(api_key)


# ---------------------------------------------------------------------------
# File management helpers
# ---------------------------------------------------------------------------

def _process_uploaded_file(uploaded_file) -> None:
    """Save uploaded file, ingest into RAG, update project state.

    File is saved to uploads/ FIRST, before any conversion. If MarkItDown
    fails on a corrupted DOCX, the user's file is preserved but ingestion
    is skipped.
    """
    project_dir = st.session_state.project_dir
    uploads_dir = project_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    # Save file to disk FIRST (before any conversion that might fail)
    file_path = uploads_dir / uploaded_file.name
    file_path.write_bytes(uploaded_file.read())

    # Attempt markdown conversion
    try:
        md_text = convert_to_markdown(file_path)
    except FileConversionError as e:
        logger.warning("Failed to parse %s: %s", uploaded_file.name, e)
        st.error(
            f"'{uploaded_file.name}' could not be parsed. "
            f"The file has been saved but won't be searchable. "
            f"Try re-exporting from Word as a clean .docx."
        )
        return

    # Generate file summary via LLM
    summary = _generate_file_summary(uploaded_file.name, md_text[:3000])

    # Initialize RAG if needed (uses cached singleton clients)
    if st.session_state.rag is None:
        chroma = get_chroma_client(str(project_dir / "vectordb"))
        voyage = get_voyage_client(config.VOYAGE_API_KEY) if config.VOYAGE_API_KEY else None
        st.session_state.rag = ForgeRAG(
            project_dir, chroma_client=chroma, voyage_client=voyage,
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

    save_project_state(project_dir, st.session_state.project_state)
    logger.info("Ingested %s: %d chunks", uploaded_file.name, chunk_count)


def _delete_file(filename: str) -> None:
    """Remove file from RAG and project state."""
    if st.session_state.rag:
        st.session_state.rag.remove_file(filename)

    st.session_state.project_state["file_summaries"] = [
        f for f in st.session_state.project_state["file_summaries"]
        if f["filename"] != filename
    ]

    file_path = st.session_state.project_dir / "uploads" / filename
    if file_path.exists():
        file_path.unlink()

    save_project_state(st.session_state.project_dir, st.session_state.project_state)
    logger.info("Deleted %s from project", filename)


def _generate_file_summary(filename: str, content_preview: str) -> str:
    """Generate 1-paragraph summary of an uploaded file via Haiku."""
    response = _anthropic_client.messages.create(
        model=config.TURN_SUMMARY_MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": (
                "Summarize this document in one paragraph (2-3 sentences). "
                "Focus on what topics it covers and what kind of information it contains.\n\n"
                f"Filename: {filename}\n\n"
                f"Content:\n{content_preview}"
            ),
        }],
    )
    return response.content[0].text


def extract_questions(text):
    """Extract numbered questions from assistant response."""
    pattern = r"\*{0,2}Question\s+(\d+)\*{0,2}[:\s]*\*{0,2}([^\n*]+)"
    matches = re.findall(pattern, text)
    return [(num, title.strip()) for num, title in matches]


st.set_page_config(page_title="Forge", layout="wide")

# Prevent sidebar expander labels from truncating
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p {
        white-space: normal;
        overflow: visible;
        text-overflow: unset;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Initialize ---
init_session_state()
logger.info("App startup — session initialized")

# --- Sidebar ---
with st.sidebar:
    st.title("Forge")

    # --- Project Management ---
    workspace_dir = ensure_workspace_exists()

    # List existing projects
    existing_projects = sorted(
        [d.name for d in workspace_dir.iterdir() if d.is_dir() and (d / "state.json").exists()],
        key=lambda x: (workspace_dir / x / "state.json").stat().st_mtime,
        reverse=True,
    )

    project_options = ["— Select a project —"] + existing_projects

    selected = st.selectbox("Project", project_options, key="project_selector")

    # New project creation
    col1, col2 = st.columns(2)
    with col1:
        new_name = st.text_input("New project name", key="new_project_name", label_visibility="collapsed", placeholder="New project name...")
    with col2:
        if st.button("Create", use_container_width=True):
            if new_name.strip():
                slug = slugify_project_name(new_name)
                project_dir = workspace_dir / slug
                if project_dir.exists():
                    st.error(f"Project '{slug}' already exists.")
                else:
                    project_dir.mkdir(parents=True)
                    (project_dir / "artifacts").mkdir()
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    init_session_state()
                    st.session_state.project_name = new_name.strip()
                    st.session_state.project_dir = project_dir
                    st.session_state.is_priming_turn = True
                    save_project(project_dir)
                    st.session_state.project_selector = slug
                    st.rerun()

    # Load selected project
    if selected != "— Select a project —":
        project_dir = workspace_dir / selected
        current_dir = getattr(st.session_state, 'project_dir', None)
        if current_dir != project_dir:
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            load_project(project_dir)
            st.session_state.project_state = load_project_state(project_dir)
            st.session_state.project_selector = selected
            st.rerun()

    # Show current project info
    if hasattr(st.session_state, 'project_name') and st.session_state.project_name:
        st.caption(f"Current: **{st.session_state.project_name}**")

    st.divider()

    # --- Project Files ---
    if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        st.subheader("Project Files")

        if not config.VOYAGE_API_KEY:
            st.warning("Set VOYAGE_API_KEY in .env to enable file search.")
        else:
            project_state = st.session_state.project_state
            file_summaries = project_state.get("file_summaries", [])

            # List existing files
            for i, file_info in enumerate(file_summaries):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.caption(f"{file_info['filename']}")
                    summary_preview = file_info["summary"][:100]
                    if len(file_info["summary"]) > 100:
                        summary_preview += "..."
                    st.caption(summary_preview)
                with col2:
                    if st.button("X", key=f"delete_file_{i}"):
                        _delete_file(file_info["filename"])
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

    # Current state indicator
    if st.session_state.active_mode:
        st.success(f"Active Mode: {st.session_state.active_mode.replace('_', ' ').title()}")
    else:
        st.info("Phase: Context Gathering")

    st.metric("Turn", st.session_state.turn_count)

    # Assumption register display
    st.divider()
    st.subheader("Assumptions")
    if st.session_state.assumption_register:
        assumptions = st.session_state.assumption_register

        # Quick summary counts
        total = len(assumptions)
        active = sum(1 for a in assumptions.values() if a["status"] == "active")
        at_risk = sum(1 for a in assumptions.values() if a["status"] == "at_risk")
        guessed = sum(1 for a in assumptions.values() if a["confidence"] == "guessed")

        st.metric("Assumptions", total)

        # Status bar
        col1, col2, col3 = st.columns(3)
        col1.metric("Active", active)
        col2.metric("At Risk", at_risk)
        col3.metric("Guessed", guessed)

        # Expandable detail view
        with st.expander("View All Assumptions", expanded=False):
            for aid, a in sorted(assumptions.items()):
                status_icon = {"active": "🟢", "at_risk": "🟡", "validated": "✅", "invalidated": "❌"}.get(a["status"], "⚪")
                confidence_icon = {"guessed": "❓", "informed": "💡", "validated": "✅"}.get(a["confidence"], "⚪")

                st.markdown(f"**{a['id']}** {status_icon} {a['claim']}")
                st.caption(f"Impact: {a['impact']} | Confidence: {confidence_icon} {a['confidence']} | Action: {a.get('recommended_action', 'None')}")
                if a.get("depends_on"):
                    st.caption(f"Depends on: {', '.join(a['depends_on'])}")
                st.markdown("---")
    else:
        st.caption("No assumptions tracked yet.")

    # Document skeleton display
    st.divider()
    st.subheader("Document Skeleton")
    skeleton = st.session_state.document_skeleton
    if skeleton["problem_statement"]:
        with st.expander("**Problem Statement**", expanded=True):
            st.write(skeleton["problem_statement"])
    if skeleton["stakeholders"]:
        st.write(f"**Stakeholders:** {len(skeleton['stakeholders'])} identified")
    if any(skeleton["success_metrics"].values()):
        st.write("**Metrics:** Defined")

    # Artifact download
    if st.session_state.latest_artifact:
        st.divider()
        st.subheader("Latest Artifact")
        if st.session_state.latest_artifact.startswith("# Solution Evaluation"):
            label = "Download Solution Evaluation"
            filename = "solution_evaluation.md"
        else:
            label = "Download Problem Brief"
            filename = "problem_brief.md"
        st.download_button(
            label=label,
            data=st.session_state.latest_artifact,
            file_name=filename,
            mime="text/markdown",
            use_container_width=True,
        )

    # Assumption register download
    if st.session_state.assumption_register:
        st.divider()
        st.subheader("Assumption Register")

        assumptions = st.session_state.assumption_register

        # JSON download
        st.download_button(
            "Download as JSON",
            data=json.dumps(assumptions, indent=2),
            file_name="assumption_register.json",
            mime="application/json",
            use_container_width=True,
        )

        # CSV download
        csv_buffer = io.StringIO()
        if assumptions:
            first = next(iter(assumptions.values()))
            fieldnames = list(first.keys())
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            for aid, a in sorted(assumptions.items()):
                row = {}
                for k, v in a.items():
                    if isinstance(v, list):
                        row[k] = "; ".join(str(i) for i in v)
                    else:
                        row[k] = v
                writer.writerow(row)

        st.download_button(
            "Download as CSV",
            data=csv_buffer.getvalue(),
            file_name="assumption_register.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Modes roadmap
    st.divider()
    st.subheader("Modes")
    st.write("✅ Mode 1: Discover & Frame")
    st.write("✅ Mode 2: Evaluate Solution")
    st.write("Mode 3: Surface Constraints")
    st.write("Mode 4: Size & Value")
    st.write("Mode 5: Prioritize & Sequence")

# --- Main Chat ---
st.title("Forge")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Priming turn: auto-send context-gathering message for new projects
if st.session_state.get("is_priming_turn") and not st.session_state.messages:
    with st.chat_message("assistant"):
        with st.spinner("Setting up project..."):
            priming_response = run_turn("__PRIMING_TURN__")
        st.markdown(priming_response)
    st.rerun()

# Show question checkboxes if the last assistant response had questions
pending_qs = st.session_state.pending_questions
if pending_qs:
    st.markdown("**Which questions would you like to respond to?**")
    for num, title in pending_qs:
        st.checkbox(
            f"Question {num}: {title}",
            value=True,
            key=f"respond_q{num}",
        )

# Chat input
if user_input := st.chat_input("Describe your problem, opportunity, or idea..."):
    # Build orchestrator input with question selection context
    if pending_qs:
        selected = []
        for num, title in pending_qs:
            if st.session_state.get(f"respond_q{num}", True):
                selected.append(num)
        # Only add context if user deselected some questions
        if selected and len(selected) < len(pending_qs):
            labels = ", ".join(f"Question {n}" for n in selected)
            orchestrator_input = f"[User is responding to {labels}]\n\n{user_input}"
        else:
            orchestrator_input = user_input
        # Clean up checkbox state
        for num, _ in pending_qs:
            st.session_state.pop(f"respond_q{num}", None)
        st.session_state.pending_questions = None
    else:
        orchestrator_input = user_input

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = run_turn(orchestrator_input)
        st.markdown(response)

    # If user selectively responded, store clean version for display history
    if orchestrator_input != user_input:
        # run_turn stored orchestrator_input; replace with clean version
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "user" and msg["content"] == orchestrator_input:
                msg["content"] = user_input
                break

    # Detect questions in new response for next turn's checkboxes
    questions = extract_questions(response)
    st.session_state.pending_questions = questions if questions else None
    st.rerun()
