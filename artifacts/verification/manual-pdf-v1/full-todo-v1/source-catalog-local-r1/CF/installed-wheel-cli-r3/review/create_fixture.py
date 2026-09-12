import json, os, sys
from pathlib import Path
from tests.support import make_checkout
from tests.upstream.test_source_catalog import published
from tests.source_publication_fixture import knowledge_proposal
from tests.upstream.test_source_publication import publish
checkout=Path(os.environ['CHECKOUT']).resolve(); make_checkout(checkout); os.chdir(checkout)
vault,capture,material,arguments=published(checkout)
# published() already performs synthetic capture/admission and a knowledge publication.
group=material['papers'][0]
out={'checkout':str(checkout),'vault':str(vault),'capture':capture,'paper_id':group['record']['paper_id'],'claim_id':group['claims'][0]['claim_id'],'evidence_ordinal':0,'source_id':group['claims'][0]['evidence'][0]['source_id']}
Path(os.environ['OUT']).write_text(json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
