"""Package retained, already-produced Docling artifacts without executing Docling."""
from __future__ import annotations
import copy,hashlib,os,re,stat
from pathlib import Path
from typing import Any,Mapping
from video_paper_wiki.contracts import ContractError,DOCLING_CORE_VERSION,DOCLING_VERSION,validate_document
from video_paper_wiki.identity import pipeline_fingerprint
from video_paper_wiki.projection_runtime import parse_projection_json
from video_paper_wiki.publication import _verify_retained_publication_input,stage_publication_request
from video_paper_wiki.receipt_audit import _Snapshot,audit_integrity
from video_paper_wiki.secure_io import read_regular_file,stamp
SCHEMA="video-paper-wiki.docling-artifact-set.v1";MIGRATION_SCHEMA="video-paper-wiki.locator-migration-proposal.v1";MAX=64*1024*1024
KINDS=("document_json","model_manifest","parser_config","run_manifest")

def _fail(code,message,pointer=""):raise ContractError(code,message,{"instance_pointer":pointer})

def _strict_file(path:Path)->tuple[bytes,os.stat_result]:
    try:first=path.lstat();raw=read_regular_file(path,missing_code="DOCLING_ARTIFACT_INVALID",unsafe_code="DOCLING_ARTIFACT_INVALID",changed_code="DOCLING_ARTIFACT_INVALID",max_bytes=MAX,limit_code="DOCLING_ARTIFACT_INVALID");last=path.lstat()
    except ContractError:raise
    except OSError:_fail("DOCLING_ARTIFACT_INVALID","staged artifact is unavailable")
    if stamp(first)!=stamp(last) or not stat.S_ISREG(first.st_mode) or first.st_nlink!=1:_fail("DOCLING_ARTIFACT_INVALID","staged artifact changed")
    return raw,first

def _profiles(bytes_map:Mapping[str,bytes])->tuple[dict[str,Any],str]:
    parsed={kind:parse_projection_json(bytes_map[kind]) for kind in KINDS}
    if any(type(parsed[k]) is not dict for k in KINDS):_fail("DOCLING_ARTIFACT_INVALID","each staged artifact must be an exact JSON object")
    run=validate_document(parsed["run_manifest"],"video-paper-wiki.run-manifest.v1")
    if "receipt_sha256" in run["output_hashes"]:_fail("DOCLING_ARTIFACT_INVALID","run manifest cannot create a receipt hash cycle")
    if run["tool_versions"].get("docling")!=DOCLING_VERSION or run["tool_versions"].get("docling_core")!=DOCLING_CORE_VERSION:_fail("DOCLING_ARTIFACT_INVALID","run versions differ")
    config=hashlib.sha256(bytes_map["parser_config"]).hexdigest();model=hashlib.sha256(bytes_map["model_manifest"]).hexdigest();document=hashlib.sha256(bytes_map["document_json"]).hexdigest()
    if (run["input_hashes"].get("parser_config_sha256")!=config or run["input_hashes"].get("model_manifest_sha256")!=model
            or run["output_hashes"].get("document_json_sha256")!=document):_fail("DOCLING_ARTIFACT_INVALID","run manifest hashes differ from exact staged bytes")
    fp=pipeline_fingerprint({"engine":"docling","engine_version":DOCLING_VERSION,"core_version":DOCLING_CORE_VERSION,"config_sha256":config,"model_manifest_sha256":model})
    if run.get("pipeline_fingerprint")!=fp:_fail("DOCLING_ARTIFACT_INVALID","run fingerprint differs")
    return run,fp

def _destinations(pdf_sha:str,fp:str,run_id:str)->dict[str,str]:
    return {"document_json":f".raw/derived/{pdf_sha}/docling/{fp}/document.json","model_manifest":f".raw/derived/{pdf_sha}/docling/{fp}/model-manifest.json","parser_config":f".raw/derived/{pdf_sha}/docling/{fp}/parser-config.json","run_manifest":f".raw/derived/{pdf_sha}/runs/{run_id}.json"}

def validate_docling_artifact_set(value:object,*,bytes_map:object)->dict[str,Any]:
    doc=validate_document(value,SCHEMA);kinds=tuple(x["kind"] for x in doc["artifacts"])
    if kinds!=KINDS:_fail("DOCLING_ARTIFACT_INVALID","artifact kinds must be the exact sorted unique tuple","/artifacts")
    if type(bytes_map) is not dict or set(bytes_map)!=set(KINDS):_fail("DOCLING_ARTIFACT_INVALID","artifact byte map differs")
    run,fp=_profiles(bytes_map)
    expected_paths=_destinations(doc["captured_pdf_sha256"],fp,run["run_id"])
    for index,item in enumerate(doc["artifacts"]):
        data=bytes_map[item["kind"]]
        if type(data) is not bytes or not 0<len(data)<=MAX or (item["path"],item["sha256"],item["size_bytes"])!=(expected_paths[item["kind"]],hashlib.sha256(data).hexdigest(),len(data)):_fail("DOCLING_ARTIFACT_INVALID","artifact descriptor differs",f"/artifacts/{index}")
    if doc["pipeline_fingerprint"]!=fp:_fail("DOCLING_ARTIFACT_INVALID","pipeline fingerprint differs","/pipeline_fingerprint")
    return copy.deepcopy(doc)

def _vault_relative(vault:Path,path:Path|str)->str:
    if not isinstance(path,(str,Path)):_fail("DOCLING_ARTIFACT_INVALID","captured PDF path is invalid")
    try:
        base=Path(os.path.normpath(os.path.abspath(os.fspath(vault))));target=Path(os.path.normpath(os.path.abspath(os.fspath(path))));relative=target.relative_to(base).as_posix()
    except (OSError,ValueError,TypeError):_fail("DOCLING_ARTIFACT_INVALID","captured PDF must be a Vault-relative captured slot")
    return relative

def prepare_docling_publication(*,captured_pdf:Path|str,document_json:Path|str,parser_config:Path|str,model_manifest:Path|str,run_manifest:Path|str,publication_context:object,batch_id:object,vault_root:Path|str)->dict[str,Any]:
    vault=Path(vault_root);relative=_vault_relative(vault,captured_pdf)
    source_paths={"document_json":Path(document_json),"parser_config":Path(parser_config),"model_manifest":Path(model_manifest),"run_manifest":Path(run_manifest)}
    retained=[];bytes_map={};initial=[];publication_baseline=[]
    try:
        for kind,path in source_paths.items():
            first=path.lstat()
            if not stat.S_ISREG(first.st_mode) or stat.S_ISLNK(first.st_mode) or first.st_nlink!=1:_fail("DOCLING_ARTIFACT_INVALID","staged artifact is unsafe")
            initial.append((kind,path,first))
        for kind,path,first in initial:
            data,observed=_strict_file(path)
            if stamp(observed)!=stamp(first):_fail("DOCLING_ARTIFACT_INVALID","staged artifact changed")
            bytes_map[kind]=data;retained.append((path,first,data))
    except BaseException:
        for _kind,path,first in initial:
            try:_data,now=_strict_file(path)
            except BaseException:raise
            if stamp(now)!=stamp(first):_fail("DOCLING_ARTIFACT_INVALID","staged artifact changed")
        raise
    def verify_sources():
        for path,first,expected in retained:
            current,now=_strict_file(path)
            if stamp(now)!=stamp(first) or current!=expected:_fail("DOCLING_ARTIFACT_INVALID","staged artifact changed")
    verify_sources();snapshot=None
    try:
        snapshot=_Snapshot(vault)
        pdf=snapshot.read(relative,max_bytes=MAX);audit=audit_integrity(vault,_snapshot=snapshot);pdf_sha=hashlib.sha256(pdf).hexdigest()
        if relative!=f".raw/captured/{pdf_sha}.pdf" or relative not in audit["ever_claimed_raw"]:_fail("DOCLING_ARTIFACT_INVALID","captured PDF is not receipt-backed")
        run,fp=_profiles(bytes_map);dest=_destinations(pdf_sha,fp,run["run_id"])
        artifacts=[{"kind":k,"path":dest[k],"sha256":hashlib.sha256(bytes_map[k]).hexdigest(),"size_bytes":len(bytes_map[k])} for k in KINDS]
        value=validate_docling_artifact_set({"schema":SCHEMA,"captured_pdf_sha256":pdf_sha,"engine":"docling","engine_version":DOCLING_VERSION,"core_version":DOCLING_CORE_VERSION,"pipeline_fingerprint":fp,"artifacts":artifacts},bytes_map=bytes_map)
        if type(publication_context) is not dict or set(publication_context)!={"operation_id","claimed_input_paths","prospective_groups"}:_fail("DOCLING_ARTIFACT_INVALID","publication context differs")
        existing={};missing={}
        for kind in KINDS:
            path=dest[kind];prior=snapshot.read_optional(path)
            if prior is None:missing[path]=bytes_map[kind]
            elif prior!=bytes_map[kind]:_fail("NONDETERMINISTIC_EXTRACTION","derived immutable path contains different bytes")
            else:existing[path]=hashlib.sha256(prior).hexdigest()
        snapshot.verify()
        verify_sources()
        if not missing:return {"artifact_set":value,"publication_request":None,"already_packaged":True,"external_gate_satisfied":False}
        staged=stage_publication_request(batch_id=batch_id,operation_id=publication_context["operation_id"],operation_type="ingest",payloads=missing,claimed_input_paths=sorted(set(publication_context["claimed_input_paths"])|{relative}|set(existing)),prospective_groups=list(publication_context["prospective_groups"]),_retained_baseline_sink=publication_baseline.append)
        if len(publication_baseline)!=1:_fail("DOCLING_ARTIFACT_INVALID","publication stager did not retain its installed input")
        _verify_retained_publication_input(publication_baseline[0],code="DOCLING_ARTIFACT_INVALID")
        verify_sources();snapshot.verify();return {"artifact_set":value,"publication_request":staged,"already_packaged":False,"external_gate_satisfied":False}
    except BaseException:
        verify_sources()
        if publication_baseline:_verify_retained_publication_input(publication_baseline[0],code="DOCLING_ARTIFACT_INVALID")
        if snapshot is not None:snapshot.verify()
        raise
    finally:
        if snapshot is not None:snapshot.close()

def propose_locator_migration(*,old_fingerprint:str,new_fingerprint:str,artifact_path:str,artifact_sha256:str,affected_claims:list[Mapping[str,str]])->dict[str,Any]:
    value={"schema":MIGRATION_SCHEMA,"old_fingerprint":old_fingerprint,"new_fingerprint":new_fingerprint,"artifact_path":artifact_path,"artifact_sha256":artifact_sha256,"affected_claims":sorted((dict(x) for x in affected_claims),key=lambda x:x.get("claim_id",""))}
    doc=validate_document(value,MIGRATION_SCHEMA);ids=[]
    for index,item in enumerate(doc["affected_claims"]):
        if item["old_fingerprint"]!=doc["old_fingerprint"] or item["new_fingerprint"]!=doc["new_fingerprint"]:_fail("DOCLING_ARTIFACT_INVALID","migration child fingerprints differ",f"/affected_claims/{index}")
        ids.append(item["claim_id"])
    if ids!=sorted(set(ids)):_fail("DOCLING_ARTIFACT_INVALID","migration claim IDs must be sorted and unique")
    expected=re.fullmatch(r"\.raw/derived/[0-9a-f]{64}/docling/([0-9a-f]{64})/document\.json",artifact_path)
    if expected is None or expected.group(1)!=new_fingerprint:_fail("DOCLING_ARTIFACT_INVALID","migration artifact path differs from new fingerprint")
    return copy.deepcopy(doc)

def run_ingest_package_command(args:object)->int:
    from video_paper_wiki.domain_cli import _json
    from video_paper_wiki.envelope import emit_error,emit_success
    try:
        result=prepare_docling_publication(captured_pdf=args.captured_pdf,document_json=args.document_json,parser_config=args.parser_config,model_manifest=args.model_manifest,run_manifest=args.run_manifest,publication_context=_json(args.request),batch_id=args.batch_id,vault_root=args.vault_root)
        return emit_success("ingest.package",result)
    except Exception as exc:return emit_error("ingest.package",getattr(exc,"code","DOCLING_ARTIFACT_INVALID"),getattr(exc,"message",str(exc)),getattr(exc,"details",{}),exit_code=getattr(exc,"exit_code",2))
