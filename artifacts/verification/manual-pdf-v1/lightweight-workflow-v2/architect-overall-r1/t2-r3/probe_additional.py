"""Malformed context and malformed UTF-8 source observations for frozen T2 r3."""
from pathlib import Path
import copy
import json
import hashlib
import tempfile
from tests.research.test_light_index import SHA_A, _write_paper
from video_paper_wiki_research import light_index as li, light_context as lc


def observe(call):
    try:
        result=call(); return {'ok':result.get('ok'),'status':result.get('status')}
    except Exception as exc:
        return {'exception':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}


def main():
    rows=[]
    with tempfile.TemporaryDirectory(prefix='lw2more-',dir='/private/tmp') as tmp:
        root=Path(tmp); ws=root/'ws'; ws.mkdir()
        _write_paper(ws,SHA_A,'Synthetic',['quasar evidence']); li.build_index(ws)
        context=lc.export_context(ws,kind='qa',query='quasar')
        cid=context['evidence'][0]['chunk_id']; doc={'text':f'Evidence [@{cid}]','citations':[{'chunk_id':cid}]}
        for value in [None,0,False,'',[],'missing']:
            c=copy.deepcopy(context)
            if value=='missing':del c['evidence']
            else:c['evidence']=value
            rows.append({'case':'malformed_evidence_'+repr(value),'result':observe(lambda:lc.validate_live_context(ws,c))})
        c=copy.deepcopy(context); del c['query']
        rows.append({'case':'missing_query','result':observe(lambda:lc.validate_live_context(ws,c))})
        source=ws/'papers'/SHA_A/'source.md'; valid=source.read_bytes()
        source.write_bytes(b'\xff')
        rows.append({'case':'invalid_utf8_source_validate','result':observe(lambda:lc.validate_live_context(ws,context))})
        source.write_bytes(valid)
        for overwrite in [True,False]:
            target=root/f'out-{overwrite}.md'
            if overwrite:target.write_bytes(b'user document\n')
            original=Path.write_bytes; injected=False
            def writer(path,data):
                nonlocal injected
                r=original(path,data)
                if path.name.endswith('.light-out.tmp') and not injected:
                    injected=True; original(source,b'\xff')
                return r
            Path.write_bytes=writer
            try:r=observe(lambda:lc.import_document(ws,context,doc,output=target,overwrite=overwrite))
            finally:Path.write_bytes=original
            rows.append({'case':'invalid_utf8_after_staging','overwrite':overwrite,'injected':injected,'result':r,
                         'output_preserved_or_absent':target.read_bytes()==b'user document\n' if overwrite else not target.exists(),
                         'owned_stage_files_left':[p.name for p in root.glob('*.light-out.tmp')]})
            source.write_bytes(valid)
    report={'synthetic_only':True,'temporary_workspace_cleaned':True,'modules':{str(Path(m.__file__)):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (lc,li)},'observations':rows}
    Path(__file__).with_name('additional-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
