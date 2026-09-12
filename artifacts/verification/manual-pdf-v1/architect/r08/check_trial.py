"""Replay saved multi-paper exports using the delivered isolated wheel."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def inventory(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    terminal = args.terminal.resolve()
    workspace = Path(read(terminal / "outputs.json")["workspace"])
    before = inventory(workspace)
    pages = []
    failures = []
    for meta_path in sorted((workspace / "papers").glob("*/source.json")):
        meta = read(meta_path)
        md_path = meta_path.with_name("source.md")
        raw = md_path.read_bytes()
        text = raw.decode("utf-8")
        page_ok = meta["document"]["sha256"] == sha(raw)
        numbers = []
        for page in meta["pages"]:
            numbers.append(page["page"])
            segment = text[page["text_start"]:page["text_end"]]
            page_ok &= sha(segment.encode()) == page["text_sha256"]
            page_ok &= f'<a id="page-{page["page"]}"></a>' in text
        page_ok &= numbers == list(range(1, meta["page_count"] + 1))
        pages.append({"paper_id": meta["paper_id"], "page_count": meta["page_count"], "checks_passed": bool(page_ok)})
        if not page_ok:
            failures.append(f"page metadata: {meta_path}")
    exports = []
    evidence = {}
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(PYTHONDONTWRITEBYTECODE="1", UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never")
    for path in sorted((terminal / "exports").glob("*.json")):
        original = read(path)
        command = [str(args.python), "-I", "-B", "-m", "video_paper_wiki_research", original["kind"], "export", "--workspace", str(workspace)]
        if original["kind"] == "qa":
            command += ["--question", original["query"]]
        else:
            command += ["--topic", original["query"], "--requirements", original["requirements"]]
            for paper_id in original["paper_ids"]:
                command += ["--paper-id", paper_id]
        process = subprocess.run(command, cwd="/private/tmp", env=env, text=True, capture_output=True, timeout=30)
        current = json.loads(process.stdout)
        expected_exit = 0 if original["ok"] else 2
        matches = current == original and process.returncode == expected_exit
        slices_ok = True
        for item in current.get("evidence", []):
            md = (workspace / item["markdown_path"]).read_bytes()
            segment = md.decode("utf-8")[item["text_start"]:item["text_end"]]
            slices_ok &= sha(md) == item["markdown_sha256"]
            slices_ok &= segment == item["text"] and sha(segment.encode()) == item["text_sha256"]
            previous = evidence.get(item["chunk_id"])
            if previous is not None:
                identity_keys = ["paper_id", "page", "text", "text_sha256", "text_start", "text_end", "markdown_path", "markdown_sha256"]
                slices_ok &= all(previous[k] == item[k] for k in identity_keys)
            evidence[item["chunk_id"]] = item
        exports.append({"file": path.name, "command": command, "exit_code": process.returncode, "status": current["status"], "exact_payload_match": matches, "slices_verified": bool(slices_ok), "evidence_count": len(current.get("evidence", [])), "paper_ids": sorted({e["paper_id"] for e in current.get("evidence", [])})})
        if not matches or not slices_ok:
            failures.append(f"export: {path.name}")
    claims = []
    for claim in read(terminal / "claim-review.json")["claims"]:
        item = evidence.get(claim["chunk_id"])
        matches = item is not None and item["paper_id"] == claim["paper_id"] and item["page"] == claim["page"] and item["text"] == claim["source_slice"] and sha(claim["source_slice"].encode()) == claim["source_slice_sha256"]
        claims.append({"claim": claim["claim"], "chunk_id": claim["chunk_id"], "source_correspondence_matches": matches})
        if not matches:
            failures.append(f"claim source: {claim['chunk_id']}")
    answers = []
    for path in sorted((terminal / "answers").glob("*.json")):
        answer = read(path)
        text = answer.get("text", answer.get("markdown", ""))
        markers = set(re.findall(r"\[@([^\]]+)\]", text))
        listed = {entry["chunk_id"] for entry in answer["citations"]}
        valid = markers == listed and bool(markers) and markers <= evidence.keys()
        answers.append({"file": path.name, "citation_set_valid": valid, "paper_ids": sorted({evidence[c]["paper_id"] for c in markers if c in evidence}), "chinese_characters": len(re.findall(r"[\u4e00-\u9fff]", text))})
        if not valid:
            failures.append(f"answer citation set: {path.name}")
    after = inventory(workspace)
    report = {"workspace": str(workspace), "python": str(args.python), "pages": pages, "exports": exports, "claims": claims, "answers": answers, "workspace_unchanged": before == after, "failures": failures, "limits": "Read-only replay and source identity verification; no new model generation or independent human fact review."}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pages": sum(p["page_count"] for p in pages), "papers": len(pages), "exports": len(exports), "claims": len(claims), "workspace_unchanged": before == after, "failures": failures}, ensure_ascii=False))


if __name__ == "__main__":
    main()
