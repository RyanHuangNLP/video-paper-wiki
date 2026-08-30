from __future__ import annotations

import os
import socket
import subprocess
import urllib.request

import pytest


@pytest.fixture
def network_attempts(monkeypatch):
    attempts: list[str] = []

    def _fail(name: str):
        def _inner(*_args, **_kwargs):
            attempts.append(name)
            pytest.fail(f"network forbidden: {name}")

        return _inner

    monkeypatch.setattr(socket.socket, "connect", _fail("socket.socket.connect"))
    monkeypatch.setattr(socket, "create_connection", _fail("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", _fail("socket.getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", _fail("socket.gethostbyname"))
    monkeypatch.setattr(urllib.request, "urlopen", _fail("urllib.request.urlopen"))
    monkeypatch.setattr(subprocess, "Popen", _fail("subprocess.Popen"))
    monkeypatch.setattr(subprocess, "run", _fail("subprocess.run"))
    monkeypatch.setattr(subprocess, "call", _fail("subprocess.call"))
    monkeypatch.setattr(subprocess, "check_call", _fail("subprocess.check_call"))
    monkeypatch.setattr(subprocess, "check_output", _fail("subprocess.check_output"))
    monkeypatch.setattr(os, "system", _fail("os.system"))
    return attempts
