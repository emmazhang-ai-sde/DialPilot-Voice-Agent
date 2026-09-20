import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_frame_bridge import (
    AgentAudioBridgeInputGate,
    BargeInDetectionConfig,
    LiveAudioFrameBridge,
    asterisk_slin16be_to_s16le,
)


class LiveAudioFrameBridgeTest(unittest.TestCase):
    def test_asterisk_slin16_big_endian_payload_becomes_s16le(self):
        payload = b"\x01\x02\x03\x04"

        self.assertEqual(asterisk_slin16be_to_s16le(payload), b"\x02\x01\x04\x03")

    def test_odd_input_byte_is_dropped_before_conversion(self):
        payload = b"\x01\x02\xff"

        self.assertEqual(asterisk_slin16be_to_s16le(payload), b"\x02\x01")

    def test_input_frame_has_stt_media_shape(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=16000,
            input_num_channels=1,
            tts_sample_rate=24000,
        )

        frame = bridge.input_frame_from_rtp_payload(b"\x01\x02")

        self.assertEqual(frame.audio, b"\x02\x01")
        self.assertEqual(frame.sample_rate, 16000)
        self.assertEqual(frame.num_channels, 1)

    def test_input_suppression_happens_before_stt_forwarding(self):
        suppress = True
        bridge = LiveAudioFrameBridge(
            input_sample_rate=16000,
            input_num_channels=1,
            tts_sample_rate=24000,
            should_suppress_input=lambda: suppress,
        )
        frame = bridge.input_frame_from_rtp_payload(b"\x01\x02")

        self.assertFalse(bridge.should_forward_input_frame(frame))

        suppress = False

        self.assertTrue(bridge.should_forward_input_frame(frame))

    def test_ai_speaking_gate_suppresses_input_before_stt_forwarding(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=16000,
            input_num_channels=1,
            tts_sample_rate=24000,
        )
        frame = bridge.input_frame_from_rtp_payload(b"\x01\x02")

        bridge.mark_ai_speaking()

        self.assertEqual(bridge.input_suppression_reason(), "assistant_playback")
        self.assertFalse(bridge.should_forward_input_frame(frame))

        bridge.mark_ai_interrupted()

        self.assertTrue(bridge.should_forward_input_frame(frame))

    def test_ai_done_speaking_enters_echo_tail_until_it_expires(self):
        now = [10.0]
        gate = AgentAudioBridgeInputGate(echo_tail_ms=500, clock=lambda: now[0])

        gate.mark_ai_speaking()
        self.assertEqual(gate.input_suppression_reason(), "assistant_playback")

        gate.mark_ai_done_speaking()

        self.assertEqual(gate.input_suppression_reason(), "playback_echo_tail")
        now[0] = 10.5
        self.assertIsNone(gate.input_suppression_reason())

    def test_reset_gate_reopens_forwarding_and_clears_candidate(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=1000,
            input_num_channels=1,
            tts_sample_rate=24000,
            barge_in_rms_threshold=500,
            barge_in_min_audio_ms=200,
        )
        frame = bridge.input_frame_from_rtp_payload(_slin16be_samples([1000] * 100))
        bridge.mark_ai_speaking()

        self.assertIsNone(bridge.detect_barge_in_candidate(frame))
        self.assertIsNotNone(bridge.detect_barge_in_candidate(frame))

        bridge.reset_gate()

        self.assertTrue(bridge.should_forward_input_frame(frame))
        bridge.mark_ai_speaking()
        self.assertIsNone(bridge.detect_barge_in_candidate(frame))

    def test_empty_input_frame_is_not_forwarded(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=16000,
            input_num_channels=1,
            tts_sample_rate=24000,
        )
        frame = bridge.input_frame_from_rtp_payload(b"\xff")

        self.assertFalse(bridge.should_forward_input_frame(frame))

    def test_tts_chunk_wraps_as_output_frame(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=16000,
            input_num_channels=1,
            tts_sample_rate=24000,
        )

        frame = bridge.output_frame_from_tts_chunk(b"\x01\x00\x02\x00")

        self.assertEqual(frame.audio, b"\x01\x00\x02\x00")
        self.assertEqual(frame.sample_rate, 24000)
        self.assertEqual(frame.num_channels, 1)

    def test_tts_chunk_rejects_incomplete_linear16_sample(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=16000,
            input_num_channels=1,
            tts_sample_rate=24000,
        )

        with self.assertRaises(ValueError):
            bridge.output_frame_from_tts_chunk(b"\x01")

    def test_sustained_audio_creates_barge_in_candidate_during_suppression(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=1000,
            input_num_channels=1,
            tts_sample_rate=24000,
            should_suppress_input=lambda: True,
            barge_in_rms_threshold=500,
            barge_in_min_audio_ms=200,
        )
        frame = bridge.input_frame_from_rtp_payload(_slin16be_samples([1000] * 100))

        self.assertIsNone(bridge.detect_barge_in_candidate(frame))
        candidate = bridge.detect_barge_in_candidate(frame)

        self.assertIsNotNone(candidate)
        self.assertGreaterEqual(candidate.audio_rms, 500)
        self.assertEqual(candidate.accumulated_audio_ms, 200)

    def test_disabled_barge_in_detection_does_not_create_candidate(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=1000,
            input_num_channels=1,
            tts_sample_rate=24000,
            should_suppress_input=lambda: True,
            barge_in_detection_config=BargeInDetectionConfig(
                enabled=False,
                rms_threshold=500,
                min_audio_ms=100,
            ),
        )
        frame = bridge.input_frame_from_rtp_payload(_slin16be_samples([1000] * 100))

        self.assertIsNone(bridge.detect_barge_in_candidate(frame))
        self.assertIsNone(bridge.detect_barge_in_candidate(frame))

    def test_barge_in_reset_gap_starts_a_new_candidate_window(self):
        now = [10.0]
        bridge = LiveAudioFrameBridge(
            input_sample_rate=1000,
            input_num_channels=1,
            tts_sample_rate=24000,
            should_suppress_input=lambda: True,
            barge_in_detection_config=BargeInDetectionConfig(
                enabled=True,
                rms_threshold=500,
                min_audio_ms=200,
                reset_gap_ms=250,
            ),
            clock=lambda: now[0],
        )
        frame = bridge.input_frame_from_rtp_payload(_slin16be_samples([1000] * 100))

        self.assertIsNone(bridge.detect_barge_in_candidate(frame))
        now[0] = 10.3
        self.assertIsNone(bridge.detect_barge_in_candidate(frame))
        now[0] = 10.4
        candidate = bridge.detect_barge_in_candidate(frame)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.accumulated_audio_ms, 200)

    def test_low_energy_resets_barge_in_candidate(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=1000,
            input_num_channels=1,
            tts_sample_rate=24000,
            should_suppress_input=lambda: True,
            barge_in_rms_threshold=500,
            barge_in_min_audio_ms=200,
        )
        loud = bridge.input_frame_from_rtp_payload(_slin16be_samples([1000] * 100))
        quiet = bridge.input_frame_from_rtp_payload(_slin16be_samples([10] * 100))

        self.assertIsNone(bridge.detect_barge_in_candidate(loud))
        self.assertIsNone(bridge.detect_barge_in_candidate(quiet))
        self.assertIsNone(bridge.detect_barge_in_candidate(loud))

    def test_barge_in_candidate_requires_suppressed_input(self):
        bridge = LiveAudioFrameBridge(
            input_sample_rate=1000,
            input_num_channels=1,
            tts_sample_rate=24000,
            should_suppress_input=lambda: False,
            barge_in_rms_threshold=500,
            barge_in_min_audio_ms=100,
        )
        frame = bridge.input_frame_from_rtp_payload(_slin16be_samples([1000] * 100))

        self.assertIsNone(bridge.detect_barge_in_candidate(frame))

def _slin16be_samples(samples):
    return b"".join(sample.to_bytes(2, "big", signed=True) for sample in samples)


if __name__ == "__main__":
    unittest.main()
