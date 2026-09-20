from __future__ import annotations

from dataclasses import dataclass
import re
import threading
import time


@dataclass(frozen=True)
class TurnHandlingConfig:
    endpointing_min_delay_ms: int = 800
    endpointing_max_delay_ms: int = 2500
    incomplete_wait_ms: int = 5000
    incomplete_short_wait_ms: int | None = None
    incomplete_long_wait_ms: int | None = None
    ambiguous_wait_ms: int = 1200
    semantic_completion_enabled: bool = True
    playback_echo_tail_ms: int = 500


@dataclass(frozen=True)
class SemanticTurnClassification:
    kind: str
    reason: str
    wait_ms: int


@dataclass(frozen=True)
class CommittedTurn:
    transcript: str
    segments: tuple[str, ...]
    committed_at: float
    silence_ms: int
    semantic_kind: str
    semantic_reason: str


@dataclass(frozen=True)
class BargeInDecision:
    should_interrupt: bool
    reason: str
    text: str = ""
    suppression_reason: str | None = None


class TurnCompletionGate:
    """Hold STT provider finals until they look like one complete caller turn."""

    _INCOMPLETE_ENDINGS = {
        "and",
        "or",
        "but",
        "because",
        "so",
        "if",
        "when",
        "while",
        "although",
        "for",
        "to",
        "with",
        "about",
        "from",
        "i mean",
        "the reason is",
    }
    _BACKCHANNELS = {
        "yeah",
        "yes",
        "yep",
        "yup",
        "uh huh",
        "uh-huh",
        "mhm",
        "mm hmm",
        "mm-hmm",
        "right",
        "okay",
        "ok",
        "sure",
        "got it",
        "i see",
    }
    _COMMAND_LIKE = {
        "wait",
        "stop",
        "no",
        "yes",
        "repeat",
        "continue",
        "hold on",
        "go ahead",
    }

    def __init__(
        self,
        config: TurnHandlingConfig | None = None,
        *,
        clock=time.monotonic,
        classifier: "SemanticTurnClassifier | None" = None,
    ):
        self.config = config or TurnHandlingConfig()
        self.classifier = classifier or SemanticTurnClassifier(self.config)
        self._clock = clock
        self._lock = threading.RLock()
        self.pending_partial: str | None = None
        self.pending_segments: list[str] = []
        self.pending_since: float | None = None
        self.last_speech_at: float | None = None
        self.user_is_speaking = False
        self.active_playback_id: str | None = None
        self.assistant_is_speaking = False
        self.echo_tail_until: float | None = None

    def on_partial(self, text: str, now: float | None = None) -> bool:
        text = _normalize_space(text)
        if not text:
            return False
        now = self._now(now)
        with self._lock:
            if self.is_input_suppressed(now=now):
                return False
            self.pending_partial = text
            self.last_speech_at = now
            self.user_is_speaking = True
            return True

    def on_final(self, text: str, now: float | None = None) -> bool:
        text = _normalize_space(text)
        if not text:
            return False
        now = self._now(now)
        with self._lock:
            if self.is_input_suppressed(now=now):
                return False
            self.pending_segments.append(text)
            if self.pending_since is None:
                self.pending_since = now
            self.pending_partial = None
            self.last_speech_at = now
            self.user_is_speaking = False
            return True

    def tick(self, now: float | None = None) -> CommittedTurn | None:
        now = self._now(now)
        with self._lock:
            if not self.pending_segments or self.last_speech_at is None:
                return None

            silence_ms = int((now - self.last_speech_at) * 1000)
            if (
                self.user_is_speaking
                and silence_ms < self.config.endpointing_max_delay_ms
            ):
                return None
            if silence_ms < self.config.endpointing_min_delay_ms:
                return None

            transcript = _normalize_space(" ".join(self.pending_segments))
            classification = self.classifier.classify(transcript)
            if silence_ms < classification.wait_ms:
                return None

            return self._commit_locked(
                now=now,
                silence_ms=silence_ms,
                classification=classification,
            )

    def reset_pending(self) -> None:
        with self._lock:
            self.pending_partial = None
            self.pending_segments = []
            self.pending_since = None
            self.last_speech_at = None
            self.user_is_speaking = False

    def on_playback_started(
        self,
        playback_id: str | None,
        now: float | None = None,
    ) -> None:
        now = self._now(now)
        with self._lock:
            self.reset_pending()
            self.active_playback_id = playback_id
            self.assistant_is_speaking = True
            self.echo_tail_until = None

    def on_playback_finished(
        self,
        playback_id: str | None = None,
        now: float | None = None,
    ) -> bool:
        now = self._now(now)
        with self._lock:
            if not self._playback_matches_locked(playback_id):
                return False
            self.active_playback_id = None
            self.assistant_is_speaking = False
            self.echo_tail_until = now + self.config.playback_echo_tail_ms / 1000
            return True

    def on_playback_interrupted(
        self,
        playback_id: str | None = None,
        now: float | None = None,
    ) -> bool:
        self._now(now)
        with self._lock:
            if not self._playback_matches_locked(playback_id):
                return False
            self.active_playback_id = None
            self.assistant_is_speaking = False
            self.echo_tail_until = None
            return True

    def on_barge_in_confirmed(
        self,
        playback_id: str | None = None,
        now: float | None = None,
    ) -> bool:
        return self.on_playback_interrupted(playback_id, now=now)

    def reset_all(self) -> None:
        with self._lock:
            self.reset_pending()
            self.active_playback_id = None
            self.assistant_is_speaking = False
            self.echo_tail_until = None

    def is_input_suppressed(self, now: float | None = None) -> bool:
        return self.input_suppression_reason(now=now) is not None

    def input_suppression_reason(self, now: float | None = None) -> str | None:
        now = self._now(now)
        with self._lock:
            if self.assistant_is_speaking:
                return "assistant_playback"
            if self.echo_tail_until is None:
                return None
            if now < self.echo_tail_until:
                return "playback_echo_tail"
            self.echo_tail_until = None
            return None

    @classmethod
    def looks_incomplete(cls, transcript: str) -> bool:
        normalized = _normalize_space(transcript).lower()
        if not normalized:
            return False
        if normalized[-1:] in ".!?":
            return False
        if normalized[-1:] in ",;:":
            return True

        words = re.findall(r"[a-z0-9']+", normalized)
        if not words:
            return False
        if words[-1] in cls._INCOMPLETE_ENDINGS:
            return True

        tail_2 = " ".join(words[-2:])
        tail_3 = " ".join(words[-3:])
        return tail_2 in cls._INCOMPLETE_ENDINGS or tail_3 in cls._INCOMPLETE_ENDINGS

    def _commit_locked(
        self,
        *,
        now: float,
        silence_ms: int,
        classification: SemanticTurnClassification,
    ) -> CommittedTurn:
        segments = tuple(self.pending_segments)
        transcript = _normalize_space(" ".join(segments))
        self.reset_pending()
        return CommittedTurn(
            transcript=transcript,
            segments=segments,
            committed_at=now,
            silence_ms=silence_ms,
            semantic_kind=classification.kind,
            semantic_reason=classification.reason,
        )

    def _now(self, now: float | None) -> float:
        return self._clock() if now is None else now

    def _playback_matches_locked(self, playback_id: str | None) -> bool:
        return playback_id is None or playback_id == self.active_playback_id


class VoiceTurnStateMachine:
    def __init__(self, gate: TurnCompletionGate | None = None):
        self.gate = gate or TurnCompletionGate()

    def on_stt_partial(self, text: str, now: float | None = None) -> None:
        self.gate.on_partial(text, now=now)

    def on_stt_final(self, text: str, now: float | None = None) -> None:
        self.gate.on_final(text, now=now)

    def tick(self, now: float | None = None) -> CommittedTurn | None:
        return self.gate.tick(now=now)


class BargeInGate:
    _INTERRUPT_WORDS = {
        "wait",
        "stop",
        "no",
        "nope",
        "actually",
        "hold",
        "pause",
        "wrong",
        "sorry",
    }
    _INTERRUPT_PHRASES = {
        "hold on",
        "hang on",
        "one second",
        "just a second",
        "that's wrong",
        "that is wrong",
        "not what",
        "let me",
        "i need",
        "i want",
        "can i",
        "could i",
    }

    def decide_audio_candidate(
        self,
        candidate,
        *,
        suppression_reason: str | None,
    ) -> BargeInDecision:
        if suppression_reason == "playback_echo_tail":
            return BargeInDecision(
                should_interrupt=False,
                reason="echo_tail_audio_suppressed",
                suppression_reason=suppression_reason,
            )
        if suppression_reason is None:
            return BargeInDecision(
                should_interrupt=False,
                reason="not_during_assistant_audio",
                suppression_reason=suppression_reason,
            )
        return BargeInDecision(
            should_interrupt=True,
            reason="sustained_audio_during_assistant_playback",
            suppression_reason=suppression_reason,
        )

    def decide_transcript(
        self,
        text: str,
        *,
        suppression_reason: str | None,
    ) -> BargeInDecision:
        normalized = _normalize_space(text)
        lowered = normalized.lower()
        if not normalized:
            return BargeInDecision(
                should_interrupt=False,
                reason="empty_transcript",
                text=normalized,
                suppression_reason=suppression_reason,
            )
        if suppression_reason == "playback_echo_tail":
            return BargeInDecision(
                should_interrupt=False,
                reason="echo_tail_transcript_suppressed",
                text=normalized,
                suppression_reason=suppression_reason,
            )
        if suppression_reason is None:
            return BargeInDecision(
                should_interrupt=False,
                reason="not_suppressed",
                text=normalized,
                suppression_reason=suppression_reason,
            )
        if lowered in TurnCompletionGate._BACKCHANNELS:
            return BargeInDecision(
                should_interrupt=False,
                reason="backchannel_during_assistant_playback",
                text=normalized,
                suppression_reason=suppression_reason,
            )

        words = set(re.findall(r"[a-z0-9']+", lowered))
        if words & self._INTERRUPT_WORDS or any(
            phrase in lowered for phrase in self._INTERRUPT_PHRASES
        ):
            return BargeInDecision(
                should_interrupt=True,
                reason="interrupt_keyword_during_assistant_playback",
                text=normalized,
                suppression_reason=suppression_reason,
            )

        return BargeInDecision(
            should_interrupt=False,
            reason="suppressed_without_interrupt_signal",
            text=normalized,
            suppression_reason=suppression_reason,
        )

    def should_interrupt(self, text: str) -> bool:
        return self.decide_transcript(
            text,
            suppression_reason="assistant_playback",
        ).should_interrupt


class SemanticTurnClassifier:
    def __init__(self, config: TurnHandlingConfig):
        self.config = config

    def classify(self, transcript: str) -> SemanticTurnClassification:
        normalized = _normalize_space(transcript)
        if not self.config.semantic_completion_enabled:
            wait_ms = (
                self.config.incomplete_wait_ms
                if TurnCompletionGate.looks_incomplete(normalized)
                else self.config.endpointing_min_delay_ms
            )
            return SemanticTurnClassification(
                kind="complete",
                reason="semantic completion disabled",
                wait_ms=wait_ms,
            )

        lowered = normalized.lower()
        words = re.findall(r"[a-z0-9']+", lowered)
        word_count = len(words)

        if not words:
            return SemanticTurnClassification(
                kind="ambiguous",
                reason="empty transcript",
                wait_ms=self.config.ambiguous_wait_ms,
            )

        if lowered in TurnCompletionGate._BACKCHANNELS:
            return SemanticTurnClassification(
                kind="backchannel",
                reason="short acknowledgement",
                wait_ms=self.config.endpointing_min_delay_ms,
            )

        if lowered in TurnCompletionGate._COMMAND_LIKE:
            return SemanticTurnClassification(
                kind="complete",
                reason="short command",
                wait_ms=self.config.endpointing_min_delay_ms,
            )

        if normalized[-1:] in ".!?":
            return SemanticTurnClassification(
                kind="complete",
                reason="terminal punctuation",
                wait_ms=self.config.endpointing_min_delay_ms,
            )

        if TurnCompletionGate.looks_incomplete(normalized):
            kind = "incomplete_short" if word_count <= 6 else "incomplete_long"
            wait_ms = (
                self.config.incomplete_short_wait_ms
                if kind == "incomplete_short"
                else self.config.incomplete_long_wait_ms
            )
            return SemanticTurnClassification(
                kind=kind,
                reason="incomplete trailing phrase",
                wait_ms=wait_ms or self.config.incomplete_wait_ms,
            )

        if word_count <= 2:
            return SemanticTurnClassification(
                kind="ambiguous",
                reason="short phrase without terminal punctuation",
                wait_ms=self.config.ambiguous_wait_ms,
            )

        return SemanticTurnClassification(
            kind="complete",
            reason="default complete utterance",
            wait_ms=self.config.endpointing_min_delay_ms,
        )


def _normalize_space(text: str) -> str:
    return " ".join((text or "").strip().split())
