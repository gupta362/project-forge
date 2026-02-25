"""Unit tests for pm_copilot.tools — 18 tool handlers + dispatch."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pm_copilot.tools import handle_tool_call


# ===================================================================
# handle_tool_call dispatch
# ===================================================================


class TestHandleToolCall:
    def test_dispatch_to_correct_handler(self, mock_session_state_for_tools):
        result = handle_tool_call("update_problem_statement", {"text": "We need X"})
        assert result == "Problem statement updated"
        assert mock_session_state_for_tools.document_skeleton["problem_statement"] == "We need X"

    def test_unknown_tool_returns_error(self, mock_session_state_for_tools):
        result = handle_tool_call("nonexistent_tool", {})
        assert "Unknown tool" in result


# ===================================================================
# register_assumption
# ===================================================================


class TestRegisterAssumption:
    def test_auto_id_a1(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        result = handle_tool_call("register_assumption", {
            "claim": "Users want this feature",
            "type": "value",
            "impact": "high",
            "confidence": "guessed",
            "basis": "Gut feeling",
            "surfaced_by": "Mode 1: Probe 1",
        })
        assert "A1" in result
        assert ss.assumption_counter == 1
        assert "A1" in ss.assumption_register

    def test_counter_increments(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        for i in range(3):
            handle_tool_call("register_assumption", {
                "claim": f"Claim {i}",
                "type": "value",
                "impact": "low",
                "confidence": "guessed",
                "basis": "test",
                "surfaced_by": "test",
            })
        assert ss.assumption_counter == 3
        assert set(ss.assumption_register.keys()) == {"A1", "A2", "A3"}

    def test_dependency_graph_wiring(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("register_assumption", {
            "claim": "Base assumption",
            "type": "value", "impact": "high", "confidence": "guessed",
            "basis": "test", "surfaced_by": "test",
        })
        handle_tool_call("register_assumption", {
            "claim": "Depends on A1",
            "type": "value", "impact": "high", "confidence": "guessed",
            "basis": "test", "surfaced_by": "test",
            "depends_on": ["A1"],
        })
        assert "A2" in ss.assumption_register["A1"]["dependents"]
        assert ss.assumption_register["A2"]["depends_on"] == ["A1"]

    def test_nonexistent_dependency_silent(self, mock_session_state_for_tools):
        """Depending on a nonexistent ID should not crash."""
        result = handle_tool_call("register_assumption", {
            "claim": "Orphan dep",
            "type": "value", "impact": "low", "confidence": "guessed",
            "basis": "test", "surfaced_by": "test",
            "depends_on": ["A999"],
        })
        assert "A1" in result

    def test_optional_fields_default(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("register_assumption", {
            "claim": "Simple",
            "type": "value", "impact": "low", "confidence": "guessed",
            "basis": "test", "surfaced_by": "test",
        })
        a = ss.assumption_register["A1"]
        assert a["recommended_action"] == ""
        assert a["implied_stakeholders"] == []
        assert a["depends_on"] == []


# ===================================================================
# update_assumption_status + cascade
# ===================================================================


class TestUpdateAssumptionStatus:
    def _register_two(self, ss):
        """Register A1 and A2 where A2 depends on A1."""
        handle_tool_call("register_assumption", {
            "claim": "Base", "type": "value", "impact": "high",
            "confidence": "guessed", "basis": "test", "surfaced_by": "test",
        })
        handle_tool_call("register_assumption", {
            "claim": "Dep", "type": "value", "impact": "high",
            "confidence": "guessed", "basis": "test", "surfaced_by": "test",
            "depends_on": ["A1"],
        })

    def test_changes_status(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        self._register_two(ss)
        handle_tool_call("update_assumption_status", {
            "assumption_id": "A1", "new_status": "confirmed", "reason": "verified"
        })
        assert ss.assumption_register["A1"]["status"] == "confirmed"

    def test_not_found(self, mock_session_state_for_tools):
        result = handle_tool_call("update_assumption_status", {
            "assumption_id": "A999", "new_status": "confirmed", "reason": "nope"
        })
        assert "not found" in result

    def test_invalidation_cascade(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        self._register_two(ss)
        result = handle_tool_call("update_assumption_status", {
            "assumption_id": "A1", "new_status": "invalidated",
            "reason": "proven wrong"
        })
        assert ss.assumption_register["A2"]["status"] == "at_risk"
        assert "⚠️" in ss.assumption_register["A2"]["basis"]
        assert "Cascade" in result

    def test_confirmation_upgrade_guessed_to_informed(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        self._register_two(ss)
        result = handle_tool_call("update_assumption_status", {
            "assumption_id": "A1", "new_status": "confirmed", "reason": "validated"
        })
        assert ss.assumption_register["A2"]["confidence"] == "informed"
        assert "Cascade" in result

    def test_confirmation_does_not_upgrade_informed(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        self._register_two(ss)
        ss.assumption_register["A2"]["confidence"] = "informed"
        handle_tool_call("update_assumption_status", {
            "assumption_id": "A1", "new_status": "confirmed", "reason": "validated"
        })
        assert ss.assumption_register["A2"]["confidence"] == "informed"

    def test_invalidation_does_not_cascade_to_non_active(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        self._register_two(ss)
        ss.assumption_register["A2"]["status"] = "invalidated"
        handle_tool_call("update_assumption_status", {
            "assumption_id": "A1", "new_status": "invalidated",
            "reason": "proven wrong"
        })
        # A2 was already invalidated, should not change to at_risk
        assert ss.assumption_register["A2"]["status"] == "invalidated"


# ===================================================================
# update_assumption_confidence
# ===================================================================


class TestUpdateAssumptionConfidence:
    def test_changes_confidence(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("register_assumption", {
            "claim": "test", "type": "value", "impact": "low",
            "confidence": "guessed", "basis": "test", "surfaced_by": "test",
        })
        handle_tool_call("update_assumption_confidence", {
            "assumption_id": "A1", "new_confidence": "validated", "reason": "proved"
        })
        assert ss.assumption_register["A1"]["confidence"] == "validated"

    def test_not_found(self, mock_session_state_for_tools):
        result = handle_tool_call("update_assumption_confidence", {
            "assumption_id": "A999", "new_confidence": "validated", "reason": "nope"
        })
        assert "not found" in result


# ===================================================================
# Skeleton tools
# ===================================================================


class TestSkeletonTools:
    def test_update_problem_statement_set(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_problem_statement", {"text": "Problem X"})
        assert ss.document_skeleton["problem_statement"] == "Problem X"

    def test_update_problem_statement_overwrite(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_problem_statement", {"text": "First"})
        handle_tool_call("update_problem_statement", {"text": "Second"})
        assert ss.document_skeleton["problem_statement"] == "Second"

    def test_update_target_audience(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_target_audience", {"text": "PMs at mid-size"})
        assert ss.document_skeleton["target_audience"] == "PMs at mid-size"

    def test_add_stakeholder_auto_id(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        result = handle_tool_call("add_stakeholder", {
            "name": "VP Marketing", "type": "decision_authority",
        })
        assert "S1" in result
        s = ss.document_skeleton["stakeholders"]["S1"]
        assert s["name"] == "VP Marketing"
        assert s["validated"] is False
        assert s["notes"] == ""

    def test_add_stakeholder_optional_fields(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("add_stakeholder", {
            "name": "CTO", "type": "execution_dependency",
            "validated": True, "notes": "Owns infra budget",
        })
        s = ss.document_skeleton["stakeholders"]["S1"]
        assert s["validated"] is True
        assert s["notes"] == "Owns infra budget"

    def test_update_success_metrics_partial(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_success_metrics", {"leading": "NPS > 50"})
        assert ss.document_skeleton["success_metrics"]["leading"] == "NPS > 50"
        assert ss.document_skeleton["success_metrics"]["lagging"] is None

    def test_update_success_metrics_preserves_existing(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_success_metrics", {"leading": "NPS"})
        handle_tool_call("update_success_metrics", {"lagging": "Revenue"})
        assert ss.document_skeleton["success_metrics"]["leading"] == "NPS"
        assert ss.document_skeleton["success_metrics"]["lagging"] == "Revenue"

    def test_add_decision_criteria_appends(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("add_decision_criteria", {
            "criteria_type": "proceed_if", "condition": "Market size > 1M"
        })
        handle_tool_call("add_decision_criteria", {
            "criteria_type": "proceed_if", "condition": "ROI > 20%"
        })
        assert len(ss.document_skeleton["decision_criteria"]["proceed_if"]) == 2

    def test_add_decision_criteria_do_not_proceed(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("add_decision_criteria", {
            "criteria_type": "do_not_proceed_if", "condition": "Regulatory block"
        })
        assert "Regulatory block" in ss.document_skeleton["decision_criteria"]["do_not_proceed_if"]


# ===================================================================
# generate_artifact
# ===================================================================


class TestGenerateArtifact:
    def _populate_skeleton(self, ss):
        """Populate skeleton with enough data for a valid artifact."""
        handle_tool_call("update_problem_statement", {"text": "Users can't X"})
        handle_tool_call("update_target_audience", {"text": "PMs"})
        handle_tool_call("add_stakeholder", {
            "name": "VP", "type": "decision_authority"
        })
        handle_tool_call("update_success_metrics", {"leading": "NPS"})
        handle_tool_call("add_decision_criteria", {
            "criteria_type": "proceed_if", "condition": "Market > 1M"
        })
        handle_tool_call("register_assumption", {
            "claim": "Users want X",
            "type": "value", "impact": "high", "confidence": "guessed",
            "basis": "Interviews", "surfaced_by": "Probe 1",
        })

    def test_problem_brief_populated(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        self._populate_skeleton(ss)
        result = handle_tool_call("generate_artifact", {
            "artifact_type": "problem_brief"
        })
        assert "# Problem Brief" in result
        assert "Users can't X" in result
        assert ss.latest_artifact == result

    def test_problem_brief_empty_warning(self, mock_session_state_for_tools):
        result = handle_tool_call("generate_artifact", {
            "artifact_type": "problem_brief"
        })
        assert result.startswith("WARNING:")
        assert "problem_statement" in result

    def test_problem_brief_filters_active_only(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        self._populate_skeleton(ss)
        # Invalidate the assumption
        ss.assumption_register["A1"]["status"] = "invalidated"
        result = handle_tool_call("generate_artifact", {
            "artifact_type": "problem_brief"
        })
        # Invalidated assumptions should not appear in the table
        assert "A1" not in result or "invalidated" not in result

    def test_solution_evaluation_brief(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("set_solution_info", {
            "solution_name": "Widget Pro",
            "solution_description": "A better widget",
        })
        handle_tool_call("set_risk_assessment", {
            "dimension": "value", "level": "low",
            "summary": "Strong demand signals",
        })
        handle_tool_call("set_go_no_go", {
            "recommendation": "go",
            "conditions": ["Market validated"],
            "dealbreakers": ["Regulatory block"],
        })
        result = handle_tool_call("generate_artifact", {
            "artifact_type": "solution_evaluation_brief"
        })
        assert "Widget Pro" in result
        assert "GO" in result

    def test_unknown_artifact_type(self, mock_session_state_for_tools):
        result = handle_tool_call("generate_artifact", {
            "artifact_type": "unknown_type"
        })
        assert "Unknown artifact type" in result

    @patch("pm_copilot.tools._write_context_file")
    def test_auto_saves_to_project_dir(self, mock_write, mock_session_state_for_tools, tmp_path):
        ss = mock_session_state_for_tools
        ss.project_dir = tmp_path
        self._populate_skeleton(ss)
        handle_tool_call("generate_artifact", {"artifact_type": "problem_brief"})
        assert (tmp_path / "artifacts" / "problem_brief.md").exists()


# ===================================================================
# Mode 2 tools
# ===================================================================


class TestMode2Tools:
    def test_set_risk_assessment_all_dimensions(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        for dim in ["value", "usability", "feasibility", "viability"]:
            handle_tool_call("set_risk_assessment", {
                "dimension": dim, "level": "medium",
                "summary": f"{dim} is moderate",
                "evidence_for": ["good signal"],
                "evidence_against": ["concern"],
            })
            assert ss.document_skeleton[f"{dim}_risk_level"] == "medium"
            assert ss.document_skeleton[f"{dim}_risk_evidence_for"] == ["good signal"]

    def test_set_validation_plan(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("set_validation_plan", {
            "riskiest_assumption": "A5",
            "approach": "painted_door",
            "description": "Test landing page",
            "success_criteria": "10% click-through",
        })
        assert ss.document_skeleton["validation_approach"] == "painted_door"
        assert ss.document_skeleton["validation_riskiest_assumption"] == "A5"

    def test_set_go_no_go(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("set_go_no_go", {
            "recommendation": "conditional_go",
            "conditions": ["Validate assumption A1"],
            "dealbreakers": ["Budget cut"],
        })
        assert ss.document_skeleton["go_no_go_recommendation"] == "conditional_go"
        assert len(ss.document_skeleton["go_no_go_conditions"]) == 1

    def test_set_solution_info(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("set_solution_info", {
            "solution_name": "Acme Widget",
            "solution_description": "Does stuff",
            "build_vs_buy": "Build — unique domain",
        })
        assert ss.document_skeleton["solution_name"] == "Acme Widget"
        assert ss.document_skeleton["build_vs_buy_assessment"] == "Build — unique domain"

    def test_set_solution_info_no_build_vs_buy(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("set_solution_info", {
            "solution_name": "Simple",
            "solution_description": "Basic tool",
        })
        assert ss.document_skeleton["build_vs_buy_assessment"] is None


# ===================================================================
# Routing tools
# ===================================================================


class TestRoutingTools:
    def test_record_probe_fired(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        ss.turn_count = 5
        handle_tool_call("record_probe_fired", {
            "probe_name": "Probe 1: Solution-Problem Separation",
            "summary": "User described solution not problem",
        })
        assert len(ss.routing_context["probes_fired"]) == 1
        assert ss.routing_context["probes_fired"][0]["name"] == "Probe 1: Solution-Problem Separation"
        assert ss.routing_context["probes_fired"][0]["turn"] == 5

    def test_record_pattern_fired(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        ss.turn_count = 3
        handle_tool_call("record_pattern_fired", {
            "pattern_name": "Pattern 1: Analytics-Execution Gap",
            "trigger_reason": "User mentions dashboards but no action",
        })
        assert len(ss.routing_context["patterns_fired"]) == 1
        assert ss.routing_context["patterns_fired"][0]["turn"] == 3

    def test_update_conversation_summary(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_conversation_summary", {
            "summary": "User described a metrics problem."
        })
        assert ss.routing_context["conversation_summary"] == "User described a metrics problem."

    def test_update_conversation_summary_overwrites(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_conversation_summary", {"summary": "First"})
        handle_tool_call("update_conversation_summary", {"summary": "Second"})
        assert ss.routing_context["conversation_summary"] == "Second"


# ===================================================================
# complete_mode
# ===================================================================


class TestCompleteMode:
    def test_resets_phase_and_mode(self, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        ss.current_phase = "mode_active"
        ss.active_mode = "mode_1"
        ss.routing_context["mode_turn_count"] = 5
        # Add some state that should persist
        handle_tool_call("register_assumption", {
            "claim": "test", "type": "value", "impact": "low",
            "confidence": "guessed", "basis": "test", "surfaced_by": "test",
        })
        handle_tool_call("complete_mode", {
            "mode_completed": "mode_1",
            "summary": "Analysis complete",
        })
        assert ss.current_phase == "gathering"
        assert ss.active_mode is None
        assert ss.routing_context["mode_turn_count"] == 0
        # Assumptions persist
        assert "A1" in ss.assumption_register


# ===================================================================
# update_org_context
# ===================================================================


class TestUpdateOrgContext:
    @patch("pm_copilot.tools._write_context_file")
    def test_sets_company(self, mock_write, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_org_context", {
            "company": "Acme Corp", "domain": "SaaS",
        })
        assert ss.org_context["company"] == "Acme Corp"

    @patch("pm_copilot.tools._write_context_file")
    def test_appends_public_context(self, mock_write, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_org_context", {
            "company": "Acme", "domain": "SaaS",
            "public_context": "First batch",
        })
        handle_tool_call("update_org_context", {
            "company": "Acme", "domain": "SaaS",
            "public_context": "Second batch",
        })
        assert "First batch\n\nSecond batch" == ss.org_context["public_context"]

    @patch("pm_copilot.tools._write_context_file")
    def test_appends_internal_context(self, mock_write, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_org_context", {
            "company": "Acme", "domain": "SaaS",
            "internal_context": "Internal A",
        })
        handle_tool_call("update_org_context", {
            "company": "Acme", "domain": "SaaS",
            "internal_context": "Internal B",
        })
        assert "Internal A\n\nInternal B" == ss.org_context["internal_context"]

    @patch("pm_copilot.tools._write_context_file")
    def test_increments_enrichment_count(self, mock_write, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_org_context", {
            "company": "Acme", "domain": "SaaS",
        })
        handle_tool_call("update_org_context", {
            "company": "Acme", "domain": "Marketing",
        })
        assert ss.org_context["enrichment_count"] == 2

    @patch("pm_copilot.tools._write_context_file")
    def test_syncs_to_project_state(self, mock_write, mock_session_state_for_tools):
        ss = mock_session_state_for_tools
        handle_tool_call("update_org_context", {
            "company": "Acme", "domain": "SaaS",
            "public_context": "Public info",
        })
        assert "Acme" in ss.project_state["org_context"]
        assert "Public info" in ss.project_state["org_context"]
