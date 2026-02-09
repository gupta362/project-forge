import streamlit as st


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

    # Dependency cascade
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

    # Defensive check: warn if skeleton is mostly empty
    empty_fields = []
    if not skeleton["problem_statement"]:
        empty_fields.append("problem_statement")
    if not skeleton["stakeholders"]:
        empty_fields.append("stakeholders")
    if not any(skeleton["success_metrics"].values()):
        empty_fields.append("success_metrics")
    if not skeleton["decision_criteria"]["proceed_if"] and not skeleton["decision_criteria"]["do_not_proceed_if"]:
        empty_fields.append("decision_criteria")
    if empty_fields:
        return (
            f"WARNING: The following skeleton fields are empty: {', '.join(empty_fields)}. "
            "You must call update_problem_statement, add_stakeholder, update_success_metrics, "
            "and add_decision_criteria BEFORE calling generate_artifact. "
            "Please populate these fields first, then call generate_artifact again."
        )

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
    st.session_state.latest_artifact = doc
    return doc


def _handle_record_pattern_fired(input: dict) -> str:
    """Record that a domain pattern triggered."""
    st.session_state.routing_context["patterns_fired"].append({
        "name": input["pattern_name"],
        "reason": input["trigger_reason"],
        "turn": st.session_state.turn_count,
    })
    return f"Recorded pattern fired: {input['pattern_name']}"


def _handle_record_probe_fired(input: dict) -> str:
    """Record that a probe was executed."""
    st.session_state.routing_context["probes_fired"].append({
        "name": input["probe_name"],
        "summary": input.get("summary", ""),
        "turn": st.session_state.turn_count,
    })
    return f"Recorded probe fired: {input['probe_name']}"


def _handle_update_conversation_summary(input: dict) -> str:
    """Update rolling conversation summary."""
    st.session_state.routing_context["conversation_summary"] = input["summary"]
    return "Conversation summary updated"


def _handle_complete_mode(input: dict) -> str:
    """Signal mode completion, return to gathering."""
    st.session_state.current_phase = "gathering"
    st.session_state.active_mode = None
    st.session_state.routing_context["mode_turn_count"] = 0
    # NOTE: Does NOT reset assumption_register, document_skeleton, probes_fired,
    # patterns_fired, or conversation_summary — context persists.
    return f"Mode {input['mode_completed']} complete. System returned to context gathering. Summary: {input['summary']}"


def _handle_update_org_context(input: dict) -> str:
    """Update dynamic org context."""
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
