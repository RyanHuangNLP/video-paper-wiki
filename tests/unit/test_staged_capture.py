from __future__ import annotations
import copy, hashlib, os, shutil, stat
from pathlib import Path
import pytest
from tests.support import make_checkout, staged_pdf_capture_input
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.staged_capture import inspect_staged_pdf_capture, validate_staged_pdf_capture_request
from video_paper_wiki.transaction_staging import encode_transaction_inspect_bundle

UPSTREAM = Path(__file__).resolve().parents[2] / "vendor/claude-obsidian"

def setup_case(tmp_path, monkeypatch):
    checkout=tmp_path/'checkout'; checkout.mkdir(); make_checkout(checkout); monkeypatch.chdir(checkout)
    request_path,data,request=staged_pdf_capture_input(checkout)
    vault=tmp_path/'vault'; (vault/'.obsidian').mkdir(parents=True)
    return checkout,request_path,data,request,vault

def replace_directory(path: Path) -> None:
    displaced=path.with_name(path.name+'-displaced')
    path.rename(displaced)
    shutil.copytree(displaced,path,copy_function=shutil.copy2)

def replace_file(path: Path) -> None:
    raw=path.read_bytes(); mode=stat.S_IMODE(path.stat().st_mode)
    path.unlink(); path.write_bytes(raw); os.chmod(path,mode)

def test_request_deep_copy_and_correlation():
    import json
    value=json.loads((Path('tests/fixtures/contracts/valid/video-paper-wiki.staged-pdf-capture-request.v1.json')).read_text())
    out=validate_staged_pdf_capture_request(value); out['plan']['file']='x'
    assert value['plan']['file']=='plan/ingest-plan.v1.json'
    value['payload']['sha256']='a'*64
    with pytest.raises(ContractError) as exc: validate_staged_pdf_capture_request(value)
    assert exc.value.code=='STAGED_CAPTURE_REQUEST_MISMATCH'

def test_shared_encoder_exact_bytes_and_shape():
    digest='a'*64; target=f'.raw/captured/{digest}.pdf'
    material={'operation_id':'op','operation_type':'capture','writes':[{'path':target,'mode':'create','sha256':digest}], 'expected_hashes':{target:None},'read_preconditions':{}}
    raw=encode_transaction_inspect_bundle(material)
    assert raw == (b'{"address_requests":[],"expected_hashes":{".raw/captured/'+digest.encode()+b'.pdf":null},"operation_id":"op","operation_type":"capture","read_preconditions":{},"schema":"claude-obsidian.transaction.v1","source_manifest_updates":{},"writes":[{"content_file":"content/'+digest.encode()+b'","mode":"create","path":".raw/captured/'+digest.encode()+b'.pdf","sha256":"'+digest.encode()+b'"}]}')
    for bad in ({**material,'extra':1},{**material,'writes':tuple(material['writes'])},{**material,'operation_id':True}):
        with pytest.raises(ContractError): encode_transaction_inspect_bundle(bad)
    cycle={}; cycle['cycle']=cycle
    for bad in (cycle, {**material, 'expected_hashes': {target: 1.0}},
                {**material, 'read_preconditions': {1: None}}):
        with pytest.raises(ContractError) as exc: encode_transaction_inspect_bundle(bad)
        assert exc.value.code == 'SCHEMA_INVALID'

def test_reuse_is_noop_and_preserves_real_suffix(tmp_path, monkeypatch):
    checkout,prepared,data,request,vault=setup_case(tmp_path,monkeypatch)
    digest=request['payload']['sha256']; captured=vault/'.raw/captured'; captured.mkdir(parents=True)
    sibling=captured/f'{digest}.legacy.pdf'; sibling.write_bytes(data); os.chmod(sibling,0o640)
    before={p.relative_to(checkout).as_posix():p.read_bytes() for p in checkout.rglob('*') if p.is_file()}
    result=inspect_staged_pdf_capture(prepared=prepared,operation_id='reuse-op',upstream_root=UPSTREAM,vault_root=vault)
    assert result['disposition']=='reuse'; assert result['requested_operation_id']=='reuse-op'
    assert result['transaction_staging'] is None and result['upstream_authority'] is None
    assert result['inspection']['stored_path'].endswith('.legacy.pdf')
    after={p.relative_to(checkout).as_posix():p.read_bytes() for p in checkout.rglob('*') if p.is_file()}
    assert before==after

def test_multiple_matching_siblings_refused(tmp_path,monkeypatch):
    _c,prepared,data,request,vault=setup_case(tmp_path,monkeypatch)
    d=request['payload']['sha256']; cap=vault/'.raw/captured'; cap.mkdir(parents=True)
    for suffix in ('pdf','old.pdf'): (cap/f'{d}.{suffix}').write_bytes(data)
    with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_create_child_failure_leaves_reusable_transport(tmp_path,monkeypatch):
    checkout,prepared,data,request,vault=setup_case(tmp_path,monkeypatch)
    def fail(*a,**k): raise ContractError('UPSTREAM_EXIT_NONZERO','failed')
    monkeypatch.setattr('video_paper_wiki.staged_capture.inspect_pinned_transaction',fail)
    with pytest.raises(ContractError): inspect_staged_pdf_capture(prepared=prepared,operation_id='retry-op',upstream_root=UPSTREAM,vault_root=vault)
    d=request['payload']['sha256']; transport=checkout/'.work/staged-pdf/transaction-inspect'
    assert (transport/'content'/d).read_bytes()==data
    assert (transport/'bundle.json').is_file()

def test_capture_directory_replacement_after_staging_is_refused(tmp_path,monkeypatch):
    _checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    raw=vault/'.raw'; captured=raw/'captured'; captured.mkdir(parents=True)
    from video_paper_wiki.staged_capture import _stage_transaction_inspect_transport as real
    def replace(*a,**k):
        value=real(*a,**k); captured.rename(raw/'old'); captured.mkdir(); return value
    monkeypatch.setattr('video_paper_wiki.staged_capture._stage_transaction_inspect_transport',replace)
    with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='race-op',upstream_root=UPSTREAM,vault_root=vault)
    assert exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_batch_replacement_after_real_staging_is_refused(tmp_path,monkeypatch):
    checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    batch=checkout/'.work/staged-pdf'
    from video_paper_wiki.staged_capture import _stage_transaction_inspect_transport as real
    def replace(*a,**k):
        value=real(*a,**k); batch.rename(checkout/'.work/old-batch'); batch.mkdir(); return value
    monkeypatch.setattr('video_paper_wiki.staged_capture._stage_transaction_inspect_transport',replace)
    with pytest.raises(Exception) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='race-op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

def test_request_same_bytes_new_inode_after_real_child_is_refused(tmp_path,monkeypatch):
    _checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    from video_paper_wiki.staged_capture import inspect_pinned_transaction as real
    def replace(*a,**k):
        value=real(*a,**k); raw=prepared.read_bytes(); prepared.unlink(); prepared.write_bytes(raw); return value
    monkeypatch.setattr('video_paper_wiki.staged_capture.inspect_pinned_transaction',replace)
    with pytest.raises(Exception) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='race-op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

def test_request_read_close_to_named_stat_replacement_is_refused(tmp_path,monkeypatch):
    _checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    from video_paper_wiki import staged_capture as module
    real=module._read_regular_file_at_bounded_identity
    def replace(parent_fd,name,path,**kwargs):
        value=real(parent_fd,name,path,**kwargs)
        if name=='staged-pdf-capture-request.v1.json':
            raw=prepared.read_bytes(); prepared.unlink(); prepared.write_bytes(raw)
        return value
    monkeypatch.setattr(module,'_read_regular_file_at_bounded_identity',replace)
    with pytest.raises(Exception) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='race-op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

def test_malformed_request_precedes_missing_plan(tmp_path,monkeypatch):
    checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    plan=checkout/'.work/staged-pdf/plan/ingest-plan.v1.json'; plan.unlink(); plan.parent.rmdir()
    prepared.write_bytes(b'{')
    with pytest.raises(Exception) as exc:
        inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='SCHEMA_INVALID'

def test_schema_invalid_canonical_request_precedes_missing_plan(tmp_path,monkeypatch):
    checkout,prepared,_data,request,vault=setup_case(tmp_path,monkeypatch)
    from video_paper_wiki.jcs import canonicalize
    plan=checkout/'.work/staged-pdf/plan/ingest-plan.v1.json'; plan.unlink(); plan.parent.rmdir()
    invalid=copy.deepcopy(request); del invalid['approval_ref_sha256']
    prepared.write_bytes(canonicalize(invalid))
    with pytest.raises(ContractError) as exc:
        inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert exc.value.code=='SCHEMA_INVALID'

def test_request_parse_error_with_prepared_replacement_returns_work_path_unsafe(
    tmp_path,monkeypatch
):
    _checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    prepared.write_bytes(b'{')
    from video_paper_wiki import staged_capture as module
    real=module.parse_strict_json
    def replace(raw,**kwargs):
        replace_directory(prepared.parent)
        return real(raw,**kwargs)
    monkeypatch.setattr(module,'parse_strict_json',replace)
    with pytest.raises(Exception) as exc:
        inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

def test_request_semantic_error_with_prepared_replacement_returns_work_path_unsafe(
    tmp_path,monkeypatch
):
    _checkout,prepared,_data,request,vault=setup_case(tmp_path,monkeypatch)
    from video_paper_wiki.jcs import canonicalize
    invalid=copy.deepcopy(request); invalid['approval_ref_sha256']='0'*64
    prepared.write_bytes(canonicalize(invalid))
    from video_paper_wiki import staged_capture as module
    real=module.validate_staged_pdf_capture_request
    def replace(value):
        replace_directory(prepared.parent)
        return real(value)
    monkeypatch.setattr(module,'validate_staged_pdf_capture_request',replace)
    with pytest.raises(Exception) as exc:
        inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

def test_request_validation_error_with_request_replacement_returns_work_path_unsafe(
    tmp_path,monkeypatch
):
    _checkout,prepared,_data,request,vault=setup_case(tmp_path,monkeypatch)
    from video_paper_wiki.jcs import canonicalize
    invalid=copy.deepcopy(request); invalid['approval_ref_sha256']='0'*64
    prepared.write_bytes(canonicalize(invalid))
    from video_paper_wiki import staged_capture as module
    real=module.validate_staged_pdf_capture_request
    def replace(value):
        replace_file(prepared)
        return real(value)
    monkeypatch.setattr(module,'validate_staged_pdf_capture_request',replace)
    with pytest.raises(Exception) as exc:
        inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

@pytest.mark.parametrize('slot',['directory','file'])
def test_plan_error_with_named_replacement_returns_work_path_unsafe(
    tmp_path,monkeypatch,slot
):
    checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    plan=checkout/'.work/staged-pdf/plan/ingest-plan.v1.json'; plan_bytes=plan.read_bytes()
    from video_paper_wiki import staged_capture as module
    real=module.parse_strict_json
    def replace(raw,**kwargs):
        if raw==plan_bytes:
            replace_directory(plan.parent) if slot=='directory' else replace_file(plan)
            raise ContractError('SCHEMA_INVALID','injected plan error')
        return real(raw,**kwargs)
    monkeypatch.setattr(module,'parse_strict_json',replace)
    with pytest.raises(Exception) as exc:
        inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

def test_unchanged_cross_field_invalid_request_preserves_request_mismatch(
    tmp_path,monkeypatch
):
    _checkout,prepared,_data,request,vault=setup_case(tmp_path,monkeypatch)
    from video_paper_wiki.jcs import canonicalize
    invalid=copy.deepcopy(request); invalid['approval_ref_sha256']='0'*64
    prepared.write_bytes(canonicalize(invalid))
    with pytest.raises(ContractError) as exc:
        inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert exc.value.code=='STAGED_CAPTURE_REQUEST_MISMATCH'

def test_plan_semantic_error_precedes_missing_blob(tmp_path,monkeypatch):
    checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    import json
    from video_paper_wiki.jcs import canonicalize
    plan_path=checkout/'.work/staged-pdf/plan/ingest-plan.v1.json'
    plan=json.loads(plan_path.read_bytes()); plan['limits']['max_pages']=0
    plan_path.write_bytes(canonicalize(plan)); (prepared.parent/_request['payload']['file'].split('/',1)[1]).unlink()
    with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert exc.value.code=='SCHEMA_INVALID'

def test_downstream_error_plus_input_drift_returns_input_error(tmp_path,monkeypatch):
    _checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    def fail(*a,**k):
        raw=prepared.read_bytes(); prepared.unlink(); prepared.write_bytes(raw)
        raise ContractError('PDF_INVALID','downstream')
    monkeypatch.setattr('video_paper_wiki.commands.prepare._validate_paper_blob',fail)
    with pytest.raises(Exception) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert getattr(exc.value,'code',None)=='WORK_PATH_UNSAFE'

def test_invalid_root_shape_precedes_missing_prepared_session(tmp_path,monkeypatch):
    checkout=tmp_path/'checkout'; checkout.mkdir(); make_checkout(checkout); monkeypatch.chdir(checkout)
    monkeypatch.setattr('video_paper_wiki.staged_capture._open_batch_session',lambda *a,**k: (_ for _ in ()).throw(AssertionError('session opened')))
    with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(
        prepared=checkout/'.work/missing/prepared/staged-pdf-capture-request.v1.json',
        operation_id='op', upstream_root=[], vault_root=tmp_path/'missing-vault')
    assert exc.value.code=='ADAPTER_PATH_INVALID'

def test_downstream_error_plus_captured_drift_returns_snapshot_error(tmp_path,monkeypatch):
    _checkout,prepared,_data,_request,vault=setup_case(tmp_path,monkeypatch)
    raw=vault/'.raw'; captured=raw/'captured'; captured.mkdir(parents=True)
    def fail(*a,**k):
        captured.rename(raw/'old'); captured.mkdir()
        raise ContractError('DOWNSTREAM_FAILED','downstream')
    monkeypatch.setattr('video_paper_wiki.staged_capture._stage_transaction_inspect_transport',fail)
    with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=prepared,operation_id='op',upstream_root=UPSTREAM,vault_root=vault)
    assert exc.value.code=='CAPTURE_SNAPSHOT_INVALID'
