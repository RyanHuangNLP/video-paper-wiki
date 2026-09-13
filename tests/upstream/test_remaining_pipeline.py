from __future__ import annotations
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
import pytest
from tests.support import make_checkout
from tests.unit.test_remaining_domain import _compile_material
from video_paper_wiki.canonical_compiler import stage_compilation
from video_paper_wiki.domain import shape_query_results
from video_paper_wiki.evidence_join import build_evidence_inventory,join_evidence_files
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.retrieval import rank_hits

def run(args,check=True):return subprocess.run(args,capture_output=True,text=True,check=check)

def test_compile_apply_lint_chunk_index_and_exact_join(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[2];up=root/'vendor/claude-obsidian';cli=[sys.executable,'-I','-B','-X','utf8',str(up/'scripts/claude-obsidian.py')]
    checkout=tmp_path/'work';checkout.mkdir();make_checkout(checkout);monkeypatch.chdir(checkout);vault=tmp_path/'vault'
    dry=json.loads(run([*cli,'init',str(vault),'--operation-id','remaining-init','--generated-at','2026-09-02T00:00:00Z']).stdout)
    run([*cli,'init',str(vault),'--operation-id','remaining-init','--generated-at','2026-09-02T00:00:00Z','--approved-plan-sha256',dry['approved_plan_sha256'],'--apply'])
    material=_compile_material();staged=stage_compilation(material,batch_id='remaining')
    bundle=Path(staged['bundle_path']);inspection=json.loads(run([*cli,'transaction','inspect',str(bundle),'--vault',str(vault)]).stdout)
    run([*cli,'transaction','apply',str(bundle),'--vault',str(vault),'--approved-plan-sha256',inspection['approval_sha256']])
    lint=run([*cli,'lint','--vault',str(vault),'--strict','--format','json'],check=False);assert lint.returncode==0,json.loads(lint.stdout).get('findings')
    run([sys.executable,'-I','-B','-X','utf8',str(up/'scripts/contextual-prefix.py'),'--vault',str(vault),'--all','--no-llm'])
    run([sys.executable,'-I','-B','-X','utf8',str(up/'scripts/bm25-index.py'),'--vault',str(vault),'build'])
    inventory=build_evidence_inventory(material['papers']);files={}
    for path in sorted(list((vault/'wiki').rglob('*.md'))+list((vault/'.vault-meta/chunks').rglob('*.json'))+[vault/'.vault-meta/bm25/index.json']):
        relative=path.relative_to(vault).as_posix();files[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    request={'schema':'video-paper-wiki.evidence-join-request.v1','inventory':inventory,'files':files,'bm25_path':'.vault-meta/bm25/index.json'}
    result=join_evidence_files(vault_root=vault,request=request)
    assert len(result['generation_sha256'])==64 and any(row['evidence_unit_ids'] for row in result['chunks'])
    hits=json.loads(run([sys.executable,'-I','-B','-X','utf8',str(up/'scripts/bm25-index.py'),'--vault',str(vault),'query','compiler','--top','10']).stdout)
    assert shape_query_results(hits)[0]['chunk_id'].startswith(('c-','l-','syn-'))
    config={'schema':'video-paper-wiki.retrieval-config.v1','corpus_version':'fixture','query_version':'fixture','top_chunks':10,'top_papers':10,'evidence_limit':8,'per_paper_evidence_limit':2,
            'generation_sha256':result['generation_sha256'],'mapping_sha256':result['mapping_sha256'],'eligibility':'active-not-deprecated','paper_tie_break':'score-desc-paper-id-asc','chunk_tie_break':'score-desc-paper-id-asc-chunk-id-asc'}
    assert rank_hits(hits,result,config)['top10']==[material['papers'][0]['record']['paper_id']]
    # A temporary parent ABA cannot redirect reads: the retained dirfd remains
    # authoritative, and reopening the named lineage observes the mutation.
    import video_paper_wiki.evidence_join as join_module
    original=join_module.read_child_regular;done=False;chunks_dir=vault/'.vault-meta/chunks';moved=vault/'.vault-meta/chunks-retained'
    def aba(parent_fd,name,**kwargs):
        nonlocal done
        if not done and str(kwargs['path']).endswith('.json') and '/chunks/' in kwargs['path'].as_posix():
            done=True;chunks_dir.rename(moved);shutil.copytree(moved,chunks_dir)
            try:return original(parent_fd,name,**kwargs)
            finally:shutil.rmtree(chunks_dir);moved.rename(chunks_dir)
        return original(parent_fd,name,**kwargs)
    monkeypatch.setattr(join_module,'read_child_regular',aba)
    with pytest.raises(ContractError):join_evidence_files(vault_root=vault,request=request)
    monkeypatch.setattr(join_module,'read_child_regular',original)
