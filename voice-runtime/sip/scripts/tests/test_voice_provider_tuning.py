import os
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "archive",
        "asterisk_legacy",
    ),
)

from voice_provider_tuning import load_provider_tuning, read_env_file


class ProviderTuningTest(unittest.TestCase):
    def test_defaults(self):
        tuning = load_provider_tuning(env={})

        self.assertEqual(tuning.modulate_sample_rate, 16000)
        self.assertEqual(tuning.modulate_num_channels, 1)
        self.assertEqual(tuning.deepgram_tts_sample_rate, 24000)
        self.assertEqual(tuning.asterisk_playback_sample_rate, 8000)
        self.assertEqual(tuning.tts_output_sink, "ari_file")
        self.assertEqual(tuning.tts_streaming_websocket_url, "")
        self.assertEqual(
            tuning.tts_streaming_asterisk_endpoint,
            "WebSocket/dialforge_ai_output/c(slin24)",
        )
        self.assertEqual(
            tuning.tts_streaming_incoming_base_url,
            "ws://host.docker.internal:8791/dialforge-ai-output",
        )
        self.assertEqual(tuning.tts_streaming_server_host, "0.0.0.0")
        self.assertEqual(tuning.tts_streaming_server_port, 8791)
        self.assertEqual(tuning.tts_streaming_server_path, "/dialforge-ai-output")
        self.assertEqual(tuning.tts_streaming_transport_wait_timeout_ms, 3000)
        self.assertEqual(tuning.tts_streaming_sample_rate, 24000)
        self.assertEqual(tuning.tts_streaming_num_channels, 1)
        self.assertTrue(tuning.barge_in_detection_enabled)
        self.assertEqual(tuning.barge_in_rms_threshold, 0)
        self.assertEqual(tuning.barge_in_min_audio_ms, 160)
        self.assertEqual(tuning.barge_in_reset_gap_ms, 500)
        self.assertTrue(tuning.modulate_partial_results)
        self.assertFalse(tuning.modulate_speaker_diarization)

    def test_env_overrides(self):
        tuning = load_provider_tuning(
            env={
                "DIALFORGE_MODULATE_SAMPLE_RATE": "8000",
                "DIALFORGE_MODULATE_NUM_CHANNELS": "2",
                "DIALFORGE_DEEPGRAM_TTS_SAMPLE_RATE": "16000",
                "DIALFORGE_ASTERISK_PLAYBACK_SAMPLE_RATE": "16000",
                "DIALFORGE_TTS_OUTPUT_SINK": "streaming_websocket",
                "DIALFORGE_TTS_STREAMING_WEBSOCKET_URL": "ws://example.test/media",
                "DIALFORGE_TTS_STREAMING_ASTERISK_ENDPOINT": "WebSocket/output",
                "DIALFORGE_TTS_STREAMING_INCOMING_BASE_URL": "ws://localhost:8790/media",
                "DIALFORGE_TTS_STREAMING_SERVER_HOST": "127.0.0.1",
                "DIALFORGE_TTS_STREAMING_SERVER_PORT": "8792",
                "DIALFORGE_TTS_STREAMING_SERVER_PATH": "media-output",
                "DIALFORGE_TTS_STREAMING_TRANSPORT_WAIT_TIMEOUT_MS": "1200",
                "DIALFORGE_TTS_STREAMING_SAMPLE_RATE": "8000",
                "DIALFORGE_TTS_STREAMING_NUM_CHANNELS": "1",
                "DIALFORGE_BARGE_IN_DETECTION_ENABLED": "false",
                "DIALFORGE_BARGE_IN_RMS_THRESHOLD": "80",
                "DIALFORGE_BARGE_IN_MIN_AUDIO_MS": "160",
                "DIALFORGE_BARGE_IN_RESET_GAP_MS": "350",
                "DIALFORGE_TURN_ENDPOINTING_MIN_DELAY_MS": "900",
                "DIALFORGE_TURN_INCOMPLETE_SHORT_WAIT_MS": "4000",
                "DIALFORGE_TURN_SEMANTIC_COMPLETION_ENABLED": "false",
            }
        )

        self.assertEqual(tuning.modulate_sample_rate, 8000)
        self.assertEqual(tuning.modulate_num_channels, 2)
        self.assertEqual(tuning.deepgram_tts_sample_rate, 16000)
        self.assertEqual(tuning.asterisk_playback_sample_rate, 16000)
        self.assertEqual(tuning.tts_output_sink, "streaming_websocket")
        self.assertEqual(tuning.tts_streaming_websocket_url, "ws://example.test/media")
        self.assertEqual(tuning.tts_streaming_asterisk_endpoint, "WebSocket/output")
        self.assertEqual(tuning.tts_streaming_incoming_base_url, "ws://localhost:8790/media")
        self.assertEqual(tuning.tts_streaming_server_host, "127.0.0.1")
        self.assertEqual(tuning.tts_streaming_server_port, 8792)
        self.assertEqual(tuning.tts_streaming_server_path, "/media-output")
        self.assertEqual(tuning.tts_streaming_transport_wait_timeout_ms, 1200)
        self.assertEqual(tuning.tts_streaming_sample_rate, 8000)
        self.assertFalse(tuning.barge_in_detection_enabled)
        self.assertEqual(tuning.barge_in_rms_threshold, 80)
        self.assertEqual(tuning.barge_in_min_audio_ms, 160)
        self.assertEqual(tuning.barge_in_reset_gap_ms, 350)
        self.assertEqual(tuning.turn_config().endpointing_min_delay_ms, 900)
        self.assertEqual(tuning.turn_config().incomplete_short_wait_ms, 4000)
        self.assertFalse(tuning.turn_config().semantic_completion_enabled)

    def test_streaming_sample_rate_defaults_to_deepgram_tts_sample_rate(self):
        tuning = load_provider_tuning(
            env={"DIALFORGE_DEEPGRAM_TTS_SAMPLE_RATE": "16000"}
        )

        self.assertEqual(tuning.deepgram_tts_sample_rate, 16000)
        self.assertEqual(tuning.tts_streaming_sample_rate, 16000)

    def test_modulate_url_construction(self):
        tuning = load_provider_tuning(
            env={
                "MODULATE_API_KEY": "secret-key",
                "DIALFORGE_MODULATE_BASE_URL": "wss://example.test/stt",
                "DIALFORGE_MODULATE_SAMPLE_RATE": "8000",
                "DIALFORGE_MODULATE_SPEAKER_DIARIZATION": "true",
                "DIALFORGE_MODULATE_PARTIAL_RESULTS": "false",
            }
        )

        parsed = urlparse(tuning.modulate_url())
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "wss")
        self.assertEqual(parsed.netloc, "example.test")
        self.assertEqual(parsed.path, "/stt")
        self.assertEqual(query["api_key"], ["secret-key"])
        self.assertEqual(query["sample_rate"], ["8000"])
        self.assertEqual(query["speaker_diarization"], ["true"])
        self.assertEqual(query["partial_results"], ["false"])

    def test_boolean_parsing_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            load_provider_tuning(
                env={"DIALFORGE_MODULATE_PARTIAL_RESULTS": "sometimes"}
            )

    def test_redacted_payload_does_not_expose_keys(self):
        tuning = load_provider_tuning(
            env={
                "DEEPGRAM_API_KEY": "deepgram-secret",
                "GROQ_API_KEY": "groq-secret",
                "MODULATE_API_KEY": "modulate-secret",
            }
        )

        payload = tuning.redacted_payload()

        self.assertEqual(payload["keys"]["deepgram_api_key"], "set")
        self.assertEqual(payload["keys"]["groq_api_key"], "set")
        self.assertEqual(payload["keys"]["modulate_api_key"], "set")
        self.assertNotIn("secret", repr(payload))

    def test_streaming_url_is_redacted(self):
        tuning = load_provider_tuning(
            env={"DIALFORGE_TTS_STREAMING_WEBSOCKET_URL": "ws://secret.test/media"}
        )

        payload = tuning.redacted_payload()

        self.assertEqual(payload["deepgram_tts"]["streaming_websocket_url"], "configured")
        self.assertNotIn("secret.test", repr(payload))

    def test_env_file_loading_and_environment_override(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("DIALFORGE_MODULATE_SAMPLE_RATE=8000\n")
            env_file.write("DIALFORGE_TURN_AMBIGUOUS_WAIT_MS='1500'\n")
            env_path = env_file.name
        try:
            self.assertEqual(
                read_env_file(env_path),
                {
                    "DIALFORGE_MODULATE_SAMPLE_RATE": "8000",
                    "DIALFORGE_TURN_AMBIGUOUS_WAIT_MS": "1500",
                },
            )
            tuning = load_provider_tuning(
                env={"DIALFORGE_MODULATE_SAMPLE_RATE": "16000"},
                env_files=[env_path],
            )
            self.assertEqual(tuning.modulate_sample_rate, 16000)
            self.assertEqual(tuning.turn_ambiguous_wait_ms, 1500)
        finally:
            os.unlink(env_path)


if __name__ == "__main__":
    unittest.main()
