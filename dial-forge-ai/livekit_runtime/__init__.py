"""LiveKit-style agent/tool prototype for DialForge.

This package started as Phase 1 of the LiveKit migration and now contains the
tool, workflow, CRM MCP, and local telephony entrypoint adapters.
"""

from livekit_runtime.local_config import (
    LocalVoiceAgentConfig,
    build_local_handoff_handler,
    build_local_runtime_context,
    config_from_env,
    load_env_files,
)
from livekit_runtime.session_state import DialForgeSessionState
from livekit_runtime.tools import (
    CRMMCPConfig,
    DEFAULT_CRM_ALLOWED_ACTIONS,
    DEFAULT_CRM_ALLOWED_TOOLS,
    DEFAULT_CRM_TOOL_OPTIONS_BY_ACTION,
    DialForgeToolBundle,
    DialForgeToolHandlers,
    build_crm_mcp_toolset,
    build_dialforge_tool_bundle,
)
from livekit_runtime.telephony import (
    LegacyAsteriskHandoffAdapter,
    LiveKitSIPConfig,
    LiveKitTelephonyAdapter,
    LocalTelephonyProfile,
    LocalTestProfile,
    TelephonyConfigError,
    TelephonyHandoffRequest,
    TelephonyHandoffResult,
    build_local_room_profile,
    build_local_sip_profile,
    default_local_test_profiles,
    local_test_profile,
)
from livekit_runtime.turn_runner import (
    OpenAICompatibleTurnRunnerConfig,
    RuntimeCapabilityTurnRunner,
    RuntimeTurnResult,
)
from livekit_runtime.workflow import (
    DialForgeWorkflowAgent,
    WorkflowDefinition,
    WorkflowStage,
    build_workflow_session_and_agent,
    runtime_context_for_stage,
)

__all__ = [
    "CRMMCPConfig",
    "DEFAULT_CRM_ALLOWED_ACTIONS",
    "DEFAULT_CRM_ALLOWED_TOOLS",
    "DEFAULT_CRM_TOOL_OPTIONS_BY_ACTION",
    "DialForgeSessionState",
    "DialForgeToolBundle",
    "DialForgeToolHandlers",
    "LocalVoiceAgentConfig",
    "LegacyAsteriskHandoffAdapter",
    "LiveKitSIPConfig",
    "LiveKitTelephonyAdapter",
    "LocalTelephonyProfile",
    "LocalTestProfile",
    "TelephonyConfigError",
    "TelephonyHandoffRequest",
    "TelephonyHandoffResult",
    "build_crm_mcp_toolset",
    "build_dialforge_tool_bundle",
    "build_local_handoff_handler",
    "build_local_room_profile",
    "build_local_runtime_context",
    "build_local_sip_profile",
    "config_from_env",
    "default_local_test_profiles",
    "load_env_files",
    "local_test_profile",
    "OpenAICompatibleTurnRunnerConfig",
    "RuntimeCapabilityTurnRunner",
    "RuntimeTurnResult",
    "DialForgeWorkflowAgent",
    "WorkflowDefinition",
    "WorkflowStage",
    "build_workflow_session_and_agent",
    "runtime_context_for_stage",
]
