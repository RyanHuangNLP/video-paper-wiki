from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "tests" / "fixtures" / "contracts"
VALID = FIXTURES / "valid"


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))
