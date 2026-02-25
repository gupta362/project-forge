"""Root conftest: MockSessionState and shared fixtures."""

import pytest


class MockSessionState(dict):
    """Dict subclass with attribute access — mirrors Streamlit session_state.

    Supports both st.session_state["key"] and st.session_state.key.
    """

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key)

    def __contains__(self, key):
        return dict.__contains__(self, key)


def _fresh_session_state(**overrides) -> MockSessionState:
    """Build a MockSessionState with the canonical shape from state.py."""
    state = MockSessionState(
        initialized=True,
        messages=[],
        turn_count=0,
        current_phase="gathering",
        active_mode=None,
        assumption_register={},
        assumption_counter=0,
        document_skeleton={
            "problem_statement": None,
            "target_audience": None,
            "stakeholders": {},
            "stakeholder_counter": 0,
            "success_metrics": {"leading": None, "lagging": None, "anti_metric": None},
            "decision_criteria": {"proceed_if": [], "do_not_proceed_if": []},
            "value_estimate": None,
            "constraints": [],
            "proposed_solution": None,
            "prioritization_rationale": None,
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
        },
        routing_context={
            "last_routing_decision": None,
            "probes_fired": [],
            "patterns_fired": [],
            "micro_synthesis_due": False,
            "critical_mass_reached": False,
            "conversation_summary": "",
            "mode_turn_count": 0,
        },
        org_context={
            "company": None,
            "public_context": "",
            "internal_context": "",
            "last_enriched_domain": "",
            "enrichment_count": 0,
        },
        latest_artifact=None,
        pending_questions=None,
        project_name=None,
        project_dir=None,
        is_priming_turn=False,
        rag=None,
        project_state={
            "file_summaries": [],
            "org_context": "",
        },
    )
    state.update(overrides)
    return state


@pytest.fixture
def mock_session_state():
    """Provide a fresh MockSessionState for each test."""
    return _fresh_session_state()
