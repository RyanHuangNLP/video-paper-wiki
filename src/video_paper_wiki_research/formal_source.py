"""Read a lightweight text snapshot and hand it to Markdown-native staging."""
from __future__ import annotations

import re
from pathlib import Path

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_source import (
    admit_markdown_source, bind_markdown_capture_result, inspect_markdown_capture,
    prepare_markdown_capture, stage_markdown_plan, validate_payload,
)
from video_paper_wiki.markdown_source_contracts import (
    APPROVAL, AUTHORITY, LIMITS, OBSERVATION, PIPELINE, PLAN, fail, sha, validate,
)
from video_paper_wiki.markdown_source_io import (
    checked_path, fixed_batch, json_bytes, markdown_slots, retain_files,
)
from video_paper_wiki.staging import resolve_checkout_root, validate_batch_id
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_index import _locate_pages, _page_intervals_match


def _source_paths(workspace_root: Path | str, paper_id: object) -> tuple[Path, Path, Path]:
    if type(paper_id) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", paper_id) is None:
        fail("MARKDOWN_SOURCE_INVALID", "select one canonical lightweight SHA-256 paper ID")
    workspace = checked_path(workspace_root)
    try:
        if not workspace.relative_to(resolve_checkout_root() / ".work").parts:
            raise ValueError
    except ValueError:
        fail("WORK_PATH_UNSAFE", "lightweight workspace must exist inside this checkout's .work")
    directory = workspace / "papers" / paper_id.split(":", 1)[1]
    return workspace, directory / "source.md", directory / "source.json"


def _observe(markdown: bytes, metadata: bytes, *, light_paper_id: str,
             paper_id: object, version_label: object) -> dict:
    meta = json_bytes(metadata, code="MARKDOWN_SOURCE_INVALID")
    try:
        text = markdown.decode("utf-8")
    except UnicodeError:
        fail("MARKDOWN_SOURCE_INVALID", "source.md must be valid UTF-8")
    if "\0" in text or not markdown:
        fail("MARKDOWN_SOURCE_INVALID", "source.md must be nonempty text without NUL")
    content_sha = light_paper_id.split(":", 1)[1]
    if type(meta) is not dict or meta.get("schema") != "video-paper-wiki.light-paper.v1" or meta.get("paper_id") != light_paper_id:
        fail("MARKDOWN_SOURCE_INVALID", "source.json does not bind this lightweight paper")
    document = meta.get("document")
    if type(document) is not dict or document.get("path") != f"papers/{content_sha}/source.md":
        fail("MARKDOWN_SOURCE_INVALID", "source.json does not bind the exact Markdown slot")
    page_count = meta.get("page_count")
    if type(page_count) is not int or not 1 <= page_count <= 300:
        fail("MARKDOWN_SOURCE_INVALID", "source.json page count is outside limits")
    try:
        pages = _locate_pages(text, page_count=page_count)
    except (ResearchError, ValueError):
        fail("MARKDOWN_SOURCE_INVALID", "source.md page anchors or headings are invalid")
    if document.get("sha256") != sha(markdown) or not _page_intervals_match(meta.get("pages"), pages):
        fail("MARKDOWN_SOURCE_STALE", "source metadata differs from live Markdown; refresh it before planning")
    source = meta.get("source")
    original_pdf = None
    if source is not None:
        if type(source) is not dict or source.get("sha256") != content_sha:
            fail("MARKDOWN_SOURCE_INVALID", "original source provenance differs from lightweight identity")
        original_pdf = content_sha
    title = meta.get("title")
    if type(title) is not str or not title.strip():
        title = light_paper_id
    observation = validate({"schema": OBSERVATION, "paper_id": paper_id, "light_paper_id": light_paper_id,
                            "title": title, "version": {"kind": "unknown" if version_label is None else "declared",
                                                           "label": version_label},
                            "markdown": {"sha256": sha(markdown), "size_bytes": len(markdown)},
                            "source_metadata_sha256": sha(metadata), "original_pdf_sha256": original_pdf,
                            "pages": [{key: value for key, value in page.items() if key != "text"} for page in pages]},
                           OBSERVATION)
    validate_payload(markdown, observation)
    return observation


def plan_markdown_source(*, workspace_root: Path | str, paper_id: object, batch_id: object,
                         canonical_paper_id: object = None, version_label: object = None) -> dict:
    workspace, markdown_path, metadata_path = _source_paths(workspace_root, paper_id)
    batch = validate_batch_id(batch_id)
    with retain_files([(markdown_path, LIMITS["max_markdown_bytes"], True),
                       (metadata_path, LIMITS["max_metadata_bytes"], True)]) as held:
        observation = _observe(held[0].data, held[1].data, light_paper_id=paper_id,
                               paper_id=paper_id if canonical_paper_id is None else canonical_paper_id,
                               version_label=version_label)
        plan = {"schema": PLAN, "batch_id": batch, "observation": observation,
                "workspace_root": str(workspace), "source_markdown_path": str(markdown_path.relative_to(workspace)),
                "source_metadata_path": str(metadata_path.relative_to(workspace)),
                "limits": dict(LIMITS), "pipeline": dict(PIPELINE)}
        with markdown_slots(batch, create=True) as slots:
            for item in held:
                item.verify()
            return stage_markdown_plan(plan, slots=slots)


def prepare_markdown_source(*, plan: Path | str, approval_ref: Path | str | None = None) -> dict:
    _path, batch = fixed_batch(plan, "plan.json")
    with markdown_slots(batch, create=False) as slots:
        raw = slots.read("plan.json")
        value = validate(json_bytes(raw, code="MARKDOWN_PLAN_INVALID"), PLAN)
        if canonicalize(value) != raw or value["batch_id"] != batch:
            fail("MARKDOWN_PLAN_INVALID", "plan is not canonical or batch-bound")
        slots.payload_slot(value["observation"]["markdown"]["sha256"])
        if approval_ref is None:
            fail("MARKDOWN_APPROVAL_REQUIRED", "supply an external Markdown approval reference")
        workspace, markdown_path, metadata_path = _source_paths(value["workspace_root"], value["observation"]["light_paper_id"])
        with retain_files([(markdown_path, LIMITS["max_markdown_bytes"], True),
                           (metadata_path, LIMITS["max_metadata_bytes"], True),
                           (approval_ref, 1048576, True)]) as held:
            observation = _observe(held[0].data, held[1].data,
                                   light_paper_id=value["observation"]["light_paper_id"],
                                   paper_id=value["observation"]["paper_id"],
                                   version_label=value["observation"]["version"]["label"])
            if observation != value["observation"]:
                fail("MARKDOWN_SOURCE_STALE", "source changed after planning")
            approval = validate(json_bytes(held[2].data, code="MARKDOWN_APPROVAL_MISMATCH"), APPROVAL)
            for item in held:
                item.verify()
            return prepare_markdown_capture(value, approval, held[0].data, slots=slots)


def _file_objects(paths):
    """Every CLI authority input stays retained until its dependent operation ends."""
    return retain_files([(path, 8388608, True) for path in paths])


def run_command(args) -> int:
    command = "formal-source." + args.formal_source_cmd
    try:
        if args.formal_source_cmd == "plan":
            result = plan_markdown_source(workspace_root=args.workspace_root, paper_id=args.paper_id,
                                           canonical_paper_id=args.canonical_paper_id, version_label=args.version_label,
                                           batch_id=args.batch_id)
        elif args.formal_source_cmd == "prepare":
            result = prepare_markdown_source(plan=args.plan, approval_ref=args.approval_ref)
        elif args.formal_source_cmd == "inspect":
            result = inspect_markdown_capture(prepared=args.prepared, operation_id=args.operation_id,
                                               upstream_root=args.upstream_root, vault_root=args.vault_root)
        elif args.formal_source_cmd == "bind-result":
            with _file_objects([args.authority, args.result, args.before, args.after]) as held:
                objects = [json_bytes(item.data, code="MARKDOWN_AUTHORITY_MISMATCH") for item in held]
                result = bind_markdown_capture_result(objects[0], objects[1], before=objects[2], after=objects[3])
        elif args.formal_source_cmd == "admit":
            paths = [args.authority] + ([args.capture_result] if args.capture_result else [])
            with _file_objects(paths) as held:
                objects = [json_bytes(item.data, code="MARKDOWN_AUTHORITY_MISMATCH") for item in held]
                result = admit_markdown_source(authority=objects[0], capture_result=objects[1] if len(objects) > 1 else None,
                                               batch_id=args.batch_id, operation_id=args.operation_id,
                                               vault_root=args.vault_root, upstream_root=args.upstream_root,
                                               ingested_at=args.ingested_at)
        else:
            fail("USAGE", "unknown formal-source operation")
        return emit_success(command, result)
    except Exception as exc:
        return emit_error(command, getattr(exc, "code", "MARKDOWN_SOURCE_INVALID"),
                          getattr(exc, "message", "Markdown source handoff failed"),
                          getattr(exc, "details", {}), exit_code=getattr(exc, "exit_code", 2))


def register_commands(subparsers) -> None:
    root = subparsers.add_parser("formal-source", allow_abbrev=False)
    commands = root.add_subparsers(dest="formal_source_cmd", required=True)
    plan = commands.add_parser("plan", allow_abbrev=False)
    for flag in ("workspace-root", "paper-id", "batch-id"):
        plan.add_argument("--" + flag, required=True)
    plan.add_argument("--canonical-paper-id")
    plan.add_argument("--version-label")
    prepare = commands.add_parser("prepare", allow_abbrev=False)
    prepare.add_argument("--plan", required=True)
    prepare.add_argument("--approval-ref")
    inspect = commands.add_parser("inspect", allow_abbrev=False)
    for flag in ("prepared", "operation-id", "upstream-root", "vault-root"):
        inspect.add_argument("--" + flag, required=True)
    bind = commands.add_parser("bind-result", allow_abbrev=False)
    for flag in ("authority", "result", "before", "after"):
        bind.add_argument("--" + flag, required=True)
    admit = commands.add_parser("admit", allow_abbrev=False)
    for flag in ("authority", "batch-id", "operation-id", "vault-root", "upstream-root", "ingested-at"):
        admit.add_argument("--" + flag, required=True)
    admit.add_argument("--capture-result")
    for parser in (plan, prepare, inspect, bind, admit):
        parser.set_defaults(handler=run_command)
