"""Deterministic Markdown projection from validated canonical domain objects."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

from video_paper_wiki.code_evidence_contracts import validate_code_evidence_manifest
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.domain import _frontmatter, _markdown, compile_concept_page
from video_paper_wiki.identity import claim_id, evidence_fingerprint, paper_page_slug, repo_page_slug
from video_paper_wiki.assessment_history import derive_assessment_heads
from video_paper_wiki.staging import stage_bytes, validate_batch_id
from video_paper_wiki.transaction_staging import encode_transaction_inspect_bundle
from video_paper_wiki.resources import read_projection_resource_bytes

SCHEMA = "video-paper-wiki.compile-input.v1"
_SECTIONS = (
    ("one_sentence_conclusion", "一句话结论"), ("research_question", "研究问题"),
    ("method", "方法"), ("representation_architecture", "表征与架构"),
    ("training_data", "训练与数据"), ("experiments_results", "实验与结果"),
    ("limitations", "局限"), ("code_resources", "代码与资源"),
    ("evidence_status", "证据状态"), ("related", "关联"),
)

def _fail(message: str) -> None:
    raise ContractError("COMPILE_INPUT_INVALID", message)

def _taxonomy_terms()->set[tuple[str,str]]:
    try:
        value=json.loads(read_projection_resource_bytes("taxonomy","v1.json").decode("utf-8"))
        return {(axis["slug"],term["slug"]) for axis in value["axes"] for term in axis["terms"]}
    except Exception as exc:
        raise ContractError("COMPILE_INPUT_INVALID","pinned taxonomy is unavailable") from exc

def concept_items_for_papers(records: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Derive the complete Concept compiler material from pinned taxonomy bytes."""
    try:
        taxonomy=json.loads(read_projection_resource_bytes("taxonomy","v1.json").decode("utf-8"))
        allowed={(axis["slug"],term["slug"]):{
            "axis":axis["slug"],"slug":term["slug"],"label_zh":term["label_zh"],
            "label_en":term.get("label_en",term["slug"]),
        } for axis in taxonomy["axes"] for term in axis["terms"]}
    except Exception as exc:
        raise ContractError("COMPILE_INPUT_INVALID","pinned taxonomy is unavailable") from exc
    selected=set()
    for raw in records:
        record=validate_document(raw,"video-paper-wiki.paper-record.v1")
        for item in record["taxonomy"]:
            key=(item["axis"],item["slug"])
            if key not in allowed:_fail("paper taxonomy term is not canonical")
            selected.add(key)
    return [allowed[key] for key in sorted(selected)]

def _claim(value: object, paper_id: str, refs: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], Mapping[str, Any]]:
    if type(value) is not dict or set(value) != {"claim_id", "stable_subject_id", "canonical_claim_text", "evidence", "assessment", "reviewed_at"}:
        _fail("claim shape differs")
    item = dict(value); cid = item["claim_id"]
    if type(cid) is not str or cid not in refs or item["stable_subject_id"] != "paper:" + paper_id:
        _fail("claim owner or reference differs")
    if claim_id(item["stable_subject_id"], item["canonical_claim_text"]) != cid:
        _fail("claim identity differs")
    if type(item["evidence"]) is not list or not item["evidence"]:
        _fail("claim evidence is empty")
    evidence_fingerprint(item["evidence"])
    return item, refs[cid]

def _paper(value: Mapping[str, Any]) -> tuple[str, bytes]:
    if not {"record","claims","events"}<=set(value)<={"record","claims","events","assessment_heads"}:
        _fail("paper compiler input differs")
    record = validate_document(value["record"], "video-paper-wiki.paper-record.v1")
    refs = {item["claim_id"]: item for item in record["section_claim_refs"]}
    if len(refs) != len(record["section_claim_refs"]): _fail("duplicate claim reference")
    claims: dict[str, tuple[dict[str, Any], Mapping[str, Any]]] = {}
    for raw in value["claims"]:
        claim, ref = _claim(raw, record["paper_id"], refs)
        if claim["claim_id"] in claims: _fail("duplicate claim")
        claims[claim["claim_id"]] = (claim, ref)
    if set(claims) != set(refs): _fail("paper claim set is incomplete")
    head_ids=derive_assessment_heads(claims=value["claims"],events=value["events"])
    if "assessment_heads" in value and value["assessment_heads"]!=head_ids:_fail("assessment head materialization differs")
    events={x["event_id"]:x for x in value["events"]}
    assessed: dict[str, str] = {}
    for cid, (claim, _ref) in claims.items():
        event = validate_document(events[head_ids[cid]], "video-paper-wiki.assessment-event.v1")
        if (event["claim_id"] != cid or event["claim_text_sha256"] != hashlib.sha256(claim["canonical_claim_text"].encode()).hexdigest()
                or event["evidence_fingerprint"] != evidence_fingerprint(claim["evidence"])):
            _fail("assessment head does not bind claim material")
        assessed[cid] = event["to_assessment"]
    if any((x["axis"],x["slug"]) not in _taxonomy_terms() for x in record["taxonomy"]):_fail("paper taxonomy term is not canonical")
    taxonomy = sorted({f"{x['axis']}/{x['slug']}" for x in record["taxonomy"]})
    title = record["title_zh"] or record["title"]
    fields=(("type","paper"),("paper_id",record["paper_id"]),("title",record["title"]),("title_zh",record["title_zh"]),
        ("authors",record["authors"]),("published_at",record["published_at"]),("arxiv_id",record.get("arxiv_id")),
        ("doi",record.get("doi")),("aliases",sorted(record["aliases"])),("source_ids",sorted(record["source_ids"])),
        ("claim_ids",sorted(claims)),("topics",taxonomy),("code_urls",sorted(record.get("code_urls",[]))),
        ("active_extraction_path",record["active_extraction_path"]),("active_extraction_sha256",record["active_extraction_sha256"]),
        ("created_at",record["created_at"]),("updated_at",record["updated_at"]),("status","generated"),
        ("created",record["created_at"][:10]),("updated",record["updated_at"][:10]),("tags",taxonomy or ["video-paper"]))
    fm="\n".join(["---"]+[f"{key}: {json.dumps(value,ensure_ascii=False,separators=(',',':'))}" for key,value in fields]+["---"])
    lines = [fm, "", "# " + _markdown(title), ""]
    for section, heading in _SECTIONS:
        lines += ["## " + heading, ""]
        rows = [(claim, ref) for claim, ref in claims.values() if ref["lifecycle"]=="active" and ref["section"] == section]
        if section=="one_sentence_conclusion":
            rows=[row for row in rows if row[1]["core"] and row[1]["lifecycle"]=="active" and assessed[row[0]["claim_id"]] in {"accepted","contested"}]
            if not 1<=len(rows)<=3:_fail("one-sentence conclusion requires one to three eligible active core claims")
        if section=="evidence_status":
            rows += [(claim,ref) for claim,ref in claims.values() if ref["lifecycle"]=="retired"]
        for claim, ref in sorted(rows, key=lambda x: x[0]["claim_id"]):
            state = assessed[claim["claim_id"]]
            if section == "one_sentence_conclusion" and ref["core"] and ref["lifecycle"] == "active" and state not in {"accepted", "contested"}:
                _fail("core conclusion is not eligible")
            lines.append(f"- {_markdown(claim['canonical_claim_text'])}  ^{claim['claim_id']}")
            lines.append(f"  - lifecycle: `{ref['lifecycle']}`; assessment: `{state}`")
        if section=="related": lines.append("- 暂无已发布的关联索引。")
        elif not rows: lines.append("- 暂无。")
        lines.append("")
    path = "wiki/papers/" + paper_page_slug(record["paper_id"]) + ".md"
    return path, unicodedata.normalize("NFC", "\n".join(lines).rstrip() + "\n").encode()

def _code(value: Mapping[str, Any]) -> tuple[str, bytes]:
    if set(value) != {"manifest", "repo_record", "alignment"}: _fail("code compiler input differs")
    manifest = validate_code_evidence_manifest(value["manifest"])
    repo = validate_document(value["repo_record"], "video-paper-wiki.repo-record.v1")
    alignment=validate_document(value["alignment"],"video-paper-wiki.paper-code-alignment.v1")
    origin = manifest["origin"]
    if (manifest["state"] != "inspected" or origin["repository"].casefold() != repo["canonical_repository"].casefold() or origin["commit"] != repo["canonical_commit"]
            or alignment["repository"].casefold()!=repo["canonical_repository"].casefold() or alignment["commit"]!=repo["canonical_commit"]
            or alignment["paper_id"] not in repo["paper_ids"] or alignment["officiality"]["status"]!=repo["officiality"] or alignment["license"]!=repo["license"]):
        _fail("code capture does not bind canonical repository")
    for capability in alignment["capabilities"]:
        for locator in capability["locators"]:
            if (locator["repository"].casefold()!=origin["repository"].casefold() or locator["commit"]!=origin["commit"]
                    or locator["source_id"]!=manifest["capture"]["source_id"]):_fail("capability locator does not bind inspected capture")
        if capability.get("absence_scope") is not None and capability["absence_scope"]["commit"]!=origin["commit"]:_fail("capability absence scope differs")
    title = f"{origin['repository']} · {origin['path']}"
    capabilities = sorted(alignment["capabilities"],key=lambda x:x["name"])
    body = _frontmatter(title=title, page_type="code", tags=["code", "video-paper"],
        extra=(("repo_id", repo["repo_id"]), ("repository", origin["repository"]), ("commit", origin["commit"]), ("source_path", origin["path"])), status="generated")
    body += "\n# " + _markdown(title) + "\n\n## 捕获证据\n\n"
    body += f"- manifest: `{manifest['manifest_sha256']}`\n- payload: `{manifest['payload']['sha256']}`\n\n## 能力矩阵\n\n"
    body += "\n".join(f"- {item['name']}: `{item['status']}`; evidence={len(item['locators'])}" for item in capabilities)
    body += "\n\n## 关联论文\n\n" + "\n".join(
        f"- [[../papers/{paper_page_slug(paper_id)}|{_markdown(paper_id)}]]"
        for paper_id in sorted(repo["paper_ids"]))
    path = "wiki/code/" + repo_page_slug(repo["repo_id"]) + ".md"
    return path, unicodedata.normalize("NFC", body.rstrip() + "\n").encode()

def compile_pages(material: object) -> dict[str, bytes]:
    doc = validate_document(material, SCHEMA)
    output: dict[str, bytes] = {}
    def add(path: str, data: bytes) -> None:
        normalized = unicodedata.normalize("NFC", path)
        if path != normalized or "\\" in path or any(p in {"", ".", ".."} for p in path.split("/")) or not path.startswith("wiki/") or not path.endswith(".md"):
            _fail("output path is not portable")
        folded = normalized.casefold()
        if any(existing.casefold() == folded or existing.startswith(normalized + "/") or normalized.startswith(existing + "/") for existing in output):
            _fail("output path collides")
        output[normalized] = data
    for item in doc["papers"]: add(*_paper(item))
    for item in doc["code"]: add(*_code(item))
    for item in doc["concepts"]:
        text = compile_concept_page(**item); add(f"wiki/concepts/{item['axis'].replace('/','-')}-{item['slug']}.md", text.encode())
    paper_paths=sorted(path for path in output if path.startswith("wiki/papers/"))
    concept_paths=sorted(path for path in output if path.startswith("wiki/concepts/"))
    if paper_paths:
        concept_links=[f"- [[../concepts/{path.rsplit('/',1)[-1][:-3]}|{path.rsplit('/',1)[-1][:-3]}]]" for path in concept_paths]
        code_links: dict[str,list[str]]={path:[] for path in paper_paths}
        for item in doc["code"]:
            code_name=repo_page_slug(item["repo_record"]["repo_id"])
            for paper_id in item["repo_record"]["paper_ids"]:
                paper_path="wiki/papers/"+paper_page_slug(paper_id)+".md"
                if paper_path in code_links:
                    code_links[paper_path].append(f"- [[../code/{code_name}|{_markdown(item['repo_record']['canonical_repository'])}]]")
        paper_links="\n".join(f"- [[../papers/{path.rsplit('/',1)[-1][:-3]}|{path.rsplit('/',1)[-1][:-3]}]]" for path in paper_paths)
        for path in paper_paths:
            related="\n".join(concept_links+sorted(code_links[path])) or "- 暂无已发布的关联索引。"
            text=output[path].decode("utf-8").replace("- 暂无已发布的关联索引。",related)
            output[path]=text.encode("utf-8")
        if concept_paths:
            for path in concept_paths:
                text=output[path].decode("utf-8").rstrip()+"\n\n## 关联\n\n"+paper_links+"\n"
                output[path]=text.encode("utf-8")
    return {path: output[path] for path in sorted(output)}

def stage_compilation(material: object, *, batch_id: object) -> dict[str, Any]:
    """Stage a preview-only generic bundle; it is not receipt-backed publication."""
    batch = validate_batch_id(batch_id); doc = validate_document(material, SCHEMA); pages = compile_pages(doc)
    writes = [{"path": p, "mode": "create", "sha256": hashlib.sha256(data).hexdigest()} for p, data in pages.items()]
    bundle = encode_transaction_inspect_bundle({"operation_id": doc["operation_id"], "operation_type": "generic", "writes": writes,
        "expected_hashes": {x["path"]: None for x in writes}, "read_preconditions": {}})
    for digest, data in sorted({hashlib.sha256(v).hexdigest(): v for v in pages.values()}.items()):
        stage_bytes(batch_id=batch, relative=("transaction-inspect", "content", digest), data=data)
    target = stage_bytes(batch_id=batch, relative=("transaction-inspect", "bundle.json"), data=bundle)
    return {"batch_id": batch, "publication_ready":False,"status":"preview-only","page_count": len(pages), "bundle_path": target.path.as_posix(), "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
            "pages": [{"path": p, "sha256": hashlib.sha256(v).hexdigest(), "size_bytes": len(v)} for p, v in pages.items()]}
