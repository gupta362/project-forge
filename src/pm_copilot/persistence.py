"""Project persistence — save/load session state to local workspace."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

from .state import init_session_state

logger = logging.getLogger("forge.persistence")

WORKSPACE_DIR = Path.home() / "Documents" / "forge-workspace" / "projects"

CURRENT_SCHEMA_VERSION = "1.0"

PERSISTED_KEYS = [
    "messages",
    "turn_count",
    "current_phase",
    "active_mode",
    "assumption_register",
    "assumption_counter",
    "document_skeleton",
    "routing_context",
    "org_context",
    "latest_artifact",
    "pending_questions",
]


def ensure_workspace_exists() -> Path:
    """Create the workspace directory if it doesn't exist and return its path."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Workspace directory ensured at %s", WORKSPACE_DIR)
    return WORKSPACE_DIR


def slugify_project_name(name: str) -> str:
    """Convert a project name to a safe directory slug.

    'Campaign Analysis: Q3 (Final)' -> 'campaign-analysis-q3-final'
    'Bob's Project / v2' -> 'bobs-project-v2'
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        slug = "untitled-project"
    return slug


def save_project(project_dir: Path) -> None:
    """Serialize current session state to project directory."""
    state_data = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project_name": st.session_state.get("project_name", "Untitled"),
        "last_saved": datetime.now().isoformat(),
    }
    for key in PERSISTED_KEYS:
        if key in st.session_state:
            state_data[key] = st.session_state[key]

    state_file = project_dir / "state.json"
    temp_file = project_dir / "state.json.tmp"
    with open(temp_file, "w") as f:
        json.dump(state_data, f, indent=2, default=str)
    temp_file.rename(state_file)
    logger.info("Project saved to %s", state_file)


def load_project(project_dir: Path) -> None:
    """Load project state, merging with current defaults for forward compatibility."""
    state_file = project_dir / "state.json"
    if not state_file.exists():
        return

    with open(state_file, "r") as f:
        saved_data = json.load(f)

    # Check schema version
    saved_version = saved_data.get("schema_version", "unknown")
    if saved_version != CURRENT_SCHEMA_VERSION:
        st.warning(
            f"This project was saved with schema version {saved_version} "
            f"(current: {CURRENT_SCHEMA_VERSION}). Some features may not work correctly."
        )

    # Initialize fresh state with all current defaults
    init_session_state()

    # Overlay saved data on top
    for key in PERSISTED_KEYS:
        if key in saved_data:
            if key == "document_skeleton":
                default_skeleton = st.session_state.document_skeleton
                saved_skeleton = saved_data[key]
                for sk, sv in saved_skeleton.items():
                    default_skeleton[sk] = sv
                st.session_state.document_skeleton = default_skeleton
            elif key == "routing_context":
                default_rc = st.session_state.routing_context
                saved_rc = saved_data[key]
                for rk, rv in saved_rc.items():
                    default_rc[rk] = rv
                st.session_state.routing_context = default_rc
            elif key == "org_context":
                default_oc = st.session_state.org_context
                saved_oc = saved_data[key]
                for ok, ov in saved_oc.items():
                    default_oc[ok] = ov
                st.session_state.org_context = default_oc
            else:
                st.session_state[key] = saved_data[key]

    # Store metadata
    st.session_state.project_name = saved_data.get("project_name", "Untitled")
    st.session_state.project_dir = project_dir

    # Load context.md into org_context if it exists
    _load_context_file(project_dir)
    logger.info("Project loaded from %s", state_file)


def _load_context_file(project_dir: Path) -> None:
    """Read context.md from disk and inject into org_context.internal_context."""
    context_file = project_dir / "context.md"
    if context_file.exists():
        content = context_file.read_text().strip()
        if content:
            st.session_state.org_context["internal_context"] = content


def _write_context_file(project_dir: Path) -> None:
    """Write current org context to context.md."""
    ctx = st.session_state.org_context
    parts = []
    if ctx["company"]:
        parts.append(f"# {ctx['company']}\n")
    if ctx["public_context"]:
        parts.append(f"## Public Context\n{ctx['public_context']}\n")
    if ctx["internal_context"]:
        parts.append(f"## Internal Context\n{ctx['internal_context']}\n")

    context_file = project_dir / "context.md"
    context_file.write_text("\n".join(parts))
