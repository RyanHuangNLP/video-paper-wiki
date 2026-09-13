"""Receipt-backed publication inspection; this module never applies a transaction."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from video_paper_wiki.contracts import ContractError, validate_document, validate_prospective
from video_paper_wiki.identity import receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.receipt_audit import _Snapshot, audit_integrity
from video_paper_wiki.projection_runtime import parse_projection_json
from video_paper_wiki.secure_io import parse_strict_json, read_regular_file, stamp
from video_paper_wiki.staging import (WORK_DIRNAME, _atomic_install, _close_fd, _ensure_dir_at,
    _existing_same_bytes, _open_batch_session, _open_dir_at, _require_exact_staged_file,
    _require_same_directory, resolve_checkout_root, validate_batch_id)
from video_paper_wiki.transaction_contracts import (HEAD_PATH, attach_upstream_inspection,
    transaction_declaration_hash, validate_transaction, verify_transaction_bytes)
from video_paper_wiki.transaction_staging import (MAX_BUNDLE_BYTES, _stage_transaction_inspect_transport,
    encode_transaction_inspect_bundle)
from video_paper_wiki.upstream_adapter import inspect_pinned_transaction

REQUEST_SCHEMA = "video-paper-wiki.knowledge-publication-request.v1"
AUTHORITY_SCHEMA = "video-paper-wiki.publication-authority.v1"
REQUEST_NAME = "knowledge-publication-request.v1.json"
REQUEST_RELATIVE = "publication-input/" + REQUEST_NAME
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DOCLING_DOCUMENT = re.compile(
    r"^\.raw/derived/[0-9a-f]{64}/docling/[0-9a-f]{64}/document\.json$"
)


def _fail(code: str, message: str, pointer: str = "") -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _decode_publication_json(path: str, data: bytes) -> Any:
    """Parse one publication JSON payload.

    Derived Docling ``document.json`` is a float-capable original-document
    artifact. Integer-JCS envelopes (requests, receipts, heads, ledgers) stay
    on ``parse_strict_json``.
    """
    if _DOCLING_DOCUMENT.fullmatch(path):
        return parse_projection_json(data)
    return parse_strict_json(data, invalid_code="SCHEMA_INVALID")


def validate_publication_request(value: object) -> dict[str, Any]:
    return copy.deepcopy(validate_document(value, REQUEST_SCHEMA))


def _check_request(document: Mapping[str, Any]) -> None:
    from video_paper_wiki.transaction_contracts import _business
    slots = document["payloads"]
    if slots != sorted(slots, key=lambda item: item["path"]):
        _fail("PUBLICATION_REQUEST_INVALID", "publication payloads must be sorted", "/payloads")
    paths = [x["path"] for x in slots]
    if len(paths) != len(set(paths)) or len(slots) > 1022:
        _fail("PUBLICATION_REQUEST_INVALID", "publication payload paths must be unique and bounded", "/payloads")
    for index, item in enumerate(slots):
        _business(item["path"],item["sha256"],f"/payloads/{index}/path",operation=document["operation_type"],mode=None)
        if item["content_file"] != "publication-input/content/" + item["sha256"]:
            _fail("PUBLICATION_REQUEST_INVALID", "content slot differs from digest", f"/payloads/{index}/content_file")
    for key in ("claimed_input_paths", "additional_read_paths"):
        if document[key] != sorted(set(document[key])):
            _fail("PUBLICATION_REQUEST_INVALID", "read paths must be sorted and unique", "/" + key)
        for index,path in enumerate(document[key]):
            if (type(path) is not str or path.startswith("/") or "\x00" in path
                    or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/"))
                    or path.startswith(".vault-meta/") or path == HEAD_PATH
                    or path.startswith("wiki/meta/operations/")
                    or not (path.startswith(("wiki/meta/ledgers/", "wiki/meta/records/", "wiki/meta/reviews/",
                                             "wiki/meta/gates/", "wiki/papers/", "wiki/code/", "wiki/concepts/",
                                             ".raw/captured/", ".raw/derived/"))
                            or path == "wiki/meta/registries/gate-heads.json")):
                _fail("PUBLICATION_REQUEST_INVALID", "read path is outside publication authority", f"/{key}/{index}")
    if set(document["claimed_input_paths"]) & set(paths):
        _fail("PUBLICATION_REQUEST_INVALID", "claimed inputs cannot also be writes", "/claimed_input_paths")
    available=set(paths)|set(document["claimed_input_paths"])|set(document["additional_read_paths"])
    seen_groups=set()
    for index,group in enumerate(document["prospective_groups"]):
        if group["group_id"] in seen_groups:_fail("PUBLICATION_REQUEST_INVALID","prospective group IDs must be unique",f"/prospective_groups/{index}/group_id")
        seen_groups.add(group["group_id"])
        for role,path in group.items():
            if role=="group_id":continue
            if path not in available:_fail("PUBLICATION_REQUEST_INVALID","prospective reference is dangling",f"/prospective_groups/{index}/{role}")
            if type(path) is not str or not path.endswith(".json") or path.startswith("/") or "\x00" in path or any(x in {"",".",".."} for x in path.split("/")):
                _fail("PUBLICATION_REQUEST_INVALID","prospective path is unsafe or not JSON",f"/prospective_groups/{index}/{role}")


def validate_publication_authority(value: object) -> dict[str, Any]:
    return copy.deepcopy(validate_document(value, AUTHORITY_SCHEMA))


def _check_authority(document: Mapping[str, Any]) -> None:
    request = validate_publication_request(document["request"])
    tx = validate_transaction(document["transaction"])
    from video_paper_wiki.transaction_staging import validate_transaction_staging
    from video_paper_wiki.upstream_adapter import validate_upstream_authority
    staging=validate_transaction_staging(document["transaction_staging"])
    upstream=validate_upstream_authority(document["upstream_authority"])
    business = tx["writes"][:-2]
    request_writes = [{"path": item["path"], "sha256": item["sha256"], "size_bytes": item["size_bytes"]}
                      for item in request["payloads"]]
    projected_writes = [{"path": item["path"], "sha256": item["sha256"], "size_bytes": item["size_bytes"]}
                        for item in business]
    if (document["request_sha256"] != hashlib.sha256(canonicalize(request)).hexdigest()
            or tx["phase"] != "inspected" or tx["operation_id"] != request["operation_id"]
            or tx["operation_type"] != request["operation_type"]
            or request_writes != projected_writes
            or request["claimed_input_paths"] != [item["path"] for item in tx["claimed_inputs"]]
            or document["request_sha256"]!=hashlib.sha256(canonicalize(request)).hexdigest()
            or upstream["transaction"] != tx
            or staging["batch_id"]!=request["batch_id"]
            or staging["operation_id"]!=tx["operation_id"] or staging["operation_type"]!=tx["operation_type"]
            or staging["bundle_sha256"] != tx["input_bundle_sha256"]
            or upstream["transport"]["bundle_sha256"]!=tx["input_bundle_sha256"]):
        _fail("PUBLICATION_RESULT_MISMATCH", "publication authority children differ")


def _request_path(prepared: Path | str, checkout: Path) -> tuple[Path, str]:
    if not isinstance(prepared, (str, Path)):
        _fail("PUBLICATION_PATH_UNSAFE", "prepared request path is invalid")
    try:
        target = Path(os.path.normpath(os.path.abspath(os.fspath(prepared))))
        relative = target.relative_to(checkout / WORK_DIRNAME)
    except (OSError, TypeError, ValueError, UnicodeError):
        _fail("PUBLICATION_PATH_UNSAFE", "prepared request path is invalid")
    if len(relative.parts) != 3 or relative.parts[1:] != ("publication-input", REQUEST_NAME):
        _fail("PUBLICATION_PATH_UNSAFE", "prepared request does not use the fixed layout")
    return target, validate_batch_id(relative.parts[0])


def stage_publication_request(*, batch_id: object, operation_id: object, operation_type: str,
                              payloads: Mapping[str, bytes], claimed_input_paths: list[str] | None = None,
                              additional_read_paths: list[str] | None = None,
                              prospective_groups: list[Mapping[str, str]] | None = None,
                              _retained_baseline_sink: Any = None) -> dict[str, Any]:
    """Stage exact content first and the closed request last under `.work/**`."""
    from video_paper_wiki.source_state import require_legacy_profile
    if not isinstance(payloads, Mapping) or any(type(path) is not str or type(data) is not bytes for path, data in payloads.items()):
        _fail("PUBLICATION_REQUEST_INVALID", "payload map must contain string-to-bytes entries")
    require_legacy_profile(payloads)
    batch = validate_batch_id(batch_id)
    if type(operation_id) is not str or _ID.fullmatch(operation_id) is None or type(operation_type) is not str or operation_type not in {"generic", "ingest"}:
        _fail("PUBLICATION_REQUEST_INVALID", "invalid publication identity")
    descriptors = []; ordered: list[tuple[str, bytes]]=[]
    for path, data in sorted(payloads.items()):
        if type(path) is not str or type(data) is not bytes:
            _fail("PUBLICATION_REQUEST_INVALID", "payload map must contain string-to-bytes entries")
        digest = hashlib.sha256(data).hexdigest()
        ordered.append((digest,data))
        descriptors.append({"path": path, "content_file": "publication-input/content/" + digest,
                            "sha256": digest, "size_bytes": len(data)})
    request = {"schema": REQUEST_SCHEMA, "batch_id": batch, "operation_id": operation_id,
               "operation_type": operation_type, "payloads": descriptors,
               "claimed_input_paths": sorted(claimed_input_paths or []),
               "additional_read_paths": sorted(additional_read_paths or []),
               "prospective_groups": [dict(x) for x in (prospective_groups or [])]}
    request = validate_publication_request(request)
    raw = canonicalize(request)
    with _open_batch_session(batch,create=True) as session:
        base=session.batch_path/"publication-input";content=base/"content";held=[]
        try:
            bfd=_ensure_dir_at(session.batch_fd,"publication-input",base,work_fd=session.work_fd);held.append(bfd)
            cfd=_ensure_dir_at(bfd,"content",content,work_fd=session.work_fd);held.append(cfd)
            bst,cst=os.fstat(bfd),os.fstat(cfd)
            def verify():
                session.verify();_require_same_directory(bfd,bst,base);_require_same_directory(cfd,cst,content)
                named=_open_dir_at(session.batch_fd,"publication-input",base)
                try:
                    _require_same_directory(named,bst,base);namedc=_open_dir_at(named,"content",content)
                    try:_require_same_directory(namedc,cst,content)
                    finally:_close_fd(namedc)
                finally:_close_fd(named)
            verify()
            for digest,data in sorted(set(ordered)):
                target=content/digest
                if not _existing_same_bytes(cfd,digest,data,target):_atomic_install(session.work_fd,cfd,digest,data,target=target,checkout_fd=session.checkout_fd)
                _require_exact_staged_file(cfd,digest,data,target);verify()
            target=base/REQUEST_NAME
            if not _existing_same_bytes(bfd,REQUEST_NAME,raw,target):_atomic_install(session.work_fd,bfd,REQUEST_NAME,raw,target=target,checkout_fd=session.checkout_fd)
            _require_exact_staged_file(bfd,REQUEST_NAME,raw,target);verify()
            if sorted(x.name for x in os.scandir(bfd))!=sorted(["content",REQUEST_NAME]) or sorted(x.name for x in os.scandir(cfd))!=sorted({d for d,_ in ordered}):_fail("PUBLICATION_PATH_UNSAFE","publication input complete set differs")
            if _retained_baseline_sink is not None:
                if not callable(_retained_baseline_sink):_fail("PUBLICATION_REQUEST_INVALID","retained baseline sink is invalid")
                request_raw,request_stat=_read_stable(target,"PUBLICATION_PATH_UNSAFE",1024*1024)
                tree=_input_tree(session.checkout,batch,request)
                _retained_baseline_sink((target,request_raw,request_stat,tree,request))
        except BaseException:
            if 'verify' in locals():verify()
            raise
        finally:
            for fd in reversed(held):_close_fd(fd)
    return {"schema": REQUEST_SCHEMA, "batch_id": batch, "request_path": target.as_posix(),
            "request_sha256": hashlib.sha256(raw).hexdigest(), "request": request}


def _verify_retained_publication_input(baseline: object, *, code: str = "PUBLICATION_PATH_UNSAFE") -> None:
    try:
        target,raw,first,tree,request=baseline
        current,now=_read_stable(target,"PUBLICATION_PATH_UNSAFE",1024*1024)
        if current!=raw or stamp(now)!=stamp(first):_fail("PUBLICATION_PATH_UNSAFE","publication request changed")
        _verify_input_tree(tree,request)
    except ContractError as exc:
        if code==exc.code:raise
        raise ContractError(code,"staged publication input changed",{}) from exc
    except Exception as exc:
        raise ContractError(code,"staged publication input changed",{}) from exc


def _read_stable(path: Path, code: str, max_bytes: int = 64 * 1024 * 1024) -> tuple[bytes, os.stat_result]:
    try:
        first = path.lstat()
        raw = read_regular_file(path, missing_code=code, unsafe_code=code, changed_code=code,
                                max_bytes=max_bytes, limit_code="TRANSACTION_LIMIT_EXCEEDED")
        now = path.lstat()
    except ContractError:
        raise
    except Exception:
        _fail(code, "publication input changed")
    if stamp(first) != stamp(now) or not stat.S_ISREG(first.st_mode) or first.st_nlink != 1:
        _fail(code, "publication input changed")
    return raw, first


def _existing_bindings(snapshot: _Snapshot) -> tuple[dict[str,str],dict[str,tuple[str,str]],dict[str,dict[str,Any]]]:
    papers={};owners={};records={}
    for path in sorted(x for x in (snapshot.inventory or ()) if x.startswith("wiki/meta/records/") and x.endswith(".json")):
        try:record=validate_document(parse_strict_json(snapshot.read(path),invalid_code="SCHEMA_INVALID"),"video-paper-wiki.paper-record.v1")
        except ContractError:continue
        extraction=record["active_extraction_path"].split("/")
        if len(extraction)<4:_fail("PUBLICATION_REQUEST_INVALID","current Paper extraction path is malformed")
        paper_id=record["paper_id"];pdf_sha=extraction[2]
        if paper_id in papers and papers[paper_id]!=pdf_sha:_fail("PUBLICATION_REQUEST_INVALID","current Paper identity is ambiguous")
        papers[paper_id]=pdf_sha
        if paper_id in records:_fail("PUBLICATION_REQUEST_INVALID","current Paper primary identity is duplicated")
        records[paper_id]=record
        for ref in record["section_claim_refs"]:
            prior=owners.get(ref["claim_id"])
            if prior is not None and prior!=paper_id:_fail("PUBLICATION_REQUEST_INVALID","current claim owner is ambiguous")
            owners[ref["claim_id"]]=paper_id
    claims={};raw=snapshot.read_optional("wiki/meta/ledgers/claim-ledger.json")
    if raw is not None:
        ledger=parse_strict_json(raw,invalid_code="SCHEMA_INVALID")
        if type(ledger) is not dict or type(ledger.get("claims")) is not dict:_fail("PUBLICATION_REQUEST_INVALID","current claim ledger is malformed")
        for claim_id,record in ledger["claims"].items():
            owner=owners.get(claim_id)
            if owner is None:continue
            if type(record) is not dict or type(record.get("text")) is not str:_fail("PUBLICATION_REQUEST_INVALID","current claim material is malformed")
            claims[claim_id]=(f"paper:{owner}",record["text"])
    return papers,claims,records


def _prospective(request: Mapping[str,Any],decoded: Mapping[str,Any],payload_bytes:Mapping[str,bytes],snapshot:_Snapshot) -> None:
    from video_paper_wiki.canonical_compiler import compile_pages,concept_items_for_papers
    from video_paper_wiki.code_evidence_contracts import validate_code_evidence_manifest
    paper_bindings,claim_bindings,current_records=_existing_bindings(snapshot)
    paper_items=[];code_items=[];paper_ids=set();repo_ids=set();prospective_records=dict(current_records)
    for index,group in enumerate(request["prospective_groups"]):
        try:bundle={key:decoded[path] for key,path in group.items() if key!="group_id"}
        except KeyError:_fail("PUBLICATION_REQUEST_INVALID","prospective reference has no parsed byte authority",f"/prospective_groups/{index}")
        try:validate_prospective(bundle,existing_paper_bindings=paper_bindings,existing_claim_bindings=claim_bindings)
        except ContractError as exc:raise ContractError(exc.code,exc.message,{**exc.details,"group":index}) from exc
        paper_roles={"paper_record","claims","events"};code_roles={"code_manifest","repo_record","alignment"}
        if set(bundle)&paper_roles and not paper_roles<=set(bundle):_fail("PUBLICATION_REQUEST_INVALID","Paper compiler triple is incomplete",f"/prospective_groups/{index}")
        if set(bundle)&code_roles and not code_roles<=set(bundle):_fail("PUBLICATION_REQUEST_INVALID","Code compiler triple is incomplete",f"/prospective_groups/{index}")
        if paper_roles<=set(bundle):
            record=validate_document(bundle["paper_record"],"video-paper-wiki.paper-record.v1");paper_id=record["paper_id"]
            if paper_id in paper_ids:_fail("PUBLICATION_REQUEST_INVALID","duplicate Paper compiler identity",f"/prospective_groups/{index}")
            paper_ids.add(paper_id);prospective_records[paper_id]=record
            paper_items.append({"record":record,"claims":bundle["claims"],"events":bundle["events"]})
        if code_roles<=set(bundle):
            manifest=validate_code_evidence_manifest(bundle["code_manifest"])
            repo=validate_document(bundle["repo_record"],"video-paper-wiki.repo-record.v1");repo_id=repo["repo_id"]
            if repo_id in repo_ids:_fail("PUBLICATION_REQUEST_INVALID","duplicate Code compiler identity",f"/prospective_groups/{index}")
            repo_ids.add(repo_id);code_items.append({"manifest":manifest,"repo_record":repo,"alignment":bundle["alignment"]})
    actual={path:data for path,data in payload_bytes.items() if path.startswith(("wiki/papers/","wiki/code/","wiki/concepts/"))}
    paper_or_concept=any(path.startswith(("wiki/papers/","wiki/concepts/")) for path in actual) or bool(paper_items)
    if paper_or_concept and paper_ids!=set(prospective_records):
        _fail("PUBLICATION_REQUEST_INVALID","Paper compiler triples do not cover the complete prospective Paper set")
    concepts=concept_items_for_papers([item["record"] for item in paper_items]) if paper_or_concept else []
    compiled=compile_pages({"schema":"video-paper-wiki.compile-input.v1","operation_id":request["operation_id"],
                            "papers":sorted(paper_items,key=lambda x:x["record"]["paper_id"]),
                            "code":sorted(code_items,key=lambda x:x["repo_record"]["repo_id"]),"concepts":concepts})
    if actual!=compiled:_fail("PUBLICATION_REQUEST_INVALID","projection payload complete set differs from canonical compiler output")


def _input_tree(checkout: Path, batch: str, request: Mapping[str, Any]) -> tuple[Path, os.stat_result, Path, os.stat_result, dict[str,tuple[os.stat_result,str,int]]]:
    base = checkout / WORK_DIRNAME / batch / "publication-input"; content = base / "content"
    try:
        base_st = base.lstat(); content_st = content.lstat()
        if (not stat.S_ISDIR(base_st.st_mode) or stat.S_ISLNK(base_st.st_mode)
                or not stat.S_ISDIR(content_st.st_mode) or stat.S_ISLNK(content_st.st_mode)):
            raise OSError
        if sorted(x.name for x in os.scandir(base)) != sorted([REQUEST_NAME, "content"]):
            raise OSError
        expected = sorted({item["sha256"] for item in request["payloads"]})
        if sorted(x.name for x in os.scandir(content)) != expected:
            raise OSError
        files={}
        descriptors={item["sha256"]:item for item in request["payloads"]}
        for name in expected:
            item = (content / name).lstat()
            if not stat.S_ISREG(item.st_mode) or stat.S_ISLNK(item.st_mode) or item.st_nlink != 1:
                raise OSError
            raw,observed=_read_stable(content/name,"PUBLICATION_PATH_UNSAFE")
            descriptor=descriptors[name]
            if stamp(observed)!=stamp(item) or len(raw)!=descriptor["size_bytes"] or hashlib.sha256(raw).hexdigest()!=name:raise OSError
            files[name]=(item,name,len(raw))
    except OSError:
        _fail("PUBLICATION_PATH_UNSAFE", "publication input complete set differs")
    return base, base_st, content, content_st, files


def _verify_input_tree(tree: tuple[Path, os.stat_result, Path, os.stat_result,dict[str,tuple[os.stat_result,str,int]]], request: Mapping[str, Any]) -> None:
    base, base_st, content, content_st,files = tree
    try:
        if stamp(base.lstat()) != stamp(base_st) or stamp(content.lstat()) != stamp(content_st):
            raise OSError
    except OSError:
        _fail("PUBLICATION_PATH_UNSAFE", "publication input directory changed")
    current=_input_tree(base.parents[2], base.parent.name, request)
    for name,(first,digest,size) in files.items():
        now,now_digest,now_size=current[4][name]
        if stamp(now)!=stamp(first) or now_digest!=digest or now_size!=size:_fail("PUBLICATION_PATH_UNSAFE","publication input content changed")


def _assemble_publication_transaction(*, operation_id, operation_type, batch,
                                      payload_bytes, claimed_input_paths, read_bytes,
                                      audit, snapshot, session, upstream_root,
                                      checkout, vault):
    """Share only receipt/transport construction after front-end validation."""
    sequence = 1 if audit["head"] is None else audit["head"]["sequence"] + 1
    old_head_bytes = None if sequence == 1 else snapshot.read(HEAD_PATH, max_bytes=1024 * 1024)
    old_head_stat = None if sequence == 1 else snapshot.files[HEAD_PATH][0]
    business = []
    original: dict[str, bytes | None] = {}
    expected: dict[str, str | None] = {}
    for path, data in sorted(payload_bytes.items()):
        try:
            old=snapshot.read_optional(path)
            if old is None: raise FileNotFoundError
            old_st=snapshot.files[path][0]
            mode = "replace"; before = hashlib.sha256(old).hexdigest(); original[path] = old
            original_mode = stat.S_IMODE(old_st.st_mode); original_size = len(old)
        except FileNotFoundError:
            mode = "create"; before = None; original[path] = None; original_mode = None; original_size = 0
        digest = hashlib.sha256(data).hexdigest(); expected[path] = before
        business.append({"path": path, "role": "business", "mode": mode, "sha256": digest,
                         "size_bytes": len(data), "original_size_bytes": original_size, "original_mode": original_mode})
    claims = [{"path": path, "mode": "read", "sha256": hashlib.sha256(read_bytes[path]).hexdigest()}
              for path in claimed_input_paths]
    previous = None if sequence == 1 else {"path": audit["head"]["receipt_path"], "sha256": audit["head"]["receipt_sha256"]}
    receipt = {"schema": "video-paper-wiki.operation-receipt.v1", "sequence": sequence, "previous": previous,
               "operation_id": operation_id, "operation_type": operation_type, "intent_sha256": "0" * 64,
               "writes": [{"path": x["path"], "mode": x["mode"], "before_sha256": expected[x["path"]], "after_sha256": x["sha256"]} for x in business],
               "claimed_inputs": claims}
    receipt["intent_sha256"] = receipt_intent_sha256(receipt)
    receipt_path = f"wiki/meta/operations/{sequence:012d}-{operation_id}.json"; receipt_raw = canonicalize(receipt)
    head = {"schema": "video-paper-wiki.operation-head.v1", "sequence": sequence, "receipt_path": receipt_path,
            "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest()}; head_raw = canonicalize(head)
    for path, data, role in ((receipt_path, receipt_raw, "receipt"), (HEAD_PATH, head_raw, "head")):
        old = None if sequence == 1 or role == "receipt" else old_head_bytes
        business.append({"path": path, "role": role, "mode": "create" if old is None else "replace",
                         "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
                         "original_size_bytes": len(old or b""), "original_mode": None if old is None else stat.S_IMODE(old_head_stat.st_mode)})
        expected[path] = None if old is None else hashlib.sha256(old).hexdigest(); original[path] = old
        payload_bytes[path] = data
    read_hashes = {p: hashlib.sha256(v).hexdigest() for p, v in read_bytes.items()}
    material = {"operation_id": operation_id, "operation_type": operation_type,
                "writes": [{k: x[k] for k in ("path", "mode", "sha256")} for x in business],
                "expected_hashes": expected, "read_preconditions": read_hashes}
    bundle = encode_transaction_inspect_bundle(material)
    if len(bundle) > MAX_BUNDLE_BYTES:
        _fail("TRANSACTION_LIMIT_EXCEEDED", "bundle exceeds limit")
    proposal = {"schema": "video-paper-wiki.transaction-facade.v1", "phase": "proposal",
                "operation_id": operation_id, "operation_type": operation_type, "writes": business,
                "expected_hashes": expected, "read_preconditions": read_hashes, "claimed_inputs": claims,
                "address_requests": [], "source_manifest_updates": {}, "engine_expanded_paths": [],
                "receipt": receipt, "head": head, "input_bundle_sha256": hashlib.sha256(bundle).hexdigest(),
                "declaration_sha256": "0" * 64, "inspection": None, "runtime_result": None}
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    proposal = validate_transaction(proposal)
    verify_transaction_bytes(proposal, write_bytes=payload_bytes, original_bytes=original, read_bytes=read_bytes)
    staging = _stage_transaction_inspect_transport(proposal, write_bytes=payload_bytes, original_bytes=original,
                                                   read_bytes=read_bytes, batch_id=batch, session=session)
    upstream = inspect_pinned_transaction(proposal, upstream_root=upstream_root,
        work_root=checkout / WORK_DIRNAME, vault_root=vault,
        bundle_path=checkout / WORK_DIRNAME / batch / "transaction-inspect" / "bundle.json")
    tx = attach_upstream_inspection(proposal, upstream["transaction"]["inspection"])
    return {"transaction": tx, "transaction_staging": staging, "upstream_authority": upstream}


def _inspect_publication_core(*, prepared: Path | str, operation_id: object,
                             upstream_root: Path | str, vault_root: Path | str,
                             _session: object, _vault_snapshot: _Snapshot) -> dict[str, Any]:
    if type(operation_id) is not str or _ID.fullmatch(operation_id) is None:
        _fail("SCHEMA_INVALID", "invalid operation id", "/operation_id")
    checkout = resolve_checkout_root(); request_path, batch = _request_path(prepared, checkout)
    raw, request_stat = _read_stable(request_path, "PUBLICATION_PATH_UNSAFE", 1024 * 1024)
    request = validate_publication_request(parse_strict_json(raw, invalid_code="SCHEMA_INVALID"))
    if canonicalize(request) != raw or request["batch_id"] != batch or request["operation_id"] != operation_id:
        _fail("PUBLICATION_REQUEST_INVALID", "request bytes or identity differ")
    input_tree = _input_tree(checkout, batch, request)
    payload_bytes: dict[str, bytes] = {}; retained: list[tuple[Path, os.stat_result]] = [(request_path, request_stat)]
    decoded: dict[str, Any] = {}
    for item in request["payloads"]:
        content = checkout / WORK_DIRNAME / batch / item["content_file"]
        data, st = _read_stable(content, "PUBLICATION_PATH_UNSAFE")
        if len(data) != item["size_bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            _fail("PUBLICATION_REQUEST_INVALID", "payload descriptor differs")
        payload_bytes[item["path"]] = data; retained.append((content, st))
        if item["path"].endswith(".json"):
            decoded[item["path"]] = _decode_publication_json(item["path"], data)
    vault = Path(vault_root)
    try:
        audit = audit_integrity(vault, _snapshot=_vault_snapshot)
        sequence = 1 if audit["head"] is None else audit["head"]["sequence"] + 1
    except ContractError as exc:
        if exc.code != "RECEIPT_BOOTSTRAP_REQUIRED":
            raise
        sequence = 1; audit = {"head": None}
    from video_paper_wiki.source_state import require_legacy_profile
    from video_paper_wiki.receipt_audit import _walk_inventory
    require_legacy_profile(payload_bytes)
    require_legacy_profile({p: _vault_snapshot.files[p][1] for p in _walk_inventory(_vault_snapshot, read_bytes=True)})
    if sequence == 1 and (request["operation_type"] != "generic" or not request["payloads"]
                          or set(request["claimed_input_paths"]) != {"wiki/meta/ledgers/claim-ledger.json", "wiki/meta/ledgers/source-ledger.json"}):
        _fail("RECEIPT_BOOTSTRAP_REQUIRED", "genesis must claim both pristine ledgers and publish business bytes")
    reads = sorted(set(request["claimed_input_paths"] + request["additional_read_paths"]))
    old_head_bytes: bytes | None = None; old_head_stat: os.stat_result | None = None
    if sequence > 1:
        reads += [audit["head"]["receipt_path"]]
        reads = sorted(set(reads))
        old_head_bytes=_vault_snapshot.read(HEAD_PATH,max_bytes=1024*1024);old_head_stat=_vault_snapshot.files[HEAD_PATH][0]
    read_bytes: dict[str, bytes] = {}; read_stats: dict[str, os.stat_result] = {}
    for path in reads:
        data=_vault_snapshot.read(path);read_stat=_vault_snapshot.files[path][0]
        read_bytes[path] = data; read_stats[path] = read_stat
        if path.endswith(".json"):
            decoded[path]=_decode_publication_json(path, data)
    _prospective(request,decoded,payload_bytes,_vault_snapshot)
    children = _assemble_publication_transaction(operation_id=operation_id,
        operation_type=request["operation_type"], batch=batch, payload_bytes=payload_bytes,
        claimed_input_paths=request["claimed_input_paths"], read_bytes=read_bytes, audit=audit,
        snapshot=_vault_snapshot, session=_session, upstream_root=upstream_root, checkout=checkout, vault=vault)
    tx, staging, upstream = (children[key] for key in ("transaction", "transaction_staging", "upstream_authority"))
    for path, first in retained:
        try:
            if stamp(path.lstat()) != stamp(first):
                _fail("PUBLICATION_PATH_UNSAFE", "publication input changed")
        except OSError:
            _fail("PUBLICATION_PATH_UNSAFE", "publication input changed")
    _verify_input_tree(input_tree, request)
    result = {"schema": AUTHORITY_SCHEMA, "request_sha256": hashlib.sha256(raw).hexdigest(),
              "request": request, "transaction": tx, "transaction_staging": staging,
              "upstream_authority": upstream}
    _vault_snapshot.verify()
    return validate_publication_authority(result)


class _RetainedPublicationAuthority:
    """Retain the exact publication and transaction transport used by inspect."""
    def __init__(self,checkout:Path,batch:str,authority:Mapping[str,Any]):
        from video_paper_wiki.catalog_store import _RetainedFile
        base=checkout/WORK_DIRNAME/batch;self.items=[];self.directories=[]
        groups=[('PUBLICATION_PATH_UNSAFE',[base/'publication-input'/REQUEST_NAME,
            *[base/item['content_file'] for item in authority['request']['payloads']]]),
            ('TRANSACTION_STAGING_INVALID',[base/authority['transaction_staging']['bundle_file'],
            *[base/item['content_file'] for item in authority['transaction_staging']['content_files']]])]
        try:
            for code,paths in groups:
                held=[]
                for path in paths:held.append(_RetainedFile(path))
                self.items.extend((item,code) for item in held)
                parents={item.path.parent for item in held}
                for parent in parents:
                    anchor=next(item for item in held if item.path.parent==parent)
                    self.directories.append((anchor,code,self._names(anchor.parent_fd)))
        except BaseException as exc:
            self.close()
            if isinstance(exc,ContractError) and exc.code in {'PUBLICATION_PATH_UNSAFE','TRANSACTION_STAGING_INVALID'}:raise
            _fail('PUBLICATION_PATH_UNSAFE','retained publication authority is unsafe')
        self.bundle_path=base/authority['transaction_staging']['bundle_file']

    @staticmethod
    def _names(fd:int)->tuple[str,...]:
        fresh=os.open('.',os.O_RDONLY|getattr(os,'O_DIRECTORY',0)|getattr(os,'O_NOFOLLOW',0),dir_fd=fd)
        try:return tuple(sorted(item.name for item in os.scandir(fresh)))
        finally:os.close(fresh)

    def verify(self)->None:
        for item,code in self.items:item.verify_edge(code)
        for anchor,code,names in self.directories:
            anchor.verify_edge(code)
            if self._names(anchor.parent_fd)!=names:_fail(code,'retained authority file set changed')

    def __enter__(self):return self.bundle_path

    def __exit__(self,exc_type,exc,tb):
        try:self.verify()
        finally:self.close()
        return False

    def close(self)->None:
        for item,_code in reversed(getattr(self,'items',[])):item.close()
        self.items=[]


def inspect_publication(*, prepared: Path | str, operation_id: object,
                        upstream_root: Path | str, vault_root: Path | str,
                        _authority_holder_out: list | None = None) -> dict[str, Any]:
    if type(operation_id) is not str or _ID.fullmatch(operation_id) is None:
        _fail("SCHEMA_INVALID", "invalid operation id", "/operation_id")
    checkout = resolve_checkout_root(); target, batch = _request_path(prepared, checkout)
    baseline_raw, baseline_stat = _read_stable(target, "PUBLICATION_PATH_UNSAFE", 1024 * 1024)
    baseline_request = validate_publication_request(parse_strict_json(baseline_raw, invalid_code="SCHEMA_INVALID"))
    baseline_tree = _input_tree(checkout, batch, baseline_request)
    vault_snapshot=None;authority_holder=None
    try:
        vault_snapshot=_Snapshot(Path(vault_root))
        try:
            with _open_batch_session(batch, create=False) as session:
                value = _inspect_publication_core(prepared=prepared, operation_id=operation_id,
                    upstream_root=upstream_root, vault_root=vault_root, _session=session,
                    _vault_snapshot=vault_snapshot)
                if _authority_holder_out is not None:
                    authority_holder=_RetainedPublicationAuthority(checkout,batch,value)
                    _authority_holder_out.append(authority_holder)
        except BaseException:
            current,current_stat=_read_stable(target,"PUBLICATION_PATH_UNSAFE",1024*1024)
            if current!=baseline_raw or stamp(current_stat)!=stamp(baseline_stat):_fail("PUBLICATION_PATH_UNSAFE","publication request changed")
            _verify_input_tree(baseline_tree,baseline_request)
            vault_snapshot.verify()
            raise
        current,current_stat=_read_stable(target,"PUBLICATION_PATH_UNSAFE",1024*1024)
        if (current!=baseline_raw or stamp(current_stat)!=stamp(baseline_stat)
                or value["request"]!=baseline_request or value["request_sha256"]!=hashlib.sha256(baseline_raw).hexdigest()):
            _fail("PUBLICATION_PATH_UNSAFE","publication request changed")
        _verify_input_tree(baseline_tree,baseline_request);vault_snapshot.verify()
        if authority_holder is not None:authority_holder.verify()
        return value
    except BaseException:
        if authority_holder is not None:
            try:authority_holder.verify()
            finally:
                authority_holder.close()
                if _authority_holder_out:_authority_holder_out.pop()
        current,current_stat=_read_stable(target,"PUBLICATION_PATH_UNSAFE",1024*1024)
        if current!=baseline_raw or stamp(current_stat)!=stamp(baseline_stat):_fail("PUBLICATION_PATH_UNSAFE","publication request changed")
        _verify_input_tree(baseline_tree,baseline_request)
        if vault_snapshot is not None:vault_snapshot.verify()
        raise
    finally:
        if vault_snapshot is not None:vault_snapshot.close()


def prepare_publication_source(*, request_path: Path | str, batch_id: object) -> dict[str, Any]:
    """Copy one closed publication-input source through a retained no-follow tree."""
    from video_paper_wiki.secure_io import close_fd,dir_open_flags,file_open_flags,open_dir_nofollow
    batch=validate_batch_id(batch_id);source=Path(request_path);content=source.parent/"content"
    if source.name!=REQUEST_NAME or source.parent.name!="publication-input":_fail("PUBLICATION_PATH_UNSAFE","publication source does not use the fixed layout")
    from video_paper_wiki.catalog_store import _RetainedFile
    root_fd=open_dir_nofollow(source.parent,missing_code="PUBLICATION_PATH_UNSAFE",unsafe_code="PUBLICATION_PATH_UNSAFE");content_fd=None;request_fd=None;request_first=None;content_first=None;files={};held=[]
    root_first=os.fstat(root_fd)
    def read_fd(fd,limit):
        os.lseek(fd,0,os.SEEK_SET);parts=[];total=0
        while True:
            part=os.read(fd,1024*1024)
            if not part:break
            total+=len(part)
            if total>limit:_fail("PUBLICATION_PATH_UNSAFE","publication source exceeds limit")
            parts.append(part)
        return b"".join(parts)
    def names(fd):
        fresh=os.open('.',dir_open_flags(),dir_fd=fd)
        try:
            if (os.fstat(fresh).st_dev,os.fstat(fresh).st_ino)!=(os.fstat(fd).st_dev,os.fstat(fd).st_ino):raise OSError
            return sorted(x.name for x in os.scandir(fresh))
        finally:close_fd(fresh)
    def verify_tree():
        try:
            for item in held:item.verify_edge("PUBLICATION_PATH_UNSAFE")
            named_root=source.parent.lstat()
            identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
            if identity(named_root)!=identity(root_first) or identity(os.fstat(root_fd))!=identity(root_first):raise OSError
            if names(root_fd)!=sorted([REQUEST_NAME,"content"]):raise OSError
            if request_fd is not None:
                rst=os.fstat(request_fd)
                if stamp(rst)!=stamp(request_first) or stamp(os.stat(REQUEST_NAME,dir_fd=root_fd,follow_symlinks=False))!=stamp(request_first):raise OSError
            if content_fd is not None:
                if stamp(os.fstat(content_fd))!=stamp(content_first) or stamp(os.stat("content",dir_fd=root_fd,follow_symlinks=False))!=stamp(content_first):raise OSError
                if names(content_fd)!=sorted(files):raise OSError
                for name,(fd,first,_data) in files.items():
                    if stamp(os.fstat(fd))!=stamp(first) or stamp(os.stat(name,dir_fd=content_fd,follow_symlinks=False))!=stamp(first):raise OSError
        except ContractError as exc:
            if exc.code=="PUBLICATION_PATH_UNSAFE":raise
            _fail("PUBLICATION_PATH_UNSAFE","publication source tree changed")
        except (OSError,ValueError,TypeError):_fail("PUBLICATION_PATH_UNSAFE","publication source tree changed")
    try:
        try:request_held=_RetainedFile(source)
        except ContractError:_fail("PUBLICATION_PATH_UNSAFE","publication request is unsafe")
        held.append(request_held);request_fd=request_held.fd;request_first=request_held.file_stat
        if request_fd is None or request_first is None or not stat.S_ISREG(request_first.st_mode) or request_first.st_nlink!=1:_fail("PUBLICATION_PATH_UNSAFE","publication request is unsafe")
        raw=read_fd(request_fd,1024*1024)
        content_fd=os.open("content",dir_open_flags(),dir_fd=root_fd);content_first=os.fstat(content_fd)
        request=validate_publication_request(parse_strict_json(raw,invalid_code="SCHEMA_INVALID"))
        if canonicalize(request)!=raw:_fail("PUBLICATION_REQUEST_INVALID","publication source request is not canonical")
        if request["batch_id"]!=batch:_fail("PUBLICATION_REQUEST_INVALID","publication batch differs")
        expected=sorted({item["sha256"] for item in request["payloads"]})
        if names(content_fd)!=expected:_fail("PUBLICATION_PATH_UNSAFE","publication source content set differs")
        for digest in expected:
            try:file_held=_RetainedFile(content/digest)
            except ContractError:_fail("PUBLICATION_PATH_UNSAFE","publication content is unsafe")
            held.append(file_held);fd=file_held.fd;first=file_held.file_stat
            if fd is None or first is None or not stat.S_ISREG(first.st_mode) or first.st_nlink!=1:_fail("PUBLICATION_PATH_UNSAFE","publication content is unsafe")
            files[digest]=(fd,first,b'');data=read_fd(fd,64*1024*1024);files[digest]=(fd,first,data)
            if hashlib.sha256(data).hexdigest()!=digest:_fail("PUBLICATION_REQUEST_INVALID","publication content digest differs")
        for item in request["payloads"]:
            if len(files[item["sha256"]][2])!=item["size_bytes"]:_fail("PUBLICATION_REQUEST_INVALID","publication content size differs")
        verify_tree();payloads={item["path"]:files[item["sha256"]][2] for item in request["payloads"]}
        result=stage_publication_request(batch_id=batch,operation_id=request["operation_id"],operation_type=request["operation_type"],payloads=payloads,claimed_input_paths=request["claimed_input_paths"],additional_read_paths=request["additional_read_paths"],prospective_groups=request["prospective_groups"])
        verify_tree()
        if result["request"]!=request or result["request_sha256"]!=hashlib.sha256(raw).hexdigest():_fail("PUBLICATION_REQUEST_INVALID","publication stager rewrote request semantics")
        return result
    except BaseException:
        verify_tree();raise
    finally:
        for item in reversed(held):item.close()
        if content_fd is not None:close_fd(content_fd)
        close_fd(root_fd)

def run_publication_inspect_command(args: object) -> int:
    from video_paper_wiki.envelope import emit_error, emit_success
    try:
        return emit_success("publication.inspect", inspect_publication(prepared=args.prepared,
            operation_id=args.operation_id, upstream_root=args.upstream_root, vault_root=args.vault_root))
    except Exception as exc:
        return emit_error("publication.inspect", getattr(exc, "code", "PUBLICATION_FAILED"),
                          getattr(exc, "message", str(exc)), getattr(exc, "details", {}),
                          exit_code=getattr(exc, "exit_code", 2))


def run_publication_prepare_command(args: object) -> int:
    from video_paper_wiki.envelope import emit_error,emit_success
    try:return emit_success("publication.prepare",prepare_publication_source(request_path=args.request,batch_id=args.batch_id))
    except Exception as exc:return emit_error("publication.prepare",getattr(exc,"code","PUBLICATION_FAILED"),getattr(exc,"message",str(exc)),getattr(exc,"details",{}),exit_code=getattr(exc,"exit_code",2))
