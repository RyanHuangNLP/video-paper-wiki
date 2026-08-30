from __future__ import annotations

from pathlib import Path

import pytest

from tests.support import make_checkout

__all__ = ["make_checkout"]


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    make_checkout(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path
