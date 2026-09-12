from pathlib import Path
import json,hashlib,tempfile
from tests.research.test_light_index import SHA_A,_write_paper
from video_paper_wiki_research import light_workflow as lw,light_index as li

def run():
 rows=[]
 with tempfile.TemporaryDirectory(prefix="lw3edge-",dir="/private/tmp") as t:
  root=Path(t)
  for case in ["control","last_staged_file_move","before_publish_hook"]:
   ws=root/case;ws.mkdir();_write_paper(ws,SHA_A,"Synthetic",["quasar evidence on native synthetic page"]);li.build_index(ws)
   source=ws/"papers"/SHA_A/"source.md";done=[False]
   def mutate():
    if not done[0]:
     source.write_text(source.read_text().replace("quasar","changed-source"));done[0]=True
   original=Path.replace
   def replace_and_edit(path,target):
    out=original(path,target)
    if path.name==lw.MANIFEST_NAME and Path(target).parent.name=="session":mutate()
    return out
   def hook(point):
    if point==lw.HOOK_BEFORE_SESSION_PUBLISH:mutate()
   if case=="last_staged_file_move":Path.replace=replace_and_edit
   try:r=lw.prepare_workflow(ws,kind="qa",query="quasar",_hook=hook if case=="before_publish_hook" else None)
   finally:Path.replace=original
   sessions=ws/".light-workflow/sessions"
   rows.append({"case":case,"injected":done[0],"result":{k:r.get(k) for k in ["ok","status","state","session_id"]},"published_sessions":len(list(sessions.iterdir())) if sessions.exists() else 0})
 report={"source_sha256":hashlib.sha256(Path(lw.__file__).read_bytes()).hexdigest(),"synthetic_only":True,"observations":rows}
 Path(__file__).with_name("publication-edge-results.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
if __name__=="__main__":run()
