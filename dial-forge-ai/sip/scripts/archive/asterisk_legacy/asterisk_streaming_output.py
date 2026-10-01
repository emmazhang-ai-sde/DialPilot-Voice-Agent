from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable
from urllib.parse import urlsplit

from websockets.sync.server import serve

from asterisk_websocket_control import flush_media


@dataclass(frozen=True)
class AsteriskStreamingRouteConfig:
    static_websocket_url: str = ""
    asterisk_endpoint: str = ""
    incoming_base_url: str = ""
    media_server_host: str = ""
    media_server_port: int = 0
    media_server_path: str = "/dialforge-ai-output"
    transport_wait_timeout_ms: int = 3000
    app_name: str = "sip-mvp-app"


@dataclass(frozen=True)
class AsteriskStreamingSession:
    websocket_url: str
    output_channel_id: str | None = None
    bridge_id: str | None = None


class AsteriskAcceptedWebSocketTransport:
    """Small adapter around an accepted chan_websocket server connection."""

    def __init__(self, websocket):
        self._websocket = websocket

    def send(self, payload):
        self._websocket.send(payload)

    def send_binary(self, payload: bytes) -> None:
        self._websocket.send(payload)

    def send_text(self, payload: str) -> None:
        self._websocket.send(payload)

    def close(self) -> None:
        # A TTS utterance ending should not close the per-call Asterisk media
        # channel. The route manager owns the actual connection lifecycle.
        return

    def force_close(self) -> None:
        self._websocket.close()


class AsteriskStreamingTransportHub:
    """Accepts the Asterisk chan_websocket connection for the active call."""

    def __init__(self, *, host: str, port: int, path: str):
        self.host = host
        self.port = port
        self.path = _normalize_path(path)
        self._condition = threading.Condition()
        self._server = None
        self._thread: threading.Thread | None = None
        self._transport: AsteriskAcceptedWebSocketTransport | None = None
        self._expected_channel_id: str | None = None
        self._started = False
        self._start_error: BaseException | None = None

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._serve_forever,
                    name="asterisk-streaming-output-hub",
                    daemon=True,
                )
                self._thread.start()
            deadline = time.monotonic() + 2
            while not self._started and self._start_error is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            if self._start_error:
                raise RuntimeError(
                    f"failed to start Asterisk streaming output hub: {self._start_error}"
                ) from self._start_error
            if not self._started:
                raise RuntimeError("timed out starting Asterisk streaming output hub")

    def expect_session(self, channel_id: str) -> None:
        with self._condition:
            self._expected_channel_id = channel_id
            self._transport = None
            self._condition.notify_all()

    def wait_for_transport(
        self,
        *,
        channel_id: str | None = None,
        timeout_ms: int = 3000,
    ) -> AsteriskAcceptedWebSocketTransport:
        deadline = time.monotonic() + max(timeout_ms, 0) / 1000
        with self._condition:
            while self._transport is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        "timed out waiting for Asterisk streaming websocket connection"
                    )
                self._condition.wait(remaining)
            return self._transport

    def current_transport(self) -> AsteriskAcceptedWebSocketTransport | None:
        with self._condition:
            return self._transport

    def close_session(self, channel_id: str | None = None) -> None:
        with self._condition:
            transport = self._transport
            self._transport = None
            self._expected_channel_id = None
            self._condition.notify_all()
        if transport is not None:
            transport.force_close()

    def _serve_forever(self) -> None:
        try:
            with serve(
                self._handle_connection,
                self.host,
                self.port,
                subprotocols=["media"],
            ) as server:
                with self._condition:
                    self._server = server
                    self._started = True
                    self._condition.notify_all()
                server.serve_forever()
        except BaseException as exc:
            with self._condition:
                self._start_error = exc
                self._condition.notify_all()

    def _handle_connection(self, websocket) -> None:
        if not self._path_matches(websocket):
            websocket.close(1008, "unexpected media path")
            return
        transport = AsteriskAcceptedWebSocketTransport(websocket)
        with self._condition:
            self._transport = transport
            self._condition.notify_all()
        try:
            for _message in websocket:
                pass
        finally:
            with self._condition:
                if self._transport is transport:
                    self._transport = None
                    self._condition.notify_all()

    def _path_matches(self, websocket) -> bool:
        request = getattr(websocket, "request", None)
        raw_path = getattr(request, "path", None) or getattr(websocket, "path", None)
        if raw_path is None:
            return True
        return urlsplit(raw_path).path == self.path


class AsteriskStreamingOutputManager:
    def __init__(
        self,
        *,
        config: AsteriskStreamingRouteConfig,
        ari_post: Callable[..., dict | None],
        ari_delete: Callable[[str], None],
        transport_hub: AsteriskStreamingTransportHub | None = None,
    ):
        self.config = config
        self._ari_post = ari_post
        self._ari_delete = ari_delete
        self._transport_hub = transport_hub
        if (
            self._transport_hub is None
            and config.media_server_host
            and config.media_server_port
        ):
            self._transport_hub = AsteriskStreamingTransportHub(
                host=config.media_server_host,
                port=config.media_server_port,
                path=config.media_server_path,
            )
        self.session: AsteriskStreamingSession | None = None

    def start(self, *, bridge_id: str | None = None) -> AsteriskStreamingSession | None:
        if self.config.static_websocket_url:
            self.session = AsteriskStreamingSession(
                websocket_url=self.config.static_websocket_url,
                bridge_id=bridge_id,
            )
            return self.session

        if not (
            self.config.asterisk_endpoint
            and self.config.incoming_base_url
            and bridge_id
        ):
            return None
        if self._transport_hub is not None:
            self._transport_hub.start()

        channel = self._ari_post(
            "/channels",
            endpoint=self.config.asterisk_endpoint,
            app=self.config.app_name,
        )
        if not channel or not channel.get("id"):
            return None
        channel_id = channel["id"]
        self.session = AsteriskStreamingSession(
            websocket_url=f"{self.config.incoming_base_url.rstrip('/')}/{channel_id}",
            output_channel_id=channel_id,
            bridge_id=bridge_id,
        )
        if self._transport_hub is not None:
            self._transport_hub.expect_session(channel_id)
        self._ari_post(f"/bridges/{bridge_id}/addChannel", channel=channel_id)
        return self.session

    def stop(self) -> None:
        if self.session and self.session.output_channel_id:
            if self._transport_hub is not None:
                self._transport_hub.close_session(self.session.output_channel_id)
            self._ari_delete(f"/channels/{self.session.output_channel_id}")
        self.session = None

    def connect_transport(self, websocket_url: str):
        if (
            self.session is None
            or websocket_url != self.session.websocket_url
            or self._transport_hub is None
        ):
            raise RuntimeError("streaming websocket URL is not managed by this route")
        return self._transport_hub.wait_for_transport(
            channel_id=self.session.output_channel_id,
            timeout_ms=self.config.transport_wait_timeout_ms,
        )

    def owns_websocket_url(self, websocket_url: str) -> bool:
        return (
            self.session is not None
            and self._transport_hub is not None
            and websocket_url == self.session.websocket_url
        )

    def flush(self, transport) -> None:
        flush_media(transport)

    def flush_current(self) -> bool:
        if self._transport_hub is None:
            return False
        transport = self._transport_hub.current_transport()
        if transport is None:
            return False
        self.flush(transport)
        return True


def _normalize_path(path: str) -> str:
    path = path.strip()
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"
