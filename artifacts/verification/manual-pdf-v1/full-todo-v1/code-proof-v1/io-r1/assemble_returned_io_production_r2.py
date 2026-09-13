"""Extract one complete returned production block into a review-only artifact."""
from pathlib import Path
import ast
import hashlib
import json
import re
import sys
from datetime import datetime, timezone


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: assemble_returned_io_production_r2.py RAW_STDOUT EMPTY_REVIEW_DIRECTORY")
    raw = Path(sys.argv[1]).absolute()
    target = Path(sys.argv[2]).absolute()
    data = raw.read_bytes()
    text = data.decode("utf-8", errors="strict")
    blocks = list(re.finditer(r"^```python\r?\n(.*?)^```[ \t]*\r?$", text, re.M | re.S))
    if len(blocks) != 1:
        raise SystemExit("Expected exactly one complete Python fenced block")
    rest = text
    for block in reversed(blocks):
        rest = rest[:block.start()] + rest[block.end():]
    if rest.strip() != "Tests not run.":
        raise SystemExit("Unexpected text outside the complete production block")
    names = ("code_proof_io.py",)
    payloads = [block.group(1).encode("utf-8") for block in blocks]
    for name, payload in zip(names, payloads):
        ast.parse(payload, filename=name)
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    outputs = []
    for name, payload in zip(names, payloads):
        path = target / name
        with path.open("xb") as stream:
            stream.write(payload)
        outputs.append(pin(path))
    report = {"schema": "full-todo.code-io-returned-production-extraction.v1", "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "raw_stdout": pin(raw), "assembler": pin(Path(__file__).absolute()), "outputs": outputs, "ast_parse_passed": True, "byte_transformations": [], "product_paths_written": False, "tests_run": False, "acceptance": False}
    result = target / "extraction.json"
    with result.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(pin(result)))


if __name__ == "__main__":
    main()
