import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "archive",
        "asterisk_legacy",
    ),
)

from voice_runtime_frames import (
    AssistantTextFrame,
    UserTurnFrame,
    user_turn_frame_from_committed,
)
from voice_turn_state import CommittedTurn


class VoiceRuntimeFramesTest(unittest.TestCase):
    def test_user_turn_frame_from_committed_preserves_turn_metadata(self):
        committed = CommittedTurn(
            transcript="wait actually",
            segments=("wait", "actually"),
            committed_at=10.0,
            silence_ms=900,
            semantic_kind="complete",
            semantic_reason="terminal punctuation",
        )

        frame = user_turn_frame_from_committed(committed, epoch=3)

        self.assertEqual(
            frame,
            UserTurnFrame(
                text="wait actually",
                epoch=3,
                segments=("wait", "actually"),
                silence_ms=900,
                semantic_kind="complete",
                semantic_reason="terminal punctuation",
            ),
        )

    def test_assistant_text_frame_carries_epoch(self):
        frame = AssistantTextFrame(text="Sure, one moment.", epoch=4)

        self.assertEqual(frame.text, "Sure, one moment.")
        self.assertEqual(frame.epoch, 4)


if __name__ == "__main__":
    unittest.main()
