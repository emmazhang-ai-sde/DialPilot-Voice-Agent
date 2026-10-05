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

from asterisk_streaming_output import (
    AsteriskStreamingOutputManager,
    AsteriskStreamingRouteConfig,
)


class AsteriskStreamingOutputManagerTest(unittest.TestCase):
    def test_disabled_route_returns_none(self):
        manager = AsteriskStreamingOutputManager(
            config=AsteriskStreamingRouteConfig(),
            ari_post=lambda path, **params: {"id": "channel-1"},
            ari_delete=lambda path: None,
        )

        self.assertIsNone(manager.start(bridge_id="bridge-1"))

    def test_static_websocket_url_session(self):
        manager = AsteriskStreamingOutputManager(
            config=AsteriskStreamingRouteConfig(
                static_websocket_url="ws://example.test/media"
            ),
            ari_post=lambda path, **params: {"id": "channel-1"},
            ari_delete=lambda path: None,
        )

        session = manager.start(bridge_id="bridge-1")

        self.assertEqual(session.websocket_url, "ws://example.test/media")
        self.assertIsNone(session.output_channel_id)

    def test_ari_created_channel_is_joined_and_cleaned_up(self):
        calls = []

        def ari_post(path, **params):
            calls.append((path, params))
            if path == "/channels":
                return {"id": "output-1"}
            return {}

        deleted = []
        manager = AsteriskStreamingOutputManager(
            config=AsteriskStreamingRouteConfig(
                asterisk_endpoint="WebSocket/streaming-output",
                incoming_base_url="ws://localhost:8790/media",
                app_name="sip-mvp-app",
            ),
            ari_post=ari_post,
            ari_delete=deleted.append,
        )

        session = manager.start(bridge_id="bridge-1")

        self.assertEqual(session.websocket_url, "ws://localhost:8790/media/output-1")
        self.assertEqual(
            calls,
            [
                (
                    "/channels",
                    {
                        "endpoint": "WebSocket/streaming-output",
                        "app": "sip-mvp-app",
                    },
                ),
                ("/bridges/bridge-1/addChannel", {"channel": "output-1"}),
            ],
        )

        manager.stop()

        self.assertEqual(deleted, ["/channels/output-1"])

    def test_ari_created_route_can_return_accepted_transport(self):
        class FakeHub:
            def __init__(self):
                self.started = False
                self.expected = []
                self.closed = []
                self.transport = FakeTransport()

            def start(self):
                self.started = True

            def expect_session(self, channel_id):
                self.expected.append(channel_id)

            def wait_for_transport(self, *, channel_id=None, timeout_ms=0):
                self.waited = (channel_id, timeout_ms)
                return self.transport

            def close_session(self, channel_id=None):
                self.closed.append(channel_id)

            def current_transport(self):
                return self.transport

        def ari_post(path, **params):
            if path == "/channels":
                return {"id": "output-1"}
            return {}

        deleted = []
        hub = FakeHub()
        manager = AsteriskStreamingOutputManager(
            config=AsteriskStreamingRouteConfig(
                asterisk_endpoint="WebSocket/streaming-output/c(slin24)",
                incoming_base_url="ws://localhost:8791/dialforge-ai-output",
                media_server_host="0.0.0.0",
                media_server_port=8791,
                media_server_path="/dialforge-ai-output",
                transport_wait_timeout_ms=1200,
            ),
            ari_post=ari_post,
            ari_delete=deleted.append,
            transport_hub=hub,
        )

        session = manager.start(bridge_id="bridge-1")

        self.assertTrue(hub.started)
        self.assertEqual(hub.expected, ["output-1"])
        self.assertTrue(manager.owns_websocket_url(session.websocket_url))
        self.assertIs(manager.connect_transport(session.websocket_url), hub.transport)
        self.assertEqual(hub.waited, ("output-1", 1200))
        self.assertTrue(manager.flush_current())
        self.assertEqual(hub.transport.text_payloads, ["FLUSH_MEDIA"])

        manager.stop()

        self.assertEqual(hub.closed, ["output-1"])
        self.assertEqual(deleted, ["/channels/output-1"])

    def test_flush_current_returns_false_without_transport(self):
        class FakeHub:
            def current_transport(self):
                return None

        manager = AsteriskStreamingOutputManager(
            config=AsteriskStreamingRouteConfig(),
            ari_post=lambda path, **params: {},
            ari_delete=lambda path: None,
            transport_hub=FakeHub(),
        )

        self.assertFalse(manager.flush_current())

class FakeTransport:
    def __init__(self):
        self.text_payloads = []

    def send_text(self, payload):
        self.text_payloads.append(payload)


if __name__ == "__main__":
    unittest.main()
