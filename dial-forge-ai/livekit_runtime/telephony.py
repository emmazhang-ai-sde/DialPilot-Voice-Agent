"""Telephony migration adapters for the LiveKit runtime target.

Phase 5 keeps two local development profiles explicit:

* ``local-room`` bypasses SIP and lets a browser client act as the caller.
* ``local-sip`` routes a Linphone/direct-SIP caller through LiveKit SIP.

The adapters in this module intentionally build LiveKit-shaped requests without
depending on the beta warm-transfer classes at import time. That keeps unit
tests stable while giving the future AgentSession path one place to plug in the
real LiveKit SIP and WarmTransferTask calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal


class TelephonyConfigError(ValueError):
    """Raised when a telephony adapter is missing required configuration."""


class LocalTelephonyProfile(str, Enum):
    """Supported local test entrypoints for the migrated LiveKit path."""

    LOCAL_ROOM = "local-room"
    LOCAL_SIP = "local-sip"


@dataclass(frozen=True)
class LocalTestProfile:
    """Human-readable run profile for local LiveKit voice testing."""

    name: LocalTelephonyProfile
    purpose: str
    client_entrypoint: str
    media_path: tuple[str, ...]
    requires_sip: bool
    setup_commands: tuple[str, ...]
    verification_checks: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "purpose": self.purpose,
            "client_entrypoint": self.client_entrypoint,
            "media_path": list(self.media_path),
            "requires_sip": self.requires_sip,
            "setup_commands": list(self.setup_commands),
            "verification_checks": list(self.verification_checks),
        }


def build_local_room_profile(
    *,
    livekit_url: str = "ws://localhost:7880",
    api_key: str = "devkey",
    api_secret: str = "secret",
    room_name: str = "dialforge-local-room",
    agent_name: str = "dialforge-agent",
) -> LocalTestProfile:
    """Build the default browser-as-caller local profile."""

    return LocalTestProfile(
        name=LocalTelephonyProfile.LOCAL_ROOM,
        purpose=(
            "Daily local development: use a browser microphone as the caller "
            "and test the AI agent, RAG, tools, workflow, handoff decisions, "
            "STT, and TTS without SIP setup."
        ),
        client_entrypoint="Browser / LiveKit Meet",
        media_path=(
            "browser microphone",
            "local LiveKit room",
            f"agent worker ({agent_name})",
            "browser speaker",
        ),
        requires_sip=False,
        setup_commands=(
            "livekit-server --dev",
            f"lk token create --api-key {api_key} --api-secret {api_secret} "
            f"--join --room {room_name} --identity local-caller --valid-for 24h",
            f"open https://meet.livekit.io/custom?liveKitUrl={livekit_url}",
        ),
        verification_checks=(
            "Agent worker joins the same room.",
            "Browser participant publishes microphone audio.",
            "Agent responds with synthesized audio.",
            "RAG/function tools/workflow events appear in agent logs.",
        ),
    )


def build_local_sip_profile(
    *,
    livekit_url: str = "ws://localhost:7880",
    sip_uri: str = "sip:127.0.0.1:5060",
    agent_name: str = "dialforge-agent",
) -> LocalTestProfile:
    """Build the Linphone/direct-SIP local integration profile."""

    return LocalTestProfile(
        name=LocalTelephonyProfile.LOCAL_SIP,
        purpose=(
            "Telephony integration testing: use Linphone or another SIP client "
            "to verify LiveKit SIP participant creation, DTMF, hangup, transfer, "
            "and SIP metadata."
        ),
        client_entrypoint=f"Linphone direct SIP call to {sip_uri}",
        media_path=(
            "Linphone",
            "livekit-sip",
            "local LiveKit room",
            f"agent worker ({agent_name})",
            "livekit-sip",
            "Linphone",
        ),
        requires_sip=True,
        setup_commands=(
            "livekit-server --dev",
            "redis-server",
            f"livekit-sip --config=config.yaml  # ws_url: {livekit_url}",
            f"linphonecsh dial {sip_uri}",
        ),
        verification_checks=(
            "A SIP participant appears in the LiveKit room.",
            "Participant attributes include SIP call metadata.",
            "DTMF reaches the room/agent when sent from Linphone.",
            "Hangup and transfer paths emit expected LiveKit disconnect/transfer events.",
        ),
    )


def default_local_test_profiles() -> dict[str, LocalTestProfile]:
    """Return the two local profiles we support after telephony migration."""

    profiles = (build_local_room_profile(), build_local_sip_profile())
    return {profile.name.value: profile for profile in profiles}


def local_test_profile(name: str) -> LocalTestProfile:
    """Look up a local test profile by name."""

    try:
        return default_local_test_profiles()[name]
    except KeyError as exc:
        valid = ", ".join(sorted(default_local_test_profiles()))
        raise TelephonyConfigError(f"unknown local telephony profile {name!r}; use one of: {valid}") from exc


@dataclass(frozen=True)
class TelephonyHandoffRequest:
    """Provider-neutral handoff request passed from ``request_handoff``."""

    reason: str
    urgency: Literal["normal", "urgent"] = "normal"
    preferred_team: str | None = None
    endpoint: str | None = None
    caller_id: str | None = None
    conversation_summary: str | None = None
    dtmf: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_handler_args(cls, **kwargs: Any) -> "TelephonyHandoffRequest":
        return cls(
            reason=str(kwargs.get("reason") or "").strip(),
            urgency=kwargs.get("urgency") or "normal",
            preferred_team=_clean_optional_string(kwargs.get("preferred_team")),
            endpoint=_clean_optional_string(kwargs.get("endpoint")),
            caller_id=_clean_optional_string(kwargs.get("caller_id")),
            metadata={
                "agent_config_id": getattr(kwargs.get("context"), "agent_config_id", None),
                "call_session_id": getattr(kwargs.get("context"), "call_session_id", None),
                "company_key": getattr(kwargs.get("context"), "company_key", None),
            },
        )


@dataclass(frozen=True)
class TelephonyHandoffResult:
    """Provider-neutral handoff result returned to RuntimeCapability."""

    ok: bool
    provider: str
    mode: str
    invite_status: str
    endpoint: str | None = None
    caller_id: str | None = None
    participant_id: str | None = None
    already_invited: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_handler_result(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "mode": self.mode,
            "invite_status": self.invite_status,
            "endpoint": self.endpoint,
            "caller_id": self.caller_id,
            "participant_id": self.participant_id,
            "already_invited": self.already_invited,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class LiveKitSIPConfig:
    """LiveKit SIP settings for outbound human handoff / warm transfer."""

    sip_trunk_id: str | None = None
    sip_number: str | None = None
    default_human_endpoint: str | None = None
    provider: str = "livekit"
    mode: Literal["warm_transfer", "sip_participant"] = "warm_transfer"
    transfer_instructions: str = (
        "Brief the human before transfer. Summarize why the caller needs help, "
        "what has already been collected, and the recommended next action."
    )
    metadata: dict[str, Any] = field(default_factory=dict)


class LiveKitTelephonyAdapter:
    """Build LiveKit SIP handoff requests behind the existing handler shape."""

    def __init__(self, config: LiveKitSIPConfig) -> None:
        self.config = config

    def build_warm_transfer_task_kwargs(
        self,
        request: TelephonyHandoffRequest,
        *,
        chat_ctx: Any = None,
    ) -> dict[str, Any]:
        """Return kwargs matching LiveKit's beta WarmTransferTask shape."""

        endpoint = request.endpoint or self.config.default_human_endpoint
        if not endpoint:
            raise TelephonyConfigError("LiveKit warm transfer requires a human endpoint")
        if not self.config.sip_trunk_id:
            raise TelephonyConfigError("LiveKit warm transfer requires sip_trunk_id")

        kwargs: dict[str, Any] = {
            "sip_call_to": endpoint,
            "sip_trunk_id": self.config.sip_trunk_id,
            "extra_instructions": self._transfer_instructions(request),
        }
        sip_number = request.caller_id or self.config.sip_number
        if sip_number:
            kwargs["sip_number"] = sip_number
        if chat_ctx is not None:
            kwargs["chat_ctx"] = chat_ctx
        if request.dtmf:
            kwargs["dtmf"] = request.dtmf
        return kwargs

    def handoff_handler(
        self,
        *,
        chat_ctx_provider: Callable[[TelephonyHandoffRequest], Any] | None = None,
    ) -> Callable[..., dict[str, Any]]:
        """Return a ``HumanHandoffHandler`` compatible callable."""

        def handle_handoff(**kwargs: Any) -> dict[str, Any]:
            request = TelephonyHandoffRequest.from_handler_args(**kwargs)
            chat_ctx = chat_ctx_provider(request) if chat_ctx_provider else None
            task_kwargs = self.build_warm_transfer_task_kwargs(request, chat_ctx=chat_ctx)
            return TelephonyHandoffResult(
                ok=True,
                provider=self.config.provider,
                mode=self.config.mode,
                invite_status="ready",
                endpoint=task_kwargs["sip_call_to"],
                caller_id=task_kwargs.get("sip_number"),
                metadata={
                    **self.config.metadata,
                    "warm_transfer_task_kwargs": task_kwargs,
                    "handoff_reason": request.reason,
                    "urgency": request.urgency,
                    "preferred_team": request.preferred_team,
                    "request_metadata": request.metadata,
                },
            ).as_handler_result()

        return handle_handoff

    def _transfer_instructions(self, request: TelephonyHandoffRequest) -> str:
        parts = [
            self.config.transfer_instructions,
            f"Handoff reason: {request.reason}.",
            f"Urgency: {request.urgency}.",
        ]
        if request.preferred_team:
            parts.append(f"Preferred team: {request.preferred_team}.")
        if request.conversation_summary:
            parts.append(f"Conversation summary: {request.conversation_summary}")
        return " ".join(parts)


class LegacyAsteriskHandoffAdapter:
    """Normalize the archived Asterisk handoff handler during migration."""

    def __init__(self, legacy_handler: Callable[..., dict[str, Any] | None]) -> None:
        self.legacy_handler = legacy_handler

    def handoff_handler(self) -> Callable[..., dict[str, Any]]:
        def handle_handoff(**kwargs: Any) -> dict[str, Any]:
            request = TelephonyHandoffRequest.from_handler_args(**kwargs)
            legacy_result = self.legacy_handler(**kwargs) or {}
            return TelephonyHandoffResult(
                ok=legacy_result.get("invite_status") != "failed",
                provider="asterisk",
                mode="legacy_bridge",
                invite_status=legacy_result.get("invite_status") or "unknown",
                endpoint=legacy_result.get("endpoint") or request.endpoint,
                caller_id=legacy_result.get("caller_id") or request.caller_id,
                participant_id=legacy_result.get("channel_id"),
                already_invited=bool(legacy_result.get("already_invited")),
                metadata={
                    "legacy_result": legacy_result,
                    "handoff_reason": request.reason,
                    "urgency": request.urgency,
                    "preferred_team": request.preferred_team,
                },
            ).as_handler_result()

        return handle_handoff


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "LegacyAsteriskHandoffAdapter",
    "LiveKitSIPConfig",
    "LiveKitTelephonyAdapter",
    "LocalTelephonyProfile",
    "LocalTestProfile",
    "TelephonyConfigError",
    "TelephonyHandoffRequest",
    "TelephonyHandoffResult",
    "build_local_room_profile",
    "build_local_sip_profile",
    "default_local_test_profiles",
    "local_test_profile",
]
