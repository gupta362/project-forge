# PM Agents v2 — Claude Code Instructions

## What You're Building

A PM co-pilot system: single orchestrator with dynamically-injected specialized modes. Two-phase-per-turn architecture. First milestone: Orchestrator + Mode 1 (Discover & Frame).

## Reference Documents (Read ALL Before Starting)

1. **`claude-code-implementation-spec-v2.1.md`** — THE BUILD SPEC. Follow it exactly. Contains file structure, data models, tool definitions, prompt templates, orchestrator logic, UI code, and build order.
2. **`orchestrator-spec-v2.1.md`** — Architecture reference. Read for understanding, not for code. The implementation spec already translates this into buildable code.
3. **`mode1-discover-frame-spec-v2.1.md`** — Mode 1 knowledge base. The FULL contents of this file get pasted into `mode1_knowledge.py` as a string. Do not summarize or truncate.

## Critical Implementation Notes

These are the result of a thorough spec review that identified 14 issues. All fixes are already incorporated into the v2.1 specs, but pay extra attention to these:

### Must-Not-Miss Items

1. **`load_dotenv()` before `Anthropic()` client** — in `orchestrator.py`, `from dotenv import load_dotenv; load_dotenv()` must appear before `client = Anthropic()`. Without this, the app crashes immediately.

2. **Phase B records probes and patterns, not Phase A** — The `record_probe_fired` and `record_pattern_fired` tools are called by Phase B. There is NO code in `_post_turn_updates` that infers probes from `routing_decision["suggested_probes"]`. Phase B is the single source of truth for what actually happened.

3. **`generate_artifact` bypasses the model** — In the tool loop in `_run_phase_b`, when the tool is `generate_artifact`, the rendered markdown goes directly to `final_text` and the model receives only `"Artifact rendered and displayed to user."` as the tool_result. The model never sees the full artifact in its context.

4. **Dependency cascade in `_handle_update_assumption_status`** — When an assumption is invalidated, its dependents get flagged as `"at_risk"` (not invalidated). When confirmed, dependent confidence can upgrade from `"guessed"` to `"informed"`. This is application-level logic, not LLM-driven.

5. **Dynamic OrgContext, no static file** — There is NO `org_context.md` file. OrgContext is built dynamically via the `update_org_context` tool. On turn 1, the model populates public context from its own knowledge. The user optionally provides internal context.

6. **`update_conversation_summary` is mandatory every turn** — Both Phase B prompts include an end-of-turn requirement to call this tool. The rolling summary is consumed by Phase A next turn. If the model doesn't call it, routing quality degrades.

7. **`complete_mode` for mode exit** — Phase B calls `complete_mode` after generating the final artifact. Phase A has a fallback safety net. Both reset `current_phase` to `"gathering"` and `active_mode` to `None`. They do NOT reset the assumption register or document skeleton.

### Architecture Principles

- **Phase A decides WHAT should happen. Phase B decides WHAT ACTUALLY HAPPENS and records it.** Never trust Phase A's suggestions as execution records.
- **LLM decides WHAT to update. Application decides HOW.** All state mutations go through tool handlers. The model never directly writes to session state.
- **Error handling is graceful, not sophisticated.** Wrap API calls in try/except. Show user-friendly messages. Preserve state. Don't crash, don't show stack traces.

## Build Order

Follow the build order in Section 12 of the implementation spec exactly:

1. **Scaffold (30 min)** — Create all files with stubs, verify streamlit runs
2. **Basic Chat Loop (1 hour)** — Phase B only, skip Phase A, verify tool calls work
3. **Phase A Routing (1 hour)** — Add routing, wire two-phase flow
4. **OrgContext + Mode 1 KB (1.5 hours)** — Dynamic org context + full knowledge base
5. **Mode Completion + Artifacts (1 hour)** — Artifact rendering, download button, mode exit
6. **E2E Testing (1-2 hours)** — Three test scenarios, verify all 14 fixes

## Package Management

Use `uv`, not `pip`. Dependencies:
```
streamlit>=1.30.0
anthropic>=0.40.0
python-dotenv>=1.0.0
```

## Style

- Procedural Python. Flat file structure. No nested packages.
- No dataclasses, no Pydantic. Plain dicts.
- No LangGraph in v1. Direct Anthropic API calls.
- Comments should explain WHY, not WHAT.

## Testing Checklist

After building, verify ALL of these:

- [ ] App starts without crash (`streamlit run app.py`)
- [ ] First turn: model calls `update_org_context` with company knowledge
- [ ] First turn: model offers user chance to add internal context
- [ ] Probes appear in `routing_context["probes_fired"]` via tool call
- [ ] Patterns appear in `routing_context["patterns_fired"]` via tool call
- [ ] `conversation_summary` updates every turn
- [ ] Phase A receives: original_input + conversation_summary + recent messages + assumption summary
- [ ] Mode entry works: Phase A sets `enter_mode`, system transitions
- [ ] Dependency cascade: invalidate an assumption, check dependents become `at_risk`
- [ ] Artifact renders in chat (not relayed by model)
- [ ] Download button appears in sidebar after artifact generation
- [ ] `complete_mode` returns system to gathering
- [ ] Error handling: set bad API key, verify graceful message instead of crash
- [ ] Context truncation: verify long conversations don't crash
