"""OpenAI-compatible turn runner for the LiveKit-style tool interface.

This is the Phase 2 bridge between today's Groq chat-completions runtime and
the LiveKit-style tool layer from Phase 1. It keeps the current media path
unchanged while moving tool orchestration out of the SIP bridge script.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from livekit_runtime.session_state import DialForgeSessionState
from livekit_runtime.tools import DialForgeToolHandlers, build_dialforge_tool_bundle
from runtime.capability_policy import (
    DEFAULT_MAX_TOOL_RESULT_CHARS,
    CapabilityCallBudgetExceeded,
    RuntimeCapabilityCallBudget,
    serialize_tool_result,
)
from runtime.capability_registry import CapabilityRegistry
from runtime.vocabulary import RuntimeContext


SentenceCallback = Callable[[str], None]
FirstTokenCallback = Callable[[], None]
ContinuePredicate = Callable[[], bool]


@dataclass(frozen=True)
class OpenAICompatibleTurnRunnerConfig:
    model: str = "openai/gpt-oss-120b"
    max_tool_rounds: int = 2
    max_tool_result_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS
    show_stream: bool = False


@dataclass(frozen=True)
class RuntimeToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class RuntimeToolEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeTurnResult:
    assistant_text: str
    fallback_used: bool = False
    tool_rounds: int = 0
    executed_tool_calls: tuple[RuntimeToolCall, ...] = ()
    events: tuple[RuntimeToolEvent, ...] = ()


class RuntimeCapabilityTurnRunner:
    """Run one assistant turn using LiveKit-style tools and an OpenAI-like client."""

    def __init__(
        self,
        *,
        client: Any,
        runtime_context: RuntimeContext | None,
        userdata: DialForgeSessionState | None = None,
        handlers: DialForgeToolHandlers | None = None,
        registry: CapabilityRegistry | None = None,
        tools_enabled: bool = True,
        config: OpenAICompatibleTurnRunnerConfig | None = None,
    ) -> None:
        self._client = client
        self._runtime_context = runtime_context
        self._userdata = userdata or (
            DialForgeSessionState.from_runtime_context(runtime_context)
            if runtime_context is not None
            else None
        )
        self._handlers = handlers or DialForgeToolHandlers()
        self._registry = registry or CapabilityRegistry.default()
        self._tools_enabled = tools_enabled
        self._config = config or OpenAICompatibleTurnRunnerConfig()

        self._events: list[RuntimeToolEvent] = []
        self._executed_tool_calls: list[RuntimeToolCall] = []
        self._tool_budget = self._build_tool_budget()
        self._tool_schemas = self._build_tool_schemas()
        self._tool_functions = self._build_tool_functions()

    @property
    def tool_names(self) -> list[str]:
        return [
            tool.get("function", {}).get("name")
            for tool in self._tool_schemas
            if tool.get("function", {}).get("name")
        ]

    @property
    def tools_exposed(self) -> bool:
        return bool(self._tool_schemas)

    def run(
        self,
        messages: list[dict[str, Any]],
        *,
        on_sentence: SentenceCallback | None = None,
        on_first_token: FirstTokenCallback | None = None,
        should_continue: ContinuePredicate | None = None,
    ) -> RuntimeTurnResult:
        """Run one LLM turn, executing tools until the model produces final text."""

        should_continue = should_continue or (lambda: True)
        model_kwargs = {"tools": self._tool_schemas} if self._tool_schemas else {}
        defer_output_until_tool_decision = bool(model_kwargs)

        for tool_round in range(self._config.max_tool_rounds + 1):
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=messages,
                stream=True,
                **model_kwargs,
            )

            sentence = ""
            full_response = ""
            first_token = True
            raw_tool_calls: dict[int, dict[str, str]] = {}

            for chunk in response:
                delta = chunk.choices[0].delta

                if getattr(delta, "tool_calls", None):
                    self._collect_delta_tool_calls(raw_tool_calls, delta.tool_calls)
                    continue

                token = delta.content
                if token is None:
                    continue

                if first_token:
                    if on_first_token is not None:
                        on_first_token()
                    first_token = False

                sentence += token
                full_response += token

                if self._config.show_stream:
                    print(token, end="", flush=True)

                if sentence.endswith((".", "!", "?")):
                    if not should_continue():
                        break
                    if on_sentence is not None and not defer_output_until_tool_decision:
                        on_sentence(sentence)
                    sentence = ""

            if self._config.show_stream:
                print()

            if raw_tool_calls:
                pending_tool_calls = self._normalized_tool_calls(raw_tool_calls)
                self._append_tool_request_message(messages, pending_tool_calls, full_response)
                self._dispatch_tool_calls(messages, pending_tool_calls)

                if tool_round >= self._config.max_tool_rounds:
                    fallback = (
                        "I’m sorry, I’m having trouble completing that action right now. "
                        "Let me continue with what I can confirm."
                    )
                    if should_continue() and on_sentence is not None:
                        on_sentence(fallback)
                    messages.append({"role": "assistant", "content": fallback})
                    self._events.append(
                        RuntimeToolEvent("runtime_capability_tool_round_limit.reached")
                    )
                    return RuntimeTurnResult(
                        assistant_text=fallback,
                        fallback_used=True,
                        tool_rounds=tool_round + 1,
                        executed_tool_calls=tuple(self._executed_tool_calls),
                        events=tuple(self._events),
                    )
                continue

            if should_continue():
                if defer_output_until_tool_decision and full_response and on_sentence is not None:
                    on_sentence(full_response)
                elif sentence and on_sentence is not None:
                    on_sentence(sentence)

            messages.append({"role": "assistant", "content": full_response})
            return RuntimeTurnResult(
                assistant_text=full_response,
                fallback_used=False,
                tool_rounds=tool_round,
                executed_tool_calls=tuple(self._executed_tool_calls),
                events=tuple(self._events),
            )

        return RuntimeTurnResult(
            assistant_text="",
            fallback_used=False,
            tool_rounds=self._config.max_tool_rounds + 1,
            executed_tool_calls=tuple(self._executed_tool_calls),
            events=tuple(self._events),
        )

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        if not self._tools_enabled or self._runtime_context is None:
            return []
        try:
            return self._registry.to_llm_tools(self._runtime_context)
        except Exception as exc:
            self._events.append(
                RuntimeToolEvent(
                    "runtime_capability_tools.failed",
                    {"error": f"{type(exc).__name__}: {exc}"},
                )
            )
            return []

    def _build_tool_budget(self) -> RuntimeCapabilityCallBudget | None:
        if not self._tools_enabled or self._runtime_context is None:
            return None
        try:
            return RuntimeCapabilityCallBudget.from_capabilities(
                self._registry.allowed_for(self._runtime_context)
            )
        except Exception as exc:
            self._events.append(
                RuntimeToolEvent(
                    "runtime_capability_policy.failed",
                    {"error": f"{type(exc).__name__}: {exc}"},
                )
            )
            return None

    def _build_tool_functions(self) -> dict[str, Callable[..., Any]]:
        if not self._tools_enabled or self._runtime_context is None:
            return {}
        bundle = build_dialforge_tool_bundle(
            self._runtime_context,
            handlers=self._handlers,
            registry=self._registry,
            max_result_chars=self._config.max_tool_result_chars,
        )
        return {
            **bundle.session_tools,
            **bundle.agent_tools,
        }

    def _collect_delta_tool_calls(
        self,
        raw_tool_calls: dict[int, dict[str, str]],
        delta_tool_calls: Any,
    ) -> None:
        for tool_call in delta_tool_calls:
            function_call = getattr(tool_call, "function", None)
            entry = raw_tool_calls.setdefault(
                tool_call.index,
                {"id": "", "name": "", "arguments": ""},
            )
            if tool_call.id:
                entry["id"] = tool_call.id
            if function_call and function_call.name:
                entry["name"] = function_call.name
            if function_call and function_call.arguments:
                entry["arguments"] += function_call.arguments

    def _normalized_tool_calls(
        self,
        raw_tool_calls: dict[int, dict[str, str]],
    ) -> list[RuntimeToolCall]:
        normalized: list[RuntimeToolCall] = []
        for index, call in sorted(raw_tool_calls.items()):
            name = (call.get("name") or "").strip() or "unknown_capability"
            normalized.append(
                RuntimeToolCall(
                    id=call.get("id") or f"runtime_tool_call_{index}",
                    name=name,
                    arguments=call.get("arguments") or "{}",
                )
            )
        return normalized

    def _append_tool_request_message(
        self,
        messages: list[dict[str, Any]],
        pending_tool_calls: list[RuntimeToolCall],
        assistant_content: str,
    ) -> None:
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in pending_tool_calls
            ],
        }
        if assistant_content:
            assistant_message["content"] = assistant_content
        messages.append(assistant_message)

    def _dispatch_tool_calls(
        self,
        messages: list[dict[str, Any]],
        pending_tool_calls: list[RuntimeToolCall],
    ) -> None:
        self._events.append(
            RuntimeToolEvent(
                "runtime_capability_tool_calls.dispatching",
                {
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in pending_tool_calls
                    ],
                    "call_session_id": getattr(self._runtime_context, "call_session_id", None),
                    "company_key": getattr(self._runtime_context, "company_key", None),
                },
            )
        )

        for call in pending_tool_calls:
            content = self._execute_tool_call(call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": content,
                }
            )

    def _execute_tool_call(self, call: RuntimeToolCall) -> str:
        budget_payload = None
        try:
            if self._tool_budget is not None:
                budget_payload = self._tool_budget.reserve(call.name)
            arguments = self._parse_tool_arguments(call.arguments)
            tool = self._tool_functions.get(call.name)
            if tool is None:
                raise ValueError(f"capability {call.name} is not allowed for this turn")
            content = self._run_tool(tool, arguments)
            self._executed_tool_calls.append(call)
            self._events.append(
                RuntimeToolEvent(
                    "runtime_capability_tool_call.executed",
                    {
                        "tool_call_id": call.id,
                        "capability": call.name,
                        "ok": True,
                        "budget": budget_payload,
                    },
                )
            )
            return content
        except CapabilityCallBudgetExceeded as exc:
            return self._error_tool_result(
                call,
                exc,
                budget=budget_payload,
                policy="max_calls_per_turn",
            )
        except Exception as exc:
            return self._error_tool_result(call, exc, budget=budget_payload)

    def _run_tool(self, tool: Callable[..., Any], arguments: dict[str, Any]) -> str:
        context = _SimpleRunContext(userdata=self._userdata)
        result = tool(context, **arguments)
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return str(result)

    def _error_tool_result(
        self,
        call: RuntimeToolCall,
        exc: Exception,
        *,
        budget: dict[str, Any] | None = None,
        policy: str | None = None,
    ) -> str:
        error = f"{type(exc).__name__}: {exc}"
        payload = {
            "tool_call_id": call.id,
            "capability": call.name,
            "error": error,
            "budget": budget,
        }
        if policy:
            payload["policy"] = policy
        self._events.append(RuntimeToolEvent("runtime_capability_tool_call.failed", payload))
        result = {
            "ok": False,
            "capability": call.name,
            "error": error,
        }
        if policy:
            result["policy"] = policy
        content, _, _ = serialize_tool_result(
            result,
            max_chars=self._config.max_tool_result_chars,
        )
        return content

    @staticmethod
    def _parse_tool_arguments(raw_arguments: str | None) -> dict[str, Any]:
        if raw_arguments is None or raw_arguments == "":
            return {}
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid tool arguments JSON: {exc}") from exc
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must decode to an object")
        return arguments


@dataclass
class _SimpleRunContext:
    userdata: DialForgeSessionState | None


__all__ = [
    "OpenAICompatibleTurnRunnerConfig",
    "RuntimeCapabilityTurnRunner",
    "RuntimeToolCall",
    "RuntimeToolEvent",
    "RuntimeTurnResult",
]
