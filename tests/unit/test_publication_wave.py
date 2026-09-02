from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from video_paper_wiki.contracts import ContractError
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki.publication import prepare_publication_source, stage_publication_request, validate_publication_request
from video_paper_wiki.receipt_audit import audit_integrity


def _put(root: Path, relative: str, data: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o600)


def _receipt_vault(root: Path) -> tuple[dict, dict]:
    data = b'{"record":1}'
    path = "wiki/meta/records/paper.json"
    receipt = {"schema":"video-paper-wiki.operation-receipt.v1","sequence":1,"previous":None,
        "operation_id":"genesis","operation_type":"generic","intent_sha256":"0"*64,
        "writes":[{"path":path,"mode":"create","before_sha256":None,"after_sha256":hashlib.sha256(data).hexdigest()}],
        "claimed_inputs":[]}
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    receipt_raw = canonicalize(receipt)
    receipt_path = "wiki/meta/operations/000000000001-genesis.json"
    head = {"schema":"video-paper-wiki.operation-head.v1","sequence":1,"receipt_path":receipt_path,
            "receipt_sha256":hashlib.sha256(receipt_raw).hexdigest()}
    _put(root, path, data); _put(root, receipt_path, receipt_raw); _put(root, "wiki/meta/registries/operation-head.json", canonicalize(head))
    return receipt, head


def test_receipt_audit_replays_unique_complete_set(tmp_path: Path):
    _receipt_vault(tmp_path)
    report = audit_integrity(tmp_path)
    assert report["valid"] and report["classification"] == "receipt_backed"
    assert report["current_paths"] == ["wiki/meta/records/paper.json"]
    extra = tmp_path / "wiki/meta/operations/000000000099-orphan.json"
    extra.write_bytes(b"{}"); extra.chmod(0o600)
    with pytest.raises(ContractError) as caught:
        audit_integrity(tmp_path)
    assert caught.value.code == "RECEIPT_CHAIN_INVALID"


def test_receipt_audit_headless_classification(tmp_path: Path):
    assert audit_integrity(tmp_path)["classification"] == "empty"
    _put(tmp_path, "wiki/meta/ledgers/source-ledger.json", b"{}")
    _put(tmp_path, "wiki/meta/ledgers/claim-ledger.json", b"{}")
    with pytest.raises(ContractError) as caught:
        audit_integrity(tmp_path)
    assert caught.value.code == "OUT_OF_BAND_WRITE"


def test_publication_request_is_content_addressed_and_request_last(tmp_path: Path, monkeypatch):
    (tmp_path / ".git").mkdir(); (tmp_path / "pyproject.toml").write_text('[project]\nname="video-paper-wiki"\n')
    monkeypatch.chdir(tmp_path)
    staged = stage_publication_request(batch_id="pub-one", operation_id="op-one", operation_type="generic",
        payloads={"wiki/meta/records/a.json":b"{}"})
    request = validate_publication_request(staged["request"])
    descriptor = request["payloads"][0]
    content = tmp_path / ".work/pub-one" / descriptor["content_file"]
    target = Path(staged["request_path"])
    assert content.read_bytes() == b"{}" and target.read_bytes() == canonicalize(request)
    assert content.stat().st_mtime_ns <= target.stat().st_mtime_ns
    bad = json.loads(target.read_text()); bad["payloads"][0]["content_file"] = "publication-input/content/nope"
    with pytest.raises(ContractError): validate_publication_request(bad)


def test_publication_prepare_source_inside_checkout_allows_staging_parent_mtime(tmp_path: Path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir(); (checkout / ".git").mkdir()
    (checkout / "pyproject.toml").write_text('[project]\nname="video-paper-wiki"\n')
    monkeypatch.chdir(checkout)
    seeded = stage_publication_request(batch_id="source-one", operation_id="source-op",
        operation_type="generic", payloads={"wiki/meta/records/source.json": b"{}"})
    staged_root = checkout / ".work/source-one/publication-input"
    source_root = checkout / "publication-input"
    source_root.mkdir()
    (source_root / "content").mkdir()
    request_raw = Path(seeded["request_path"]).read_bytes()
    request = validate_publication_request(parse_strict_json(request_raw, invalid_code="SCHEMA_INVALID"))
    (source_root / "knowledge-publication-request.v1.json").write_bytes(request_raw)
    for item in request["payloads"]:
        (source_root / "content" / item["content_file"].split("/")[-1]).write_bytes(
            (staged_root / item["content_file"].removeprefix("publication-input/")).read_bytes())
    # Force the real prepare path to install under .work after its retained source baseline.
    import shutil
    shutil.rmtree(checkout / ".work/source-one")
    result = prepare_publication_source(
        request_path=source_root / "knowledge-publication-request.v1.json", batch_id="source-one")
    assert result["request"] == request


def test_compiler_never_emits_out_of_scope_catalog():
    source = Path(__file__).resolve().parents[2] / "src/video_paper_wiki/canonical_compiler.py"
    assert "wiki/video-papers/catalog.md" not in source.read_text(encoding="utf-8")


def _claim_history():
    from video_paper_wiki import identity
    evidence = json.loads((Path(__file__).resolve().parents[1] / "fixtures/assessment-history/complete-vectors.json").read_text())["evidence"]["code"]
    text = "A bounded review claim."; subject = "paper:arxiv:2311.15127"
    claim = {"claim_id":identity.claim_id(subject,text),"stable_subject_id":subject,
             "canonical_claim_text":text,"evidence":[evidence],"assessment":"provisional","reviewed_at":None}
    event = {"schema":"video-paper-wiki.assessment-event.v1","event_id":"ase-"+"0"*20,
             "claim_id":claim["claim_id"],"previous_event_id":None,"actor_kind":"system",
             "transition_kind":"genesis","from_assessment":None,"to_assessment":"provisional",
             "claim_text_sha256":hashlib.sha256(text.encode()).hexdigest(),
             "evidence_fingerprint":identity.evidence_fingerprint([evidence]),"decided_by":"fixture",
             "decided_at":"2026-09-01T00:00:00Z","reason":"Fixture genesis."}
    event["event_id"] = identity.assessment_event_id(event)
    return claim, [event]


def _vault_with_files(root: Path, files: dict[str, bytes]) -> None:
    writes=[]
    for path,data in sorted(files.items()):
        _put(root,path,data);writes.append({"path":path,"mode":"create","before_sha256":None,"after_sha256":hashlib.sha256(data).hexdigest()})
    receipt={"schema":"video-paper-wiki.operation-receipt.v1","sequence":1,"previous":None,"operation_id":"fixture-genesis","operation_type":"generic","intent_sha256":"0"*64,"writes":writes,"claimed_inputs":[]}
    receipt["intent_sha256"]=receipt_intent_sha256(receipt);raw=canonicalize(receipt);rp="wiki/meta/operations/000000000001-fixture-genesis.json"
    head={"schema":"video-paper-wiki.operation-head.v1","sequence":1,"receipt_path":rp,"receipt_sha256":hashlib.sha256(raw).hexdigest()}
    _put(root,rp,raw);_put(root,"wiki/meta/registries/operation-head.json",canonicalize(head))


def _review_vault(root:Path):
    from video_paper_wiki.ledger_locator import encode_ledger_evidence
    claim,events=_claim_history();paper=json.loads((Path(__file__).resolve().parents[1]/"fixtures/contracts/valid/video-paper-wiki.paper-record.v1.json").read_text())
    paper["paper_id"]="arxiv:2311.15127";paper["section_claim_refs"]=[{"section":"one_sentence_conclusion","claim_id":claim["claim_id"],"core":True,"lifecycle":"active"}]
    record={"text":claim["canonical_claim_text"],"risk":"low","assessment":"provisional","confidence":"medium","location":{"path":"wiki/papers/arxiv-2311.15127.md","anchor":"^"+claim["claim_id"]},"reviewed_at":None,"notes":None,"supersedes":None,"evidence":[encode_ledger_evidence(x) for x in claim["evidence"]]}
    ledger={"schema":"claude-obsidian.claim-ledger.v1","generated_at":"2026-09-01T00:00:00Z","claims":{claim["claim_id"]:record}}
    event_path=f"wiki/meta/reviews/{claim['claim_id']}/{events[0]['event_id']}.json"
    files={"wiki/meta/ledgers/claim-ledger.json":canonicalize(ledger),"wiki/meta/records/paper.json":canonicalize(paper),event_path:canonicalize(events[0])}
    _vault_with_files(root,files);return claim,events,ledger


def test_review_consumes_only_mechanical_decision_and_vault_authority(tmp_path: Path, monkeypatch):
    from video_paper_wiki import review_workflow as review_module
    from video_paper_wiki.canonical_compiler import compile_pages,concept_items_for_papers
    prepare_review_transition=review_module.prepare_review_transition;validate_review_transition_authority=review_module.validate_review_transition_authority
    checkout=tmp_path/"checkout";checkout.mkdir();(checkout/".git").mkdir();(checkout/"pyproject.toml").write_text('[project]\nname="video-paper-wiki"\n');monkeypatch.chdir(checkout)
    vault=tmp_path/"vault";vault.mkdir();claim,events,ledger=_review_vault(vault)
    future=json.loads(json.dumps(ledger));future["generated_at"]="2026-09-02T01:02:03Z";future["claims"][claim["claim_id"]]["assessment"]="accepted";future["claims"][claim["claim_id"]]["reviewed_at"]="2026-09-02"
    decision={"schema":"video-paper-wiki.review-decision.v1","claim_id":claim["claim_id"],"expected_previous_event_id":events[0]["event_id"],"assessment":"accepted","decided_by":"human:fixture","decided_at":"2026-09-02T01:02:03Z","reason":"Synthetic mechanical decision."}
    new_claim=review_module._claim(future["claims"][claim["claim_id"]],"arxiv:2311.15127",claim["claim_id"])
    generated=review_module._event(new_claim,events[0],actor="human",transition="human_assessment",target="accepted",decided_by=decision["decided_by"],decided_at=decision["decided_at"],reason=decision["reason"])
    paper_path="wiki/meta/records/paper-input.json";claims_path="wiki/meta/records/claims-input.json";events_path="wiki/meta/records/events-input.json"
    material={"schema":"video-paper-wiki.compile-input.v1","operation_id":"review-one","papers":[{"record":json.loads((vault/"wiki/meta/records/paper.json").read_text()),"claims":[new_claim],"events":events+[generated]}],"code":[],"concepts":[]};material["concepts"]=concept_items_for_papers([material["papers"][0]["record"]]);pages=compile_pages(material)
    payloads={"wiki/meta/ledgers/claim-ledger.json":canonicalize(future),paper_path:canonicalize(material["papers"][0]["record"]),claims_path:canonicalize([new_claim]),events_path:canonicalize(events+[generated])}|pages
    context={"operation_id":"review-one","payloads":payloads,"claimed_input_paths":[],"prospective_groups":[{"group_id":"paper","paper_record":paper_path,"claims":claims_path,"events":events_path}]}
    result=prepare_review_transition(decision=decision,publication_context=context,batch_id="review-batch",vault_root=vault)
    assert result["claim"]["assessment"]=="accepted" and result["events"][0]["actor_kind"]=="human"
    assert validate_review_transition_authority(result)==result
    coherent=json.loads(json.dumps(result));coherent["claim_ledger"]["generated_at"]="2026-09-02T01:02:04Z"
    ledger_raw=canonicalize(coherent["claim_ledger"])
    descriptor=next(x for x in coherent["publication_request"]["request"]["payloads"] if x["path"]=="wiki/meta/ledgers/claim-ledger.json")
    descriptor["sha256"]=hashlib.sha256(ledger_raw).hexdigest();descriptor["size_bytes"]=len(ledger_raw);descriptor["content_file"]="publication-input/content/"+descriptor["sha256"]
    request_raw=canonicalize(coherent["publication_request"]["request"]);request_sha=hashlib.sha256(request_raw).hexdigest()
    coherent["publication_request"]["request_sha256"]=request_sha;coherent["request_sha256"]=request_sha
    with pytest.raises(ContractError) as caught:validate_review_transition_authority(coherent)
    assert caught.value.code=="REVIEW_PUBLICATION_INVALID"
    bad={**decision,"expected_previous_event_id":"ase-"+"f"*20}
    with pytest.raises(ContractError) as caught:prepare_review_transition(decision=bad,publication_context=context,batch_id="bad-review",vault_root=vault)
    assert caught.value.code=="REVIEW_DECISION_INVALID"
    for broken in (
        {**context,"prospective_groups":[]},
        {**context,"payloads":{path:data for path,data in context["payloads"].items() if not path.startswith("wiki/papers/")}},
        {**context,"prospective_groups":context["prospective_groups"]*2},
    ):
        with pytest.raises(ContractError) as caught:prepare_review_transition(decision=decision,publication_context=broken,batch_id="review-broken",vault_root=vault)
        assert caught.value.code=="REVIEW_PUBLICATION_INVALID"
    wrong_time=json.loads(json.dumps(future));wrong_time["generated_at"]="2026-09-02T01:02:04Z"
    with pytest.raises(ContractError) as caught:prepare_review_transition(decision=decision,publication_context={**context,"payloads":{**context["payloads"],"wiki/meta/ledgers/claim-ledger.json":canonicalize(wrong_time)}},batch_id="review-time",vault_root=vault)
    assert caught.value.code=="REVIEW_PUBLICATION_INVALID"
    invalidation={"schema":"video-paper-wiki.review-invalidation-request.v1","claim_id":claim["claim_id"],"expected_previous_event_id":events[0]["event_id"],"expected_old_evidence_fingerprint":"a"*64,"expected_new_claim_sha256":"b"*64,"decided_at":"2026-09-02T01:02:03Z","reason":"Synthetic invalidation."}
    with pytest.raises(ContractError) as caught:review_module.prepare_evidence_invalidation(request=invalidation,publication_context={"operation_id":"invalidate-time","payloads":{"wiki/meta/ledgers/claim-ledger.json":canonicalize(wrong_time)},"claimed_input_paths":[],"prospective_groups":[]},batch_id="invalidate-time",vault_root=vault)
    assert caught.value.code=="REVIEW_PUBLICATION_INVALID"


def test_docling_package_uses_receipt_backed_vault_and_reuses_exact_bytes(tmp_path: Path, monkeypatch):
    from video_paper_wiki.extraction_artifact import prepare_docling_publication
    from video_paper_wiki.identity import pipeline_fingerprint
    checkout=tmp_path/"checkout";checkout.mkdir();(checkout/".git").mkdir();(checkout/"pyproject.toml").write_text('[project]\nname="video-paper-wiki"\n');monkeypatch.chdir(checkout)
    vault=tmp_path/"vault";vault.mkdir();pdf=b"%PDF fixture";pdf_sha=hashlib.sha256(pdf).hexdigest();captured=f".raw/captured/{pdf_sha}.pdf";_vault_with_files(vault,{captured:pdf})
    data={"document_json":b'{"text":"x","value":0.5}',"parser_config":b'{"profile":"fixture"}',"model_manifest":b'{"models":[]}'}
    fp=pipeline_fingerprint({"engine":"docling","engine_version":"2.117.0","core_version":"2.92.0","config_sha256":hashlib.sha256(data["parser_config"]).hexdigest(),"model_manifest_sha256":hashlib.sha256(data["model_manifest"]).hexdigest()})
    run={"schema":"video-paper-wiki.run-manifest.v1","run_id":"run-1","tool_versions":{"vpwiki":"fixture","python":"3.13","docling":"2.117.0","docling_core":"2.92.0"},"input_hashes":{"parser_config_sha256":hashlib.sha256(data["parser_config"]).hexdigest(),"model_manifest_sha256":hashlib.sha256(data["model_manifest"]).hexdigest()},"output_hashes":{"document_json_sha256":hashlib.sha256(data["document_json"]).hexdigest()},"started_at":"2026-09-01T00:00:00Z","ended_at":"2026-09-01T00:00:01Z","error_code":None,"pipeline_fingerprint":fp};data["run_manifest"]=canonicalize(run)
    paths={"captured_pdf":vault/captured}
    for kind,raw in data.items():paths[kind]=tmp_path/kind;paths[kind].write_bytes(raw)
    context={"operation_id":"extract-one","claimed_input_paths":[],"prospective_groups":[]}
    result=prepare_docling_publication(**paths,publication_context=context,batch_id="extract-batch",vault_root=vault)
    assert not result["already_packaged"] and len(result["artifact_set"]["artifacts"])==4 and result["external_gate_satisfied"] is False
    desired={item["path"]:data[item["kind"]] for item in result["artifact_set"]["artifacts"]};_vault_with_files(vault,desired|{captured:pdf})
    reused=prepare_docling_publication(**paths,publication_context={**context,"operation_id":"extract-reuse"},batch_id="extract-reuse",vault_root=vault)
    assert reused["already_packaged"] and reused["publication_request"] is None
    first=result["artifact_set"]["artifacts"][0]["path"];(vault/first).write_bytes(b"{}")
    with pytest.raises(ContractError) as caught:prepare_docling_publication(**paths,publication_context=context,batch_id="extract-bad",vault_root=vault)
    assert caught.value.code in {"NONDETERMINISTIC_EXTRACTION","OUT_OF_BAND_WRITE"}


def test_docling_partial_reuse_and_source_barrier(tmp_path:Path,monkeypatch):
    from video_paper_wiki import extraction_artifact as module
    from video_paper_wiki.identity import pipeline_fingerprint
    checkout=tmp_path/"checkout";checkout.mkdir();(checkout/".git").mkdir();(checkout/"pyproject.toml").write_text('[project]\nname="video-paper-wiki"\n');monkeypatch.chdir(checkout)
    vault=tmp_path/"vault";vault.mkdir();pdf=b"%PDF partial";pdf_sha=hashlib.sha256(pdf).hexdigest();captured=f".raw/captured/{pdf_sha}.pdf"
    data={"document_json":b'{"text":"x"}',"parser_config":b'{"profile":"fixture"}',"model_manifest":b'{"models":[]}'}
    fp=pipeline_fingerprint({"engine":"docling","engine_version":"2.117.0","core_version":"2.92.0","config_sha256":hashlib.sha256(data["parser_config"]).hexdigest(),"model_manifest_sha256":hashlib.sha256(data["model_manifest"]).hexdigest()})
    run={"schema":"video-paper-wiki.run-manifest.v1","run_id":"run-partial","tool_versions":{"vpwiki":"fixture","python":"3.13","docling":"2.117.0","docling_core":"2.92.0"},"input_hashes":{"parser_config_sha256":hashlib.sha256(data["parser_config"]).hexdigest(),"model_manifest_sha256":hashlib.sha256(data["model_manifest"]).hexdigest()},"output_hashes":{"document_json_sha256":hashlib.sha256(data["document_json"]).hexdigest()},"started_at":"2026-09-01T00:00:00Z","ended_at":"2026-09-01T00:00:01Z","error_code":None,"pipeline_fingerprint":fp};data["run_manifest"]=canonicalize(run)
    dest=module._destinations(pdf_sha,fp,"run-partial");_vault_with_files(vault,{captured:pdf,dest["document_json"]:data["document_json"]})
    paths={"captured_pdf":vault/captured}
    for kind,raw in data.items():paths[kind]=tmp_path/kind;paths[kind].write_bytes(raw)
    context={"operation_id":"partial","claimed_input_paths":[],"prospective_groups":[]}
    result=module.prepare_docling_publication(**paths,publication_context=context,batch_id="partial",vault_root=vault)
    assert not result["already_packaged"] and len(result["publication_request"]["request"]["payloads"])==3
    real_snapshot=module._Snapshot
    def snapshot_failure(_vault):
        source=paths["model_manifest"];replacement=source.with_suffix(".snapshot-new");replacement.write_bytes(source.read_bytes());os.replace(replacement,source)
        raise ContractError("AUDIT_RACE","synthetic snapshot construction failure")
    monkeypatch.setattr(module,"_Snapshot",snapshot_failure)
    with pytest.raises(ContractError) as caught:module.prepare_docling_publication(**paths,publication_context={**context,"operation_id":"snapshot-failure"},batch_id="snapshot-failure",vault_root=vault)
    assert caught.value.code=="DOCLING_ARTIFACT_INVALID"
    monkeypatch.setattr(module,"_Snapshot",real_snapshot)
    real_stage=module.stage_publication_request
    for suffix,replacement_bytes in (("same",None),("different",b"different")):
        def swap_after_stage(*, _replacement=replacement_bytes, **kwargs):
            value=real_stage(**kwargs);descriptor=value["request"]["payloads"][0]
            target=checkout/".work"/kwargs["batch_id"]/descriptor["content_file"];replacement=target.with_name("post-stage-replacement")
            replacement.write_bytes(target.read_bytes() if _replacement is None else _replacement);os.replace(replacement,target);return value
        monkeypatch.setattr(module,"stage_publication_request",swap_after_stage)
        with pytest.raises(ContractError) as caught:module.prepare_docling_publication(**paths,publication_context={**context,"operation_id":"post-stage-"+suffix},batch_id="post-stage-"+suffix,vault_root=vault)
        assert caught.value.code=="DOCLING_ARTIFACT_INVALID"
    monkeypatch.setattr(module,"stage_publication_request",real_stage)
    original=module.stage_publication_request
    def changed(**kwargs):
        value=original(**kwargs);source=paths["parser_config"];replacement=source.with_suffix(".new");replacement.write_bytes(source.read_bytes());os.replace(replacement,source);return value
    monkeypatch.setattr(module,"stage_publication_request",changed)
    with pytest.raises(ContractError) as caught:module.prepare_docling_publication(**paths,publication_context={**context,"operation_id":"barrier"},batch_id="barrier",vault_root=vault)
    assert caught.value.code=="DOCLING_ARTIFACT_INVALID"


def test_receipt_audit_accepts_receipt_claimed_code_capture(tmp_path:Path):
    payload=b"code\n";digest=hashlib.sha256(payload).hexdigest();captured=f".raw/captured/{digest}.bin";record=b'{"record":1}'
    _vault_with_files(tmp_path,{"wiki/meta/records/paper.json":record})
    head=json.loads((tmp_path/"wiki/meta/registries/operation-head.json").read_text());previous_raw=(tmp_path/head["receipt_path"]).read_bytes()
    updated=b'{"record":2}';successor={"schema":"video-paper-wiki.operation-receipt.v1","sequence":2,"previous":{"path":head["receipt_path"],"sha256":hashlib.sha256(previous_raw).hexdigest()},"operation_id":"code-capture","operation_type":"generic","intent_sha256":"0"*64,"writes":[{"path":"wiki/meta/records/paper.json","mode":"replace","before_sha256":hashlib.sha256(record).hexdigest(),"after_sha256":hashlib.sha256(updated).hexdigest()}],"claimed_inputs":[{"path":captured,"mode":"read","sha256":digest}]}
    successor["intent_sha256"]=receipt_intent_sha256(successor);raw=canonicalize(successor);path="wiki/meta/operations/000000000002-code-capture.json";_put(tmp_path,captured,payload);_put(tmp_path,"wiki/meta/records/paper.json",updated);_put(tmp_path,path,raw)
    _put(tmp_path,"wiki/meta/registries/operation-head.json",canonicalize({"schema":"video-paper-wiki.operation-head.v1","sequence":2,"receipt_path":path,"receipt_sha256":hashlib.sha256(raw).hexdigest()}))
    assert captured in audit_integrity(tmp_path)["ever_claimed_raw"]
