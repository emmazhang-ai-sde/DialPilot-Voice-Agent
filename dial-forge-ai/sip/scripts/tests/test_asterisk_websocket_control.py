import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from asterisk_websocket_control import FLUSH_MEDIA, flush_media


class TextTransport:
    def __init__(self):
        self.sent_text = []

    def send_text(self, command):
        self.sent_text.append(command)


class SendTransport:
    def __init__(self):
        self.sent = []

    def send(self, command):
        self.sent.append(command)


class AsteriskWebSocketControlTest(unittest.TestCase):
    def test_flush_media_prefers_send_text(self):
        transport = TextTransport()

        flush_media(transport)

        self.assertEqual(transport.sent_text, [FLUSH_MEDIA])

    def test_flush_media_falls_back_to_send(self):
        transport = SendTransport()

        flush_media(transport)

        self.assertEqual(transport.sent, [FLUSH_MEDIA])


if __name__ == "__main__":
    unittest.main()
