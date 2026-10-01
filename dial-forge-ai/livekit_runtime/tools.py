"""LiveKit-style tools backed by DialForge RuntimeCapability handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from livekit_runtime.livekit_compat import (
    LIVEKIT_AVAILABLE,
    LiveKitDependencyError,
    RunContext,
    ToolFlag,
    function_tool,
    mcp,
)
from livekit_runtime.session_state import DialForgeSessionState
from runtime.capability_executor import (
    HumanHandoffHandler,
    RetrievalHandler,
    StageTransitionHandler,
    execute_capability_call,
)
from runtime.capability_policy import DEFAULT_MAX_TOOL_RESULT_CHARS, serialize_tool_result
from runtime.capability_registry import CapabilityRegistry, REQUEST_HANDOFF, RETRIEVE_COMPANY_KB
from runtime.vocabulary import CapabilityKind, RuntimeCapability, RuntimeContext


DEFAULT_CRM_ALLOWED_ACTIONS = (
    "search_contact",
    "get_contact",
    "search_company",
    "create_contact",
    "update_contact",
    "add_note",
    "log_call",
    "create_followup_task",
)

# Backward-compatible alias. Prefer DEFAULT_CRM_ALLOWED_ACTIONS in new code:
# these are DialForge CRM actions, not necessarily provider MCP tool names.
DEFAULT_CRM_ALLOWED_TOOLS = DEFAULT_CRM_ALLOWED_ACTIONS


DEFAULT_CRM_TOOL_OPTIONS_BY_ACTION: dict[str, dict[str, Any]] = {
    "create_contact": {"on_duplicate": "confirm"},
    "update_contact": {"on_duplicate": "confirm"},
    "add_note": {"on_duplicate": "reject", "duplicate_scope": "name_and_args"},
    "log_call": {"flags": ToolFlag.CANCELLABLE, "on_duplicate": "reject"},
}


@dataclass(frozen=True)
class CRMMCPConfig:
    """Provider-agnostic CRM MCP configuration.

    ``allowed_actions`` are DialForge's stable CRM vocabulary. ``action_tool_map``
    translates those actions to the provider's concrete MCP tool names. If a
    mapping is omitted, the action name is used as the provider tool name.
    """

    url: str
    provider: str = "generic"
    headers: dict[str, Any] = field(default_factory=dict)
    allowed_actions: tuple[str, ...] = DEFAULT_CRM_ALLOWED_ACTIONS
    action_tool_map: dict[str, str] = field(default_factory=dict)
    transport_type: Literal["sse", "streamable_http"] | None = "streamable_http"
    client_session_timeout_seconds: float = 30.0
    toolset_id: str | None = None
    tool_options_by_action: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def resolved_toolset_id(self) -> str:
        return self.toolset_id or f"crm:{self.provider}"

    def provider_tool_name(self, action: str) -> str:
        return self.action_tool_map.get(action, action)

    def resolved_allowed_tools(self) -> tuple[str, ...]:
        return tuple(self.provider_tool_name(action) for action in self.allowed_actions)

    def resolved_tool_options(self) -> dict[str, dict[str, Any]]:
        options: dict[str, dict[str, Any]] = {}
        by_action = {
            **DEFAULT_CRM_TOOL_OPTIONS_BY_ACTION,
            **self.tool_options_by_action,
        }
        for action, action_options in by_action.items():
            provider_tool = self.provider_tool_name(action)
            if provider_tool in self.resolved_allowed_tools():
                options[provider_tool] = dict(action_options)
        for provider_tool, provider_options in self.tool_options.items():
            options[provider_tool] = dict(provider_options)
        return options


@dataclass(frozen=True)
class DialForgeToolHandlers:
    """Injected side-effect handlers used by LiveKit-style function tools."""

    retrieval_handler: RetrievalHandler | None = None
    stage_transition_handler: StageTransitionHandler | None = None
    human_handoff_handler: HumanHandoffHandler | None = None


@dataclass(frozen=True)
class DialForgeToolBundle:
    """Tools split by LiveKit lifecycle scope."""

    session_tools: dict[str, Callable[..., Any]]
    agent_tools: dict[str, Callable[..., Any]]
    crm_toolsets: list[Any] = field(default_factory=list)

    def as_session_tools(self) -> list[Any]:
        return [*self.session_tools.values(), *self.crm_toolsets]

    def as_agent_tools(self) -> list[Any]:
        return list(self.agent_tools.values())


def build_dialforge_tool_bundle(
    runtime_context: RuntimeContext,
    *,
    handlers: DialForgeToolHandlers | None = None,
    registry: CapabilityRegistry | None = None,
    crm_mcp_config: CRMMCPConfig | None = None,
    max_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS,
) -> DialForgeToolBundle:
    """Expose currently allowed DialForge capabilities as LiveKit-style tools.

    The bundle intentionally mirrors LiveKit's lifecycle:

    * information and human handoff tools are session-scoped;
    * stage transition tools are agent-scoped;
    * CRM MCP tools are session-scoped external toolsets.
    """

    handlers = handlers or DialForgeToolHandlers()
    registry = registry or CapabilityRegistry.default()
    session_tools: dict[str, Callable[..., Any]] = {}
    agent_tools: dict[str, Callable[..., Any]] = {}

    for capability in registry.allowed_for(runtime_context):
        tool = _tool_for_capability(
            runtime_context=runtime_context,
            capability=capability,
            handlers=handlers,
            registry=registry,
            max_result_chars=max_result_chars,
        )
        if capability.kind is CapabilityKind.STATE:
            agent_tools[capability.name] = tool
        else:
            session_tools[capability.name] = tool

    crm_toolsets = [build_crm_mcp_toolset(crm_mcp_config)] if crm_mcp_config else []
    return DialForgeToolBundle(
        session_tools=session_tools,
        agent_tools=agent_tools,
        crm_toolsets=crm_toolsets,
    )


def build_crm_mcp_toolset(config: CRMMCPConfig) -> Any:
    """Build a LiveKit MCPToolset for CRM access."""

    if not LIVEKIT_AVAILABLE:
        raise LiveKitDependencyError(
            "livekit-agents[mcp] is required to build CRM MCP toolsets."
        )

    return mcp.MCPToolset(
        id=config.resolved_toolset_id,
        mcp_server=mcp.MCPServerHTTP(
            url=config.url,
            transport_type=config.transport_type,
            headers=config.headers,
            allowed_tools=list(config.resolved_allowed_tools()),
            client_session_timeout_seconds=config.client_session_timeout_seconds,
        ),
        tool_options=config.resolved_tool_options(),
    )


def _tool_for_capability(
    *,
    runtime_context: RuntimeContext,
    capability: RuntimeCapability,
    handlers: DialForgeToolHandlers,
    registry: CapabilityRegistry,
    max_result_chars: int,
) -> Callable[..., Any]:
    if capability.name == RETRIEVE_COMPANY_KB.name:
        return _retrieve_company_kb_tool(
            runtime_context=runtime_context,
            capability=capability,
            handlers=handlers,
            registry=registry,
            max_result_chars=max_result_chars,
        )

    if capability.name == REQUEST_HANDOFF.name:
        return _request_handoff_tool(
            runtime_context=runtime_context,
            capability=capability,
            handlers=handlers,
            registry=registry,
            max_result_chars=max_result_chars,
        )

    if capability.kind is CapabilityKind.STATE:
        return _stage_transition_tool(
            runtime_context=runtime_context,
            capability=capability,
            handlers=handlers,
            registry=registry,
            max_result_chars=max_result_chars,
        )

    raise ValueError(f"unsupported LiveKit-style capability: {capability.name}")


def _retrieve_company_kb_tool(
    *,
    runtime_context: RuntimeContext,
    capability: RuntimeCapability,
    handlers: DialForgeToolHandlers,
    registry: CapabilityRegistry,
    max_result_chars: int,
) -> Callable[..., Any]:
    @function_tool(name=capability.name, description=capability.description)
    async def retrieve_company_kb(
        context: RunContext[DialForgeSessionState],
        query: str,
    ) -> str:
        result = execute_capability_call(
            runtime_context,
            capability.name,
            {"query": query},
            registry=registry,
            retrieval_handler=handlers.retrieval_handler,
        )
        _record_result(context, result)
        return _serialize_result(result, max_result_chars=max_result_chars)

    return retrieve_company_kb


def _request_handoff_tool(
    *,
    runtime_context: RuntimeContext,
    capability: RuntimeCapability,
    handlers: DialForgeToolHandlers,
    registry: CapabilityRegistry,
    max_result_chars: int,
) -> Callable[..., Any]:
    @function_tool(name=capability.name, description=capability.description)
    async def request_handoff(
        context: RunContext[DialForgeSessionState],
        reason: str,
        urgency: str = "normal",
        preferred_team: str | None = None,
    ) -> str:
        result = execute_capability_call(
            runtime_context,
            capability.name,
            {
                "reason": reason,
                "urgency": urgency,
                "preferred_team": preferred_team,
            },
            registry=registry,
            human_handoff_handler=handlers.human_handoff_handler,
        )
        userdata = _userdata(context)
        if userdata is not None:
            userdata.handoff_requested = True
            userdata.last_handoff_reason = reason
        _record_result(context, result)
        return _serialize_result(result, max_result_chars=max_result_chars)

    return request_handoff


def _stage_transition_tool(
    *,
    runtime_context: RuntimeContext,
    capability: RuntimeCapability,
    handlers: DialForgeToolHandlers,
    registry: CapabilityRegistry,
    max_result_chars: int,
) -> Callable[..., Any]:
    @function_tool(name=capability.name, description=capability.description)
    async def transition_stage(
        context: RunContext[DialForgeSessionState],
        reason: str = "",
    ) -> str:
        result = execute_capability_call(
            runtime_context,
            capability.name,
            {"reason": reason},
            registry=registry,
            stage_transition_handler=handlers.stage_transition_handler,
        )
        userdata = _userdata(context)
        if userdata is not None:
            userdata.stage = result.get("current_stage")
            userdata.last_stage_transition_reason = reason
        _record_result(context, result)
        return _serialize_result(result, max_result_chars=max_result_chars)

    return transition_stage


def _record_result(context: RunContext[DialForgeSessionState], result: dict[str, Any]) -> None:
    userdata = _userdata(context)
    if userdata is not None:
        userdata.record_tool_result(result)


def _userdata(context: RunContext[DialForgeSessionState]) -> DialForgeSessionState | None:
    return getattr(context, "userdata", None)


def _serialize_result(result: dict[str, Any], *, max_result_chars: int) -> str:
    content, _, _ = serialize_tool_result(result, max_chars=max_result_chars)
    return content


__all__ = [
    "CRMMCPConfig",
    "DEFAULT_CRM_ALLOWED_ACTIONS",
    "DEFAULT_CRM_ALLOWED_TOOLS",
    "DEFAULT_CRM_TOOL_OPTIONS_BY_ACTION",
    "DialForgeToolBundle",
    "DialForgeToolHandlers",
    "build_crm_mcp_toolset",
    "build_dialforge_tool_bundle",
]
