FLUSH_MEDIA = "FLUSH_MEDIA"


def send_text_control(transport, command: str) -> None:
    if hasattr(transport, "send_text"):
        transport.send_text(command)
        return
    transport.send(command)


def flush_media(transport) -> None:
    send_text_control(transport, FLUSH_MEDIA)
