# Project Forge — Persistence & Workspace Specification

## Document Purpose
This is the build specification for adding local project persistence and workspace management to Project Forge. It covers: project directory structure, state serialization/deserialization, context file management, UI changes, and the priming turn for new projects.

**Dependencies:** Orchestrator + Mode 1 + Mode 2 must be built and working before this.

---

## 0. What This Adds

**Current state:** Everything lives in `st.session_state` and dies on page refresh. No way to resume a session or pre-load team context.

**After this build:**
- Projects are saved to `~/Documents/forge-workspace/projects/` as JSON + markdown files
- Sessions auto-save after every turn — you never lose work
- You can resume a project where you left off (conversation, assumptions, skeleton, everything)
- New projects start with a "priming turn" where Forge asks about team context before problem exploration
- `context.md` can be manually edited between sessions and Forge will pick up changes

**What this does NOT change:**
- No changes to Phase A/B loop mechanics
- No changes to Mode 1 or Mode 2 knowledge bases or probes
- No changes to tool definitions or handlers (except `update_org_context` now also writes to `context.md`)
- No changes to the two-phase orchestrator logic

---

## 1. Project Directory Structure

```
~/Documents/forge-workspace/
└── projects/
    ├── campaign-roi-analysis/
    │   ├── state.json          # Full serialized session state
    │   ├── context.md          # Team/org context (read before every turn, written by update_org_context)
    │   └── artifacts/          # Auto-saved artifacts
    │       ├── problem_brief.md
    │       └── solution_evaluation.md
    └── store-delivery-optimization/
        ├── state.json
        ├── context.md
        └── artifacts/
```

**Location:** `~/Documents/forge-workspace/projects/`. Hardcoded for v1. This directory syncs via OneDrive/SharePoint automatically — Forge does not manage git or any version control for the workspace.

**Directory creation:** The app creates `~/Documents/forge-workspace/projects/` on first run if it doesn't exist.

---

## 2. Project Name Slugification

Users will type names like "Campaign Analysis: Q3 (Final)" or "Bob's Project / v2". These must be converted to safe directory names.

### Slugify Function

```python
import re

def slugify_project_name(name: str) -> str:
    """Convert a project name to a safe directory slug.
    
    'Campaign Analysis: Q3 (Final)' -> 'campaign-analysis-q3-final'
    'Bob's Project / v2' -> 'bobs-project-v2'
    """
    # Lowercase
    slug = name.lower()
    # Replace any non-alphanumeric character (except hyphens and spaces) with nothing
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    # Replace whitespace (one or more) with a single hyphen
    slug = re.sub(r"\s+", "-", slug.strip())
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    # Fallback if empty
    if not slug:
        slug = "untitled-project"
    return slug
```

The display name (what the user typed) is stored inside `state.json` as `project_name`. The slug is only used for the directory name.

---

## 3. State Serialization

### What Gets Saved

Everything in `st.session_state` except `initialized` and UI-transient state. Saved as a single `state.json` file.

```python
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
```

### Schema Version

Every `state.json` includes a version tag at the top level:

```json
{
    "schema_version": "1.0",
    "project_name": "Campaign ROI Analysis",
    "last_saved": "2026-02-16T15:30:00",
    "messages": [...],
    "turn_count": 7,
    ...
}
```

**Version handling on load:** If `schema_version` is missing or doesn't match the current version, show a warning: "This project was created with a different version of Forge. Some features may not work correctly. Consider starting a new project." Do NOT crash. Still attempt merge-on-load.

### Serialize Function

```python
import json
from datetime import datetime
from pathlib import Path

CURRENT_SCHEMA_VERSION = "1.0"

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
    # Write to temp file first, then rename (atomic write prevents corruption)
    temp_file = project_dir / "state.json.tmp"
    with open(temp_file, "w") as f:
        json.dump(state_data, f, indent=2, default=str)
    temp_file.rename(state_file)
```

### Deserialize Function (Merge-on-Load)

```python
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
    
    # First: initialize fresh state with all current defaults
    # This ensures any new fields added in later versions get their defaults
    init_session_state()
    
    # Then: overlay saved data on top
    for key in PERSISTED_KEYS:
        if key in saved_data:
            if key == "document_skeleton":
                # Merge skeleton: keep new default keys, overlay saved values
                default_skeleton = st.session_state.document_skeleton
                saved_skeleton = saved_data[key]
                for sk, sv in saved_skeleton.items():
                    default_skeleton[sk] = sv
                st.session_state.document_skeleton = default_skeleton
            elif key == "routing_context":
                # Same merge strategy for routing_context
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
```

**Why merge for dicts, direct assign for everything else:** `document_skeleton`, `routing_context`, and `org_context` are dicts that grow over time as modes are added. New keys get defaults from `init_session_state()`, old keys get restored from the save file. Lists and scalars (`messages`, `turn_count`, etc.) are replaced entirely.

---

## 4. Context File Management (context.md)

### Read-Before-Write Strategy

`context.md` is the SOURCE OF TRUTH for team/org context. It is:
- **Read from disk** before every Phase A routing call (captures manual edits)
- **Written to** ONLY when `update_org_context` tool is explicitly called
- **Never overwritten** by auto-save of `state.json` (state.json stores org_context separately, but context.md is always re-read)

### Load Context File

```python
def _load_context_file(project_dir: Path) -> None:
    """Read context.md from disk and inject into org_context.internal_context."""
    context_file = project_dir / "context.md"
    if context_file.exists():
        content = context_file.read_text().strip()
        if content:
            st.session_state.org_context["internal_context"] = content
```

This function is called:
1. When a project is loaded (`load_project`)
2. Before every Phase A call (in `run_turn`, before `_run_phase_a`)

### Write Context File

Only happens inside the `_handle_update_org_context` handler. Add this to the existing handler:

```python
def _handle_update_org_context(input: dict) -> str:
    # ... existing logic ...
    
    # Write context.md if we have a project directory
    if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        _write_context_file(st.session_state.project_dir)
    
    return f"Org context updated for {input.get('company', 'unknown')} / {input.get('domain', 'unknown')}"

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
```

### Manual Editing

Users can edit `context.md` in any text editor between sessions. Forge re-reads it before every turn, so changes are picked up automatically. No special sync logic needed.

---

## 5. Artifact Auto-Save

When `generate_artifact` is called, the rendered markdown is also saved to the project's `artifacts/` directory.

Add to `_handle_generate_artifact` (after setting `st.session_state.latest_artifact`):

```python
# Auto-save artifact to project directory
if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
    artifacts_dir = st.session_state.project_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    if artifact_type == "problem_brief":
        filename = "problem_brief.md"
    elif artifact_type == "solution_evaluation_brief":
        filename = "solution_evaluation.md"
    else:
        filename = f"{artifact_type}.md"
    (artifacts_dir / filename).write_text(doc)
```

---

## 6. The Priming Turn (New Project Flow)

### What Happens When a New Project Is Created

1. User clicks "New Project" in sidebar
2. User enters a project name → slugified → directory created
3. `st.session_state` is reset via `init_session_state()`
4. `st.session_state.project_name` and `st.session_state.project_dir` are set
5. `st.session_state.is_priming_turn` is set to `True`
6. Forge sends the priming message (NOT from the user — system-initiated):

> "New project started. Before we dig into a specific problem, give me the lay of the land. Who's the team, what do they do, what systems do they work with, and any politics or context I should know? The more I understand upfront, the better my questions will be."

7. User responds with team context
8. Forge calls `update_org_context` to store it (which also writes `context.md`)
9. Forge responds with: acknowledgment of context + "Now, what problem or opportunity are you exploring?"
10. `st.session_state.is_priming_turn` is set to `False`
11. Normal Mode 1 flow begins from here

### Escape Hatch

If the user says something like "skip, here's my problem" or immediately states a problem instead of team context, Forge should NOT block. It proceeds to normal intake triage with thinner context. The priming turn is a suggestion, not a gate.

### Implementation

This is a prompt change, not an architecture change. Add to `PHASE_B_ORCHESTRATOR_PROMPT`:

```
## New Project Priming (First Turn of New Project Only)
If is_priming_turn is True:
1. Welcome the user to the new project
2. Ask for team/organizational context: team structure, key stakeholders, what everyone does, 
   systems they work with, terminology, objectives, known challenges
3. Frame it as: "The more context I have, the sharper my questions will be"
4. If the user provides context, call update_org_context to store it
5. Then ask: "Got it. Now, what problem or opportunity are you exploring?"
6. If the user skips and jumps straight to a problem, proceed normally — don't re-ask for context

Do NOT ask for the problem statement during the priming turn. Let the user provide context first.
```

Add `is_priming_turn` to the Phase B prompt format variables.

---

## 7. UI Changes (app.py)

### Sidebar — Project Management (Top of Sidebar)

Replace the current sidebar top with:

```python
with st.sidebar:
    st.title("Forge")
    
    # --- Project Management ---
    workspace_dir = Path.home() / "Documents" / "forge-workspace" / "projects"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    # List existing projects
    existing_projects = sorted(
        [d.name for d in workspace_dir.iterdir() if d.is_dir() and (d / "state.json").exists()],
        key=lambda x: (workspace_dir / x / "state.json").stat().st_mtime,
        reverse=True,  # Most recently modified first
    )
    
    # Add "No project" option for fresh start
    project_options = ["— Select a project —"] + existing_projects
    
    # Project selector
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
                    # Reset state for new project
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    init_session_state()
                    st.session_state.project_name = new_name.strip()
                    st.session_state.project_dir = project_dir
                    st.session_state.is_priming_turn = True
                    # Save initial empty state
                    save_project(project_dir)
                    st.rerun()
    
    # Load selected project
    if selected != "— Select a project —":
        project_dir = workspace_dir / selected
        # Only load if we're not already in this project
        current_dir = getattr(st.session_state, 'project_dir', None)
        if current_dir != project_dir:
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            load_project(project_dir)
            st.rerun()
    
    # Show current project info
    if hasattr(st.session_state, 'project_name') and st.session_state.project_name:
        st.caption(f"Current: **{st.session_state.project_name}**")
    
    st.divider()
    # ... rest of existing sidebar (mode status, assumptions, skeleton, downloads, etc.)
```

### Remove "New Session" Button

Replace with the project management UI above. The "New Session" button concept is replaced by "Create" new project.

### Priming Turn Auto-Message

When `is_priming_turn` is True and there are no messages, automatically trigger the priming message:

```python
# After chat history display, before chat input
if st.session_state.get("is_priming_turn") and not st.session_state.messages:
    # Auto-send priming message
    with st.chat_message("assistant"):
        with st.spinner("Setting up project..."):
            # Inject a synthetic "system" trigger to Phase B
            priming_response = run_turn("__PRIMING_TURN__")
        st.markdown(priming_response)
```

In `orchestrator.py`, detect `__PRIMING_TURN__` in `run_turn`:

```python
def run_turn(user_message: str) -> str:
    # Handle priming turn
    if user_message == "__PRIMING_TURN__":
        st.session_state.turn_count += 1
        priming_msg = (
            "New project started. Before we dig into a specific problem, give me the lay of the land.\n\n"
            "Tell me about the team and context for this project:\n"
            "- Who's the team? What does everyone do?\n"
            "- Key stakeholders and decision-makers?\n"
            "- Systems, tools, or data sources they work with?\n"
            "- Any terminology I should know?\n"
            "- Current objectives or priorities?\n"
            "- Known challenges or political dynamics?\n\n"
            "The more context I have upfront, the sharper my diagnostic questions will be. "
            "Or if you'd rather jump straight to the problem, go ahead — we can fill in context as we go."
        )
        st.session_state.messages.append({"role": "assistant", "content": priming_msg})
        st.session_state.is_priming_turn = False
        # Auto-save
        if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
            save_project(st.session_state.project_dir)
        return priming_msg
    
    # ... normal run_turn logic ...
```

---

## 8. Auto-Save Integration

### Where Auto-Save Fires

At the end of `run_turn()`, after `_post_turn_updates()`:

```python
def run_turn(user_message: str) -> str:
    # ... existing logic ...
    
    # --- AUTO-SAVE ---
    if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        save_project(st.session_state.project_dir)
    
    return response_text
```

### Context Re-Read Before Phase A

At the start of `run_turn()`, before `_run_phase_a()`:

```python
def run_turn(user_message: str) -> str:
    st.session_state.turn_count += 1
    st.session_state.messages.append({"role": "user", "content": user_message})
    
    # Re-read context.md to capture manual edits
    if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        _load_context_file(st.session_state.project_dir)
    
    # --- PHASE A: Route ---
    routing_decision = _run_phase_a(user_message)
    # ... rest of turn ...
```

Note: `_load_context_file` is imported from `persistence.py`.

---

## 9. State Changes

### New Session State Fields

Add to `init_session_state()` in `state.py`:

```python
st.session_state.project_name = None       # Display name of current project
st.session_state.project_dir = None        # Path object to project directory
st.session_state.is_priming_turn = False   # True only on first turn of new project
```

These are NOT persisted in `state.json` (project_dir is reconstructed from the directory path on load, project_name IS persisted as metadata).

### PERSISTED_KEYS Update

`project_name` is saved in state.json as metadata but `project_dir` and `is_priming_turn` are NOT saved (they're transient).

---

## 10. File Summary

### New file: `src/pm_copilot/persistence.py`

Contains:
- `WORKSPACE_DIR` constant (`~/Documents/forge-workspace/projects/`)
- `CURRENT_SCHEMA_VERSION` constant
- `PERSISTED_KEYS` list
- `slugify_project_name(name: str) -> str`
- `save_project(project_dir: Path) -> None`
- `load_project(project_dir: Path) -> None`
- `_load_context_file(project_dir: Path) -> None`
- `_write_context_file(project_dir: Path) -> None`
- `ensure_workspace_exists() -> Path` (creates workspace dir if needed, returns path)

### Modified: `src/pm_copilot/state.py`

- Add `project_name`, `project_dir`, `is_priming_turn` to `init_session_state()`

### Modified: `src/pm_copilot/app.py`

- Import from persistence.py
- Replace sidebar top with project management UI (selector, create, load)
- Remove "New Session" button
- Add priming turn auto-message logic
- Remove manual "New Session" reset (replaced by project creation)

### Modified: `src/pm_copilot/orchestrator.py`

- Import `_load_context_file`, `save_project` from persistence
- Add context re-read at start of `run_turn()`
- Add auto-save at end of `run_turn()`
- Add `__PRIMING_TURN__` handling at top of `run_turn()`

### Modified: `src/pm_copilot/tools.py`

- In `_handle_update_org_context`: add call to `_write_context_file` after updating state
- In `_handle_generate_artifact`: add artifact auto-save to project `artifacts/` directory
- Import `_write_context_file` from persistence

### Modified: `src/pm_copilot/prompts.py`

- No prompt changes needed — the priming turn is handled by the `__PRIMING_TURN__` sentinel in orchestrator.py, not by prompt engineering. The existing Turn 1 intake triage in `PHASE_B_ORCHESTRATOR_PROMPT` handles the user's context response naturally (calls `update_org_context`).

---

## 11. Build Sequence for Claude Code (6 Prompts)

### Prompt 0: Absorption (Plan Mode)

```
Read these files and confirm your understanding before we build:
- src/pm_copilot/state.py
- src/pm_copilot/app.py
- src/pm_copilot/orchestrator.py
- src/pm_copilot/tools.py
- docs/specs/persistence-spec.md (this file)

Confirm:
1. You understand the project directory structure
2. You understand merge-on-load for forward compatibility
3. You understand the read-before-write strategy for context.md
4. You understand the priming turn flow
5. You understand where auto-save fires (end of run_turn)
6. You understand where context re-read fires (start of run_turn)
```

### Prompt 1: persistence.py

```
Create src/pm_copilot/persistence.py with ALL functions from the spec:
- WORKSPACE_DIR, CURRENT_SCHEMA_VERSION, PERSISTED_KEYS
- slugify_project_name
- save_project (with atomic write via temp file)
- load_project (with merge-on-load for dicts, direct assign for scalars)
- _load_context_file
- _write_context_file
- ensure_workspace_exists

Make sure:
- save_project uses atomic write (write to .tmp, then rename)
- load_project calls init_session_state() FIRST, then overlays saved data
- load_project merges document_skeleton, routing_context, and org_context as dicts
- load_project shows st.warning for schema version mismatch (don't crash)
- slugify handles colons, slashes, parentheses, apostrophes, unicode
```

### Prompt 2: state.py

```
Add three new fields to init_session_state() in state.py:
- project_name = None
- project_dir = None  
- is_priming_turn = False

These go AFTER the existing fields. Do not change any existing fields.
```

### Prompt 3: orchestrator.py

```
Modify orchestrator.py:

1. Add imports at top:
   from .persistence import save_project, _load_context_file

2. Add __PRIMING_TURN__ handling at the TOP of run_turn(), before any other logic:
   - If user_message == "__PRIMING_TURN__": generate the priming message (from spec), 
     append to messages, set is_priming_turn = False, auto-save, return
   
3. Add context re-read AFTER incrementing turn_count but BEFORE _run_phase_a:
   - If project_dir exists, call _load_context_file(project_dir)
   
4. Add auto-save at the END of run_turn(), after _post_turn_updates:
   - If project_dir exists, call save_project(project_dir)
```

### Prompt 4: tools.py

```
Modify tools.py:

1. Add import at top:
   from pathlib import Path
   from .persistence import _write_context_file

2. In _handle_update_org_context, AFTER the existing logic and BEFORE the return:
   - If st.session_state has project_dir and it's not None, call _write_context_file(project_dir)

3. In _handle_generate_artifact, AFTER setting st.session_state.latest_artifact:
   - If st.session_state has project_dir and it's not None:
     - Create artifacts/ subdirectory if needed
     - Write the artifact to the appropriate filename (problem_brief.md or solution_evaluation.md)
```

### Prompt 5: app.py

```
Modify app.py with the project management UI:

1. Add imports:
   from pathlib import Path
   from pm_copilot.persistence import (
       slugify_project_name, save_project, load_project, ensure_workspace_exists
   )

2. Replace the sidebar top section (before st.divider()) with:
   - Project selector dropdown (reads existing project dirs)
   - New project name input + Create button
   - Current project display
   - See spec Section 7 for exact UI layout

3. Remove the "New Session" button entirely

4. Add priming turn auto-message:
   - After chat history display, before chat input
   - If is_priming_turn is True and no messages exist, auto-trigger __PRIMING_TURN__
   - Display the priming message
   - st.rerun() after to show the message and enable chat input

5. The project load logic must:
   - Clear all session state
   - Call load_project(project_dir) 
   - st.rerun()

6. Project creation must:
   - Validate name is not empty
   - Slugify the name
   - Check if directory already exists (show error if so)
   - Create directory + artifacts subdirectory
   - Reset session state
   - Set project_name, project_dir, is_priming_turn
   - Save initial state
   - st.rerun()
```

---

## 12. Testing Checklist

After building, verify ALL of these:

- [ ] Workspace directory is created at `~/Documents/forge-workspace/projects/` on first run
- [ ] New project creation: type name with special characters → directory created with clean slug
- [ ] New project creation: duplicate name → error message, no crash
- [ ] Priming turn: new project shows context-gathering message automatically
- [ ] Priming turn: user provides team context → stored in org_context AND context.md
- [ ] Priming turn: user skips context and states problem → system proceeds normally
- [ ] Auto-save: send a message, check state.json is updated in project directory
- [ ] Resume: close browser tab, reopen app, select project → conversation resumes with all state
- [ ] Resume: assumptions, skeleton, routing context all restored correctly
- [ ] Resume: conversation history displays correctly
- [ ] Forward compatibility: manually delete a key from state.json, reload → no crash, missing key gets default
- [ ] Schema version: manually change schema_version in state.json → warning shown, project still loads
- [ ] Context manual edit: while app is running, edit context.md in text editor → send next message → Forge sees the updated context
- [ ] Artifact auto-save: generate a problem brief → check artifacts/problem_brief.md exists in project dir
- [ ] Project selector: shows projects sorted by most recently modified
- [ ] Multiple projects: create two projects, switch between them, verify state is independent

---

## 13. Known Limitations

1. **Single user only** — No locking, no multi-user access. If you open two browser tabs on the same project, last-write-wins.
2. **No project deletion from UI** — Delete project directories manually from Finder/terminal.
3. **No project rename from UI** — Rename directories manually. The display name in state.json won't auto-update.
4. **Workspace path is hardcoded** — `~/Documents/forge-workspace/`. Change requires editing persistence.py.
5. **No backup/versioning** — OneDrive/SharePoint sync provides cloud backup. No built-in version history.

---

*Status: SPEC COMPLETE*
*Depends on: Orchestrator + Mode 1 + Mode 2 (all built)*
*Build before: Mode 3*
