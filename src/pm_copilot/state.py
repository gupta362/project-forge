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
            # Mode 2 fields — flat keys, no nesting
            "solution_name": None,
            "solution_description": None,
            "value_risk_level": None,
            "value_risk_summary": None,
            "value_risk_evidence_for": [],
            "value_risk_evidence_against": [],
            "usability_risk_level": None,
            "usability_risk_summary": None,
            "usability_risk_evidence_for": [],
            "usability_risk_evidence_against": [],
            "feasibility_risk_level": None,
            "feasibility_risk_summary": None,
            "feasibility_risk_evidence_for": [],
            "feasibility_risk_evidence_against": [],
            "viability_risk_level": None,
            "viability_risk_summary": None,
            "viability_risk_evidence_for": [],
            "viability_risk_evidence_against": [],
            "build_vs_buy_assessment": None,
            "validation_riskiest_assumption": None,
            "validation_approach": None,
            "validation_description": None,
            "validation_timeline": None,
            "validation_success_criteria": None,
            "go_no_go_recommendation": None,
            "go_no_go_conditions": [],
            "go_no_go_dealbreakers": [],
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
        st.session_state.pending_questions = None  # Questions from latest assistant response for checkbox UI
        st.session_state.project_name = None
        st.session_state.project_dir = None
        st.session_state.is_priming_turn = False
        st.session_state.rag = None  # ForgeRAG instance (transient, not persisted)
        st.session_state.project_state = {  # Persisted in project_state.json
            "file_summaries": [],
            "org_context": "",
        }
