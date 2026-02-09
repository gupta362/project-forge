# PM Agents v2 — Claude Code Implementation Spec
## Orchestrator + Mode 1: Discover & Frame

### Document Purpose
This is the build specification for Claude Code. It contains everything needed to implement the Orchestrator + Mode 1 system: file structure, data models, tool implementations, prompt templates, Streamlit UI, and session management. Build exactly what's described here.

**Changelog v2.1 (post spec review — 14 items):**
- Bug #1: Added load_dotenv() before Anthropic client init
- Bug #2: Added record_pattern_fired tool (Phase B records patterns, not inferred)
- Bug #2b: Added record_probe_fired tool (Phase B records probes, not Phase A suggestions)
- Arch #3: Added rolling conversation_summary written by Phase B, consumed by Phase A
- Arch #5: Added dependency cascade logic to update_assumption_status handler
- #6: Phase A latency accepted for v1, noted in known limitations
- #7: generate_artifact output bypasses model — rendered directly to user
- #8: Added complete_mode tool + Phase A fallback for mode exit
- #9: Added turn_count and mode_turn_count to Phase B prompts
- #10: Probe completion criteria referenced in record_probe_fired
- #11: Domain pattern checking changed from final-turn-only to every-turn with discipline
- #12: OrgContext replaced with dynamic enrichment (model knowledge + optional user input)
- #13: Added error handling around all API calls + context window safety
- #14: Added artifact download button in sidebar

### Reference Documents
- `orchestrator-spec-v2.md` — Full orchestrator design spec (architecture, routing, state management, transitions)
- `mode1-discover-frame-spec-v2.md` — Full Mode 1 knowledge base (probes, patterns, output structure)

---

## 1. Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| LLM | Claude (Anthropic API) | Use `claude-sonnet-4-20250514` for both phases |
| Frontend | Streamlit | Chat interface + sidebar |
| Language | Python 3.11+ | Procedural style, minimal OOP |
| State | Python dicts in Streamlit session_state | No database needed for v1 |
| Package Manager | uv | Not pip |

### API Configuration
```python
# .env file
ANTHROPIC_API_KEY=your_key_here
```

---

## 2. File Structure

Flat structure. No nested packages, no abstract base classes, no framework patterns.

```
pm-agents-v2/
├── app.py                    # Streamlit entry point, UI layout, chat loop
├── orchestrator.py           # Phase A (routing) + Phase B (execution) logic
├── state.py                  # State objects: assumption register, document skeleton
├── tools.py                  # Tool function implementations (called by LLM)
├── prompts.py                # All prompt templates (orchestrator, mode 1, system)
├── mode1_knowledge.py        # Mode 1 knowledge base text (probes, patterns, output structure)
├── org_context.py            # OrgContext helper — formats dynamic org context for prompts
├── config.py                 # Model names, token limits, other constants
├── .env                      # API key
└── requirements.txt          # Dependencies
```

**Why flat:** Abhisek prefers simple, comprehensible code. Every file has one job. No hunting through nested directories.

---

## 3. Data Models (`state.py`)

All state is plain Python dicts stored in `st.session_state`. No Pydantic, no dataclasses — just dicts with clear key names.

### 3.1 Session State Structure

```python
def init_session_state():
    """Call once at app startup. Sets up all state containers."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.messages = []  # Chat history: [{"role": "user"/"assistant", "content": "..."}]
        st.session_state.turn_count = 0
        st.session_state.current_phase = "gathering"  # "gathering" | "mode_active"
        st.session_state.active_mode = None  # None | "mode_1" | "mode_2" etc.
        st.session_state.assumption_register = {}  # keyed by assumption_id
        st.session_state.assumption_counter = 0  # For generating IDs
        st.session_state.document_skeleton = {
            "problem_statement": None,
            "target_audience": None,
            "stakeholders": {},  # keyed by stakeholder_id
            "stakeholder_counter": 0,
            "success_metrics": {"leading": None, "lagging": None, "anti_metric": None},
            "decision_criteria": {"proceed_if": [], "do_not_proceed_if": []},
            "value_estimate": None,
            "constraints": [],
            "proposed_solution": None,
            "prioritization_rationale": None,
        }
        st.session_state.routing_context = {
            "last_routing_decision": None,
            "probes_fired": [],  # Track which Mode 1 probes have been used (written by Phase B via tool)
            "patterns_fired": [],  # Track which domain patterns have triggered (written by Phase B via tool)
            "micro_synthesis_due": False,
            "critical_mass_reached": False,
            "conversation_summary": "",  # Rolling summary written by Phase B after each turn (#3)
            "mode_turn_count": 0,  # Turns since current mode was entered (#9)
        }
        st.session_state.org_context = {  # Dynamic enrichment (#12)
            "company": None,           # Detected company name
            "public_context": "",      # Model-knowledge-based public context
            "internal_context": "",    # User-provided internal details
            "last_enriched_domain": "",  # What domain/area the last enrichment covered
            "enrichment_count": 0,     # How many times we've enriched (cap at 3)
        }
        st.session_state.latest_artifact = None  # Rendered markdown from generate_artifact (#14)
```

### 3.2 Assumption Schema

Each assumption in the register:

```python
{
    "id": "A1",
    "claim": "Campaign budget allocation is suboptimal",
    "type": "value",  # value | technical | stakeholder_dependency | market | organizational
    "impact": "high",  # high | medium | low
    "confidence": "guessed",  # validated | informed | guessed
    "status": "active",  # active | at_risk | invalidated | confirmed
    "basis": "Implied by user's problem statement",
    "surfaced_by": "Mode 1: Probe 1",
    "depends_on": [],  # list of assumption IDs
    "dependents": [],  # populated automatically when other assumptions reference this one
    "recommended_action": "Validate with campaign managers",
    "implied_stakeholders": [],
    "created_turn": 3,
    "last_updated_turn": 3,
}
```

### 3.3 Stakeholder Schema

```python
{
    "id": "S1",
    "name": "Store Operations",
    "type": "execution_dependency",  # decision_authority | pain_holder | status_quo_beneficiary | execution_dependency
    "validated": False,
    "notes": "Must validate if solution requires store-level changes",
}
```

---

## 4. Tool Implementations (`tools.py`)

These are Python functions that the LLM calls via Anthropic's tool use. They mutate `st.session_state` directly.

**Important:** These are NOT LangGraph tools. They are Anthropic API tool definitions passed to the model, with Python handler functions that execute when the model calls them.

### 4.1 Tool Definitions (for Anthropic API)

```python
TOOL_DEFINITIONS = [
    {
        "name": "register_assumption",
        "description": "Register a new assumption discovered during analysis. Call this whenever you identify something that is being assumed but not validated.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim": {"type": "string", "description": "The specific assumption being made"},
                "type": {"type": "string", "enum": ["value", "technical", "stakeholder_dependency", "market", "organizational"]},
                "impact": {"type": "string", "enum": ["high", "medium", "low"],
                           "description": "High = if wrong, changes whether you'd pursue at all. Medium = changes approach. Low = refines details."},
                "confidence": {"type": "string", "enum": ["validated", "informed", "guessed"]},
                "basis": {"type": "string", "description": "Where this assumption came from"},
                "surfaced_by": {"type": "string", "description": "Which probe or pattern identified this (e.g. 'Mode 1: Probe 1')"},
                "depends_on": {"type": "array", "items": {"type": "string"}, "description": "IDs of assumptions this depends on", "default": []},
                "recommended_action": {"type": "string", "description": "What to do about this assumption", "default": ""},
                "implied_stakeholders": {"type": "array", "items": {"type": "string"}, "description": "Stakeholders implied by this assumption", "default": []},
            },
            "required": ["claim", "type", "impact", "confidence", "basis", "surfaced_by"],
        },
    },
    {
        "name": "update_assumption_status",
        "description": "Update the status of an existing assumption (e.g., when new information confirms or invalidates it).",
        "input_schema": {
            "type": "object",
            "properties": {
                "assumption_id": {"type": "string"},
                "new_status": {"type": "string", "enum": ["active", "at_risk", "invalidated", "confirmed"]},
                "reason": {"type": "string"},
            },
            "required": ["assumption_id", "new_status", "reason"],
        },
    },
    {
        "name": "update_assumption_confidence",
        "description": "Update the confidence level of an existing assumption.",
        "input_schema": {
            "type": "object",
            "properties": {
                "assumption_id": {"type": "string"},
                "new_confidence": {"type": "string", "enum": ["validated", "informed", "guessed"]},
                "reason": {"type": "string"},
            },
            "required": ["assumption_id", "new_confidence", "reason"],
        },
    },
    {
        "name": "update_problem_statement",
        "description": "Set or update the problem statement in the document skeleton.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "update_target_audience",
        "description": "Set or update the target audience.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "add_stakeholder",
        "description": "Add a stakeholder to the document skeleton.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ["decision_authority", "pain_holder", "status_quo_beneficiary", "execution_dependency"]},
                "validated": {"type": "boolean", "default": False},
                "notes": {"type": "string", "default": ""},
            },
            "required": ["name", "type"],
        },
    },
    {
        "name": "update_success_metrics",
        "description": "Set or update success metrics. Only include the fields you want to change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "leading": {"type": "string"},
                "lagging": {"type": "string"},
                "anti_metric": {"type": "string"},
            },
        },
    },
    {
        "name": "add_decision_criteria",
        "description": "Add a proceed/don't-proceed criterion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "criteria_type": {"type": "string", "enum": ["proceed_if", "do_not_proceed_if"]},
                "condition": {"type": "string", "description": "Specific, measurable condition"},
            },
            "required": ["criteria_type", "condition"],
        },
    },
    {
        "name": "generate_artifact",
        "description": "Render the current document skeleton into a formatted artifact. Call this when the user asks for a deliverable or when a mode completes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_type": {"type": "string", "enum": ["problem_brief"]},
            },
            "required": ["artifact_type"],
        },
    },
    {
        "name": "record_pattern_fired",
        "description": "Record that a domain pattern has been evaluated and triggered. Call this whenever a domain pattern's trigger conditions are met and you incorporate it into analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern_name": {"type": "string", "description": "Pattern identifier (e.g. 'Pattern 1: Analytics-Execution Gap')"},
                "trigger_reason": {"type": "string", "description": "Brief explanation of why the trigger conditions were met"},
            },
            "required": ["pattern_name", "trigger_reason"],
        },
    },
    {
        "name": "record_probe_fired",
        "description": "Record that a diagnostic probe has been executed this turn. Call this when you actively explore a probe's questions with the user. Assess whether the probe's completion criteria are satisfied or still open.",
        "input_schema": {
            "type": "object",
            "properties": {
                "probe_name": {"type": "string", "description": "Probe identifier (e.g. 'Probe 1: Solution-Problem Separation')"},
                "summary": {"type": "string", "description": "What was learned AND whether the probe's completion criteria are satisfied or still open"},
            },
            "required": ["probe_name"],
        },
    },
    {
        "name": "update_conversation_summary",
        "description": "Update the rolling conversation summary. Call this at the END of every turn with a 2-3 sentence summary of: what has been established so far, what key open questions remain, and what changed this turn.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "2-3 sentence cumulative summary of conversation state"},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "complete_mode",
        "description": "Signal that the current mode's work is complete. Call this after generating the final artifact and providing closing recommendations. This returns the system to context gathering for the next problem or mode.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode_completed": {"type": "string", "description": "Which mode just completed (e.g. 'mode_1')"},
                "summary": {"type": "string", "description": "Brief summary of what was accomplished"},
            },
            "required": ["mode_completed", "summary"],
        },
    },
    {
        "name": "update_org_context",
        "description": "Update the organizational context. Call on the first turn to capture public knowledge about the company/domain, and when the user provides internal context. Can also be called when the problem domain shifts materially.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Company or organization name"},
                "public_context": {"type": "string", "description": "Public knowledge about the company, org structure, competitive landscape, relevant history"},
                "internal_context": {"type": "string", "description": "User-provided internal details (append to existing)"},
                "domain": {"type": "string", "description": "The domain/functional area this context covers"},
            },
            "required": ["company", "domain"],
        },
    },
]
```

### 4.2 Tool Handler Functions

```python
import streamlit as st


def handle_tool_call(tool_name: str, tool_input: dict) -> str:
    """Route a tool call to the appropriate handler. Returns result string."""
    handlers = {
        "register_assumption": _handle_register_assumption,
        "update_assumption_status": _handle_update_assumption_status,
        "update_assumption_confidence": _handle_update_assumption_confidence,
        "update_problem_statement": _handle_update_problem_statement,
        "update_target_audience": _handle_update_target_audience,
        "add_stakeholder": _handle_add_stakeholder,
        "update_success_metrics": _handle_update_success_metrics,
        "add_decision_criteria": _handle_add_decision_criteria,
        "generate_artifact": _handle_generate_artifact,
        "record_pattern_fired": _handle_record_pattern_fired,
        "record_probe_fired": _handle_record_probe_fired,
        "update_conversation_summary": _handle_update_conversation_summary,
        "complete_mode": _handle_complete_mode,
        "update_org_context": _handle_update_org_context,
    }
    handler = handlers.get(tool_name)
    if handler:
        return handler(tool_input)
    return f"Unknown tool: {tool_name}"


def _handle_register_assumption(input: dict) -> str:
    st.session_state.assumption_counter += 1
    aid = f"A{st.session_state.assumption_counter}"
    assumption = {
        "id": aid,
        "claim": input["claim"],
        "type": input["type"],
        "impact": input["impact"],
        "confidence": input["confidence"],
        "status": "active",
        "basis": input["basis"],
        "surfaced_by": input["surfaced_by"],
        "depends_on": input.get("depends_on", []),
        "dependents": [],
        "recommended_action": input.get("recommended_action", ""),
        "implied_stakeholders": input.get("implied_stakeholders", []),
        "created_turn": st.session_state.turn_count,
        "last_updated_turn": st.session_state.turn_count,
    }
    # Wire up dependency graph
    for dep_id in assumption["depends_on"]:
        if dep_id in st.session_state.assumption_register:
            st.session_state.assumption_register[dep_id]["dependents"].append(aid)
    st.session_state.assumption_register[aid] = assumption
    return f"Registered assumption {aid}: {input['claim']}"


def _handle_update_assumption_status(input: dict) -> str:
    aid = input["assumption_id"]
    if aid not in st.session_state.assumption_register:
        return f"Assumption {aid} not found"
    assumption = st.session_state.assumption_register[aid]
    assumption["status"] = input["new_status"]
    assumption["last_updated_turn"] = st.session_state.turn_count

    # Dependency cascade (#5)
    cascade_results = []
    if input["new_status"] == "invalidated":
        for dep_id in assumption.get("dependents", []):
            dep = st.session_state.assumption_register.get(dep_id)
            if dep and dep["status"] == "active":
                dep["status"] = "at_risk"
                dep["basis"] += f"\n⚠️ Dependency {aid} was invalidated: {input['reason']}"
                dep["last_updated_turn"] = st.session_state.turn_count
                cascade_results.append(f"{dep_id} flagged as at_risk")
    elif input["new_status"] == "confirmed":
        for dep_id in assumption.get("dependents", []):
            dep = st.session_state.assumption_register.get(dep_id)
            if dep and dep["confidence"] == "guessed":
                dep["confidence"] = "informed"
                dep["last_updated_turn"] = st.session_state.turn_count
                cascade_results.append(f"{dep_id} confidence upgraded to informed")

    result = f"Updated {aid} status to {input['new_status']}: {input['reason']}"
    if cascade_results:
        result += f"\nCascade: {'; '.join(cascade_results)}"
    return result


def _handle_update_assumption_confidence(input: dict) -> str:
    aid = input["assumption_id"]
    if aid not in st.session_state.assumption_register:
        return f"Assumption {aid} not found"
    st.session_state.assumption_register[aid]["confidence"] = input["new_confidence"]
    st.session_state.assumption_register[aid]["last_updated_turn"] = st.session_state.turn_count
    return f"Updated {aid} confidence to {input['new_confidence']}: {input['reason']}"


def _handle_update_problem_statement(input: dict) -> str:
    st.session_state.document_skeleton["problem_statement"] = input["text"]
    return "Problem statement updated"


def _handle_update_target_audience(input: dict) -> str:
    st.session_state.document_skeleton["target_audience"] = input["text"]
    return "Target audience updated"


def _handle_add_stakeholder(input: dict) -> str:
    st.session_state.document_skeleton["stakeholder_counter"] += 1
    sid = f"S{st.session_state.document_skeleton['stakeholder_counter']}"
    st.session_state.document_skeleton["stakeholders"][sid] = {
        "id": sid,
        "name": input["name"],
        "type": input["type"],
        "validated": input.get("validated", False),
        "notes": input.get("notes", ""),
    }
    return f"Added stakeholder {sid}: {input['name']}"


def _handle_update_success_metrics(input: dict) -> str:
    metrics = st.session_state.document_skeleton["success_metrics"]
    if "leading" in input:
        metrics["leading"] = input["leading"]
    if "lagging" in input:
        metrics["lagging"] = input["lagging"]
    if "anti_metric" in input:
        metrics["anti_metric"] = input["anti_metric"]
    return "Success metrics updated"


def _handle_add_decision_criteria(input: dict) -> str:
    criteria_type = input["criteria_type"]
    st.session_state.document_skeleton["decision_criteria"][criteria_type].append(input["condition"])
    return f"Added {criteria_type}: {input['condition']}"


def _handle_generate_artifact(input: dict) -> str:
    """Render current state into formatted document. Returns the rendered markdown."""
    skeleton = st.session_state.document_skeleton
    assumptions = st.session_state.assumption_register

    # Build assumption table rows
    assumption_rows = ""
    for aid, a in sorted(assumptions.items()):
        if a["status"] in ("active", "at_risk"):
            assumption_rows += f"| {a['id']} | {a['claim']} | {a['impact']} | {a['confidence']} | {a['status']} |\n"

    # Build stakeholder list
    stakeholder_text = ""
    for sid, s in skeleton["stakeholders"].items():
        validated = "✅" if s["validated"] else "⬜"
        stakeholder_text += f"- {validated} **{s['name']}** ({s['type']}): {s['notes']}\n"

    # Build decision criteria
    proceed = "\n".join(f"- {c}" for c in skeleton["decision_criteria"]["proceed_if"])
    do_not = "\n".join(f"- {c}" for c in skeleton["decision_criteria"]["do_not_proceed_if"])

    # Build metrics
    metrics = skeleton["success_metrics"]
    metrics_text = ""
    if metrics["leading"]:
        metrics_text += f"- **Leading:** {metrics['leading']}\n"
    if metrics["lagging"]:
        metrics_text += f"- **Lagging:** {metrics['lagging']}\n"
    if metrics["anti_metric"]:
        metrics_text += f"- **Anti-metric:** {metrics['anti_metric']}\n"

    doc = f"""# Problem Brief

## Problem Statement
{skeleton['problem_statement'] or '_Not yet defined_'}

## Target Audience
{skeleton['target_audience'] or '_Not yet defined_'}

## Stakeholders
{stakeholder_text or '_None identified yet_'}

## Key Assumptions

| ID | Claim | Impact | Confidence | Status |
|----|-------|--------|------------|--------|
{assumption_rows or '| — | No assumptions registered yet | — | — | — |'}

## Success Metrics
{metrics_text or '_Not yet defined_'}

## Decision Criteria

**Worth pursuing IF:**
{proceed or '_Not yet defined_'}

**Do NOT invest IF:**
{do_not or '_Not yet defined_'}
"""
    st.session_state.latest_artifact = doc  # Store for download button (#14)
    return doc


def _handle_record_pattern_fired(input: dict) -> str:
    """Record that a domain pattern triggered (#2)."""
    st.session_state.routing_context["patterns_fired"].append({
        "name": input["pattern_name"],
        "reason": input["trigger_reason"],
        "turn": st.session_state.turn_count,
    })
    return f"Recorded pattern fired: {input['pattern_name']}"


def _handle_record_probe_fired(input: dict) -> str:
    """Record that a probe was executed (#2b)."""
    st.session_state.routing_context["probes_fired"].append({
        "name": input["probe_name"],
        "summary": input.get("summary", ""),
        "turn": st.session_state.turn_count,
    })
    return f"Recorded probe fired: {input['probe_name']}"


def _handle_update_conversation_summary(input: dict) -> str:
    """Update rolling conversation summary (#3)."""
    st.session_state.routing_context["conversation_summary"] = input["summary"]
    return "Conversation summary updated"


def _handle_complete_mode(input: dict) -> str:
    """Signal mode completion, return to gathering (#8)."""
    st.session_state.current_phase = "gathering"
    st.session_state.active_mode = None
    st.session_state.routing_context["mode_turn_count"] = 0
    # NOTE: Does NOT reset assumption_register, document_skeleton, probes_fired,
    # patterns_fired, or conversation_summary — context persists.
    return f"Mode {input['mode_completed']} complete. System returned to context gathering. Summary: {input['summary']}"


def _handle_update_org_context(input: dict) -> str:
    """Update dynamic org context (#12)."""
    ctx = st.session_state.org_context
    ctx["company"] = input.get("company", ctx["company"])
    ctx["last_enriched_domain"] = input.get("domain", ctx["last_enriched_domain"])
    if input.get("public_context"):
        if ctx["public_context"]:
            ctx["public_context"] += "\n\n" + input["public_context"]
        else:
            ctx["public_context"] = input["public_context"]
    if input.get("internal_context"):
        if ctx["internal_context"]:
            ctx["internal_context"] += "\n\n" + input["internal_context"]
        else:
            ctx["internal_context"] = input["internal_context"]
    ctx["enrichment_count"] += 1
    return f"Org context updated for {input.get('company', 'unknown')} / {input.get('domain', 'unknown')}"
```

---

## 5. Prompt Templates (`prompts.py`)

### 5.1 System Prompt (Always Present)

```python
SYSTEM_PROMPT = """You are a PM co-pilot that helps Product Managers think through problems rigorously. You work collaboratively — you think WITH the user, not FOR them.

You have access to tools for tracking assumptions and building document skeletons. Use them actively as you discover information — don't wait until the end.

## Core Behaviors

1. **Progressive questioning:** Ask 2-3 motivated questions per turn maximum. Every question must explain WHY you're asking it. One cognitive task per turn.

2. **Micro-synthesis:** Every 2-3 turns, synthesize what you've learned so far in 1-2 sentences before asking follow-up questions.

3. **Density-to-risk:** Your depth of probing is driven by assumption risk, NOT user's tone. If someone says "just build X" but you've identified high-risk unvalidated assumptions, you probe deeply regardless. Stay concise, but ask the hard question.

4. **Dual-tone output:** When providing analysis:
   - Analysis section: Blunt, direct, for the PM. Name risks, identify political dynamics, flag where they might be wrong.
   - Stakeholder Questions section: Diplomatic, ready to use in meetings. Each maps to a specific risk from analysis.
   Never interleave these two tones.

5. **Generative, not blocking:** Make soft guesses marked with ⚠️ and register them as assumptions. Don't stop progress because something is unvalidated — track it and proceed.

6. **Concrete decision criteria:** Always produce specific "proceed IF" and "do NOT proceed IF" conditions. Never say "proceed with caution."

## Tool Usage

Call tools AS you discover information, not in batch at the end:
- `register_assumption` — whenever you identify something assumed but not validated
- `update_assumption_status` — when new info confirms or invalidates an assumption  
- `update_problem_statement` — when you can articulate the core problem
- `add_stakeholder` — when you identify someone relevant
- `update_success_metrics` — when metrics become clear
- `add_decision_criteria` — when you can state specific proceed/don't criteria
- `generate_artifact` — when the user asks for a deliverable or analysis is complete
- `record_probe_fired` — when you actively explore a probe's questions with the user
- `record_pattern_fired` — when a domain pattern's trigger conditions are met
- `update_conversation_summary` — at the END of every turn (mandatory)
- `update_org_context` — on first turn (company context) and when user provides internal context
- `complete_mode` — after generating final artifact and closing recommendations

## What NOT To Do
- Don't accept the problem as stated — always probe for embedded solutions and hidden assumptions
- Don't ask generic PM-101 questions — be specific to the input
- Don't dump a wall of analysis unprompted — use progressive disclosure
- Don't list 5+ risks at once — surface highest priority first
- Don't say "Have you considered X might not work?" — use diplomatic questioning strategies instead
- Don't assign tasks ("You should talk to X") — instead: "For this to work, X needs to be on board. What's your relationship with them?"
"""
```

### 5.2 Phase A Prompt (Routing/Think)

This is prepended to the user's message for the lightweight routing call.

```python
PHASE_A_PROMPT = """You are in ROUTING MODE. Your job is to analyze the current state and decide what to do next. Respond ONLY with a JSON object — no other text.

## Original Problem Statement (Turn 1)
{original_input}

## Rolling Summary (written by analysis phase last turn)
{conversation_summary}

## Current State
Turn count: {turn_count}
Current phase: {current_phase}
Active mode: {active_mode}
Probes fired: {probes_fired}
Patterns fired: {patterns_fired}
Micro-synthesis due: {micro_synthesis_due}
Critical mass reached: {critical_mass_reached}
Current org context domain: {org_context_domain}

## Assumption Register Summary
{assumption_summary}

## Conversation So Far (last 3 turns)
{recent_messages}

## Routing Logic

1. If current_phase is "gathering":
   - Evaluate the three diagnostic signals: Solution Specificity, Evidence of Prior Validation, Specificity of Ask
   - If critical mass criteria met (problem articulable in 2-3 sentences + primary stakeholders identified + highest-impact assumptions surfaced): set enter_mode = "mode_1"
   - Otherwise: continue gathering context

2. Check for assumption conflicts:
   - Direct contradiction with new information
   - High Impact + Guessed assumptions that haven't been probed
   - New stakeholders with decision authority

3. Decide next action

4. If active_mode is set and mode appears complete (artifact generated, user acknowledged, or user pivoting to new topic) but Phase B didn't call complete_mode: set next_action = "complete_mode" as safety net.

5. Check org context relevance:
   - Compare the current problem domain (from conversation_summary) against org_context_domain
   - If the problem has moved to a materially different domain or functional area AND enrichment_count < 3: set enrichment_needed = true
   - "Materially different" means: different business function (marketing → logistics), different stakeholder ecosystem, or different competitive context. NOT just new details within the same domain.

## Respond with this JSON structure:
{{
    "next_action": "ask_questions" | "micro_synthesize" | "enter_mode" | "continue_mode" | "flag_conflict" | "complete_mode",
    "enter_mode": null | "mode_1",
    "reasoning": "Brief explanation of why",
    "conflict_flags": [],
    "high_risk_unprobed": ["list of assumption IDs or descriptions that are high-impact + guessed and haven't been addressed"],
    "suggested_probes": ["Probe 1", "Probe 3"],
    "micro_synthesis_due": true | false,
    "enrichment_needed": false,
    "enrichment_query": "targeted description of what domain to enrich if enrichment_needed is true"
}}
"""
```

### 5.3 Phase B Prompt — Orchestrator Questioning

Used when Phase A decides to continue gathering context (no mode active yet).

```python
PHASE_B_ORCHESTRATOR_PROMPT = """You are gathering context to understand the user's problem before entering a specialized analysis mode.

## Turn Info
Turn count: {turn_count}

## Routing Decision
{phase_a_output}

## Full Conversation History
{full_messages}

## OrgContext
{org_context}

## Guidelines for This Turn

**If next_action is "ask_questions":**
- Ask 2-3 focused questions based on the suggested_probes
- Every question must be motivated: tell the user WHY you're asking
- If high_risk_unprobed items exist, prioritize those
- Use the appropriate probe logic from Mode 1 knowledge base
- When you explore a probe's questions, call record_probe_fired with the probe name and a brief summary of what you learned

**If next_action is "micro_synthesize":**
- Start with: "Here's what I'm understanding so far: [1-2 sentences]"
- Then ask 1-2 follow-up questions based on what's still unclear

**If next_action is "flag_conflict":**
- Surface the conflict directly but concisely
- Explain what changed and what it means
- Ask the user how they'd like to proceed

## Intake Triage (First Turn Only)
If turn_count is 1:
1. Extract the company/organization and domain from the user's message
2. Call update_org_context with public knowledge about the company — org structure, competitive landscape, known strategic context, industry dynamics relevant to the stated problem
3. Evaluate: Solution Specificity, Evidence of Prior Validation, Specificity of Ask
4. If solution + no validation evidence, note you'll start with discovery
5. Acknowledge what public context you have about the organization
6. Offer the user a chance to add internal context: "I've pulled some context about [company]. If there's anything internal that would help — team structure, past decisions, terminology — feel free to share at any point. Otherwise we'll work with what's publicly available."
7. Do NOT block on this. Ask your first substantive questions in the same turn.
8. Always offer an escape hatch: "...or have you already validated the underlying problem and want to jump ahead?"

## End-of-Turn Requirement
Before finishing your response, you MUST call update_conversation_summary with a 2-3 sentence summary covering:
1. What has been established so far (key facts, validated context)
2. What key open questions or unvalidated assumptions remain
3. What changed or was learned this turn
This summary is consumed by the routing phase next turn. Be precise and cumulative — it replaces the previous summary entirely.

Remember: Register assumptions via tool calls as you discover them. Don't wait.
"""
```

### 5.4 Phase B Prompt — Mode 1 Active

Used when Phase A decides to enter or continue Mode 1.

```python
PHASE_B_MODE1_PROMPT = """You are now operating in Mode 1: Discover & Frame.

Core question: "What's really going on, and is it worth pursuing?"

## Turn Info
Turn count: {turn_count}
First turn in current mode: {is_first_mode_turn}

## Routing Decision
{phase_a_output}

## Full Conversation History
{full_messages}

## Current Assumption Register
{full_assumptions}

## Current Document Skeleton
{document_skeleton}

## OrgContext
{org_context}

## Mode 1 Knowledge Base
{mode1_knowledge}

## Your Task This Turn

Continue the discovery and framing process. Based on where we are:

**If this is the FIRST Mode 1 turn (is_first_mode_turn = True):**
- Synthesize everything learned during context gathering
- Run the highest-priority unaddressed probes
- Register initial assumptions
- Present your emerging understanding of the problem

**If this is a CONTINUATION turn:**
- Incorporate the user's latest input
- Update assumptions if new info changes them
- Run the next priority probe(s)

**If you have enough information for a Problem Frame:**
- Generate the full Problem Frame Document using dual-tone structure:
  1. Problem Statement (genuinely reframed, NOT restatement)
  2. What This Is NOT About
  3. Why Now
  4. Analysis Section (blunt, direct)
  5. Stakeholder Questions Section (diplomatic, ready to use)
  6. Decision Criteria (specific proceed IF / do NOT invest IF)
  7. Recommended Next Steps
- Call all relevant tool functions to populate document skeleton and assumption register
- Call generate_artifact("problem_brief") to render the document
- When you call generate_artifact, the rendered document will be displayed directly to the user. You will receive a confirmation. You may add brief commentary after (e.g., recommended next steps, what to validate first) but do not attempt to reproduce or summarize the artifact content.
- After generating the artifact and providing your closing recommendations, call complete_mode to signal that Mode 1's work is done.

## Probe Tracking
When you explore a probe's questions with the user, call record_probe_fired with the probe name and a summary. Assess whether the probe's completion criteria are satisfied or still open in the summary. You may revisit a probe on a later turn if its criteria weren't met, but do not re-explore aspects that are already resolved.

## Domain Pattern Checks
Evaluate domain patterns on EVERY Mode 1 turn, but with discipline:
- Only trigger a pattern when its trigger conditions are CLEARLY met based on information gathered so far — not speculation about what might be true
- When a pattern triggers, call record_pattern_fired with the pattern name and reason BEFORE registering the associated assumption, so the pattern's implications inform your questions this turn
- Patterns that triggered on earlier turns (visible in patterns_fired) should NOT be re-evaluated unless new information materially changes the trigger or suppression conditions
- If trigger conditions are partially met but you need more information to confirm, note this internally and probe for the missing information — do not trigger the pattern yet

## Diplomatic Questioning Strategies (for Stakeholder Questions section)
When generating stakeholder-ready questions, use these strategies:
1. Outcome Question — ask what outcome they want instead of challenging solution
2. Specificity Test — ask them to apply idea to a concrete case
3. "Closest Attempt" Question — ask about prior attempts without judging
4. Elevation Frame — position challenge as expanding opportunity
5. Constraint Surfacing — frame constraint discovery as ensuring success

Anti-patterns to avoid:
- "Have you considered X might not work?"
- Listing 5+ risks at once
- "The research says X"
- "You should talk to [team]"
- Asking questions you know the answer to

## End-of-Turn Requirement
Before finishing your response, you MUST call update_conversation_summary with a 2-3 sentence summary covering:
1. What has been established so far (key facts, validated context)
2. What key open questions or unvalidated assumptions remain
3. What changed or was learned this turn
This summary is consumed by the routing phase next turn. Be precise and cumulative — it replaces the previous summary entirely.
"""
```

---

## 6. Mode 1 Knowledge Base (`mode1_knowledge.py`)

This file contains the full text of the Mode 1 knowledge base, loaded as a string and injected into Phase B prompts when Mode 1 is active. It includes all 7 probes, all 8 domain patterns with trigger/suppression conditions, the prioritization engine, and the output structure.

```python
MODE1_KNOWLEDGE = """
[PASTE THE FULL CONTENTS OF mode1-discover-frame-spec-v2.md HERE]
"""
```

**Implementation note:** Copy the entire contents of `mode1-discover-frame-spec-v2.md` into this string. Do not summarize or truncate — the full knowledge base is needed for the LLM to operate with expert-level depth.

**Context window consideration:** The Mode 1 knowledge base is ~4,000 tokens. Combined with system prompt (~800 tokens), Phase B prompt (~600 tokens), OrgContext (~500-1,000 tokens), conversation history, and assumption register, total prompt will be well within context limits for extended conversations.

---

## 7. OrgContext — Dynamic Enrichment (`org_context.py`)

OrgContext is no longer a static file. It is built dynamically from model knowledge + optional user input.

```python
import streamlit as st


def format_org_context() -> str:
    """Format the dynamic org context for prompt injection."""
    ctx = st.session_state.org_context
    if not ctx["company"] and not ctx["public_context"] and not ctx["internal_context"]:
        return "(No organizational context yet. On the first turn, use update_org_context to populate public knowledge about the user's company/domain.)"

    parts = []
    if ctx["company"]:
        parts.append(f"## Organization: {ctx['company']}")
    if ctx["public_context"]:
        parts.append(f"## Public Context\n{ctx['public_context']}")
    if ctx["internal_context"]:
        parts.append(f"## Internal Context (user-provided)\n{ctx['internal_context']}")
    return "\n\n".join(parts)
```

**No `org_context.md` file needed.** The model generates public context on the first turn using its own knowledge, stored via the `update_org_context` tool call. Internal context is appended when the user provides it.

**Context window consideration:** Org context is typically 500-1000 tokens — same as the old static file. The model's knowledge may generate slightly more or less depending on the company.

---

## 8. Orchestrator Logic (`orchestrator.py`)

This is the core engine. It handles the two-phase-per-turn architecture.

```python
import json
import streamlit as st
from dotenv import load_dotenv  # Bug #1: load .env before Anthropic client
load_dotenv()

from anthropic import Anthropic
from tools import handle_tool_call, TOOL_DEFINITIONS
from prompts import (
    SYSTEM_PROMPT,
    PHASE_A_PROMPT,
    PHASE_B_ORCHESTRATOR_PROMPT,
    PHASE_B_MODE1_PROMPT,
)
from mode1_knowledge import MODE1_KNOWLEDGE
from org_context import format_org_context
from config import MODEL_NAME


client = Anthropic()


def run_turn(user_message: str) -> str:
    """
    Process one user turn through the two-phase architecture.
    Returns the assistant's response text.
    """
    st.session_state.turn_count += 1

    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": user_message})

    # --- PHASE A: Route ---
    routing_decision = _run_phase_a(user_message)

    # --- Handle enrichment if Phase A flagged it (#12) ---
    # Enrichment is handled BY Phase B — Phase A just flags it.
    # The flag is passed in routing_decision for Phase B to act on.

    # --- PHASE B: Act ---
    response_text = _run_phase_b(routing_decision)

    # Add assistant response to history
    st.session_state.messages.append({"role": "assistant", "content": response_text})

    # --- POST-TURN: Update routing context ---
    _post_turn_updates(routing_decision)

    return response_text


def _run_phase_a(user_message: str) -> dict:
    """
    Lightweight routing call. Reads state, decides what to do next.
    Returns parsed routing decision dict.
    """
    # Build assumption summary for routing
    assumption_summary = _build_assumption_summary()

    # Get original input (first user message) (#3)
    original_input = ""
    for m in st.session_state.messages:
        if m["role"] == "user":
            original_input = m["content"]
            break

    # Get rolling conversation summary (#3)
    conversation_summary = st.session_state.routing_context.get("conversation_summary", "")

    # Get recent messages (last 3 turns = 6 messages)
    recent = st.session_state.messages[-6:]
    recent_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent
    )

    prompt = PHASE_A_PROMPT.format(
        turn_count=st.session_state.turn_count,
        current_phase=st.session_state.current_phase,
        active_mode=st.session_state.active_mode,
        probes_fired=st.session_state.routing_context["probes_fired"],
        patterns_fired=st.session_state.routing_context["patterns_fired"],
        micro_synthesis_due=st.session_state.routing_context["micro_synthesis_due"],
        critical_mass_reached=st.session_state.routing_context["critical_mass_reached"],
        assumption_summary=assumption_summary,
        recent_messages=recent_text,
        original_input=original_input,
        conversation_summary=conversation_summary or "(No summary yet — first turn)",
        org_context_domain=st.session_state.org_context.get("last_enriched_domain", ""),
    )

    # Error handling (#13)
    try:
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=500,
            system="You are a routing engine. Respond ONLY with valid JSON. No markdown, no explanation.",
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse JSON from response
        raw = response.content[0].text.strip()
        # Handle potential markdown code fence
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        routing = json.loads(raw)
    except Exception:
        # Fallback: continue with safe default (#13)
        routing = {
            "next_action": "ask_questions",
            "enter_mode": None,
            "reasoning": "Phase A error or parse failure, defaulting to questions",
            "conflict_flags": [],
            "high_risk_unprobed": [],
            "suggested_probes": [],
            "micro_synthesis_due": False,
            "enrichment_needed": False,
            "enrichment_query": "",
        }

    # Handle mode entry
    if routing.get("enter_mode") == "mode_1" and st.session_state.active_mode != "mode_1":
        st.session_state.current_phase = "mode_active"
        st.session_state.active_mode = "mode_1"
        st.session_state.routing_context["critical_mass_reached"] = True
        st.session_state.routing_context["mode_turn_count"] = 0  # Reset for new mode (#9)

    # Handle complete_mode from Phase A safety net (#8)
    if routing.get("next_action") == "complete_mode":
        st.session_state.current_phase = "gathering"
        st.session_state.active_mode = None
        st.session_state.routing_context["mode_turn_count"] = 0

    return routing


def _run_phase_b(routing_decision: dict) -> str:
    """
    Heavy execution call. Either orchestrator questioning or mode execution.
    Handles tool calls in a loop until the model stops calling tools.
    Returns the final text response.
    """
    # Build org context string (#12)
    org_context_text = format_org_context()

    # Build the appropriate prompt
    if st.session_state.active_mode == "mode_1":
        phase_b_prompt = PHASE_B_MODE1_PROMPT.format(
            phase_a_output=json.dumps(routing_decision, indent=2),
            full_messages=_format_messages(st.session_state.messages),
            full_assumptions=_format_assumptions(),
            document_skeleton=_format_skeleton(),
            org_context=org_context_text,
            mode1_knowledge=MODE1_KNOWLEDGE,
            turn_count=st.session_state.turn_count,
            is_first_mode_turn=(st.session_state.routing_context["mode_turn_count"] == 0),
        )
    else:
        phase_b_prompt = PHASE_B_ORCHESTRATOR_PROMPT.format(
            phase_a_output=json.dumps(routing_decision, indent=2),
            full_messages=_format_messages(st.session_state.messages),
            org_context=org_context_text,
            turn_count=st.session_state.turn_count,
        )

    # Context window safety check (#13)
    estimated_tokens = len(phase_b_prompt) // 4
    if estimated_tokens > 150000:  # ~80% of 200K context
        # Truncate older messages, keeping first + last 10 turns
        messages = st.session_state.messages
        if len(messages) > 22:  # More than 11 turns
            first_msg = messages[0]
            recent_msgs = messages[-20:]
            truncated = [first_msg, {"role": "assistant", "content": "[...earlier conversation truncated for context length...]"}] + recent_msgs
            # Rebuild prompt with truncated messages
            if st.session_state.active_mode == "mode_1":
                phase_b_prompt = PHASE_B_MODE1_PROMPT.format(
                    phase_a_output=json.dumps(routing_decision, indent=2),
                    full_messages=_format_messages(truncated),
                    full_assumptions=_format_assumptions(),
                    document_skeleton=_format_skeleton(),
                    org_context=org_context_text,
                    mode1_knowledge=MODE1_KNOWLEDGE,
                    turn_count=st.session_state.turn_count,
                    is_first_mode_turn=(st.session_state.routing_context["mode_turn_count"] == 0),
                )
            else:
                phase_b_prompt = PHASE_B_ORCHESTRATOR_PROMPT.format(
                    phase_a_output=json.dumps(routing_decision, indent=2),
                    full_messages=_format_messages(truncated),
                    org_context=org_context_text,
                    turn_count=st.session_state.turn_count,
                )

    # Build messages for API call
    api_messages = [{"role": "user", "content": phase_b_prompt}]

    # Tool use loop with error handling (#13)
    final_text = ""
    try:
        while True:
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=api_messages,
                tools=TOOL_DEFINITIONS,
            )

            # Process response content blocks
            tool_calls_made = False
            tool_results = []
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
                elif block.type == "tool_use":
                    tool_calls_made = True
                    result = handle_tool_call(block.name, block.input)
                    # Special handling for generate_artifact (#7):
                    # Render directly to user, send confirmation to model
                    if block.name == "generate_artifact":
                        final_text += "\n\n" + result  # Artifact goes to user
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "Artifact rendered and displayed to user.",
                        })
                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

            # If no tool calls, we're done
            if not tool_calls_made:
                break

            # If tool calls were made, append assistant response + tool results and continue
            api_messages.append({"role": "assistant", "content": response.content})
            api_messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        # Error handling (#13)
        if final_text:
            final_text += "\n\n---\n⚠️ I encountered an error mid-response. What I've shared above is still valid. Please try sending your next message and I'll continue."
        else:
            final_text = "I hit a temporary issue processing your message. Your conversation is preserved — please try again."

    return final_text


def _post_turn_updates(routing_decision: dict):
    """Update routing context after a turn completes."""
    # Track micro-synthesis cadence
    if st.session_state.turn_count % 3 == 0:
        st.session_state.routing_context["micro_synthesis_due"] = True
    else:
        st.session_state.routing_context["micro_synthesis_due"] = False

    # Increment mode turn count if in a mode (#9)
    if st.session_state.active_mode:
        st.session_state.routing_context["mode_turn_count"] += 1

    # NOTE: probes_fired and patterns_fired are now tracked by Phase B via
    # record_probe_fired and record_pattern_fired tools (#2, #2b).
    # No longer inferred from routing_decision["suggested_probes"].


# --- Helper formatters ---

def _build_assumption_summary() -> str:
    """Build a concise summary of assumptions for the routing prompt."""
    assumptions = st.session_state.assumption_register
    if not assumptions:
        return "No assumptions registered yet."

    lines = []
    for aid, a in sorted(assumptions.items()):
        flag = "🔴" if a["impact"] == "high" and a["confidence"] == "guessed" else ""
        lines.append(f"{flag} {a['id']}: [{a['impact']}/{a['confidence']}/{a['status']}] {a['claim']}")
    return "\n".join(lines)


def _format_messages(messages: list) -> str:
    """Format message history for prompt injection."""
    return "\n\n".join(
        f"**{m['role'].upper()}:** {m['content']}" for m in messages
    )


def _format_assumptions() -> str:
    """Format full assumption register for mode prompts."""
    assumptions = st.session_state.assumption_register
    if not assumptions:
        return "No assumptions registered yet."

    lines = []
    for aid, a in sorted(assumptions.items()):
        lines.append(
            f"- **{a['id']}** [{a['type']}] {a['claim']}\n"
            f"  Impact: {a['impact']} | Confidence: {a['confidence']} | Status: {a['status']}\n"
            f"  Basis: {a['basis']} | Surfaced by: {a['surfaced_by']}\n"
            f"  Depends on: {a['depends_on']} | Action: {a['recommended_action']}"
        )
    return "\n".join(lines)


def _format_skeleton() -> str:
    """Format document skeleton for mode prompts."""
    s = st.session_state.document_skeleton
    parts = []
    if s["problem_statement"]:
        parts.append(f"Problem: {s['problem_statement']}")
    if s["target_audience"]:
        parts.append(f"Audience: {s['target_audience']}")
    if s["stakeholders"]:
        sh_lines = [f"  - {v['name']} ({v['type']})" for v in s["stakeholders"].values()]
        parts.append("Stakeholders:\n" + "\n".join(sh_lines))
    metrics = s["success_metrics"]
    if any(metrics.values()):
        parts.append(f"Metrics: Leading={metrics['leading']}, Lagging={metrics['lagging']}, Anti={metrics['anti_metric']}")
    if s["decision_criteria"]["proceed_if"]:
        parts.append("Proceed IF: " + "; ".join(s["decision_criteria"]["proceed_if"]))
    if s["decision_criteria"]["do_not_proceed_if"]:
        parts.append("Do NOT IF: " + "; ".join(s["decision_criteria"]["do_not_proceed_if"]))
    return "\n".join(parts) if parts else "Document skeleton is empty."
```

---

## 9. Streamlit UI (`app.py`)

```python
import streamlit as st
from state import init_session_state
from orchestrator import run_turn


st.set_page_config(page_title="PM Co-Pilot", layout="wide")

# --- Initialize ---
init_session_state()

# --- Sidebar ---
with st.sidebar:
    st.title("🧭 PM Co-Pilot")
    st.caption("Orchestrator + Mode 1: Discover & Frame")

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
    assumptions = st.session_state.assumption_register
    if assumptions:
        for aid, a in sorted(assumptions.items()):
            # Color-code by risk
            if a["impact"] == "high" and a["confidence"] == "guessed":
                icon = "🔴"
            elif a["impact"] == "high":
                icon = "🟡"
            else:
                icon = "🟢"
            with st.expander(f"{icon} {a['id']}: {a['claim'][:50]}..."):
                st.write(f"**Type:** {a['type']}")
                st.write(f"**Impact:** {a['impact']} | **Confidence:** {a['confidence']}")
                st.write(f"**Status:** {a['status']}")
                st.write(f"**Basis:** {a['basis']}")
                st.write(f"**Action:** {a['recommended_action']}")
    else:
        st.caption("No assumptions tracked yet.")

    # Document skeleton display
    st.divider()
    st.subheader("Document Skeleton")
    skeleton = st.session_state.document_skeleton
    if skeleton["problem_statement"]:
        st.write(f"**Problem:** {skeleton['problem_statement'][:100]}...")
    if skeleton["stakeholders"]:
        st.write(f"**Stakeholders:** {len(skeleton['stakeholders'])} identified")
    if any(skeleton["success_metrics"].values()):
        st.write("**Metrics:** ✅ Defined")

    # Artifact download (#14)
    if st.session_state.latest_artifact:
        st.divider()
        st.subheader("Latest Artifact")
        st.download_button(
            label="📄 Download Problem Brief",
            data=st.session_state.latest_artifact,
            file_name="problem_brief.md",
            mime="text/markdown",
            use_container_width=True,
        )

    # Reset button
    st.divider()
    if st.button("🔄 New Session", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    # Modes roadmap
    st.divider()
    st.subheader("Modes")
    st.write("✅ Mode 1: Discover & Frame")
    st.write("🔲 Mode 2: Evaluate Solution")
    st.write("🔲 Mode 3: Surface Constraints")
    st.write("🔲 Mode 4: Size & Value")
    st.write("🔲 Mode 5: Prioritize & Sequence")

# --- Main Chat ---
st.title("PM Co-Pilot")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if user_input := st.chat_input("Describe your problem, opportunity, or idea..."):
    # Display user message immediately
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run through orchestrator
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = run_turn(user_input)
        st.markdown(response)
```

---

## 10. Config (`config.py`)

```python
MODEL_NAME = "claude-sonnet-4-20250514"
PHASE_A_MODEL = "claude-sonnet-4-20250514"  # Could use Haiku for routing if cost matters
MAX_CONVERSATION_TURNS = 50  # Safety limit
```

---

## 11. Requirements (`requirements.txt`)

```
streamlit>=1.30.0
anthropic>=0.40.0
python-dotenv>=1.0.0
```

**Note:** LangGraph is NOT used in v1. The implementation uses direct Anthropic API calls with a simple tool loop. LangGraph can be introduced later if we need more complex state machines (multi-mode transitions, automatic looping, persistent checkpoints). Starting without it keeps the code simpler and more debuggable.

---

## 12. Implementation Plan — Build Order

### Step 1: Scaffold (30 min)
- Create all files with stubs
- Set up `.env` with API key
- Verify `streamlit run app.py` works with empty chat

### Step 2: Basic Chat Loop (1 hour)
- Implement `orchestrator.py` with Phase B only (skip Phase A routing)
- Use system prompt + direct Anthropic API call
- Verify tool calls work (register_assumption, etc.)
- Verify sidebar updates when assumptions are registered

### Step 3: Phase A Routing (1 hour)
- Implement `_run_phase_a` with routing prompt
- Wire up two-phase flow
- Test: first turn should trigger intake triage
- Test: turn 3 should trigger micro-synthesis
- Test: ~turn 5-7 should trigger mode entry

### Step 4: OrgContext + Mode 1 Knowledge Base (1.5 hours)
- Implement `org_context.py` with `format_org_context()` helper
- Populate `mode1_knowledge.py` with full spec contents (including v2.1 probe completion criteria and pattern timing notes)
- Implement Mode 1 Phase B prompt
- Test: On first turn, model should call `update_org_context` with public knowledge about the stated company
- Test: Model should offer user chance to add internal context (non-blocking)
- Test: Mode 1 should run probes in priority order
- Test: Domain patterns should fire with trigger conditions met, with org-specific context informing questions
- Test: Pattern timing should match guidance (e.g., Pattern 3 fires early, Pattern 8 fires late)

### Step 5: Mode Completion + Artifact Generation (1 hour)
- Test `generate_artifact("problem_brief")` — verify it renders directly to user (#7), not relayed by model
- Verify all document skeleton fields render correctly
- Verify assumptions table renders
- Test `complete_mode` — verify system returns to gathering state (#8)
- Verify artifact appears in sidebar download button (#14)
- Test mode re-entry: after completing Mode 1, system should be able to enter Mode 1 again for a new problem

### Step 6: End-to-End Testing (1-2 hours)
- Run through the digital twins scenario end-to-end
- Run through the store delivery scenario
- Check: Does it avoid the 7 failure modes?
- Check: Does density-to-risk work? (brief input + high risk → deep probing)
- Check: Do domain patterns fire correctly? (trigger AND suppression, with correct timing)
- Check: Is the Problem Frame output genuinely reframed, not restated?
- Check: Do probes get recorded with completion status? (#2b, #10)
- Check: Do patterns get recorded when triggered? (#2)
- Check: Does the rolling summary update each turn? (#3)
- Check: Does the dependency cascade work? (invalidate A1 → A3 becomes at_risk if dependent) (#5)
- Check: Does the download button appear after artifact generation? (#14)
- Check: Does complete_mode return system to gathering? (#8)
- Check: Does error handling work gracefully? (test with invalid API key) (#13)

---

## 13. Key Implementation Decisions & Rationale

### Why No LangGraph in v1?

The two-phase architecture maps cleanly to two sequential API calls. LangGraph's value is in complex state machines with branching, looping, and persistent checkpoints. We don't need that yet. Direct API calls are simpler to debug and understand. Add LangGraph later if we need:
- Automatic multi-mode transitions without user confirmation
- Persistent conversation state across sessions
- Parallel mode execution

### Why Direct Anthropic API (Not LangChain)?

LangChain adds abstraction layers that make debugging harder. The Anthropic SDK is clean and well-documented. Tool use with the native SDK is straightforward. We can always wrap it later if needed.

### Why Tool Calls Instead of Structured Output?

Tool calls create an explicit audit trail. Every state change is logged as a function call. The application layer handles data integrity. The LLM decides WHAT to update; the application decides HOW. This is more reliable than asking the LLM to output a JSON blob and parsing it.

### Why Two API Calls Per Turn?

A single call trying to route + analyze + generate tools suffers from attention dilution. Phase A is lightweight (~500 token output) and fast. Phase B gets a focused task with the right context injected. The cost of the extra API call is minimal compared to the quality improvement.

### Why Session State (Not Database)?

For v1, conversations are ephemeral. No need for persistence across sessions. Streamlit's session_state is simple and sufficient. Add database persistence later if needed for multi-session analysis.

---

## 14. Testing Scenarios

### Scenario 1: Digital Twins (Solution-First Input)
```
"The UCM could benefit from a pre-activation decision capability that uses 
linked digital twins to predict campaign performance before budget is committed."
```
**Expected behavior:**
- Probe 1 fires: separates digital twins (solution) from campaign prediction (need)
- Pattern 3 fires: conference-driven solution anchoring
- Pattern 2 fires: dual-customer ambiguity (KPM vs platform)
- Pattern 1 may fire: store reality check (if campaigns affect store execution)
- Pattern 6 may fire: alternative profit framing
- Questions focus on: What's the current estimation process? What breaks? Why now?

### Scenario 2: Store Delivery (Operations Input)
```
"We need to improve our store delivery scheduling to reduce out-of-stocks."
```
**Expected behavior:**
- Probe 1: No embedded solution → validate problem existence
- Probe 2: Why now? Has something changed?
- Probe 4 fires: Store reality check (directly about store operations)
- Pattern 5 may fire: Talent dependency (if solution requires specialized work)
- Questions focus on: What's driving out-of-stocks? Is it scheduling or something else?

### Scenario 3: Brief High-Risk Input (Density-to-Risk Test)
```
"Build a GenAI tool for campaign optimization. Go."
```
**Expected behavior:**
- System does NOT match the user's brief, action-oriented energy
- Probe 1 fires aggressively: What problem does GenAI solve here?
- Pattern 3 fires: conference-driven solution anchoring (GenAI is buzzworthy)
- System stays concise but asks the hard question
- Something like: "You're ready to move fast — before we do, one thing: what specific campaign decision is being made poorly today that GenAI would fix?"

---

## 15. Known Limitations (v1)

1. **No multi-mode transitions** — Mode 1 only. When it suggests "next mode," the user handles it manually.
2. **No conversation persistence** — Sessions reset on page refresh. State is in-memory only.
3. **No automatic conflict detection** — Phase A checks for conflicts, but the routing logic is prompt-based, not deterministic. May miss subtle conflicts.
4. **No streaming** — Responses appear all at once after both phases complete. Could add streaming for Phase B later.
5. **Phase A reliability** — Routing via JSON output from an LLM is inherently fuzzy. May sometimes route incorrectly. The fallback default (continue asking questions) is safe.
6. **Context window growth** — Long conversations will accumulate message history. Rough truncation strategy added for safety but may lose nuance from early turns.
7. **Two API calls per turn = latency** — Phase A + Phase B = 6-25 seconds per turn. Accepted for v1. Phase A skipping for predictable cases (e.g., turn 1, already in mode) can be added later once Phase A has proven reliable. Autonomy must be earned.
8. **update_conversation_summary compliance** — Phase B must call this tool every turn. If it doesn't, the rolling summary goes stale. Monitor this during testing. If compliance is below ~90%, add a defensive fallback in _post_turn_updates that generates a basic summary from structured state.
9. **OrgContext from model knowledge** — Public context quality depends on the model's training data about the company. For obscure companies, context may be thin. The user can supplement with internal context.
