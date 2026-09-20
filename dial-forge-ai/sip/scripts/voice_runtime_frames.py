from __future__ import annotations

from dataclasses import dataclass

from voice_turn_state import CommittedTurn


@dataclass(frozen=True)
class UserTurnFrame:
    text: str
    epoch: int
    segments: tuple[str, ...] = ()
    silence_ms: int = 0
    semantic_kind: str = ""
    semantic_reason: str = ""


@dataclass(frozen=True)
class AssistantTextFrame:
    text: str
    epoch: int


def user_turn_frame_from_committed(
    committed: CommittedTurn,
    *,
    epoch: int,
) -> UserTurnFrame:
    return UserTurnFrame(
        text=committed.transcript,
        epoch=epoch,
        segments=committed.segments,
        silence_ms=committed.silence_ms,
        semantic_kind=committed.semantic_kind,
        semantic_reason=committed.semantic_reason,
    )
