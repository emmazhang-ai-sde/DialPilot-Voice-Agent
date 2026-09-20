from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlencode

from voice_turn_state import TurnHandlingConfig


@dataclass(frozen=True)
class ProviderTuning:
    deepgram_api_key: str = ""
    groq_api_key: str = ""
    modulate_api_key: str = ""
    modulate_base_url: str = "wss://platform.modulate.ai/api/velma-2-stt-streaming"
    modulate_audio_format: str = "s16le"
    modulate_sample_rate: int = 16000
    modulate_num_channels: int = 1
    modulate_speaker_diarization: bool = False
    modulate_partial_results: bool = True
    deepgram_tts_encoding: str = "linear16"
    deepgram_tts_sample_rate: int = 24000
    deepgram_tts_container: str = "none"
    tts_output_sink: str = "ari_file"
    tts_streaming_websocket_url: str = ""
    tts_streaming_asterisk_endpoint: str = "WebSocket/dialforge_ai_output/c(slin24)"
    tts_streaming_incoming_base_url: str = "ws://host.docker.internal:8791/dialforge-ai-output"
    tts_streaming_server_host: str = "0.0.0.0"
    tts_streaming_server_port: int = 8791
    tts_streaming_server_path: str = "/dialforge-ai-output"
    tts_streaming_transport_wait_timeout_ms: int = 3000
    tts_streaming_sample_rate: int = 24000
    tts_streaming_num_channels: int = 1
    asterisk_playback_sample_rate: int = 8000
    barge_in_detection_enabled: bool = True
    barge_in_rms_threshold: int = 0
    barge_in_min_audio_ms: int = 160
    barge_in_reset_gap_ms: int = 500
    turn_endpointing_min_delay_ms: int = 800
    turn_endpointing_max_delay_ms: int = 2500
    turn_incomplete_wait_ms: int = 5000
    turn_incomplete_short_wait_ms: int | None = None
    turn_incomplete_long_wait_ms: int | None = None
    turn_ambiguous_wait_ms: int = 1200
    turn_semantic_completion_enabled: bool = True
    turn_playback_echo_tail_ms: int = 500

    def modulate_url(self) -> str:
        return f"{self.modulate_base_url}?{urlencode(self.modulate_query_params())}"

    def modulate_query_params(self) -> dict[str, str]:
        return {
            "api_key": self.modulate_api_key,
            "audio_format": self.modulate_audio_format,
            "sample_rate": str(self.modulate_sample_rate),
            "num_channels": str(self.modulate_num_channels),
            "speaker_diarization": _bool_to_query(self.modulate_speaker_diarization),
            "partial_results": _bool_to_query(self.modulate_partial_results),
        }

    def turn_config(self) -> TurnHandlingConfig:
        return TurnHandlingConfig(
            endpointing_min_delay_ms=self.turn_endpointing_min_delay_ms,
            endpointing_max_delay_ms=self.turn_endpointing_max_delay_ms,
            incomplete_wait_ms=self.turn_incomplete_wait_ms,
            incomplete_short_wait_ms=self.turn_incomplete_short_wait_ms,
            incomplete_long_wait_ms=self.turn_incomplete_long_wait_ms,
            ambiguous_wait_ms=self.turn_ambiguous_wait_ms,
            semantic_completion_enabled=self.turn_semantic_completion_enabled,
            playback_echo_tail_ms=self.turn_playback_echo_tail_ms,
        )

    def redacted_payload(self) -> dict[str, object]:
        return {
            "keys": {
                "deepgram_api_key": _key_status(self.deepgram_api_key),
                "groq_api_key": _key_status(self.groq_api_key),
                "modulate_api_key": _key_status(self.modulate_api_key),
            },
            "modulate": {
                "base_url": self.modulate_base_url,
                "audio_format": self.modulate_audio_format,
                "sample_rate": self.modulate_sample_rate,
                "num_channels": self.modulate_num_channels,
                "speaker_diarization": self.modulate_speaker_diarization,
                "partial_results": self.modulate_partial_results,
            },
            "deepgram_tts": {
                "encoding": self.deepgram_tts_encoding,
                "sample_rate": self.deepgram_tts_sample_rate,
                "container": self.deepgram_tts_container,
                "output_sink": self.tts_output_sink,
                "streaming_websocket_url": _url_status(self.tts_streaming_websocket_url),
                "streaming_asterisk_endpoint": _url_status(
                    self.tts_streaming_asterisk_endpoint
                ),
                "streaming_incoming_base_url": _url_status(
                    self.tts_streaming_incoming_base_url
                ),
                "streaming_server_host": self.tts_streaming_server_host,
                "streaming_server_port": self.tts_streaming_server_port,
                "streaming_server_path": self.tts_streaming_server_path,
                "streaming_transport_wait_timeout_ms": (
                    self.tts_streaming_transport_wait_timeout_ms
                ),
                "streaming_sample_rate": self.tts_streaming_sample_rate,
                "streaming_num_channels": self.tts_streaming_num_channels,
            },
            "asterisk_playback": {
                "sample_rate": self.asterisk_playback_sample_rate,
            },
            "barge_in": {
                "enabled": self.barge_in_detection_enabled,
                "rms_threshold": self.barge_in_rms_threshold,
                "min_audio_ms": self.barge_in_min_audio_ms,
                "reset_gap_ms": self.barge_in_reset_gap_ms,
            },
            "turn_timing": {
                "endpointing_min_delay_ms": self.turn_endpointing_min_delay_ms,
                "endpointing_max_delay_ms": self.turn_endpointing_max_delay_ms,
                "incomplete_wait_ms": self.turn_incomplete_wait_ms,
                "incomplete_short_wait_ms": self.turn_incomplete_short_wait_ms,
                "incomplete_long_wait_ms": self.turn_incomplete_long_wait_ms,
                "ambiguous_wait_ms": self.turn_ambiguous_wait_ms,
                "semantic_completion_enabled": self.turn_semantic_completion_enabled,
                "playback_echo_tail_ms": self.turn_playback_echo_tail_ms,
            },
        }


def load_provider_tuning(
    *,
    env: dict[str, str] | None = None,
    env_files: list[str] | None = None,
) -> ProviderTuning:
    merged = {}
    for env_file in env_files or []:
        merged.update(read_env_file(env_file))
    merged.update(dict(os.environ if env is None else env))
    deepgram_tts_sample_rate = _int(
        merged,
        "DIALFORGE_DEEPGRAM_TTS_SAMPLE_RATE",
        ProviderTuning.deepgram_tts_sample_rate,
    )

    return ProviderTuning(
        deepgram_api_key=_get(merged, "DEEPGRAM_API_KEY", ""),
        groq_api_key=_get(merged, "GROQ_API_KEY", ""),
        modulate_api_key=_get(merged, "MODULATE_API_KEY", ""),
        modulate_base_url=_get(
            merged,
            "DIALFORGE_MODULATE_BASE_URL",
            ProviderTuning.modulate_base_url,
        ),
        modulate_audio_format=_get(
            merged,
            "DIALFORGE_MODULATE_AUDIO_FORMAT",
            ProviderTuning.modulate_audio_format,
        ),
        modulate_sample_rate=_int(
            merged,
            "DIALFORGE_MODULATE_SAMPLE_RATE",
            ProviderTuning.modulate_sample_rate,
        ),
        modulate_num_channels=_int(
            merged,
            "DIALFORGE_MODULATE_NUM_CHANNELS",
            ProviderTuning.modulate_num_channels,
        ),
        modulate_speaker_diarization=_bool(
            merged,
            "DIALFORGE_MODULATE_SPEAKER_DIARIZATION",
            ProviderTuning.modulate_speaker_diarization,
        ),
        modulate_partial_results=_bool(
            merged,
            "DIALFORGE_MODULATE_PARTIAL_RESULTS",
            ProviderTuning.modulate_partial_results,
        ),
        deepgram_tts_encoding=_get(
            merged,
            "DIALFORGE_DEEPGRAM_TTS_ENCODING",
            ProviderTuning.deepgram_tts_encoding,
        ),
        deepgram_tts_sample_rate=deepgram_tts_sample_rate,
        deepgram_tts_container=_get(
            merged,
            "DIALFORGE_DEEPGRAM_TTS_CONTAINER",
            ProviderTuning.deepgram_tts_container,
        ),
        tts_output_sink=_get(
            merged,
            "DIALFORGE_TTS_OUTPUT_SINK",
            ProviderTuning.tts_output_sink,
        ),
        tts_streaming_websocket_url=_get(
            merged,
            "DIALFORGE_TTS_STREAMING_WEBSOCKET_URL",
            ProviderTuning.tts_streaming_websocket_url,
        ),
        tts_streaming_asterisk_endpoint=_get(
            merged,
            "DIALFORGE_TTS_STREAMING_ASTERISK_ENDPOINT",
            ProviderTuning.tts_streaming_asterisk_endpoint,
        ),
        tts_streaming_incoming_base_url=_get(
            merged,
            "DIALFORGE_TTS_STREAMING_INCOMING_BASE_URL",
            ProviderTuning.tts_streaming_incoming_base_url,
        ),
        tts_streaming_server_host=_get(
            merged,
            "DIALFORGE_TTS_STREAMING_SERVER_HOST",
            ProviderTuning.tts_streaming_server_host,
        ),
        tts_streaming_server_port=_int(
            merged,
            "DIALFORGE_TTS_STREAMING_SERVER_PORT",
            ProviderTuning.tts_streaming_server_port,
        ),
        tts_streaming_server_path=_normalize_path(
            _get(
                merged,
                "DIALFORGE_TTS_STREAMING_SERVER_PATH",
                ProviderTuning.tts_streaming_server_path,
            )
        ),
        tts_streaming_transport_wait_timeout_ms=_int(
            merged,
            "DIALFORGE_TTS_STREAMING_TRANSPORT_WAIT_TIMEOUT_MS",
            ProviderTuning.tts_streaming_transport_wait_timeout_ms,
        ),
        tts_streaming_sample_rate=_int(
            merged,
            "DIALFORGE_TTS_STREAMING_SAMPLE_RATE",
            deepgram_tts_sample_rate,
        ),
        tts_streaming_num_channels=_int(
            merged,
            "DIALFORGE_TTS_STREAMING_NUM_CHANNELS",
            ProviderTuning.tts_streaming_num_channels,
        ),
        asterisk_playback_sample_rate=_int(
            merged,
            "DIALFORGE_ASTERISK_PLAYBACK_SAMPLE_RATE",
            ProviderTuning.asterisk_playback_sample_rate,
        ),
        barge_in_detection_enabled=_bool(
            merged,
            "DIALFORGE_BARGE_IN_DETECTION_ENABLED",
            ProviderTuning.barge_in_detection_enabled,
        ),
        barge_in_rms_threshold=_int(
            merged,
            "DIALFORGE_BARGE_IN_RMS_THRESHOLD",
            ProviderTuning.barge_in_rms_threshold,
        ),
        barge_in_min_audio_ms=_int(
            merged,
            "DIALFORGE_BARGE_IN_MIN_AUDIO_MS",
            ProviderTuning.barge_in_min_audio_ms,
        ),
        barge_in_reset_gap_ms=_int(
            merged,
            "DIALFORGE_BARGE_IN_RESET_GAP_MS",
            ProviderTuning.barge_in_reset_gap_ms,
        ),
        turn_endpointing_min_delay_ms=_int(
            merged,
            "DIALFORGE_TURN_ENDPOINTING_MIN_DELAY_MS",
            ProviderTuning.turn_endpointing_min_delay_ms,
        ),
        turn_endpointing_max_delay_ms=_int(
            merged,
            "DIALFORGE_TURN_ENDPOINTING_MAX_DELAY_MS",
            ProviderTuning.turn_endpointing_max_delay_ms,
        ),
        turn_incomplete_wait_ms=_int(
            merged,
            "DIALFORGE_TURN_INCOMPLETE_WAIT_MS",
            ProviderTuning.turn_incomplete_wait_ms,
        ),
        turn_incomplete_short_wait_ms=_optional_int(
            merged,
            "DIALFORGE_TURN_INCOMPLETE_SHORT_WAIT_MS",
            ProviderTuning.turn_incomplete_short_wait_ms,
        ),
        turn_incomplete_long_wait_ms=_optional_int(
            merged,
            "DIALFORGE_TURN_INCOMPLETE_LONG_WAIT_MS",
            ProviderTuning.turn_incomplete_long_wait_ms,
        ),
        turn_ambiguous_wait_ms=_int(
            merged,
            "DIALFORGE_TURN_AMBIGUOUS_WAIT_MS",
            ProviderTuning.turn_ambiguous_wait_ms,
        ),
        turn_semantic_completion_enabled=_bool(
            merged,
            "DIALFORGE_TURN_SEMANTIC_COMPLETION_ENABLED",
            ProviderTuning.turn_semantic_completion_enabled,
        ),
        turn_playback_echo_tail_ms=_int(
            merged,
            "DIALFORGE_TURN_PLAYBACK_ECHO_TAIL_MS",
            ProviderTuning.turn_playback_echo_tail_ms,
        ),
    )


def default_env_files(base_dir: str) -> list[str]:
    return [
        os.path.abspath(os.path.join(base_dir, "..", "..", ".env.local")),
        os.path.abspath(os.path.join(base_dir, "..", "..", "ai-pipeline", ".env.local")),
    ]


def read_env_file(path: str) -> dict[str, str]:
    values = {}
    try:
        with open(path) as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        return {}
    return values


def _get(env: dict[str, str], name: str, default):
    value = env.get(name)
    if value is None or value == "":
        return default
    return value


def _int(env: dict[str, str], name: str, default: int) -> int:
    value = _get(env, name, None)
    return default if value is None else int(value)


def _optional_int(env: dict[str, str], name: str, default: int | None) -> int | None:
    value = _get(env, name, None)
    return default if value is None else int(value)


def _bool(env: dict[str, str], name: str, default: bool) -> bool:
    value = _get(env, name, None)
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean-like value")


def _bool_to_query(value: bool) -> str:
    return "true" if value else "false"


def _normalize_path(value: str) -> str:
    value = value.strip()
    if not value:
        return "/"
    return value if value.startswith("/") else f"/{value}"


def _key_status(value: str) -> str:
    return "set" if value else "missing"


def _url_status(value: str) -> str:
    return "configured" if value else "missing"
