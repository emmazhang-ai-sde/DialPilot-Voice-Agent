import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_turn_state import BargeInGate, TurnCompletionGate, TurnHandlingConfig


class TurnCompletionGateTest(unittest.TestCase):
    def make_gate(self):
        return TurnCompletionGate(
            TurnHandlingConfig(
                endpointing_min_delay_ms=800,
                endpointing_max_delay_ms=2500,
                incomplete_wait_ms=3000,
                incomplete_short_wait_ms=3000,
                incomplete_long_wait_ms=6000,
                ambiguous_wait_ms=1200,
                playback_echo_tail_ms=500,
            )
        )

    def test_final_waits_for_min_endpointing_delay(self):
        gate = self.make_gate()

        gate.on_final("I need a table", now=10.0)

        self.assertIsNone(gate.tick(now=10.7))
        committed = gate.tick(now=10.8)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "I need a table")
        self.assertEqual(committed.semantic_kind, "complete")

    def test_incomplete_final_waits_and_merges_next_final(self):
        gate = self.make_gate()

        gate.on_final("I need a table for", now=10.0)

        self.assertIsNone(gate.tick(now=10.8))

        gate.on_final("six people", now=11.0)
        committed = gate.tick(now=11.8)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "I need a table for six people")
        self.assertEqual(committed.segments, ("I need a table for", "six people"))

    def test_incomplete_final_eventually_commits_after_wait(self):
        gate = self.make_gate()

        gate.on_final("I am calling because", now=10.0)

        self.assertIsNone(gate.tick(now=12.9))
        committed = gate.tick(now=13.0)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "I am calling because")

    def test_partial_speech_delays_pending_commit(self):
        gate = self.make_gate()

        gate.on_final("I need a table", now=10.0)
        gate.on_partial("actually I also", now=10.7)

        self.assertIsNone(gate.tick(now=11.6))

        gate.on_final("actually I also need catering", now=11.7)
        committed = gate.tick(now=12.5)

        self.assertIsNotNone(committed)
        self.assertEqual(
            committed.transcript,
            "I need a table actually I also need catering",
        )

    def test_reset_pending_drops_uncommitted_segments(self):
        gate = self.make_gate()

        gate.on_partial("I need", now=10.0)
        gate.on_final("I need a table", now=10.2)
        gate.reset_pending()

        self.assertIsNone(gate.tick(now=20.0))

    def test_punctuation_marks_complete_turn(self):
        gate = self.make_gate()

        gate.on_final("Can I book a table?", now=10.0)
        committed = gate.tick(now=10.8)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "Can I book a table?")

    def test_playback_suppresses_partial_and_final_input(self):
        gate = self.make_gate()

        gate.on_playback_started("playback-1", now=10.0)

        self.assertFalse(gate.on_partial("hello", now=10.1))
        self.assertFalse(gate.on_final("hello", now=10.2))
        self.assertIsNone(gate.tick(now=20.0))

    def test_playback_finish_suppresses_echo_tail_then_allows_input(self):
        gate = self.make_gate()

        gate.on_playback_started("playback-1", now=10.0)
        self.assertTrue(gate.on_playback_finished("playback-1", now=12.0))

        self.assertFalse(gate.on_final("echo", now=12.4))
        self.assertTrue(gate.on_final("real caller", now=12.5))
        committed = gate.tick(now=13.8)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "real caller")
        self.assertEqual(committed.semantic_kind, "ambiguous")

    def test_playback_interruption_reopens_input_immediately(self):
        gate = self.make_gate()

        gate.on_playback_started("playback-1", now=10.0)
        self.assertTrue(gate.on_playback_interrupted("playback-1", now=10.2))

        self.assertTrue(gate.on_final("wait", now=10.3))
        committed = gate.tick(now=11.3)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "wait")

    def test_barge_in_confirmed_reopens_input_without_echo_tail(self):
        gate = self.make_gate()

        gate.on_playback_started("playback-1", now=10.0)
        self.assertTrue(gate.on_barge_in_confirmed("playback-1", now=10.2))

        self.assertTrue(gate.on_final("wait", now=10.21))
        committed = gate.tick(now=11.21)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "wait")

    def test_stale_playback_finish_does_not_clear_suppression(self):
        gate = self.make_gate()

        gate.on_playback_started("playback-2", now=10.0)

        self.assertFalse(gate.on_playback_finished("playback-1", now=10.2))
        self.assertFalse(gate.on_final("still suppressed", now=10.3))

    def test_reset_pending_keeps_playback_suppression(self):
        gate = self.make_gate()

        gate.on_playback_started("playback-1", now=10.0)
        gate.reset_pending()

        self.assertFalse(gate.on_final("still suppressed", now=10.1))

    def test_backchannel_commits_with_semantic_metadata(self):
        gate = self.make_gate()

        gate.on_final("yeah", now=10.0)
        committed = gate.tick(now=10.8)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.transcript, "yeah")
        self.assertEqual(committed.semantic_kind, "backchannel")
        self.assertEqual(committed.semantic_reason, "short acknowledgement")

    def test_ambiguous_short_phrase_uses_adaptive_wait(self):
        gate = self.make_gate()

        gate.on_final("maybe tomorrow", now=10.0)

        self.assertIsNone(gate.tick(now=10.8))
        committed = gate.tick(now=11.3)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.semantic_kind, "ambiguous")

    def test_incomplete_long_phrase_uses_longer_wait(self):
        gate = self.make_gate()

        gate.on_final("I need to talk with someone from accounting because", now=10.0)

        self.assertIsNone(gate.tick(now=15.9))
        committed = gate.tick(now=16.0)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.semantic_kind, "incomplete_long")

    def test_question_shape_is_complete(self):
        gate = self.make_gate()

        gate.on_final("Can you help me?", now=10.0)
        committed = gate.tick(now=10.8)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.semantic_kind, "complete")
        self.assertEqual(committed.semantic_reason, "terminal punctuation")

    def test_semantic_completion_can_be_disabled(self):
        gate = TurnCompletionGate(
            TurnHandlingConfig(
                endpointing_min_delay_ms=800,
                endpointing_max_delay_ms=2500,
                incomplete_wait_ms=3000,
                ambiguous_wait_ms=1200,
                semantic_completion_enabled=False,
            )
        )

        gate.on_final("maybe tomorrow", now=10.0)
        committed = gate.tick(now=10.8)

        self.assertIsNotNone(committed)
        self.assertEqual(committed.semantic_kind, "complete")
        self.assertEqual(committed.semantic_reason, "semantic completion disabled")


class BargeInGateTest(unittest.TestCase):
    def test_interrupt_keyword_during_assistant_playback_interrupts(self):
        decision = BargeInGate().decide_transcript(
            "wait",
            suppression_reason="assistant_playback",
        )

        self.assertTrue(decision.should_interrupt)
        self.assertEqual(decision.reason, "interrupt_keyword_during_assistant_playback")

    def test_backchannel_during_assistant_playback_does_not_interrupt(self):
        decision = BargeInGate().decide_transcript(
            "yeah",
            suppression_reason="assistant_playback",
        )

        self.assertFalse(decision.should_interrupt)
        self.assertEqual(decision.reason, "backchannel_during_assistant_playback")

    def test_echo_tail_transcript_does_not_interrupt(self):
        decision = BargeInGate().decide_transcript(
            "stop",
            suppression_reason="playback_echo_tail",
        )

        self.assertFalse(decision.should_interrupt)
        self.assertEqual(decision.reason, "echo_tail_transcript_suppressed")

    def test_sustained_audio_candidate_interrupts_during_assistant_playback(self):
        decision = BargeInGate().decide_audio_candidate(
            object(),
            suppression_reason="assistant_playback",
        )

        self.assertTrue(decision.should_interrupt)
        self.assertEqual(decision.reason, "sustained_audio_during_assistant_playback")

    def test_audio_candidate_in_echo_tail_does_not_interrupt(self):
        decision = BargeInGate().decide_audio_candidate(
            object(),
            suppression_reason="playback_echo_tail",
        )

        self.assertFalse(decision.should_interrupt)
        self.assertEqual(decision.reason, "echo_tail_audio_suppressed")


if __name__ == "__main__":
    unittest.main()
