import asyncio
import json
import unittest

from livekit_runtime.livekit_compat import LIVEKIT_AVAILABLE, LiveKitDependencyError, ToolFlag
from livekit_runtime.prototype_agent import build_prototype_session_and_agent
from livekit_runtime.session_state import DialForgeSessionState
from livekit_runtime.tools import (
    CRMMCPConfig,
    DEFAULT_CRM_ALLOWED_ACTIONS,
    DialForgeToolHandlers,
    build_crm_mcp_toolset,
    build_dialforge_tool_bundle,
)
from runtime.vocabulary import KnowledgeBaseResource, RuntimeContext, StageTransition


class FakeRunContext:
    def __init__(self, userdata):
        self.userdata = userdata


class LiveKitRuntimeToolTest(unittest.TestCase):
    def test_bundle_splits_session_and_agent_scoped_tools(self):
        bundle = build_dialforge_tool_bundle(
            self._full_context(),
            handlers=DialForgeToolHandlers(
                retrieval_handler=lambda **kwargs: [],
                stage_transition_handler=lambda **kwargs: None,
                human_handoff_handler=lambda **kwargs: None,
            ),
        )

        self.assertIn("retrieve_company_kb", bundle.session_tools)
        self.assertIn("request_handoff", bundle.session_tools)
        self.assertIn("confirmed_worth_automating", bundle.agent_tools)
        self.assertNotIn("confirmed_worth_automating", bundle.session_tools)

    def test_retrieve_tool_reuses_existing_capability_executor(self):
        calls = []

        def fake_retrieval_handler(**kwargs):
            calls.append(kwargs)
            return [
                {
                    "source_file": "globifye.md",
                    "section": "Overview",
                    "content": "GlobiFYE automates phone workflows.",
                    "distance": 0.1,
                }
            ]

        bundle = build_dialforge_tool_bundle(
            self._knowledge_context(),
            handlers=DialForgeToolHandlers(retrieval_handler=fake_retrieval_handler),
        )
        state = DialForgeSessionState.from_runtime_context(self._knowledge_context())

        result_text = asyncio.run(
            bundle.session_tools["retrieve_company_kb"](
                FakeRunContext(state),
                query="What does GlobiFYE do?",
            )
        )
        result = json.loads(result_text)

        self.assertTrue(result["has_evidence"])
        self.assertEqual(calls[0]["company_key"], "globifye")
        self.assertEqual(state.last_tool_results[-1]["capability"], "retrieve_company_kb")

    def test_stage_tool_updates_session_state(self):
        stage_calls = []

        def fake_stage_handler(**kwargs):
            stage_calls.append(kwargs)
            return {"updated": True}

        context = self._stage_context()
        bundle = build_dialforge_tool_bundle(
            context,
            handlers=DialForgeToolHandlers(stage_transition_handler=fake_stage_handler),
        )
        state = DialForgeSessionState.from_runtime_context(context)

        result_text = asyncio.run(
            bundle.agent_tools["confirmed_worth_automating"](
                FakeRunContext(state),
                reason="caller confirmed call volume",
            )
        )
        result = json.loads(result_text)

        self.assertEqual(result["current_stage"], "contact")
        self.assertEqual(state.stage, "contact")
        self.assertEqual(state.last_stage_transition_reason, "caller confirmed call volume")
        self.assertEqual(stage_calls[0]["target_stage"], "contact")

    def test_handoff_tool_marks_userdata(self):
        handoff_calls = []

        def fake_handoff_handler(**kwargs):
            handoff_calls.append(kwargs)
            return {"invite_status": "queued"}

        context = self._handoff_context()
        bundle = build_dialforge_tool_bundle(
            context,
            handlers=DialForgeToolHandlers(human_handoff_handler=fake_handoff_handler),
        )
        state = DialForgeSessionState.from_runtime_context(context)

        result_text = asyncio.run(
            bundle.session_tools["request_handoff"](
                FakeRunContext(state),
                reason="caller asked for a human",
                urgency="urgent",
                preferred_team="sales",
            )
        )
        result = json.loads(result_text)

        self.assertTrue(state.handoff_requested)
        self.assertEqual(state.last_handoff_reason, "caller asked for a human")
        self.assertEqual(result["urgency"], "urgent")
        self.assertEqual(handoff_calls[0]["preferred_team"], "sales")

    def test_crm_mcp_requires_livekit_dependency_when_uninstalled(self):
        if LIVEKIT_AVAILABLE:
            self.skipTest("livekit-agents is installed in this environment")

        with self.assertRaises(LiveKitDependencyError):
            build_crm_mcp_toolset(CRMMCPConfig(url="https://crm.example.com/mcp"))

    def test_crm_mcp_config_defaults_to_generic_action_names(self):
        config = CRMMCPConfig(url="https://crm.example.com/mcp")

        self.assertEqual(config.provider, "generic")
        self.assertEqual(config.allowed_actions, DEFAULT_CRM_ALLOWED_ACTIONS)
        self.assertEqual(config.resolved_allowed_tools(), DEFAULT_CRM_ALLOWED_ACTIONS)
        self.assertEqual(config.resolved_toolset_id, "crm:generic")

    def test_crm_mcp_config_maps_actions_to_provider_tools(self):
        config = CRMMCPConfig(
            provider="salesforce",
            url="https://salesforce.example.com/mcp",
            allowed_actions=("search_contact", "create_contact", "log_call"),
            action_tool_map={
                "search_contact": "salesforce_search_contact",
                "create_contact": "salesforce_create_lead",
                "log_call": "salesforce_log_activity",
            },
            tool_options_by_action={
                "create_contact": {"on_duplicate": "reject"},
            },
            tool_options={
                "salesforce_custom_tool": {"on_duplicate": "confirm"},
            },
        )

        self.assertEqual(
            config.resolved_allowed_tools(),
            (
                "salesforce_search_contact",
                "salesforce_create_lead",
                "salesforce_log_activity",
            ),
        )
        self.assertEqual(
            config.resolved_tool_options()["salesforce_create_lead"],
            {"on_duplicate": "reject"},
        )
        self.assertEqual(
            config.resolved_tool_options()["salesforce_log_activity"],
            {"flags": ToolFlag.CANCELLABLE, "on_duplicate": "reject"},
        )
        self.assertEqual(
            config.resolved_tool_options()["salesforce_custom_tool"],
            {"on_duplicate": "confirm"},
        )

    def test_prototype_session_and_agent_use_expected_tool_scopes(self):
        session, agent = build_prototype_session_and_agent(
            self._full_context(),
            handlers=DialForgeToolHandlers(
                retrieval_handler=lambda **kwargs: [],
                stage_transition_handler=lambda **kwargs: None,
                human_handoff_handler=lambda **kwargs: None,
            ),
        )

        self.assertIsInstance(session.userdata, DialForgeSessionState)
        self.assertEqual(session.userdata.company_key, "globifye")
        self.assertEqual(len(session.tools), 2)
        self.assertEqual(len(agent.tools), 1)

    def _knowledge_context(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            knowledge_bases=[
                KnowledgeBaseResource(
                    knowledge_profile_id="globifye",
                    company_key="globifye",
                    retrieval_policy={"top_k": 4},
                    fallback_policy={"mode": "standard_line"},
                )
            ],
        )

    def _stage_context(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            current_stage="prospect",
            stage_transitions=[
                StageTransition(
                    name="confirmed_worth_automating",
                    target="contact",
                    description="Prospect confirmed a meaningful phone automation need.",
                )
            ],
        )

    def _handoff_context(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            session_state={
                "human_handoff_enabled": True,
                "default_human_endpoint": "PJSIP/sales",
            },
        )

    def _full_context(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            current_stage="prospect",
            stage_transitions=[
                StageTransition(
                    name="confirmed_worth_automating",
                    target="contact",
                    description="Prospect confirmed a meaningful phone automation need.",
                )
            ],
            knowledge_bases=[
                KnowledgeBaseResource(
                    knowledge_profile_id="globifye",
                    company_key="globifye",
                )
            ],
            session_state={
                "human_handoff_enabled": True,
                "default_human_endpoint": "PJSIP/sales",
            },
        )


if __name__ == "__main__":
    unittest.main()
