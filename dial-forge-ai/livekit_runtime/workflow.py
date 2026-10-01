"""Stage workflow and handoff-agent primitives for DialForge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from livekit_runtime.livekit_compat import Agent, RunContext, function_tool
from livekit_runtime.session_state import DialForgeSessionState
from livekit_runtime.tools import (
    CRMMCPConfig,
    DialForgeToolBundle,
    DialForgeToolHandlers,
    build_dialforge_tool_bundle,
)
from runtime.capability_executor import execute_capability_call
from runtime.capability_registry import CapabilityRegistry
from runtime.vocabulary import RuntimeContext, StageTransition


@dataclass(frozen=True)
class WorkflowStage:
    """One conversational stage with its own instructions and exits."""

    name: str
    instructions: str
    transitions: tuple[StageTransition, ...] = ()
    tools: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "transitions", tuple(self.transitions))
        object.__setattr__(self, "tools", tuple(self.tools))


@dataclass(frozen=True)
class WorkflowDefinition:
    """Provider-neutral workflow graph for stage agents."""

    stages: dict[str, WorkflowStage]
    initial_stage: str

    def __post_init__(self) -> None:
        if self.initial_stage not in self.stages:
            raise ValueError(f"unknown initial_stage: {self.initial_stage}")
        for stage in self.stages.values():
            for transition in stage.transitions:
                if transition.target not in self.stages:
                    raise ValueError(
                        f"stage {stage.name} transition {transition.name} targets "
                        f"unknown stage {transition.target}"
                    )
        object.__setattr__(self, "stages", dict(self.stages))

    @classmethod
    def from_stage_graph(
        cls,
        *,
        stage_graph: dict[str, dict[str, Any]],
        initial_stage: str,
        instructions_by_stage: dict[str, str],
    ) -> "WorkflowDefinition":
        stages = {}
        for stage_name, config in stage_graph.items():
            edges = config.get("edges") or {}
            stages[stage_name] = WorkflowStage(
                name=stage_name,
                instructions=instructions_by_stage.get(
                    stage_name,
                    str(config.get("instructions") or stage_name.replace("_", " ")),
                ),
                transitions=tuple(
                    StageTransition.from_edge(edge_name, edge)
                    for edge_name, edge in edges.items()
                ),
            )
        return cls(stages=stages, initial_stage=initial_stage)

    def stage(self, stage_name: str) -> WorkflowStage:
        try:
            return self.stages[stage_name]
        except KeyError as exc:
            raise ValueError(f"unknown workflow stage: {stage_name}") from exc


class DialForgeWorkflowAgent(Agent):
    """LiveKit-style agent whose tools hand off to the next workflow stage."""

    def __init__(
        self,
        *,
        workflow: WorkflowDefinition,
        stage_name: str,
        runtime_context: RuntimeContext,
        handlers: DialForgeToolHandlers | None = None,
        registry: CapabilityRegistry | None = None,
        chat_ctx: Any = None,
    ) -> None:
        self.workflow = workflow
        self.stage_name = stage_name
        self.stage = workflow.stage(stage_name)
        self.runtime_context = runtime_context_for_stage(runtime_context, workflow, stage_name)
        self.handlers = handlers or DialForgeToolHandlers()
        self.registry = registry or CapabilityRegistry.default()

        super().__init__(
            instructions=self.stage.instructions,
            chat_ctx=chat_ctx,
            tools=[
                *self.stage.tools,
                *self._build_stage_handoff_tools(),
            ],
        )

    def _build_stage_handoff_tools(self) -> list[Any]:
        return [
            self._build_stage_handoff_tool(transition)
            for transition in self.stage.transitions
        ]

    def _build_stage_handoff_tool(self, transition: StageTransition) -> Any:
        @function_tool(name=transition.name, description=transition.description)
        async def handoff_to_stage(
            context: RunContext[DialForgeSessionState],
            reason: str = "",
        ) -> Agent:
            previous_stage = self.stage_name
            target_stage = transition.target
            reason_text = (reason or "").strip()

            userdata = getattr(context, "userdata", None)
            if userdata is not None:
                userdata.stage = target_stage
                userdata.last_stage_transition_reason = reason_text
                userdata.record_workflow_handoff(
                    transition_name=transition.name,
                    previous_stage=previous_stage,
                    target_stage=target_stage,
                    reason=reason_text,
                )

            if self.handlers.stage_transition_handler is not None:
                result = execute_capability_call(
                    self.runtime_context,
                    transition.name,
                    {"reason": reason_text},
                    registry=self.registry,
                    stage_transition_handler=self.handlers.stage_transition_handler,
                )
                if userdata is not None:
                    userdata.record_tool_result(result)

            return DialForgeWorkflowAgent(
                workflow=self.workflow,
                stage_name=target_stage,
                runtime_context=self.runtime_context,
                handlers=self.handlers,
                registry=self.registry,
                chat_ctx=_copy_chat_ctx_without_instructions(self.chat_ctx),
            )

        return handoff_to_stage


def runtime_context_for_stage(
    base_context: RuntimeContext,
    workflow: WorkflowDefinition,
    stage_name: str,
) -> RuntimeContext:
    stage = workflow.stage(stage_name)
    return RuntimeContext(
        agent_config_id=base_context.agent_config_id,
        company_key=base_context.company_key,
        call_session_id=base_context.call_session_id,
        owner=base_context.owner,
        current_stage=stage.name,
        stage_transitions=stage.transitions,
        knowledge_bases=base_context.knowledge_bases,
        session_state=dict(base_context.session_state),
    )


def build_workflow_session_and_agent(
    runtime_context: RuntimeContext,
    *,
    workflow: WorkflowDefinition,
    handlers: DialForgeToolHandlers | None = None,
    registry: CapabilityRegistry | None = None,
    crm_mcp_config: CRMMCPConfig | None = None,
    initial_stage: str | None = None,
) -> tuple[Any, DialForgeWorkflowAgent]:
    """Build media-free AgentSession + current workflow Agent."""

    from livekit_runtime.livekit_compat import AgentSession, get_or_create_event_loop

    stage_name = initial_stage or runtime_context.current_stage or workflow.initial_stage
    stage_context = runtime_context_for_stage(runtime_context, workflow, stage_name)
    bundle: DialForgeToolBundle = build_dialforge_tool_bundle(
        stage_context,
        handlers=handlers,
        registry=registry,
        crm_mcp_config=crm_mcp_config,
    )
    session = AgentSession(
        userdata=DialForgeSessionState.from_runtime_context(stage_context),
        tools=bundle.as_session_tools(),
        loop=get_or_create_event_loop(),
    )
    agent = DialForgeWorkflowAgent(
        workflow=workflow,
        stage_name=stage_name,
        runtime_context=stage_context,
        handlers=handlers,
        registry=registry,
    )
    return session, agent


def _copy_chat_ctx_without_instructions(chat_ctx: Any) -> Any:
    if chat_ctx is None:
        return None
    copy = getattr(chat_ctx, "copy", None)
    if callable(copy):
        try:
            return copy(exclude_instructions=True)
        except TypeError:
            return copy()
    return chat_ctx


__all__ = [
    "DialForgeWorkflowAgent",
    "WorkflowDefinition",
    "WorkflowStage",
    "build_workflow_session_and_agent",
    "runtime_context_for_stage",
]
