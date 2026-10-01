"""Prototype LiveKit Agent wiring for DialForge tools.

This module is intentionally media-free: it does not connect to a LiveKit room
or Asterisk. It builds an AgentSession and Agent object with the right tool
layout so we can validate the agent/tool architecture first.
"""

from __future__ import annotations

from typing import Any

from livekit_runtime.livekit_compat import Agent, AgentSession, get_or_create_event_loop
from livekit_runtime.session_state import DialForgeSessionState
from livekit_runtime.tools import (
    CRMMCPConfig,
    DialForgeToolBundle,
    DialForgeToolHandlers,
    build_dialforge_tool_bundle,
)
from runtime.vocabulary import RuntimeContext


DEFAULT_AGENT_INSTRUCTIONS = (
    "You are a DialForge voice sales agent. Use tools for factual knowledge lookup, "
    "CRM access, stage transitions, and human handoff. Keep spoken responses concise."
)


class DialForgeLiveKitAgent(Agent):
    """Stage-aware LiveKit Agent shell for Phase 1."""

    def __init__(
        self,
        *,
        runtime_context: RuntimeContext,
        handlers: DialForgeToolHandlers | None = None,
        tool_bundle: DialForgeToolBundle | None = None,
        instructions: str = DEFAULT_AGENT_INSTRUCTIONS,
        chat_ctx: Any = None,
    ) -> None:
        self.runtime_context = runtime_context
        self.tool_bundle = tool_bundle or build_dialforge_tool_bundle(
            runtime_context,
            handlers=handlers,
        )
        super().__init__(
            instructions=instructions,
            chat_ctx=chat_ctx,
            tools=self.tool_bundle.as_agent_tools(),
        )


def build_prototype_session_and_agent(
    runtime_context: RuntimeContext,
    *,
    handlers: DialForgeToolHandlers | None = None,
    crm_mcp_config: CRMMCPConfig | None = None,
    instructions: str = DEFAULT_AGENT_INSTRUCTIONS,
) -> tuple[AgentSession, DialForgeLiveKitAgent]:
    """Build media-free LiveKit objects for tool-interface validation."""

    bundle = build_dialforge_tool_bundle(
        runtime_context,
        handlers=handlers,
        crm_mcp_config=crm_mcp_config,
    )
    session = AgentSession(
        userdata=DialForgeSessionState.from_runtime_context(runtime_context),
        tools=bundle.as_session_tools(),
        loop=get_or_create_event_loop(),
    )
    agent = DialForgeLiveKitAgent(
        runtime_context=runtime_context,
        handlers=handlers,
        tool_bundle=bundle,
        instructions=instructions,
    )
    return session, agent


__all__ = [
    "DEFAULT_AGENT_INSTRUCTIONS",
    "DialForgeLiveKitAgent",
    "build_prototype_session_and_agent",
]
