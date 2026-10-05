"""Session userdata shared by DialForge LiveKit-style tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.vocabulary import RuntimeContext


@dataclass
class DialForgeSessionState:
    """Mutable per-call state stored on ``AgentSession.userdata``."""

    company_key: str
    agent_config_id: str
    call_session_id: str | None = None
    stage: str | None = None
    lead_id: str | None = None
    handoff_requested: bool = False
    last_stage_transition_reason: str | None = None
    last_handoff_reason: str | None = None
    last_tool_results: list[dict[str, Any]] = field(default_factory=list)
    workflow_handoffs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_runtime_context(cls, context: RuntimeContext) -> "DialForgeSessionState":
        return cls(
            company_key=context.company_key,
            agent_config_id=context.agent_config_id,
            call_session_id=context.call_session_id,
            stage=context.current_stage,
        )

    def record_tool_result(self, result: dict[str, Any]) -> None:
        self.last_tool_results.append(dict(result))
        if len(self.last_tool_results) > 20:
            self.last_tool_results = self.last_tool_results[-20:]

    def record_workflow_handoff(
        self,
        *,
        transition_name: str,
        previous_stage: str | None,
        target_stage: str,
        reason: str,
    ) -> None:
        self.workflow_handoffs.append(
            {
                "transition_name": transition_name,
                "previous_stage": previous_stage,
                "target_stage": target_stage,
                "reason": reason,
            }
        )
        if len(self.workflow_handoffs) > 20:
            self.workflow_handoffs = self.workflow_handoffs[-20:]


__all__ = ["DialForgeSessionState"]
