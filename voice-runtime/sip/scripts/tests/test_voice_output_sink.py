import os
import sys
import tempfile
import unittest
import wave

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "archive",
        "asterisk_legacy",
    ),
)

from voice_frame_bridge import OutputAudioRawFrame
from voice_output_sink import (
    AriFilePlaybackConfig,
    AriFilePlaybackSink,
    AssistantSpeechHandle,
    OutputSinkUnavailable,
    SerializerFrameEncoder,
    StreamingWebSocketOutputConfig,
    StreamingWebSocketOutputSink,
    create_output_sink,
    pipecat_audio_frame_converter,
)


class AriFilePlaybackSinkTest(unittest.TestCase):
    def make_sink(self, staging_dir, *, ari_result=None):
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))

        def fake_ari_post(path, **params):
            calls.append((path, params))
            return ari_result if ari_result is not None else {"id": "playback-1"}

        sink = AriFilePlaybackSink(
            config=AriFilePlaybackConfig(
                staging_dir=staging_dir,
                asterisk_container="asterisk-mvp",
                sounds_dir_in_container="/var/lib/asterisk/sounds/custom",
            ),
            ari_post=fake_ari_post,
            subprocess_run=fake_run,
        )
        return sink, calls

    def test_play_writes_wav_copies_file_and_starts_ari_playback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink, calls = self.make_sink(tmpdir)

            result = sink.play(
                frames=[
                    OutputAudioRawFrame(
                        audio=b"\x01\x00\x02\x00",
                        sample_rate=24000,
                        num_channels=1,
                    )
                ],
                channel_id="channel-1",
            )

            self.assertEqual(result.playback_id, "playback-1")
            self.assertEqual(result.sound_name, "reply_1")
            self.assertFalse(result.interrupted)
            with wave.open(result.raw_wav_path, "rb") as wav_file:
                self.assertEqual(wav_file.getframerate(), 24000)
                self.assertEqual(wav_file.getnchannels(), 1)
                self.assertEqual(wav_file.readframes(2), b"\x01\x00\x02\x00")
            self.assertEqual(calls[0][0][0], "ffmpeg")
            self.assertEqual(calls[1][0][0:2], ["docker", "cp"])
            self.assertEqual(
                calls[2],
                (
                    "/channels/channel-1/play",
                    {"media": "sound:custom/reply_1"},
                ),
            )

    def test_empty_frames_do_not_start_playback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink, calls = self.make_sink(tmpdir)

            result = sink.play(frames=[], channel_id="channel-1")

            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_cancelled_handle_prevents_ari_file_playback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink, calls = self.make_sink(tmpdir)
            handle = AssistantSpeechHandle(turn_id="turn-1", epoch=1)
            handle.cancel()

            result = sink.play(
                frames=[
                    OutputAudioRawFrame(
                        audio=b"\x01\x00",
                        sample_rate=24000,
                        num_channels=1,
                    )
                ],
                channel_id="channel-1",
                speech_handle=handle,
            )

            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_silent_frames_do_not_start_playback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink, calls = self.make_sink(tmpdir)

            result = sink.play(
                frames=[
                    OutputAudioRawFrame(audio=b"", sample_rate=24000, num_channels=1)
                ],
                channel_id="channel-1",
            )

            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_rejects_mixed_sample_rates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink, _ = self.make_sink(tmpdir)

            with self.assertRaises(ValueError):
                sink.play(
                    frames=[
                        OutputAudioRawFrame(
                            audio=b"\x01\x00",
                            sample_rate=24000,
                            num_channels=1,
                        ),
                        OutputAudioRawFrame(
                            audio=b"\x02\x00",
                            sample_rate=16000,
                            num_channels=1,
                        ),
                    ],
                    channel_id="channel-1",
                )

    def test_rejects_mixed_channel_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink, _ = self.make_sink(tmpdir)

            with self.assertRaises(ValueError):
                sink.play(
                    frames=[
                        OutputAudioRawFrame(
                            audio=b"\x01\x00",
                            sample_rate=24000,
                            num_channels=1,
                        ),
                        OutputAudioRawFrame(
                            audio=b"\x02\x00",
                            sample_rate=24000,
                            num_channels=2,
                        ),
                    ],
                    channel_id="channel-1",
                )

    def test_factory_selects_ari_file_sink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink = create_output_sink(
                sink_name="ari_file",
                ari_config=AriFilePlaybackConfig(
                    staging_dir=tmpdir,
                    asterisk_container="asterisk-mvp",
                    sounds_dir_in_container="/sounds",
                ),
                ari_post=lambda path, **params: {"id": "playback-1"},
            )

            self.assertIsInstance(sink, AriFilePlaybackSink)

    def test_streaming_placeholder_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sink = create_output_sink(
                sink_name="streaming",
                ari_config=AriFilePlaybackConfig(
                    staging_dir=tmpdir,
                    asterisk_container="asterisk-mvp",
                    sounds_dir_in_container="/sounds",
                ),
                ari_post=lambda path, **params: {"id": "playback-1"},
            )

            with self.assertRaises(OutputSinkUnavailable):
                sink.play(frames=[], channel_id="channel-1")

    def test_unknown_sink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                create_output_sink(
                    sink_name="unknown",
                    ari_config=AriFilePlaybackConfig(
                        staging_dir=tmpdir,
                        asterisk_container="asterisk-mvp",
                        sounds_dir_in_container="/sounds",
                    ),
                    ari_post=lambda path, **params: {"id": "playback-1"},
                )


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.sent_text = []
        self.closed = False

    def send(self, payload):
        self.sent.append(payload)

    def send_text(self, payload):
        self.sent_text.append(payload)

    def close(self):
        self.closed = True


class StreamingWebSocketOutputSinkTest(unittest.TestCase):
    def test_streams_frames_in_order(self):
        transport = FakeWebSocket()
        sink = StreamingWebSocketOutputSink(
            config=StreamingWebSocketOutputConfig(
                websocket_url="ws://example.test/media",
                sample_rate=24000,
                num_channels=1,
            ),
            websocket_connect=lambda url: transport,
        )

        result = sink.play(
            frames=[
                OutputAudioRawFrame(audio=b"\x01\x00", sample_rate=24000, num_channels=1),
                OutputAudioRawFrame(audio=b"\x02\x00", sample_rate=24000, num_channels=1),
            ],
            channel_id="channel-1",
        )

        self.assertEqual(result.sound_name, "streaming-websocket")
        self.assertFalse(result.interrupted)
        self.assertEqual(transport.sent, [b"\x01\x00", b"\x02\x00"])
        self.assertTrue(transport.closed)

    def test_streams_generator_frames_without_precollecting(self):
        transport = FakeWebSocket()
        events = []

        class RecordingEncoder:
            def encode(self, frame):
                events.append(("encode", frame.audio))
                return frame.audio

        def frames():
            for payload in (b"\x01\x00", b"\x02\x00"):
                events.append(("yield", payload))
                yield OutputAudioRawFrame(
                    audio=payload,
                    sample_rate=24000,
                    num_channels=1,
                )

        sink = StreamingWebSocketOutputSink(
            config=StreamingWebSocketOutputConfig(
                websocket_url="ws://example.test/media",
                sample_rate=24000,
                num_channels=1,
            ),
            websocket_connect=lambda url: transport,
            encoder=RecordingEncoder(),
        )

        result = sink.play(frames=frames(), channel_id="channel-1")

        self.assertFalse(result.interrupted)
        self.assertEqual(
            events,
            [
                ("yield", b"\x01\x00"),
                ("encode", b"\x01\x00"),
                ("yield", b"\x02\x00"),
                ("encode", b"\x02\x00"),
            ],
        )
        self.assertEqual(transport.sent, [b"\x01\x00", b"\x02\x00"])

    def test_cancelled_stream_flushes_media(self):
        transport = FakeWebSocket()
        handle = AssistantSpeechHandle(turn_id="turn-1", epoch=1)

        class CancellingEncoder:
            def __init__(self):
                self.count = 0

            def encode(self, frame):
                self.count += 1
                if self.count == 2:
                    handle.cancel()
                return frame.audio

        sink = StreamingWebSocketOutputSink(
            config=StreamingWebSocketOutputConfig(
                websocket_url="ws://example.test/media",
                sample_rate=24000,
                num_channels=1,
            ),
            websocket_connect=lambda url: transport,
            encoder=CancellingEncoder(),
        )

        result = sink.play(
            frames=[
                OutputAudioRawFrame(audio=b"\x01\x00", sample_rate=24000, num_channels=1),
                OutputAudioRawFrame(audio=b"\x02\x00", sample_rate=24000, num_channels=1),
                OutputAudioRawFrame(audio=b"\x03\x00", sample_rate=24000, num_channels=1),
            ],
            channel_id="channel-1",
            speech_handle=handle,
        )

        self.assertEqual(transport.sent, [b"\x01\x00", b"\x02\x00"])
        self.assertEqual(transport.sent_text, ["FLUSH_MEDIA"])
        self.assertTrue(result.interrupted)

    def test_cancelled_stream_before_connect_returns_interrupted(self):
        handle = AssistantSpeechHandle(turn_id="turn-1", epoch=1)
        handle.cancel()

        def connect(_url):
            raise AssertionError("streaming sink should not connect after pre-cancel")

        sink = StreamingWebSocketOutputSink(
            config=StreamingWebSocketOutputConfig(
                websocket_url="ws://example.test/media",
                sample_rate=24000,
                num_channels=1,
            ),
            websocket_connect=connect,
        )

        result = sink.play(
            frames=[
                OutputAudioRawFrame(audio=b"\x01\x00", sample_rate=24000, num_channels=1),
            ],
            channel_id="channel-1",
            speech_handle=handle,
        )

        self.assertTrue(result.interrupted)

    def test_serializer_frame_encoder_accepts_poc_style_serializer(self):
        class FakeSerializer:
            def __init__(self):
                self.seen = []

            def serialize(self, frame):
                self.seen.append(frame)
                return [bytearray(frame.audio[:1]), bytes(frame.audio[1:])]

        transport = FakeWebSocket()
        serializer = FakeSerializer()
        sink = StreamingWebSocketOutputSink(
            config=StreamingWebSocketOutputConfig(
                websocket_url="ws://example.test/media",
                sample_rate=24000,
                num_channels=1,
            ),
            websocket_connect=lambda url: transport,
            encoder=SerializerFrameEncoder(serializer),
        )

        result = sink.play(
            frames=[
                OutputAudioRawFrame(audio=b"\x01\x02", sample_rate=24000, num_channels=1),
            ],
            channel_id="channel-1",
        )

        self.assertFalse(result.interrupted)
        self.assertEqual(transport.sent, [b"\x01\x02"])
        self.assertEqual(serializer.seen[0].audio, b"\x01\x02")

    def test_pipecat_frame_converter_builds_audio_raw_frame(self):
        frame = pipecat_audio_frame_converter(
            OutputAudioRawFrame(audio=b"\x01\x02", sample_rate=24000, num_channels=1)
        )

        self.assertEqual(type(frame).__name__, "AudioRawFrame")
        self.assertEqual(frame.audio, b"\x01\x02")
        self.assertEqual(frame.sample_rate, 24000)
        self.assertEqual(frame.num_channels, 1)


if __name__ == "__main__":
    unittest.main()
