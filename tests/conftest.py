"""Pytest configuration and global fixtures for offline testing."""

import socket
import pytest

_real_connect = socket.socket.connect


def _blocked_connect(self, address):
    host = address[0] if isinstance(address, tuple) and len(address) > 0 else str(address)
    # Allow local connections (ChromaDB memory/local server or internal loopbacks)
    if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return _real_connect(self, address)
    raise RuntimeError(
        f"Network access is blocked in offline unit tests! Attempted connection to non-loopback address: {address}"
    )


@pytest.fixture(autouse=True)
def block_external_network(request, monkeypatch):
    """Autouse fixture that blocks real network calls to non-loopback addresses."""
    if "network" in request.keywords:
        return
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
