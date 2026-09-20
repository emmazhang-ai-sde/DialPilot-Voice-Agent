import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from asterisk_streaming_encoder import AsteriskWebSocketFrameEncoder
from voice_frame_bridge import OutputAudioRawFrame


class AsteriskWebSocketFrameEncoderTest(unittest.TestCase):
    def test_encodes_raw_binary_audio(self):
        encoder = AsteriskWebSocketFrameEncoder(sample_rate=24000, num_channels=1)
        frame = OutputAudioRawFrame(
            audio=b"\x01\x00\x02\x00",
            sample_rate=24000,
            num_channels=1,
        )

        self.assertEqual(encoder.encode(frame), b"\x01\x00\x02\x00")

    def test_rejects_unexpected_sample_rate(self):
        encoder = AsteriskWebSocketFrameEncoder(sample_rate=24000, num_channels=1)

        with self.assertRaises(ValueError):
            encoder.encode(
                OutputAudioRawFrame(audio=b"\x01\x00", sample_rate=16000, num_channels=1)
            )

    def test_rejects_unexpected_channel_count(self):
        encoder = AsteriskWebSocketFrameEncoder(sample_rate=24000, num_channels=1)

        with self.assertRaises(ValueError):
            encoder.encode(
                OutputAudioRawFrame(audio=b"\x01\x00", sample_rate=24000, num_channels=2)
            )

    def test_rejects_unaligned_pcm(self):
        encoder = AsteriskWebSocketFrameEncoder(sample_rate=24000, num_channels=1)

        with self.assertRaises(ValueError):
            encoder.encode(
                OutputAudioRawFrame(audio=b"\x01", sample_rate=24000, num_channels=1)
            )


if __name__ == "__main__":
    unittest.main()
