"""Compatibility boundary for LiveKit Agents imports.

Production code should install and use ``livekit-agents``. The lightweight
fallbacks here keep unit tests for our business-tool mapping runnable before
the package is installed locally; they do not implement LiveKit's agent runtime.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Flag, auto
from typing import Any, Callable, Generic, TypeVar


class LiveKitDependencyError(ImportError):
    """Raised when a real LiveKit runtime object is required but unavailable."""


try:
    from livekit.agents import Agent, AgentSession, RunContext, function_tool, mcp
    from livekit.agents.llm import ToolFlag

    LIVEKIT_AVAILABLE = True
except ModuleNotFoundError:
    LIVEKIT_AVAILABLE = False

    UserdataT = TypeVar("UserdataT")

    class ToolFlag(Flag):
        NONE = 0
        IGNORE_ON_ENTER = auto()
        CANCELLABLE = auto()

    class RunContext(Generic[UserdataT]):
        pass

    @dataclass(frozen=True)
    class _FunctionToolInfo:
        name: str
        description: str | None = None

    def function_tool(
        f: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        **_: Any,
    ):
        def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
            setattr(
                func,
                "__livekit_tool_info",
                _FunctionToolInfo(name=name or func.__name__, description=description),
            )
            return func

        if f is not None:
            return decorate(f)
        return decorate

    class Agent:
        def __init__(
            self,
            *,
            instructions: str,
            tools: list[Any] | None = None,
            chat_ctx: Any = None,
            **kwargs: Any,
        ) -> None:
            self.instructions = instructions
            self.tools = list(tools or [])
            self.chat_ctx = chat_ctx
            self.kwargs = kwargs

    class AgentSession:
        def __init__(self, *, userdata: Any = None, tools: list[Any] | None = None, **kwargs: Any):
            self.userdata = userdata
            self.tools = list(tools or [])
            self.kwargs = kwargs

    class _UnavailableMCP:
        def __getattr__(self, name: str) -> Any:
            raise LiveKitDependencyError(
                "livekit-agents[mcp] is required to build MCP toolsets. "
                "Install requirements.txt before running the LiveKit prototype."
            )

    mcp = _UnavailableMCP()


def ensure_livekit_available() -> None:
    if not LIVEKIT_AVAILABLE:
        raise LiveKitDependencyError(
            "livekit-agents is not installed. Install requirements.txt before "
            "running a real LiveKit AgentSession."
        )


def get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Return an event loop for sync prototype builders and tests."""

    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


__all__ = [
    "Agent",
    "AgentSession",
    "LIVEKIT_AVAILABLE",
    "LiveKitDependencyError",
    "RunContext",
    "ToolFlag",
    "ensure_livekit_available",
    "function_tool",
    "get_or_create_event_loop",
    "mcp",
]
