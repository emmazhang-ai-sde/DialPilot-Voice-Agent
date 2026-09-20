from __future__ import annotations

from dataclasses import dataclass

from voice_frame_bridge import OutputAudioRawFrame


@dataclass(frozen=True)
class AsteriskWebSocketFrameEncoder:
    sample_rate: int
    num_channels: int = 1
    sample_width_bytes: int = 2

    def encode(self, frame: OutputAudioRawFrame) -> bytes:
        if frame.sample_rate != self.sample_rate:
            raise ValueError("streaming frame sample rate does not match encoder")
        if frame.num_channels != self.num_channels:
            raise ValueError("streaming frame channel count does not match encoder")
        if len(frame.audio) % self.sample_width_bytes:
            raise ValueError("streaming frame must contain aligned 16-bit PCM samples")
        return bytes(frame.audio)
