import json
import streamlit as st
from dotenv import load_dotenv  # load .env before Anthropic client
load_dotenv()

from anthropic import Anthropic
from .tools import handle_tool_call, TOOL_DEFINITIONS
from .prompts import (
    SYSTEM_PROMPT,
    PHASE_A_PROMPT,
    PHASE_B_ORCHESTRATOR_PROMPT,
    PHASE_B_MODE1_PROMPT,
)
from .mode1_knowledge import MODE1_KNOWLEDGE
from .org_context import format_org_context
from .config import MODEL_NAME


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

    # Get original input (first user message)
    original_input = ""
    for m in st.session_state.messages:
        if m["role"] == "user":
            original_input = m["content"]
            break

    # Get rolling conversation summary
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
        # Fallback: continue with safe default
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
        st.session_state.routing_context["mode_turn_count"] = 0

    # Handle complete_mode from Phase A safety net
    if routing.get("next_action") == "complete_mode":
        st.session_state.current_phase = "gathering"
        st.session_state.active_mode = None
        st.session_state.routing_context["mode_turn_count"] = 0

    # Store for debugging
    st.session_state.routing_context["last_routing_decision"] = routing

    return routing


def _run_phase_b(routing_decision: dict) -> str:
    """
    Heavy execution call. Either orchestrator questioning or mode execution.
    Handles tool calls in a loop until the model stops calling tools.
    Returns the final text response.
    """
    org_context_text = format_org_context()

    # Build the appropriate prompt based on active mode
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

    # Context window safety check
    estimated_tokens = len(phase_b_prompt) // 4
    if estimated_tokens > 150000:
        messages = st.session_state.messages
        if len(messages) > 22:
            first_msg = messages[0]
            recent_msgs = messages[-20:]
            truncated = [first_msg, {"role": "assistant", "content": "[...earlier conversation truncated for context length...]"}] + recent_msgs
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

    # Tool use loop with error handling
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
                    # generate_artifact output bypasses model — rendered directly to user
                    if block.name == "generate_artifact":
                        final_text += "\n\n" + result
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

    # Increment mode turn count if in a mode
    if st.session_state.active_mode:
        st.session_state.routing_context["mode_turn_count"] += 1

    # NOTE: probes_fired and patterns_fired are tracked by Phase B via
    # record_probe_fired and record_pattern_fired tools.
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
