"""Read-only release handoff audit; writes only the requested report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_map(root: Path, mapping: dict[str, str]) -> list[dict]:
    return [
        {"path": path, "expected": expected, "actual": digest(root / path)}
        for path, expected in mapping.items()
        if digest(root / path) != expected
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    release = args.release.resolve()
    baseline = read(release / "baseline.json")
    source = Path(baseline["source_root"])
    terminals = {str(n): read(release / f"terminal-{n}/ready.json") for n in range(1, 5)}
    handoffs = terminals["4"]["handoffs"]
    terminal_records = []
    for n, ready in terminals.items():
        own = release / f"terminal-{n}"
        ready_sha = digest(own / "ready.json")
        expected_ready = handoffs.get(f"terminal-{n}", {}).get("ready_sha256")
        artifacts = []
        for entry in ready.get("artifacts", []):
            path = Path(entry["path"])
            actual = digest(path)
            artifacts.append({"path": str(path), "expected": entry["sha256"], "actual": actual, "matches": actual == entry["sha256"]})
        files = []
        for entry in ready.get("files", []):
            origin = Path(entry.get("draft_root", source)) / entry["path"]
            files.append({"path": entry["path"], "origin": str(origin), "expected": entry["sha256"], "actual": digest(origin), "integration_actual": digest(source / entry["path"])})
        terminal_records.append({
            "terminal": int(n), "status": ready["status"], "stopped_writing": ready.get("stopped_writing"),
            "ready_sha256": ready_sha, "received_by_terminal4_sha256": expected_ready,
            "terminal4_received_current_ready": expected_ready is None or expected_ready == ready_sha,
            "baseline_matches": ready.get("baseline_sha256") == digest(release / "baseline.json"),
            "artifacts": artifacts, "files": files,
            "source_hash_differences": check_map(source, ready.get("verified_source_files", {})),
        })
    pdfs = [{**entry, "actual_sha256": digest(Path(entry["path"]))} for entry in baseline["pdf_inputs"]]
    protected = [{"path": path, "expected": expected, "actual": digest(Path(path))} for path, expected in baseline["protected_evidence"].items()]
    snapshot = {path: digest(source / path) for path in baseline["reviewed_files"]}
    snapshot["docs/lightweight-pdf-quickstart.md"] = digest(source / "docs/lightweight-pdf-quickstart.md")
    snapshot_sha = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    report = {
        "source_root": str(source), "baseline_sha256": digest(release / "baseline.json"),
        "source_differences_from_857_baseline": check_map(source, baseline["source_files"]),
        "product_test_build_differences_from_413_baseline": check_map(source, baseline["product_and_test_files"]),
        "terminals": terminal_records, "original_pdfs": pdfs, "protected_evidence": protected,
        "current_18_file_review_scope": snapshot, "current_18_file_snapshot_sha256": snapshot_sha,
        "note": "This is a local review-scope snapshot, not the entire Git delivery manifest or a CI result.",
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(args.report), "source_differences": report["source_differences_from_857_baseline"],
        "handoff_mismatches": [r["terminal"] for r in terminal_records if not r["terminal4_received_current_ready"]],
        "artifact_mismatches": [{"terminal": r["terminal"], **a} for r in terminal_records for a in r["artifacts"] if not a["matches"]],
        "snapshot_sha256": snapshot_sha,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
