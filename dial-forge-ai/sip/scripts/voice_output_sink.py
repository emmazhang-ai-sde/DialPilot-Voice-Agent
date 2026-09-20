from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import itertools
import os
import subprocess
import wave
from typing import Callable, Iterable, Protocol, Sequence

from asterisk_streaming_encoder import AsteriskWebSocketFrameEncoder
from asterisk_websocket_control import flush_media
from voice_frame_bridge import OutputAudioRawFrame


@dataclass(frozen=True)
class AriFilePlaybackConfig:
    staging_dir: str
    asterisk_container: str
    sounds_dir_in_container: str
    playback_sample_rate: int = 8000
    sample_width_bytes: int = 2


@dataclass(frozen=True)
class PlaybackResult:
    playback_id: str | None
    sound_name: str
    raw_wav_path: str | None
    asterisk_wav_path: str | None
    interrupted: bool = False


@dataclass
class AssistantSpeechHandle:
    turn_id: str
    epoch: int
    allow_interruptions: bool = True
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


class OutputSink(Protocol):
    def play(
        self,
        *,
        frames: Iterable[OutputAudioRawFrame],
        channel_id: str,
        speech_handle: AssistantSpeechHandle | None = None,
    ) -> PlaybackResult | None:
        ...


class OutputSinkUnavailable(RuntimeError):
    pass


class FrameEncoder(Protocol):
    def encode(self, frame: OutputAudioRawFrame) -> bytes:
        ...


@dataclass(frozen=True)
class StreamingWebSocketOutputConfig:
    websocket_url: str
    sample_rate: int
    num_channels: int = 1


class SerializerFrameEncoder:
    """Adapter for PoC-style Asterisk serializers exposed as serialize(frame)."""

    def __init__(
        self,
        serializer,
        *,
        frame_converter: Callable[[OutputAudioRawFrame], object] | None = None,
    ):
        self._serializer = serializer
        self._frame_converter = frame_converter or (lambda frame: frame)

    def encode(self, frame: OutputAudioRawFrame) -> bytes:
        serializer_frame = self._frame_converter(frame)
        serialize = getattr(self._serializer, "serialize", None)
        if serialize is None:
            payload = self._serializer(serializer_frame)
        else:
            payload = serialize(serializer_frame)
        if inspect.isawaitable(payload):
            payload = _await_sync(payload)
        return _serializer_payload_to_bytes(payload)


def pipecat_audio_frame_converter(frame: OutputAudioRawFrame):
    from pipecat.frames.frames import AudioRawFrame

    return AudioRawFrame(
        audio=frame.audio,
        sample_rate=frame.sample_rate,
        num_channels=frame.num_channels,
    )


class AriFilePlaybackSink:
    """Current production sink: frames -> WAV -> ffmpeg -> Docker copy -> ARI play."""

    def __init__(
        self,
        *,
        config: AriFilePlaybackConfig,
        ari_post: Callable[..., dict | None],
        subprocess_run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.config = config
        self._ari_post = ari_post
        self._subprocess_run = subprocess_run
        self._reply_counter = 0

    def play(
        self,
        *,
        frames: Iterable[OutputAudioRawFrame],
        channel_id: str,
        speech_handle: AssistantSpeechHandle | None = None,
    ) -> PlaybackResult | None:
        if speech_handle and speech_handle.cancelled:
            return None
        audio_frames = [frame for frame in frames if frame.audio]
        if not audio_frames:
            return None
        if speech_handle and speech_handle.cancelled:
            return None

        sample_rate, num_channels = _validate_frame_shape(audio_frames)
        os.makedirs(self.config.staging_dir, exist_ok=True)

        self._reply_counter += 1
        sound_name = f"reply_{self._reply_counter}"
        raw_wav_path = os.path.join(self.config.staging_dir, f"{sound_name}_24k.wav")
        asterisk_wav_path = os.path.join(self.config.staging_dir, f"{sound_name}.wav")

        with wave.open(raw_wav_path, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(self.config.sample_width_bytes)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(frame.audio for frame in audio_frames))

        self._subprocess_run(
            [
                "ffmpeg",
                "-y",
                "-i",
                raw_wav_path,
                "-ar",
                str(self.config.playback_sample_rate),
                "-ac",
                "1",
                "-f",
                "wav",
                asterisk_wav_path,
            ],
            check=True,
            capture_output=True,
        )
        self._subprocess_run(
            [
                "docker",
                "cp",
                asterisk_wav_path,
                (
                    f"{self.config.asterisk_container}:"
                    f"{self.config.sounds_dir_in_container}/{sound_name}.wav"
                ),
            ],
            check=True,
        )

        result = self._ari_post(
            f"/channels/{channel_id}/play",
            media=f"sound:custom/{sound_name}",
        )
        return PlaybackResult(
            playback_id=result["id"] if result else None,
            sound_name=sound_name,
            raw_wav_path=raw_wav_path,
            asterisk_wav_path=asterisk_wav_path,
            interrupted=False,
        )


class StreamingNotConfiguredSink:
    def play(
        self,
        *,
        frames: Iterable[OutputAudioRawFrame],
        channel_id: str,
        speech_handle: AssistantSpeechHandle | None = None,
    ) -> PlaybackResult | None:
        raise OutputSinkUnavailable(
            "streaming output sink selected, but no streaming websocket URL is configured"
        )


class StreamingWebSocketOutputSink:
    def __init__(
        self,
        *,
        config: StreamingWebSocketOutputConfig,
        websocket_connect: Callable[[str], object],
        encoder: FrameEncoder | None = None,
    ):
        self.config = config
        self._websocket_connect = websocket_connect
        self._encoder = encoder or AsteriskWebSocketFrameEncoder(
            sample_rate=config.sample_rate,
            num_channels=config.num_channels,
        )

    def play(
        self,
        *,
        frames: Iterable[OutputAudioRawFrame],
        channel_id: str,
        speech_handle: AssistantSpeechHandle | None = None,
    ) -> PlaybackResult | None:
        if speech_handle and speech_handle.cancelled:
            return PlaybackResult(
                playback_id=None,
                sound_name="streaming-websocket",
                raw_wav_path=None,
                asterisk_wav_path=None,
                interrupted=True,
            )
        audio_frames = (frame for frame in frames if frame.audio)
        try:
            first_frame = next(audio_frames)
        except StopIteration:
            return None
        transport = self._websocket_connect(self.config.websocket_url)
        interrupted = False
        try:
            for frame in itertools.chain((first_frame,), audio_frames):
                if speech_handle and speech_handle.cancelled:
                    interrupted = True
                    flush_media(transport)
                    break
                payload = self._encoder.encode(frame)
                if payload:
                    _send_binary(transport, payload)
                if speech_handle and speech_handle.cancelled:
                    interrupted = True
                    flush_media(transport)
                    break
        finally:
            close = getattr(transport, "close", None)
            if close:
                close()
        return PlaybackResult(
            playback_id=None,
            sound_name="streaming-websocket",
            raw_wav_path=None,
            asterisk_wav_path=None,
            interrupted=interrupted,
        )


def create_output_sink(
    *,
    sink_name: str,
    ari_config: AriFilePlaybackConfig,
    ari_post: Callable[..., dict | None],
    streaming_config: StreamingWebSocketOutputConfig | None = None,
    websocket_connect: Callable[[str], object] | None = None,
) -> OutputSink:
    normalized = sink_name.strip().lower()
    if normalized in {"", "ari_file"}:
        return AriFilePlaybackSink(config=ari_config, ari_post=ari_post)
    if normalized in {"streaming", "streaming_websocket"}:
        if streaming_config is None or not streaming_config.websocket_url:
            return StreamingNotConfiguredSink()
        if websocket_connect is None:
            raise OutputSinkUnavailable("streaming websocket sink requires a connection factory")
        return StreamingWebSocketOutputSink(
            config=streaming_config,
            websocket_connect=websocket_connect,
        )
    raise ValueError(f"unknown output sink: {sink_name}")


def _validate_frame_shape(frames: Sequence[OutputAudioRawFrame]) -> tuple[int, int]:
    sample_rate = frames[0].sample_rate
    num_channels = frames[0].num_channels
    for frame in frames:
        if frame.sample_rate != sample_rate:
            raise ValueError("output frames must use one sample rate")
        if frame.num_channels != num_channels:
            raise ValueError("output frames must use one channel count")
    return sample_rate, num_channels


def _send_binary(transport, payload: bytes) -> None:
    if hasattr(transport, "send_binary"):
        transport.send_binary(payload)
        return
    transport.send(payload)


def _serializer_payload_to_bytes(payload) -> bytes:
    if payload is None:
        return b""
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, (list, tuple)):
        return b"".join(_serializer_payload_to_bytes(item) for item in payload)
    if isinstance(payload, str):
        raise TypeError("audio serializer returned text control data instead of bytes")
    raise TypeError(f"audio serializer returned unsupported payload: {type(payload).__name__}")


def _await_sync(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("async serializer cannot be awaited from a running event loop")
