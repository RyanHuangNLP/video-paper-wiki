#!/usr/bin/env python3
"""Generate a validated 3-paper/1-code installed-vertical fixture.

Outputs are synthetic mechanical inputs. They prove no provenance, license,
officiality, scientific assessment, visual acceptance, or external gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from io import BytesIO
from pathlib import Path

# Locate the checkout before importing its public package and reusable test
# fixture constructors.  Callers can override this without changing bytes.
ROOT = Path(os.environ.get("VPWIKI_REPO", Path(__file__).resolve().parents[2])).resolve()
if not (ROOT / "tests").is_dir():
    ROOT = Path.cwd().resolve()
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from pypdf import PdfReader, PdfWriter

from tests.support import code_evidence_request, complete_ingest_plan, make_approval_ref, paper_source_request
from video_paper_wiki.approval import bind_approval_ref
from video_paper_wiki.assessment_history import derive_assessment_heads
from video_paper_wiki.canonical_compiler import compile_pages, concept_items_for_papers
from video_paper_wiki.code_evidence_contracts import (code_manifest_hash, code_proposal_hash,
    code_snippet_sha256, code_text_metadata, validate_code_evidence_manifest)
from video_paper_wiki.contracts import validate_document
from video_paper_wiki.identity import assessment_event_id, claim_id, evidence_fingerprint
from video_paper_wiki.jcs import canonicalize

FIX = ROOT / "tests/fixtures/contracts/valid"
HIST = ROOT / "tests/fixtures/assessment-history/complete-vectors.json"
SHA = lambda data: hashlib.sha256(data).hexdigest()
UTC = "2026-09-02T00:00:00Z"


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonicalize(value))


def pdf(index: int) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72 + index, height=96 + index)
    writer.add_metadata({"/Title": f"Synthetic Video Paper {index}", "/Subject": "fixture-only"})
    output = BytesIO(); writer.write(output); raw = output.getvalue()
    assert len(PdfReader(BytesIO(raw)).pages) == 1
    return raw


def paper(base: dict, evidence: dict, index: int) -> dict:
    record = copy.deepcopy(base)
    arxiv = ["2311.15127", "0002.00002", "0003.00003"][index - 1]
    record.update({"paper_id": "arxiv:" + arxiv, "arxiv_id": arxiv,
                   "title": f"Synthetic Video Paper {index}", "title_zh": f"合成视频论文{index}",
                   "aliases": [f"Synthetic Paper {index}"], "code_urls": [] if index > 1 else record["code_urls"]})
    text = f"Synthetic mechanically accepted compiler claim {index}."
    subject = "paper:" + record["paper_id"]; cid = claim_id(subject, text)
    fp = evidence_fingerprint([evidence])
    claim = {"claim_id": cid, "stable_subject_id": subject, "canonical_claim_text": text,
             "evidence": [copy.deepcopy(evidence)], "assessment": "accepted", "reviewed_at": "2026-09-02"}
    genesis = {"schema":"video-paper-wiki.assessment-event.v1", "event_id":"ase-"+"0"*20,
        "claim_id":cid,"previous_event_id":None,"actor_kind":"system","transition_kind":"genesis",
        "from_assessment":None,"to_assessment":"provisional","claim_text_sha256":SHA(text.encode()),
        "evidence_fingerprint":fp,"decided_by":"fixture-system","decided_at":UTC,"reason":"Synthetic genesis."}
    genesis["event_id"] = assessment_event_id(genesis)
    accepted = {**genesis,"event_id":"ase-"+"0"*20,"previous_event_id":genesis["event_id"],
        "actor_kind":"human","transition_kind":"human_assessment","from_assessment":"provisional",
        "to_assessment":"accepted","decided_by":"human:synthetic-fixture","reason":"Mechanical fixture acceptance."}
    accepted["event_id"] = assessment_event_id(accepted)
    record["section_claim_refs"] = [{"section":"one_sentence_conclusion","claim_id":cid,"core":True,"lifecycle":"active"}]
    validate_document(record, "video-paper-wiki.paper-record.v1")
    events = [accepted, genesis]
    heads = derive_assessment_heads(claims=[claim], events=events)
    return {"record":record,"claims":[claim],"events":events,"assessment_heads":heads}


def code_triple(payload: bytes, first_paper: str) -> dict:
    repo = json.loads((FIX / "video-paper-wiki.repo-record.v1.json").read_text())
    alignment = json.loads((FIX / "video-paper-wiki.paper-code-alignment.v1.json").read_text())
    manifest = json.loads((FIX / "video-paper-wiki.code-evidence-manifest.v1.json").read_text())
    repo["paper_ids"] = [first_paper]
    alignment["paper_id"] = first_paper
    manifest["origin"] = {"repository":repo["canonical_repository"],"commit":repo["canonical_commit"],"path":"train.py"}
    manifest["payload"] = {"sha256":SHA(payload),"size_bytes":len(payload)}
    manifest.update(code_text_metadata(payload)); manifest["proposal_sha256"] = code_proposal_hash(manifest)
    manifest["state"] = "inspected"
    manifest["capture"] = {"stored_path":f".raw/captured/{SHA(payload)}.bin","source_identity":SHA(payload),
        "source_id":"src-repo","inspection_approval_hash":"a"*64,"operation_id":"vertical-code"}
    manifest["manifest_sha256"] = code_manifest_hash(manifest)
    snippet = code_snippet_sha256(payload, 10, 30)
    for capability in alignment["capabilities"]:
        for locator in capability["locators"]:
            locator.update({"source_id":"src-repo","repository":repo["canonical_repository"],
                            "commit":repo["canonical_commit"],"path":"train.py",
                            "lines":{"start":10,"end":30},"snippet_sha256":snippet})
        if capability.get("absence_scope") is not None:
            capability["absence_scope"]["commit"] = repo["canonical_commit"]
    validate_code_evidence_manifest(manifest, payload=payload)
    validate_document(repo, "video-paper-wiki.repo-record.v1")
    validate_document(alignment, "video-paper-wiki.paper-code-alignment.v1")
    return {"manifest":manifest,"repo_record":repo,"alignment":alignment}


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    base = json.loads((FIX / "video-paper-wiki.paper-record.v1.json").read_text())
    evidence = json.loads(HIST.read_text())["evidence"]["code"]
    papers = [paper(base, evidence, i) for i in range(1, 4)]
    code = ("# 合成 UTF-8 fixture\n" + "\n".join(f"line_{i} = {i}" for i in range(1, 33)) + "\n").encode()
    triple = code_triple(code, papers[0]["record"]["paper_id"])
    records = [x["record"] for x in papers]
    material = {"schema":"video-paper-wiki.compile-input.v1","operation_id":"vertical-compile",
                "papers":papers,"code":[triple],"concepts":concept_items_for_papers(records)}
    validate_document(material, "video-paper-wiki.compile-input.v1")
    pages1 = compile_pages(material); pages2 = compile_pages(copy.deepcopy(material)); assert pages1 == pages2
    dump(out / "compile-input.json", material)
    (out / "code.py").write_bytes(code)
    plans = []
    for i in range(1, 4):
        raw = pdf(i); digest = SHA(raw); (out / f"paper-{i}.pdf").write_bytes(raw)
        request = paper_source_request(batch_id=f"vertical-paper-{i}", local_sha256=digest,
                                       arxiv_id=records[i-1]["arxiv_id"])
        plan = complete_ingest_plan(request); ref = make_approval_ref(plan)
        bind_approval_ref(plan, ref); dump(out / f"paper-{i}.request.json", request); dump(out / f"paper-{i}.plan.json", plan); dump(out / f"paper-{i}.approval-ref.json", ref)
        plans.append({"kind":"paper-source","batch_id":plan["batch_id"],"input_sha256":digest,
                      "plan_sha256":SHA(canonicalize(plan)),"approval_ref_sha256":SHA(canonicalize(ref))})
    request = code_evidence_request(batch_id="vertical-code", repository=triple["repo_record"]["canonical_repository"],
                                    commit=triple["repo_record"]["canonical_commit"], source_path="train.py")
    plan = complete_ingest_plan(request); ref = make_approval_ref(plan, input_sha256=SHA(code)); bind_approval_ref(plan, ref)
    dump(out / "code.request.json", request); dump(out / "code.plan.json", plan); dump(out / "code.approval-ref.json", ref)
    plans.append({"kind":"code-evidence","batch_id":plan["batch_id"],"input_sha256":SHA(code),
                  "plan_sha256":SHA(canonicalize(plan)),"approval_ref_sha256":SHA(canonicalize(ref))})
    summary = {"schema":"vpwiki.synthetic-installed-fixture.v1","compile_input_sha256":SHA(canonicalize(material)),
        "page_count":len(pages1),"page_paths":list(pages1),"page_hashes":{k:SHA(v) for k,v in pages1.items()},
        "plans":plans,"external_gate_satisfied":False,"human_assessment":False,"provenance_verified":False,
        "license_verified":False,"visual_acceptance":False}
    dump(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv)!=2:
        raise SystemExit('usage: _installed_fixture_builder.py OUTPUT_DIRECTORY')
    main(Path(sys.argv[1]))
