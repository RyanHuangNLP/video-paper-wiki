"""Exact canonical-claim to pinned upstream chunk join; gold is never an input."""
from __future__ import annotations
import hashlib
import os,re,stat
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import evidence_fingerprint, locator_fingerprint, paper_page_slug
from video_paper_wiki.assessment_history import derive_assessment_heads
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.projection_runtime import parse_projection_json,runtime_projection_sha256,validate_runtime_record
from video_paper_wiki.secure_io import close_fd,dir_open_flags,open_dir_nofollow,read_child_regular,stamp

def _fail(message: str) -> None: raise ContractError("EVIDENCE_JOIN_INVALID", message)

def build_evidence_inventory(papers: object) -> dict[str, Any]:
    if type(papers) is not list: _fail("papers must be a list")
    units=[]; seen=set()
    for item in papers:
        if type(item) is not dict or not {"record","claims","events"}<=set(item)<={"record","claims","events","assessment_heads"}: _fail("paper inventory input differs")
        record=validate_document(item["record"],"video-paper-wiki.paper-record.v1")
        refs={x["claim_id"]:x for x in record["section_claim_refs"]}
        if len(refs)!=len(record["section_claim_refs"]):_fail("paper claim references are duplicated")
        heads=derive_assessment_heads(claims=item["claims"],events=item["events"])
        if "assessment_heads" in item and item["assessment_heads"]!=heads:_fail("assessment head materialization differs")
        events={x["event_id"]:x for x in item["events"]}
        for claim in item["claims"]:
            if type(claim) is not dict or set(claim)!={"claim_id","stable_subject_id","canonical_claim_text","evidence","assessment","reviewed_at"}: _fail("claim shape differs")
            cid=claim["claim_id"]; ref=refs.get(cid); event=validate_document(events.get(heads.get(cid)),"video-paper-wiki.assessment-event.v1")
            if ref is None or claim["stable_subject_id"]!="paper:"+record["paper_id"] or event["claim_id"]!=cid:
                _fail("claim owner or assessment differs")
            if (event["evidence_fingerprint"]!=evidence_fingerprint(claim["evidence"])
                    or event["claim_text_sha256"]!=hashlib.sha256(claim["canonical_claim_text"].encode()).hexdigest()
                    or event["to_assessment"]!=claim["assessment"]
                    or event["decided_at"][:10]!=claim["reviewed_at"]): _fail("stale assessment materialization")
            for locator in claim["evidence"]:
                fingerprint=locator_fingerprint(locator)
                unit_id="evu-"+hashlib.sha256(canonicalize({"paper_id":record["paper_id"],"claim_id":cid,"locator_fingerprint":fingerprint})).hexdigest()[:20]
                if unit_id in seen:_fail("duplicate evidence unit")
                seen.add(unit_id);units.append({"evidence_unit_id":unit_id,"paper_id":record["paper_id"],"claim_id":cid,"locator_fingerprint":fingerprint,"locator":locator,"core":ref["core"],
                    "lifecycle":ref["lifecycle"],"assessment":event["to_assessment"],"default_eligible":ref["lifecycle"]=="active" and event["to_assessment"]!="deprecated",
                    "gold_eligible":ref["lifecycle"]=="active" and ref["core"] and event["to_assessment"] in {"accepted","contested"}})
    return validate_document({"schema":"video-paper-wiki.evidence-inventory.v1","units":sorted(units,key=lambda x:x["evidence_unit_id"])},"video-paper-wiki.evidence-inventory.v1")

def validate_evidence_inventory(value:object)->dict[str,Any]:
    """Validate and recompute every materialized evidence-unit identity."""
    inv=validate_document(value,"video-paper-wiki.evidence-inventory.v1"); seen=set()
    for unit in inv["units"]:
        fingerprint=locator_fingerprint(unit["locator"])
        expected="evu-"+hashlib.sha256(canonicalize({"paper_id":unit["paper_id"],"claim_id":unit["claim_id"],"locator_fingerprint":fingerprint})).hexdigest()[:20]
        default=unit["lifecycle"]=="active" and unit["assessment"]!="deprecated"
        gold=unit["lifecycle"]=="active" and unit["core"] and unit["assessment"] in {"accepted","contested"}
        if unit["locator_fingerprint"]!=fingerprint or unit["evidence_unit_id"]!=expected or unit["default_eligible"]!=default or unit["gold_eligible"]!=gold or expected in seen:_fail("inventory derived identity differs")
        seen.add(expected)
    return inv

def evidence_mapping_sha256(value:object)->str:
    if type(value) is not dict or set(value)!={"schema","profile","generation_sha256","inventory","chunks","mapping_sha256"}:_fail("mapping authority shape differs")
    return hashlib.sha256(canonicalize({key:item for key,item in value.items() if key!="mapping_sha256"})).hexdigest()

def validate_evidence_mapping_authority(value:object)->dict[str,Any]:
    mapping=validate_document(value,"video-paper-wiki.evidence-mapping-authority.v1")
    validate_evidence_inventory(mapping["inventory"])
    if mapping["mapping_sha256"]!=evidence_mapping_sha256(mapping):_fail("mapping authority digest differs")
    return mapping

def join_evidence(*, inventory: object, pages: Mapping[str,bytes], chunks: Mapping[str,object], bm25: object) -> dict[str,Any]:
    inv=validate_evidence_inventory(inventory)
    if not isinstance(pages,Mapping) or not isinstance(chunks,Mapping):_fail("byte maps are required")
    index=validate_runtime_record("bm25",bm25); docs=index.get("docs")
    if type(docs) is not dict or set(docs)!=set(chunks):_fail("BM25 and chunk sets differ")
    units_by_page:dict[str,list[dict]]={}
    for unit in inv["units"]: units_by_page.setdefault("wiki/papers/"+paper_page_slug(unit["paper_id"])+".md",[]).append(unit)
    joined=[]; mapped=set(); page_seen=set(); expected_index:dict[str,int]={};seen_paths=set();seen_pairs=set()
    for chunk_id in sorted(chunks):
        chunk=validate_runtime_record("chunk",chunks[chunk_id]); page=chunk["page_path"]
        if chunk_id!=f"{chunk['page_address']}:{chunk['chunk_index']}":_fail("chunk identity differs")
        pair=(chunk["page_address"],chunk["chunk_index"])
        if pair in seen_pairs or chunk["chunk_index"]!=expected_index.get(page,0):_fail("chunk indices are not contiguous or unique")
        seen_pairs.add(pair)
        expected_index[page]=chunk["chunk_index"]+1
        if page not in pages:_fail("chunk page bytes are absent")
        page_bytes=pages[page]
        if page not in page_seen:
            text=page_bytes.decode("utf-8"); anchors=re.findall(r'(?m)(?<!\S)\^(clm-[0-9a-f]{20})[ \t]*$',text)
            expected={unit["claim_id"] for unit in units_by_page.get(page,[])}
            if set(anchors)!=expected or any(anchors.count(cid)!=1 for cid in set(anchors)):_fail("claim anchor set is missing, duplicated, unknown, or cross-owner")
            page_seen.add(page)
        body_hash="sha256:"+hashlib.sha256(chunk["raw_text"].encode()).hexdigest(); page_hash="sha256:"+hashlib.sha256(page_bytes).hexdigest()
        entry=docs[chunk_id]
        expected_path=f".vault-meta/chunks/{chunk['page_address']}/chunk-{chunk['chunk_index']:03d}.json"
        if expected_path in seen_paths:_fail("chunk path is duplicated")
        seen_paths.add(expected_path)
        if chunk["body_hash"]!=body_hash or chunk["page_body_hash"]!=page_hash or entry["body_hash"]!=body_hash or entry["page_body_hash"]!=page_hash or entry["path"]!=expected_path:
            _fail("chunk/index byte binding differs")
        selected=[]
        for unit in units_by_page.get(page,[]):
            if re.search(r'(?m)(?<!\S)\^'+re.escape(unit["claim_id"])+r'[ \t]*$',chunk["raw_text"]):
                selected.append(unit["evidence_unit_id"]);mapped.add(unit["evidence_unit_id"])
        page_units=units_by_page.get(page,[])
        joined.append({"chunk_id":chunk_id,"path":expected_path,"body_hash":body_hash,"page_body_hash":page_hash,"paper_id":page_units[0]["paper_id"] if page_units else None,"evidence_unit_ids":sorted(set(selected)),
            "default_evidence_unit_ids":sorted({u["evidence_unit_id"] for u in page_units if u["default_eligible"] and u["evidence_unit_id"] in selected})})
    if mapped!={x["evidence_unit_id"] for x in inv["units"]}:_fail("evidence unit is not represented in chunks")
    material={"inventory_sha256":hashlib.sha256(canonicalize(inv)).hexdigest(),"pages":{p:hashlib.sha256(b).hexdigest() for p,b in sorted(pages.items())},
        "chunks":{cid:runtime_projection_sha256("chunk",chunks[cid]) for cid in sorted(chunks)},"bm25_sha256":runtime_projection_sha256("bm25",bm25),"profile":"claude-obsidian.chunk-v1+bm25-v2"}
    result={"schema":"video-paper-wiki.evidence-mapping-authority.v1","inventory":inv,"chunks":joined,"profile":"claude-obsidian.chunk-v1+bm25-v2","generation_sha256":hashlib.sha256(canonicalize(material)).hexdigest(),"mapping_sha256":"0"*64}
    result["mapping_sha256"]=evidence_mapping_sha256(result)
    return validate_evidence_mapping_authority(result)

def join_evidence_files(*, vault_root:Path|str, request:object)->dict[str,Any]:
    """Bind an exact declaration to real no-follow page/chunk/index bytes."""
    request=validate_document(request,"video-paper-wiki.evidence-join-request.v1")
    root=Path(vault_root); retained=[]; directories=[]; directory_fds={}; pages={};chunks={};bm25=None
    root_fd=open_dir_nofollow(root,missing_code="EVIDENCE_JOIN_INVALID",unsafe_code="EVIDENCE_JOIN_INVALID")
    root_stat=os.fstat(root_fd);directory_fds[()]=root_fd;directories.append(((),None,None,root_fd,root_stat))
    def retain_parent(relative:str)->tuple[int,str]:
        parts=relative.split("/");parent=()
        for part in parts[:-1]:
            child=parent+(part,)
            if child not in directory_fds:
                parent_fd=directory_fds[parent]
                try:
                    named=os.stat(part,dir_fd=parent_fd,follow_symlinks=False);fd=os.open(part,dir_open_flags(),dir_fd=parent_fd);opened=os.fstat(fd)
                except OSError:_fail("join directory is unsafe")
                if not stat.S_ISDIR(named.st_mode) or stamp(named)!=stamp(opened):close_fd(fd);_fail("join directory identity differs")
                directory_fds[child]=fd;directories.append((child,parent_fd,part,fd,opened))
            parent=child
        return directory_fds[parent],parts[-1]
    def verify():
        try:
            reopened=open_dir_nofollow(root,missing_code="EVIDENCE_JOIN_INVALID",unsafe_code="EVIDENCE_JOIN_INVALID")
            try:
                if stamp(os.fstat(reopened))!=stamp(root_stat):_fail("join root changed")
            finally:close_fd(reopened)
            for _parts,parent_fd,name,fd,first in directories[1:]:
                now=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
                if not stat.S_ISDIR(now.st_mode) or stamp(now)!=stamp(first) or stamp(os.fstat(fd))!=stamp(first):_fail("join directory changed")
            for parent_fd,name,first in retained:
                if stamp(os.stat(name,dir_fd=parent_fd,follow_symlinks=False))!=stamp(first):_fail("join input changed")
        except OSError:_fail("join input changed")
    try:
        for relative,digest in sorted(request["files"].items()):
            if type(relative) is not str or type(digest) is not str or len(digest)!=64 or relative.startswith("/") or "\\" in relative or any(x in {"",".",".."} for x in relative.split("/")):_fail("file declaration differs")
            if not ((relative.startswith("wiki/") and relative.endswith(".md")) or relative.startswith(".vault-meta/chunks/") or relative==request["bm25_path"]):_fail("file declaration is outside the closed join set")
            parent_fd,name=retain_parent(relative);path=root/relative
            try:first=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            except OSError:_fail("join input is unsafe")
            if stat.S_ISLNK(first.st_mode) or not stat.S_ISREG(first.st_mode):_fail("join input is unsafe")
            data=read_child_regular(parent_fd,name,path=path,missing_code="EVIDENCE_JOIN_INVALID",unsafe_code="EVIDENCE_JOIN_INVALID",changed_code="EVIDENCE_JOIN_INVALID",max_bytes=64*1024*1024,limit_code="EVIDENCE_JOIN_INVALID")
            retained.append((parent_fd,name,first))
            if hashlib.sha256(data).hexdigest()!=digest:_fail("declared file digest differs")
            if relative.startswith("wiki/") and relative.endswith(".md"):pages[relative]=data
            elif relative.startswith(".vault-meta/chunks/"):
                value=parse_projection_json(data);chunk=validate_runtime_record("chunk",value);chunk_id=f"{chunk['page_address']}:{chunk['chunk_index']}"
                if chunk_id in chunks:_fail("chunk identity is duplicated")
                chunks[chunk_id]=chunk
            if relative==request["bm25_path"]:bm25=parse_projection_json(data)
        if bm25 is None:_fail("BM25 declaration is missing")
        result=join_evidence(inventory=request["inventory"],pages=pages,chunks=chunks,bm25=bm25);verify();return result
    except BaseException:
        verify();raise
    finally:
        for _parts,_parent,_name,fd,_first in reversed(directories):close_fd(fd)
