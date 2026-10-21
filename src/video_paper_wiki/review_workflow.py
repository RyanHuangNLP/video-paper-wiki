"""Receipt-backed deterministic review transitions; decisions are mechanical inputs."""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki import identity
from video_paper_wiki.assessment_history import derive_assessment_heads
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import decode_ledger_evidence
from video_paper_wiki.publication import _prospective, inspect_publication, stage_publication_request
from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
from video_paper_wiki.secure_io import parse_strict_json

DECISION_SCHEMA = "video-paper-wiki.review-decision.v1"
INVALIDATION_SCHEMA = "video-paper-wiki.review-invalidation-request.v1"
AUTHORITY_SCHEMA = "video-paper-wiki.review-transition-authority.v1"
LEDGER = "wiki/meta/ledgers/claim-ledger.json"


def _fail(code: str, message: str, pointer: str = "") -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _claim(record: Mapping[str, Any], paper_id: str, claim_id: str) -> dict[str, Any]:
    try:
        evidence=[decode_ledger_evidence(x) for x in record["evidence"]]
        value={"claim_id":claim_id,"stable_subject_id":"paper:"+paper_id,
            "canonical_claim_text":record["text"],"evidence":evidence,
            "assessment":record["assessment"],"reviewed_at":record.get("reviewed_at")}
        # This also validates claim/text/evidence identities when history is supplied.
        identity.claim_identity_material(value["stable_subject_id"],value["canonical_claim_text"])
        if identity.claim_id(value["stable_subject_id"],value["canonical_claim_text"])!=claim_id:
            _fail("REVIEW_PUBLICATION_INVALID","claim ID differs from its canonical material")
        return value
    except (KeyError, TypeError, ContractError) as exc:
        if isinstance(exc,ContractError): raise
        _fail("REVIEW_PUBLICATION_INVALID","claim ledger record is incomplete")


def _parse_ledger(raw: bytes | dict[str,Any]) -> dict[str, Any]:
    value=copy.deepcopy(raw) if type(raw) is dict else parse_strict_json(raw,invalid_code="REVIEW_PUBLICATION_INVALID")
    if (type(value) is not dict or set(value)!={"schema","generated_at","claims"}
            or value["schema"]!="claude-obsidian.claim-ledger.v1" or type(value["claims"]) is not dict):
        _fail("REVIEW_PUBLICATION_INVALID","claim ledger is not the closed upstream material")
    generated=value["generated_at"]
    if (type(generated) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z",generated) is None):
        _fail("REVIEW_PUBLICATION_INVALID","claim ledger generated_at is not canonical UTC")
    try:datetime.fromisoformat(generated[:-1]+"+00:00")
    except ValueError:_fail("REVIEW_PUBLICATION_INVALID","claim ledger generated_at is not a real UTC timestamp")
    return value


def _owner(snapshot: _Snapshot, claim_id: str, payloads: Mapping[str,bytes]) -> tuple[str,dict[str,Any]]:
    matches=[]
    paths=set(snapshot.inventory or ())
    for path in sorted(x for x in paths if x.startswith("wiki/meta/records/") and x.endswith(".json")):
        try: raw=snapshot.read(path)
        except ContractError: continue
        try: record=validate_document(parse_strict_json(raw,invalid_code="REVIEW_PUBLICATION_INVALID"),"video-paper-wiki.paper-record.v1")
        except ContractError: continue
        if any(x["claim_id"]==claim_id for x in record["section_claim_refs"]): matches.append((path,record))
    if len(matches)!=1:_fail("REVIEW_PUBLICATION_INVALID","claim must have exactly one Paper owner")
    return matches[0]


def _events(snapshot: _Snapshot, claim_id: str) -> tuple[list[dict[str,Any]],dict[str,bytes]]:
    prefix=f"wiki/meta/reviews/{claim_id}/"; values=[]; raw={}
    for path in sorted(x for x in (snapshot.inventory or ()) if x.startswith(prefix) and x.endswith(".json")):
        data=snapshot.read(path); event=validate_document(parse_strict_json(data,invalid_code="REVIEW_PUBLICATION_INVALID"),"video-paper-wiki.assessment-event.v1")
        if canonicalize(event)!=data or event["claim_id"]!=claim_id:_fail("REVIEW_PUBLICATION_INVALID","review event bytes or owner differ")
        expected=f"{prefix}{event['event_id']}.json"
        if path!=expected:_fail("REVIEW_PUBLICATION_INVALID","review event path differs from event identity")
        values.append(event);raw[path]=data
    return values,raw


def _event(claim: Mapping[str,Any], previous: Mapping[str,Any], *, actor: str,
           transition: str, target: str, decided_by: str, decided_at: str, reason: str) -> dict[str,Any]:
    value={"schema":"video-paper-wiki.assessment-event.v1","event_id":"ase-"+"0"*20,
        "claim_id":claim["claim_id"],"previous_event_id":previous["event_id"],
        "actor_kind":actor,"transition_kind":transition,"from_assessment":previous["to_assessment"],
        "to_assessment":target,"claim_text_sha256":hashlib.sha256(claim["canonical_claim_text"].encode()).hexdigest(),
        "evidence_fingerprint":identity.evidence_fingerprint(claim["evidence"]),"decided_by":decided_by,
        "decided_at":decided_at,"reason":reason}
    value["event_id"]=identity.assessment_event_id(value)
    return validate_document(value,"video-paper-wiki.assessment-event.v1")


def _context(value: object) -> tuple[str,dict[str,bytes],list[str],list[dict[str,str]]]:
    if type(value) is not dict or set(value)!={"operation_id","payloads","claimed_input_paths","prospective_groups"}:
        _fail("REVIEW_PUBLICATION_INVALID","publication context must be exact")
    if type(value["payloads"]) is not dict or any(type(k) is not str or type(v) is not bytes for k,v in value["payloads"].items()):
        _fail("REVIEW_PUBLICATION_INVALID","publication payloads must be exact bytes")
    return value["operation_id"],dict(value["payloads"]),list(value["claimed_input_paths"]),[dict(x) for x in value["prospective_groups"]]


def _load(vault_root: Path|str, context: object, claim_id: str):
    operation,payloads,claimed,groups=_context(context)
    if LEDGER not in payloads:_fail("REVIEW_PUBLICATION_INVALID","complete prospective claim ledger slot is required")
    snapshot=_Snapshot(Path(vault_root))
    try:
        audit_integrity(vault_root,_snapshot=snapshot)
        current=_parse_ledger(snapshot.read(LEDGER));future=_parse_ledger(payloads[LEDGER])
        if claim_id not in current["claims"] or claim_id not in future["claims"]:_fail("REVIEW_PUBLICATION_INVALID","selected claim is absent from a complete ledger")
        _path,paper=_owner(snapshot,claim_id,payloads);events,event_bytes=_events(snapshot,claim_id)
        old=_claim(current["claims"][claim_id],paper["paper_id"],claim_id)
        new=_claim(future["claims"][claim_id],paper["paper_id"],claim_id)
        heads=derive_assessment_heads(claims=[old],events=events)
        head=next(x for x in events if x["event_id"]==heads[claim_id])
        return snapshot,operation,payloads,claimed,groups,current,future,paper,old,new,events,event_bytes,head
    except BaseException:
        snapshot.verify();snapshot.close();raise


def _authority(value: dict[str,Any]) -> dict[str,Any]:
    doc=validate_document(value,AUTHORITY_SCHEMA);events=doc["events"];claims=doc["generated_claims"]
    if len(events)!=len(claims) or doc["claim"]!=claims[0]:_fail("REVIEW_PUBLICATION_INVALID","generated events and claims differ")
    ledger=_parse_ledger(doc["claim_ledger"])
    if not events or any(event["decided_at"]!=ledger["generated_at"] for event in events):
        _fail("REVIEW_PUBLICATION_INVALID","claim ledger generated_at differs from terminal event time")
    expected_transition=doc["transition_kind"]
    ledger_claims=ledger["claims"]
    expected_paths=[]
    for index,(event,claim) in enumerate(zip(events,claims)):
        if event["claim_id"]!=claim["claim_id"] or event["transition_kind"]!=expected_transition:_fail("REVIEW_PUBLICATION_INVALID","generated event owner or transition differs")
        record=ledger_claims.get(claim["claim_id"])
        try: ledger_evidence=[decode_ledger_evidence(x) for x in record["evidence"]]
        except (TypeError,KeyError,ContractError):_fail("REVIEW_PUBLICATION_INVALID","generated claim is absent from complete ledger")
        if (record["text"]!=claim["canonical_claim_text"] or record["assessment"]!=claim["assessment"]
                or record.get("reviewed_at")!=claim["reviewed_at"] or ledger_evidence!=claim["evidence"]):
            _fail("REVIEW_PUBLICATION_INVALID","generated claim differs from complete ledger")
        material=copy.deepcopy(event);material["event_id"]="ase-"+"0"*20
        if (identity.assessment_event_id(material)!=event["event_id"]
                or event["claim_text_sha256"]!=hashlib.sha256(claim["canonical_claim_text"].encode()).hexdigest()
                or event["evidence_fingerprint"]!=identity.evidence_fingerprint(claim["evidence"])
                or event["to_assessment"]!=claim["assessment"]
                or claim["reviewed_at"]!=(event["decided_at"][:10] if event["actor_kind"]=="human" else None)):
            _fail("REVIEW_PUBLICATION_INVALID","generated event identity or terminal material differs",f"/events/{index}")
        expected_paths.append(f"wiki/meta/reviews/{event['claim_id']}/{event['event_id']}.json")
    if doc["event_paths"]!=expected_paths:_fail("REVIEW_PUBLICATION_INVALID","event paths differ from event identities")
    request=doc["publication_request"];raw=canonicalize(request["request"])
    if hashlib.sha256(raw).hexdigest()!=request["request_sha256"] or doc["request_sha256"]!=request["request_sha256"]:_fail("REVIEW_PUBLICATION_INVALID","staged request hash differs")
    descriptors={x["path"]:(x["sha256"],x["size_bytes"]) for x in request["request"]["payloads"]};expected={LEDGER:canonicalize(doc["claim_ledger"])}
    expected.update({path:canonicalize(event) for path,event in zip(doc["event_paths"],events)})
    for path,data in expected.items():
        if descriptors.get(path)!=(hashlib.sha256(data).hexdigest(),len(data)):_fail("REVIEW_PUBLICATION_INVALID","staged review material differs",path)
    return copy.deepcopy(doc)


def validate_review_transition_authority(value: object) -> dict[str,Any]: return _authority(value)


def _finish(*, snapshot:_Snapshot, operation:str, payloads:dict[str,bytes], claimed:list[str], groups:list[dict[str,str]],
            batch_id:object, transition:str, claim:dict[str,Any], generated:list[dict[str,Any]], generated_claims:list[dict[str,Any]], ledger:dict[str,Any]) -> dict[str,Any]:
    event_paths=[]
    for event in generated:
        path=f"wiki/meta/reviews/{event['claim_id']}/{event['event_id']}.json";event_paths.append(path);payloads[path]=canonicalize(event)
    payloads[LEDGER]=canonicalize(ledger)
    try:
        decoded={path:parse_strict_json(data,invalid_code="REVIEW_PUBLICATION_INVALID") for path,data in payloads.items() if path.endswith(".json")}
        owner_path,paper=_owner(snapshot,claim["claim_id"],payloads)
        selected=[]
        for index,group in enumerate(groups):
            path=group.get("paper_record")
            if path is not None and decoded.get(path)==paper:selected.append((index,group))
        if len(selected)!=1:_fail("REVIEW_PUBLICATION_INVALID","exactly one retained owner Paper compiler group is required")
        index,selected_group=selected[0]
        if set(selected_group)!={"group_id","paper_record","claims","events"}:_fail("REVIEW_PUBLICATION_INVALID","selected Paper compiler group is incomplete")
        try:group_claims=decoded[selected_group["claims"]];group_events=decoded[selected_group["events"]]
        except KeyError:_fail("REVIEW_PUBLICATION_INVALID","selected Paper compiler material is missing")
        expected_claims=[];expected_events=[]
        for ref in paper["section_claim_refs"]:
            claim_id=ref["claim_id"]
            if claim_id not in ledger["claims"]:_fail("REVIEW_PUBLICATION_INVALID","future ledger omits an owner claim")
            expected_claims.append(_claim(ledger["claims"][claim_id],paper["paper_id"],claim_id))
            retained,_raw=_events(snapshot,claim_id);expected_events.extend(retained)
        expected_events.extend(generated)
        if (type(group_claims) is not list or type(group_events) is not list
                or sorted(group_claims,key=lambda x:x.get("claim_id","") if isinstance(x,dict) else "")!=sorted(expected_claims,key=lambda x:x["claim_id"])
                or sorted(group_events,key=lambda x:x.get("event_id","") if isinstance(x,dict) else "")!=sorted(expected_events,key=lambda x:x["event_id"])):
            _fail("REVIEW_PUBLICATION_INVALID","selected Paper claims or complete event history differs")
        try:_prospective({"operation_id":operation,"prospective_groups":groups},decoded,payloads,snapshot)
        except ContractError as exc:raise ContractError("REVIEW_PUBLICATION_INVALID",exc.message,{**exc.details,"group":index}) from exc
        staged=stage_publication_request(batch_id=batch_id,operation_id=operation,operation_type="generic",payloads=payloads,
            claimed_input_paths=sorted(set(claimed)-set(payloads)),prospective_groups=groups)
        value={"schema":AUTHORITY_SCHEMA,"transition_kind":transition,"claim":claim,"generated_claims":generated_claims,"events":generated,
            "claim_ledger":ledger,"event_paths":event_paths,"request_sha256":staged["request_sha256"],"publication_request":staged}
        snapshot.verify();return _authority(value)
    except BaseException:
        snapshot.verify();raise


def prepare_review_transition(*, decision: object, publication_context: object, batch_id: object,
                              vault_root: Path|str) -> dict[str,Any]:
    request=validate_document(decision,DECISION_SCHEMA);claim_id=request["claim_id"]
    loaded=_load(vault_root,publication_context,claim_id);snapshot,operation,payloads,claimed,groups,current,future,paper,old,new,events,event_bytes,head=loaded
    try:
        if future["generated_at"]!=request["decided_at"]:_fail("REVIEW_PUBLICATION_INVALID","future ledger generated_at differs from decision time")
        if request["expected_previous_event_id"]!=head["event_id"]:_fail("REVIEW_DECISION_INVALID","review head expectation is stale")
        if any(x["actor_kind"]=="human" for x in events): first=False
        else:first=True
        expected=copy.deepcopy(current); expected["generated_at"]=future["generated_at"]
        expected_record=copy.deepcopy(current["claims"][claim_id]);expected_record["assessment"]=request["assessment"];expected_record["reviewed_at"]=request["decided_at"][:10]
        expected["claims"][claim_id]=expected_record
        event=_event(new,head,actor="human",transition="human_assessment",target=request["assessment"],decided_by=request["decided_by"],decided_at=request["decided_at"],reason=request["reason"])
        generated=[event];generated_claims=[new]
        # A direct predecessor is derived solely from the current ledger edge and same Paper refs.
        predecessor=current["claims"][claim_id].get("supersedes")
        if first and predecessor is not None:
            refs={x["claim_id"]:x for x in paper["section_claim_refs"]}
            if claim_id not in refs or predecessor not in refs or not (refs[claim_id]["core"] and refs[claim_id]["lifecycle"]=="active" and refs[predecessor]["core"] and refs[predecessor]["lifecycle"]=="retired"):
                _fail("REVIEW_PUBLICATION_INVALID","direct predecessor is not the same Paper active/retired core edge")
            pred_events,_=_events(snapshot,predecessor);pred_old=_claim(current["claims"][predecessor],paper["paper_id"],predecessor)
            pred_head_id=derive_assessment_heads(claims=[pred_old],events=pred_events)[predecessor];pred_head=next(x for x in pred_events if x["event_id"]==pred_head_id)
            if pred_old["assessment"]!="deprecated":
                pred_record=copy.deepcopy(current["claims"][predecessor]);pred_record["assessment"]="deprecated";pred_record["reviewed_at"]=request["decided_at"][:10];expected["claims"][predecessor]=pred_record
                pred_new=_claim(pred_record,paper["paper_id"],predecessor)
                generated.append(_event(pred_new,pred_head,actor="human",transition="human_assessment",target="deprecated",decided_by=request["decided_by"],decided_at=request["decided_at"],reason="Direct predecessor deprecated: "+request["reason"]));generated_claims.append(pred_new)
        if future!=expected:_fail("REVIEW_PUBLICATION_INVALID","prospective claim ledger is not the exact derived materialization")
        result=_finish(snapshot=snapshot,operation=operation,payloads=payloads,claimed=claimed,groups=groups,batch_id=batch_id,transition="human_assessment",claim=new,generated=generated,generated_claims=generated_claims,ledger=future)
        snapshot.close();snapshot=None;return result
    except BaseException:
        if snapshot is not None:snapshot.verify();snapshot.close()
        raise


def prepare_evidence_invalidation(*, request: object, publication_context: object, batch_id: object,
                                  vault_root: Path|str) -> dict[str,Any]:
    req=validate_document(request,INVALIDATION_SCHEMA);claim_id=req["claim_id"]
    loaded=_load(vault_root,publication_context,claim_id);snapshot,operation,payloads,claimed,groups,current,future,paper,old,new,events,_raw,head=loaded
    try:
        if future["generated_at"]!=req["decided_at"]:_fail("REVIEW_PUBLICATION_INVALID","future ledger generated_at differs from invalidation time")
        old_fp=identity.evidence_fingerprint(old["evidence"]);new_fp=identity.evidence_fingerprint(new["evidence"])
        if (req["expected_previous_event_id"]!=head["event_id"] or req["expected_old_evidence_fingerprint"]!=old_fp
                or req["expected_new_claim_sha256"]!=hashlib.sha256(canonicalize(new)).hexdigest()):_fail("REVIEW_PUBLICATION_INVALID","invalidation expectation differs")
        if old["claim_id"]!=new["claim_id"] or old_fp==new_fp or new["assessment"]!="provisional" or new["reviewed_at"] is not None:
            _fail("REVIEW_PUBLICATION_INVALID","invalidation requires exact changed evidence and provisional materialization")
        expected=copy.deepcopy(current);expected["generated_at"]=future["generated_at"];expected["claims"][claim_id]=future["claims"][claim_id]
        if expected!=future:_fail("REVIEW_PUBLICATION_INVALID","invalidation changed unrelated ledger material")
        event=_event(new,head,actor="system",transition="evidence_invalidation",target="provisional",decided_by="video-paper-wiki",decided_at=req["decided_at"],reason=req["reason"])
        result=_finish(snapshot=snapshot,operation=operation,payloads=payloads,claimed=claimed,groups=groups,batch_id=batch_id,transition="evidence_invalidation",claim=new,generated=[event],generated_claims=[new],ledger=future)
        snapshot.close();snapshot=None;return result
    except BaseException:
        if snapshot is not None:snapshot.verify();snapshot.close()
        raise


def inspect_review_publication(**kwargs: object) -> dict[str,Any]: return inspect_publication(**kwargs)

def _command_context(value:dict[str,Any])->dict[str,Any]:
    from video_paper_wiki.secure_io import read_regular_file
    context=dict(value);files=context.pop("payload_files",{})
    context["payloads"]={path:read_regular_file(Path(source),missing_code="REVIEW_PUBLICATION_INVALID",unsafe_code="REVIEW_PUBLICATION_INVALID",changed_code="REVIEW_PUBLICATION_INVALID",max_bytes=67108864,limit_code="REVIEW_PUBLICATION_INVALID") for path,source in files.items()}
    return context

def run_review_prepare_command(args:object)->int:
    from video_paper_wiki.domain_cli import _json
    from video_paper_wiki.envelope import emit_error,emit_success
    try:
        state=_json(args.state);result=prepare_review_transition(decision=_json(args.decision),publication_context=_command_context(state["publication_context"]),batch_id=args.batch_id,vault_root=args.vault_root)
        return emit_success("review.prepare",result)
    except Exception as exc:return emit_error("review.prepare",getattr(exc,"code","REVIEW_FAILED"),getattr(exc,"message",str(exc)),getattr(exc,"details",{}),exit_code=getattr(exc,"exit_code",2))

def run_review_invalidate_command(args:object)->int:
    from video_paper_wiki.domain_cli import _json
    from video_paper_wiki.envelope import emit_error,emit_success
    try:
        state=_json(args.state);result=prepare_evidence_invalidation(request=_json(args.change),publication_context=_command_context(state["publication_context"]),batch_id=args.batch_id,vault_root=args.vault_root)
        return emit_success("review.invalidate",result)
    except Exception as exc:return emit_error("review.invalidate",getattr(exc,"code","REVIEW_FAILED"),getattr(exc,"message",str(exc)),getattr(exc,"details",{}),exit_code=getattr(exc,"exit_code",2))
