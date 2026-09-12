from __future__ import annotations
import copy,hashlib,json,os
from pathlib import Path
import pytest
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.publication import validate_publication_request
from video_paper_wiki.receipt_audit import audit_integrity
from video_paper_wiki.extraction_artifact import validate_docling_artifact_set,propose_locator_migration
from tests.unit.test_publication_wave import _receipt_vault,_put


def _request(count:int):
    rows=[]
    for i in range(count):
        digest=hashlib.sha256(str(i).encode()).hexdigest();rows.append({"path":f"wiki/meta/records/r{i:04d}.json","content_file":"publication-input/content/"+digest,"sha256":digest,"size_bytes":1})
    return {"schema":"video-paper-wiki.knowledge-publication-request.v1","batch_id":"bounded","operation_id":"bounded","operation_type":"generic","payloads":rows,"claimed_input_paths":[],"additional_read_paths":[],"prospective_groups":[]}


def test_request_preflight_closes_paths_references_and_1022_boundary():
    assert len(validate_publication_request(_request(1022))["payloads"])==1022
    for mutate in (
        lambda x:x["payloads"].append(copy.deepcopy(x["payloads"][0])),
        lambda x:x["payloads"].__setitem__(0,{**x["payloads"][0],"path":"/tmp/escape"}),
        lambda x:x["prospective_groups"].append({"group_id":"g","paper_record":"wiki/meta/records/missing.json"}),
    ):
        value=_request(1);mutate(value)
        with pytest.raises(ContractError):validate_publication_request(value)


def test_audit_late_head_inode_and_lock_override(monkeypatch,tmp_path:Path):
    _receipt_vault(tmp_path)
    import video_paper_wiki.receipt_audit as module
    original=module._inventory_names;called=False
    def changed(snapshot):
        nonlocal called
        names=original(snapshot)
        if not called:
            called=True;target=tmp_path/module.HEAD;data=target.read_bytes();replacement=target.with_name("new-head");replacement.write_bytes(data);replacement.chmod(0o600);os.replace(replacement,target)
        return names
    monkeypatch.setattr(module,"_inventory_names",changed)
    with pytest.raises(ContractError) as caught:audit_integrity(tmp_path)
    assert caught.value.code=="AUDIT_RACE"


def test_audit_extra_receipt_managed_drift_and_orphan(tmp_path:Path):
    _receipt_vault(tmp_path)
    extra=tmp_path/"wiki/meta/operations/000000000099-extra.json";extra.write_bytes(b"{}");extra.chmod(0o600)
    with pytest.raises(ContractError) as caught:audit_integrity(tmp_path)
    assert caught.value.code=="RECEIPT_CHAIN_INVALID"
    extra.unlink();record=tmp_path/"wiki/meta/records/paper.json";record.write_bytes(b"changed")
    with pytest.raises(ContractError) as caught:audit_integrity(tmp_path)
    assert caught.value.code=="OUT_OF_BAND_WRITE"


def test_docling_kind_tuple_receipt_cycle_and_migration_binding():
    data={"document_json":b"{}","model_manifest":b"{}","parser_config":b"{}","run_manifest":b"{}"}
    doc={"schema":"video-paper-wiki.docling-artifact-set.v1","captured_pdf_sha256":"a"*64,"engine":"docling","engine_version":"2.117.0","core_version":"2.92.0","pipeline_fingerprint":"b"*64,"artifacts":[{"kind":"document_json","path":"x","sha256":hashlib.sha256(b"{}").hexdigest(),"size_bytes":2} for _ in range(4)]}
    with pytest.raises(ContractError) as caught:validate_docling_artifact_set(doc,bytes_map=data)
    assert caught.value.code in {"SCHEMA_INVALID","DOCLING_ARTIFACT_INVALID"}
    with pytest.raises(ContractError):propose_locator_migration(old_fingerprint="a"*64,new_fingerprint="b"*64,artifact_path=f".raw/derived/{'c'*64}/docling/{'b'*64}/document.json",artifact_sha256="d"*64,affected_claims=[{"claim_id":"clm-"+"e"*20,"old_fingerprint":"f"*64,"new_fingerprint":"b"*64}])

def test_audit_ignores_explicitly_out_of_scope_user_tree(tmp_path:Path):
    _receipt_vault(tmp_path)
    notes=tmp_path/"wiki/notes";notes.mkdir(parents=True);os.mkfifo(notes/"user.fifo")
    (tmp_path/"wiki/index.md").write_text("user navigation")
    assert audit_integrity(tmp_path)["valid"] is True

def test_projection_payload_requires_canonical_compiler_group(tmp_path:Path):
    from video_paper_wiki.publication import _prospective
    from video_paper_wiki.receipt_audit import _Snapshot
    raw=b"# caller page\n";digest=hashlib.sha256(raw).hexdigest()
    request={"schema":"video-paper-wiki.knowledge-publication-request.v1","batch_id":"projection","operation_id":"projection","operation_type":"generic","payloads":[{"path":"wiki/papers/caller.md","content_file":"publication-input/content/"+digest,"sha256":digest,"size_bytes":len(raw)}],"claimed_input_paths":[],"additional_read_paths":[],"prospective_groups":[]}
    snap=_Snapshot(tmp_path)
    try:
        with pytest.raises(ContractError) as caught:_prospective(validate_publication_request(request),{}, {"wiki/papers/caller.md":raw},snap)
        assert caught.value.code=="PUBLICATION_REQUEST_INVALID"
    finally:snap.close()

def test_request_rejects_unsafe_read_paths_before_vault_access():
    value=_request(1);value["additional_read_paths"]=["../../etc/passwd"]
    with pytest.raises(ContractError) as caught:validate_publication_request(value)
    assert caught.value.code=="PUBLICATION_REQUEST_INVALID"

def test_projection_rejects_partial_paper_and_code_triples(tmp_path:Path):
    from video_paper_wiki.publication import _prospective
    from video_paper_wiki.receipt_audit import _Snapshot
    for role in ("paper_record","code_manifest"):
        raw=b"{}";digest=hashlib.sha256(raw).hexdigest();path=f"wiki/meta/records/{role}.json"
        request=_request(1);request["payloads"][0]={"path":path,"content_file":"publication-input/content/"+digest,"sha256":digest,"size_bytes":2}
        request["prospective_groups"]=[{"group_id":"g",role:path}]
        snap=_Snapshot(tmp_path)
        try:
            with pytest.raises(ContractError):_prospective(validate_publication_request(request),{path:{}},{path:raw},snap)
        finally:snap.close()

def test_publication_input_final_verifier_rejects_same_bytes_new_inode(tmp_path:Path):
    from video_paper_wiki.publication import _input_tree,_verify_input_tree
    checkout=tmp_path;data=b"{}";digest=hashlib.sha256(data).hexdigest()
    request=_request(1);request["batch_id"]="bounded";request["payloads"][0]={"path":"wiki/meta/records/a.json","content_file":"publication-input/content/"+digest,"sha256":digest,"size_bytes":len(data)}
    base=checkout/".work/bounded/publication-input";(base/"content").mkdir(parents=True)
    (base/"knowledge-publication-request.v1.json").write_bytes(canonicalize(request));target=base/"content"/digest;target.write_bytes(data)
    tree=_input_tree(checkout,"bounded",request);replacement=base/"content/replacement";replacement.write_bytes(data);os.replace(replacement,target)
    with pytest.raises(ContractError) as caught:_verify_input_tree(tree,request)
    assert caught.value.code=="PUBLICATION_PATH_UNSAFE"

def test_valid_code_triple_compiles_exactly_once(tmp_path:Path,monkeypatch):
    from video_paper_wiki import canonical_compiler
    from video_paper_wiki.code_evidence_contracts import code_manifest_hash,code_proposal_hash
    from video_paper_wiki.publication import _prospective
    from video_paper_wiki.receipt_audit import _Snapshot
    fixtures=Path(__file__).resolve().parents[1]/"fixtures/contracts/valid"
    manifest=json.loads((fixtures/"video-paper-wiki.code-evidence-manifest.v1.json").read_text())
    repo=json.loads((fixtures/"video-paper-wiki.repo-record.v1.json").read_text());alignment=json.loads((fixtures/"video-paper-wiki.paper-code-alignment.v1.json").read_text())
    manifest["origin"]={"repository":repo["canonical_repository"],"commit":repo["canonical_commit"],"path":"train.py"}
    manifest["proposal_sha256"]=code_proposal_hash(manifest);manifest["state"]="inspected";manifest["capture"]={"stored_path":f".raw/captured/{manifest['payload']['sha256']}.bin","source_identity":manifest["payload"]["sha256"],"source_id":"src-repo","inspection_approval_hash":"a"*64,"operation_id":"capture-code"};manifest["manifest_sha256"]=code_manifest_hash(manifest)
    material={"schema":"video-paper-wiki.compile-input.v1","operation_id":"code-only","papers":[],"code":[{"manifest":manifest,"repo_record":repo,"alignment":alignment}],"concepts":[]};pages=canonical_compiler.compile_pages(material)
    objects={"wiki/meta/records/code-manifest.json":manifest,"wiki/meta/records/repo.json":repo,"wiki/meta/records/alignment.json":alignment}
    payload={path:canonicalize(value) for path,value in objects.items()}|pages
    descriptors=[{"path":path,"content_file":"publication-input/content/"+hashlib.sha256(data).hexdigest(),"sha256":hashlib.sha256(data).hexdigest(),"size_bytes":len(data)} for path,data in sorted(payload.items())]
    request={"schema":"video-paper-wiki.knowledge-publication-request.v1","batch_id":"code-only","operation_id":"code-only","operation_type":"generic","payloads":descriptors,"claimed_input_paths":[],"additional_read_paths":[],"prospective_groups":[{"group_id":"code","code_manifest":"wiki/meta/records/code-manifest.json","repo_record":"wiki/meta/records/repo.json","alignment":"wiki/meta/records/alignment.json"}]}
    calls=0;original=canonical_compiler.compile_pages
    def counted(value):
        nonlocal calls;calls+=1;return original(value)
    monkeypatch.setattr(canonical_compiler,"compile_pages",counted);snap=_Snapshot(tmp_path)
    try:_prospective(validate_publication_request(request),objects,payload,snap)
    finally:snap.close()
    assert calls==1
    bad=copy.deepcopy(objects);bad["wiki/meta/records/code-manifest.json"]["origin"]["commit"]="b"*40
    snap=_Snapshot(tmp_path)
    try:
        with pytest.raises(ContractError):_prospective(validate_publication_request(request),bad,payload,snap)
    finally:snap.close()

def test_paper_projection_derives_taxonomy_and_requires_complete_current_coverage(tmp_path:Path):
    from tests.unit.test_remaining_domain import _compile_material
    from video_paper_wiki.canonical_compiler import compile_pages,concept_items_for_papers
    from video_paper_wiki.publication import _prospective
    from video_paper_wiki.receipt_audit import _Snapshot
    material=_compile_material();paper=material["papers"][0];material["concepts"]=concept_items_for_papers([paper["record"]]);pages=compile_pages(material)
    objects={"wiki/meta/records/paper-input.json":paper["record"],"wiki/meta/records/claims.json":paper["claims"],"wiki/meta/records/events.json":paper["events"]}
    payload={path:canonicalize(value) for path,value in objects.items()}|pages
    descriptors=[{"path":path,"content_file":"publication-input/content/"+hashlib.sha256(data).hexdigest(),"sha256":hashlib.sha256(data).hexdigest(),"size_bytes":len(data)} for path,data in sorted(payload.items())]
    request={"schema":"video-paper-wiki.knowledge-publication-request.v1","batch_id":"paper","operation_id":material["operation_id"],"operation_type":"generic","payloads":descriptors,"claimed_input_paths":[],"additional_read_paths":[],"prospective_groups":[{"group_id":"paper","paper_record":"wiki/meta/records/paper-input.json","claims":"wiki/meta/records/claims.json","events":"wiki/meta/records/events.json"}]}
    snap=_Snapshot(tmp_path)
    try:_prospective(validate_publication_request(request),objects,payload,snap)
    finally:snap.close()
    other=copy.deepcopy(paper["record"]);other["paper_id"]="arxiv:2311.15128";other["section_claim_refs"]=[]
    _put(tmp_path,"wiki/meta/records/other.json",canonicalize(other));snap=_Snapshot(tmp_path)
    from video_paper_wiki.receipt_audit import _inventory_names
    snap.inventory=_inventory_names(snap)
    try:
        with pytest.raises(ContractError) as caught:_prospective(validate_publication_request(request),objects,payload,snap)
        assert caught.value.code=="PUBLICATION_REQUEST_INVALID"
    finally:snap.close()

def test_publication_outer_snapshot_failure_still_rechecks_content(tmp_path:Path,monkeypatch):
    from video_paper_wiki import publication as module
    checkout=tmp_path/"checkout";checkout.mkdir();(checkout/".git").mkdir();(checkout/"pyproject.toml").write_text('[project]\nname="video-paper-wiki"\n');monkeypatch.chdir(checkout)
    staged=module.stage_publication_request(batch_id="outer-race",operation_id="outer-race",operation_type="generic",payloads={"wiki/meta/records/a.json":b"{}"})
    descriptor=staged["request"]["payloads"][0];target=checkout/".work/outer-race"/descriptor["content_file"]
    def fail_snapshot(_root):
        replacement=target.with_name("replacement");replacement.write_bytes(target.read_bytes());os.replace(replacement,target)
        raise ContractError("AUDIT_RACE","synthetic snapshot failure")
    monkeypatch.setattr(module,"_Snapshot",fail_snapshot)
    with pytest.raises(ContractError) as caught:module.inspect_publication(prepared=staged["request_path"],operation_id="outer-race",upstream_root=tmp_path/"upstream",vault_root=tmp_path/"vault")
    assert caught.value.code=="PUBLICATION_PATH_UNSAFE"

def test_duplicate_retained_paper_primary_identity_is_refused(tmp_path:Path):
    from video_paper_wiki.publication import _prospective
    from video_paper_wiki.receipt_audit import _Snapshot,_inventory_names
    record=json.loads((Path(__file__).resolve().parents[1]/"fixtures/contracts/valid/video-paper-wiki.paper-record.v1.json").read_text())
    _put(tmp_path,"wiki/meta/records/a.json",canonicalize(record));_put(tmp_path,"wiki/meta/records/b.json",canonicalize(record))
    snap=_Snapshot(tmp_path);snap.inventory=_inventory_names(snap)
    try:
        with pytest.raises(ContractError) as caught:_prospective({"operation_id":"duplicate","prospective_groups":[]},{},{},snap)
        assert caught.value.code=="PUBLICATION_REQUEST_INVALID"
    finally:snap.close()
