from __future__ import annotations

import socket
import urllib.request

import pytest


@pytest.fixture
def network_attempts(monkeypatch):
    attempts: list[str] = []

    def _fail(name: str):
        def _inner(*_args, **_kwargs):
            attempts.append(name)
            pytest.fail("network forbidden")

        return _inner

    monkeypatch.setattr(socket.socket, "connect", _fail("socket.socket.connect"))
    monkeypatch.setattr(socket, "create_connection", _fail("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", _fail("socket.getaddrinfo"))
    monkeypatch.setattr(urllib.request, "urlopen", _fail("urllib.request.urlopen"))
    return attempts
