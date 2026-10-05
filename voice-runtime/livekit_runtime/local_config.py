"""Local LiveKit entrypoint configuration for DialForge."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from communication.call_session import CallSession
from livekit_runtime.telephony import (
    LiveKitSIPConfig,
    LiveKitTelephonyAdapter,
    LocalTelephonyProfile,
    TelephonyHandoffResult,
)
from rag.knowledge_base_registry import KnowledgeBaseRegistry
from runtime.agent_registry import AgentConfig, AgentRegistry
from runtime.context_builder import build_runtime_context
from runtime.vocabulary import RuntimeContext


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILES = (
    REPO_ROOT / ".env.local",
    REPO_ROOT / "deal-pilot-ai" / ".env.local",
)
DEFAULT_KNOWLEDGE_BASE_ROOT = REPO_ROOT / "examples" / "knowledge-bases"
DEFAULT_COMPANIES_PATH = DEFAULT_KNOWLEDGE_BASE_ROOT / "companies.json"
DEFAULT_KNOWLEDGE_PROFILES_PATH = DEFAULT_KNOWLEDGE_BASE_ROOT / "knowledge_profiles.json"


@dataclass(frozen=True)
class LocalVoiceAgentConfig:
    """Environment-backed settings shared by local-room and local-sip."""

    profile: LocalTelephonyProfile
    agent_name: str
    company_key: str
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    media_provider: str
    stt_provider: str
    stt_model: str
    stt_language: str | None
    llm_provider: str
    llm_model: str
    tts_provider: str
    tts_model: str
    tts_voice: str | None
    room_name: str
    initial_stage: str | None
    stage_graph: dict[str, dict[str, Any]] | None
    human_handoff_enabled: bool
    human_endpoint: str | None
    human_caller_id: str | None
    sip_trunk_id: str | None
    sip_number: str | None
    greeting: str
    ivr_detection: bool
    max_tool_steps: int
    companies_path: Path
    knowledge_profiles_path: Path


def load_env_files(paths: tuple[Path, ...] = DEFAULT_ENV_FILES) -> None:
    """Load simple KEY=VALUE env files without adding a dotenv dependency."""

    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def config_from_env(env: dict[str, str] | None = None) -> LocalVoiceAgentConfig:
    """Build local LiveKit agent config from environment variables."""

    if env is None:
        env = os.environ
    profile = LocalTelephonyProfile(
        env.get("DIALFORGE_LOCAL_PROFILE", LocalTelephonyProfile.LOCAL_ROOM.value)
    )
    company_key = env.get("DIALFORGE_COMPANY_KEY", "globifye")
    room_name = env.get("DIALFORGE_ROOM_NAME", f"dialforge-{company_key}-{profile.value}")
    human_endpoint = _optional(env.get("LIVEKIT_SUPERVISOR_PHONE_NUMBER")) or _optional(
        env.get("DIALFORGE_HUMAN_ENDPOINT")
    )
    human_caller_id = _optional(env.get("LIVEKIT_SIP_NUMBER")) or _optional(
        env.get("DIALFORGE_HUMAN_CALLER_ID")
    )
    sip_trunk_id = _optional(env.get("LIVEKIT_SIP_OUTBOUND_TRUNK")) or _optional(
        env.get("SIP_OUTBOUND_TRUNK_ID")
    )

    return LocalVoiceAgentConfig(
        profile=profile,
        agent_name=env.get("DIALFORGE_AGENT_NAME", "dialforge-agent"),
        company_key=company_key,
        livekit_url=env.get("LIVEKIT_URL", "ws://localhost:7880"),
        livekit_api_key=env.get("LIVEKIT_API_KEY", "devkey"),
        livekit_api_secret=env.get("LIVEKIT_API_SECRET", "secret"),
        media_provider=env.get("DIALFORGE_MEDIA_PROVIDER", "direct"),
        stt_provider=env.get("DIALFORGE_STT_PROVIDER", "deepgram"),
        stt_model=env.get("DIALFORGE_STT_MODEL", "nova-3"),
        stt_language=_optional(env.get("DIALFORGE_STT_LANGUAGE", "en-US")),
        llm_provider=env.get("DIALFORGE_LLM_PROVIDER", "groq"),
        llm_model=env.get("DIALFORGE_LLM_MODEL", "openai/gpt-oss-120b"),
        tts_provider=env.get("DIALFORGE_TTS_PROVIDER", "deepgram"),
        tts_model=env.get("DIALFORGE_TTS_MODEL", "aura-2-arcas-en"),
        tts_voice=_optional(env.get("DIALFORGE_TTS_VOICE")),
        room_name=room_name,
        initial_stage=_optional(env.get("DIALFORGE_INITIAL_STAGE")),
        stage_graph=_stage_graph_from_env(env),
        human_handoff_enabled=_bool(
            env.get("DIALFORGE_HUMAN_HANDOFF_ENABLED"),
            default=bool(human_endpoint and sip_trunk_id),
        ),
        human_endpoint=human_endpoint,
        human_caller_id=human_caller_id,
        sip_trunk_id=sip_trunk_id,
        sip_number=_optional(env.get("LIVEKIT_SIP_NUMBER")),
        greeting=env.get(
            "DIALFORGE_GREETING",
            "Greet the caller briefly, introduce yourself as the company's AI voice agent, "
            "and ask how you can help.",
        ),
        ivr_detection=_bool(
            env.get("DIALFORGE_IVR_DETECTION"),
            default=profile is LocalTelephonyProfile.LOCAL_SIP,
        ),
        max_tool_steps=int(env.get("DIALFORGE_MAX_TOOL_STEPS", "3")),
        companies_path=Path(env.get("DIALFORGE_COMPANIES_PATH", str(DEFAULT_COMPANIES_PATH))),
        knowledge_profiles_path=Path(
            env.get("DIALFORGE_KNOWLEDGE_PROFILES_PATH", str(DEFAULT_KNOWLEDGE_PROFILES_PATH))
        ),
    )


def build_local_runtime_context(config: LocalVoiceAgentConfig) -> RuntimeContext:
    """Create a RuntimeContext for a local LiveKit room/SIP session."""

    agent = load_agent_config(config)
    call_session = CallSession.from_agent(
        agent,
        call_session_id=f"{config.profile.value}:{config.room_name}",
    )
    knowledge_registry = KnowledgeBaseRegistry.from_path(config.knowledge_profiles_path)
    return build_runtime_context(
        agent=agent,
        session=call_session,
        knowledge_base_registry=knowledge_registry,
        current_stage=config.initial_stage,
        stage_graph=config.stage_graph,
        default_human_endpoint=config.human_endpoint,
        human_caller_id=config.human_caller_id,
        session_state={
            "human_handoff_enabled": config.human_handoff_enabled,
            "default_human_endpoint": config.human_endpoint,
            "human_caller_id": config.human_caller_id,
            "local_profile": config.profile.value,
            "livekit_room": config.room_name,
        },
    )


def load_agent_config(config: LocalVoiceAgentConfig) -> AgentConfig:
    registry = AgentRegistry.from_legacy_companies(config.companies_path)
    agent = registry.get(config.company_key)
    if agent is None:
        known = ", ".join(agent.company_key for agent in registry.agents())
        raise ValueError(f"unknown DIALFORGE_COMPANY_KEY={config.company_key!r}; known: {known}")
    return agent


def build_local_handoff_handler(config: LocalVoiceAgentConfig) -> Callable[..., dict[str, Any]]:
    """Build a local handoff handler for request_handoff."""

    if config.human_endpoint and config.sip_trunk_id:
        adapter = LiveKitTelephonyAdapter(
            LiveKitSIPConfig(
                sip_trunk_id=config.sip_trunk_id,
                sip_number=config.sip_number or config.human_caller_id,
                default_human_endpoint=config.human_endpoint,
                metadata={"local_profile": config.profile.value},
            )
        )
        return adapter.handoff_handler()

    def not_configured_handoff(**kwargs: Any) -> dict[str, Any]:
        return TelephonyHandoffResult(
            ok=False,
            provider="livekit",
            mode="not_configured",
            invite_status="not_configured",
            endpoint=config.human_endpoint,
            caller_id=config.human_caller_id,
            metadata={
                "reason": kwargs.get("reason"),
                "urgency": kwargs.get("urgency"),
                "preferred_team": kwargs.get("preferred_team"),
                "missing": ["LIVEKIT_SUPERVISOR_PHONE_NUMBER", "LIVEKIT_SIP_OUTBOUND_TRUNK"],
            },
        ).as_handler_result()

    return not_configured_handoff


def local_stage_transition_handler(**kwargs: Any) -> dict[str, Any]:
    return {
        "updated": True,
        "transition_name": kwargs.get("transition_name"),
        "previous_stage": kwargs.get("previous_stage"),
        "target_stage": kwargs.get("target_stage"),
        "reason": kwargs.get("reason"),
    }


def _stage_graph_from_env(env: dict[str, str]) -> dict[str, dict[str, Any]] | None:
    raw = _optional(env.get("DIALFORGE_STAGE_GRAPH_JSON"))
    if raw:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("DIALFORGE_STAGE_GRAPH_JSON must decode to an object")
        return parsed

    path = _optional(env.get("DIALFORGE_STAGE_GRAPH_PATH"))
    if path:
        with open(path) as f:
            parsed = json.load(f)
        if not isinstance(parsed, dict):
            raise ValueError("DIALFORGE_STAGE_GRAPH_PATH must contain a JSON object")
        return parsed

    return None


def _bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


__all__ = [
    "LocalVoiceAgentConfig",
    "build_local_handoff_handler",
    "build_local_runtime_context",
    "config_from_env",
    "load_agent_config",
    "load_env_files",
    "local_stage_transition_handler",
]
