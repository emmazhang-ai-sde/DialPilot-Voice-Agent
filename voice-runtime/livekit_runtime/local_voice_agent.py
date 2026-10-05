"""LiveKit local-room/local-sip worker for DialForge.

Run through one of the thin wrappers:

```bash
venv/bin/python -m livekit_runtime.local_room dev
venv/bin/python -m livekit_runtime.local_sip dev
```
"""

from __future__ import annotations

import logging
import os
from typing import Any

from livekit_runtime.local_config import (
    build_local_handoff_handler,
    build_local_runtime_context,
    config_from_env,
    load_env_files,
    local_stage_transition_handler,
)
from livekit_runtime.prototype_agent import DEFAULT_AGENT_INSTRUCTIONS, DialForgeLiveKitAgent
from livekit_runtime.session_state import DialForgeSessionState
from livekit_runtime.tools import DialForgeToolHandlers, build_dialforge_tool_bundle


logger = logging.getLogger("dialforge-livekit-local")

_LIVEKIT_IMPORT_ERROR: ModuleNotFoundError | None = None

try:
    from livekit.agents import (
        AgentServer,
        AgentSession,
        JobContext,
        MetricsCollectedEvent,
        TurnHandlingOptions,
        cli,
        inference,
        metrics,
    room_io,
    )
    from livekit.plugins import deepgram, groq, openai
except ModuleNotFoundError as exc:
    AgentServer = None  # type: ignore[assignment]
    AgentSession = None  # type: ignore[assignment]
    JobContext = Any  # type: ignore[assignment]
    MetricsCollectedEvent = Any  # type: ignore[assignment]
    TurnHandlingOptions = None  # type: ignore[assignment]
    cli = None  # type: ignore[assignment]
    inference = None  # type: ignore[assignment]
    metrics = None  # type: ignore[assignment]
    room_io = None  # type: ignore[assignment]
    deepgram = None  # type: ignore[assignment]
    groq = None  # type: ignore[assignment]
    openai = None  # type: ignore[assignment]
    _LIVEKIT_IMPORT_ERROR = exc


load_env_files()
_CONFIG = config_from_env()

if AgentServer is not None:
    os.environ.setdefault("LIVEKIT_URL", _CONFIG.livekit_url)
    os.environ.setdefault("LIVEKIT_API_KEY", _CONFIG.livekit_api_key)
    os.environ.setdefault("LIVEKIT_API_SECRET", _CONFIG.livekit_api_secret)
    server = AgentServer(
        ws_url=_CONFIG.livekit_url,
        api_key=_CONFIG.livekit_api_key,
        api_secret=_CONFIG.livekit_api_secret,
    )
else:
    server = None


async def _entrypoint(ctx: JobContext) -> None:
    config = config_from_env()
    runtime_context = build_local_runtime_context(config)
    handlers = DialForgeToolHandlers(
        stage_transition_handler=local_stage_transition_handler,
        human_handoff_handler=build_local_handoff_handler(config),
    )
    bundle = build_dialforge_tool_bundle(runtime_context, handlers=handlers)
    session = AgentSession(
        stt=_build_stt(config),
        llm=_build_llm(config),
        tts=_build_tts(config),
        tools=bundle.as_session_tools(),
        userdata=DialForgeSessionState.from_runtime_context(runtime_context),
        ivr_detection=config.ivr_detection,
        max_tool_steps=config.max_tool_steps,
        turn_handling=TurnHandlingOptions(
            interruption={
                "resume_false_interruption": True,
                "false_interruption_timeout": 1.0,
            },
            preemptive_generation={"enabled": True, "max_retries": 3},
        ),
        aec_warmup_duration=3.0,
    )
    agent = DialForgeLiveKitAgent(
        runtime_context=runtime_context,
        handlers=handlers,
        tool_bundle=bundle,
        instructions=_instructions(config),
    )

    ctx.log_context_fields = {
        "room": ctx.room.name,
        "dialforge_profile": config.profile.value,
        "company_key": config.company_key,
        "agent_name": config.agent_name,
    }

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent) -> None:
        if getattr(ev.metrics, "type", None) == "stt_metrics":
            return
        metrics.log_metrics(ev.metrics)

    async def log_usage() -> None:
        logger.info("LiveKit local session usage: %s", session.usage)

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
        ),
    )
    session.generate_reply(instructions=config.greeting)


if server is not None:
    server.rtc_session(_entrypoint, agent_name=_CONFIG.agent_name)


def main() -> None:
    if _LIVEKIT_IMPORT_ERROR is not None or server is None or cli is None:
        raise SystemExit(
            "livekit-agents is not installed in this venv. Run "
            "`venv/bin/pip install -r requirements.txt` before starting the "
            "LiveKit local entrypoint."
        ) from _LIVEKIT_IMPORT_ERROR

    cli.run_app(server)


def _build_stt(config: Any) -> Any:
    if config.media_provider == "direct":
        if config.stt_provider != "deepgram":
            raise ValueError(f"unsupported direct STT provider: {config.stt_provider}")
        kwargs = {"language": config.stt_language} if config.stt_language else {}
        return deepgram.STT(model=_strip_provider_prefix(config.stt_model), **kwargs)

    kwargs = {"language": config.stt_language} if config.stt_language else {}
    return inference.STT(config.stt_model, **kwargs)


def _build_llm(config: Any) -> Any:
    if config.media_provider == "direct":
        if config.llm_provider == "groq":
            return groq.LLM(model=_strip_provider_prefix(config.llm_model))
        if config.llm_provider == "openai":
            return openai.LLM(model=_strip_provider_prefix(config.llm_model))
        raise ValueError(f"unsupported direct LLM provider: {config.llm_provider}")

    return inference.LLM(config.llm_model)


def _build_tts(config: Any) -> Any:
    if config.media_provider == "direct":
        if config.tts_provider == "deepgram":
            return deepgram.TTS(model=_strip_provider_prefix(config.tts_model))
        if config.tts_provider == "groq":
            kwargs = {"voice": config.tts_voice} if config.tts_voice else {}
            return groq.TTS(model=_strip_provider_prefix(config.tts_model), **kwargs)
        raise ValueError(f"unsupported direct TTS provider: {config.tts_provider}")

    kwargs = {"voice": config.tts_voice} if config.tts_voice else {}
    return inference.TTS(config.tts_model, **kwargs)


def _instructions(config: Any) -> str:
    return (
        f"{DEFAULT_AGENT_INSTRUCTIONS} You are currently handling a "
        f"{config.profile.value} test call for company_key={config.company_key}. "
        "Speak naturally, keep responses short, and use tools for facts, workflow "
        "changes, CRM access, and human handoff."
    )


def _strip_provider_prefix(model: str) -> str:
    for prefix in ("deepgram/", "groq/"):
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


if __name__ == "__main__":
    main()


__all__ = ["main", "server"]
