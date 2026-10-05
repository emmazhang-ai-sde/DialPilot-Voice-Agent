import asyncio
import unittest

from livekit_runtime.session_state import DialForgeSessionState
from livekit_runtime.tools import DialForgeToolHandlers
from livekit_runtime.workflow import (
    DialForgeWorkflowAgent,
    WorkflowDefinition,
    WorkflowStage,
    build_workflow_session_and_agent,
    runtime_context_for_stage,
)
from runtime.vocabulary import KnowledgeBaseResource, RuntimeContext, StageTransition


class FakeRunContext:
    def __init__(self, userdata):
        self.userdata = userdata


def tool_names(agent):
    return [
        getattr(getattr(tool, "__livekit_tool_info", None), "name", None)
        for tool in agent.tools
    ]


class WorkflowAgentTest(unittest.TestCase):
    def test_workflow_context_uses_stage_transitions(self):
        context = runtime_context_for_stage(
            self._base_context(),
            self._workflow(),
            "prospect",
        )

        self.assertEqual(context.current_stage, "prospect")
        self.assertEqual(
            [transition.name for transition in context.stage_transitions],
            ["confirmed_worth_automating"],
        )

    def test_stage_agent_exposes_current_stage_handoff_tools(self):
        agent = DialForgeWorkflowAgent(
            workflow=self._workflow(),
            stage_name="prospect",
            runtime_context=self._base_context(),
        )

        self.assertEqual(agent.stage_name, "prospect")
        self.assertEqual(agent.instructions, "Qualify whether there is a phone workflow.")
        self.assertEqual(tool_names(agent), ["confirmed_worth_automating"])

    def test_handoff_tool_returns_next_stage_agent_and_updates_userdata(self):
        calls = []

        def fake_stage_handler(**kwargs):
            calls.append(kwargs)
            return {"updated": True}

        workflow = self._workflow()
        state = DialForgeSessionState.from_runtime_context(self._base_context())
        agent = DialForgeWorkflowAgent(
            workflow=workflow,
            stage_name="prospect",
            runtime_context=self._base_context(),
            handlers=DialForgeToolHandlers(stage_transition_handler=fake_stage_handler),
        )

        next_agent = asyncio.run(
            agent.tools[0](
                FakeRunContext(state),
                reason="caller confirmed enough volume",
            )
        )

        self.assertIsInstance(next_agent, DialForgeWorkflowAgent)
        self.assertEqual(next_agent.stage_name, "contact")
        self.assertEqual(next_agent.instructions, "Collect and confirm contact details.")
        self.assertEqual(tool_names(next_agent), ["confirmed_demo_interest"])
        self.assertEqual(state.stage, "contact")
        self.assertEqual(state.last_stage_transition_reason, "caller confirmed enough volume")
        self.assertEqual(state.workflow_handoffs[-1]["previous_stage"], "prospect")
        self.assertEqual(state.workflow_handoffs[-1]["target_stage"], "contact")
        self.assertEqual(calls[0]["transition_name"], "confirmed_worth_automating")
        self.assertEqual(calls[0]["target_stage"], "contact")
        self.assertEqual(state.last_tool_results[-1]["capability"], "confirmed_worth_automating")

    def test_workflow_session_keeps_global_tools_session_scoped(self):
        session, agent = build_workflow_session_and_agent(
            self._base_context_with_knowledge(),
            workflow=self._workflow(),
            handlers=DialForgeToolHandlers(
                retrieval_handler=lambda **kwargs: [],
                stage_transition_handler=lambda **kwargs: None,
                human_handoff_handler=lambda **kwargs: None,
            ),
        )

        self.assertIsInstance(session.userdata, DialForgeSessionState)
        self.assertEqual(session.userdata.stage, "prospect")
        self.assertEqual(len(session.tools), 2)
        self.assertEqual(tool_names(agent), ["confirmed_worth_automating"])

    def _workflow(self):
        return WorkflowDefinition(
            initial_stage="prospect",
            stages={
                "prospect": WorkflowStage(
                    name="prospect",
                    instructions="Qualify whether there is a phone workflow.",
                    transitions=(
                        StageTransition(
                            name="confirmed_worth_automating",
                            target="contact",
                            description="Caller confirmed a meaningful phone workflow.",
                        ),
                    ),
                ),
                "contact": WorkflowStage(
                    name="contact",
                    instructions="Collect and confirm contact details.",
                    transitions=(
                        StageTransition(
                            name="confirmed_demo_interest",
                            target="demo",
                            description="Caller wants to book a demo.",
                        ),
                    ),
                ),
                "demo": WorkflowStage(
                    name="demo",
                    instructions="Schedule the demo.",
                ),
            },
        )

    def _base_context(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            current_stage="prospect",
        )

    def _base_context_with_knowledge(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            current_stage="prospect",
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
