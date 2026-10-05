import unittest

from livekit_runtime.telephony import (
    LegacyAsteriskHandoffAdapter,
    LiveKitSIPConfig,
    LiveKitTelephonyAdapter,
    LocalTelephonyProfile,
    TelephonyConfigError,
    TelephonyHandoffRequest,
    build_local_room_profile,
    build_local_sip_profile,
    default_local_test_profiles,
    local_test_profile,
)


class FakeRuntimeContext:
    agent_config_id = "agent-globifye"
    call_session_id = "call-1"
    company_key = "globifye"


class TelephonyMigrationTest(unittest.TestCase):
    def test_local_room_profile_is_browser_based_and_does_not_require_sip(self):
        profile = build_local_room_profile()

        self.assertEqual(profile.name, LocalTelephonyProfile.LOCAL_ROOM)
        self.assertFalse(profile.requires_sip)
        self.assertIn("Browser", profile.client_entrypoint)
        self.assertIn("local LiveKit room", profile.media_path)
        self.assertTrue(any("meet.livekit.io" in command for command in profile.setup_commands))

    def test_local_sip_profile_keeps_linphone_integration_path(self):
        profile = build_local_sip_profile(sip_uri="sip:192.0.2.10:5060")

        self.assertEqual(profile.name, LocalTelephonyProfile.LOCAL_SIP)
        self.assertTrue(profile.requires_sip)
        self.assertIn("Linphone", profile.client_entrypoint)
        self.assertIn("livekit-sip", profile.media_path)
        self.assertTrue(any("livekit-sip" in command for command in profile.setup_commands))

    def test_default_profiles_expose_both_local_test_modes(self):
        profiles = default_local_test_profiles()

        self.assertEqual(set(profiles), {"local-room", "local-sip"})
        self.assertEqual(local_test_profile("local-room").name, LocalTelephonyProfile.LOCAL_ROOM)

    def test_unknown_profile_raises_clear_error(self):
        with self.assertRaisesRegex(TelephonyConfigError, "unknown local telephony profile"):
            local_test_profile("asterisk")

    def test_livekit_adapter_builds_warm_transfer_kwargs(self):
        adapter = LiveKitTelephonyAdapter(
            LiveKitSIPConfig(
                sip_trunk_id="trunk-123",
                sip_number="+15550001111",
                default_human_endpoint="+15550002222",
            )
        )
        request = TelephonyHandoffRequest(
            reason="caller asked for a human",
            urgency="urgent",
            preferred_team="sales",
        )

        kwargs = adapter.build_warm_transfer_task_kwargs(request, chat_ctx="chat")

        self.assertEqual(kwargs["sip_call_to"], "+15550002222")
        self.assertEqual(kwargs["sip_trunk_id"], "trunk-123")
        self.assertEqual(kwargs["sip_number"], "+15550001111")
        self.assertEqual(kwargs["chat_ctx"], "chat")
        self.assertIn("caller asked for a human", kwargs["extra_instructions"])
        self.assertIn("Preferred team: sales.", kwargs["extra_instructions"])

    def test_livekit_adapter_handoff_handler_returns_provider_neutral_result(self):
        adapter = LiveKitTelephonyAdapter(
            LiveKitSIPConfig(
                sip_trunk_id="trunk-123",
                default_human_endpoint="+15550002222",
            )
        )
        handler = adapter.handoff_handler(chat_ctx_provider=lambda request: {"summary": request.reason})

        result = handler(
            context=FakeRuntimeContext(),
            reason="escalate billing question",
            urgency="normal",
            preferred_team="support",
            endpoint=None,
            caller_id="+15550001111",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "livekit")
        self.assertEqual(result["mode"], "warm_transfer")
        self.assertEqual(result["invite_status"], "ready")
        self.assertEqual(result["endpoint"], "+15550002222")
        self.assertEqual(result["caller_id"], "+15550001111")
        task_kwargs = result["metadata"]["warm_transfer_task_kwargs"]
        self.assertEqual(task_kwargs["chat_ctx"], {"summary": "escalate billing question"})
        self.assertEqual(result["metadata"]["request_metadata"]["company_key"], "globifye")

    def test_livekit_adapter_requires_handoff_endpoint_and_trunk(self):
        no_endpoint = LiveKitTelephonyAdapter(LiveKitSIPConfig(sip_trunk_id="trunk-123"))
        no_trunk = LiveKitTelephonyAdapter(
            LiveKitSIPConfig(default_human_endpoint="+15550002222")
        )
        request = TelephonyHandoffRequest(reason="need a human")

        with self.assertRaisesRegex(TelephonyConfigError, "human endpoint"):
            no_endpoint.build_warm_transfer_task_kwargs(request)
        with self.assertRaisesRegex(TelephonyConfigError, "sip_trunk_id"):
            no_trunk.build_warm_transfer_task_kwargs(request)

    def test_legacy_asterisk_adapter_normalizes_existing_handler_result(self):
        calls = []

        def legacy_handler(**kwargs):
            calls.append(kwargs)
            return {
                "invite_status": "ringing",
                "channel_id": "asterisk-channel-1",
                "endpoint": "PJSIP/sales-endpoint",
                "caller_id": "Sales",
                "already_invited": False,
            }

        handler = LegacyAsteriskHandoffAdapter(legacy_handler).handoff_handler()
        result = handler(
            context=FakeRuntimeContext(),
            reason="caller requested sales",
            urgency="urgent",
            preferred_team="sales",
            endpoint=None,
            caller_id=None,
        )

        self.assertEqual(calls[0]["reason"], "caller requested sales")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "asterisk")
        self.assertEqual(result["mode"], "legacy_bridge")
        self.assertEqual(result["invite_status"], "ringing")
        self.assertEqual(result["participant_id"], "asterisk-channel-1")
        self.assertEqual(result["metadata"]["handoff_reason"], "caller requested sales")


if __name__ == "__main__":
    unittest.main()
