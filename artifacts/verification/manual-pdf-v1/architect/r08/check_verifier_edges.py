"""Independent mixed-good/bad source-citation probes; no product mutations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix="vp.r08.edges.", dir="/private/tmp") as tmp:
        base = Path(tmp)
        workspace = base / "ws"
        source = workspace / "papers" / ("a" * 64) / "source.md"
        source.parent.mkdir(parents=True)
        source.write_text('<a id="page-1"></a>\n\n## PDF 第 1 页\n\nquasar\n', encoding="utf-8")
        output = base / "out" / "answer.md"
        output.parent.mkdir()
        good = f"../ws/papers/{'a' * 64}/source.md#page-1"
        missing = f"../missing/papers/{'a' * 64}/source.md"
        assert source.is_file()
        assert not (output.parent / missing).exists()
        assert 'id="page-2"' not in source.read_text()
        cases = [
            ("valid_only", f"[ok]({good})\n", True, None),
            ("missing_file_plain", f"[ok]({good})\n[bad]({missing}#page-1)\n", False, False),
            ("missing_file_query", f"[ok]({good})\n[bad]({missing}?x=1#page-1)\n", False, False),
            ("missing_file_markdown_title", f'[ok]({good})\n[bad]({missing}#page-1 "missing")\n', False, False),
            ("missing_anchor_unquoted_html", f'[ok]({good})\n<a href=../ws/papers/{"a" * 64}/source.md#page-2>bad</a>\n', False, False),
        ]
        for name, markdown, expected_ok, bad_target_exists in cases:
            output.write_text(markdown, encoding="utf-8")
            destination = base / f"{name}.json"
            command = [str(args.python), "-B", str(args.verifier), "--workspace", str(workspace), "--output", str(output), "--report", str(destination)]
            process = subprocess.run(command, cwd=base, text=True, capture_output=True, timeout=15)
            report = json.loads(destination.read_text()) if destination.exists() else None
            observed_ok = report is not None and report.get("ok") is True and process.returncode == 0
            results.append({"name": name, "markdown": markdown, "expected_ok": expected_ok, "bad_target_or_anchor_exists": bad_target_exists, "command": command, "exit_code": process.returncode, "report": report, "observed_ok": observed_ok, "expectation_matches": expected_ok == observed_ok})
    payload = {"verifier": str(args.verifier), "verifier_sha256": hashlib.sha256(args.verifier.read_bytes()).hexdigest(), "cases": results, "input_workspaces_cleaned": True}
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{key: row[key] for key in ("name", "expected_ok", "observed_ok", "exit_code", "expectation_matches")} for row in results]))


if __name__ == "__main__":
    main()
