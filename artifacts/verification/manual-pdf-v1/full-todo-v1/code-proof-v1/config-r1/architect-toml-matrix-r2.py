"""Replay hand-authored TOML transition expectations using only the stdlib."""
import hashlib
import json
from pathlib import Path
import sys
import tomllib

ROOT = Path('/Users/huangzhanpeng/python_code/video-paper-wiki')
matrix = ROOT / 'docs/ai/packets/full-todo-v1/CODE-CONFIG-TOML-MATRIX-R2.json'
raw = matrix.read_bytes()
document = json.loads(raw)
rows = []
for case in document['cases']:
    try:
        value = tomllib.loads(case['source'])
    except tomllib.TOMLDecodeError:
        observed = {'accepted': False, 'exception_type': 'TOMLDecodeError'}
        passed = not case['expected']['accepted']
    else:
        observed = {'accepted': True, 'semantic_value': value}
        passed = case['expected']['accepted'] and value == case['expected']['semantic_value']
    rows.append({'id': case['id'], 'passed': passed, 'observed': observed})
result = {'schema': 'full-todo.code-config-toml-matrix-observation.v1', 'runtime': sys.version, 'matrix_sha256': hashlib.sha256(raw).hexdigest(), 'matrix_size_bytes': len(raw), 'case_count': len(rows), 'passed': sum(r['passed'] for r in rows), 'production_imported': False, 'observations': rows}
print(json.dumps(result, indent=2))
sys.exit(0 if all(r['passed'] for r in rows) else 1)
