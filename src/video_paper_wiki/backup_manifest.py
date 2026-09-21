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

def _work_path(path:str)->bool:
    return path==".work" or path.startswith(".work/")

def _vault_path(path:str)->bool:
    return path==".raw" or path.startswith(".raw/") or path=="wiki" or path.startswith("wiki/")

def _observe_vault_tree(root_fd:int)->set[str]:
    found:set[str]=set()
    def walk(dir_fd:int,rel:str)->None:
        found.add(rel)
        try:entries=list(os.scandir(dir_fd))
        except OSError:_fail("research source complete set changed")
        for entry in entries:
            child=rel+"/"+entry.name
            if child in EXCLUDED or any(child==item or child.startswith(item+"/") for item in EXCLUDED):continue
            try:st=entry.stat(follow_symlinks=False)
            except OSError:_fail("research source complete set changed")
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):_fail("research source complete set changed")
            if stat.S_ISDIR(st.st_mode):
                try:child_fd=os.open(entry.name,dir_open_flags(),dir_fd=dir_fd)
                except OSError:_fail("research source complete set changed")
                try:walk(child_fd,child)
                finally:close_fd(child_fd)
            else:found.add(child)
    for name in ROOTS:
        try:fd=os.open(name,dir_open_flags(),dir_fd=root_fd)
        except OSError:_fail("research source complete set changed")
        try:walk(fd,name)
        finally:close_fd(fd)
    return found

def _recheck_vault_snapshot(vault_snap)->None:
    """Re-read retained Vault bytes and the complete vault path set."""
    from video_paper_wiki.receipt_audit import _inventory_names
    from video_paper_wiki.secure_io import SecureIOError
    if vault_snap is None or getattr(vault_snap,"root_fd",None) is None:_fail("research source changed")
    vault_snap.verify()
    for relative,(first,raw) in list(vault_snap.files.items()):
        try:current=vault_snap.read(relative,max_bytes=max(len(raw),1))
        except (ContractError,SecureIOError,OSError) as exc:
            if isinstance(exc,ContractError) and exc.code=="AUDIT_RACE":raise
            _fail("research source content changed")
        if current!=raw or stamp(vault_snap.files[relative][0])!=stamp(first):_fail("research source content changed")
    if vault_snap.inventory is not None and _inventory_names(vault_snap)!=vault_snap.inventory:_fail("research source complete set changed")
    captured={path for path in vault_snap.directories if _vault_path(path)}|{path for path in vault_snap.files if _vault_path(path)}
    if _observe_vault_tree(vault_snap.root_fd)!=captured:_fail("research source complete set changed")

def _recheck_research_sources(vault_snap,checkout_snap)->None:
    """Recheck both retained roots. Vault is checked again after checkout content."""
    _recheck_vault_snapshot(vault_snap)
    if checkout_snap is None or getattr(checkout_snap,"root_fd",None) is None:_fail("checkout coverage changed")
    checkout_snap.verify()
    _recheck_vault_snapshot(vault_snap)

def _reraise_after_recheck(vault_snap,checkout_snap,original:BaseException)->None:
    try:_recheck_research_sources(vault_snap,checkout_snap)
    except ContractError as drift:
        if drift.code=="AUDIT_RACE":raise
        raise ContractError("BACKUP_MANIFEST_INVALID","research sources changed",{}) from drift
    raise original

def build_research_backup_manifest(vault_root:Path|str,checkout_root:Path|str,*,operation_head:object|None=None,expected_claimed_raw:object|None=None,_snapshot=None,_checkout_snapshot=None)->dict[str,Any]:
    """Bind one receipt-backed Vault manifest to the p3-r1 checkout whitelist."""
    from video_paper_wiki.backup_coverage import COVERAGE_VERSION,POLICY_V2,RESEARCH_ROOTS,SCHEMA_V2,CoverageSnapshot,assert_distinct_or_same,scan_research_coverage
    from video_paper_wiki.receipt_audit import _Snapshot
    vault_abs,checkout_abs=assert_distinct_or_same(vault_root,checkout_root)
    owns_vault=_snapshot is None;owns_checkout=_checkout_snapshot is None
    vault_snap=_snapshot if _snapshot is not None else _Snapshot(Path(vault_root))
    checkout_snap=_checkout_snapshot
    try:
        if checkout_snap is None:checkout_snap=CoverageSnapshot(checkout_root)
        try:
            vault_doc=build_backup_manifest(vault_root,operation_head=operation_head,expected_claimed_raw=expected_claimed_raw,_snapshot=vault_snap)
            entry_base=len(vault_doc["directories"])+len(vault_doc["files"])
            byte_base=sum(row["size_bytes"] for row in vault_doc["files"])
            checkout_snap=scan_research_coverage(checkout_root,snapshot=checkout_snap,entry_base=entry_base,byte_base=byte_base)
            report=checkout_snap.report
            if report is None:_fail("checkout coverage is missing")
            directories=list(vault_doc["directories"])+list(report["directories"])
            files=list(vault_doc["files"])+list(report["files"])
            if len(directories)+len(files)>MAX_ENTRIES or sum(row["size_bytes"] for row in files)>MAX_TOTAL_BYTES:_fail("manifest resource limit exceeded")
            directories=sorted(directories,key=lambda row:row["path"].encode());files=sorted(files,key=lambda row:row["path"].encode())
            paths=[row["path"] for row in directories]+[row["path"] for row in files]
            if len(paths)!=len(set(paths)):_fail("manifest paths differ")
            value={"schema":SCHEMA_V2,"policy":POLICY_V2,"source_roots":{"vault":vault_abs,"checkout":checkout_abs},"source_anchor":vault_doc["source_anchor"],"vault_manifest_sha256":vault_doc["manifest_sha256"],"roots":list(RESEARCH_ROOTS),"raw_included":True,"scope":{"coverage_version":COVERAGE_VERSION,"batch_ids":list(report["batches"]),"complete_project":False},"coverage":report["coverage"],"excluded":report["excluded"],"directories":directories,"files":files,"manifest_sha256":"0"*64}
            value["manifest_sha256"]=hashlib.sha256(canonicalize({key:item for key,item in value.items() if key!="manifest_sha256"})).hexdigest()
            result=validate_document(value,SCHEMA_V2)
            _recheck_research_sources(vault_snap,checkout_snap)
            return result
        except BaseException as original:_reraise_after_recheck(vault_snap,checkout_snap,original)
    finally:
        if owns_checkout and checkout_snap is not None:checkout_snap.close()
        if owns_vault:vault_snap.close()

def verify_restored_research_tree(root:Path|str,manifest:object,*,expected_manifest_sha256:str)->dict[str,Any]:
    """Check a restored tree without opening the original vault or checkout."""
    from video_paper_wiki.backup_coverage import SCHEMA_V2,scan_research_coverage
    expected=validate_document(manifest,SCHEMA_V2)
    digest=hashlib.sha256(canonicalize({key:item for key,item in expected.items() if key!="manifest_sha256"})).hexdigest()
    if type(expected_manifest_sha256) is not str or digest!=expected["manifest_sha256"] or digest!=expected_manifest_sha256:_fail("manifest self hash differs")
    target=Path(root)
    try:
        mode=target.lstat()
        if not stat.S_ISDIR(mode.st_mode) or stat.S_ISLNK(mode.st_mode) or stat.S_IMODE(mode.st_mode)!=0o700:raise ContractError("RESTORE_ROOT_UNSAFE","restored root must be an exact private directory",{})
    except ContractError:raise
    except OSError:raise ContractError("RESTORE_ROOT_UNSAFE","restored root is unsafe",{})
    for label in ("vault","checkout"):
        source=Path(expected["source_roots"][label])
        try:
            if source.exists() and (os.path.samefile(target,source) or _paths_nest(target,source)):
                raise ContractError("RESTORE_ROOT_UNSAFE","restore root overlaps a recorded source",{})
        except ContractError:raise
        except OSError:raise ContractError("RESTORE_ROOT_UNSAFE","recorded source root is unsafe",{})
    checkout_snap=None
    try:
        vault_doc=build_backup_manifest(target)
        if vault_doc["manifest_sha256"]!=expected["vault_manifest_sha256"] or vault_doc["source_anchor"]!=expected["source_anchor"]:
            raise ContractError("RESTORE_VERIFICATION_FAILED","restored vault manifest differs",{})
        checkout_snap=scan_research_coverage(target)
        report=checkout_snap.report or {}
        if report.get("batches")!=expected["scope"]["batch_ids"] or report.get("coverage")!=expected["coverage"]:
            raise ContractError("RESTORE_VERIFICATION_FAILED","restored research coverage differs",{})
        if report.get("directories")!=[row for row in expected["directories"] if _work_path(row["path"])] or report.get("files")!=[row for row in expected["files"] if row["path"].startswith(".work/")]:
            raise ContractError("RESTORE_VERIFICATION_FAILED","restored research files differ",{})
        if vault_doc["directories"]!=[row for row in expected["directories"] if not _work_path(row["path"])] or vault_doc["files"]!=[row for row in expected["files"] if not row["path"].startswith(".work/")]:
            raise ContractError("RESTORE_VERIFICATION_FAILED","restored vault files differ",{})
        checkout_snap.verify()
        included=sum(1 for row in expected["coverage"] if row["state"]=="included")
        absent=sum(1 for row in expected["coverage"] if row["state"]=="absent")
        return {"valid":True,"raw_included":True,"file_count":len(expected["files"]),"manifest_sha256":digest,"source_anchor":expected["source_anchor"],"vault_manifest_sha256":expected["vault_manifest_sha256"],"batch_count":len(expected["scope"]["batch_ids"]),"included_rules":included,"absent_rules":absent,"external_backup_observation":False}
    except ContractError as exc:
        if checkout_snap is not None:
            try:checkout_snap.verify()
            except ContractError:raise ContractError("RESTORE_VERIFICATION_FAILED","restored research tree changed",{})
        if exc.code in {"RESTORE_ROOT_UNSAFE","RESTORE_VERIFICATION_FAILED","BACKUP_MANIFEST_INVALID"}:raise
        raise ContractError("RESTORE_VERIFICATION_FAILED","restore verification failed",{}) from exc
    finally:
        if checkout_snap is not None:checkout_snap.close()

def _paths_nest(left:Path,right:Path)->bool:
    lp=left.absolute().parts;rp=right.absolute().parts
    return lp!=rp and (lp[:len(rp)]==rp or rp[:len(lp)]==lp)
