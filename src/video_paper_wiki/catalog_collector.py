"""Retained collector for the disposable search-catalog projection."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
import unicodedata
from pathlib import Path
from typing import Any

from video_paper_wiki.assessment_history import derive_assessment_heads
from video_paper_wiki.canonical_compiler import compile_pages, concept_items_for_papers
from video_paper_wiki.code_evidence_contracts import validate_code_evidence_manifest
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.evidence_join import build_evidence_inventory, join_evidence
from video_paper_wiki.identity import paper_page_slug, repo_id as canonical_repo_id
from video_paper_wiki.ledger_locator import decode_ledger_evidence, encode_ledger_locator
from video_paper_wiki.projection_input import _BRANCHES, validate_projection_bytes
from video_paper_wiki.projection_runtime import parse_projection_json, validate_runtime_record
from video_paper_wiki.receipt_audit import _Snapshot, _walk_inventory, audit_integrity
from video_paper_wiki.resources import read_projection_resource_bytes
from video_paper_wiki.secure_io import parse_strict_json

_DEP_NAMES=("attrs","jsonschema","jsonschema-specifications","referencing","rpds-py")


def _fail(message: str) -> None:
    raise ContractError("CATALOG_INPUT_INVALID", message)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _document(raw: bytes, title: str) -> dict[str, Any]:
    return validate_document(parse_strict_json(raw, invalid_code="CATALOG_INPUT_INVALID"), title)


def _kind(path: str) -> str | None:
    matches=[kind for kind,pattern in _BRANCHES.items() if pattern.fullmatch(path)]
    if len(matches)>1:_fail("canonical input path is ambiguous")
    return matches[0] if matches else None


def _row_tables() -> dict[str,list[dict[str,Any]]]:
    manifest=json.loads(read_projection_resource_bytes("catalog","base-catalog-v1.columns.json"))
    return {item["name"]:[] for item in manifest["tables"]}


def _add(rows: dict[str,list[dict[str,Any]]], table: str, **values: Any) -> None:
    rows[table].append(values)


def _taxonomy(rows:dict[str,list[dict[str,Any]]], raw:bytes)->None:
    doc=json.loads(raw);policy=doc["policy"];_add(rows,"taxonomy_meta",input_path="taxonomy/v1.json",version=doc["version"],
        unknown_terms=policy["unknown_terms"],silent_create=int(policy["silent_create"]),
        statement_en=policy["statement_en"],statement_zh=policy["statement_zh"])
    for ai,axis in enumerate(doc["axes"]):
        _add(rows,"taxonomy_axes",axis=axis["slug"],taxonomy_path="taxonomy/v1.json",ordinal=ai,label_zh=axis["label_zh"],label_en=axis["label_en"])
        for oi,alias in enumerate(axis.get("aliases",[])):_add(rows,"taxonomy_axis_aliases",axis=axis["slug"],ordinal=oi,alias=alias)
        for ti,term in enumerate(axis["terms"]):
            _add(rows,"taxonomy_terms",axis=axis["slug"],slug=term["slug"],ordinal=ti,label_zh=term["label_zh"],status=term["status"])
            for oi,alias in enumerate(term.get("aliases",[])):_add(rows,"taxonomy_term_aliases",axis=axis["slug"],slug=term["slug"],ordinal=oi,alias=alias)


def _ledgers(rows:dict[str,list[dict[str,Any]]], sources:dict, claims:dict)->None:
    _add(rows,"ledger_meta",ledger_kind="source",input_path="wiki/meta/ledgers/source-ledger.json",schema=sources["schema"],generated_at=sources["generated_at"])
    _add(rows,"ledger_meta",ledger_kind="claim",input_path="wiki/meta/ledgers/claim-ledger.json",schema=claims["schema"],generated_at=claims["generated_at"])
    for sid,item in sorted(sources["sources"].items()):
        origin=item["origin"]
        opt=lambda name:(int(item.get(name) is not None),item.get(name))
        cp,cv=opt("content_sha256");ip,iv=opt("ingested_at");rp,rv=opt("retrieved_at");fp,fv=opt("refresh_due");kp,kv=opt("independence_key");sp,sv=opt("supersedes")
        _add(rows,"sources",source_id=sid,ledger_kind="source",origin_kind=origin["kind"],origin_locator=origin["locator"],content_kind=item["content_kind"],title=item["title"],authority=item["authority"],review_status=item["review_status"],content_sha256_present=cp,content_sha256=cv,ingested_at_present=ip,ingested_at=iv,retrieved_at_present=rp,retrieved_at=rv,refresh_due_present=fp,refresh_due=fv,independence_key_present=kp,independence_key=kv,supersedes_present=sp,supersedes=sv)
        for ordinal,page in enumerate(item.get("pages",[])):_add(rows,"source_pages",source_id=sid,ordinal=ordinal,page_path=page)
        if origin["kind"]=="file":_add(rows,"source_artifacts",source_id=sid,artifact_path=origin["locator"])
    for cid,item in sorted(claims["claims"].items()):
        location=item["location"];notes=item.get("notes");sup=item.get("supersedes")
        _add(rows,"claims",claim_id=cid,ledger_kind="claim",text=item["text"],risk=item["risk"],assessment=item["assessment"],confidence=item["confidence"],location_path=location["path"],location_anchor_present=int(location.get("anchor") is not None),location_anchor=location.get("anchor"),reviewed_at=item.get("reviewed_at"),notes_present=int(notes is not None),notes=notes,supersedes_present=int(sup is not None),supersedes=sup)
        for ordinal,evidence in enumerate(item["evidence"]):
            decode_ledger_evidence(evidence)
            _add(rows,"claim_evidence",claim_id=cid,ordinal=ordinal,source_id=evidence["source_id"],wire_relation=evidence["relation"],locator_wire=evidence["locator"])


def _paper(rows:dict[str,list[dict[str,Any]]], path:str, doc:dict)->None:
    pid=doc["paper_id"]
    _add(rows,"papers",paper_id=pid,input_path=path,schema=doc["schema"],title=doc["title"],title_zh=doc["title_zh"],published_at=doc["published_at"],arxiv_id=doc.get("arxiv_id"),doi=doc.get("doi"),active_extraction_path=doc.get("active_extraction_path"),active_extraction_sha256=doc.get("active_extraction_sha256"),code_urls_present=int("code_urls" in doc),created_at=doc["created_at"],updated_at=doc["updated_at"])
    _add(rows,"subjects",subject_id="paper:"+pid,owner_kind="paper",paper_id=pid,repo_id=None)
    for table,key,col in (("paper_authors","authors","author"),("paper_aliases","aliases","alias"),("paper_sources","source_ids","source_id"),("paper_code_urls","code_urls","url")):
        for ordinal,value in enumerate(doc.get(key,[])):_add(rows,table,paper_id=pid,ordinal=ordinal,**{col:value})
    for ordinal,item in enumerate(doc["taxonomy"]):_add(rows,"paper_taxonomy",paper_id=pid,ordinal=ordinal,axis=item["axis"],slug=item["slug"])
    for ordinal,item in enumerate(doc["section_claim_refs"]):_add(rows,"claim_refs",claim_id=item["claim_id"],subject_id="paper:"+pid,ordinal=ordinal,section=item["section"],capability=None,core=int(item["core"]),lifecycle=item["lifecycle"])


def _repo(rows:dict[str,list[dict[str,Any]]], path:str, doc:dict)->None:
    rid=doc["repo_id"]
    _add(rows,"repos",repo_id=rid,input_path=path,schema=doc["schema"],canonical_repository=doc["canonical_repository"],canonical_commit=doc["canonical_commit"],officiality=doc["officiality"],license_spdx_id=doc["license"]["spdx_id"],license_notes=doc["license"]["notes"],archived=int(doc["archived"]) if "archived" in doc else None,created_at=doc["created_at"],updated_at=doc["updated_at"])
    _add(rows,"subjects",subject_id="repo:"+rid,owner_kind="repo",paper_id=None,repo_id=rid)
    for ordinal,pid in enumerate(doc["paper_ids"]):_add(rows,"repo_papers",repo_id=rid,ordinal=ordinal,paper_id=pid)
    for ordinal,item in enumerate(doc["capability_claim_refs"]):_add(rows,"claim_refs",claim_id=item["claim_id"],subject_id="repo:"+rid,ordinal=ordinal,section=None,capability=item["capability"],core=None,lifecycle=item["lifecycle"])


def _event(rows:dict[str,list[dict[str,Any]]],path:str,doc:dict)->None:
    _add(rows,"assessment_events",input_path=path,**doc)


def _code(rows:dict[str,list[dict[str,Any]]],path:str,doc:dict)->None:
    doc=validate_code_evidence_manifest(doc);origin=doc["origin"];payload=doc["payload"];capture=doc["capture"]
    rid=canonical_repo_id(origin["repository"])
    _add(rows,"code_manifests",input_path=path,schema=doc["schema"],state=doc["state"],repo_id=rid,repository=origin["repository"],commit=origin["commit"],origin_path=origin["path"],source_id=capture["source_id"],payload_sha256=payload["sha256"],payload_size_bytes=payload["size_bytes"],media_type=doc["media_type"],encoding=doc["encoding"],line_canonicalization=doc["line_canonicalization"],newline_style=doc["newline_style"],ends_with_newline=int(doc["ends_with_newline"]),line_count=doc["line_count"],normalized_sha256=doc["normalized_sha256"],proposal_sha256=doc["proposal_sha256"],stored_path=capture["stored_path"],source_identity=capture["source_identity"],inspection_approval_hash=capture["inspection_approval_hash"],operation_id=capture["operation_id"],manifest_sha256=doc["manifest_sha256"])
    _add(rows,"code_origins",repo_id=rid,commit=origin["commit"],origin_path=origin["path"],source_id=capture["source_id"])


def _run(rows:dict[str,list[dict[str,Any]]],path:str,doc:dict)->None:
    tools=doc["tool_versions"];inputs=doc["input_hashes"];outputs=doc["output_hashes"]
    def g(d,k):return d.get(k)
    _add(rows,"run_manifests",input_path=path,schema=doc["schema"],run_id=doc["run_id"],vpwiki_version=tools["vpwiki"],python_version=tools["python"],docling_version=g(tools,"docling"),docling_core_version=g(tools,"docling_core"),claude_obsidian_version=g(tools,"claude_obsidian"),input_ingest_plan_sha256=g(inputs,"ingest_plan_sha256"),input_prepared_sha256=g(inputs,"prepared_sha256"),input_source_sha256=g(inputs,"source_sha256"),input_parser_config_sha256=g(inputs,"parser_config_sha256"),input_model_manifest_sha256=g(inputs,"model_manifest_sha256"),output_document_json_sha256=g(outputs,"document_json_sha256"),output_draft_sha256=g(outputs,"draft_sha256"),output_receipt_sha256=g(outputs,"receipt_sha256"),started_at=doc["started_at"],ended_at=doc["ended_at"],error_code=doc["error_code"],pipeline_fingerprint=doc.get("pipeline_fingerprint"))
    source_sha=path.split('/')[2];fp=doc.get("pipeline_fingerprint")
    captured=[x["artifact_path"] for x in rows["artifacts"] if x["artifact_kind"]=="captured-artifact" and x["artifact_path"].startswith(f".raw/captured/{source_sha}.")]
    if len(captured)!=1:_fail("run source capture is missing or duplicated")
    _add(rows,"run_artifact_bindings",run_path=path,role="source",artifact_path=captured[0])
    if fp:
        base=f".raw/derived/{source_sha}/docling/{fp}/"
        for role,name in (("parser_config","parser-config.json"),("model_manifest","model-manifest.json"),("document","document.json")):_add(rows,"run_artifact_bindings",run_path=path,role=role,artifact_path=base+name)


def _alignment(rows:dict[str,list[dict[str,Any]]],path:str,doc:dict)->None:
    rid=canonical_repo_id(doc["repository"]);lic=doc["license"]
    _add(rows,"alignment_manifests",input_path=path,schema=doc["schema"],paper_id=doc["paper_id"],repo_id=rid,repository=doc["repository"],commit=doc["commit"],officiality=doc["officiality"]["status"],license_spdx_id=lic["spdx_id"],license_notes=lic["notes"],archived=int(doc["archived"]))
    for ordinal,loc in enumerate(doc["officiality"]["evidence"]):_add(rows,"alignment_officiality_evidence",alignment_path=path,ordinal=ordinal,source_id=loc["source_id"],locator_wire=encode_ledger_locator(loc))
    for ordinal,cap in enumerate(doc["capabilities"]):
        absence=cap.get("absence_scope")
        _add(rows,"alignment_capabilities",alignment_path=path,ordinal=ordinal,name=cap["name"],status=cap["status"],absence_scope_present=int(absence is not None),absence_commit=absence["commit"] if absence else None,absence_tree_prefix=absence["tree_prefix"] if absence else None,checkpoint_kind=cap.get("checkpoint_kind"))
        for oi,loc in enumerate(cap["locators"]):_add(rows,"alignment_capability_locators",alignment_path=path,capability_name=cap["name"],ordinal=oi,source_id=loc["source_id"],locator_wire=encode_ledger_locator(loc))
        for oi,pattern in enumerate(absence["search_patterns"] if absence else []):_add(rows,"alignment_absence_patterns",alignment_path=path,capability_name=cap["name"],ordinal=oi,pattern=pattern)


def _generation(inventory:dict,upstream:Path)->dict:
    profile=json.loads(read_projection_resource_bytes("catalog","base-catalog-v1.generation-profile.json"))
    src=Path(__file__).resolve().parent
    impl=[{"path":p,"sha256":_sha((src/p.removeprefix("video_paper_wiki/")).read_bytes())} for p in profile["implementation"]["files"]]
    resources=[]
    for p in profile["resources"]["files"]:
        logical=p.removeprefix("video_paper_wiki/");kind,name=logical.split('/',1);kind={"schemas":"schema"}.get(kind,kind)
        raw=read_projection_resource_bytes(kind,name)
        if raw is None:_fail("fixed generation resource is missing")
        resources.append({"path":p,"sha256":_sha(raw)})
    deps=[]
    for name in _DEP_NAMES + (("typing-extensions",) if sys.version_info[:2]==(3,12) else ()):
        deps.append({"name":name,"version":importlib.metadata.version(name)})
    ups=[{"path":p,"sha256":_sha((upstream/p).read_bytes())} for p in profile["upstream"]["files"]]
    return {"schema":"video-paper-wiki.projection-generation.v1","profile":"base-catalog-v1","inventory":inventory,
        "implementation":{"package_version":"0.1.0","files":impl},"resources":{"files":resources},
        "dependencies":{"profile":"vpwiki-jsonschema-date-utc-v1","distributions":deps},
        "upstream":{"commit":profile["upstream"]["commit"],"version":profile["upstream"]["version"],"files":ups},
        "runtime":{"python_implementation":platform.python_implementation(),"python_version":platform.python_version(),"unicode_version":unicodedata.unidata_version,"prefix_mode":"synthetic","chunk_profile":"claude-obsidian.chunk.v1","bm25_profile":"claude-obsidian.bm25.v2"}}


def collect_current_catalog_material(*,vault_root:Path|str,upstream_root:Path|str,retrieval_config:object,
                                     _retain:bool=False)->dict[str,Any]|tuple[dict[str,Any],_Snapshot]:
    """Collect all catalog authority from retained current bytes, never caller rows."""
    vault=Path(vault_root);upstream=Path(upstream_root);snap=_Snapshot(vault);success=False
    try:
        # Catalog authority begins at the canonical receipt head.  Reusing the
        # same retained snapshot binds head/chain/managed replay to every page,
        # chunk and row collected below.
        audit_integrity(vault,_snapshot=snap)
        actual=_walk_inventory(snap,read_bytes=True)
        from video_paper_wiki.source_state import require_legacy_profile
        require_legacy_profile({p: snap.files[p][1] for p in actual})
        tax=read_projection_resource_bytes("taxonomy","v1.json")
        if tax is None:_fail("taxonomy resource is unavailable")
        byte_map={p:snap.files[p][1] for p in sorted(actual) if _kind(p) is not None}
        byte_map["taxonomy/v1.json"]=tax
        entries=[{"path":p,"kind":_kind(p) or "taxonomy","sha256":_sha(raw),"size_bytes":len(raw)} for p,raw in sorted(byte_map.items())]
        inventory={"schema":"video-paper-wiki.projection-input.v1","entries":entries};validate_projection_bytes(inventory,bytes_map=byte_map)
        rows=_row_tables();_taxonomy(rows,tax)
        source=_document(byte_map["wiki/meta/ledgers/source-ledger.json"],"claude-obsidian.source-ledger.v1") if False else parse_strict_json(byte_map["wiki/meta/ledgers/source-ledger.json"],invalid_code="CATALOG_INPUT_INVALID")
        claim=parse_strict_json(byte_map["wiki/meta/ledgers/claim-ledger.json"],invalid_code="CATALOG_INPUT_INVALID");_ledgers(rows,source,claim)
        papers=[];events=[];codes=[];repos={};alignments=[]
        for entry in entries:
            p,k=entry["path"],entry["kind"]
            if k in {"paper-record","repo-record","assessment-event","run-manifest","code-evidence-manifest","alignment-manifest"}:
                title={"paper-record":"video-paper-wiki.paper-record.v1","repo-record":"video-paper-wiki.repo-record.v1","assessment-event":"video-paper-wiki.assessment-event.v1","run-manifest":"video-paper-wiki.run-manifest.v1","code-evidence-manifest":"video-paper-wiki.code-evidence-manifest.v1","alignment-manifest":"video-paper-wiki.paper-code-alignment.v1"}[k]
                doc=_document(byte_map[p],title)
                if k=="paper-record":_paper(rows,p,doc);papers.append(doc)
                elif k=="repo-record":_repo(rows,p,doc);repos[doc["repo_id"]]=doc
                elif k=="assessment-event":_event(rows,p,doc);events.append(doc)
                elif k=="code-evidence-manifest":_code(rows,p,doc);codes.append(doc)
                elif k=="alignment-manifest":_alignment(rows,p,doc);alignments.append(doc)
                else:_run(rows,p,doc)
            if k in {"captured-artifact","docling-document","parser-config","model-manifest"}:
                _add(rows,"artifacts",artifact_path=p,artifact_kind=k,file_sha256=entry["sha256"],size_bytes=entry["size_bytes"])
        for p in entries:
            _add(rows,"canonical_inputs",path=p["path"],kind=p["kind"],file_sha256=p["sha256"],size_bytes=p["size_bytes"])
        claims=[]
        refs={r["claim_id"]:r for r in rows["claim_refs"]}
        for cid,item in sorted(claim["claims"].items()):claims.append({"claim_id":cid,"stable_subject_id":refs[cid]["subject_id"],"canonical_claim_text":item["text"],"evidence":[decode_ledger_evidence(x) for x in item["evidence"]],"assessment":item["assessment"],"reviewed_at":item.get("reviewed_at")})
        heads=derive_assessment_heads(claims=claims,events=events)
        for cid,eid in sorted(heads.items()):_add(rows,"assessment_heads",claim_id=cid,head_event_id=eid)
        compile_papers=[]
        for paper in papers:
            owned=[x for x in claims if x["stable_subject_id"]=="paper:"+paper["paper_id"]]
            compile_papers.append({"record":paper,"claims":owned,"events":[e for e in events if e["claim_id"] in {x["claim_id"] for x in owned}]})
        compile_code=[]
        for manifest in codes:
            rid=canonical_repo_id(manifest["origin"]["repository"])
            for alignment in alignments:
                if canonical_repo_id(alignment["repository"])==rid and alignment["commit"]==manifest["origin"]["commit"]:compile_code.append({"manifest":manifest,"repo_record":repos[rid],"alignment":alignment})
        compiled=compile_pages({"schema":"video-paper-wiki.compile-input.v1","operation_id":"catalog-build","papers":compile_papers,"code":compile_code,"concepts":concept_items_for_papers(papers)})
        bm_path=".vault-meta/bm25/index.json";bm_raw=snap.read(bm_path);bm=parse_projection_json(bm_raw);validate_runtime_record("bm25",bm)
        chunks=[];pages_raw={};chunk_records={}
        for cid,doc in sorted(bm["docs"].items()):
            cp=doc["path"];raw=snap.read(cp);rec=parse_projection_json(raw);validate_runtime_record("chunk",rec)
            chunks.append({"path":cp,"bytes":raw,"record":rec});chunk_records[cid]=rec
            pages_raw.setdefault(rec["page_path"],snap.read(rec["page_path"]))
        inventory_authority=build_evidence_inventory(compile_papers)
        mapping=join_evidence(inventory=inventory_authority,pages=pages_raw,chunks=chunk_records,bm25=bm)
        indexed=[]
        paper_by_path={p:paper["paper_id"] for p,paper in (("wiki/papers/"+paper_page_slug(x["paper_id"])+".md",x) for x in papers)}
        for p,raw in sorted(pages_raw.items()):
            role="paper" if p.startswith("wiki/papers/") else "code" if p.startswith("wiki/code/") else "concept" if p.startswith("wiki/concepts/") else "other"
            rec=next(x for x in chunk_records.values() if x["page_path"]==p)
            indexed.append({"path":p,"role":role,"bytes":raw,"paper_id":paper_by_path.get(p),"page_address":rec["page_address"]})
        tables=[]
        manifest=json.loads(read_projection_resource_bytes("catalog","base-catalog-v1.columns.json"))
        for definition in manifest["tables"]:
            cols=[x["name"] for x in definition["columns"]];tables.append({"name":definition["name"],"columns":cols,"rows":[[row.get(c) for c in cols] for row in rows[definition["name"]]]})
        generation=_generation(inventory,upstream)
        builders=[{"path":"video_paper_wiki/catalog_collector.py","sha256":_sha(Path(__file__).read_bytes())},{"path":"video_paper_wiki/catalog_reporting.py","sha256":_sha(Path(__file__).with_name('catalog_reporting.py').read_bytes())},{"path":"video_paper_wiki/catalog_store.py","sha256":_sha(Path(__file__).with_name('catalog_store.py').read_bytes())}]
        snap.verify()
        result={"base_generation_material":generation,"base_tables":tables,"mapping":mapping,"config":retrieval_config,"indexed_pages":indexed,"compiled_pages":[{"path":p,"compiler_role":"paper" if p.startswith('wiki/papers/') else "code" if p.startswith('wiki/code/') else "concept","bytes":raw} for p,raw in compiled.items()],"chunks":chunks,"bm25":{"path":bm_path,"bytes":bm_raw,"record":bm},"builder_files":builders}
        success=True
        return (result,snap) if _retain else result
    finally:
        if not (_retain and success):
            try:snap.verify()
            finally:snap.close()
