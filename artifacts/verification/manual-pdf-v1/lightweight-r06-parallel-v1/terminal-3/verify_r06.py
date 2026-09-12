#!/usr/bin/env python3
"""Parameterized R06 verifier. Implementation under test is always an argument."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

SANA_SHA256 = "759588574b9b33bff83a6c8c05da1455535498c6cb70992678079242ddaeb23b"
MAIN_REPO = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
BUILD_BACKEND = MAIN_REPO / ".work" / "test-build-backend"
UV_CACHE = MAIN_REPO / ".work" / "cache" / "uv-tests"
SOURCE_HREF = re.compile(r"papers/[0-9a-f]{64}/source\.md#page-\d+")
PAGE_N = re.compile(r"page-(\d+)$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _env_for(*, python: Path, source_root: Path | None, installed_root: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["UV_OFFLINE"] = "1"
    env["UV_PYTHON_DOWNLOADS"] = "never"
    env["UV_CACHE_DIR"] = str(UV_CACHE)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if source_root is not None and installed_root is not None:
        raise SystemExit("use either --source-root or --installed-root, not both")
    if source_root is not None:
        env["PYTHONPATH"] = str((source_root / "src").resolve())
    elif installed_root is not None:
        env["PYTHONPATH"] = str(installed_root.resolve())
    else:
        raise SystemExit("provide --source-root or --installed-root (implementation must be an argument)")
    return env


def import_identity(*, python: Path, source_root: Path | None, installed_root: Path | None) -> dict[str, Any]:
    probe = r"""
import hashlib, json
from pathlib import Path
import video_paper_wiki_research.light_index as module
path = Path(module.__file__).resolve()
print(json.dumps({"module": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
"""
    env = _env_for(python=python, source_root=source_root, installed_root=installed_root)
    result = subprocess.run(
        [str(python), "-B", "-c", probe],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "python": str(python),
            "source_root": None if source_root is None else str(source_root.resolve()),
            "installed_root": None if installed_root is None else str(installed_root.resolve()),
        }
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    payload["ok"] = True
    payload["python"] = str(python)
    payload["source_root"] = None if source_root is None else str(source_root.resolve())
    payload["installed_root"] = None if installed_root is None else str(installed_root.resolve())
    payload["pythonpath"] = env.get("PYTHONPATH")
    return payload


def run_cli(
    *,
    python: Path,
    source_root: Path | None,
    installed_root: Path | None,
    argv: list[str],
) -> dict[str, Any]:
    env = _env_for(python=python, source_root=source_root, installed_root=installed_root)
    cmd = [str(python), "-B", "-m", "video_paper_wiki_research", *argv]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    stdout = result.stdout.strip()
    try:
        payload = json.loads(stdout.splitlines()[-1]) if stdout else {}
    except json.JSONDecodeError:
        payload = {"raw_stdout": result.stdout}
    return {
        "argv": cmd,
        "returncode": result.returncode,
        "payload": payload,
        "stderr": result.stderr[-4000:],
    }


def _knowledge_bytes(workspace: Path) -> dict[str, Any]:
    text_meta = 0
    index_bytes = 0
    copies: list[str] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(workspace).as_posix()
        suffix = path.suffix.lower()
        if suffix in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm"}:
            copies.append(rel)
        if rel.endswith("source.md") or rel.endswith("source.json"):
            text_meta += path.stat().st_size
        if rel.endswith(".light-index/index.v1.json") or rel.endswith("index.v1.json"):
            index_bytes += path.stat().st_size
    return {
        "text_metadata_bytes": text_meta,
        "index_bytes": index_bytes,
        "binary_copies": copies,
    }


def _parse_hrefs(markdown: str) -> list[str]:
    found = SOURCE_HREF.findall(markdown)
    return list(dict.fromkeys(found))


def _verify_links(markdown: str, workspace: Path, output_file: Path) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    errors: list[str] = []
    text = markdown
    for href in _parse_hrefs(text):
        relative, anchor = href.split("#", 1)
        source = (workspace / relative).resolve()
        ok = source.is_file()
        has_anchor = False
        if ok:
            body = source.read_text(encoding="utf-8")
            has_anchor = f'id="{anchor}"' in body
        checked.append({"href": href, "resolved": str(source), "exists": ok, "anchor": has_anchor})
        if not ok:
            errors.append(f"missing {source}")
        elif not has_anchor:
            errors.append(f"missing anchor {anchor} in {source}")
    written = output_file.read_text(encoding="utf-8") if output_file.is_file() else ""
    return {
        "checked": checked,
        "errors": errors,
        "returned_markdown_equals_written": written == markdown,
        "output_file": str(output_file),
        "output_parent_has_space": " " in str(output_file.parent),
    }


def _model_from_evidence(kind: str, context: dict[str, Any]) -> dict[str, Any]:
    evidence = context.get("evidence") or []
    if not evidence:
        raise SystemExit("export produced no evidence; cannot build a current-session model document")
    item = evidence[0]
    chunk = item["chunk_id"]
    snippet = str(item.get("text") or "").replace("\n", " ").strip()[:240]
    cite = {
        "chunk_id": chunk,
        "paper_id": item["paper_id"],
        "page": item["page"],
        "text_sha256": item["text_sha256"],
    }
    if kind == "qa":
        return {"text": f"Based on the supplied evidence: {snippet} [@{chunk}]", "citations": [cite]}
    return {"markdown": f"根据给定证据：{snippet}\n\n[@{chunk}]", "citations": [cite]}


def cli_flow(
    *,
    python: Path,
    source_root: Path | None,
    installed_root: Path | None,
    workspace: Path,
    output_dir: Path,
    pdf: Path,
    label: str,
) -> dict[str, Any]:
    identity = import_identity(python=python, source_root=source_root, installed_root=installed_root)
    pdf_sha = _sha256(pdf)
    add = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=["pdf", "add", "--pdf", str(pdf), "--workspace", str(workspace)],
    )
    build = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=["index", "build", "--workspace", str(workspace)],
    )
    question = "What method does this paper describe?"
    qa_export = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=["qa", "export", "--question", question, "--workspace", str(workspace)],
    )
    qa_context = qa_export["payload"]
    qa_answer = _model_from_evidence("qa", qa_context) if qa_context.get("ok") else None
    writing_export = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=[
            "writing",
            "export",
            "--topic",
            "paper overview",
            "--requirements",
            "two short paragraphs with citations",
            "--workspace",
            str(workspace),
        ],
    )
    writing_context = writing_export["payload"]
    writing_draft = _model_from_evidence("writing", writing_context) if writing_context.get("ok") else None
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_answer_path = output_dir / "qa-answer.json"
    writing_draft_path = output_dir / "writing-draft.json"
    qa_context_path = output_dir / "qa-context.json"
    writing_context_path = output_dir / "writing-context.json"
    _dump(qa_context_path, qa_context)
    _dump(writing_context_path, writing_context)
    qa_import = None
    writing_import = None
    qa_md = output_dir / "qa answer.md"
    writing_md = output_dir / "writing draft.md"
    if qa_answer is not None:
        _dump(qa_answer_path, qa_answer)
        qa_import = run_cli(
            python=python,
            source_root=source_root,
            installed_root=installed_root,
            argv=[
                "qa",
                "import",
                "--context",
                str(qa_context_path),
                "--answer",
                str(qa_answer_path),
                "--output",
                str(qa_md),
                "--workspace",
                str(workspace),
            ],
        )
    if writing_draft is not None:
        _dump(writing_draft_path, writing_draft)
        writing_import = run_cli(
            python=python,
            source_root=source_root,
            installed_root=installed_root,
            argv=[
                "writing",
                "import",
                "--context",
                str(writing_context_path),
                "--draft",
                str(writing_draft_path),
                "--output",
                str(writing_md),
                "--workspace",
                str(workspace),
            ],
        )
    sizes = _knowledge_bytes(workspace)
    qa_links = (
        _verify_links(str((qa_import or {}).get("payload", {}).get("markdown") or ""), workspace, qa_md)
        if qa_import
        else None
    )
    writing_links = (
        _verify_links(str((writing_import or {}).get("payload", {}).get("markdown") or ""), workspace, writing_md)
        if writing_import
        else None
    )
    page_count = (add.get("payload") or {}).get("page_count")
    return {
        "label": label,
        "identity": identity,
        "pdf": str(pdf),
        "pdf_sha256": pdf_sha,
        "pdf_digest_unchanged": pdf_sha == _sha256(pdf),
        "workspace": str(workspace),
        "output_dir": str(output_dir),
        "add": add,
        "index_build": build,
        "qa_export": {"returncode": qa_export["returncode"], "ok": qa_context.get("ok"), "status": qa_context.get("status")},
        "writing_export": {
            "returncode": writing_export["returncode"],
            "ok": writing_context.get("ok"),
            "status": writing_context.get("status"),
        },
        "qa_import": None
        if qa_import is None
        else {"returncode": qa_import["returncode"], "ok": qa_import["payload"].get("ok"), "path": qa_import["payload"].get("path")},
        "writing_import": None
        if writing_import is None
        else {
            "returncode": writing_import["returncode"],
            "ok": writing_import["payload"].get("ok"),
            "path": writing_import["payload"].get("path"),
        },
        "page_count": page_count,
        "sizes": sizes,
        "qa_links": qa_links,
        "writing_links": writing_links,
        "model_json": {
            "qa_answer": str(qa_answer_path) if qa_answer is not None else None,
            "writing_draft": str(writing_draft_path) if writing_draft is not None else None,
        },
    }


def legacy_restore(
    *,
    python: Path,
    source_root: Path | None,
    installed_root: Path | None,
    workspace: Path,
    fixture: Path,
) -> dict[str, Any]:
    identity = import_identity(python=python, source_root=source_root, installed_root=installed_root)
    provenance = json.loads((fixture / "provenance.json").read_text(encoding="utf-8"))
    mapping = provenance["materialize"]
    for name, relative in mapping.items():
        dest = workspace / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture / name, dest)
    before = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=["qa", "export", "--question", "quasar", "--workspace", str(workspace)],
    )
    rebuild = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=["index", "build", "--workspace", str(workspace)],
    )
    after_q = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=["qa", "export", "--question", "quasar", "--workspace", str(workspace)],
    )
    after_n = run_cli(
        python=python,
        source_root=source_root,
        installed_root=installed_root,
        argv=["qa", "export", "--question", "nebula", "--workspace", str(workspace)],
    )

    def _page(payload: dict[str, Any]) -> int | None:
        evidence = payload.get("evidence") or []
        if not evidence:
            return None
        return evidence[0].get("page")

    return {
        "identity": identity,
        "workspace": str(workspace),
        "copied_from": str(fixture),
        "before_quasar": {
            "ok": before["payload"].get("ok"),
            "status": before["payload"].get("status"),
            "page": _page(before["payload"]),
        },
        "rebuild": {"returncode": rebuild["returncode"], "ok": rebuild["payload"].get("ok"), "status": rebuild["payload"].get("status")},
        "after_quasar": {
            "ok": after_q["payload"].get("ok"),
            "status": after_q["payload"].get("status"),
            "page": _page(after_q["payload"]),
        },
        "after_nebula": {
            "ok": after_n["payload"].get("ok"),
            "status": after_n["payload"].get("status"),
            "page": _page(after_n["payload"]),
        },
        "required": provenance.get("required_fixed_observation"),
    }


def wheel_build(*, source_root: Path, installed_root: Path, dist_dir: Path) -> dict[str, Any]:
    if installed_root.resolve() == source_root.resolve() or source_root.resolve() in installed_root.resolve().parents:
        raise SystemExit("installed-root must be outside the source tree")
    if not BUILD_BACKEND.is_dir():
        raise SystemExit(f"missing lightweight build backend {BUILD_BACKEND}")
    dist_dir.mkdir(parents=True, exist_ok=True)
    installed_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BUILD_BACKEND)
    env["UV_OFFLINE"] = "1"
    env["UV_PYTHON_DOWNLOADS"] = "never"
    env["UV_CACHE_DIR"] = str(UV_CACHE)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    python = Path(sys.executable)
    build = subprocess.run(
        [str(python), "-B", "-m", "hatchling", "build", "-t", "wheel"],
        cwd=str(source_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    wheels = sorted((source_root / "dist").glob("*.whl")) if (source_root / "dist").is_dir() else []
    if not wheels:
        wheels = sorted(dist_dir.glob("*.whl"))
    copied = None
    if wheels:
        copied = dist_dir / wheels[-1].name
        shutil.copy2(wheels[-1], copied)
    install = None
    if copied is not None:
        target = installed_root / "site"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        with zipfile.ZipFile(copied) as archive:
            archive.extractall(target)
        install = {"target": str(target), "wheel": str(copied)}
    return {
        "build_returncode": build.returncode,
        "build_stdout": build.stdout[-4000:],
        "build_stderr": build.stderr[-4000:],
        "wheel": None if copied is None else str(copied),
        "install": install,
        "source_root": str(source_root.resolve()),
        "installed_root": str(installed_root.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--installed-root", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--pdf", type=Path, default=None)
    parser.add_argument("--legacy-fixture", type=Path, default=None)
    parser.add_argument("--dist-dir", type=Path, default=None)
    parser.add_argument("--step", required=True, choices=["identity", "cli-flow", "legacy-restore", "wheel-build"])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    python = args.python.expanduser()
    if not python.is_file():
        raise SystemExit(f"python is not a file: {python}")
    source_root = args.source_root.expanduser().resolve() if args.source_root else None
    installed_root = args.installed_root.expanduser().resolve() if args.installed_root else None
    if args.step == "identity":
        payload = import_identity(python=python, source_root=source_root, installed_root=installed_root)
        payload["label"] = args.label
        _dump(args.report, payload)
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0 if payload.get("ok") else 2
    if args.step == "cli-flow":
        if args.workspace is None or args.output_dir is None or args.pdf is None:
            raise SystemExit("cli-flow requires --workspace --output-dir --pdf")
        payload = cli_flow(
            python=python,
            source_root=source_root,
            installed_root=installed_root,
            workspace=args.workspace.expanduser().resolve(),
            output_dir=args.output_dir.expanduser(),
            pdf=args.pdf.expanduser().resolve(),
            label=args.label or "cli-flow",
        )
        _dump(args.report, payload)
        print(json.dumps({"ok": payload["identity"].get("ok"), "page_count": payload.get("page_count"), "label": payload["label"], "module": payload["identity"].get("module"), "sha256": payload["identity"].get("sha256")}, ensure_ascii=False), flush=True)
        return 0 if payload["identity"].get("ok") and payload["add"]["returncode"] == 0 else 2
    if args.step == "legacy-restore":
        if args.workspace is None or args.legacy_fixture is None:
            raise SystemExit("legacy-restore requires --workspace --legacy-fixture")
        payload = legacy_restore(
            python=python,
            source_root=source_root,
            installed_root=installed_root,
            workspace=args.workspace.expanduser().resolve(),
            fixture=args.legacy_fixture.expanduser().resolve(),
        )
        _dump(args.report, payload)
        print(json.dumps({"before": payload["before_quasar"], "after_quasar": payload["after_quasar"], "after_nebula": payload["after_nebula"], "sha256": payload["identity"].get("sha256")}, ensure_ascii=False), flush=True)
        return 0
    if args.step == "wheel-build":
        if source_root is None or installed_root is None or args.dist_dir is None:
            raise SystemExit("wheel-build requires --source-root --installed-root --dist-dir")
        payload = wheel_build(source_root=source_root, installed_root=installed_root, dist_dir=args.dist_dir.expanduser().resolve())
        _dump(args.report, payload)
        print(json.dumps({"wheel": payload.get("wheel"), "returncode": payload["build_returncode"]}, ensure_ascii=False), flush=True)
        return 0 if payload["build_returncode"] == 0 and payload.get("wheel") else 2
    raise SystemExit("unknown step")


if __name__ == "__main__":
    raise SystemExit(main())
