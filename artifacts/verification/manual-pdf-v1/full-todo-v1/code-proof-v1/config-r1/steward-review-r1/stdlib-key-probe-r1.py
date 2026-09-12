"""Read-only CONFIG stdlib-tree key-type probe for the frozen candidate."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[7]
CANDIDATE = ROOT / ".work/parallel/code-proof-v1/terminal-1/source"
OUT = Path(__file__).with_name("stdlib-key-probe-r1.json")
PRODUCTION = CANDIDATE / "src/video_paper_wiki/code_config_parser.py"

def digest(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def main() -> None:
    tracked = [
        CANDIDATE / "src/video_paper_wiki/code_config_parser.py",
        CANDIDATE / "tests/fixtures/code-config-vectors-v1.json",
        CANDIDATE / "tests/unit/test_code_config_parser.py",
    ]
    before = [digest(path) for path in tracked]
    head = subprocess.check_output(["git", "-C", str(CANDIDATE), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(CANDIDATE), "rev-parse", "HEAD^{tree}"], text=True).strip()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(CANDIDATE / "src"))
    import video_paper_wiki.code_config_parser as parser

    limits = dict(parser.CODE_CONFIG_PROFILE_LIMITS)

    class Key(str):
        pass

    subclass_key = Key("a")
    with patch("json.loads", return_value={subclass_key: True}):
        try:
            parser.parse_code_config_bytes(
                payload=b'{"a":true}', config_format="json", limits=limits
            )
        except parser.CodeConfigError as exc:
            subclass_result = {
                "outcome": "CODE_CONFIG_ERROR",
                "code": exc.code,
                "details": exc.details,
            }
        except BaseException as exc:  # pragma: no cover - evidence path
            subclass_result = {
                "outcome": "RAW_EXCEPTION",
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            }
        else:
            subclass_result = {"outcome": "ACCEPTED"}

    callbacks: list[str] = []
    armed = False

    class Trap(str):
        def __hash__(self):
            if armed:
                callbacks.append("hash")
                raise AssertionError("hash callback")
            return str.__hash__(self)

        def __eq__(self, other):
            if armed:
                callbacks.append("eq")
                raise AssertionError("eq callback")
            return str.__eq__(self, other)

        def __str__(self):
            if armed:
                callbacks.append("str")
                raise AssertionError("str callback")
            return str.__str__(self)

    trap = Trap("a")
    wrong_tree = {trap: True}
    armed = True
    try:
        with patch("json.loads", return_value=wrong_tree):
            try:
                parser.parse_code_config_bytes(
                    payload=b'{"a":true}', config_format="json", limits=dict(limits)
                )
            except parser.CodeConfigError as exc:
                trap_result = {
                    "outcome": "CODE_CONFIG_ERROR",
                    "code": exc.code,
                    "details": exc.details,
                }
            except BaseException as exc:  # pragma: no cover - evidence path
                trap_result = {
                    "outcome": "RAW_EXCEPTION",
                    "exception_type": type(exc).__name__,
                    "exception": str(exc),
                }
            else:
                trap_result = {"outcome": "ACCEPTED"}
    finally:
        armed = False

    after = [digest(path) for path in tracked]
    record = {
        "$schema": "video-paper-wiki.code-config-stdlib-key-probe-r1.v1",
        "revision": 1,
        "candidate_head": head,
        "candidate_tree": tree,
        "contract": {
            "path": "docs/ai/packets/full-todo-v1/CODE-CONFIG-KERNEL-R1.md",
            "sha256": "997ef4dce91e493f161b327ff5686aa349bd747e25ee13727248a68ba4d375d4",
            "requirement": "scanner-accepted stdlib mismatch, including unsupported stdlib types, is PARSER_MISMATCH",
            "lines": "148-156",
        },
        "production": digest(PRODUCTION),
        "probes": {
            "str_subclass_object_key": subclass_result,
            "str_subclass_callback": {**trap_result, "callbacks": callbacks},
        },
        "expected_contract_outcome": {
            "str_subclass_object_key": "CODE_CONFIG_PARSER_MISMATCH",
            "str_subclass_callback": "bounded CodeConfigError without invoking subclass callbacks",
        },
        "integrity": {"before": before, "after": after, "unchanged": before == after},
        "scope_controls": {
            "source_modified": False,
            "tests_modified": False,
            "fixture_modified": False,
            "git_mutation": False,
            "network_or_provider": False,
            "candidate_only_read_and_patched_stdlib_return": True,
        },
    }
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(), "bytes": OUT.stat().st_size}, indent=2))

if __name__ == "__main__":
    main()
