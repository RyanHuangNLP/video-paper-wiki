"""Inspect one prepared PDF through deterministic staging and the pinned inspector."""
from __future__ import annotations

import copy
import hashlib
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, NoReturn

from video_paper_wiki.approval import approval_ref_sha256, bind_approval_ref, jcs_sha256
from video_paper_wiki.capture_contracts import capture_approval_hash, validate_capture_inspection
from video_paper_wiki.captured_snapshot import capture_snapshot
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki.staging import (
    WORK_DIRNAME, StagingError, _RetainedBatchSession, _close_fd,
    _open_batch_session, _open_dir_at, _read_regular_file_at_bounded_identity, _stat_at,
    _require_exact_staged_file, _require_same_directory, resolve_checkout_root,
    validate_batch_id,
)
from video_paper_wiki.transaction_contracts import transaction_declaration_hash, validate_transaction
from video_paper_wiki.transaction_staging import (
    MAX_BUNDLE_BYTES, _stage_transaction_inspect_transport,
    encode_transaction_inspect_bundle, validate_transaction_staging,
)
from video_paper_wiki.upstream_adapter import (
    _check_upstream_authority_fields, _directory_argument, _path_argument,
    _roots_are_disjoint, inspect_pinned_transaction,
)

REQUEST_SCHEMA = "video-paper-wiki.staged-pdf-capture-request.v1"
AUTHORITY_SCHEMA = "video-paper-wiki.staged-pdf-capture-authority.v1"
REQUEST_FILE = "staged-pdf-capture-request.v1.json"
REQUEST_RELATIVE = "prepared/" + REQUEST_FILE
REQUEST_MISMATCH = "STAGED_CAPTURE_REQUEST_MISMATCH"
RESULT_MISMATCH = "STAGED_CAPTURE_RESULT_MISMATCH"
_OPERATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _fail(code: str, pointer: str, message: str) -> NoReturn:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _check_request(document: Mapping[str, Any]) -> None:
    ref, plan, payload = document["approval_ref"], document["plan"], document["payload"]
    if document["approval_ref_sha256"] != approval_ref_sha256(ref):
        _fail(REQUEST_MISMATCH, "/approval_ref_sha256", "approval-ref digest differs")
    checks = (
        (document["batch_id"], ref["batch_id"], "/batch_id"),
        (plan["approval_hash"], ref["plan_approval_hash"], "/plan/approval_hash"),
        (plan["plan_kind"], ref["plan_kind"], "/plan/plan_kind"),
        (plan["stable_subject_id"], ref["stable_subject_id"], "/plan/stable_subject_id"),
        (plan["limits_sha256"], ref["limits_sha256"], "/plan/limits_sha256"),
        (plan["network_targets_sha256"], ref["network_targets_sha256"], "/plan/network_targets_sha256"),
        (plan["pipeline_fingerprint"], ref["pipeline_fingerprint"], "/plan/pipeline_fingerprint"),
        (payload["sha256"], ref["input_sha256"], "/payload/sha256"),
        (payload["file"], f"prepared/{payload['sha256']}.blob", "/payload/file"),
    )
    for actual, expected, pointer in checks:
        if actual != expected:
            _fail(REQUEST_MISMATCH, pointer, "request fields are not correlated")


def validate_staged_pdf_capture_request(document: object) -> dict[str, object]:
    return copy.deepcopy(validate_document(document, REQUEST_SCHEMA))


def _check_authority(document: Mapping[str, Any]) -> None:
    request = validate_staged_pdf_capture_request(document["request"])
    inspection = validate_capture_inspection(document["inspection"])
    payload = request["payload"]
    common = (
        document["request_file"] == REQUEST_RELATIVE
        and document["request_sha256"] == hashlib.sha256(canonicalize(request)).hexdigest()
        and inspection["route"] == "staged-capture"
        and inspection["media_type"] == "application/pdf"
        and inspection["payload"] == {"sha256": payload["sha256"], "size_bytes": payload["size_bytes"]}
        and inspection["source_path"] is None
        and inspection["proposal_sha256"] is None
        and inspection["source_identity"] == payload["sha256"]
        and capture_approval_hash(inspection) == inspection["approval_hash"]
    )
    if not common:
        _fail(RESULT_MISMATCH, "/inspection", "authority request and inspection differ")
    if document["disposition"] == "reuse":
        valid = (
            document["transaction_staging"] is None and document["upstream_authority"] is None
            and inspection["would_change"] is False and inspection["operation_id"] is None
            and inspection["upstream_plan_sha256"] is None and len(inspection["siblings"]) == 1
            and inspection["stored_path"] == inspection["siblings"][0]["path"]
        )
        if not valid:
            _fail(RESULT_MISMATCH, "/disposition", "reuse authority differs")
        return
    staging = validate_transaction_staging(document["transaction_staging"])
    upstream = document["upstream_authority"]
    _check_upstream_authority_fields(upstream)
    tx = upstream["transaction"]
    target = f".raw/captured/{payload['sha256']}.pdf"
    write = tx["writes"][0] if len(tx["writes"]) == 1 else None
    plan = tx["inspection"]
    content = staging["content_files"]
    transport = upstream["transport"]
    valid = (
        inspection["would_change"] is True and inspection["siblings"] == []
        and inspection["operation_id"] == document["requested_operation_id"]
        and inspection["stored_path"] == target
        and write == {
            "path": target, "role": "business", "mode": "create",
            "sha256": payload["sha256"], "size_bytes": payload["size_bytes"],
            "original_size_bytes": 0, "original_mode": None,
        }
        and tx["operation_id"] == document["requested_operation_id"]
        and tx["operation_type"] == "capture" and tx["phase"] == "inspected"
        and tx["expected_hashes"] == {target: None} and tx["read_preconditions"] == {}
        and staging["batch_id"] == request["batch_id"]
        and staging["operation_id"] == tx["operation_id"]
        and staging["operation_type"] == tx["operation_type"] == "capture"
        and staging["transaction_declaration_sha256"] == tx["declaration_sha256"]
        and content == [{"content_file": "transaction-inspect/content/" + payload["sha256"], "sha256": payload["sha256"], "size_bytes": payload["size_bytes"]}]
        and staging["bundle_sha256"] == tx["input_bundle_sha256"] == transport["bundle_sha256"]
        and staging["bundle_size_bytes"] == transport["bundle_size_bytes"]
        and transport["content_files"] == [{"write_path": target, "content_file": "content/" + payload["sha256"], "sha256": payload["sha256"], "size_bytes": payload["size_bytes"]}]
        and plan is not None and inspection["upstream_plan_sha256"] == plan["approval_sha256"]
    )
    if not valid:
        _fail(RESULT_MISMATCH, "/upstream_authority", "create authority children differ")


def validate_staged_pdf_capture_authority(document: object) -> dict[str, object]:
    return copy.deepcopy(validate_document(document, AUTHORITY_SCHEMA))


class _Inputs:
    def __init__(self, session: _RetainedBatchSession, plan_fd: int, prepared_fd: int, plan_bytes: bytes, request_bytes: bytes, request: dict[str, Any], plan_stat: os.stat_result, request_stat: os.stat_result):
        self.session, self.plan_fd, self.prepared_fd = session, plan_fd, prepared_fd
        self.plan_bytes, self.request_bytes, self.request = plan_bytes, request_bytes, request
        self.blob: bytes | None = None
        self.plan_dir_stat, self.prepared_dir_stat = os.fstat(plan_fd), os.fstat(prepared_fd)
        self.plan_path = session.batch_path / "plan" / "ingest-plan.v1.json"
        self.request_path = session.batch_path / "prepared" / REQUEST_FILE
        self.blob_name = request["payload"]["file"].split("/", 1)[1]
        self.blob_path = session.batch_path / "prepared" / self.blob_name
        self.file_stats: tuple[os.stat_result, os.stat_result, os.stat_result | None] = (
            plan_stat, request_stat, None,
        )

    def load_blob(self) -> bytes:
        self.verify()
        data, identity = _read_regular_file_at_bounded_identity(
            self.prepared_fd, self.blob_name, self.blob_path,
            max_bytes=self.request["payload"]["size_bytes"],
        )
        self.blob = data
        self.file_stats = (self.file_stats[0], self.file_stats[1], identity)
        self.verify()
        return data

    @staticmethod
    def _same_file(actual: os.stat_result | None, expected: os.stat_result | None) -> bool:
        if actual is None or expected is None:
            return actual is expected
        return (actual.st_dev, actual.st_ino, actual.st_mode, actual.st_size, actual.st_mtime_ns) == (expected.st_dev, expected.st_ino, expected.st_mode, expected.st_size, expected.st_mtime_ns)

    def verify(self) -> None:
        self.session.verify()
        _require_same_directory(self.plan_fd, self.plan_dir_stat, self.plan_path.parent)
        _require_same_directory(self.prepared_fd, self.prepared_dir_stat, self.request_path.parent)
        named_plan = _open_dir_at(self.session.batch_fd, "plan", self.plan_path.parent)
        named_prepared = _open_dir_at(self.session.batch_fd, "prepared", self.request_path.parent)
        try:
            _require_same_directory(named_plan, self.plan_dir_stat, self.plan_path.parent)
            _require_same_directory(named_prepared, self.prepared_dir_stat, self.request_path.parent)
            current = (
                _stat_at(named_plan, "ingest-plan.v1.json", self.plan_path),
                _stat_at(named_prepared, REQUEST_FILE, self.request_path),
                (_stat_at(named_prepared, self.blob_name, self.blob_path)
                 if self.file_stats[2] is not None else None),
            )
            if any(not self._same_file(a, b) for a, b in zip(current, self.file_stats, strict=True)):
                raise StagingError("WORK_PATH_UNSAFE", "prepared input identity changed", {"path": self.request_path.as_posix()})
        finally:
            _close_fd(named_prepared); _close_fd(named_plan)
        _require_exact_staged_file(self.plan_fd, "ingest-plan.v1.json", self.plan_bytes, self.plan_path)
        _require_exact_staged_file(self.prepared_fd, REQUEST_FILE, self.request_bytes, self.request_path)
        if self.blob is not None:
            _require_exact_staged_file(self.prepared_fd, self.blob_name, self.blob, self.blob_path)


@contextmanager
def _inputs(batch: str) -> Iterator[_Inputs]:
    with _open_batch_session(batch, create=False) as session:
        assert isinstance(session, _RetainedBatchSession)
        plan_fd = prepared_fd = None
        try:
            prepared_path = session.batch_path / "prepared"
            request_path = session.batch_path / REQUEST_RELATIVE
            plan_path = session.batch_path / "plan"
            plan_file = plan_path / "ingest-plan.v1.json"
            prepared_fd = _open_dir_at(session.batch_fd, "prepared", prepared_path)
            prepared_dir_stat = os.fstat(prepared_fd)
            request_bytes: bytes | None = None
            request_stat: os.stat_result | None = None
            plan_dir_stat: os.stat_result | None = None
            plan_bytes: bytes | None = None
            plan_stat: os.stat_result | None = None

            def verify_phase() -> None:
                session.verify()
                _require_same_directory(prepared_fd, prepared_dir_stat, prepared_path)
                if plan_fd is not None and plan_dir_stat is not None:
                    _require_same_directory(plan_fd, plan_dir_stat, plan_path)
                named_prepared = _open_dir_at(session.batch_fd, "prepared", prepared_path)
                named_plan: int | None = None
                try:
                    _require_same_directory(named_prepared, prepared_dir_stat, prepared_path)
                    if request_bytes is not None and request_stat is not None:
                        if not _Inputs._same_file(
                            _stat_at(named_prepared, REQUEST_FILE, request_path), request_stat,
                        ):
                            raise StagingError(
                                "WORK_PATH_UNSAFE", "prepared request identity changed",
                                {"path": request_path.as_posix()},
                            )
                        _require_exact_staged_file(
                            named_prepared, REQUEST_FILE, request_bytes, request_path,
                        )
                    if plan_fd is not None and plan_dir_stat is not None:
                        named_plan = _open_dir_at(session.batch_fd, "plan", plan_path)
                        _require_same_directory(named_plan, plan_dir_stat, plan_path)
                        if plan_bytes is not None and plan_stat is not None:
                            if not _Inputs._same_file(
                                _stat_at(named_plan, "ingest-plan.v1.json", plan_file), plan_stat,
                            ):
                                raise StagingError(
                                    "WORK_PATH_UNSAFE", "prepared plan identity changed",
                                    {"path": plan_file.as_posix()},
                                )
                            _require_exact_staged_file(
                                named_plan, "ingest-plan.v1.json", plan_bytes, plan_file,
                            )
                finally:
                    _close_fd(named_plan)
                    _close_fd(named_prepared)

            try:
                request_bytes, request_stat = _read_regular_file_at_bounded_identity(
                    prepared_fd, REQUEST_FILE, request_path, max_bytes=1048576,
                )
                request_obj = parse_strict_json(request_bytes, invalid_code="SCHEMA_INVALID")
                request = validate_staged_pdf_capture_request(request_obj)
                if canonicalize(request) != request_bytes:
                    _fail(REQUEST_MISMATCH, "/request", "request is not canonical")
            except BaseException:
                verify_phase()
                raise
            try:
                verify_phase()
                plan_fd = _open_dir_at(session.batch_fd, "plan", plan_path)
                plan_dir_stat = os.fstat(plan_fd)
                verify_phase()
                plan_bytes, plan_stat = _read_regular_file_at_bounded_identity(
                    plan_fd, "ingest-plan.v1.json", plan_file, max_bytes=1048576,
                )
                verify_phase()
            except BaseException:
                verify_phase()
                raise
            assert plan_bytes is not None and plan_stat is not None
            value = _Inputs(session, plan_fd, prepared_fd, plan_bytes, request_bytes, request, plan_stat, request_stat)
            value.verify()
            try:
                yield value
            except BaseException:
                value.verify()
                raise
            else:
                value.verify()
        finally:
            _close_fd(prepared_fd); _close_fd(plan_fd)


def _prepared_batch(prepared: Path | str, checkout: Path) -> str:
    if not isinstance(prepared, (str, Path)):
        _fail("ADAPTER_PATH_INVALID", "/prepared", "prepared path is invalid")
    try:
        raw = os.fspath(prepared)
        if "\x00" in raw:
            raise ValueError
        normalized = Path(os.path.normpath(os.path.abspath(raw)))
        relative = normalized.relative_to(checkout / WORK_DIRNAME)
    except (OSError, ValueError, TypeError, UnicodeError, StagingError):
        _fail("ADAPTER_PATH_INVALID", "/prepared", "prepared path is invalid")
    parts = relative.parts
    if len(parts) != 3 or parts[1:] != ("prepared", REQUEST_FILE):
        _fail("ADAPTER_PATH_INVALID", "/prepared", "prepared path does not use fixed layout")
    try:
        return validate_batch_id(parts[0])
    except StagingError:
        _fail("ADAPTER_PATH_INVALID", "/prepared", "prepared path has invalid batch")


def _proposal(operation_id: str, payload: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(payload).hexdigest()
    target = f".raw/captured/{digest}.pdf"
    write = {"path": target, "role": "business", "mode": "create", "sha256": digest, "size_bytes": len(payload), "original_size_bytes": 0, "original_mode": None}
    material = {"operation_id": operation_id, "operation_type": "capture", "writes": [{"path": target, "mode": "create", "sha256": digest}], "expected_hashes": {target: None}, "read_preconditions": {}}
    bundle = encode_transaction_inspect_bundle(material)
    proposal = {
        "schema": "video-paper-wiki.transaction-facade.v1", "phase": "proposal",
        "operation_id": operation_id, "operation_type": "capture", "writes": [write],
        "expected_hashes": {target: None}, "read_preconditions": {}, "claimed_inputs": [],
        "address_requests": [], "source_manifest_updates": {}, "engine_expanded_paths": [],
        "receipt": None, "head": None, "input_bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "declaration_sha256": "0" * 64, "inspection": None, "runtime_result": None,
    }
    proposal["declaration_sha256"] = transaction_declaration_hash(proposal)
    return validate_transaction(proposal)


def _inspection(request: Mapping[str, Any], *, operation_id: str | None, sibling: dict[str, object] | None, approval: str | None) -> dict[str, Any]:
    payload = request["payload"]
    value = {
        "schema": "video-paper-wiki.capture-inspection.v1", "route": "staged-capture",
        "media_type": "application/pdf", "payload": {"sha256": payload["sha256"], "size_bytes": payload["size_bytes"]},
        "source_path": None, "proposal_sha256": None,
        "stored_path": sibling["path"] if sibling else f".raw/captured/{payload['sha256']}.pdf",
        "source_identity": payload["sha256"], "siblings": [copy.deepcopy(sibling)] if sibling else [],
        "would_change": sibling is None, "operation_id": operation_id if sibling is None else None,
        "upstream_plan_sha256": approval if sibling is None else None, "approval_hash": "0" * 64,
    }
    value["approval_hash"] = capture_approval_hash(value)
    return validate_capture_inspection(value)


def inspect_staged_pdf_capture(*, prepared: Path | str, operation_id: object, upstream_root: Path | str, vault_root: Path | str) -> dict[str, object]:
    if type(operation_id) is not str or _OPERATION.fullmatch(operation_id) is None:
        _fail("SCHEMA_INVALID", "/operation_id", "invalid bounded operation ID")
    try:
        lexical_checkout = Path(os.path.normpath(os.getcwd()))
    except (OSError, ValueError, UnicodeError):
        _fail("ADAPTER_PATH_INVALID", "/prepared", "current checkout path is invalid")
    batch = _prepared_batch(prepared, lexical_checkout)
    upstream_lexical = _path_argument(upstream_root, "upstream_root", check_realpath=False)
    vault_lexical = _path_argument(vault_root, "vault_root", check_realpath=False)
    _roots_are_disjoint(vault_lexical, lexical_checkout / WORK_DIRNAME, upstream_lexical)
    checkout = resolve_checkout_root()
    upstream = _directory_argument(upstream_root, "upstream_root")
    vault = _directory_argument(vault_root, "vault_root")
    _roots_are_disjoint(vault, checkout / WORK_DIRNAME, upstream)
    with _inputs(batch) as inputs:
        request = inputs.request
        if request["batch_id"] != batch:
            _fail(REQUEST_MISMATCH, "/batch_id", "request batch differs from path")
        plan_obj = parse_strict_json(inputs.plan_bytes, invalid_code="SCHEMA_INVALID")
        plan = validate_document(plan_obj, "video-paper-wiki.ingest-plan.v1")
        if canonicalize(plan) != inputs.plan_bytes:
            _fail(REQUEST_MISMATCH, "/plan", "plan is not canonical")
        descriptor = request["plan"]
        if descriptor["sha256"] != hashlib.sha256(inputs.plan_bytes).hexdigest() or descriptor["size_bytes"] != len(inputs.plan_bytes):
            _fail(REQUEST_MISMATCH, "/plan", "plan descriptor differs")
        if descriptor["approval_hash"] != plan["approval_hash"] or descriptor["stable_subject_id"] != plan["stable_subject_id"] or descriptor["input_kind"] != plan["input"]["kind"] or descriptor["limits_sha256"] != jcs_sha256(plan["limits"]) or descriptor["network_targets_sha256"] != jcs_sha256(plan["network_targets"]) or descriptor["pipeline_fingerprint"] != plan["pipeline_fingerprint"]:
            _fail(REQUEST_MISMATCH, "/plan", "plan fields differ")
        bind_approval_ref(plan, request["approval_ref"])
        payload = request["payload"]
        blob = inputs.load_blob()
        if hashlib.sha256(blob).hexdigest() != payload["sha256"] or len(blob) != payload["size_bytes"]:
            _fail(REQUEST_MISMATCH, "/payload", "payload descriptor differs")
        from video_paper_wiki.commands.prepare import _validate_paper_blob
        pages, media = _validate_paper_blob(blob, max_pages=plan["limits"]["max_pages"])
        if pages != payload["page_count"] or media != payload["media_type"] or len(blob) > plan["limits"]["max_bytes"]:
            _fail(REQUEST_MISMATCH, "/payload", "PDF validation differs")
        inputs.verify()
        with capture_snapshot(vault, payload["sha256"]) as snapshot:
            request_sha = hashlib.sha256(inputs.request_bytes).hexdigest()
            if snapshot.sibling is not None:
                inspection = _inspection(request, operation_id=None, sibling=snapshot.sibling, approval=None)
                result = {"schema": AUTHORITY_SCHEMA, "requested_operation_id": operation_id, "request_file": REQUEST_RELATIVE, "request_sha256": request_sha, "request": request, "disposition": "reuse", "inspection": inspection, "transaction_staging": None, "upstream_authority": None}
                inputs.verify(); snapshot.verify()
                return validate_staged_pdf_capture_authority(result)
            proposal = _proposal(operation_id, blob)
            bundle = encode_transaction_inspect_bundle({"operation_id": proposal["operation_id"], "operation_type": proposal["operation_type"], "writes": [{"path": w["path"], "mode": w["mode"], "sha256": w["sha256"]} for w in proposal["writes"]], "expected_hashes": proposal["expected_hashes"], "read_preconditions": proposal["read_preconditions"]})
            if len(bundle) > MAX_BUNDLE_BYTES:
                _fail("TRANSACTION_LIMIT_EXCEEDED", "/bundle_size_bytes", "bundle exceeds transaction limit")
            target = proposal["writes"][0]["path"]
            inputs.verify(); snapshot.verify()
            try:
                staging = _stage_transaction_inspect_transport(proposal, write_bytes={target: blob}, original_bytes={target: None}, read_bytes={}, batch_id=batch, session=inputs.session)
                inputs.verify(); snapshot.verify()
                authority = inspect_pinned_transaction(proposal, upstream_root=upstream, work_root=checkout / WORK_DIRNAME, vault_root=vault, bundle_path=checkout / WORK_DIRNAME / batch / "transaction-inspect" / "bundle.json")
            except Exception:
                inputs.verify(); snapshot.verify()
                raise
            inputs.verify(); snapshot.verify()
            approval = authority["transaction"]["inspection"]["approval_sha256"]
            inspection = _inspection(request, operation_id=operation_id, sibling=None, approval=approval)
            result = {"schema": AUTHORITY_SCHEMA, "requested_operation_id": operation_id, "request_file": REQUEST_RELATIVE, "request_sha256": request_sha, "request": request, "disposition": "create", "inspection": inspection, "transaction_staging": staging, "upstream_authority": authority}
            validated = validate_staged_pdf_capture_authority(result)
            inputs.verify(); snapshot.verify()
            return validated


def run_capture_inspect_command(args: object) -> int:
    """Adapt argparse values to the closed CLI envelope."""
    from video_paper_wiki.envelope import emit_error, emit_staging_error, emit_success

    command = "capture.inspect"
    try:
        value = inspect_staged_pdf_capture(
            prepared=getattr(args, "prepared"),
            operation_id=getattr(args, "operation_id"),
            upstream_root=getattr(args, "upstream_root"),
            vault_root=getattr(args, "vault_root"),
        )
    except StagingError as exc:
        return emit_staging_error(command, exc)
    except Exception as exc:
        return emit_error(
            command, str(getattr(exc, "code", "USAGE")),
            str(getattr(exc, "message", exc)),
            dict(getattr(exc, "details", {}) or {}),
            exit_code=int(getattr(exc, "exit_code", 2)),
        )
    return emit_success(command, value)
