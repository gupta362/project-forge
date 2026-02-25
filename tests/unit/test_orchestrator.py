"""Unit tests for pm_copilot.orchestrator — 2-phase engine + post-turn updates."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from tests.conftest import _fresh_session_state
from tests.unit.conftest import _make_anthropic_response


# We need to patch st and client at module level for orchestrator imports
# Use a module-scoped approach: import orchestrator functions after patching


# ===================================================================
# Helpers
# ===================================================================


@pytest.fixture
def orch_env(mock_session_state_for_orchestrator, mock_anthropic_client):
    """Full orchestrator test environment with patched st + client + persistence."""
    ss = mock_session_state_for_orchestrator
    with patch("pm_copilot.orchestrator.client", mock_anthropic_client), \
         patch("pm_copilot.orchestrator.save_project"), \
         patch("pm_copilot.orchestrator._load_context_file"), \
         patch("pm_copilot.orchestrator.format_org_context", return_value="Mocked org context"):
        from pm_copilot.orchestrator import (
            run_turn,
            _run_phase_a,
            _run_phase_b,
            _build_phase_b_prompt,
            _post_turn_updates,
            _build_assumption_summary,
            _format_messages,
            _format_skeleton,
        )
        yield SimpleNamespace(
            ss=ss,
            client=mock_anthropic_client,
            run_turn=run_turn,
            _run_phase_a=_run_phase_a,
            _run_phase_b=_run_phase_b,
            _build_phase_b_prompt=_build_phase_b_prompt,
            _post_turn_updates=_post_turn_updates,
            _build_assumption_summary=_build_assumption_summary,
            _format_messages=_format_messages,
            _format_skeleton=_format_skeleton,
        )


def _routing_json(overrides=None):
    """Build a valid Phase A routing JSON response."""
    default = {
        "next_action": "ask_questions",
        "enter_mode": None,
        "reasoning": "test",
        "conflict_flags": [],
        "high_risk_unprobed": [],
        "suggested_probes": [],
        "micro_synthesis_due": False,
        "enrichment_needed": False,
        "enrichment_query": "",
        "requires_retrieval": True,
    }
    if overrides:
        default.update(overrides)
    return default


# ===================================================================
# run_turn
# ===================================================================


class TestRunTurn:
    def test_priming_turn_bypass(self, orch_env):
        ss = orch_env.ss
        ss.is_priming_turn = True
        result = orch_env.run_turn("__PRIMING_TURN__")
        assert "New project started" in result
        assert ss.is_priming_turn is False
        assert ss.turn_count == 1

    def test_normal_turn_increments_count(self, orch_env):
        ss = orch_env.ss
        # Phase A returns valid JSON routing
        routing = _routing_json()
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            json.dumps(routing)
        )
        orch_env.run_turn("Hello, I need help with a product problem")
        assert ss.turn_count == 1

    def test_appends_user_and_assistant_messages(self, orch_env):
        ss = orch_env.ss
        routing = _routing_json()
        # Phase A returns routing JSON, Phase B returns text
        orch_env.client.messages.create.side_effect = [
            _make_anthropic_response(json.dumps(routing)),  # Phase A
            _make_anthropic_response("I understand your problem."),  # Phase B
        ]
        orch_env.run_turn("My problem is X")
        assert ss.messages[0]["role"] == "user"
        assert ss.messages[0]["content"] == "My problem is X"
        assert ss.messages[1]["role"] == "assistant"

    def test_assembles_rag_context_when_requires_retrieval(self, orch_env):
        ss = orch_env.ss
        mock_rag = MagicMock()
        mock_rag.enabled = True
        mock_rag.assemble_context.return_value = {
            "context_block": "", "probe_content": "",
            "pattern_content": "", "retrieved_documents": "",
            "retrieved_conversations": "",
        }
        ss.rag = mock_rag
        ss.project_dir = Path("/fake")

        routing = _routing_json({"requires_retrieval": True})
        orch_env.client.messages.create.side_effect = [
            _make_anthropic_response(json.dumps(routing)),
            _make_anthropic_response("Response"),
        ]
        orch_env.run_turn("question")
        mock_rag.assemble_context.assert_called_once()

    def test_uses_minimal_when_no_retrieval(self, orch_env):
        ss = orch_env.ss
        mock_rag = MagicMock()
        mock_rag.enabled = True
        mock_rag.assemble_context_minimal.return_value = {
            "context_block": "", "probe_content": "",
            "pattern_content": "", "retrieved_documents": "",
            "retrieved_conversations": "",
        }
        ss.rag = mock_rag
        ss.project_dir = Path("/fake")

        routing = _routing_json({"requires_retrieval": False})
        orch_env.client.messages.create.side_effect = [
            _make_anthropic_response(json.dumps(routing)),
            _make_anthropic_response("Response"),
        ]
        orch_env.run_turn("filler")
        mock_rag.assemble_context_minimal.assert_called_once()


# ===================================================================
# _run_phase_a
# ===================================================================


class TestRunPhaseA:
    def test_returns_parsed_routing_dict(self, orch_env):
        routing = _routing_json()
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            json.dumps(routing)
        )
        orch_env.ss.messages.append({"role": "user", "content": "test"})
        result = orch_env._run_phase_a("test")
        assert result["next_action"] == "ask_questions"

    def test_handles_json_in_markdown_fence(self, orch_env):
        routing = _routing_json()
        fenced = f"```json\n{json.dumps(routing)}\n```"
        orch_env.client.messages.create.return_value = _make_anthropic_response(fenced)
        orch_env.ss.messages.append({"role": "user", "content": "test"})
        result = orch_env._run_phase_a("test")
        assert result["next_action"] == "ask_questions"

    def test_fallback_on_json_parse_error(self, orch_env):
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            "This is not JSON at all"
        )
        orch_env.ss.messages.append({"role": "user", "content": "test"})
        result = orch_env._run_phase_a("test")
        assert result["next_action"] == "ask_questions"
        assert "error" in result["reasoning"].lower() or "fallback" in result["reasoning"].lower()

    def test_fallback_on_api_error(self, orch_env):
        orch_env.client.messages.create.side_effect = RuntimeError("API down")
        orch_env.ss.messages.append({"role": "user", "content": "test"})
        result = orch_env._run_phase_a("test")
        assert result["next_action"] == "ask_questions"

    def test_enters_mode_1(self, orch_env):
        ss = orch_env.ss
        routing = _routing_json({"enter_mode": "mode_1"})
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            json.dumps(routing)
        )
        ss.messages.append({"role": "user", "content": "test"})
        orch_env._run_phase_a("test")
        assert ss.active_mode == "mode_1"
        assert ss.current_phase == "mode_active"

    def test_enters_mode_2(self, orch_env):
        ss = orch_env.ss
        routing = _routing_json({"enter_mode": "mode_2"})
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            json.dumps(routing)
        )
        ss.messages.append({"role": "user", "content": "test"})
        orch_env._run_phase_a("test")
        assert ss.active_mode == "mode_2"

    def test_does_not_reenter_already_active_mode(self, orch_env):
        ss = orch_env.ss
        ss.active_mode = "mode_1"
        ss.current_phase = "mode_active"
        ss.routing_context["mode_turn_count"] = 5
        routing = _routing_json({"enter_mode": "mode_1"})
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            json.dumps(routing)
        )
        ss.messages.append({"role": "user", "content": "test"})
        orch_env._run_phase_a("test")
        # mode_turn_count should NOT be reset
        assert ss.routing_context["mode_turn_count"] == 5

    def test_complete_mode_safety_net(self, orch_env):
        ss = orch_env.ss
        ss.active_mode = "mode_1"
        ss.current_phase = "mode_active"
        routing = _routing_json({"next_action": "complete_mode"})
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            json.dumps(routing)
        )
        ss.messages.append({"role": "user", "content": "test"})
        orch_env._run_phase_a("test")
        assert ss.current_phase == "gathering"
        assert ss.active_mode is None

    def test_stores_decision_in_routing_context(self, orch_env):
        ss = orch_env.ss
        routing = _routing_json()
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            json.dumps(routing)
        )
        ss.messages.append({"role": "user", "content": "test"})
        orch_env._run_phase_a("test")
        assert ss.routing_context["last_routing_decision"] is not None


# ===================================================================
# _run_phase_b
# ===================================================================


class TestRunPhaseB:
    def test_returns_text_response(self, orch_env):
        orch_env.client.messages.create.return_value = _make_anthropic_response(
            "Here is my analysis."
        )
        result = orch_env._run_phase_b(_routing_json())
        assert "analysis" in result

    def test_tool_use_loop(self, orch_env):
        """First call → tool_use → handle → second call → text → done."""
        orch_env.client.messages.create.side_effect = [
            # First call: tool use
            _make_anthropic_response(
                text="Let me register this.",
                tool_calls=[("update_problem_statement", {"text": "Problem"}, "tool_1")],
            ),
            # Second call after tool result: text only
            _make_anthropic_response("Done registering."),
        ]
        with patch("pm_copilot.orchestrator.handle_tool_call", return_value="OK"):
            result = orch_env._run_phase_b(_routing_json())
        assert "Done registering" in result
        assert orch_env.client.messages.create.call_count == 2

    def test_generate_artifact_bypass(self, orch_env):
        """generate_artifact result appended directly, tool_result says 'rendered'."""
        orch_env.client.messages.create.side_effect = [
            _make_anthropic_response(
                text="Generating artifact.",
                tool_calls=[("generate_artifact", {"artifact_type": "problem_brief"}, "tool_1")],
            ),
            _make_anthropic_response("All done."),
        ]
        with patch("pm_copilot.orchestrator.handle_tool_call",
                    return_value="# Problem Brief\n\nContent here"):
            result = orch_env._run_phase_b(_routing_json())
        assert "# Problem Brief" in result
        # Check that the tool result sent back says "rendered"
        second_call_msgs = orch_env.client.messages.create.call_args_list[1]
        user_msg = second_call_msgs.kwargs.get("messages", second_call_msgs[1].get("messages", []))[-1]
        tool_results = user_msg["content"]
        assert any("rendered" in str(tr.get("content", "")).lower() for tr in tool_results)

    def test_api_error_with_partial_text(self, orch_env):
        # First call succeeds with text, second raises
        orch_env.client.messages.create.side_effect = [
            _make_anthropic_response(
                text="Partial analysis.",
                tool_calls=[("update_problem_statement", {"text": "X"}, "t1")],
            ),
            RuntimeError("API error"),
        ]
        with patch("pm_copilot.orchestrator.handle_tool_call", return_value="OK"):
            result = orch_env._run_phase_b(_routing_json())
        assert "Partial analysis" in result
        assert "error" in result.lower()

    def test_api_error_no_text_fallback(self, orch_env):
        orch_env.client.messages.create.side_effect = RuntimeError("API error")
        result = orch_env._run_phase_b(_routing_json())
        assert "temporary issue" in result.lower() or "try again" in result.lower()

    def test_empty_response_handling(self, orch_env):
        """Empty text after tool calls → fallback message."""
        orch_env.client.messages.create.return_value = _make_anthropic_response("")
        result = orch_env._run_phase_b(_routing_json())
        assert "couldn't generate" in result.lower() or len(result) > 0

    def test_context_window_truncation(self, orch_env):
        """More than 22 messages + large prompt → truncation."""
        ss = orch_env.ss
        # Add 30 messages
        for i in range(15):
            ss.messages.append({"role": "user", "content": f"Message {i}" * 200})
            ss.messages.append({"role": "assistant", "content": f"Reply {i}" * 200})
        orch_env.client.messages.create.return_value = _make_anthropic_response("OK")
        # Should not crash
        result = orch_env._run_phase_b(_routing_json())
        assert result == "OK"


# ===================================================================
# _build_phase_b_prompt
# ===================================================================


class TestBuildPhaseBPrompt:
    def test_orchestrator_mode_with_rag(self, orch_env):
        assembled = {
            "context_block": "Acme Corp context",
            "probe_content": "", "pattern_content": "",
            "retrieved_documents": "", "retrieved_conversations": "",
        }
        prompt = orch_env._build_phase_b_prompt(_routing_json(), assembled)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_mode1_with_rag(self, orch_env):
        orch_env.ss.active_mode = "mode_1"
        assembled = {
            "context_block": "Context",
            "probe_content": "Probe instructions",
            "pattern_content": "",
            "retrieved_documents": "Some docs",
            "retrieved_conversations": "",
        }
        prompt = orch_env._build_phase_b_prompt(_routing_json(), assembled)
        assert "Probe instructions" in prompt or len(prompt) > 100

    def test_mode2_with_rag(self, orch_env):
        orch_env.ss.active_mode = "mode_2"
        assembled = {
            "context_block": "Context",
            "probe_content": "", "pattern_content": "",
            "retrieved_documents": "", "retrieved_conversations": "",
        }
        prompt = orch_env._build_phase_b_prompt(_routing_json(), assembled)
        assert isinstance(prompt, str)

    def test_legacy_mode_no_rag(self, orch_env):
        """assembled_context=None → uses full MODE1_KNOWLEDGE."""
        orch_env.ss.active_mode = "mode_1"
        with patch("pm_copilot.orchestrator.format_org_context", return_value="Org ctx"):
            prompt = orch_env._build_phase_b_prompt(_routing_json(), assembled_context=None)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_messages_override(self, orch_env):
        override = [
            {"role": "user", "content": "Override message"},
            {"role": "assistant", "content": "Override reply"},
        ]
        assembled = {
            "context_block": "", "probe_content": "",
            "pattern_content": "", "retrieved_documents": "",
            "retrieved_conversations": "",
        }
        prompt = orch_env._build_phase_b_prompt(
            _routing_json(), assembled, messages_override=override
        )
        assert "Override message" in prompt


# ===================================================================
# _post_turn_updates — INTEGRATION POINT TESTS
# ===================================================================


class TestPostTurnUpdates:
    def test_micro_synthesis_turn_3(self, orch_env):
        ss = orch_env.ss
        ss.turn_count = 3
        orch_env._post_turn_updates(_routing_json(), "user msg", "response")
        assert ss.routing_context["micro_synthesis_due"] is True

    def test_micro_synthesis_turn_4(self, orch_env):
        ss = orch_env.ss
        ss.turn_count = 4
        orch_env._post_turn_updates(_routing_json(), "user msg", "response")
        assert ss.routing_context["micro_synthesis_due"] is False

    def test_micro_synthesis_turn_6(self, orch_env):
        ss = orch_env.ss
        ss.turn_count = 6
        orch_env._post_turn_updates(_routing_json(), "user msg", "response")
        assert ss.routing_context["micro_synthesis_due"] is True

    def test_mode_turn_counting(self, orch_env):
        ss = orch_env.ss
        ss.active_mode = "mode_1"
        ss.routing_context["mode_turn_count"] = 2
        orch_env._post_turn_updates(_routing_json(), "msg", "resp")
        assert ss.routing_context["mode_turn_count"] == 3

    def test_mode_turn_not_incremented_without_mode(self, orch_env):
        ss = orch_env.ss
        ss.active_mode = None
        ss.routing_context["mode_turn_count"] = 0
        orch_env._post_turn_updates(_routing_json(), "msg", "resp")
        assert ss.routing_context["mode_turn_count"] == 0

    def test_rag_turn_indexing_beyond_window(self, orch_env):
        """turn > ALWAYS_ON_TURN_WINDOW → _generate_turn_summary + rag.index_turn called."""
        ss = orch_env.ss
        mock_rag = MagicMock()
        mock_rag.enabled = True
        ss.rag = mock_rag
        ss.turn_count = 5  # > ALWAYS_ON_TURN_WINDOW (3)
        with patch("pm_copilot.orchestrator._generate_turn_summary",
                    return_value="Summary of turn"):
            orch_env._post_turn_updates(_routing_json(), "user msg", "response")
        mock_rag.index_turn.assert_called_once()

    def test_rag_skips_indexing_within_window(self, orch_env):
        """turn ≤ ALWAYS_ON_TURN_WINDOW → rag.index_turn NOT called."""
        ss = orch_env.ss
        mock_rag = MagicMock()
        mock_rag.enabled = True
        ss.rag = mock_rag
        ss.turn_count = 2  # ≤ 3
        orch_env._post_turn_updates(_routing_json(), "user msg", "response")
        mock_rag.index_turn.assert_not_called()

    def test_rag_handles_indexing_failure(self, orch_env):
        """rag.index_turn raises → warning logged, no crash."""
        ss = orch_env.ss
        mock_rag = MagicMock()
        mock_rag.enabled = True
        mock_rag.index_turn.side_effect = RuntimeError("Embedding failed")
        ss.rag = mock_rag
        ss.turn_count = 5
        with patch("pm_copilot.orchestrator._generate_turn_summary",
                    return_value="Summary"):
            # Should not raise
            orch_env._post_turn_updates(_routing_json(), "msg", "resp")

    def test_called_from_run_turn(self, orch_env):
        """Verify _post_turn_updates is called with correct args from run_turn."""
        ss = orch_env.ss
        routing = _routing_json()
        orch_env.client.messages.create.side_effect = [
            _make_anthropic_response(json.dumps(routing)),
            _make_anthropic_response("Response text"),
        ]
        with patch("pm_copilot.orchestrator._post_turn_updates") as mock_ptu:
            orch_env.run_turn("user input")
        mock_ptu.assert_called_once()
        args = mock_ptu.call_args
        assert args[0][1] == "user input"  # user_message
        assert args[0][2] == "Response text"  # response_text


# ===================================================================
# Helper formatters
# ===================================================================


class TestBuildAssumptionSummary:
    def test_empty(self, orch_env):
        result = orch_env._build_assumption_summary()
        assert "No assumptions" in result

    def test_with_high_risk_flag(self, orch_env):
        orch_env.ss.assumption_register = {
            "A1": {
                "id": "A1", "claim": "Users want X",
                "impact": "high", "confidence": "guessed", "status": "active",
            }
        }
        result = orch_env._build_assumption_summary()
        assert "🔴" in result
        assert "A1" in result

    def test_no_flag_for_low_impact(self, orch_env):
        orch_env.ss.assumption_register = {
            "A1": {
                "id": "A1", "claim": "Minor detail",
                "impact": "low", "confidence": "guessed", "status": "active",
            }
        }
        result = orch_env._build_assumption_summary()
        assert "🔴" not in result


class TestFormatMessages:
    def test_wraps_large_user_input(self, orch_env):
        messages = [{"role": "user", "content": "x" * 600}]
        result = orch_env._format_messages(messages)
        assert "<user_context>" in result

    def test_does_not_wrap_short_input(self, orch_env):
        messages = [{"role": "user", "content": "Hello"}]
        result = orch_env._format_messages(messages)
        assert "<user_context>" not in result


class TestFormatSkeleton:
    def test_empty_skeleton(self, orch_env):
        result = orch_env._format_skeleton()
        assert "empty" in result.lower()

    def test_populated_skeleton(self, orch_env):
        ss = orch_env.ss
        ss.document_skeleton["problem_statement"] = "Problem X"
        ss.document_skeleton["target_audience"] = "PMs"
        ss.document_skeleton["stakeholders"] = {
            "S1": {"name": "VP", "type": "decision_authority"}
        }
        result = orch_env._format_skeleton()
        assert "Problem X" in result
        assert "PMs" in result
        assert "VP" in result

    def test_mode2_fields(self, orch_env):
        ss = orch_env.ss
        ss.document_skeleton["solution_name"] = "Widget Pro"
        ss.document_skeleton["value_risk_level"] = "high"
        ss.document_skeleton["value_risk_summary"] = "Uncertain demand"
        ss.document_skeleton["go_no_go_recommendation"] = "conditional_go"
        result = orch_env._format_skeleton()
        assert "Widget Pro" in result
        assert "high" in result
        assert "conditional_go" in result
