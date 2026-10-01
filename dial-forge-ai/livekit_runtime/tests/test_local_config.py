import tempfile
import unittest
from unittest import mock
from pathlib import Path

from livekit_runtime.local_config import (
    build_local_handoff_handler,
    build_local_runtime_context,
    config_from_env,
    load_env_files,
)
from livekit_runtime.telephony import LocalTelephonyProfile


class LocalConfigTest(unittest.TestCase):
    def test_config_defaults_to_local_room(self):
        config = config_from_env({})

        self.assertEqual(config.profile, LocalTelephonyProfile.LOCAL_ROOM)
        self.assertEqual(config.company_key, "globifye")
        self.assertEqual(config.livekit_url, "ws://localhost:7880")
        self.assertEqual(config.media_provider, "direct")
        self.assertEqual(config.stt_provider, "deepgram")
        self.assertEqual(config.llm_provider, "groq")
        self.assertEqual(config.tts_provider, "deepgram")
        self.assertFalse(config.ivr_detection)

    def test_local_sip_defaults_ivr_detection_on(self):
        config = config_from_env({"DIALFORGE_LOCAL_PROFILE": "local-sip"})

        self.assertEqual(config.profile, LocalTelephonyProfile.LOCAL_SIP)
        self.assertTrue(config.ivr_detection)

    def test_livekit_handoff_config_enables_handoff(self):
        config = config_from_env(
            {
                "LIVEKIT_SUPERVISOR_PHONE_NUMBER": "+15550002222",
                "LIVEKIT_SIP_OUTBOUND_TRUNK": "ST_123",
                "LIVEKIT_SIP_NUMBER": "+15550001111",
            }
        )

        self.assertTrue(config.human_handoff_enabled)
        handler = build_local_handoff_handler(config)
        result = handler(reason="caller wants a human", urgency="urgent")

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "warm_transfer")
        self.assertEqual(result["endpoint"], "+15550002222")
        self.assertEqual(result["caller_id"], "+15550001111")

    def test_missing_livekit_handoff_config_returns_not_configured(self):
        config = config_from_env({})
        handler = build_local_handoff_handler(config)

        result = handler(reason="caller wants a human", urgency="normal")

        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "not_configured")
        self.assertEqual(result["invite_status"], "not_configured")

    def test_builds_runtime_context_from_repo_config(self):
        config = config_from_env(
            {
                "DIALFORGE_COMPANY_KEY": "globifye",
                "DIALFORGE_INITIAL_STAGE": "prospect",
                "DIALFORGE_STAGE_GRAPH_JSON": (
                    '{"prospect":{"edges":{"confirmed_worth_automating":'
                    '{"target":"contact","description":"caller is qualified"}}},'
                    '"contact":{"edges":{}}}'
                ),
                "DIALFORGE_HUMAN_HANDOFF_ENABLED": "true",
                "LIVEKIT_SUPERVISOR_PHONE_NUMBER": "+15550002222",
            }
        )

        context = build_local_runtime_context(config)

        self.assertEqual(context.company_key, "globifye")
        self.assertEqual(context.current_stage, "prospect")
        self.assertEqual(context.stage_transitions[0].name, "confirmed_worth_automating")
        self.assertTrue(context.session_state["human_handoff_enabled"])
        self.assertEqual(context.session_state["local_profile"], "local-room")

    def test_load_env_files_does_not_override_existing_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env.local"
            env_path.write_text("EXAMPLE_KEY=from-file\nOTHER_KEY='quoted'\n")
            env = {"EXAMPLE_KEY": "existing"}

            with mock.patch.dict("os.environ", env, clear=True):
                load_env_files((env_path,))
                import os

                self.assertEqual(os.environ["EXAMPLE_KEY"], "existing")
                self.assertEqual(os.environ["OTHER_KEY"], "quoted")


if __name__ == "__main__":
    unittest.main()
