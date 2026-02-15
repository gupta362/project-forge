# PM Agents v2 — Build Status & Document Manifest

## Purpose
This is the single source of truth for what's been built, what's next, and where every build document lives. Commit this to the repo root as `docs/BUILD-STATUS.md`.

---

## Current State

| Component | Status | Last Updated |
|-----------|--------|-------------|
| Orchestrator (two-phase architecture) | ✅ Built & tested | Feb 2025 |
| Mode 1: Discover & Frame | ✅ Built & tested | Feb 2025 |
| Mode 2: Evaluate Solution | 📋 Spec finalized v1.1, ready to build | Feb 15 2025 |
| UI Improvements (download buttons, assumption display) | 📋 Spec ready, build after Mode 2 | Feb 15 2025 |
| Mode 3-5 | 🔲 Not started | — |
| Enterprise integrations (Confluence, SharePoint) | 🔲 Not started | — |
| Multi-user auth / persistence | 🔲 Not started | — |

---

## Document Manifest

### What goes in `docs/` — BUILD DOCUMENTS ONLY

These are the documents you need to build and maintain the system. No explainers, no historical artifacts, no status reports.

#### Specifications (the WHAT and WHY)

| File | Repo Path | Description |
|------|-----------|-------------|
| orchestrator-spec.md | `docs/specs/orchestrator-spec.md` | Orchestrator architecture: two-phase loop, state management, routing logic, context handling. v2.1 with all 14 spec review fixes. |
| mode1-spec.md | `docs/specs/mode1-spec.md` | Mode 1 knowledge base: 7 diagnostic probes, 8 domain patterns, trigger conditions, completion criteria, behavioral rules. v2.1. Also pasted into `mode1_knowledge.py`. |
| mode2-spec.md | `docs/specs/mode2-spec.md` | Mode 2 knowledge base: 7 solution-evaluation probes, 5 domain patterns, three-layer risk identification, semantic tools, artifact structure. v1.1 (post-engineering review). Also pasted into `mode2_knowledge.py`. |
| implementation-spec.md | `docs/specs/implementation-spec.md` | The BIG build spec for Orchestrator + Mode 1. File structure, data models, tool definitions with exact code, prompt templates, Streamlit UI, session management. This is what Claude Code builds from. v2.1. |

#### Build Guides (the HOW)

| File | Repo Path | Description |
|------|-----------|-------------|
| mode1-instructions.md | `docs/build/mode1-instructions.md` | Claude Code operating instructions for Orchestrator + Mode 1 build. Critical implementation notes, architecture principles, build order, testing checklist. |
| mode1-prompts.md | `docs/build/mode1-prompts.md` | Step-by-step prompts to feed Claude Code for Mode 1 build. 7 prompts (Prompt 0-6). |
| mode2-instructions.md | `docs/build/mode2-instructions.md` | Claude Code operating instructions for Mode 2 build. File-by-file changes, exact code, 4 semantic tools, artifact renderer, testing scenarios. |
| mode2-prompts.md | `docs/build/mode2-prompts.md` | Step-by-step prompts to feed Claude Code for Mode 2 build. 6 prompts (Prompt 0-5). |
| ui-improvements.md | `docs/build/ui-improvements.md` | Post-Mode-2 UI improvements: assumption register download, improved display, input sandboxing. |

#### Tracking

| File | Repo Path | Description |
|------|-----------|-------------|
| BUILD-STATUS.md | `docs/BUILD-STATUS.md` | THIS FILE. Master tracking document. |

---

## File Mapping: Outputs → Repo

Use this table to copy files from the delivery outputs into your repo with clean names.

| Output File Name | Copy To Repo As |
|-----------------|----------------|
| `orchestrator-spec-v3.md` | `docs/specs/orchestrator-spec.md` |
| `mode1-discover-frame-spec-v3.md` | `docs/specs/mode1-spec.md` |
| `mode2-evaluate-solution-spec.md` | `docs/specs/mode2-spec.md` |
| `claude-code-implementation-spec-updated.md` | `docs/specs/implementation-spec.md` |
| `claude-code-instructions.md` | `docs/build/mode1-instructions.md` |
| `claude-code-prompts.md` | `docs/build/mode1-prompts.md` |
| `mode2-claude-code-instructions.md` | `docs/build/mode2-instructions.md` |
| `mode2-claude-code-prompts.md` | `docs/build/mode2-prompts.md` |
| `ui-improvements.md` | `docs/build/ui-improvements.md` |
| `BUILD-STATUS.md` | `docs/BUILD-STATUS.md` |

---

## What does NOT go in `docs/`

These files were created during design sessions but are NOT build documents. They're reference/explainer material. Keep them separately or discard.

| File | What It Is | Keep? |
|------|-----------|-------|
| `pm-agents-explainer-v2*.jsx` | Interactive visual explainer of the architecture | Optional — useful for onboarding, not for building |
| `design-decisions-tuning-map.md` | Record of 14 spec review decisions and rationale | Optional — historical reference |
| `pm-agents-v2-status.md` | Earlier status report | Superseded by BUILD-STATUS.md |
| `pm-agents-v2-tuning-map.md` | Earlier tuning map | Superseded by design-decisions-tuning-map.md |

---

## Repo Structure After Copying

```
pm-agents-v2/
├── src/
│   └── pm_copilot/
│       ├── app.py
│       ├── config.py
│       ├── orchestrator.py
│       ├── org_context.py
│       ├── prompts.py
│       ├── state.py
│       ├── tools.py
│       ├── mode1_knowledge.py      ← contents of mode1-spec.md as string
│       └── mode2_knowledge.py      ← contents of mode2-spec.md as string (Mode 2 build)
├── docs/
│   ├── BUILD-STATUS.md             ← THIS FILE
│   ├── specs/
│   │   ├── orchestrator-spec.md
│   │   ├── mode1-spec.md
│   │   ├── mode2-spec.md
│   │   └── implementation-spec.md
│   └── build/
│       ├── mode1-instructions.md
│       ├── mode1-prompts.md
│       ├── mode2-instructions.md
│       ├── mode2-prompts.md
│       └── ui-improvements.md
├── .env
├── pyproject.toml
└── CLAUDE.md
```

---

## Build Sequence

### Phase 1: Orchestrator + Mode 1 ✅ COMPLETE
**Docs used:** `implementation-spec.md` + `mode1-instructions.md` + `mode1-prompts.md`
**Specs referenced:** `orchestrator-spec.md` + `mode1-spec.md`

### Phase 2: Mode 2 — NEXT
**Docs to use:** `mode2-instructions.md` + `mode2-prompts.md`
**Specs referenced:** `mode2-spec.md`
**Pre-req:** Switch config.py from Haiku to Sonnet before testing

### Phase 3: UI Improvements — AFTER Mode 2
**Docs to use:** `ui-improvements.md`
**What it adds:** Assumption register download (JSON + CSV), improved sidebar display, input sandboxing for large pastes, file upload widget

### Phase 4: Modes 3-5 — FUTURE
**Specs:** Not yet written
**Pattern:** Same as Mode 2 — spec first, then build instructions + prompts

### Phase 5: Enterprise — FUTURE
**What:** Multi-user auth, persistent storage, Confluence/SharePoint integration
**Framework change:** Streamlit → FastAPI + React (when user count exceeds ~10)

---

## Version History

| Date | Change |
|------|--------|
| Feb 8-9, 2025 | Orchestrator + Mode 1 specs finalized (v2.1) with 14 spec review fixes |
| Feb 9, 2025 | Mode 1 build instructions + prompts created |
| Feb 15, 2025 | Mode 2 spec drafted and finalized (v1.1 post-engineering review) |
| Feb 15, 2025 | Mode 2 build instructions + prompts created |
| Feb 15, 2025 | UI improvements spec created |
| Feb 15, 2025 | BUILD-STATUS.md created — master tracking document |
