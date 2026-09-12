"""Architect replay of independent T1 findings using synthetic PDFs only."""
from pathlib import Path
import hashlib
import json
import tempfile
from tests.research.test_light_pdf import _pdf_with_page_texts, _write_pdf
from video_paper_wiki_research import light_pdf as lp, light_workspace as ls, light_index as li


def observe(call):
    try:
        result = call()
        return {k: result.get(k) for k in ('ok','status','state','index_state','message','diagnostics')}
    except Exception as exc:
        return {'exception':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)}


def main():
    rows=[]
    with tempfile.TemporaryDirectory(prefix='lw1p-',dir='/private/tmp') as temp:
        root=Path(temp)
        pdf=_write_pdf(root/'native.pdf',_pdf_with_page_texts(['Synthetic native evidence.']))
        digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
        ws=root/'utf8'; first=lp.extract_pdf(pdf,ws)
        source=Path(first['markdown_path']); source.write_bytes(b'\xff')
        rows.append({'case':'invalid_utf8_extract','result':observe(lambda:lp.extract_pdf(pdf,ws)), 'bad_source_preserved':source.read_bytes()==b'\xff'})
        rows.append({'case':'invalid_utf8_inspect','result':observe(lambda:ls.inspect_workspace(ws))})

        ws=root/'bad-staging'; (ws/'papers').mkdir(parents=True)
        token='ownedprobe'; staged=lp._staging_dir(ws,digest,token); staged.mkdir(parents=True)
        (staged/'source.md').write_text('invalid staged content\n'); (staged/'source.json').write_text('{"schema":"wrong"}\n')
        lp._write_marker(lp._marker_path(ws,digest,token),lp._marker_payload(digest,token))
        result=observe(lambda:lp.extract_pdf(pdf,ws))
        final=ws/'papers'/digest
        rows.append({'case':'invalid_recognized_staging_public_api','result':result,'invalid_final_pair_published':(final/'source.json').is_file() and (final/'source.md').is_file()})

        ws=root/'symlink'; ws.mkdir(); outside=root/'outside'; outside.mkdir()
        (ws/'.light-transactions').symlink_to(outside,target_is_directory=True)
        rows.append({'case':'transaction_symlink','result':observe(lambda:lp.extract_pdf(pdf,ws)),
                     'outside_files':sorted(str(x.relative_to(outside)) for x in outside.rglob('*') if x.is_file())})

        ws=root/'empty'; ws.mkdir(); built=li.build_index(ws)
        rows.append({'case':'empty_current_index','build':{'ok':built['ok'],'paper_count':built['paper_count']},'inspect':observe(lambda:ls.inspect_workspace(ws))})
    report={'synthetic_only':True,'temporary_workspace_cleaned':True,
            'modules':{str(Path(m.__file__)):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (lp,ls)},'observations':rows}
    Path(__file__).with_name('probe-pdf-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
