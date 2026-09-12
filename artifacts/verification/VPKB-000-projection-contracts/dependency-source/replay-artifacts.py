"""Fetch only four recorded lock artifacts and inspect metadata without importing them.

Run explicitly outside pytest with Python 3.11+, --repo CHECKOUT --out NEW_TMP_DIR.
No package install, execution, source extraction, extras or model downloads occur.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import tomllib
import urllib.parse
import urllib.request
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
lock_bytes = (args.repo / 'uv.lock').read_bytes()
expected = json.loads((Path(__file__).parent / 'source-license-observation.json').read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(lock_bytes) == expected['uv_lock_sha256'], 'lock differs from observed source'
packages = {p['name']: p for p in tomllib.loads(lock_bytes.decode())['package']}
args.out.mkdir(parents=True, exist_ok=False)
artifacts = [(n, packages[n]['wheels'][0]) for n in ('docling', 'docling-slim', 'docling-core')]
artifacts.append(('docling', packages['docling']['sdist']))
rows = []
class ExactHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != 'https' or target.hostname != 'files.pythonhosted.org':
            raise ValueError('redirect outside exact artifact host refused')
        return super().redirect_request(req, fp, code, msg, headers, newurl)
opener = urllib.request.build_opener(ExactHostRedirect)
for name, entry in artifacts:
    url = entry['url']
    parsed = urllib.parse.urlsplit(url)
    assert parsed.scheme == 'https' and parsed.hostname == 'files.pythonhosted.org'
    with opener.open(url, timeout=60) as response:
        raw = response.read(entry['size'] + 1)
    assert len(raw) == entry['size'] and sha(raw) == entry['hash'].split(':', 1)[1]
    artifact = args.out / Path(parsed.path).name
    artifact.write_bytes(raw)
    members = []
    if artifact.suffix == '.whl':
        with zipfile.ZipFile(artifact) as archive:
            for member in archive.namelist():
                if member.endswith('/METADATA') or (not member.endswith('/') and 'license' in member.lower()):
                    members.append((member, archive.read(member)))
    else:
        with tarfile.open(artifact) as archive:
            for member in archive.getmembers():
                if member.isfile() and (member.name.endswith('/PKG-INFO') or 'license' in member.name.lower()):
                    members.append((member.name, archive.extractfile(member).read()))
    destination = args.out / 'metadata' / name
    destination.mkdir(parents=True, exist_ok=True)
    for member, data in members:
        (destination / Path(member).name).write_bytes(data)
    rows.append({'url': url, 'sha256': sha(raw), 'bytes': len(raw),
                 'metadata_license_members': [{'name': n, 'sha256': sha(b), 'bytes': len(b)} for n, b in members]})
(args.out / 'replay-observation.json').write_text(json.dumps(rows, indent=2) + '\n')
print(json.dumps({'verified_artifacts': len(rows), 'output': str(args.out), 'packages_executed': False}))
