from __future__ import annotations

import socket
import urllib.request

import pytest


@pytest.fixture
def network_attempts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    def blocked(name: str):
        def fail(*args: object, **kwargs: object) -> None:
            attempts.append(name)
            pytest.fail(f"network attempt through {name}")

        return fail

    monkeypatch.setattr(socket.socket, "connect", blocked("socket.connect"))
    monkeypatch.setattr(socket, "create_connection", blocked("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", blocked("socket.getaddrinfo"))
    monkeypatch.setattr(urllib.request, "urlopen", blocked("urllib.request.urlopen"))
    return attempts
