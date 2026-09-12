from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--verifier",
        action="store",
        default=os.environ.get("VERIFY_LINKS_SCRIPT", ""),
        help="absolute path to the verify_links.py CLI script under test",
    )


@pytest.fixture
def verifier(request: pytest.FixtureRequest) -> Path:
    raw = request.config.getoption("--verifier") or os.environ.get("VERIFY_LINKS_SCRIPT") or ""
    if not raw:
        pytest.fail("select a verifier with --verifier /abs/verify_links.py or VERIFY_LINKS_SCRIPT")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        pytest.fail(f"verifier path must be absolute: {path}")
    if not path.is_file() or path.is_symlink():
        pytest.fail(f"verifier is not a regular file: {path}")
    return path.resolve()
