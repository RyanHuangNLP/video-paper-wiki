"""Run the installed operator entry point and record its exact child processes."""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path


def main() -> None:
    audit_path=Path(sys.argv[1]);entrypoint=Path(sys.argv[2]);operator_args=sys.argv[3:]
    import video_paper_wiki
    import video_paper_wiki_operator
    real_popen=subprocess.Popen;children=[]

    def observe(kind,argv):
        if isinstance(argv,(list,tuple)):words=[str(item) for item in argv]
        else:words=[str(argv)]
        children.append({'kind':kind,'argv':words})

    class Popen(real_popen):
        def __init__(self,argv,*args,**kwargs):
            observe('Popen',argv);super().__init__(argv,*args,**kwargs)

    subprocess.Popen=Popen
    record={'entrypoint':str(entrypoint),'entrypoint_argv':[str(entrypoint),*operator_args],
        'origins':{'video_paper_wiki':video_paper_wiki.__file__,
            'video_paper_wiki_operator':video_paper_wiki_operator.__file__},'children':children}
    try:
        sys.argv=record['entrypoint_argv'];runpy.run_path(str(entrypoint),run_name='__main__')
    finally:
        audit_path.write_text(json.dumps(record,sort_keys=True,separators=(',',':'))+'\n')


if __name__=='__main__':main()
