from pathlib import Path
import os, pytest
from tests.support import make_checkout, staged_pdf_capture_input
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.staged_capture import inspect_staged_pdf_capture
from video_paper_wiki.cli import main
UPSTREAM=Path(__file__).resolve().parents[2]/'vendor/claude-obsidian'

def case(tmp_path,monkeypatch):
 c=tmp_path/'c'; c.mkdir(); make_checkout(c); monkeypatch.chdir(c); p,data,r=staged_pdf_capture_input(c); v=tmp_path/'v'; (v/'.obsidian').mkdir(parents=True); return c,p,data,r,v

def test_reuse_attempts_no_process_network_or_write(tmp_path,monkeypatch):
 c,p,data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True); (cap/f'{d}.pdf').write_bytes(data)
 def boom(*a,**k): raise AssertionError('forbidden effect')
 for name in ('_proposal','encode_transaction_inspect_bundle','_stage_transaction_inspect_transport','inspect_pinned_transaction'):
  monkeypatch.setattr('video_paper_wiki.staged_capture.'+name,boom)
 monkeypatch.setattr('subprocess.Popen',boom); monkeypatch.setattr('subprocess.run',boom); monkeypatch.setattr('socket.socket',boom)
 def snapshot(root):
  return {(p.relative_to(root).as_posix(),p.lstat().st_ino,p.lstat().st_mode): (p.read_bytes() if p.is_file() else None) for p in root.rglob('*')}
 before_checkout=snapshot(c); before_vault=snapshot(v)
 out=inspect_staged_pdf_capture(prepared=p,operation_id='op',upstream_root=UPSTREAM,vault_root=v)
 assert out['disposition']=='reuse'
 assert snapshot(c)==before_checkout and snapshot(v)==before_vault

def test_matching_symlink_and_directory_refused(tmp_path,monkeypatch):
 c,p,data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True)
 outside=tmp_path/'outside'; outside.write_bytes(data); (cap/f'{d}.pdf').symlink_to(outside)
 with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=p,operation_id='op',upstream_root=UPSTREAM,vault_root=v)
 assert exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

@pytest.mark.parametrize('kind',['directory','fifo','wrong-bytes','malformed'])
def test_matching_unsafe_entries_are_refused(tmp_path,monkeypatch,kind):
 c,p,data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True); target=cap/f'{d}.pdf'
 if kind=='directory': target.mkdir()
 elif kind=='fifo': os.mkfifo(target)
 elif kind=='wrong-bytes': target.write_bytes(b'wrong')
 else: target=cap/f'{d}.'; target.write_bytes(data)
 with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=p,operation_id='op',upstream_root=UPSTREAM,vault_root=v)
 assert exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_capture_entry_limit_is_closed(tmp_path,monkeypatch):
 c,p,data,r,v=case(tmp_path,monkeypatch); cap=v/'.raw/captured'; cap.mkdir(parents=True)
 for index in range(1025): (cap/f'x{index}').write_bytes(b'')
 with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=p,operation_id='op',upstream_root=UPSTREAM,vault_root=v)
 assert exc.value.code=='UPSTREAM_LIMIT_EXCEEDED'

def test_initial_scan_lineage_drift_overrides_entry_limit(tmp_path,monkeypatch):
 _c,_p,_data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True)
 for index in range(1025): (cap/f'x{index}').write_bytes(b'')
 from video_paper_wiki import captured_snapshot as module
 real=module._scan; attacked=False
 def replace(fd,digest):
  nonlocal attacked
  if not attacked:
   attacked=True; cap.rename(v/'.raw/captured-old'); cap.mkdir()
  return real(fd,digest)
 monkeypatch.setattr(module,'_scan',replace)
 with pytest.raises(ContractError) as exc:
  with module.capture_snapshot(v,d): pass
 assert attacked and exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_verify_rescan_lineage_drift_overrides_entry_limit(tmp_path,monkeypatch):
 _c,_p,_data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True)
 for index in range(1025): (cap/f'x{index}').write_bytes(b'')
 from video_paper_wiki import captured_snapshot as module
 real=module._scan; calls=0
 def replace(fd,digest):
  nonlocal calls
  calls+=1
  if calls==1: return (),None,b''
  if calls==2: cap.rename(v/'.raw/captured-old'); cap.mkdir()
  return real(fd,digest)
 monkeypatch.setattr(module,'_scan',replace)
 with pytest.raises(ContractError) as exc:
  with module.capture_snapshot(v,d): pass
 assert calls==2 and exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_successful_initial_scan_rechecks_persistent_lineage_replacement(tmp_path,monkeypatch):
 _c,_p,_data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True)
 from video_paper_wiki import captured_snapshot as module
 real=module._scan; attacked=False
 def replace(fd,digest):
  nonlocal attacked
  value=real(fd,digest)
  if not attacked:
   attacked=True; cap.rename(v/'.raw/captured-old'); cap.mkdir()
  return value
 monkeypatch.setattr(module,'_scan',replace)
 with pytest.raises(ContractError) as exc:
  with module.capture_snapshot(v,d): pass
 assert attacked and exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_direct_snapshot_verify_maps_persistent_vault_rename(tmp_path,monkeypatch):
 _c,_p,_data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; (v/'.raw/captured').mkdir(parents=True)
 from video_paper_wiki import captured_snapshot as module
 with pytest.raises(ContractError) as exit_exc:
  with module.capture_snapshot(v,d) as snapshot:
   v.rename(tmp_path/'vault-old')
   with pytest.raises(ContractError) as direct_exc: snapshot.verify()
   assert direct_exc.value.code=='CAPTURE_SNAPSHOT_INVALID'
 assert exit_exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_initial_scan_has_lineage_checks_before_and_after(tmp_path,monkeypatch):
 _c,_p,_data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; (v/'.raw/captured').mkdir(parents=True)
 from video_paper_wiki import captured_snapshot as module
 real_verify=module._verify_directory_lineage; real_scan=module._scan; events=[]
 def verify(*args,**kwargs): events.append('verify'); return real_verify(*args,**kwargs)
 def scan(*args,**kwargs): events.append('scan'); return real_scan(*args,**kwargs)
 monkeypatch.setattr(module,'_verify_directory_lineage',verify); monkeypatch.setattr(module,'_scan',scan)
 with module.capture_snapshot(v,d):
  assert events[:3]==['verify','scan','verify']

def test_successful_verify_rescan_rechecks_persistent_lineage_replacement(tmp_path,monkeypatch):
 _c,_p,_data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True)
 from video_paper_wiki import captured_snapshot as module
 real=module._scan; calls=0
 def replace(fd,digest):
  nonlocal calls
  calls+=1; value=real(fd,digest)
  if calls==2:
   cap.rename(v/'.raw/captured-old'); cap.mkdir()
  return value
 monkeypatch.setattr(module,'_scan',replace)
 with pytest.raises(ContractError) as exc:
  with module.capture_snapshot(v,d): pass
 assert calls==2 and exc.value.code=='CAPTURE_SNAPSHOT_INVALID'

def test_matching_file_open_is_nonblocking() -> None:
 from video_paper_wiki.captured_snapshot import _file_flags
 assert not hasattr(os,'O_NONBLOCK') or _file_flags() & os.O_NONBLOCK

def test_fixed_prepared_path_only(tmp_path,monkeypatch):
 c,p,data,r,v=case(tmp_path,monkeypatch)
 with pytest.raises(ContractError) as exc: inspect_staged_pdf_capture(prepared=p.parent/(r['payload']['sha256']+'.blob'),operation_id='op',upstream_root=UPSTREAM,vault_root=v)
 assert exc.value.code=='ADAPTER_PATH_INVALID'

def test_cli_has_only_four_required_capture_flags(tmp_path,monkeypatch,capsys):
 c,p,data,r,v=case(tmp_path,monkeypatch); d=r['payload']['sha256']; cap=v/'.raw/captured'; cap.mkdir(parents=True); (cap/f'{d}.pdf').write_bytes(data)
 argv=['capture','inspect','--prepared',str(p),'--operation-id','cli-op','--upstream-root',str(UPSTREAM),'--vault-root',str(v)]
 assert main(argv)==0
 import json
 envelope=json.loads(capsys.readouterr().out)
 assert envelope['ok'] is True and envelope['data']['disposition']=='reuse'
 for flag in ('--batch-id','--apply','--target','--network'):
  assert main(argv+[flag,'x'])==2
  assert json.loads(capsys.readouterr().out)['error']['code']=='USAGE'
