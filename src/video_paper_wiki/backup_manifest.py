"""Raw-inclusive complete-set inventory; archive work stays in upstream checkpoint."""
from __future__ import annotations
import hashlib,os,stat,unicodedata
from pathlib import Path
from typing import Any
from video_paper_wiki.contracts import ContractError,validate_document
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import close_fd,dir_open_flags,file_open_flags,open_dir_nofollow,stamp
from video_paper_wiki.secure_io import parse_strict_json,read_regular_file

ROOTS=(".raw","wiki");EXCLUDED=(".vault-meta",".work")
MAX_ENTRIES=65_534;MAX_TOTAL_BYTES=0xffff_ffff-1;MAX_FILE_BYTES=64*1024*1024
def _fail(message:str)->None:raise ContractError("BACKUP_MANIFEST_INVALID",message)
def _portable(path:str)->None:
    if not path or path.startswith("/") or "\\" in path or unicodedata.normalize("NFC",path)!=path or any(x in {"",".",".."} for x in path.split("/")):_fail("manifest path is not portable")

def derive_claimed_raw(root:Path|str,operation_head:object|None=None)->tuple[str,set[str]]:
    """Derive raw coverage from the Vault's canonical head; argument is expectation only."""
    base=Path(root);retained=[]
    def read(relative:str)->bytes:
        target=base/relative
        try:first=target.lstat()
        except OSError:_fail("canonical receipt authority is missing")
        raw=read_regular_file(target,missing_code="BACKUP_MANIFEST_INVALID",unsafe_code="BACKUP_MANIFEST_INVALID",changed_code="BACKUP_MANIFEST_INVALID",max_bytes=1024*1024,limit_code="BACKUP_MANIFEST_INVALID")
        try:now=target.lstat()
        except OSError:_fail("canonical receipt authority changed")
        if stamp(first)!=stamp(now):_fail("canonical receipt authority changed")
        retained.append((target,first));return raw
    def verify()->None:
        try:
            for target,first in retained:
                if stamp(target.lstat())!=stamp(first):_fail("canonical receipt authority changed")
        except OSError:_fail("canonical receipt authority changed")
    try:
        head=validate_document(parse_strict_json(read("wiki/meta/registries/operation-head.json"),invalid_code="BACKUP_MANIFEST_INVALID"),"video-paper-wiki.operation-head.v1")
        if operation_head is not None and validate_document(operation_head,"video-paper-wiki.operation-head.v1")!=head:_fail("expected operation head differs from canonical Vault head")
        chain=[];path=head["receipt_path"];expected=head["receipt_sha256"];seen=set()
        while path is not None:
            if path in seen:_fail("receipt chain cycles")
            seen.add(path);raw=read(path)
            if hashlib.sha256(raw).hexdigest()!=expected:_fail("receipt chain digest differs")
            receipt=validate_document(parse_strict_json(raw,invalid_code="BACKUP_MANIFEST_INVALID"),"video-paper-wiki.operation-receipt.v1")
            chain.append(receipt);previous=receipt["previous"]
            path=None if previous is None else previous["path"];expected=None if previous is None else previous["sha256"]
        if not chain or chain[0]["sequence"]!=head["sequence"] or [x["sequence"] for x in chain]!=list(range(head["sequence"],0,-1)):_fail("receipt chain sequence differs")
        verify()
        return head["receipt_sha256"],({w["path"] for r in chain for w in r["writes"] if w["path"].startswith(".raw/")}
            | {x["path"] for r in chain for x in r["claimed_inputs"] if x["path"].startswith(".raw/")})
    except BaseException:
        verify();raise

def _scan(base:Path,*,snapshot=None)->tuple[list[str],list[dict[str,Any]]]:
    retained=[];directories=[];files=[];keys={};total=0
    root_fd=(os.dup(snapshot.root_fd) if snapshot is not None else open_dir_nofollow(base,missing_code="BACKUP_MANIFEST_INVALID",unsafe_code="BACKUP_MANIFEST_INVALID"));root_stat=os.fstat(root_fd)
    def add(rel:str)->None:
        _portable(rel);key=unicodedata.normalize("NFC",rel).casefold()
        if key in keys and keys[key]!=rel:_fail("manifest path collision")
        keys[key]=rel
    def walk(parent_fd:int,name:str,rel:str)->None:
        nonlocal total
        try:fd=os.open(name,dir_open_flags(),dir_fd=parent_fd)
        except OSError:_fail("directory entry is unsafe")
        try:
            first=os.fstat(fd);named=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            if stamp(first)!=stamp(named) or not stat.S_ISDIR(first.st_mode):_fail("directory identity differs")
            path=base/rel;retained.append((path,first));add(rel);directories.append({"path":rel,"mode":stat.S_IMODE(first.st_mode)})
            if snapshot is not None:
                prior=snapshot.directories.get(rel)
                if prior is not None and stamp(prior)!=stamp(first):_fail("directory identity differs")
                snapshot.directories.setdefault(rel,first)
            for entry in sorted(os.scandir(fd),key=lambda x:x.name.encode()):
                child_rel=rel+"/"+entry.name
                if child_rel in EXCLUDED or any(child_rel.startswith(x+"/") for x in EXCLUDED):continue
                st=entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(st.st_mode):walk(fd,entry.name,child_rel);continue
                if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_nlink!=1:_fail("file entry is unsafe")
                add(child_rel)
                try:file_fd=os.open(entry.name,file_open_flags(),dir_fd=fd)
                except OSError:_fail("file entry is unsafe")
                try:
                    opened=os.fstat(file_fd)
                    if stamp(opened)!=stamp(st) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1:_fail("file identity differs")
                    prior=(snapshot.files.get(child_rel) if snapshot is not None else None)
                    if prior is not None and stamp(prior[0])!=stamp(opened):_fail("file identity differs")
                    if snapshot is not None and prior is None:snapshot.files[child_rel]=(opened,b"")
                    digest=hashlib.sha256();size=0;parts=[]
                    while True:
                        chunk=os.read(file_fd,1024*1024)
                        if not chunk:break
                        size+=len(chunk);total+=len(chunk)
                        if size>MAX_FILE_BYTES or total>MAX_TOTAL_BYTES:_fail("manifest resource limit exceeded")
                        digest.update(chunk);parts.append(chunk)
                    if stamp(os.fstat(file_fd))!=stamp(opened) or stamp(os.stat(entry.name,dir_fd=fd,follow_symlinks=False))!=stamp(opened):_fail("file changed while hashing")
                    retained.append((base/child_rel,opened));files.append({"path":child_rel,"sha256":digest.hexdigest(),"size_bytes":size,"mode":stat.S_IMODE(opened.st_mode)})
                    if snapshot is not None:
                        raw=b"".join(parts)
                        if prior is not None and prior[1]!=raw:_fail("file identity differs")
                        snapshot.files[child_rel]=(opened,raw)
                finally:close_fd(file_fd)
                if len(directories)+len(files)>MAX_ENTRIES:_fail("manifest entry limit exceeded")
            if stamp(os.fstat(fd))!=stamp(first) or stamp(os.stat(name,dir_fd=parent_fd,follow_symlinks=False))!=stamp(first):_fail("directory changed while scanning")
        finally:close_fd(fd)
    try:
        for name in ROOTS:walk(root_fd,name,name)
        for path,first in retained:
            try:now=path.lstat()
            except OSError:_fail("source tree changed")
            if stamp(now)!=stamp(first):_fail("source tree changed")
        named_root=base.lstat()
        if (named_root.st_dev,named_root.st_ino)!=(root_stat.st_dev,root_stat.st_ino):_fail("source root changed")
        return sorted(directories,key=lambda x:x["path"].encode()),sorted(files,key=lambda x:x["path"].encode())
    finally:close_fd(root_fd)

def build_backup_manifest(root:Path|str,*,operation_head:object|None=None,expected_claimed_raw:object|None=None,_snapshot=None)->dict[str,Any]:
    from video_paper_wiki.receipt_audit import _Snapshot,audit_integrity
    base=Path(root);snap=_snapshot or _Snapshot(base);owns=_snapshot is None
    try:
        try:authority=audit_integrity(base,_snapshot=snap)
        except ContractError as exc:
            if exc.code=='AUDIT_RACE':raise
            raise ContractError('BACKUP_MANIFEST_INVALID','Vault truth is not eligible for backup',{}) from exc
        if authority["classification"]!="receipt_backed":_fail("backup requires receipt-backed Vault truth")
        anchor=authority["head"]["receipt_sha256"];claimed=set(authority["ever_claimed_raw"])
        if operation_head is not None:
            try:expected_head=validate_document(operation_head,"video-paper-wiki.operation-head.v1")
            except ContractError as exc:raise ContractError('BACKUP_MANIFEST_INVALID','expected operation head is invalid',{}) from exc
            if expected_head!=authority["head"]:_fail("expected operation head differs from canonical Vault head")
        if expected_claimed_raw is not None and (type(expected_claimed_raw) is not list or set(expected_claimed_raw)!=claimed):_fail("expected raw inventory differs from receipt authority")
        directories,files=_scan(base,snapshot=snap);actual_raw={x["path"] for x in files if x["path"].startswith(".raw/")}
        # The pinned upstream owns one byte-bound control file outside the
        # domain receipt chain.  It remains part of the archive and restored
        # complete set; every other raw byte must be receipt-authorized.
        upstream_control={".raw/.manifest.json"}&actual_raw
        authorized_raw=claimed|upstream_control
        expected_raw_dirs={".raw"}
        for raw_path in authorized_raw:
            parts=raw_path.split("/")
            expected_raw_dirs.update("/".join(parts[:index]) for index in range(2,len(parts)))
        actual_raw_dirs={x["path"] for x in directories if x["path"]==".raw" or x["path"].startswith(".raw/")}
        if authorized_raw!=actual_raw or expected_raw_dirs!=actual_raw_dirs:
            _fail("raw complete set differs from receipt authority")
        value={"schema":"video-paper-wiki.backup-manifest.v1","policy":"vpwiki-private-archive-complete-set-v1","source_anchor":anchor,"excluded":list(EXCLUDED),"roots":list(ROOTS),"directories":directories,"files":files,"raw_included":True,"manifest_sha256":"0"*64}
        value["manifest_sha256"]=hashlib.sha256(canonicalize({k:v for k,v in value.items() if k!="manifest_sha256"})).hexdigest()
        result=validate_document(value,"video-paper-wiki.backup-manifest.v1");snap.verify();return result
    except BaseException as original:
        try:snap.verify()
        except ContractError as drift:
            if drift.code=='AUDIT_RACE':raise
            raise ContractError('BACKUP_MANIFEST_INVALID','Vault truth is not eligible for backup',{}) from drift
        raise original
    finally:
        if owns:snap.close()

def verify_restored_tree(root:Path|str,manifest:object,*,operation_head:object|None=None,source_root:Path|str)->dict[str,Any]:
    from video_paper_wiki.receipt_audit import _Snapshot,audit_integrity
    expected=validate_document(manifest,"video-paper-wiki.backup-manifest.v1")
    digest=hashlib.sha256(canonicalize({k:v for k,v in expected.items() if k!="manifest_sha256"})).hexdigest()
    if digest!=expected["manifest_sha256"]:_fail("manifest self hash differs")
    target=Path(root);source=Path(source_root)
    try:
        ts=target.lstat();ss=source.lstat()
        if not stat.S_ISDIR(ts.st_mode) or stat.S_IMODE(ts.st_mode)!=0o700:raise ContractError("RESTORE_ROOT_UNSAFE","restored root must be an exact private directory",{})
        if os.path.samefile(target,source):raise ContractError("RESTORE_ROOT_UNSAFE","restore root aliases source",{})
        ta=target.absolute().parts;sa=source.absolute().parts
        if ta[:len(sa)]==sa or sa[:len(ta)]==ta:raise ContractError("RESTORE_ROOT_UNSAFE","restore and source roots overlap",{})
    except ContractError:raise
    except OSError:raise ContractError("RESTORE_ROOT_UNSAFE","source or restored root is unsafe",{})
    source_snap=_Snapshot(source);target_snap=_Snapshot(target)
    try:
        authority=audit_integrity(source,_snapshot=source_snap)
        if authority["classification"]!="receipt_backed" or authority["head"]["receipt_sha256"]!=expected["source_anchor"]:
            raise ContractError("RESTORE_VERIFICATION_FAILED","source anchor differs",{})
        if operation_head is not None and validate_document(operation_head,"video-paper-wiki.operation-head.v1")!=authority["head"]:
            raise ContractError("RESTORE_VERIFICATION_FAILED","expected source head differs",{})
        directories,files=_scan(target,snapshot=target_snap)
        if directories!=expected["directories"] or files!=expected["files"]:
            raise ContractError("RESTORE_VERIFICATION_FAILED","restored tree differs from manifest",{})
        source_snap.verify();target_snap.verify()
        return {"valid":True,"raw_included":True,"file_count":len(files),"manifest_sha256":digest,"source_anchor":expected["source_anchor"]}
    except ContractError as exc:
        try:source_snap.verify();target_snap.verify()
        except ContractError:raise ContractError("RESTORE_VERIFICATION_FAILED","source or restored tree changed",{})
        if exc.code in {"RESTORE_ROOT_UNSAFE","RESTORE_VERIFICATION_FAILED"}:raise
        raise ContractError("RESTORE_VERIFICATION_FAILED","restore verification failed",{}) from exc
    finally:source_snap.close();target_snap.close()
