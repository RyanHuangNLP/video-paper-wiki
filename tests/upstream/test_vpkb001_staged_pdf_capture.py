from pathlib import Path
from tests.support import make_checkout, staged_pdf_capture_input
from video_paper_wiki.staged_capture import inspect_staged_pdf_capture
from video_paper_wiki.staged_capture import validate_staged_pdf_capture_authority
from video_paper_wiki.contracts import ContractError
import copy, pytest
UPSTREAM=Path(__file__).resolve().parents[2]/'vendor/claude-obsidian'

def test_create_uses_real_pinned_read_only_inspect_and_reuses_staging(tmp_path,monkeypatch):
 c=tmp_path/'checkout'; c.mkdir(); make_checkout(c); monkeypatch.chdir(c)
 prepared,data,request=staged_pdf_capture_input(c); vault=tmp_path/'vault'; (vault/'.obsidian').mkdir(parents=True)
 first=inspect_staged_pdf_capture(prepared=prepared,operation_id='capture-pdf',upstream_root=UPSTREAM,vault_root=vault)
 assert first['disposition']=='create'; assert first['transaction_staging']['already_staged'] is False
 assert first['upstream_authority']['transaction']['phase']=='inspected'
 assert not (vault/'.raw/captured').exists()
 second=inspect_staged_pdf_capture(prepared=prepared,operation_id='capture-pdf',upstream_root=UPSTREAM,vault_root=vault)
 assert second['transaction_staging']['already_staged'] is True
 assert second['upstream_authority']==first['upstream_authority']

def test_create_authority_crossed_staging_type_and_profile_io_are_refused_or_absent(tmp_path,monkeypatch):
 c=tmp_path/'checkout'; c.mkdir(); make_checkout(c); monkeypatch.chdir(c)
 prepared,_data,_request=staged_pdf_capture_input(c); vault=tmp_path/'vault'; (vault/'.obsidian').mkdir(parents=True)
 authority=inspect_staged_pdf_capture(prepared=prepared,operation_id='capture-pdf',upstream_root=UPSTREAM,vault_root=vault)
 monkeypatch.setattr('video_paper_wiki.upstream_adapter._profile',lambda: (_ for _ in ()).throw(AssertionError('profile I/O')))
 assert validate_staged_pdf_capture_authority(authority)==authority
 crossed=copy.deepcopy(authority); crossed['transaction_staging']['operation_type']='ingest'
 with pytest.raises(ContractError) as exc: validate_staged_pdf_capture_authority(crossed)
 assert exc.value.code=='STAGED_CAPTURE_RESULT_MISMATCH'
