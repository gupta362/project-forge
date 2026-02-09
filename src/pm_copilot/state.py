import streamlit as st


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
            "conversation_summary": "",  # Rolling summary written by Phase B after each turn
            "mode_turn_count": 0,  # Turns since current mode was entered
        }
        st.session_state.org_context = {  # Dynamic enrichment
            "company": None,           # Detected company name
            "public_context": "",      # Model-knowledge-based public context
            "internal_context": "",    # User-provided internal details
            "last_enriched_domain": "",  # What domain/area the last enrichment covered
            "enrichment_count": 0,     # How many times we've enriched (cap at 3)
        }
        st.session_state.latest_artifact = None  # Rendered markdown from generate_artifact
