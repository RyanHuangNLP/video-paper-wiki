from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import json
from pathlib import Path


def _module():
    path = Path("operator/src/video_paper_wiki_operator/cli.py")
    spec = importlib.util.spec_from_file_location("vpwiki_operator_cli_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_index_query_preserves_upstream_global_option_order(monkeypatch, tmp_path):
    module = _module()
    root = tmp_path / "upstream"
    (root / "scripts").mkdir(parents=True)
    observed = []
    monkeypatch.setattr(module, "_verified_root", lambda _raw: root)
    monkeypatch.setattr(module, "_confirm", lambda _words: (_ for _ in ()).throw(AssertionError("read-only query asked for confirmation")))
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **_kwargs: observed.append(argv) or subprocess.CompletedProcess(argv, 0))
    assert module.main(["--upstream-root", str(root), "index", "--vault", "/v", "query", "paper"]) == 0
    assert observed == [[sys.executable, "-I", "-B", "-X", "utf8", str(root / "scripts" / "bm25-index.py"), "--vault", "/v", "query", "paper"]]


def test_index_build_requires_confirmation(monkeypatch, tmp_path):
    module = _module(); root = tmp_path / "upstream"; (root / "scripts").mkdir(parents=True)
    monkeypatch.setattr(module, "_verified_root", lambda _raw: root)
    monkeypatch.setattr(module, "_confirm", lambda words: (_ for _ in ()).throw(AssertionError("disabled alias asked for confirmation")))
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0))
    assert module.main(["--upstream-root", str(root), "index", "--vault", "/v", "build"]) == 2


def test_catalog_build_exact_surface_confirms_before_authentication(monkeypatch,tmp_path):
    module=_module();root=tmp_path/"upstream";observed=[];config=tmp_path/'policy.json'
    config.write_text(json.dumps({'schema':'video-paper-wiki.retrieval-policy.v1','corpus_version':'c','query_version':'q','top_chunks':10,'top_papers':10,'evidence_limit':8,'per_paper_evidence_limit':2,'eligibility':'active-not-deprecated','paper_tie_break':'score-desc-paper-id-asc','chunk_tie_break':'score-desc-paper-id-asc-chunk-id-asc'}))
    monkeypatch.setattr(module,"_confirm",lambda words:False)
    monkeypatch.setattr(module,"_verified_root",lambda _raw:(_ for _ in ()).throw(AssertionError("pin checked before TTY confirmation")))
    assert module.main(["catalog","build","--vault-root","/v","--upstream-root",str(root),"--config",str(config)])==2

    monkeypatch.setattr(module,"_confirm",lambda words:True)
    monkeypatch.setattr(module,"_verified_root",lambda _raw:root)
    monkeypatch.setattr("video_paper_wiki.catalog_store.build_current_catalog",lambda **kw:observed.append(kw))
    assert module.main(["catalog","build","--vault-root","/v","--upstream-root",str(root),"--config",str(config)])==0
    assert observed and observed[0]['vault_root']=='/v' and observed[0]['upstream_root']==root
    assert observed[0]['retrieval_config']['schema']=='video-paper-wiki.retrieval-policy.v1'


def test_index_vault_after_action_and_query_words_are_read_only(monkeypatch, tmp_path):
    module = _module(); root = tmp_path / "upstream"; (root / "scripts").mkdir(parents=True); observed=[]
    monkeypatch.setattr(module, "_verified_root", lambda _raw: root)
    monkeypatch.setattr(module, "_confirm", lambda _words: (_ for _ in ()).throw(AssertionError("query asked for confirmation")))
    monkeypatch.setattr(module.subprocess, "run", lambda argv, **_kwargs: observed.append(argv) or subprocess.CompletedProcess(argv, 0))
    for text in ("build", "query", "stats"):
        assert module.main(["--upstream-root",str(root),"index","query","--vault","/v",text]) == 0
    assert all(argv[-3:-1] == ["query", "--vault"] or "query" in argv for argv in observed)


def test_gate_apply_non_tty_and_second_observation_drift_are_closed(monkeypatch,tmp_path,capsys):
    module=_module();root=tmp_path/'upstream';monkeypatch.setattr(module,'_verified_root',lambda _raw:root)
    class Held:
        def __init__(self,*_a,**_kw):pass
        def verify(self):pass
        def close(self):pass
    monkeypatch.setattr('video_paper_wiki.gate_decision._Prepared',Held)
    monkeypatch.setattr('video_paper_wiki.receipt_audit._Snapshot',Held)
    class Bundle:
        def __enter__(self):return tmp_path/'bundle.json'
        def verify(self):pass
        def close(self):pass
        def __exit__(self,*_a):return False
    monkeypatch.setattr('video_paper_wiki.gate_decision._retained_gate_bundle',lambda *_a,**_kw:Bundle())
    tx={'inspection':{'approval_sha256':'a'*64}};base={'publication_authority':{'transaction':tx,'upstream_authority':{'transaction':tx}}}
    calls=[]
    def inspect_base(**kw):
        calls.append(kw)
        if kw.get('_apply_holder_out') is not None:kw['_apply_holder_out'].append((Bundle(),tmp_path/'bundle.json'))
        return base
    monkeypatch.setattr('video_paper_wiki.gate_decision.inspect_gate',inspect_base)
    monkeypatch.setattr(module,'_confirm',lambda _words:False)
    argv=['gate','apply','--prepared','p','--operation-id','g','--upstream-root',str(root),'--vault-root','v','--approved-plan-sha256','a'*64]
    assert module.main(argv)==2;assert len(calls)==1
    assert json.loads(capsys.readouterr().out)['error']['code']=='HUMAN_APPROVAL_REQUIRED'
    changed={**base,'changed':True};calls.clear();observations=iter((base,changed));monkeypatch.setattr(module,'_confirm',lambda _words:True)
    def inspect_changed(**kw):
        calls.append(kw)
        if kw.get('_apply_holder_out') is not None:kw['_apply_holder_out'].append((Bundle(),tmp_path/'bundle.json'))
        return next(observations)
    monkeypatch.setattr('video_paper_wiki.gate_decision.inspect_gate',inspect_changed)
    assert module.main(argv)==2;assert len(calls)==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='GATE_STATE_INVALID'


def test_backup_create_observes_manifest_before_confirmation(monkeypatch,tmp_path,capsys):
    module=_module();manifest=tmp_path/'manifest.json';manifest.write_text('{}');calls=[];vault=tmp_path/'vault';vault.mkdir()
    monkeypatch.setattr('video_paper_wiki.backup_manifest.build_backup_manifest',lambda root,**kw:calls.append(root) or {})
    monkeypatch.setattr(module,'_confirm',lambda _words:False)
    assert module.main(['backup','create','--vault-root',str(vault),'--manifest',str(manifest),'--destination',str(tmp_path/'a.zip')])==2
    assert calls==[str(vault)] and json.loads(capsys.readouterr().out)['error']['code']=='HUMAN_APPROVAL_REQUIRED'


def test_backup_restore_missing_source_root_is_stable_usage_error(capsys):
    module=_module()
    assert module.main(['backup','restore','--archive','a','--restore-root','r','--manifest','m',
        '--upstream-root','u','--config','c'])==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='USAGE_INVALID'


def test_backup_create_retains_manifest_named_identity_across_confirmation(monkeypatch,tmp_path,capsys):
    module=_module();manifest=tmp_path/'manifest.json';manifest.write_text('{}');vault=tmp_path/'vault';vault.mkdir();called=[]
    monkeypatch.setattr('video_paper_wiki.backup_manifest.build_backup_manifest',lambda root,**kw:{})
    monkeypatch.setattr('video_paper_wiki.backup_archive.create_backup_archive',lambda **kw:called.append(kw) or {})
    def replace(_words):
        replacement=manifest.with_suffix('.new');replacement.write_bytes(manifest.read_bytes());os.replace(replacement,manifest);return True
    monkeypatch.setattr(module,'_confirm',replace)
    assert module.main(['backup','create','--vault-root',str(vault),'--manifest',str(manifest),
        '--destination',str(tmp_path/'a.zip')])==2
    assert called==[] and json.loads(capsys.readouterr().out)['error']['code']=='BACKUP_RACE'


def test_backup_create_retains_destination_parent_across_confirmation(monkeypatch,tmp_path,capsys):
    module=_module();manifest=tmp_path/'manifest.json';manifest.write_text('{}');vault=tmp_path/'vault';vault.mkdir();dest=tmp_path/'dest';dest.mkdir();called=[]
    monkeypatch.setattr('video_paper_wiki.backup_manifest.build_backup_manifest',lambda root,**kw:{})
    monkeypatch.setattr('video_paper_wiki.backup_archive.create_backup_archive',lambda **kw:called.append(kw) or {})
    def replace(_words):
        moved=tmp_path/'dest-old';dest.rename(moved);dest.mkdir();return True
    monkeypatch.setattr(module,'_confirm',replace)
    assert module.main(['backup','create','--vault-root',str(vault),'--manifest',str(manifest),
        '--destination',str(dest/'a.zip')])==2
    assert called==[] and json.loads(capsys.readouterr().out)['error']['code']=='BACKUP_RACE'


def test_gate_apply_retains_first_prepared_identity_across_prompt(monkeypatch,tmp_path,capsys):
    module=_module();from tests.support import make_checkout
    from video_paper_wiki import gate_decision as gate
    from video_paper_wiki.identity import gate_event_id
    from video_paper_wiki.jcs import canonicalize
    checkout=tmp_path/'checkout';checkout.mkdir();make_checkout(checkout);monkeypatch.chdir(checkout);vault=tmp_path/'vault';vault.mkdir()
    manifest=canonicalize({'papers':3,'repositories':5});decision={'schema':'video-paper-wiki.gate-decision.v1','gate_id':gate.GATE,
        'event_id':'gde-'+'0'*20,'previous_event_id':None,'actor_kind':'human','choice':'keep-modelscope',
        'baseline_manifest_sha256':__import__('hashlib').sha256(manifest).hexdigest(),'derived_full_map_repo_ids':gate.CHOICES['keep-modelscope'],
        'decided_by':'synthetic-test-only','decided_at':'2026-09-02T00:00:00Z','reason':'mechanical fixture'}
    decision['event_id']=gate_event_id(decision);d=tmp_path/'decision.json';m=tmp_path/'manifest.json';d.write_bytes(canonicalize(decision));m.write_bytes(manifest)
    prepared=Path(gate.prepare_gate(decision_path=d,baseline_manifest_path=m,batch_id='gate-prompt')['request_path'])
    base=checkout/'.work/gate-prompt';pcontent=base/'publication-input/content';tcontent=base/'transaction-inspect/content';pcontent.mkdir(parents=True);tcontent.mkdir(parents=True)
    import hashlib
    pdata=b'publication';pd=hashlib.sha256(pdata).hexdigest();(pcontent/pd).write_bytes(pdata);(pcontent.parent/'knowledge-publication-request.v1.json').write_bytes(b'{}')
    tdata=b'transaction';td=hashlib.sha256(tdata).hexdigest();(tcontent/td).write_bytes(tdata);bundle=b'{}';(tcontent.parent/'bundle.json').write_bytes(bundle)
    staging={'batch_id':'gate-prompt','bundle_file':'transaction-inspect/bundle.json','bundle_sha256':hashlib.sha256(bundle).hexdigest(),
        'bundle_size_bytes':len(bundle),'content_files':[{'content_file':f'transaction-inspect/content/{td}','sha256':td,'size_bytes':len(tdata)}]}
    tx={'inspection':{'approval_sha256':'a'*64}}
    authority={'publication_authority':{'transaction':tx,'transaction_staging':staging,'request':{'payloads':[{'content_file':f'publication-input/content/{pd}'}]}}}
    monkeypatch.setattr(module,'_verified_root',lambda _raw:tmp_path/'upstream')
    class Bundle:
        def verify(self):pass
        def close(self):pass
        def __exit__(self,*_a):return False
    def inspected(**kw):
        if kw.get('_apply_holder_out') is not None:kw['_apply_holder_out'].append((Bundle(),tmp_path/'bundle.json'))
        return authority
    monkeypatch.setattr(gate,'inspect_gate',inspected);monkeypatch.setattr(gate,'validate_document',lambda value,_schema:value)
    calls=[];monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:calls.append(a) or subprocess.CompletedProcess(a,0))
    def replace(_words):
        replacement=prepared.with_suffix('.new');replacement.write_bytes(prepared.read_bytes());os.replace(replacement,prepared);return True
    monkeypatch.setattr(module,'_confirm',replace)
    argv=['gate','apply','--prepared',str(prepared),'--operation-id','gate-prompt','--upstream-root','u','--vault-root',str(vault),'--approved-plan-sha256','a'*64]
    assert module.main(argv)==2 and calls==[]
    assert json.loads(capsys.readouterr().out)['error']['code']=='GATE_PATH_UNSAFE'


def test_gate_apply_child_error_rechecks_first_vault_authority(monkeypatch,tmp_path,capsys):
    module=_module();root=tmp_path/'upstream';drift={'value':False};closed=[]
    monkeypatch.setattr(module,'_verified_root',lambda _raw:root)
    class Prepared:
        def __init__(self,*_a,**_kw):pass
        def verify(self):pass
        def close(self):closed.append('prepared')
    class Vault:
        def __init__(self,*_a,**_kw):pass
        def verify(self):
            if drift['value']:
                from video_paper_wiki.contracts import ContractError
                raise ContractError('AUDIT_RACE','same-byte Vault edge replacement')
        def close(self):closed.append('vault')
    class Bundle:
        def __enter__(self):return tmp_path/'bundle.json'
        def __exit__(self,*_a):return False
    tx={'inspection':{'approval_sha256':'a'*64}}
    authority={'publication_authority':{'transaction':tx}}
    monkeypatch.setattr('video_paper_wiki.gate_decision._Prepared',Prepared)
    monkeypatch.setattr('video_paper_wiki.receipt_audit._Snapshot',Vault)
    monkeypatch.setattr('video_paper_wiki.gate_decision._retained_gate_bundle',lambda *_a,**_kw:Bundle())
    def inspected(**kw):
        if kw.get('_apply_holder_out') is not None:kw['_apply_holder_out'].append((Bundle(),tmp_path/'bundle.json'))
        return authority
    monkeypatch.setattr('video_paper_wiki.gate_decision.inspect_gate',inspected)
    monkeypatch.setattr('video_paper_wiki.receipt_audit.audit_integrity',lambda *_a,**_kw:{'head':None})
    monkeypatch.setattr(module,'_confirm',lambda _words:True)
    def fail_child(*_a,**_kw):
        drift['value']=True
        return subprocess.CompletedProcess([],1)
    monkeypatch.setattr(module.subprocess,'run',fail_child)
    argv=['gate','apply','--prepared','p','--operation-id','g','--upstream-root',str(root),
        '--vault-root','v','--approved-plan-sha256','a'*64]
    assert module.main(argv)==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='GATE_STATE_INVALID'
    assert sorted(closed)==['prepared','vault']


def test_gate_success_transition_allows_exact_writes_but_rejects_unrelated_inode_aba(tmp_path):
    module=_module();from video_paper_wiki.receipt_audit import _Snapshot
    vault=tmp_path/'vault';mutable=vault/'wiki/meta/registries/gate-heads.json';unrelated=vault/'wiki/papers/held.md'
    for path,data in ((mutable,b'old gate'),(unrelated,b'held paper')):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o600)
    for path in vault.rglob('*'):
        if path.is_dir():path.chmod(0o700)
    snap=_Snapshot(vault)
    try:
        snap.read('wiki/meta/registries/gate-heads.json');snap.read('wiki/papers/held.md')
        replacement=mutable.with_name('replacement');replacement.write_bytes(b'new gate');replacement.chmod(0o600);os.replace(replacement,mutable)
        module._verify_gate_vault_transition(snap,{'wiki/meta/registries/gate-heads.json'})
        replacement=unrelated.with_name('replacement');replacement.write_bytes(b'held paper');replacement.chmod(0o600);os.replace(replacement,unrelated)
        import pytest
        with pytest.raises(Exception) as caught:module._verify_gate_vault_transition(snap,{'wiki/meta/registries/gate-heads.json'})
        assert caught.value.code=='GATE_STATE_INVALID'
    finally:snap.close()


def test_research_backup_usage_errors_stay_stable(capsys):
    module=_module()
    assert module.main(['backup','create','--profile','research-r1','--vault-root','/v','--manifest','/m','--destination','/a'])==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='USAGE_INVALID'
    assert module.main(['backup','create','--checkout-root','/c','--vault-root','/v','--manifest','/m','--destination','/a'])==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='USAGE_INVALID'
    assert module.main(['backup','restore','--profile','research-r1','--archive','/a','--restore-root','/r','--manifest','/m','--upstream-root','/u','--config','/c'])==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='USAGE_INVALID'
    assert module.main(['backup','restore','--profile','research-r1','--source-root','/v','--expected-manifest-sha256','ab'*32,'--archive','/a','--restore-root','/r','--manifest','/m','--upstream-root','/u','--config','/c'])==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='USAGE_INVALID'
    assert module.main(['backup','restore','--source-root','/v','--expected-manifest-sha256','ab'*32,'--archive','/a','--restore-root','/r','--manifest','/m','--upstream-root','/u','--config','/c'])==2
    assert json.loads(capsys.readouterr().out)['error']['code']=='USAGE_INVALID'


def _research_operator_paths(tmp_path):
    from tests.unit.test_research_backup import _checkout, _vault
    from video_paper_wiki.backup_manifest import build_research_backup_manifest
    from video_paper_wiki.jcs import canonicalize
    vault=tmp_path/'vault'; checkout=tmp_path/'checkout'
    _vault(vault); _checkout(checkout)
    manifest=build_research_backup_manifest(vault, checkout)
    path=tmp_path/'manifest.json'
    path.write_bytes(canonicalize(manifest)); path.chmod(0o600)
    dest=tmp_path/'out'/'backup.zip'; dest.parent.mkdir()
    return vault, checkout, path, dest


def test_research_create_non_tty_writes_nothing(tmp_path):
    vault, checkout, manifest, dest = _research_operator_paths(tmp_path)
    root = Path(__file__).resolve().parents[2]
    code = "import sys\nsys.path.insert(0, 'operator/src')\nfrom video_paper_wiki_operator.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"
    argv = [sys.executable, '-c', code, 'backup', 'create', '--profile', 'research-r1', '--vault-root', str(vault), '--checkout-root', str(checkout), '--manifest', str(manifest), '--destination', str(dest)]
    result = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)['error']['code'] == 'HUMAN_APPROVAL_REQUIRED'
    assert not dest.exists()


def test_research_create_accepts_real_pty_confirmation(tmp_path):
    import pty
    vault, checkout, manifest, dest = _research_operator_paths(tmp_path)
    root = Path(__file__).resolve().parents[2]
    code = "import sys\nsys.path.insert(0, 'operator/src')\nfrom video_paper_wiki_operator.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"
    argv = [sys.executable, '-c', code, 'backup', 'create', '--profile', 'research-r1', '--vault-root', str(vault), '--checkout-root', str(checkout), '--manifest', str(manifest), '--destination', str(dest)]
    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, cwd=root, stdin=slave, stdout=subprocess.PIPE, stderr=slave)
    os.close(slave)
    os.write(master, b'backup create\n')
    stdout, _ = proc.communicate(timeout=60)
    os.close(master)
    assert proc.returncode == 0, stdout
    assert json.loads(stdout)['research_validation'] == 'pending'
    assert dest.is_file()


def test_research_create_rejects_manifest_replaced_during_confirmation(monkeypatch, tmp_path, capsys):
    module = _module()
    vault, checkout, manifest, dest = _research_operator_paths(tmp_path)
    def replace(_words):
        replacement = manifest.with_suffix('.new')
        replacement.write_bytes(manifest.read_bytes())
        os.replace(replacement, manifest)
        return True
    monkeypatch.setattr(module, '_confirm', replace)
    assert module.main(['backup', 'create', '--profile', 'research-r1', '--vault-root', str(vault), '--checkout-root', str(checkout), '--manifest', str(manifest), '--destination', str(dest)]) == 2
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'BACKUP_RACE'
    assert not dest.exists()


def _research_restore_ready(tmp_path):
    from tests.unit.test_research_backup import _checkout, _vault
    from video_paper_wiki.backup_archive import create_backup_archive
    from video_paper_wiki.backup_manifest import build_research_backup_manifest
    from video_paper_wiki.jcs import canonicalize

    vault = tmp_path / "vault"
    checkout = tmp_path / "checkout"
    _vault(vault)
    _checkout(checkout)
    manifest = build_research_backup_manifest(vault, checkout)
    path = tmp_path / "manifest.json"
    path.write_bytes(canonicalize(manifest))
    path.chmod(0o600)
    archive = tmp_path / "backup.zip"
    create_backup_archive(
        vault_root=vault, checkout_root=checkout, manifest=manifest, destination=archive, profile="research-r1"
    )
    restore = tmp_path / "restore"
    restore.mkdir(mode=0o700)
    root = Path(__file__).resolve().parents[2]
    return {
        "manifest": path,
        "archive": archive,
        "restore": restore,
        "digest": manifest["manifest_sha256"],
        "upstream": root / "vendor" / "claude-obsidian",
        "config": root / "tests/fixtures/contracts/valid/video-paper-wiki.retrieval-policy.v1.json",
    }


def _restore_argv(ready):
    return [
        "backup",
        "restore",
        "--profile",
        "research-r1",
        "--archive",
        str(ready["archive"]),
        "--manifest",
        str(ready["manifest"]),
        "--expected-manifest-sha256",
        ready["digest"],
        "--restore-root",
        str(ready["restore"]),
        "--upstream-root",
        str(ready["upstream"]),
        "--config",
        str(ready["config"]),
    ]


def test_research_restore_non_tty_leaves_the_root_empty(tmp_path):
    ready = _research_restore_ready(tmp_path)
    root = Path(__file__).resolve().parents[2]
    code = "import sys\nsys.path.insert(0, 'operator/src')\nfrom video_paper_wiki_operator.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"
    argv = [sys.executable, "-c", code, *_restore_argv(ready)]
    result = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["error"]["code"] == "HUMAN_APPROVAL_REQUIRED"
    assert list(ready["restore"].iterdir()) == []


def test_research_restore_rejects_archive_replaced_during_confirmation(monkeypatch, tmp_path, capsys):
    module = _module()
    ready = _research_restore_ready(tmp_path)

    def replace(_words):
        archive = ready["archive"]
        replacement = archive.with_suffix(".new")
        replacement.write_bytes(archive.read_bytes())
        os.replace(replacement, archive)
        return True

    monkeypatch.setattr(module, "_confirm", replace)
    assert module.main(_restore_argv(ready)) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "RESTORE_VERIFICATION_FAILED"
    assert list(ready["restore"].iterdir()) == []


def test_research_restore_rejects_manifest_replaced_during_confirmation(monkeypatch, tmp_path, capsys):
    module = _module()
    ready = _research_restore_ready(tmp_path)

    def replace(_words):
        manifest = ready["manifest"]
        replacement = manifest.with_suffix(".new")
        replacement.write_bytes(manifest.read_bytes())
        os.replace(replacement, manifest)
        return True

    monkeypatch.setattr(module, "_confirm", replace)
    assert module.main(_restore_argv(ready)) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "RESTORE_VERIFICATION_FAILED"
    assert list(ready["restore"].iterdir()) == []


def test_research_create_rejects_checkout_changed_during_confirmation(monkeypatch, tmp_path, capsys):
    module = _module()
    vault, checkout, manifest, dest = _research_operator_paths(tmp_path)

    def replace(_words):
        draft = checkout / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json"
        draft.write_bytes(b'{"draft":2}')
        return True

    monkeypatch.setattr(module, "_confirm", replace)
    assert module.main(["backup", "create", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout), "--manifest", str(manifest), "--destination", str(dest)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] in {"BACKUP_RACE", "BACKUP_COVERAGE_INVALID"}
    assert not dest.exists()


def test_research_create_rejects_destination_parent_replaced_during_confirmation(monkeypatch, tmp_path, capsys):
    module = _module()
    vault, checkout, manifest, dest = _research_operator_paths(tmp_path)

    def replace(_words):
        parent = dest.parent
        moved = parent.with_name(parent.name + "-old")
        parent.rename(moved)
        parent.mkdir(mode=0o700)
        return True

    monkeypatch.setattr(module, "_confirm", replace)
    assert module.main(["backup", "create", "--profile", "research-r1", "--vault-root", str(vault), "--checkout-root", str(checkout), "--manifest", str(manifest), "--destination", str(dest)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BACKUP_RACE"
    assert not dest.exists()


def test_research_create_rejects_source_root_races_during_confirmation(monkeypatch, tmp_path, capsys):
    from tests.unit.test_research_backup import _checkout, _vault
    from video_paper_wiki.backup_manifest import build_research_backup_manifest
    from video_paper_wiki.jcs import canonicalize

    def replace_tree(path: Path) -> None:
        moved = path.with_name(path.name + "-replaced")
        path.rename(moved)
        path.mkdir(mode=0o700)

    for kind in ("vault", "checkout", "vault-parent", "checkout-parent", "appear", "delete"):
        module = _module()
        home = tmp_path / kind
        vault_home = home / "vhome"
        checkout_home = home / "chome"
        vault_home.mkdir(parents=True)
        checkout_home.mkdir()
        vault = vault_home / "vault"
        checkout = checkout_home / "checkout"
        _vault(vault)
        _checkout(checkout)
        manifest = build_research_backup_manifest(vault, checkout)
        manifest_path = home / "manifest.json"
        manifest_path.write_bytes(canonicalize(manifest))
        manifest_path.chmod(0o600)
        dest = home / "out" / "backup.zip"
        dest.parent.mkdir()

        def mutate(_words, _kind=kind):
            if _kind == "vault":
                replace_tree(vault)
            elif _kind == "checkout":
                replace_tree(checkout)
            elif _kind == "vault-parent":
                replace_tree(vault_home)
            elif _kind == "checkout-parent":
                replace_tree(checkout_home)
            elif _kind == "appear":
                plan = checkout / ".work" / "b1" / "plan"
                plan.mkdir(mode=0o700)
                target = plan / "ingest-plan.v1.json"
                target.write_bytes(b"{}")
                target.chmod(0o600)
            else:
                draft = checkout / ".work" / "b1" / "draft" / "paper-analysis-draft.v1.json"
                draft.unlink()
            return True

        monkeypatch.setattr(module, "_confirm", mutate)
        code = module.main(
            [
                "backup",
                "create",
                "--profile",
                "research-r1",
                "--vault-root",
                str(vault),
                "--checkout-root",
                str(checkout),
                "--manifest",
                str(manifest_path),
                "--destination",
                str(dest),
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert code == 2, kind
        assert payload["error"]["code"] in {"BACKUP_RACE", "BACKUP_COVERAGE_INVALID", "BACKUP_MANIFEST_INVALID", "AUDIT_RACE"}, kind
        assert not dest.exists()


def test_research_restore_rejects_root_parent_replaced_during_confirmation(monkeypatch, tmp_path, capsys):
    module = _module()
    ready = _research_restore_ready(tmp_path)
    nested = tmp_path / "nest"
    nested.mkdir(mode=0o700)
    target = nested / "restore"
    ready["restore"].rename(target)
    ready["restore"] = target

    def replace(_words):
        parent = ready["restore"].parent
        moved = tmp_path / "nest-old"
        parent.rename(moved)
        parent.mkdir(mode=0o700)
        (parent / "restore").mkdir(mode=0o700)
        return True

    monkeypatch.setattr(module, "_confirm", replace)
    assert module.main(_restore_argv(ready)) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] in {"RESTORE_ROOT_UNSAFE", "RESTORE_VERIFICATION_FAILED"}
    assert list(ready["restore"].iterdir()) == []
