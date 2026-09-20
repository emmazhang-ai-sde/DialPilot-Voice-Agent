from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable


@dataclass(frozen=True)
class InputAudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int


@dataclass(frozen=True)
class OutputAudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int


@dataclass(frozen=True)
class BargeInCandidate:
    audio_rms: int
    accumulated_audio_ms: int
    threshold: int
    min_audio_ms: int


@dataclass(frozen=True)
class BargeInDetectionConfig:
    enabled: bool = True
    rms_threshold: int = 0
    min_audio_ms: int = 160
    reset_gap_ms: int = 500


class AgentAudioBridgeInputGate:
    """Productionized shape of the archive AgentAudioBridgeProcessor input guard."""

    def __init__(
        self,
        *,
        echo_tail_ms: int = 500,
        barge_in_detection: BargeInDetectionConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.echo_tail_ms = echo_tail_ms
        self.barge_in_detection = barge_in_detection or BargeInDetectionConfig()
        self._clock = clock
        self.ai_speaking_until = 0.0
        self._barge_in_audio_ms = 0
        self._last_barge_in_audio_at: float | None = None

    def mark_ai_speaking(self) -> None:
        self.ai_speaking_until = float("inf")

    def mark_ai_done_speaking(self, now: float | None = None) -> None:
        now = self._now(now)
        self.ai_speaking_until = now + self.echo_tail_ms / 1000
        self.reset_barge_in_candidate()

    def mark_ai_interrupted(self) -> None:
        self.ai_speaking_until = 0.0
        self.reset_barge_in_candidate()

    def reset(self) -> None:
        self.ai_speaking_until = 0.0
        self.reset_barge_in_candidate()

    def is_input_suppressed(self, now: float | None = None) -> bool:
        return self.input_suppression_reason(now=now) is not None

    def input_suppression_reason(self, now: float | None = None) -> str | None:
        now = self._now(now)
        if self.ai_speaking_until == float("inf"):
            return "assistant_playback"
        if now < self.ai_speaking_until:
            return "playback_echo_tail"
        self.ai_speaking_until = 0.0
        return None

    def detect_barge_in_candidate(
        self,
        frame: InputAudioRawFrame,
        *,
        suppression_reason: str | None,
        now: float | None = None,
    ) -> BargeInCandidate | None:
        config = self.barge_in_detection
        if (
            not config.enabled
            or config.rms_threshold <= 0
            or not frame.audio
            or suppression_reason is None
        ):
            self.reset_barge_in_candidate()
            return None

        audio_rms = _pcm16le_rms(frame.audio)
        if audio_rms < config.rms_threshold:
            self.reset_barge_in_candidate()
            return None

        now = self._now(now)
        if (
            self._last_barge_in_audio_at is not None
            and (now - self._last_barge_in_audio_at) * 1000 > config.reset_gap_ms
        ):
            self._barge_in_audio_ms = 0
        self._last_barge_in_audio_at = now

        self._barge_in_audio_ms += _frame_duration_ms(frame)
        if self._barge_in_audio_ms < config.min_audio_ms:
            return None

        return BargeInCandidate(
            audio_rms=audio_rms,
            accumulated_audio_ms=self._barge_in_audio_ms,
            threshold=config.rms_threshold,
            min_audio_ms=config.min_audio_ms,
        )

    def reset_barge_in_candidate(self) -> None:
        self._barge_in_audio_ms = 0
        self._last_barge_in_audio_at = None

    def _now(self, now: float | None) -> float:
        return self._clock() if now is None else now


class LiveAudioFrameBridge:
    """Normalize live Asterisk audio into frame-shaped STT/TTS boundaries."""

    def __init__(
        self,
        *,
        input_sample_rate: int,
        input_num_channels: int,
        tts_sample_rate: int,
        tts_num_channels: int = 1,
        should_suppress_input: Callable[[], bool] | None = None,
        echo_tail_ms: int = 500,
        barge_in_rms_threshold: int = 0,
        barge_in_min_audio_ms: int = 160,
        barge_in_reset_gap_ms: int = 500,
        barge_in_detection_config: BargeInDetectionConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.input_sample_rate = input_sample_rate
        self.input_num_channels = input_num_channels
        self.tts_sample_rate = tts_sample_rate
        self.tts_num_channels = tts_num_channels
        self._should_suppress_input = should_suppress_input
        if barge_in_detection_config is None:
            barge_in_detection_config = BargeInDetectionConfig(
                enabled=True,
                rms_threshold=barge_in_rms_threshold,
                min_audio_ms=barge_in_min_audio_ms,
                reset_gap_ms=barge_in_reset_gap_ms,
            )
        self.input_gate = AgentAudioBridgeInputGate(
            echo_tail_ms=echo_tail_ms,
            barge_in_detection=barge_in_detection_config,
            clock=clock,
        )

    def input_frame_from_rtp_payload(self, payload: bytes) -> InputAudioRawFrame:
        return InputAudioRawFrame(
            audio=asterisk_slin16be_to_s16le(payload),
            sample_rate=self.input_sample_rate,
            num_channels=self.input_num_channels,
        )

    def should_forward_input_frame(self, frame: InputAudioRawFrame) -> bool:
        if not frame.audio:
            return False
        return not self.is_input_suppressed()

    def is_input_suppressed(self) -> bool:
        return self.input_suppression_reason() is not None

    def input_suppression_reason(self) -> str | None:
        reason = self.input_gate.input_suppression_reason()
        if reason is not None:
            return reason
        if self._should_suppress_input is not None and self._should_suppress_input():
            return "external_input_suppression"
        return None

    def detect_barge_in_candidate(
        self,
        frame: InputAudioRawFrame,
    ) -> BargeInCandidate | None:
        return self.input_gate.detect_barge_in_candidate(
            frame,
            suppression_reason=self.input_suppression_reason(),
        )

    def reset_barge_in_candidate(self) -> None:
        self.input_gate.reset_barge_in_candidate()

    def mark_ai_speaking(self) -> None:
        self.input_gate.mark_ai_speaking()

    def mark_ai_done_speaking(self) -> None:
        self.input_gate.mark_ai_done_speaking()

    def mark_ai_interrupted(self) -> None:
        self.input_gate.mark_ai_interrupted()

    def reset_gate(self) -> None:
        self.input_gate.reset()

    def output_frame_from_tts_chunk(self, chunk: bytes) -> OutputAudioRawFrame:
        audio = bytes(chunk)
        if len(audio) % 2:
            raise ValueError("linear16 TTS chunk must contain complete 16-bit samples")
        return OutputAudioRawFrame(
            audio=audio,
            sample_rate=self.tts_sample_rate,
            num_channels=self.tts_num_channels,
        )


def asterisk_slin16be_to_s16le(payload: bytes) -> bytes:
    even_payload = payload[: len(payload) - (len(payload) % 2)]
    swapped = bytearray(len(even_payload))
    swapped[0::2] = even_payload[1::2]
    swapped[1::2] = even_payload[0::2]
    return bytes(swapped)


def _frame_duration_ms(frame: InputAudioRawFrame) -> int:
    bytes_per_sample = 2 * frame.num_channels
    if bytes_per_sample <= 0 or frame.sample_rate <= 0:
        return 0
    sample_count = len(frame.audio) // bytes_per_sample
    return int(sample_count / frame.sample_rate * 1000)


def _pcm16le_rms(audio: bytes) -> int:
    sample_count = len(audio) // 2
    if sample_count <= 0:
        return 0
    total = 0
    for index in range(0, sample_count * 2, 2):
        sample = int.from_bytes(audio[index : index + 2], "little", signed=True)
        total += sample * sample
    return int(math.sqrt(total / sample_count))
