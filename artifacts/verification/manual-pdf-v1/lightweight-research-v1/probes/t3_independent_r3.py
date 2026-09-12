from __future__ import annotations
import copy, enum, hashlib, json, shutil, sys, tempfile
from pathlib import Path
source=Path('artifacts/verification/manual-pdf-v1/lightweight-research-v1/terminal-3/r3/files').resolve()
root_source=Path('.work/parallel/lightweight-research-v1/terminal-3/source').resolve()
sys.path[:0]=[str(source),str(source/'src'),str(root_source),str(root_source/'src')]
from tests.research.test_light_writing_project import _workspace,_writing_context,_create_project,_outline_document,_section_document,_chunk,_revision_dir
from video_paper_wiki_research import light_writing_project as w
from video_paper_wiki_research.light_context import LIGHT_CONTEXT_INVALID
from video_paper_wiki_research.light_workflow import sha256_canonical,persisted_bytes
from video_paper_wiki_research.contracts import ResearchError

obs=[]
def rec(name, ok, detail=None):
    obs.append({'case':name,'passed':bool(ok),'detail':detail})

def tree(ws):
    out={}
    root=ws/w.WRITING_DIRNAME
    if root.exists():
        for p in sorted(root.rglob('*')):
            if p.is_file() and not p.is_symlink(): out[str(p.relative_to(ws))]=p.read_bytes()
    return out

def setup(root):
    ws=_workspace(root); c,wr,imp=_create_project(ws); return ws,c,wr,imp,_outline_document(c)
def setup_first(root):
    ws=_workspace(root); c=_writing_context(ws); wr=w.export_writing_outline(ws,c); return ws,c,wr,None,_outline_document(c)

with tempfile.TemporaryDirectory(prefix='t3-independent-r3-',dir='/private/tmp') as td:
    root=Path(td)
    # 1. First-outline owned intent interruption matrix.
    ws,c,wr,imp,doc=setup_first(root/'before-own')
    real=w._create_staging
    def fail_before(*args,kind=None,**kw):
        if kind==w.PENDING_HEAD_KIND: raise ResearchError(w.LIGHT_WRITING_PROJECT_CONFLICT,'before ownership')
        return real(*args,kind=kind,**kw)
    w._create_staging=fail_before
    try: first=w.import_writing_outline(ws,wr,doc)
    finally: w._create_staging=real
    second=w.import_writing_outline(ws,wr,doc)
    rec('first_outline_before_ownership_retry', first.get('ok') is False and second.get('ok') is True, {'first':first,'second':second})

    ws,c,wr,imp,doc=setup_first(root/'before-payload')
    real=w._write_payload_tree
    def fail_payload(payload,files):
        if set(files)=={w.INTENT_NAME}: raise ResearchError(w.LIGHT_WRITING_PROJECT_CONFLICT,'before intent payload')
        return real(payload,files)
    w._write_payload_tree=fail_payload
    try: first=w.import_writing_outline(ws,wr,doc)
    finally: w._write_payload_tree=real
    second=w.import_writing_outline(ws,wr,doc)
    rec('first_outline_before_payload_retry', first.get('ok') is False and second.get('ok') is True, {'first':first,'second':second})

    ws,c,wr,imp,doc=setup_first(root/'after-revision')
    real=w._publish_revision
    def fail_after_revision(*a,**kw):
        out=real(*a,**kw); raise OSError('after revision install')
    w._publish_revision=fail_after_revision
    try: first=w.import_writing_outline(ws,wr,doc)
    finally: w._publish_revision=real
    pid=next(p.name for p in (ws/w.WRITING_DIRNAME/w.PROJECTS_DIRNAME).iterdir() if p.is_dir())
    revs=list((ws/w.WRITING_DIRNAME/w.PROJECTS_DIRNAME/pid/w.REVISIONS_DIRNAME).iterdir())
    second=w.import_writing_outline(ws,wr,doc)
    rec('first_outline_after_revision_retry', first.get('ok') is False and len(revs)==1 and second.get('ok') is True, {'first':first,'revisions':len(revs),'second':second})

    ws,c,wr,imp,doc=setup_first(root/'after-head')
    real=w._cleanup_pending_head_intent
    def fail_cleanup(*a,**kw): raise ResearchError(w.LIGHT_WRITING_PROJECT_CONFLICT,'after HEAD')
    w._cleanup_pending_head_intent=fail_cleanup
    try: first=w.import_writing_outline(ws,wr,doc)
    finally: w._cleanup_pending_head_intent=real
    second=w.import_writing_outline(ws,wr,doc)
    rec('first_outline_after_head_retry', first.get('ok') is False and second.get('ok') is True, {'first':first,'second':second})

    # Unowned existing revision: force install then remove intent, exact retry must refuse.
    ws,c,wr,imp,doc=setup_first(root/'unowned')
    real_pub=w._publish_revision
    def fail_after(*a,**kw): out=real_pub(*a,**kw); raise OSError('after revision install')
    w._publish_revision=fail_after
    try: first=w.import_writing_outline(ws,wr,doc)
    finally: w._publish_revision=real_pub
    st=ws/w.WRITING_DIRNAME/w.STAGING_DIRNAME
    if st.exists(): shutil.rmtree(st)
    refused=w.import_writing_outline(ws,wr,doc)
    rec('unowned_existing_revision_refused', first.get('ok') is False and refused.get('ok') is False and refused.get('status')==w.LIGHT_WRITING_PROJECT_CONFLICT, {'first':first,'refused':refused})

    # Edited intent staging must refuse.
    ws,c,wr,imp,doc=setup_first(root/'edited')
    w._publish_revision=fail_after
    try: first=w.import_writing_outline(ws,wr,doc)
    finally: w._publish_revision=real_pub
    touched=False
    for p in (ws/w.WRITING_DIRNAME/w.STAGING_DIRNAME).rglob('*'):
        if p.is_file() and p.name==w.INTENT_NAME:
            p.write_bytes(p.read_bytes()+b' '); touched=True; break
    refused=w.import_writing_outline(ws,wr,doc)
    rec('edited_intent_refused', touched and first.get('ok') is False and refused.get('ok') is False and refused.get('status')==w.LIGHT_WRITING_PROJECT_CONFLICT, {'touched':touched,'refused':refused})

    # 2. Malformed live/new/stored boundary and backup no-raise.
    ws,c,wr,imp,doc=setup(root/'malformed')
    before=tree(ws)
    malformed=[]
    for value in [10**400, True, float('nan'), float('inf'), float('-inf')]:
        x=copy.deepcopy(c); x['evidence'][0]['score']=value
        out=w.export_writing_outline(ws,x)
        malformed.append((out.get('status')==LIGHT_CONTEXT_INVALID, out.get('ok') is False, tree(ws)==before))
    listed=copy.deepcopy(wr); listed['schema']=[]
    out=w.import_writing_outline(ws,listed,doc)
    malformed.append((out.get('status')==w.LIGHT_WRITING_PROJECT_INVALID, tree(ws)==before))
    missing=copy.deepcopy(doc); del missing['sections'][0]['goal']
    out=w.import_writing_outline(ws,wr,missing)
    malformed.append((out.get('status')==w.LIGHT_WRITING_PROJECT_INVALID, tree(ws)==before))
    surrogate=copy.deepcopy(doc); surrogate['title']='bad'+chr(0xd800)
    out=w.import_writing_outline(ws,wr,surrogate)
    malformed.append((out.get('ok') is False, tree(ws)==before))
    exp=w.export_writing_section(ws,project_id=imp['project_id'],section_id='s1')
    sec=_section_document(imp['project_id'],'s1',_chunk(c),'x'); sec['status']=[]
    out=w.import_writing_section(ws,exp,sec); malformed.append((out.get('status')==w.LIGHT_WRITING_PROJECT_INVALID,tree(ws)==before))
    sec=_section_document(imp['project_id'],'s1',_chunk(c),'x'); sec['citations']={}
    out=w.import_writing_section(ws,exp,sec); malformed.append((out.get('status')==w.LIGHT_WRITING_PROJECT_INVALID,tree(ws)==before))
    rec('malformed_live_and_new_boundary', all(malformed), {'checks':malformed})

    # Stored malformed kind list, missing markdown, huge score, surrogate. History+backup must never raise.
    stored=[]
    for name,mut in [
      ('kind',lambda p:p.__setitem__('kind',[])),
      ('missing',lambda p:p['sections'][0].pop('markdown')),
      ('score',lambda p:p['evidence'][0].__setitem__('score',10**400)),
    ]:
        sw,sc,swr,si,sdoc=setup(root/('stored-'+name))
        d=_revision_dir(sw,si['project_id'],si['revision_id'])
        payload=json.loads((d/'document.json').read_text()) if name!='score' else json.loads((d/'context.json').read_text())
        mut(payload)
        target=d/('document.json' if name!='score' else 'context.json')
        # huge score cannot be canonicalized; use ensure_ascii and max int digits handling is fine after parse.
        target.write_text(json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n')
        try: hist=w.writing_project_history(sw,project_id=si['project_id']); hist_no_raise=True
        except BaseException as e: hist_no_raise=False; hist={'exc':repr(e)}
        try: blockers=w.writing_backup_blockers(sw); backup_no_raise=True
        except BaseException as e: backup_no_raise=False; blockers={'exc':repr(e)}
        stored.append((name,hist_no_raise,backup_no_raise,hist.get('ok') is False,bool(blockers) if isinstance(blockers,list) else True))
    # surrogate raw JSON in document title, preserving parseable escaped surrogate.
    sw,sc,swr,si,sdoc=setup(root/'stored-surrogate'); d=_revision_dir(sw,si['project_id'],si['revision_id']); p=d/'document.json'; payload=json.loads(p.read_text()); payload['title']='bad'+chr(0xd800); p.write_text(json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n')
    try: hist=w.writing_project_history(sw,project_id=si['project_id']); hn=True
    except BaseException as e: hn=False; hist={'exc':repr(e)}
    try: blockers=w.writing_backup_blockers(sw); bn=True
    except BaseException as e: bn=False; blockers={'exc':repr(e)}
    stored.append(('surrogate',hn,bn,hist.get('ok') is False,bool(blockers) if isinstance(blockers,list) else True))
    rec('malformed_stored_history_backup', all(x[1] and x[2] and x[3] and x[4] for x in stored), {'checks':stored})

    # 3. Forged selected unwritten successor in history/export/backup/import retry, then legal unknown and repeated provisional.
    ws,c,wr,imp,doc=setup(root/'unwritten'); pid,parent=imp['project_id'],imp['revision_id']; pd=_revision_dir(ws,pid,parent); parentdoc=json.loads((pd/'document.json').read_text())
    child=copy.deepcopy(parentdoc); child.update(kind='section',target_section_id='s1',parent_revision_id=parent)
    rid=w._revision_identity(project_id=pid,parent_revision_id=parent,context_sha256=sha256_canonical(c),document=child)
    files=w._revision_files(workspace=ws,project_id=pid,revision_id=rid,parent_revision_id=parent,context=c,document=child)
    cd=w._revision_dir(ws,pid,rid); cd.mkdir(); [ (cd/n).write_bytes(b) for n,b in files.items() ]
    w._head_path(ws,pid).write_bytes(persisted_bytes({'schema':w.HEAD_SCHEMA,'project_id':pid,'revision_id':rid}))
    hist=w.writing_project_history(ws,project_id=pid); ex=w.export_writing_section(ws,project_id=pid,section_id='s1'); blk=w.writing_backup_blockers(ws)
    retry=w.import_writing_section(ws,{'ok':True,'status':'OK','message':w.SECTION_MESSAGE,'schema':w.SECTION_CONTEXT_SCHEMA,'project_id':pid,'parent_revision_id':parent,'section_id':'s1','context':c,'context_sha256':sha256_canonical(c),'outline':parentdoc['outline'],'previous_section':parentdoc['sections'][0],'instructions':'','prompt':w.SECTION_PROMPT,'wrapper_sha256':'0'*64},{'citations':[],'markdown':'','project_id':pid,'schema':w.SECTION_DOCUMENT_SCHEMA,'section_id':'s1','status':'unwritten'})
    rec('selected_unwritten_forgery_rejected_all_paths', hist.get('ok') is False and ex.get('ok') is False and bool(blk) and retry.get('ok') is False, {'history':hist,'export':ex,'backup':blk,'retry':retry})

    # legal unknown retry/no-op and same provisional retry must remain accepted.
    lw,lc,lwr,li,ld=setup(root/'legal'); lpid=li['project_id']; unknown={'citations':[],'markdown':'证据不足','project_id':lpid,'schema':w.SECTION_DOCUMENT_SCHEMA,'section_id':'s1','status':'unknown'}
    pe=w.export_writing_section(lw,project_id=lpid,section_id='s1'); a=w.import_writing_section(lw,pe,unknown); b=w.import_writing_section(lw,pe,unknown)
    pe2=w.export_writing_section(lw,project_id=lpid,section_id='s2'); prov=_section_document(lpid,'s2',_chunk(lc,1),'实验'); p1=w.import_writing_section(lw,pe2,prov); p2=w.import_writing_section(lw,pe2,prov)
    rec('legal_unknown_and_provisional_retries', a.get('ok') and b.get('ok') and b.get('reused') is True and p1.get('ok') and p2.get('ok') and p2.get('reused') is True, {'unknown_first':a,'unknown_retry':b,'prov_first':p1,'prov_retry':p2})

print(json.dumps({'passed':sum(1 for x in obs if x['passed']),'total':len(obs),'observations':obs},ensure_ascii=False,indent=2,default=repr))
