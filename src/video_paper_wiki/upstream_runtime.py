"""Thin, read-only calls into the pinned Claude Obsidian public programs."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path
from video_paper_wiki.contracts import ContractError

MAX_OUTPUT=16*1024*1024

def _fail(code:str,message:str): raise ContractError(code,message)
def _root(value:Path|str)->Path:
    path=Path(value).resolve()
    if not path.is_dir() or not (path/'claude_obsidian'/'__init__.py').is_file(): _fail('UPSTREAM_PIN_MISMATCH','upstream root is not a Claude Obsidian source tree')
    return path

def _run(argv:list[str],*,cwd:Path,allowed_codes:tuple[int,...]=(0,),include_code:bool=False)->object:
    try:
        with tempfile.TemporaryDirectory(prefix='vpwiki-readonly-') as scratch_raw:
            scratch=Path(scratch_raw); os.chmod(scratch,0o700)
            env={k:str(scratch) for k in ('HOME','TEMP','TMP','TMPDIR')}
            result=subprocess.run(argv,cwd=cwd,env=env,input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,check=False)
    except (OSError,subprocess.TimeoutExpired): _fail('UPSTREAM_EXECUTION_FAILED','pinned read-only command failed to execute')
    if len(result.stdout)>MAX_OUTPUT or len(result.stderr)>MAX_OUTPUT: _fail('UPSTREAM_LIMIT_EXCEEDED','pinned output exceeds limit')
    if result.returncode not in allowed_codes: _fail('UPSTREAM_READONLY_FAILED','pinned read-only command reported failure')
    try: value=json.loads(result.stdout)
    except (UnicodeError,json.JSONDecodeError): _fail('UPSTREAM_CONTRACT_MISMATCH','pinned output is not JSON')
    return {'exit_code':result.returncode,'data':value} if include_code else value

def lint_vault(*,vault_root:Path|str,upstream_root:Path|str,as_of:str|None=None)->object:
    root=verify_upstream(upstream_root); script=root/'scripts'/'claude-obsidian.py'
    argv=[sys.executable,'-I','-B','-X','utf8',str(script),'lint','--vault',str(Path(vault_root).resolve()),'--strict','--format','json']
    if as_of: argv += ['--as-of',as_of]
    return _run(argv,cwd=root,allowed_codes=(0,1),include_code=True)

def bm25_query(*,vault_root:Path|str,upstream_root:Path|str,text:str,top:int=20)->object:
    if type(text) is not str or not text or type(top) is not int or not 1<=top<=100: _fail('QUERY_INVALID','query text or top is invalid')
    root=verify_upstream(upstream_root)
    return _run([sys.executable,'-I','-B','-X','utf8',str(root/'scripts'/'bm25-index.py'),'--vault',str(Path(vault_root).resolve()),'query',text,'--top',str(top)],cwd=root)

def bm25_status(*,vault_root:Path|str,upstream_root:Path|str)->object:
    root=verify_upstream(upstream_root)
    return _run([sys.executable,'-I','-B','-X','utf8',str(root/'scripts'/'bm25-index.py'),'--vault',str(Path(vault_root).resolve()),'stats'],cwd=root)

def verify_upstream(upstream_root:Path|str)->Path:
    root=_root(upstream_root)
    from video_paper_wiki.upstream_adapter import _authenticate, _profile
    _raw,profile=_profile(); _authenticate(root,profile)
    return root

def doctor(*,vault_root:Path|str,upstream_root:Path|str)->object:
    root=verify_upstream(upstream_root)
    return _run([sys.executable,'-I','-B','-X','utf8',str(root/'scripts'/'claude-obsidian.py'),'doctor','--vault',str(Path(vault_root).resolve())],cwd=root)
