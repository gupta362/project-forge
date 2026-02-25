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
    PHASE_B_MODE2_PROMPT,
)
from .mode1_knowledge import MODE1_KNOWLEDGE, MODE1_CORE_INSTRUCTIONS
from .mode2_knowledge import MODE2_KNOWLEDGE, MODE2_CORE_INSTRUCTIONS
from .org_context import format_org_context
from . import config
from .config import MODEL_NAME
from .rag import ForgeRAG, _create_chroma_client, _create_voyage_client
from .persistence import save_project, _load_context_file
from .logging_config import setup_logging
logger = setup_logging()


client = Anthropic()


@st.cache_resource
def _get_chroma_client(vectordb_path: str):
    """Cached ChromaDB client singleton — avoids SQLite thread-lock errors."""
    return _create_chroma_client(vectordb_path)


@st.cache_resource
def _get_voyage_client(api_key: str):
    """Cached Voyage AI client singleton."""
    return _create_voyage_client(api_key)


def run_turn(user_message: str) -> str:
    """
    Process one user turn through the two-phase architecture.
    Returns the assistant's response text.
    """
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
        if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
            save_project(st.session_state.project_dir)
        return priming_msg

    st.session_state.turn_count += 1
    logger.info("=== Turn %d start ===", st.session_state.turn_count)

    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": user_message})

    # Re-read context.md to capture manual edits
    if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        _load_context_file(st.session_state.project_dir)

    # Initialize RAG if needed (uses @st.cache_resource singletons from app.py)
    if st.session_state.project_dir and st.session_state.rag is None:
        try:
            chroma = _get_chroma_client(str(st.session_state.project_dir / "vectordb"))
            voyage = _get_voyage_client(config.VOYAGE_API_KEY) if config.VOYAGE_API_KEY else None
            st.session_state.rag = ForgeRAG(
                st.session_state.project_dir,
                chroma_client=chroma,
                voyage_client=voyage,
            )
        except Exception as e:
            logger.warning("RAG initialization failed: %s", e)

    # --- PHASE A: Route ---
    routing_decision = _run_phase_a(user_message)

    # --- Context Assembly (with retrieval bypass for filler turns) ---
    assembled = None
    if st.session_state.rag and st.session_state.rag.enabled:
        if routing_decision.get("requires_retrieval", True):
            assembled = st.session_state.rag.assemble_context(
                user_message=user_message,
                phase_a_decision=routing_decision,
                current_turn=st.session_state.turn_count,
                project_state=st.session_state.project_state,
            )
        else:
            assembled = st.session_state.rag.assemble_context_minimal(
                phase_a_decision=routing_decision,
                current_turn=st.session_state.turn_count,
                project_state=st.session_state.project_state,
            )
            logger.info("Retrieval bypassed — filler turn detected by Phase A")

    # --- PHASE B: Act ---
    response_text = _run_phase_b(routing_decision, assembled_context=assembled)

    # Add assistant response to history
    st.session_state.messages.append({"role": "assistant", "content": response_text})

    # --- POST-TURN: Update routing context ---
    _post_turn_updates(routing_decision, user_message, response_text)

    # Auto-save project state
    if hasattr(st.session_state, 'project_dir') and st.session_state.project_dir:
        save_project(st.session_state.project_dir)
        logger.info("Auto-saved state to %s", st.session_state.project_dir)

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

        logger.debug(
            "API usage - input_tokens: %d, output_tokens: %d, stop_reason: %s",
            response.usage.input_tokens, response.usage.output_tokens, response.stop_reason,
        )

        # Parse JSON from response
        raw = response.content[0].text.strip()
        # Handle potential markdown code fence
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        routing = json.loads(raw)
        logger.info("Phase A decision: %s", json.dumps(routing))
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
            "requires_retrieval": True,
        }

    # Handle mode entry
    if routing.get("enter_mode") == "mode_1" and st.session_state.active_mode != "mode_1":
        st.session_state.current_phase = "mode_active"
        st.session_state.active_mode = "mode_1"
        st.session_state.routing_context["critical_mass_reached"] = True
        st.session_state.routing_context["mode_turn_count"] = 0
    elif routing.get("enter_mode") == "mode_2" and st.session_state.active_mode != "mode_2":
        st.session_state.current_phase = "mode_active"
        st.session_state.active_mode = "mode_2"
        st.session_state.routing_context["mode_turn_count"] = 0

    # Handle complete_mode from Phase A safety net
    if routing.get("next_action") == "complete_mode":
        st.session_state.current_phase = "gathering"
        st.session_state.active_mode = None
        st.session_state.routing_context["mode_turn_count"] = 0

    # Store for debugging
    st.session_state.routing_context["last_routing_decision"] = routing

    return routing


def _run_phase_b(routing_decision: dict, assembled_context: dict | None = None) -> str:
    """
    Heavy execution call. Either orchestrator questioning or mode execution.
    Handles tool calls in a loop until the model stops calling tools.
    Returns the final text response.

    If assembled_context is provided (RAG enabled), uses targeted context
    instead of full knowledge base dumps. Falls back to legacy behavior
    when assembled_context is None.
    """
    logger.info("Phase B executing: %s", st.session_state.active_mode or "orchestrator")

    phase_b_prompt = _build_phase_b_prompt(routing_decision, assembled_context)

    # Context window safety check
    estimated_tokens = len(phase_b_prompt) // 4
    if estimated_tokens > 150000:
        messages = st.session_state.messages
        if len(messages) > 22:
            first_msg = messages[0]
            recent_msgs = messages[-20:]
            truncated = [first_msg, {"role": "assistant", "content": "[...earlier conversation truncated for context length...]"}] + recent_msgs
            phase_b_prompt = _build_phase_b_prompt(
                routing_decision, assembled_context, messages_override=truncated
            )

    # Build messages for API call
    api_messages = [{"role": "user", "content": phase_b_prompt}]

    # Tool use loop with error handling
    final_text = ""
    try:
        while True:
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=8096,
                system=SYSTEM_PROMPT,
                messages=api_messages,
                tools=TOOL_DEFINITIONS,
            )
            logger.debug(
                "API usage - input_tokens: %d, output_tokens: %d, stop_reason: %s",
                response.usage.input_tokens, response.usage.output_tokens, response.stop_reason,
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

    # Safety net: if tool calls consumed all tokens and no text was generated
    if not final_text.strip():
        logger.warning("Phase B returned empty response — likely token exhaustion from tool calls")
        final_text = "I processed your input but couldn't generate a visible response. This usually means the analysis was very detailed — please try asking a follow-up question."

    return final_text


def _build_phase_b_prompt(
    routing_decision: dict,
    assembled_context: dict | None = None,
    messages_override: list | None = None,
) -> str:
    """Build the Phase B prompt, using assembled context when available.

    If assembled_context is None, falls back to legacy behavior (full
    knowledge base, full org context). This ensures the app works
    without RAG configured.
    """
    messages = messages_override or st.session_state.messages

    if assembled_context is not None:
        # --- RAG-enhanced path: targeted context ---
        if st.session_state.active_mode == "mode_1":
            return PHASE_B_MODE1_PROMPT.format(
                phase_a_output=json.dumps(routing_decision, indent=2),
                full_messages=_format_messages(messages),
                full_assumptions=_format_assumptions(),
                document_skeleton=_format_skeleton(),
                org_context=assembled_context["context_block"],
                mode1_knowledge=(
                    MODE1_CORE_INSTRUCTIONS
                    + _assembled_sections(assembled_context)
                ),
                turn_count=st.session_state.turn_count,
                is_first_mode_turn=(st.session_state.routing_context["mode_turn_count"] == 0),
            )
        elif st.session_state.active_mode == "mode_2":
            return PHASE_B_MODE2_PROMPT.format(
                phase_a_output=json.dumps(routing_decision, indent=2),
                full_messages=_format_messages(messages),
                full_assumptions=_format_assumptions(),
                document_skeleton=_format_skeleton(),
                org_context=assembled_context["context_block"],
                mode2_knowledge=(
                    MODE2_CORE_INSTRUCTIONS
                    + _assembled_sections(assembled_context)
                ),
                turn_count=st.session_state.turn_count,
                is_first_mode_turn=(st.session_state.routing_context["mode_turn_count"] == 0),
            )
        else:
            return PHASE_B_ORCHESTRATOR_PROMPT.format(
                phase_a_output=json.dumps(routing_decision, indent=2),
                full_messages=_format_messages(messages),
                org_context=assembled_context["context_block"],
                turn_count=st.session_state.turn_count,
            )
    else:
        # --- Legacy path: full knowledge base (no RAG) ---
        org_context_text = format_org_context()
        if st.session_state.active_mode == "mode_1":
            return PHASE_B_MODE1_PROMPT.format(
                phase_a_output=json.dumps(routing_decision, indent=2),
                full_messages=_format_messages(messages),
                full_assumptions=_format_assumptions(),
                document_skeleton=_format_skeleton(),
                org_context=org_context_text,
                mode1_knowledge=MODE1_KNOWLEDGE,
                turn_count=st.session_state.turn_count,
                is_first_mode_turn=(st.session_state.routing_context["mode_turn_count"] == 0),
            )
        elif st.session_state.active_mode == "mode_2":
            return PHASE_B_MODE2_PROMPT.format(
                phase_a_output=json.dumps(routing_decision, indent=2),
                full_messages=_format_messages(messages),
                full_assumptions=_format_assumptions(),
                document_skeleton=_format_skeleton(),
                org_context=org_context_text,
                mode2_knowledge=MODE2_KNOWLEDGE,
                turn_count=st.session_state.turn_count,
                is_first_mode_turn=(st.session_state.routing_context["mode_turn_count"] == 0),
            )
        else:
            return PHASE_B_ORCHESTRATOR_PROMPT.format(
                phase_a_output=json.dumps(routing_decision, indent=2),
                full_messages=_format_messages(messages),
                org_context=org_context_text,
                turn_count=st.session_state.turn_count,
            )


def _assembled_sections(assembled_context: dict) -> str:
    """Format the assembled RAG context sections for prompt injection."""
    parts = []
    if assembled_context["probe_content"]:
        parts.append(f"\n\n## Active Probe\n{assembled_context['probe_content']}")
    if assembled_context["pattern_content"]:
        parts.append(f"\n\n## Triggered Patterns\n{assembled_context['pattern_content']}")
    if assembled_context["retrieved_documents"]:
        parts.append(f"\n\n## Retrieved Document Context\n{assembled_context['retrieved_documents']}")
    if assembled_context["retrieved_conversations"]:
        parts.append(f"\n\n## Earlier Relevant Exchanges\n{assembled_context['retrieved_conversations']}")
    return "".join(parts)


def _post_turn_updates(routing_decision: dict, user_message: str = "", assistant_response: str = ""):
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

    # Generate turn summary and index in ChromaDB (for future retrieval)
    if st.session_state.rag and st.session_state.rag.enabled:
        if st.session_state.turn_count > config.ALWAYS_ON_TURN_WINDOW:
            try:
                summary = _generate_turn_summary(user_message, assistant_response)
                st.session_state.rag.index_turn(
                    turn_number=st.session_state.turn_count,
                    user_message=user_message,
                    assistant_response=assistant_response,
                    turn_summary=summary,
                    active_probe=st.session_state.routing_context.get("active_probe", ""),
                    active_mode=st.session_state.active_mode or "",
                )
            except Exception as e:
                logger.warning("Turn indexing failed: %s", e)


def _generate_turn_summary(user_message: str, assistant_response: str) -> str:
    """Generate 1-2 sentence summary of a completed turn via Haiku.

    Uses the same Anthropic client as all other API calls — just points
    to TURN_SUMMARY_MODEL (Haiku) instead of MODEL_NAME (Sonnet).
    """
    response = client.messages.create(
        model=config.TURN_SUMMARY_MODEL,
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": (
                "Summarize this conversation exchange in 1-2 sentences. "
                "Focus on what was discussed and any decisions or assumptions made.\n\n"
                f"User: {user_message[:1000]}\n\n"
                f"Assistant: {assistant_response[:1000]}"
            ),
        }],
    )
    return response.content[0].text


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


def _format_user_input(user_message: str) -> str:
    """Wrap large user inputs in XML tags for instruction isolation."""
    if len(user_message) > 500:
        return f"<user_context>\n{user_message}\n</user_context>"
    return user_message


def _format_messages(messages: list) -> str:
    """Format message history for prompt injection."""
    formatted = []
    for m in messages:
        content = _format_user_input(m["content"]) if m["role"] == "user" else m["content"]
        formatted.append(f"**{m['role'].upper()}:** {content}")
    return "\n\n".join(formatted)


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
    # Mode 2 fields
    if s.get("solution_name"):
        parts.append(f"Solution: {s['solution_name']}")
    if s.get("solution_description"):
        parts.append(f"Description: {s['solution_description']}")
    for dim in ["value", "usability", "feasibility", "viability"]:
        level = s.get(f"{dim}_risk_level")
        if level:
            summary = s.get(f"{dim}_risk_summary", "")
            parts.append(f"{dim.title()} Risk: {level} — {summary}")
    rec = s.get("go_no_go_recommendation")
    if rec:
        parts.append(f"Go/No-Go: {rec}")
    return "\n".join(parts) if parts else "Document skeleton is empty."
