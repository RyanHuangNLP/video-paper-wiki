"""Deterministic classic-ZIP private archive profile for raw-inclusive Vault truth."""
from __future__ import annotations
import binascii,hashlib,os,secrets,stat,struct,unicodedata
from pathlib import Path
from typing import Any
from video_paper_wiki.backup_manifest import MAX_ENTRIES
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import read_regular_file

META="VPWIKI-BACKUP-MANIFEST.json";MAX32=0xffff_ffff

def _fail(code:str,msg:str)->None:raise ContractError(code,msg)
def _portable(name:str,*,directory:bool=False)->None:
    value=name[:-1] if directory and name.endswith('/') else name
    if (not value or value.startswith('/') or '\\' in value or unicodedata.normalize('NFC',value)!=value
            or any(part in {'','.','..'} for part in value.split('/'))):
        _fail('BACKUP_ARCHIVE_INVALID','archive filename is not portable')
def _row(name:str,data:bytes,mode:int,is_dir:bool)->tuple[bytes,bytes]:
    nb=name.encode('utf-8');crc=0 if is_dir else binascii.crc32(data)&MAX32;size=len(data)
    if size>=MAX32 or len(nb)>65535:_fail('BACKUP_ARCHIVE_INVALID','archive entry exceeds classic ZIP')
    local=struct.pack('<IHHHHHIIIHH',0x04034b50,20,0x0800,0,0,0x21,crc,size,size,len(nb),0)+nb+data
    ext=(((stat.S_IFDIR if is_dir else stat.S_IFREG)|mode)<<16)|(0x10 if is_dir else 0)
    central=struct.pack('<IHHHHHHIIIHHHHHII',0x02014b50,(3<<8)|20,20,0x0800,0,0,0x21,crc,size,size,len(nb),0,0,0,0,ext,0)+nb
    return local,central

def validate_backup_manifest(value:object)->dict[str,Any]:
    from video_paper_wiki.contracts import validate_document
    try:doc=validate_document(value,'video-paper-wiki.backup-manifest.v1')
    except ContractError as exc:
        if exc.code=='BACKUP_MANIFEST_INVALID':raise
        raise ContractError('BACKUP_MANIFEST_INVALID','backup manifest schema differs',{}) from exc
    material={k:v for k,v in doc.items() if k!='manifest_sha256'}
    if hashlib.sha256(canonicalize(material)).hexdigest()!=doc['manifest_sha256']:_fail('BACKUP_MANIFEST_INVALID','manifest self hash differs')
    directories=[x['path'] for x in doc['directories']];files=[x['path'] for x in doc['files']];paths=directories+files
    if (len(paths)>MAX_ENTRIES or directories!=sorted(directories,key=lambda x:x.encode())
            or files!=sorted(files,key=lambda x:x.encode()) or len(paths)!=len(set(paths))):
        _fail('BACKUP_MANIFEST_INVALID','manifest paths differ')
    return doc

def encode_backup_archive(*,vault_root:Path|str,manifest:object,_snapshot=None)->bytes:
    doc=validate_backup_manifest(manifest);base=Path(vault_root);mraw=canonicalize(doc)
    entries=[(META,mraw,0o600,False)]
    by_dir={x['path']:x for x in doc['directories']};by_file={x['path']:x for x in doc['files']}
    for path in sorted(set(by_dir)|set(by_file),key=lambda x:x.encode()):
        if path in by_dir:entries.append((path+'/',b'',by_dir[path]['mode'],True))
        else:
            row=by_file[path];raw=(_snapshot.read(path,max_bytes=64*1024*1024) if _snapshot is not None else read_regular_file(base/path,missing_code='BACKUP_RACE',unsafe_code='BACKUP_RACE',changed_code='BACKUP_RACE',max_bytes=64*1024*1024,limit_code='BACKUP_RACE'))
            if len(raw)!=row['size_bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:_fail('BACKUP_RACE','archive source differs from manifest')
            entries.append((path,raw,row['mode'],False))
    if len(entries)>65535:_fail('BACKUP_ARCHIVE_INVALID','archive entry count exceeds classic ZIP')
    locals=[];centrals=[];offset=0
    for name,data,mode,is_dir in entries:
        local,central=_row(name,data,mode,is_dir);locals.append(local)
        central=central[:-len(name.encode())-0] if False else central
        # overwrite the final relative offset field (four bytes before filename)
        pos=42;central=central[:pos]+struct.pack('<I',offset)+central[pos+4:]
        centrals.append(central);offset+=len(local)
    body=b''.join(locals);directory=b''.join(centrals)
    if len(body)>=MAX32 or len(directory)>=MAX32 or len(body)+len(directory)+22>=MAX32:_fail('BACKUP_ARCHIVE_INVALID','archive exceeds classic ZIP')
    eocd=struct.pack('<IHHHHIIH',0x06054b50,0,0,len(entries),len(entries),len(directory),len(body),0)
    return body+directory+eocd

def _decode(raw:bytes)->tuple[dict[str,Any],dict[str,tuple[bytes,int,bool]]]:
    if len(raw)<22:_fail('BACKUP_ARCHIVE_INVALID','archive is truncated')
    e=struct.unpack('<IHHHHIIH',raw[-22:])
    if e[0]!=0x06054b50 or e[1:3]!=(0,0) or e[3]!=e[4] or e[7]!=0 or e[5]+e[6]+22!=len(raw):_fail('BACKUP_ARCHIVE_INVALID','archive EOCD differs')
    count,central_size,central_offset=e[3],e[5],e[6]
    if count>65535 or count>MAX_ENTRIES+1:_fail('BACKUP_ARCHIVE_INVALID','archive entry count exceeds limit')
    pos=0;entries={};order=[];portable={}
    while pos<central_offset:
        if pos+30>len(raw):_fail('BACKUP_ARCHIVE_INVALID','local header is truncated')
        h=struct.unpack('<IHHHHHIIIHH',raw[pos:pos+30])
        if h[0]!=0x04034b50 or h[1:6]!=(20,0x0800,0,0,0x21) or h[10]!=0:_fail('BACKUP_ARCHIVE_INVALID','local header differs')
        nlen,xlen=h[9],h[10]
        if pos+30+nlen>central_offset:_fail('BACKUP_ARCHIVE_INVALID','local filename is truncated')
        try:name=raw[pos+30:pos+30+nlen].decode('utf-8')
        except UnicodeDecodeError:_fail('BACKUP_ARCHIVE_INVALID','archive filename is not UTF-8')
        if name.encode('utf-8')!=raw[pos+30:pos+30+nlen]:_fail('BACKUP_ARCHIVE_INVALID','archive filename encoding differs')
        _portable(name,directory=name.endswith('/'));key=unicodedata.normalize('NFC',name.rstrip('/')).casefold()
        if key in portable:_fail('BACKUP_ARCHIVE_INVALID','archive filename collision')
        portable[key]=name
        start=pos+30+nlen+xlen;data=raw[start:start+h[7]]
        if len(data)!=h[7] or h[7]!=h[8] or (binascii.crc32(data)&MAX32)!=h[6] or name in entries:_fail('BACKUP_ARCHIVE_INVALID','archive entry differs')
        entries[name]=(data,None,name.endswith('/'));order.append((name,pos,h));pos=start+h[7]
    if pos!=central_offset:_fail('BACKUP_ARCHIVE_INVALID','local section differs')
    cpos=central_offset;seen=[]
    for expected_name,offset,lh in order:
        if cpos+46>len(raw):_fail('BACKUP_ARCHIVE_INVALID','central header is truncated')
        h=struct.unpack('<IHHHHHHIIIHHHHHII',raw[cpos:cpos+46]);nlen=h[10]
        if cpos+46+nlen>len(raw)-22:_fail('BACKUP_ARCHIVE_INVALID','central filename is truncated')
        try:name=raw[cpos+46:cpos+46+nlen].decode('utf-8')
        except UnicodeDecodeError:_fail('BACKUP_ARCHIVE_INVALID','archive filename is not UTF-8')
        local_name, _offset, lh = expected_name, offset, lh
        if (h[0]!=0x02014b50 or h[1:7]!=((3<<8)|20,20,0x0800,0,0,0x21)
                or h[7:10]!=lh[6:9] or h[11:15]!=(0,0,0,0) or h[16]!=offset
                or name!=local_name or name.encode('utf-8')!=raw[cpos+46:cpos+46+nlen]):
            _fail('BACKUP_ARCHIVE_INVALID','central header differs')
        is_dir=name.endswith('/');expected_type=stat.S_IFDIR if is_dir else stat.S_IFREG
        attrs=h[15];mode=(attrs>>16)&0o7777
        if stat.S_IFMT(attrs>>16) != expected_type:
            _fail('BACKUP_ARCHIVE_INVALID','central entry type differs')
        expected_dos=0x10 if is_dir else 0
        if (attrs&0xffff)!=expected_dos:_fail('BACKUP_ARCHIVE_INVALID','central external attributes differ')
        entries[name]=(entries[name][0],mode,is_dir);seen.append(name);cpos+=46+nlen
    if cpos!=len(raw)-22 or len(seen)!=count or cpos-central_offset!=central_size:_fail('BACKUP_ARCHIVE_INVALID','central directory differs')
    if not seen or seen[0]!=META:_fail('BACKUP_ARCHIVE_INVALID','archive metadata is missing')
    if entries[META][1]!=0o600 or entries[META][2]:_fail('BACKUP_ARCHIVE_INVALID','archive metadata mode differs')
    from video_paper_wiki.secure_io import parse_strict_json
    doc=validate_backup_manifest(parse_strict_json(entries[META][0],invalid_code='BACKUP_ARCHIVE_INVALID'))
    expected=[META]+sorted([x['path']+'/' for x in doc['directories']]+[x['path'] for x in doc['files']],key=lambda x:x.rstrip('/').encode())
    if seen!=expected or set(entries)!=set(expected):_fail('BACKUP_ARCHIVE_INVALID','archive member set or order differs')
    for row in doc['directories']:
        data,mode,is_dir=entries[row['path']+'/']
        if data or not is_dir or mode!=row['mode']:_fail('BACKUP_ARCHIVE_INVALID','archive directory differs')
    for row in doc['files']:
        data,mode,is_dir=entries[row['path']]
        if is_dir or mode!=row['mode'] or len(data)!=row['size_bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
            _fail('BACKUP_ARCHIVE_INVALID','archive file differs')
    return doc,entries

def create_backup_archive(*,vault_root:Path|str,manifest:object,destination:Path|str,
        _source_snapshot=None,_destination_parent_fd:int|None=None)->dict[str,Any]:
    from video_paper_wiki.backup_manifest import build_backup_manifest
    from video_paper_wiki.receipt_audit import _Snapshot
    from video_paper_wiki.secure_io import close_fd,open_dir_nofollow
    doc=validate_backup_manifest(manifest);owned_source=_source_snapshot is None;owned_parent=_destination_parent_fd is None
    source_snap=_source_snapshot if _source_snapshot is not None else _Snapshot(Path(vault_root));parent_fd=_destination_parent_fd;fd=None;installed=False;temp=''
    try:
        if build_backup_manifest(vault_root,_snapshot=source_snap)!=doc:_fail('BACKUP_RACE','manifest differs from current source authority')
        data=encode_backup_archive(vault_root=vault_root,manifest=doc,_snapshot=source_snap);decoded,_=_decode(data)
        if decoded!=doc:_fail('BACKUP_ARCHIVE_INVALID','encoded archive failed self validation')
        target=Path(destination)
        if parent_fd is None:parent_fd=open_dir_nofollow(target.parent,missing_code='BACKUP_ARCHIVE_CONFLICT',unsafe_code='BACKUP_ARCHIVE_CONFLICT')
        temp='.vpwiki-backup-'+secrets.token_hex(12)
        try:os.stat(target.name,dir_fd=parent_fd,follow_symlinks=False)
        except FileNotFoundError:pass
        else:_fail('BACKUP_ARCHIVE_CONFLICT','archive destination exists')
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_CLOEXEC',0)
        fd=os.open(temp,flags,0o600,dir_fd=parent_fd);view=memoryview(data)
        while view:
            written=os.write(fd,view)
            if written<=0:_fail('BACKUP_ARCHIVE_CONFLICT','archive sibling write failed')
            view=view[written:]
        os.fsync(fd);os.close(fd);fd=None
        check=os.open(temp,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0),dir_fd=parent_fd)
        try:
            observed=b''
            while True:
                part=os.read(check,1024*1024)
                if not part:break
                observed+=part
        finally:os.close(check)
        if observed!=data:_fail('BACKUP_ARCHIVE_CONFLICT','archive sibling differs')
        try:os.link(temp,target.name,src_dir_fd=parent_fd,dst_dir_fd=parent_fd,follow_symlinks=False)
        except FileExistsError:_fail('BACKUP_ARCHIVE_CONFLICT','archive destination exists')
        except OSError:_fail('RECOVERY_REQUIRED','archive installation is ambiguous')
        installed=True
        try:os.unlink(temp,dir_fd=parent_fd);os.fsync(parent_fd)
        except OSError:_fail('RECOVERY_REQUIRED','archive installation durability is ambiguous')
        check=os.open(target.name,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0),dir_fd=parent_fd)
        try:
            observed=b''
            while True:
                part=os.read(check,1024*1024)
                if not part:break
                observed+=part
        finally:os.close(check)
        if observed!=data:_fail('RECOVERY_REQUIRED','archive installation differs')
        source_snap.verify()
        return {'archive_sha256':hashlib.sha256(data).hexdigest(),'archive_size_bytes':len(data),'manifest_sha256':doc['manifest_sha256'],'source_anchor':doc['source_anchor'],'external_backup_observation':False}
    finally:
        if fd is not None:close_fd(fd)
        if not installed and parent_fd is not None and temp:
            try:os.unlink(temp,dir_fd=parent_fd)
            except OSError:pass
        try:
            try:source_snap.verify()
            except ContractError as exc:raise ContractError('BACKUP_RACE','backup source changed',{}) from exc
        finally:
            if owned_parent and parent_fd is not None:close_fd(parent_fd)
            if owned_source:source_snap.close()

def _restore_backup_archive_core(*,archive:Path|str,source_root:Path|str,restore_root:Path|str,manifest:object,
        _source_snapshot=None,_archive_authority=None,_restore_fd:int|None=None)->dict[str,Any]:
    from video_paper_wiki.catalog_store import _RetainedFile
    from video_paper_wiki.receipt_audit import _Snapshot
    from video_paper_wiki.backup_manifest import build_backup_manifest
    from video_paper_wiki.secure_io import close_fd,dir_open_flags,open_dir_nofollow,stamp
    owned_source=_source_snapshot is None;owned_archive=_archive_authority is None;owned_root=_restore_fd is None
    source_snap=_source_snapshot if _source_snapshot is not None else _Snapshot(Path(source_root))
    try:archive_held=_archive_authority if _archive_authority is not None else _RetainedFile(Path(archive))
    except ContractError:
        if owned_source:source_snap.close()
        _fail('BACKUP_ARCHIVE_INVALID','archive is unsafe')
    try:
        fd=archive_held.fd;os.lseek(fd,0,os.SEEK_SET);parts=[];total=0
        while True:
            part=os.read(fd,1024*1024)
            if not part:break
            total+=len(part)
            if total>=MAX32:_fail('BACKUP_ARCHIVE_INVALID','archive exceeds classic ZIP')
            parts.append(part)
        raw=b''.join(parts)
    except OSError:_fail('BACKUP_ARCHIVE_INVALID','archive read failed')
    doc,entries=_decode(raw)
    if doc!=validate_backup_manifest(manifest):_fail('BACKUP_ARCHIVE_INVALID','embedded manifest differs')
    if build_backup_manifest(source_root,_snapshot=source_snap)!=doc:_fail('RESTORE_VERIFICATION_FAILED','source authority differs from manifest')
    root=Path(restore_root)
    root_fd=_restore_fd if _restore_fd is not None else open_dir_nofollow(root,missing_code='RESTORE_ROOT_UNSAFE',unsafe_code='RESTORE_ROOT_UNSAFE');st=os.fstat(root_fd)
    try:named_root=root.lstat()
    except OSError:_fail('RESTORE_ROOT_UNSAFE','restore root is missing')
    if stamp(named_root)!=stamp(st) or not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode)!=0o700 or list(os.scandir(root_fd)):_fail('RESTORE_ROOT_UNSAFE','restore root must be empty private directory')
    source=Path(source_root)
    try:
        if os.path.samefile(root,source):_fail('RESTORE_ROOT_UNSAFE','restore root aliases source')
    except FileNotFoundError:_fail('RESTORE_ROOT_UNSAFE','source root is missing')
    ra=root.absolute().parts;sa=source.absolute().parts
    if ra[:len(sa)]==sa or sa[:len(ra)]==ra:_fail('RESTORE_ROOT_UNSAFE','restore and source roots overlap')
    created=[]
    def parent(relative:str)->tuple[int,str]:
        parts=relative.split('/');fd=os.dup(root_fd)
        try:
            for item in parts[:-1]:
                nxt=os.open(item,dir_open_flags(),dir_fd=fd);close_fd(fd);fd=nxt
            return fd,parts[-1]
        except BaseException:close_fd(fd);raise
    try:
        for row in sorted(doc['directories'],key=lambda x:(x['path'].count('/'),x['path'].encode())):
            pfd,name=parent(row['path'])
            try:
                os.mkdir(name,row['mode'],dir_fd=pfd)
                dfd=os.open(name,dir_open_flags(),dir_fd=pfd)
                try:os.fchmod(dfd,row['mode']);os.fsync(dfd);created.append(('dir',row['path'],os.fstat(dfd)))
                finally:close_fd(dfd)
                os.fsync(pfd)
            finally:close_fd(pfd)
        for row in doc['files']:
            data,mode,is_dir=entries.get(row['path'],(None,None,None))
            if data is None or is_dir or mode!=row['mode'] or hashlib.sha256(data).hexdigest()!=row['sha256']:_fail('BACKUP_ARCHIVE_INVALID','archive member differs')
            pfd,name=parent(row['path']);fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),row['mode'],dir_fd=pfd)
            try:
                os.fchmod(fd,row['mode'])
                view=memoryview(data)
                while view:view=view[os.write(fd,view):]
                if stat.S_IMODE(os.fstat(fd).st_mode)!=row['mode']:_fail('RESTORE_VERIFICATION_FAILED','restored file mode differs')
                os.fsync(fd)
                if hashlib.sha256(data).hexdigest()!=row['sha256']:_fail('BACKUP_ARCHIVE_INVALID','archive member digest differs')
                os.fsync(fd)
                created.append(('file',row['path'],os.fstat(fd)))
            finally:os.close(fd);os.fsync(pfd);close_fd(pfd)
    except BaseException as exc:
        for kind,relative,_first in reversed(created):
            pfd,name=parent(relative)
            try:
                if kind=='file':os.unlink(name,dir_fd=pfd)
                else:os.rmdir(name,dir_fd=pfd)
            except OSError:pass
            finally:close_fd(pfd)
        if isinstance(exc,ContractError):raise
        _fail('RESTORE_VERIFICATION_FAILED','archive extraction failed')
    finally:
        try:
            archive_held.verify('RESTORE_VERIFICATION_FAILED');source_snap.verify()
            identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
            if identity(os.fstat(root_fd))!=identity(st) or identity(root.lstat())!=identity(st):_fail('RESTORE_ROOT_UNSAFE','restore root changed')
        finally:
            if owned_root:close_fd(root_fd)
            if owned_archive:archive_held.close()
            if owned_source:source_snap.close()
    from video_paper_wiki.backup_manifest import verify_restored_tree
    verify_restored_tree(root,doc,source_root=source_root)
    # The semantic verifier must not establish a fresh baseline for files that
    # this extraction installed.  Reopen every installed named edge and bind it
    # to the inode captured at creation, after the verifier has returned.
    try:
        for kind,relative,first in created:
            pfd,name=parent(relative)
            try:current=os.stat(name,dir_fd=pfd,follow_symlinks=False)
            finally:close_fd(pfd)
            identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
            if (identity(current)!=identity(first) if kind=='dir' else stamp(current)!=stamp(first)):
                _fail('RESTORE_VERIFICATION_FAILED','restored entry changed during verification')
    except OSError as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','restored entry changed during verification',{}) from exc
    return {'archive_sha256':hashlib.sha256(raw).hexdigest(),'manifest_sha256':doc['manifest_sha256'],'restore_root':root.as_posix(),'source_anchor':doc['source_anchor'],'external_backup_observation':False}

def restore_backup_archive(*,archive:Path|str,source_root:Path|str,restore_root:Path|str,manifest:object,
        _source_snapshot=None,_archive_authority=None,_restore_fd:int|None=None)->dict[str,Any]:
    """Retain every external authority across decode, extraction and verification."""
    from video_paper_wiki.catalog_store import _RetainedFile
    from video_paper_wiki.receipt_audit import _Snapshot
    from video_paper_wiki.secure_io import close_fd,open_dir_nofollow
    owned_source=_source_snapshot is None;owned_archive=_archive_authority is None;owned_root=_restore_fd is None
    source=_source_snapshot if _source_snapshot is not None else _Snapshot(Path(source_root));archive_held=_archive_authority;root_fd=_restore_fd;root_first=None
    try:
        try:
            if archive_held is None:archive_held=_RetainedFile(Path(archive))
        except ContractError:_fail('BACKUP_ARCHIVE_INVALID','archive is unsafe')
        root=Path(restore_root)
        if root_fd is None:
            try:root_fd=open_dir_nofollow(root,missing_code='RESTORE_ROOT_UNSAFE',unsafe_code='RESTORE_ROOT_UNSAFE')
            except BaseException as exc:raise ContractError('RESTORE_ROOT_UNSAFE','restore root is unsafe',{}) from exc
        root_first=os.fstat(root_fd)
        identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
        if identity(root.lstat())!=identity(root_first) or stat.S_IMODE(root_first.st_mode)!=0o700:_fail('RESTORE_ROOT_UNSAFE','restore root is unsafe')
        result=_restore_backup_archive_core(archive=archive,source_root=source_root,restore_root=restore_root,
            manifest=manifest,_source_snapshot=source,_archive_authority=archive_held,_restore_fd=root_fd)
        return result
    except ContractError:raise
    except BaseException as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','restore failed',{}) from exc
    finally:
        try:
            if root_fd is not None:
                identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
                try:
                    if identity(os.fstat(root_fd))!=identity(root_first) or identity(Path(restore_root).lstat())!=identity(root_first):raise OSError
                except OSError as exc:raise ContractError('RESTORE_ROOT_UNSAFE','restore root changed',{}) from exc
            try:source.verify()
            except ContractError as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','source changed during restore',{}) from exc
            if archive_held is not None:
                try:archive_held.verify('RESTORE_VERIFICATION_FAILED')
                except ContractError as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','archive changed during restore',{}) from exc
        finally:
            if owned_root and root_fd is not None:close_fd(root_fd)
            if owned_archive and archive_held is not None:archive_held.close()
            if owned_source:source.close()

__all__=['validate_backup_manifest','encode_backup_archive','create_backup_archive','restore_backup_archive']
