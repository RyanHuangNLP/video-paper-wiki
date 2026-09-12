#!/usr/bin/env python3
"""Terminal-3 release walkthrough helper. Does not patch product source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

MAIN_REPO = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
SOURCE_ROOT = Path("/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration")
INSTALLED_PY = Path(
    "/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration"
    "/.work/r06-wheel-prefix/venv/bin/python"
)
SOURCE_PY = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python")
CWD_OUTSIDE = Path("/private/tmp/vp.t3rel")
PDF = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/inbox/arxiv-2204.03458.pdf")
EXPECTED_PDF_SHA = "564428dc63dfe59725377fbcf0b108e1fcc3378b82f32c5b042ce861679da96f"
WS = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/"
    "lightweight-release-parallel-v1/terminal-3/.work/workspace"
)
OUT = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/"
    "manual-pdf-v1/lightweight-release-parallel-v1/terminal-3/import outputs"
)
EVIDENCE = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/"
    "manual-pdf-v1/lightweight-release-parallel-v1/terminal-3"
)
DRAFT = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/"
    "lightweight-release-parallel-v1/terminal-3/draft"
)
LEGACY_SRC = SOURCE_ROOT / "tests/research/fixtures/r06-legacy-workspace"
LEGACY_WS = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/"
    "lightweight-release-parallel-v1/terminal-3/.work/legacy-restore"
)
SCRATCH = Path("/var/folders/_q/bjgsg0bs7sd_2g1swc6mtdhc0000gn/T/grok-goal-c24a6a0758ce/implementer")
MODULES = ("cli", "light_index", "light_pdf", "light_qa", "light_writing")
MD_LINK = re.compile(r"\]\((?:<)?([^)>]+)(?:>)?\)")
TICK_LINK = re.compile(r"`([^`]*source\.md#page-\d+)`")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def installed_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = ""
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["UV_OFFLINE"] = "1"
    env["UV_PYTHON_DOWNLOADS"] = "never"
    env["UV_CACHE_DIR"] = str(MAIN_REPO / ".work/cache/uv-tests")
    return env


def source_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SOURCE_ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def run_cmd(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 180) -> dict[str, Any]:
    cwd.mkdir(parents=True, exist_ok=True)
    started = time.time()
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    rec: dict[str, Any] = {
        "cwd": str(cwd),
        "argv": argv,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration_s": round(time.time() - started, 3),
        "pythonpath": env.get("PYTHONPATH", ""),
        "isolated_flags": [flag for flag in argv if flag in ("-I", "-B", "-E", "-s")],
    }
    text = proc.stdout.strip()
    if text:
        try:
            rec["payload"] = json.loads(text)
        except json.JSONDecodeError:
            rec["payload"] = None
    else:
        rec["payload"] = None
    return rec


def probe_modules(python: Path, *, isolated: bool, env: dict[str, str], cwd: Path) -> dict[str, Any]:
    names = ", ".join(repr(name) for name in MODULES)
    code = f"""
import hashlib, json
from importlib import import_module
from pathlib import Path
out = {{}}
for name in [{names}]:
    mod = import_module("video_paper_wiki_research." + name)
    path = Path(mod.__file__)
    out[name] = {{"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
pkg = import_module("video_paper_wiki_research")
out["package"] = {{"file": str(Path(pkg.__file__)), "sha256": hashlib.sha256(Path(pkg.__file__).read_bytes()).hexdigest()}}
print(json.dumps(out))
"""
    argv = [str(python)]
    if isolated:
        argv.extend(["-I", "-B", "-c", code])
    else:
        argv.extend(["-B", "-c", code])
    rec = run_cmd(argv, cwd=cwd, env=env, timeout=30)
    return rec


def verify_hrefs(md_path: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    parent = md_path.parent
    found: list[str] = []
    for match in MD_LINK.finditer(text):
        href = match.group(1).strip()
        if "source.md" in href or "#page-" in href:
            found.append(href)
    for match in TICK_LINK.finditer(text):
        href = match.group(1).strip()
        if href not in found:
            found.append(href)
    errors: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    for href in found:
        path_part, sep, anchor = href.partition("#")
        target = Path(path_part)
        resolved = target if target.is_absolute() else (parent / path_part).resolve()
        item: dict[str, Any] = {
            "href": href,
            "resolved_from": str(parent),
            "resolved": str(resolved),
            "exists": resolved.is_file(),
            "anchor": anchor or None,
        }
        if not resolved.is_file():
            item["ok"] = False
            errors.append({**item, "error": "target_missing"})
            checked.append(item)
            continue
        body = resolved.read_text(encoding="utf-8")
        if anchor:
            needle = f'id="{anchor}"'
            item["anchor_present"] = needle in body
            if needle not in body:
                item["ok"] = False
                errors.append({**item, "error": "anchor_missing"})
                checked.append(item)
                continue
        item["ok"] = True
        checked.append(item)
    return {
        "markdown": str(md_path),
        "parent": str(parent),
        "href_count": len(found),
        "ok": not errors,
        "errors": errors,
        "checked": checked,
    }


def workspace_inventory(workspace: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    pdf_or_image = []
    text_meta = 0
    index_bytes = 0
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        rel = str(path.relative_to(workspace))
        files.append({"path": rel, "bytes": size, "sha256": sha256_file(path)})
        suffix = path.suffix.lower()
        if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}:
            pdf_or_image.append(rel)
        if path.name in {"source.md", "source.json"} or path.suffix in {".md", ".json"} and ".light-index" not in rel:
            if path.name != "index.v1.json":
                text_meta += size
        if path.name == "index.v1.json":
            index_bytes += size
    return {
        "workspace": str(workspace),
        "file_count": len(files),
        "files": files,
        "pdf_or_image_copies": pdf_or_image,
        "text_metadata_bytes": text_meta,
        "index_bytes": index_bytes,
        "text_metadata_under_1mib": text_meta < 1024 * 1024,
        "index_under_5mib": index_bytes < 5 * 1024 * 1024,
        "no_binary_copies": not pdf_or_image,
    }


def cmd_identity() -> None:
    CWD_OUTSIDE.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    help1 = run_cmd(
        [str(INSTALLED_PY), "-I", "-B", "-m", "video_paper_wiki_research", "--help"],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=30,
    )
    (SCRATCH / "installed-help.txt").write_text(help1["stdout"] + help1["stderr"], encoding="utf-8")
    (EVIDENCE / "installed-help.txt").write_text(help1["stdout"] + help1["stderr"], encoding="utf-8")
    modules = probe_modules(INSTALLED_PY, isolated=True, env=installed_env(), cwd=CWD_OUTSIDE)
    dump(EVIDENCE / "installed-modules.json", modules)
    dump(SCRATCH / "installed-modules.json", modules.get("payload") or modules)
    source_modules = probe_modules(SOURCE_PY, isolated=False, env=source_env(), cwd=CWD_OUTSIDE)
    dump(EVIDENCE / "source-import.json", source_modules)
    dump(SCRATCH / "source-import.json", source_modules.get("payload") or source_modules)
    dump(
        EVIDENCE / "installed-run.json",
        {
            "launch_1_help": {
                "cwd": help1["cwd"],
                "argv": help1["argv"],
                "exit_code": help1["exit_code"],
                "stdout_head": help1["stdout"][:1500],
                "stderr": help1["stderr"],
                "pythonpath": help1["pythonpath"],
            },
            "note": "launch_2 is the product command in walkthrough (pdf add) using the same interpreter flags",
        },
    )
    dump(SCRATCH / "installed-run.json", help1)
    print(json.dumps({"help_exit": help1["exit_code"], "modules_exit": modules["exit_code"], "source_exit": source_modules["exit_code"]}))


def cmd_ingest() -> None:
    if sha256_file(PDF) != EXPECTED_PDF_SHA:
        raise SystemExit(f"PDF sha mismatch: {sha256_file(PDF)}")
    if WS.exists():
        shutil.rmtree(WS)
    WS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    add = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "pdf",
            "add",
            "--pdf",
            str(PDF),
            "--workspace",
            str(WS),
            "--title",
            "Video Diffusion Models",
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=180,
    )
    dump(EVIDENCE / "walkthrough-add.json", add)
    build = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "index",
            "build",
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    dump(EVIDENCE / "walkthrough-index.json", build)
    print(json.dumps({"add_exit": add["exit_code"], "add_ok": (add.get("payload") or {}).get("ok"), "index_exit": build["exit_code"], "index_ok": (build.get("payload") or {}).get("ok")}))


def cmd_export() -> None:
    question = "What method does this paper propose?"
    qa = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "export",
            "--question",
            question,
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    (OUT / "qa-context.json").write_text(qa["stdout"], encoding="utf-8")
    dump(EVIDENCE / "walkthrough-qa-export.json", {k: v for k, v in qa.items() if k != "stdout"})
    zh = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "export",
            "--question",
            "这篇论文的方法是什么？",
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    dump(EVIDENCE / "walkthrough-qa-export-zh.json", {k: v for k, v in zh.items() if k != "stdout"})
    (EVIDENCE / "walkthrough-qa-export-zh-stdout.json").write_text(zh["stdout"] or "{}\n", encoding="utf-8")
    writing = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "writing",
            "export",
            "--topic",
            "video diffusion models",
            "--requirements",
            "Two short paragraphs citing original PDF file pages",
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    (OUT / "writing-context.json").write_text(writing["stdout"], encoding="utf-8")
    dump(EVIDENCE / "walkthrough-writing-export.json", {k: v for k, v in writing.items() if k != "stdout"})
    payload = qa.get("payload") or {}
    evidence = payload.get("evidence") or []
    print(
        json.dumps(
            {
                "qa_exit": qa["exit_code"],
                "qa_ok": payload.get("ok"),
                "qa_status": payload.get("status"),
                "qa_evidence": len(evidence),
                "zh_status": (zh.get("payload") or {}).get("status"),
                "writing_status": (writing.get("payload") or {}).get("status"),
                "writing_evidence": len((writing.get("payload") or {}).get("evidence") or []),
            }
        )
    )


def cmd_import() -> None:
    qa = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "import",
            "--context",
            str(OUT / "qa-context.json"),
            "--answer",
            str(OUT / "qa-answer.json"),
            "--output",
            str(OUT / "qa answer.md"),
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    dump(EVIDENCE / "walkthrough-qa-import.json", qa)
    writing = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "writing",
            "import",
            "--context",
            str(OUT / "writing-context.json"),
            "--draft",
            str(OUT / "writing-draft.json"),
            "--output",
            str(OUT / "writing draft.md"),
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    dump(EVIDENCE / "walkthrough-writing-import.json", writing)
    qa_href = verify_hrefs(OUT / "qa answer.md")
    w_href = verify_hrefs(OUT / "writing draft.md")
    dump(EVIDENCE / "href-check.json", {"qa": qa_href, "writing": w_href})
    dump(SCRATCH / "href-check.json", {"qa": qa_href, "writing": w_href})
    qa_md_disk = (OUT / "qa answer.md").read_text(encoding="utf-8")
    w_md_disk = (OUT / "writing draft.md").read_text(encoding="utf-8")
    qa_payload = qa.get("payload") or {}
    w_payload = writing.get("payload") or {}
    markdown_eq = {
        "qa_json_equals_disk": qa_payload.get("markdown") == qa_md_disk,
        "writing_json_equals_disk": w_payload.get("markdown") == w_md_disk,
        "qa_path": qa_payload.get("path"),
        "writing_path": w_payload.get("path"),
    }
    dump(EVIDENCE / "markdown-equals-disk.json", markdown_eq)
    print(
        json.dumps(
            {
                "qa_import_exit": qa["exit_code"],
                "qa_ok": qa_payload.get("ok"),
                "qa_status": qa_payload.get("status"),
                "writing_import_exit": writing["exit_code"],
                "writing_ok": w_payload.get("ok"),
                "qa_href_ok": qa_href["ok"],
                "writing_href_ok": w_href["ok"],
                "qa_href_count": qa_href["href_count"],
                "writing_href_count": w_href["href_count"],
                **markdown_eq,
            }
        )
    )


def cmd_stale() -> None:
    papers = list((WS / "papers").glob("*/source.md"))
    if len(papers) != 1:
        raise SystemExit(f"expected one source.md, found {papers}")
    source = papers[0]
    original = source.read_text(encoding="utf-8")
    source.write_text(original + "\n<!-- t3-release stale marker -->\n", encoding="utf-8")
    before = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "export",
            "--question",
            "What method does this paper propose?",
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    rebuild = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "index",
            "build",
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    after = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "export",
            "--question",
            "What method does this paper propose?",
            "--workspace",
            str(WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    rec = {
        "edited": str(source),
        "before": {k: v for k, v in before.items() if k != "stdout"},
        "rebuild": {k: v for k, v in rebuild.items() if k != "stdout"},
        "after": {k: v for k, v in after.items() if k != "stdout"},
        "before_status": (before.get("payload") or {}).get("status"),
        "after_status": (after.get("payload") or {}).get("status"),
        "after_ok": (after.get("payload") or {}).get("ok"),
    }
    dump(EVIDENCE / "walkthrough-stale.json", rec)
    print(json.dumps({"before": rec["before_status"], "after": rec["after_status"], "after_ok": rec["after_ok"]}))


def cmd_legacy() -> None:
    if LEGACY_WS.exists():
        shutil.rmtree(LEGACY_WS)
    paper_id = "670c70b59a0fa748f4a3c123458d4928e8813f6358ae1f4403f0a01cbaa3e3bb"
    paper_dir = LEGACY_WS / "papers" / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    (LEGACY_WS / ".light-index").mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_SRC / "source.md", paper_dir / "source.md")
    shutil.copy2(LEGACY_SRC / "source.json", paper_dir / "source.json")
    shutil.copy2(LEGACY_SRC / "index.v1.json", LEGACY_WS / ".light-index" / "index.v1.json")
    shutil.copy2(LEGACY_SRC / "provenance.json", LEGACY_WS / "provenance.json")
    before = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "export",
            "--question",
            "quasar",
            "--workspace",
            str(LEGACY_WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    rebuild = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "index",
            "build",
            "--workspace",
            str(LEGACY_WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    quasar = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "export",
            "--question",
            "quasar",
            "--workspace",
            str(LEGACY_WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )
    nebula = run_cmd(
        [
            str(INSTALLED_PY),
            "-I",
            "-B",
            "-m",
            "video_paper_wiki_research",
            "qa",
            "export",
            "--question",
            "nebula",
            "--workspace",
            str(LEGACY_WS),
        ],
        cwd=CWD_OUTSIDE,
        env=installed_env(),
        timeout=60,
    )

    def pages(rec: dict[str, Any]) -> list[Any]:
        return [item.get("page") for item in (rec.get("payload") or {}).get("evidence") or []]

    rec = {
        "legacy_src": str(LEGACY_SRC),
        "legacy_ws": str(LEGACY_WS),
        "copied_not_mutated_shared_fixture": True,
        "before_status": (before.get("payload") or {}).get("status"),
        "rebuild_ok": (rebuild.get("payload") or {}).get("ok"),
        "quasar_status": (quasar.get("payload") or {}).get("status"),
        "quasar_pages": pages(quasar),
        "nebula_status": (nebula.get("payload") or {}).get("status"),
        "nebula_pages": pages(nebula),
        "before": {k: v for k, v in before.items() if k != "stdout"},
        "rebuild": {k: v for k, v in rebuild.items() if k != "stdout"},
        "quasar": {k: v for k, v in quasar.items() if k != "stdout"},
        "nebula": {k: v for k, v in nebula.items() if k != "stdout"},
    }
    dump(EVIDENCE / "legacy-restore.json", rec)
    print(
        json.dumps(
            {
                "before": rec["before_status"],
                "quasar_pages": rec["quasar_pages"],
                "nebula_pages": rec["nebula_pages"],
            }
        )
    )


def cmd_inventory() -> None:
    inv = workspace_inventory(WS)
    dump(EVIDENCE / "workspace-inventory.json", inv)
    print(json.dumps({k: inv[k] for k in ("file_count", "text_metadata_bytes", "index_bytes", "no_binary_copies", "pdf_or_image_copies")}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["identity", "ingest", "export", "import", "stale", "legacy", "inventory"])
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    {"identity": cmd_identity, "ingest": cmd_ingest, "export": cmd_export, "import": cmd_import, "stale": cmd_stale, "legacy": cmd_legacy, "inventory": cmd_inventory}[args.step]()


if __name__ == "__main__":
    main()
