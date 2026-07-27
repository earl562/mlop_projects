import socket

import pytest


def test_external_tcp_connection_is_blocked() -> None:
    # Given an address reserved for documentation rather than a local service.
    external_address = ("192.0.2.1", 443)

    # When the suite attempts an external connection, then it is rejected by policy.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.01)
        with pytest.raises(RuntimeError, match="External network access blocked in tests"):
            client.connect(external_address)


def test_loopback_tcp_connection_is_allowed() -> None:
    # Given a real listener bound only to loopback.
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener,
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client,
    ):
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        # When a client connects locally, then the connection succeeds.
        client.connect(listener.getsockname())
        accepted, _ = listener.accept()
        accepted.close()
