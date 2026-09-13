"""Closed deterministic reports over a verified immutable catalog."""
from __future__ import annotations

import copy
import sqlite3
from pathlib import Path
from typing import Any

from video_paper_wiki.catalog_store import DB_RELATIVE, _RetainedFile, _meta, _readonly, catalog_status
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize

_KINDS={"code-openness","paper-lifecycle","evidence-coverage"}

def _fail(code:str,message:str)->None:raise ContractError(code,message)
def _rows(con:sqlite3.Connection,sql:str,args:tuple=())->list[dict[str,Any]]:
    cursor=con.execute(sql,args);cols=[x[0] for x in cursor.description];return [dict(zip(cols,row)) for row in cursor]

def _code(con:sqlite3.Connection,paper_id:str|None)->list[dict[str,Any]]:
    papers=_rows(con,"SELECT paper_id,title FROM papers"+(" WHERE paper_id=?" if paper_id else "")+" ORDER BY paper_id",(paper_id,) if paper_id else ())
    for paper in papers:
        repos=[]
        for repo in _rows(con,"SELECT r.repo_id,r.canonical_repository,r.canonical_commit,r.archived,r.officiality AS officiality_status,r.license_spdx_id,r.license_notes FROM repo_papers rp JOIN repos r ON r.repo_id=rp.repo_id WHERE rp.paper_id=? ORDER BY r.repo_id",(paper["paper_id"],)):
            repo["archived"]=None if repo["archived"] is None else bool(repo["archived"]);alignments=[]
            for a in _rows(con,'SELECT input_path,repo_id,repository,"commit" AS "commit",archived,officiality AS officiality_status,license_spdx_id,license_notes FROM alignment_manifests WHERE paper_id=? AND repo_id=? ORDER BY input_path',(paper["paper_id"],repo["repo_id"])):
                a["archived"]=bool(a["archived"])
                a["officiality_evidence"]=_rows(con,"SELECT ordinal,source_id,locator_wire FROM alignment_officiality_evidence WHERE alignment_path=? ORDER BY ordinal",(a["input_path"],))
                capabilities=[]
                for c in _rows(con,"SELECT ordinal,name,status,checkpoint_kind,absence_scope_present,absence_commit,absence_tree_prefix FROM alignment_capabilities WHERE alignment_path=? ORDER BY ordinal,name",(a["input_path"],)):
                    c["absence_scope"]={"present":bool(c.pop("absence_scope_present")),"commit":c.pop("absence_commit"),"tree_prefix":c.pop("absence_tree_prefix"),"patterns":[x["pattern"] for x in _rows(con,"SELECT pattern FROM alignment_absence_patterns WHERE alignment_path=? AND capability_name=? ORDER BY ordinal",(a["input_path"],c["name"]))]}
                    c["evidence"]=_rows(con,"SELECT ordinal,source_id,locator_wire FROM alignment_capability_locators WHERE alignment_path=? AND capability_name=? ORDER BY ordinal",(a["input_path"],c["name"]))
                    capabilities.append(c)
                a["capabilities"]=capabilities;alignments.append(a)
            repo["alignments"]=alignments;repos.append(repo)
        paper["repositories"]=repos
    return papers

def _lifecycle(con:sqlite3.Connection,paper_id:str|None)->list[dict[str,Any]]:
    papers=_rows(con,"SELECT paper_id,title,active_extraction_path,active_extraction_sha256 FROM papers"+(" WHERE paper_id=?" if paper_id else "")+" ORDER BY paper_id",(paper_id,) if paper_id else ())
    for paper in papers:
        paper["active_extraction"]={"path":paper.pop("active_extraction_path"),"sha256":paper.pop("active_extraction_sha256")}
        claims=_rows(con,"SELECT cr.ordinal,cr.claim_id,cr.section,cr.capability,cr.core,cr.lifecycle,c.assessment,c.confidence,c.reviewed_at,ah.head_event_id AS assessment_head_event_id FROM subjects s JOIN claim_refs cr ON cr.subject_id=s.subject_id JOIN claims c ON c.claim_id=cr.claim_id LEFT JOIN assessment_heads ah ON ah.claim_id=cr.claim_id WHERE s.owner_kind='paper' AND s.paper_id=? ORDER BY cr.ordinal,cr.claim_id",(paper["paper_id"],))
        for claim in claims:
            claim["core"]=None if claim["core"] is None else bool(claim["core"])
            # The canonical claim ledger records the review day.  The report
            # contract uses the common UTC instant profile, so expose that
            # closed value at the start of the recorded UTC day.
            if claim["reviewed_at"] is not None and len(claim["reviewed_at"])==10:
                claim["reviewed_at"] += "T00:00:00Z"
        paper["claims"]=claims
    return papers

def _coverage(con:sqlite3.Connection,paper_id:str|None)->list[dict[str,Any]]:
    papers=_rows(con,"SELECT paper_id,title FROM papers"+(" WHERE paper_id=?" if paper_id else "")+" ORDER BY paper_id",(paper_id,) if paper_id else ())
    for paper in papers:
        units=[]
        for unit in _rows(con,"SELECT evidence_unit_id,claim_id,locator_fingerprint,lifecycle,assessment,core,default_eligible,gold_eligible FROM search_evidence_units WHERE paper_id=? ORDER BY evidence_unit_id",(paper["paper_id"],)):
            for key in ("core","default_eligible","gold_eligible"):unit[key]=bool(unit[key])
            unit["mapped_chunks"]=_rows(con,"SELECT c.page_path,c.chunk_index,c.chunk_id FROM search_chunk_evidence e JOIN search_chunks c ON c.chunk_id=e.chunk_id WHERE e.evidence_unit_id=? ORDER BY c.page_path,c.chunk_index,c.chunk_id",(unit["evidence_unit_id"],));units.append(unit)
        mapped=sum(bool(x["mapped_chunks"]) for x in units);chunks=sum(len(x["mapped_chunks"]) for x in units)
        paper["coverage"]={"evidence_unit_count":len(units),"mapped_evidence_unit_count":mapped,"unmapped_evidence_unit_count":len(units)-mapped,"mapped_chunk_count":chunks};paper["evidence_units"]=units
    return papers

def catalog_report(*,vault_root:Path|str,upstream_root:Path|str,retrieval_config:object,report_kind:str,paper_id:str|None=None,barrier=None)->dict[str,Any]:
    if type(report_kind) is not str or report_kind not in _KINDS or (paper_id is not None and type(paper_id) is not str):_fail("CATALOG_REPORT_INVALID","report arguments are invalid")
    path=Path(vault_root)/DB_RELATIVE
    held=_RetainedFile(path);live=[]
    try:
        status=catalog_status(vault_root,upstream_root,retrieval_config,_live_holder=live)
        if status["state"]!="current":_fail("CATALOG_STALE","catalog is stale")
        con=_readonly(path,held)
        try:
            con.execute("BEGIN");meta=_meta(con);rows={"code-openness":_code,"paper-lifecycle":_lifecycle,"evidence-coverage":_coverage}[report_kind](con,paper_id);con.execute("COMMIT")
        finally:con.close()
        if barrier:barrier("before-report-recheck")
        held.verify()
        for snapshot in live:snapshot.verify()
        result={"schema":"video-paper-wiki.catalog-report.v1","report_kind":report_kind,"catalog_state":"current","paper_id_filter":paper_id,
                **{k:meta[k] for k in ("join_generation_sha256","mapping_sha256","retrieval_config_sha256","catalog_generation_sha256")},"rows":rows}
        try:validate_document(result,"video-paper-wiki.catalog-report.v1")
        except ContractError:_fail("CATALOG_STALE","catalog report rows violate the closed schema")
        raw=canonicalize(result)
        if len(raw)>8*1024*1024:_fail("CATALOG_REPORT_LIMIT_EXCEEDED","catalog report exceeds byte limit")
        return copy.deepcopy(result)
    except ContractError:
        held.verify()
        for snapshot in live:snapshot.verify()
        raise
    except (OSError,sqlite3.Error,KeyError,TypeError):_fail("CATALOG_STALE","catalog report source is invalid")
    finally:
        held.close()
        for snapshot in live:
            try:snapshot.verify()
            finally:snapshot.close()

__all__=["catalog_report"]
