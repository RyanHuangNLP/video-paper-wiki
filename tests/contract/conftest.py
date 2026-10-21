from __future__ import annotations

from pathlib import Path

import pytest

from .paths import SCHEMAS


@pytest.fixture(scope="session")
def schema_paths() -> list[Path]:
    return sorted(SCHEMAS.glob("*.schema.json"))
