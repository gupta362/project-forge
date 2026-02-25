import logging
import streamlit as st

from .persistence import _write_context_file

logger = logging.getLogger("forge.tools")


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
                "artifact_type": {"type": "string", "enum": ["problem_brief", "solution_evaluation_brief"]},
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
        "name": "set_risk_assessment",
        "description": "Set or update a risk assessment for one of the four Cagan risk dimensions (value, usability, feasibility, viability). Call this as you evaluate each dimension during Mode 2.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "enum": ["value", "usability", "feasibility", "viability"],
                              "description": "Which risk dimension to assess"},
                "level": {"type": "string", "enum": ["low", "medium", "high"]},
                "summary": {"type": "string", "description": "1-2 sentence assessment of this risk dimension"},
                "evidence_for": {"type": "array", "items": {"type": "string"},
                                "description": "Evidence supporting low risk", "default": []},
                "evidence_against": {"type": "array", "items": {"type": "string"},
                                    "description": "Evidence supporting high risk", "default": []},
            },
            "required": ["dimension", "level", "summary"],
        },
    },
    {
        "name": "set_validation_plan",
        "description": "Set the recommended validation approach for the riskiest assumption. Call this after identifying the key risks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "riskiest_assumption": {"type": "string", "description": "Assumption ID (e.g., 'A5')"},
                "approach": {"type": "string", "enum": ["painted_door", "concierge", "technical_spike", "wizard_of_oz", "prototype", "other"]},
                "description": {"type": "string", "description": "Specific validation plan"},
                "timeline": {"type": "string", "description": "Estimated duration"},
                "success_criteria": {"type": "string", "description": "What 'validated' looks like"},
            },
            "required": ["riskiest_assumption", "approach", "description", "success_criteria"],
        },
    },
    {
        "name": "set_go_no_go",
        "description": "Set the go/no-go recommendation with conditions and dealbreakers. Call this when the evaluation is complete, before generating the artifact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recommendation": {"type": "string", "enum": ["go", "conditional_go", "pivot", "no_go"]},
                "conditions": {"type": "array", "items": {"type": "string"},
                              "description": "What must be true for 'go'"},
                "dealbreakers": {"type": "array", "items": {"type": "string"},
                                "description": "What would make this 'no_go'"},
            },
            "required": ["recommendation", "conditions", "dealbreakers"],
        },
    },
    {
        "name": "set_solution_info",
        "description": "Set the solution name, description, and optionally build-vs-buy assessment. Call on first Mode 2 turn to identify what's being evaluated.",
        "input_schema": {
            "type": "object",
            "properties": {
                "solution_name": {"type": "string", "description": "Name of the solution being evaluated"},
                "solution_description": {"type": "string", "description": "2-3 sentence summary of the proposed solution"},
                "build_vs_buy": {"type": "string", "description": "Build vs buy assessment summary (optional)"},
            },
            "required": ["solution_name", "solution_description"],
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
    logger.debug("Tool call: %s | input: %.200s", tool_name, str(tool_input))
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
        "set_risk_assessment": _handle_set_risk_assessment,
        "set_validation_plan": _handle_set_validation_plan,
        "set_go_no_go": _handle_set_go_no_go,
        "set_solution_info": _handle_set_solution_info,
        "record_pattern_fired": _handle_record_pattern_fired,
        "record_probe_fired": _handle_record_probe_fired,
        "update_conversation_summary": _handle_update_conversation_summary,
        "complete_mode": _handle_complete_mode,
        "update_org_context": _handle_update_org_context,
    }
    handler = handlers.get(tool_name)
    if handler:
        return handler(tool_input)
    logger.warning("Unknown tool name: %s", tool_name)
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
    """Dispatch to the appropriate artifact renderer."""
    artifact_type = input["artifact_type"]
    if artifact_type == "problem_brief":
        doc = _render_problem_brief()
    elif artifact_type == "solution_evaluation_brief":
        doc = _render_solution_evaluation_brief()
    else:
        return f"Unknown artifact type: {artifact_type}"

    # Auto-save artifact to project directory (skip validation warnings)
    if not doc.startswith("WARNING:") and hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        artifacts_dir = st.session_state.project_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        if artifact_type == "problem_brief":
            filename = "problem_brief.md"
        elif artifact_type == "solution_evaluation_brief":
            filename = "solution_evaluation.md"
        else:
            filename = f"{artifact_type}.md"
        (artifacts_dir / filename).write_text(doc)

    return doc


def _render_problem_brief() -> str:
    """Render Mode 1 artifact from skeleton + assumptions."""
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


def _render_solution_evaluation_brief() -> str:
    """Render Mode 2 artifact from flat skeleton keys + assumptions."""
    skeleton = st.session_state.document_skeleton
    assumptions = st.session_state.assumption_register

    # Defensive check
    empty_fields = []
    if not skeleton.get("solution_name"):
        empty_fields.append("solution_name")
    if not skeleton.get("value_risk_level"):
        empty_fields.append("value_risk_level")
    if not skeleton.get("go_no_go_recommendation"):
        empty_fields.append("go_no_go_recommendation")
    if empty_fields:
        return (
            f"WARNING: The following skeleton fields are empty: {', '.join(empty_fields)}. "
            "You must call set_solution_info, set_risk_assessment, and set_go_no_go "
            "BEFORE calling generate_artifact. Please populate these fields first, then call generate_artifact again."
        )

    # Build risk sections
    def format_risk(dimension_name, display_name):
        level = skeleton.get(f"{dimension_name}_risk_level")
        if not level:
            return f"### {display_name}: _Not assessed_\n"
        summary = skeleton.get(f"{dimension_name}_risk_summary", "_No summary_")
        text = f"### {display_name}: {level.upper()}\n{summary}\n"
        evidence_for = skeleton.get(f"{dimension_name}_risk_evidence_for", [])
        evidence_against = skeleton.get(f"{dimension_name}_risk_evidence_against", [])
        if evidence_for:
            text += "\n**Supporting evidence:**\n" + "\n".join(f"- {e}" for e in evidence_for) + "\n"
        if evidence_against:
            text += "\n**Concerns:**\n" + "\n".join(f"- {e}" for e in evidence_against) + "\n"
        return text

    risk_text = ""
    risk_text += format_risk("value", "Value Risk")
    risk_text += format_risk("usability", "Usability Risk")
    risk_text += format_risk("feasibility", "Feasibility Risk")
    risk_text += format_risk("viability", "Viability Risk")

    # Build assumption table (all active/at_risk)
    assumption_rows = ""
    for aid, a in sorted(assumptions.items()):
        if a["status"] in ("active", "at_risk"):
            assumption_rows += f"| {a['id']} | {a['claim']} | {a['impact']} | {a['confidence']} | {a['recommended_action']} |\n"

    # Build vs buy
    bvb = skeleton.get("build_vs_buy_assessment")
    bvb_text = bvb if bvb else "_Not applicable or not assessed_"

    # Validation plan
    vp_approach = skeleton.get("validation_approach")
    if vp_approach:
        vp_text = f"**Approach:** {vp_approach}\n"
        vp_text += f"{skeleton.get('validation_description', '')}\n"
        if skeleton.get("validation_timeline"):
            vp_text += f"\n**Timeline:** {skeleton['validation_timeline']}\n"
        if skeleton.get("validation_success_criteria"):
            vp_text += f"\n**Success criteria:** {skeleton['validation_success_criteria']}\n"
    else:
        vp_text = "_Not yet defined_"

    # Go/no-go
    rec = (skeleton.get("go_no_go_recommendation") or "NOT YET DETERMINED").upper().replace("_", " ")
    conditions = "\n".join(f"- {c}" for c in skeleton.get("go_no_go_conditions", []))
    dealbreakers = "\n".join(f"- {d}" for d in skeleton.get("go_no_go_dealbreakers", []))

    doc = f"""# Solution Evaluation: {skeleton.get('solution_name', '_Unnamed_')}

## Executive Summary
{skeleton.get('solution_description', '_No description_')}

## Problem-Solution Fit
Evaluated against: {skeleton.get('problem_statement', '_No problem statement from Mode 1_')}

## Risk Assessment

{risk_text}

## Build vs. Buy Consideration
{bvb_text}

## Key Assumptions Requiring Validation

| ID | Assumption | Impact | Confidence | Recommended Validation |
|----|-----------|--------|------------|----------------------|
{assumption_rows or '| — | No assumptions registered | — | — | — |'}

## Recommended Validation Approach
{vp_text}

## Go/No-Go Assessment
**Recommendation: {rec}**

**Proceed IF:**
{conditions or '_Not yet defined_'}

**Do NOT proceed IF:**
{dealbreakers or '_Not yet defined_'}
"""
    st.session_state.latest_artifact = doc
    return doc


def _handle_set_risk_assessment(input: dict) -> str:
    """Set risk assessment for one of the four Cagan dimensions."""
    dim = input["dimension"]
    skeleton = st.session_state.document_skeleton
    skeleton[f"{dim}_risk_level"] = input["level"]
    skeleton[f"{dim}_risk_summary"] = input["summary"]
    if "evidence_for" in input:
        skeleton[f"{dim}_risk_evidence_for"] = input["evidence_for"]
    if "evidence_against" in input:
        skeleton[f"{dim}_risk_evidence_against"] = input["evidence_against"]
    return f"Set {dim} risk: {input['level']} — {input['summary']}"


def _handle_set_validation_plan(input: dict) -> str:
    """Set the validation plan."""
    skeleton = st.session_state.document_skeleton
    skeleton["validation_riskiest_assumption"] = input["riskiest_assumption"]
    skeleton["validation_approach"] = input["approach"]
    skeleton["validation_description"] = input["description"]
    skeleton["validation_timeline"] = input.get("timeline")
    skeleton["validation_success_criteria"] = input["success_criteria"]
    return f"Validation plan set: {input['approach']} for {input['riskiest_assumption']}"


def _handle_set_go_no_go(input: dict) -> str:
    """Set the go/no-go recommendation."""
    skeleton = st.session_state.document_skeleton
    skeleton["go_no_go_recommendation"] = input["recommendation"]
    skeleton["go_no_go_conditions"] = input["conditions"]
    skeleton["go_no_go_dealbreakers"] = input["dealbreakers"]
    return f"Go/no-go set: {input['recommendation']}"


def _handle_set_solution_info(input: dict) -> str:
    """Set solution name, description, and optionally build-vs-buy."""
    skeleton = st.session_state.document_skeleton
    skeleton["solution_name"] = input["solution_name"]
    skeleton["solution_description"] = input["solution_description"]
    if "build_vs_buy" in input and input["build_vs_buy"]:
        skeleton["build_vs_buy_assessment"] = input["build_vs_buy"]
    return f"Solution info set: {input['solution_name']}"


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
    # Write context.md if we have a project directory
    if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        _write_context_file(st.session_state.project_dir)
    # Sync to project_state for RAG context assembly
    if hasattr(st.session_state, 'project_state'):
        parts = []
        if ctx.get("company"):
            parts.append(ctx["company"])
        if ctx.get("last_enriched_domain"):
            parts.append(f"Domain: {ctx['last_enriched_domain']}")
        if ctx.get("public_context"):
            parts.append(ctx["public_context"])
        if ctx.get("internal_context"):
            parts.append(ctx["internal_context"])
        st.session_state.project_state["org_context"] = "\n".join(parts)
    return f"Org context updated for {input.get('company', 'unknown')} / {input.get('domain', 'unknown')}"
