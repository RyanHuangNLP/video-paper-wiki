"""Staged source context and provisional knowledge proposal.

Internal helpers: `verify_pinned_source_id` (the only subprocess route),
ledger locator encode/decode, engine draft schema validation, claim identity,
and pipeline fingerprint. Outputs stay prospective.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_paper_wiki.contracts import ContractError, validate_document as validate_engine_document
from video_paper_wiki.identity import bind_claim_id, paper_subject_id, pipeline_fingerprint
from video_paper_wiki.ledger_locator import decode_ledger_locator
from video_paper_wiki.secure_io import SOURCE_CHANGED, SecureIOError, read_regular_file
from video_paper_wiki.upstream_adapter import verify_pinned_source_id

from video_paper_wiki_research.contracts import (
    BLOCK_LIMIT,
    DOCUMENT_JSON_MAX_BYTES,
    INTAKE_INVALID,
    LEGACY_DRAFT_SCHEMA,
    PARSER_OUTPUT_INVALID,
    PARSER_PROFILE_INVALID,
    PDF_MAX_BYTES,
    SECTION_SPECS,
    SOURCE_ANALYSIS_BINDING_MISMATCH,
    SOURCE_ANALYSIS_EMPTY,
    SOURCE_ANALYSIS_INVALID,
    SOURCE_CONTEXT_INVALID,
    TEXT_BUDGET,
    TRANSPORT_SCHEMA,
    ResearchError,
    dump_float_json,
    exact_ref,
    identity_component_ok,
    parse_float_json,
    saved_bytes,
    seal_document,
    sha256_bytes,
    task_prompt_bytes,
)
from video_paper_wiki_research.locator_truth import (
    as_ratio,
    block_id_for,
    charge_inventory,
    check_bbox,
    encode_block_locator,
    external_bbox,
    parse_supported_prov,
    pdf_page_geometry,
    ratio_eq,
    text_node,
    validate_export_profile,
)
from video_paper_wiki_research.manual_pdf import load_intake
from video_paper_wiki_research.parser_profile import load_profile
from video_paper_wiki_research.storage import (
    RetainedResearchSession,
    load_saved_document,
    session_from_research_path,
    stage_research,
    write_document,
)

RUN_FILES = {
    "document_json": "document.json",
    "parser_config": "parser-config.json",
    "model_manifest": "model-manifest.json",
    "run_manifest": "run.json",
}


def _read(path: Path, *, code: str, max_bytes: int) -> bytes:
    try:
        return read_regular_file(
            path,
            missing_code=code,
            unsafe_code=code,
            changed_code=SOURCE_CHANGED,
            max_bytes=max_bytes,
            limit_code=code,
        )
    except SecureIOError as exc:
        raise ResearchError(code, str(exc.message), dict(exc.details)) from exc


def load_run_bytes(run_dir: Path) -> dict[str, bytes]:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run path must be a directory")
    out: dict[str, bytes] = {}
    for kind, name in RUN_FILES.items():
        limit = DOCUMENT_JSON_MAX_BYTES if kind == "document_json" else 8 * 1024 * 1024
        out[kind] = _read(run_dir / name, code=SOURCE_CONTEXT_INVALID, max_bytes=limit)
    return out


def _artifact(session: RetainedResearchSession, run_id: str, kind: str, data: bytes) -> dict[str, Any]:
    name = RUN_FILES[kind]
    rel = session.posix("runs", run_id, name)
    return {"path": rel, "sha256": sha256_bytes(data), "size_bytes": len(data)}


def build_context(
    session: RetainedResearchSession,
    *,
    intake_path: Path,
    profile_path: Path,
    run_dir: Path,
    upstream_root: Path,
) -> dict[str, Any]:
    intake_session, intake, _intake_raw = load_intake(intake_path)
    if intake_session != session.session_id:
        raise ResearchError(INTAKE_INVALID, "intake does not belong to this session")
    profile_session = session_from_research_path(profile_path, kind_dir="profile")
    if profile_session != session.session_id:
        raise ResearchError(PARSER_PROFILE_INVALID, "profile does not belong to this session")
    profile, _profile_raw = load_profile(profile_path)
    run_session = session_from_research_path(run_dir / "run.json", kind_dir="runs")
    if run_session != session.session_id:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run does not belong to this session")
    run_id = run_dir.name
    blobs = load_run_bytes(run_dir)
    parser = profile["data"]["parser"]
    if sha256_bytes(blobs["parser_config"]) != parser["config_sha256"]:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run parser-config hash differs from profile")
    if sha256_bytes(blobs["model_manifest"]) != parser["model_manifest_sha256"]:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run model-manifest hash differs from profile")
    document_sha = sha256_bytes(blobs["document_json"])
    run_doc = parse_float_json(blobs["run_manifest"], invalid_code=SOURCE_CONTEXT_INVALID)
    try:
        run_doc = validate_engine_document(run_doc, expected_schema="video-paper-wiki.run-manifest.v1")
    except ContractError as exc:
        raise ResearchError(SOURCE_CONTEXT_INVALID, str(exc.message), dict(exc.details)) from exc
    if run_doc.get("error_code") is not None:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run manifest is not a successful export")
    if "receipt_sha256" in run_doc.get("output_hashes", {}):
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run manifest cannot create a receipt hash cycle")
    fingerprint = pipeline_fingerprint(parser)
    if run_doc.get("pipeline_fingerprint") != fingerprint:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run fingerprint differs from profile")
    if run_doc["input_hashes"].get("parser_config_sha256") != parser["config_sha256"]:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run parser-config hash differs")
    if run_doc["input_hashes"].get("model_manifest_sha256") != parser["model_manifest_sha256"]:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run model-manifest hash differs")
    if run_doc["output_hashes"].get("document_json_sha256") != document_sha:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run document hash differs")
    pdf_sha = str(intake["data"]["pdf_sha256"])
    if run_doc["input_hashes"].get("source_sha256") != pdf_sha:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "run source hash differs from intake")
    blob = session.checkout / ".work" / "blobs" / pdf_sha
    pdf = _read(blob, code=INTAKE_INVALID, max_bytes=PDF_MAX_BYTES)
    if sha256_bytes(pdf) != pdf_sha:
        raise ResearchError(INTAKE_INVALID, "intake blob digest differs")
    stored_path = f".raw/captured/{pdf_sha}.pdf"
    try:
        source_id = verify_pinned_source_id(stored_path, pdf_sha, upstream_root=upstream_root)
    except ContractError as exc:
        raise ResearchError(SOURCE_CONTEXT_INVALID, str(exc.message), dict(exc.details)) from exc
    document = parse_float_json(blobs["document_json"], invalid_code=PARSER_OUTPUT_INVALID)
    validate_export_profile(document)
    geometry = pdf_page_geometry(pdf, int(intake["data"]["page_count"]))
    pages = document["pages"]
    artifact_path = f".raw/derived/{pdf_sha}/docling/{fingerprint}/document.json"
    inventory = [0]
    omitted: list[dict[str, str]] = []
    eligible: list[dict[str, Any]] = []
    texts = document.get("texts") if type(document.get("texts")) is list else []
    seen_spans: dict[tuple[int, int, int], str] = {}
    for index, _node in enumerate(texts):
        charge_inventory(inventory)
        text, ref, prov = text_node(document, index)
        if not text:
            omitted.append({"ref": ref, "reason": "empty_text"})
            continue
        if not prov:
            omitted.append({"ref": ref, "reason": "unsupported_provenance"})
            continue
        parsed_items: list[dict[str, Any]] = []
        for item in prov:
            charge_inventory(inventory)
            parsed = parse_supported_prov(item, ref=ref)
            if parsed is None:
                omitted.append({"ref": ref, "reason": "unsupported_provenance"})
                continue
            parsed_items.append(parsed)
        parsed_items.sort(key=lambda item: (item["page_no"], item["charspan"][0], item["charspan"][1]))
        for parsed in parsed_items:
            page_no = parsed["page_no"]
            start, end = parsed["charspan"]
            if page_no not in geometry:
                raise ResearchError(SOURCE_CONTEXT_INVALID, "provenance page is not in the PDF")
            key = str(page_no)
            if key not in pages:
                raise ResearchError(SOURCE_CONTEXT_INVALID, "provenance page is missing from document.pages")
            page = pages[key]
            size = page["size"]
            page_geom = geometry[page_no]
            if not ratio_eq(as_ratio(size["width"]), page_geom["width"]) or not ratio_eq(
                as_ratio(size["height"]), page_geom["height"]
            ):
                raise ResearchError(SOURCE_CONTEXT_INVALID, "document page size differs from the PDF")
            if not 0 <= start < end <= len(text):
                raise ResearchError(SOURCE_CONTEXT_INVALID, "charspan is outside the node text")
            span_key = (page_no, start, end)
            for existing_page, existing_start, existing_end in seen_spans:
                if existing_page == page_no and not (end <= existing_start or start >= existing_end):
                    raise ResearchError(SOURCE_CONTEXT_INVALID, "overlapping provenance spans")
            seen_spans[span_key] = ref
            check_bbox(parsed["bbox"], page_geom["width"], page_geom["height"], page_geom["width_f"], page_geom["height_f"])
            slice_text = text[start:end]
            bbox = external_bbox(parsed["bbox"], page_geom["height"], page_geom["height_f"])
            wire = encode_block_locator(
                source_id=source_id,
                page=page_no,
                ref=ref,
                bbox=bbox,
                charspan=[start, end],
                artifact_path=artifact_path,
                artifact_sha256=document_sha,
                text=slice_text,
            )
            eligible.append({"ref": ref, "text": slice_text, "locator": wire, "page": page_no})
    for kind in ("tables", "pictures", "groups"):
        nodes = document.get(kind)
        if type(nodes) is not list:
            continue
        for index, _node in enumerate(nodes):
            charge_inventory(inventory)
            omitted.append({"ref": f"#/{kind}/{index}", "reason": "non_text_node"})
    blocks: list[dict[str, str]] = []
    text_used = 0
    stopped = False
    stop_reason = None
    for item in eligible:
        if stopped:
            omitted.append({"ref": item["ref"], "reason": stop_reason or "block_limit"})
            continue
        encoded = item["text"].encode("utf-8")
        block_over = len(blocks) >= BLOCK_LIMIT
        text_over = text_used + len(encoded) > TEXT_BUDGET
        if block_over or text_over:
            stopped = True
            stop_reason = "block_limit" if block_over else "text_budget"
            omitted.append({"ref": item["ref"], "reason": stop_reason})
            continue
        wire = item["locator"]
        blocks.append({"block_id": block_id_for(wire), "text": item["text"], "locator": wire})
        text_used += len(encoded)
    for item in omitted:
        charge_inventory(inventory)
    local_artifacts = {
        kind: _artifact(session, run_id, kind, blobs[kind]) for kind in RUN_FILES
    }
    data = {
        "intake": exact_ref(intake),
        "profile": exact_ref(profile),
        "local_artifacts": local_artifacts,
        "run_sha256": sha256_bytes(blobs["run_manifest"]),
        "paper_id": intake["data"]["paper_id"],
        "prospective_source_id": source_id,
        "pdf_sha256": pdf_sha,
        "prospective_document_path": artifact_path,
        "document_sha256": document_sha,
        "pipeline_fingerprint": fingerprint,
        "evidence_scope": "staged-pdf-text",
        "state": "staged_extraction",
        "capture_authorized": False,
        "receipt_backed": False,
        "published": False,
        "blocks": blocks,
        "omitted": omitted,
        "prompt_sha256": "0" * 64,
    }
    prompt = task_prompt_bytes(data)
    data["prompt_sha256"] = sha256_bytes(prompt)
    document = seal_document("context", data)
    staged, ref = write_document(session, "contexts", document)
    return {
        "context": document,
        "ref": ref,
        "path": staged.path.as_posix(),
        "prompt": prompt.decode("utf-8"),
        "prompt_sha256": data["prompt_sha256"],
        "already_staged": staged.already_staged,
        "next_action": "awaiting_model_proposal",
        "state": "staged_extraction",
        "capture_authorized": False,
        "receipt_backed": False,
        "published": False,
    }


def _legacy_draft(transport: dict[str, Any]) -> dict[str, Any]:
    claims = []
    for claim in transport["claims"]:
        locators = []
        for wire in claim["locators"]:
            locators.append(decode_ledger_locator(wire))
        item = dict(claim)
        item["locators"] = locators
        claims.append(item)
    draft = dict(transport)
    draft["schema"] = LEGACY_DRAFT_SCHEMA
    draft["claims"] = claims
    return draft


def render_markdown(*, title: str, pdf_sha256: str, transport: dict[str, Any], claims: list[dict[str, Any]]) -> str:
    lines = [
        f"# {title}",
        "",
        "Status: staged_analysis_proposal (provisional; not published; not receipt-backed)",
        f"PDF: {pdf_sha256}",
        "",
    ]
    heading = {section_id: heading_zh for section_id, heading_zh in SECTION_SPECS}
    grouped: dict[str, list[dict[str, Any]]] = {section_id: [] for section_id, _heading in SECTION_SPECS}
    for claim in claims:
        grouped[str(claim["section"])].append(claim)
    for section_id, heading_zh in SECTION_SPECS:
        lines.append(f"## {heading_zh}")
        section_claims = grouped[section_id]
        if not section_claims:
            lines.append("")
            continue
        for claim in section_claims:
            citations = []
            for wire in claim["locators"]:
                locator = decode_ledger_locator(wire)
                citations.append(f"page {locator['page']}, {locator['ref']}")
            lines.append(f"- `{claim['claim_id']}` {claim['claim_text']} ({'; '.join(citations)})")
        lines.append("")
    del heading, transport
    return "\n".join(lines).rstrip() + "\n"


def analyze_proposal(
    session: RetainedResearchSession,
    *,
    context_path: Path,
    proposal_path: Path,
    upstream_root: Path,
) -> dict[str, Any]:
    context_session = session_from_research_path(context_path, kind_dir="contexts")
    if context_session != session.session_id:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "context does not belong to this session")
    context, context_raw = load_saved_document(context_path, kind="context", invalid_code=SOURCE_CONTEXT_INVALID)
    data = context["data"]
    if sha256_bytes(context_raw) != exact_ref(context)["sha256"]:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "context bytes differ")
    raw = _read(proposal_path, code=SOURCE_ANALYSIS_INVALID, max_bytes=8 * 1024 * 1024)
    from video_paper_wiki_research.contracts import parse_envelope_json

    unsealed = parse_envelope_json(raw, invalid_code=SOURCE_ANALYSIS_INVALID)
    if type(unsealed) is not dict:
        raise ResearchError(SOURCE_ANALYSIS_INVALID, "proposal must be an object")
    required = {"context", "generator", "generated_at", "prompt_sha256", "transport_draft"}
    if set(unsealed) != required:
        raise ResearchError(SOURCE_ANALYSIS_INVALID, "unsealed proposal fields differ")
    if unsealed["context"] != exact_ref(context):
        raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "proposal context ref differs")
    generator = unsealed["generator"]
    if type(generator) is not dict or set(generator) != {"model", "runtime"}:
        raise ResearchError(SOURCE_ANALYSIS_INVALID, "generator must have model and runtime")
    if not identity_component_ok(generator["model"]) or not identity_component_ok(generator["runtime"]):
        raise ResearchError(SOURCE_ANALYSIS_INVALID, "generator identity is invalid")
    prompt = task_prompt_bytes(data)
    if unsealed["prompt_sha256"] != sha256_bytes(prompt) or unsealed["prompt_sha256"] != data["prompt_sha256"]:
        raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "prompt hash differs")
    pdf_sha = str(data["pdf_sha256"])
    stored_path = f".raw/captured/{pdf_sha}.pdf"
    try:
        source_id = verify_pinned_source_id(
            stored_path,
            pdf_sha,
            upstream_root=upstream_root,
            expected_source_id=str(data["prospective_source_id"]),
        )
    except ContractError as exc:
        raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, str(exc.message), dict(exc.details)) from exc
    if source_id != data["prospective_source_id"]:
        raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "prospective source ID differs")
    transport = unsealed["transport_draft"]
    if type(transport) is not dict or transport.get("schema") != TRANSPORT_SCHEMA:
        raise ResearchError(SOURCE_ANALYSIS_INVALID, "transport_draft schema differs")
    if transport.get("paper_id") != data["paper_id"]:
        raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "transport paper_id differs")
    claims = transport.get("claims")
    if type(claims) is not list or not claims:
        raise ResearchError(SOURCE_ANALYSIS_EMPTY, "proposal has no supportable claims")
    allowed = {block["locator"]: block for block in data["blocks"]}
    subject = paper_subject_id(str(data["paper_id"]))
    for claim in claims:
        if type(claim) is not dict:
            raise ResearchError(SOURCE_ANALYSIS_INVALID, "claim must be an object")
        if claim.get("assessment") != "provisional":
            raise ResearchError(SOURCE_ANALYSIS_INVALID, "claims must remain provisional")
        locators = claim.get("locators")
        if type(locators) is not list or not locators:
            raise ResearchError(SOURCE_ANALYSIS_INVALID, "each claim needs at least one locator")
        for wire in locators:
            if type(wire) is not str or wire not in allowed:
                raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "locator is not drawn from supplied blocks")
            locator = decode_ledger_locator(wire)
            if locator["source_id"] != data["prospective_source_id"]:
                raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "locator source_id is not prospective")
            if locator["artifact_path"] != data["prospective_document_path"]:
                raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "locator path is not prospective")
            if locator["artifact_sha256"] != data["document_sha256"]:
                raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "locator document hash differs")
            block = allowed[wire]
            if locator["ref"] != decode_ledger_locator(block["locator"])["ref"]:
                raise ResearchError(SOURCE_ANALYSIS_BINDING_MISMATCH, "locator ref differs")
        try:
            bind_claim_id(
                stated_claim_id=str(claim.get("claim_id")),
                subject=subject,
                canonical_claim_text=str(claim.get("claim_text")),
            )
        except Exception as exc:
            raise ResearchError(SOURCE_ANALYSIS_INVALID, "claim_id does not match identity material") from exc
    try:
        legacy = _legacy_draft(transport)
        validate_engine_document(legacy, expected_schema=LEGACY_DRAFT_SCHEMA)
    except ContractError as exc:
        raise ResearchError(SOURCE_ANALYSIS_INVALID, str(exc.message), dict(exc.details)) from exc
    except Exception as exc:
        raise ResearchError(SOURCE_ANALYSIS_INVALID, "legacy draft is invalid") from exc
    legacy_bytes = dump_float_json(legacy)
    sealed_data = {
        "context": exact_ref(context),
        "generator": generator,
        "generated_at": unsealed["generated_at"],
        "prompt_sha256": unsealed["prompt_sha256"],
        "transport_draft": transport,
        "legacy_draft_sha256": sha256_bytes(legacy_bytes),
        "state": "staged_analysis_proposal",
        "capture_authorized": False,
        "receipt_backed": False,
        "published": False,
    }
    document = seal_document("proposal", sealed_data)
    staged, ref = write_document(session, "proposals", document)
    digest = str(document["content_sha256"])
    draft_rel = ("proposals", f"{digest}.draft.json")
    md_rel = ("proposals", f"{digest}.md")
    markdown = render_markdown(
        title=str(transport["title"]),
        pdf_sha256=pdf_sha,
        transport=transport,
        claims=list(claims),
    )
    draft_staged = stage_research(session, draft_rel, legacy_bytes)
    md_staged = stage_research(session, md_rel, markdown.encode("utf-8"))
    if sha256_bytes(draft_staged.path.read_bytes()) != sealed_data["legacy_draft_sha256"]:
        raise ResearchError(SOURCE_ANALYSIS_INVALID, "legacy draft companion hash differs")
    return {
        "proposal": document,
        "ref": ref,
        "path": staged.path.as_posix(),
        "legacy_draft_path": draft_staged.path.as_posix(),
        "markdown_path": md_staged.path.as_posix(),
        "legacy_draft_sha256": sealed_data["legacy_draft_sha256"],
        "already_staged": staged.already_staged,
        "state": "staged_analysis_proposal",
        "capture_authorized": False,
        "receipt_backed": False,
        "published": False,
        "next_action": "human_review",
    }
