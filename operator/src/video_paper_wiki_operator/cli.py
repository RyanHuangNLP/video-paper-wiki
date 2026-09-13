"""Explicit operator-only delegator to the pinned Claude Obsidian programs."""
from __future__ import annotations
import argparse, hashlib, json, os, stat, subprocess, sys
from pathlib import Path

READ_ONLY={('doctor',),('lint',),('contracts',),('transaction','inspect')}
PIN='9f8c1199047eac2c3828496279fbb7ba9540b90b'

class _UsageError(Exception):
    pass

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)

def _index_arguments(words:list[str])->tuple[list[str],str]:
    tail=words[1:]; vault=None; remaining=[]; index=0
    while index<len(tail):
        if tail[index]=='--vault':
            if vault is not None or index+1>=len(tail): raise SystemExit('index requires one --vault PATH')
            vault=tail[index+1]; index+=2
        else: remaining.append(tail[index]); index+=1
    if vault is None or not remaining or remaining[0] not in {'build','query','stats'}:
        raise SystemExit('index requires --vault PATH and build, query, or stats')
    return ['--vault',vault,*remaining],remaining[0]

def _verified_root(raw:str)->Path:
    root=Path(raw).resolve()
    base=['git','-c','core.fsmonitor=false','--no-optional-locks','--no-replace-objects','-C',str(root)]
    try:
        head=subprocess.run([*base,'rev-parse','HEAD'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=True).stdout.strip()
        dirty=subprocess.run([*base,'status','--porcelain=v1','--untracked-files=all'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=True).stdout
    except (OSError,subprocess.CalledProcessError):
        raise _UsageError('upstream root cannot be authenticated')
    if head!=PIN or dirty: raise _UsageError('upstream root does not match the clean pinned checkout')
    return root

def _confirm(words:list[str])->bool:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        return False
    token=' '.join(words[:2]); sys.stderr.write(f'Type {token!r} to run the pinned upstream command: '); sys.stderr.flush()
    return sys.stdin.readline().strip()==token

def _emit_error(code:str,message:str)->int:
    sys.stdout.write(json.dumps({'ok':False,'error':{'code':code,'message':message,'details':{}}},sort_keys=True,separators=(',',':'))+'\n');return 2

def _emit_child_json(result:subprocess.CompletedProcess)->int:
    """Normalize a successful pinned child result to one closed JSON line."""
    if result.returncode:
        if result.stdout:sys.stdout.buffer.write(result.stdout)
        if result.stderr:sys.stderr.buffer.write(result.stderr)
        return result.returncode
    try:value=json.loads(result.stdout)
    except (TypeError,UnicodeDecodeError,json.JSONDecodeError):
        return _emit_error('OPERATOR_CHILD_INVALID','pinned child returned invalid JSON')
    if type(value) is not dict or result.stderr:
        return _emit_error('OPERATOR_CHILD_INVALID','pinned child returned an invalid result')
    sys.stdout.write(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n');return 0

def _verify_parent_authority(held,code:str)->None:
    from video_paper_wiki.contracts import ContractError
    try:
        identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
        for parent,name,child,first in held.edges:
            if identity(os.fstat(child))!=identity(first) or identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=identity(first):raise OSError
        if identity(os.fstat(held.parent_fd))!=identity(held.parent_stat):raise OSError
    except OSError as exc:raise ContractError(code,'retained parent authority changed') from exc

def _verify_gate_vault_root(held)->None:
    """Bind the post-apply Vault to the root opened before the first inspect.

    A successful transaction intentionally changes the managed inventory, so the
    pre-apply snapshot cannot be verified as an unchanged snapshot after apply.
    Its retained root descriptor still proves that the post-audit inspected the
    same named Vault root rather than a replacement tree.
    """
    from video_paper_wiki.contracts import ContractError
    try:
        first=held.root_stat;named=held.root.lstat();opened=os.fstat(held.root_fd)
        identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
        if identity(named)!=identity(first) or identity(opened)!=identity(first):raise OSError
    except (AttributeError,OSError) as exc:
        raise ContractError('GATE_STATE_INVALID','gate Vault root changed') from exc

def _verify_gate_vault_transition(held,mutable_paths:set[str],after=None)->None:
    """Verify the pre-inspect authority except exact transaction destinations."""
    from video_paper_wiki.contracts import ContractError
    from video_paper_wiki.secure_io import stamp
    relative=''
    try:
        _verify_gate_vault_root(held)
        identity=lambda value:(value.st_dev,value.st_ino,stat.S_IMODE(value.st_mode))
        for relative,first in held.directories.items():
            if not relative:continue
            fd=os.dup(held.root_fd)
            try:
                for part in relative.split('/'):
                    nxt=os.open(part,os.O_RDONLY|getattr(os,'O_DIRECTORY',0)|getattr(os,'O_NOFOLLOW',0),dir_fd=fd);os.close(fd);fd=nxt
                if identity(os.fstat(fd))!=identity(first):raise OSError
            finally:os.close(fd)
        for relative,(first,first_raw) in held.files.items():
            if relative in mutable_paths:continue
            if after is None:
                if stamp(held._current_stat(relative))!=stamp(first):raise OSError
            else:
                current,current_raw=after.files[relative]
                if identity(current)!=identity(first) or current.st_size!=first.st_size or current_raw!=first_raw:raise OSError
    except (ContractError,OSError) as exc:
        raise ContractError('GATE_STATE_INVALID','gate Vault authority changed during apply: '+relative,{'path':relative}) from exc

def _verify_gate_post_inventory(before,after,authority)->None:
    from video_paper_wiki.contracts import ContractError
    publication=authority['publication_authority'];transaction=publication['transaction']
    payloads={item['path'] for item in publication['request']['payloads']}
    receipt=transaction['head']['receipt_path']
    # Receipt audit validates the operation-scoped runtime journal separately;
    # _Snapshot is deliberately the managed wiki/.raw inventory only.
    allowed=payloads|{receipt,'wiki/meta/registries/operation-head.json'}
    expected_files=set(before.files)|allowed
    if set(after.files)!=expected_files:
        raise ContractError('GATE_STATE_INVALID','gate apply changed an unauthorized Vault path',{
            'missing':sorted(expected_files-set(after.files)),'extra':sorted(set(after.files)-expected_files)})
    expected_dirs=set(before.directories)
    for path in allowed:
        parts=path.split('/')[:-1]
        expected_dirs.update('/'.join(parts[:i]) for i in range(1,len(parts)+1))
    if set(after.directories)!=expected_dirs:
        raise ContractError('GATE_STATE_INVALID','gate apply changed an unauthorized Vault directory')

def _gate_apply_barrier(phase:str,**_observed:object)->None:
    """Private deterministic race seam; it cannot bypass any validation."""
    return None

def _main(argv:list[str]|None=None)->int:
    parser=_Parser(prog='vpwiki-admin')
    parser.add_argument('--upstream-root')
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    ns=parser.parse_args(argv); words=list(ns.arguments)
    if words[:1]==['--']: words=words[1:]
    if not words: parser.error('an upstream command is required')
    if words[:2]==['transaction','apply']:
        command=_Parser(prog='vpwiki-admin transaction apply');command.add_argument('--bundle',required=True);command.add_argument('--vault-root',required=True);command.add_argument('--upstream-root',required=True);command.add_argument('--approved-plan-sha256',required=True);args=command.parse_args(words[2:])
        if not _confirm(words):return _emit_error('OPERATOR_CONFIRMATION_REQUIRED','interactive confirmation is required')
        root=_verified_root(args.upstream_root)
        child=subprocess.run([sys.executable,'-I','-B','-X','utf8',str(root/'scripts/claude-obsidian.py'),'transaction','apply',args.bundle,'--vault',args.vault_root,'--approved-plan-sha256',args.approved_plan_sha256],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        return _emit_child_json(child)
    if words[:2]==['gate','apply']:
        command=_Parser(prog='vpwiki-admin gate apply');command.add_argument('--prepared',required=True);command.add_argument('--operation-id',required=True);command.add_argument('--upstream-root',required=True);command.add_argument('--vault-root',required=True);command.add_argument('--approved-plan-sha256',required=True);args=command.parse_args(words[2:])
        bundle_holder=None;gate_prepared=None;gate_vault=None;post_vault=None;child_succeeded=False
        try:
            root=_verified_root(args.upstream_root)
            from video_paper_wiki.gate_decision import _Prepared,inspect_gate
            from video_paper_wiki.receipt_audit import _Snapshot
            from video_paper_wiki.jcs import canonicalize
            gate_prepared=_Prepared(args.prepared)
            try:gate_vault=_Snapshot(Path(args.vault_root))
            except Exception as exc:
                from video_paper_wiki.contracts import ContractError
                raise ContractError('GATE_STATE_INVALID','gate retained authority is unsafe') from exc
            apply_holder=[]
            first=inspect_gate(prepared=args.prepared,operation_id=args.operation_id,upstream_root=root,vault_root=args.vault_root,
                _prepared_snapshot=gate_prepared,_vault_snapshot=gate_vault,_apply_holder_out=apply_holder)
            if len(apply_holder)!=1:
                from video_paper_wiki.contracts import ContractError
                raise ContractError('GATE_STATE_INVALID','gate inspection did not retain one apply authority')
            bundle_holder,bundle=apply_holder[0]
            _gate_apply_barrier('before-prompt',prepared=gate_prepared,vault=gate_vault,holder=bundle_holder)
            tx=first['publication_authority']['transaction'];approval=tx['inspection']['approval_sha256']
            if approval!=args.approved_plan_sha256:
                gate_prepared.verify();gate_vault.verify()
                from video_paper_wiki.contracts import ContractError
                raise ContractError('HUMAN_APPROVAL_REQUIRED','approved plan differs from inspected plan')
            sys.stderr.write('Exact gate operation/transaction/plan:\n'+canonicalize({'operation_id':args.operation_id,'transaction':tx,'approved_plan_sha256':approval}).decode()+'\n')
            if not _confirm(words):
                gate_prepared.verify();gate_vault.verify()
                from video_paper_wiki.contracts import ContractError
                raise ContractError('HUMAN_APPROVAL_REQUIRED','interactive confirmation is required')
            _gate_apply_barrier('after-prompt',prepared=gate_prepared,vault=gate_vault,holder=bundle_holder)
            gate_prepared.verify();gate_vault.verify();bundle_holder.verify()
            second=inspect_gate(prepared=args.prepared,operation_id=args.operation_id,upstream_root=root,vault_root=args.vault_root,
                _prepared_snapshot=gate_prepared,_vault_snapshot=gate_vault)
            if canonicalize(first)!=canonicalize(second):
                from video_paper_wiki.contracts import ContractError
                raise ContractError('GATE_STATE_INVALID','gate authority changed after confirmation')
            gate_prepared.verify();gate_vault.verify();bundle_holder.verify()
            from video_paper_wiki.receipt_audit import audit_integrity
            pre_audit=audit_integrity(args.vault_root,_snapshot=gate_vault);pre_head=pre_audit['head'];bundle_holder.verify()
            child=subprocess.run([sys.executable,'-I','-B','-X','utf8',str(root/'scripts/claude-obsidian.py'),'transaction','apply',str(bundle),'--vault',args.vault_root,'--approved-plan-sha256',approval],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
            from video_paper_wiki.contracts import ContractError
            if child.returncode!=0:raise ContractError('GATE_STATE_INVALID','pinned native gate apply failed')
            child_succeeded=True;post_vault=_Snapshot(Path(args.vault_root));audit=audit_integrity(args.vault_root,_snapshot=post_vault)
            if audit['orphans']!=pre_audit['orphans']:
                raise ContractError('GATE_STATE_INVALID','gate apply changed the raw orphan set')
            if first['registry']['event_path'] not in audit['current_paths'] or first['registry']['baseline_path'] not in audit['current_paths'] or 'wiki/meta/registries/gate-heads.json' not in audit['current_paths']:
                raise ContractError('GATE_STATE_INVALID','published gate state is not receipt-backed')
            from video_paper_wiki.secure_io import load_strict_json,read_regular_file
            from video_paper_wiki.secure_io import parse_strict_json
            published_registry=parse_strict_json(post_vault.read('wiki/meta/registries/gate-heads.json',max_bytes=1024*1024),invalid_code='GATE_STATE_INVALID')
            published_event=parse_strict_json(post_vault.read(first['registry']['event_path'],max_bytes=1024*1024),invalid_code='GATE_STATE_INVALID')
            published_baseline=post_vault.read(first['registry']['baseline_path'],max_bytes=1024*1024)
            head=audit['head'];receipt=parse_strict_json(post_vault.read(head['receipt_path'],max_bytes=1024*1024),invalid_code='GATE_STATE_INVALID')
            expected_paths=sorted(item['path'] for item in first['publication_authority']['request']['payloads'])
            written=sorted(item['path'] for item in receipt['writes'])
            inspected=first['publication_authority']['transaction']
            if (published_registry!=first['registry'] or published_event!=first['decision']
                    or hashlib.sha256(published_baseline).hexdigest()!=first['baseline_manifest_sha256']
                    or receipt['operation_id']!=args.operation_id or written!=expected_paths
                    or receipt!=inspected['receipt'] or head!=inspected['head']
                    or (pre_head is not None and receipt['sequence']!=pre_head['sequence']+1)
                    or (pre_head is not None and receipt['previous']!={'path':pre_head['receipt_path'],'sha256':pre_head['receipt_sha256']})):
                raise ContractError('GATE_STATE_INVALID','published gate bytes differ from inspected authority')
            mutable={item['path'] for item in first['publication_authority']['request']['payloads']}
            mutable.add('wiki/meta/registries/operation-head.json')
            gate_prepared.verify();_verify_gate_vault_transition(gate_vault,mutable,post_vault)
            _verify_gate_post_inventory(gate_vault,post_vault,first);post_vault.verify()
            bundle_holder.__exit__(None,None,None);bundle_holder=None
            post_vault.close();post_vault=None;gate_vault.close();gate_vault=None;gate_prepared.close();gate_prepared=None
            result={'ok':True,'data':{'schema':'video-paper-wiki.gate-apply-result.v1','published_gate_state':'closed','gate_event_id':first['decision']['event_id'],'receipt_audit':audit,'external_gate_satisfied':False}}
            sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n');return 0
        except Exception as exc:
            if bundle_holder is not None:
                try:bundle_holder.__exit__(type(exc),exc,exc.__traceback__)
                except Exception as drift:exc=drift
            try:
                if gate_prepared is not None:gate_prepared.verify()
            except Exception as drift:exc=drift
            try:
                if gate_vault is not None:
                    if child_succeeded:
                        mutable={item['path'] for item in first['publication_authority']['request']['payloads']};mutable.add('wiki/meta/registries/operation-head.json')
                        _verify_gate_vault_transition(gate_vault,mutable,post_vault)
                    else:gate_vault.verify()
                if post_vault is not None:
                    _verify_gate_post_inventory(gate_vault,post_vault,first);post_vault.verify()
            except Exception:
                from video_paper_wiki.contracts import ContractError
                if getattr(exc,'code',None)!='GATE_STATE_INVALID':
                    exc=ContractError('GATE_STATE_INVALID','gate authority changed during apply')
            return _emit_error(getattr(exc,'code','GATE_STATE_INVALID'),getattr(exc,'message','gate apply failed'))
        finally:
            if post_vault is not None:post_vault.close()
            if gate_vault is not None:gate_vault.close()
            if gate_prepared is not None:gate_prepared.close()
    if words[:2]==['backup','create']:
        command=_Parser(prog='vpwiki-admin backup create');command.add_argument('--vault-root',required=True);command.add_argument('--manifest',required=True);command.add_argument('--destination',required=True);args=command.parse_args(words[2:])
        from video_paper_wiki.backup_archive import create_backup_archive
        from video_paper_wiki.backup_manifest import build_backup_manifest
        from video_paper_wiki.secure_io import load_strict_json,open_dir_nofollow,close_fd
        from video_paper_wiki.catalog_store import _RetainedFile
        from video_paper_wiki.receipt_audit import _Snapshot
        manifest_held=None;source_snap=None;destination_held=None;parent_fd=None
        try:
            from video_paper_wiki.contracts import ContractError
            try:manifest_held=_RetainedFile(Path(args.manifest))
            except ContractError as exc:raise ContractError('BACKUP_MANIFEST_INVALID','backup manifest is unsafe') from exc
            try:source_snap=_Snapshot(Path(args.vault_root))
            except ContractError as exc:raise ContractError('BACKUP_RACE','backup source is unsafe') from exc
            manifest=load_strict_json(args.manifest,missing_code='BACKUP_MANIFEST_INVALID',unsafe_code='BACKUP_MANIFEST_INVALID',invalid_code='BACKUP_MANIFEST_INVALID',changed_code='BACKUP_MANIFEST_INVALID');first=build_backup_manifest(args.vault_root,_snapshot=source_snap)
            if first!=manifest:return _emit_error('BACKUP_RACE','manifest differs from current Vault')
            destination=Path(args.destination)
            try:destination_held=_RetainedFile(destination,required=False)
            except ContractError as exc:raise ContractError('BACKUP_ARCHIVE_CONFLICT','archive destination is unsafe') from exc
            parent_fd=destination_held.parent_fd
            try:os.stat(destination.name,dir_fd=parent_fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:return _emit_error('BACKUP_ARCHIVE_CONFLICT','archive destination exists')
            if not _confirm(words):
                manifest_held.verify_edge('BACKUP_RACE');source_snap.verify();_verify_parent_authority(destination_held,'BACKUP_RACE')
                return _emit_error('HUMAN_APPROVAL_REQUIRED','interactive confirmation is required')
            manifest_held.verify_edge('BACKUP_RACE');source_snap.verify();_verify_parent_authority(destination_held,'BACKUP_RACE')
            try:os.stat(destination.name,dir_fd=parent_fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:return _emit_error('BACKUP_ARCHIVE_CONFLICT','archive destination changed after confirmation')
            if build_backup_manifest(args.vault_root,_snapshot=source_snap)!=first:return _emit_error('BACKUP_RACE','backup source changed after confirmation')
            result=create_backup_archive(vault_root=args.vault_root,manifest=manifest,destination=args.destination,
                _source_snapshot=source_snap,_destination_parent_fd=parent_fd)
            manifest_held.verify_edge('BACKUP_RACE');source_snap.verify();_verify_parent_authority(destination_held,'BACKUP_RACE')
            sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n');return 0
        except Exception as exc:
            try:
                if manifest_held is not None:manifest_held.verify_edge('BACKUP_RACE')
                if source_snap is not None:source_snap.verify()
                if destination_held is not None:_verify_parent_authority(destination_held,'BACKUP_RACE')
            except Exception as drift:exc=drift
            return _emit_error(getattr(exc,'code','BACKUP_ARCHIVE_INVALID'),getattr(exc,'message','backup create failed'))
        finally:
            if source_snap is not None:source_snap.close()
            if destination_held is not None:destination_held.close()
            if manifest_held is not None:manifest_held.close()
    if words[:2]==['backup','restore']:
        command=_Parser(prog='vpwiki-admin backup restore');command.add_argument('--archive',required=True);command.add_argument('--source-root',required=True);command.add_argument('--restore-root',required=True);command.add_argument('--manifest',required=True);command.add_argument('--upstream-root',required=True);command.add_argument('--config',required=True);args=command.parse_args(words[2:])
        root=_verified_root(args.upstream_root)
        from video_paper_wiki.backup_archive import restore_backup_archive
        from video_paper_wiki.secure_io import load_strict_json,open_dir_nofollow,close_fd
        from video_paper_wiki.backup_manifest import build_backup_manifest
        from video_paper_wiki.secure_io import read_regular_file
        from video_paper_wiki.catalog_store import _RetainedFile
        from video_paper_wiki.receipt_audit import _Snapshot
        manifest_held=None;archive_held=None;source_snap=None;restore_authority=None;config_held=None;restore_fd=None;restore_first=None
        try:
            from video_paper_wiki.contracts import ContractError
            try:manifest_held=_RetainedFile(Path(args.manifest))
            except ContractError as exc:raise ContractError('BACKUP_MANIFEST_INVALID','backup manifest is unsafe') from exc
            try:archive_held=_RetainedFile(Path(args.archive))
            except ContractError as exc:raise ContractError('BACKUP_ARCHIVE_INVALID','backup archive is unsafe') from exc
            try:source_snap=_Snapshot(Path(args.source_root))
            except ContractError as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','restore source is unsafe') from exc
            try:config_held=_RetainedFile(Path(args.config))
            except ContractError as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','retrieval policy or config is unsafe') from exc
            from video_paper_wiki.catalog_store import _config
            from video_paper_wiki.secure_io import parse_strict_json
            os.lseek(config_held.fd,0,os.SEEK_SET);config_raw=os.read(config_held.fd,1_048_577)
            if len(config_raw)>1_048_576:raise ContractError('RESTORE_VERIFICATION_FAILED','retrieval policy or config exceeds limit')
            try:config_obj,_config_raw=_config(parse_strict_json(config_raw,invalid_code='CATALOG_STALE'),allow_policy=True)
            except ContractError as exc:raise ContractError('RESTORE_VERIFICATION_FAILED','retrieval policy or config is invalid') from exc
            try:restore_authority=_RetainedFile(Path(args.restore_root)/'.vpwiki-root-authority',required=False)
            except ContractError as exc:raise ContractError('RESTORE_ROOT_UNSAFE','restore root is unsafe') from exc
            restore_fd=restore_authority.parent_fd;restore_first=os.fstat(restore_fd)
            manifest=load_strict_json(args.manifest,missing_code='BACKUP_MANIFEST_INVALID',unsafe_code='BACKUP_MANIFEST_INVALID',invalid_code='BACKUP_MANIFEST_INVALID',changed_code='BACKUP_MANIFEST_INVALID')
            source_first=build_backup_manifest(args.source_root,_snapshot=source_snap);archive_first=read_regular_file(Path(args.archive),missing_code='BACKUP_ARCHIVE_INVALID',unsafe_code='BACKUP_ARCHIVE_INVALID',changed_code='BACKUP_ARCHIVE_INVALID',max_bytes=0xffffffff-1,limit_code='BACKUP_ARCHIVE_INVALID')
            fresh=os.open('.',os.O_RDONLY|getattr(os,'O_DIRECTORY',0),dir_fd=restore_fd)
            try:empty=not any(os.scandir(fresh))
            finally:close_fd(fresh)
            if source_first!=manifest:raise ContractError('RESTORE_VERIFICATION_FAILED','restore source differs from manifest')
            if not stat.S_ISDIR(restore_first.st_mode) or stat.S_IMODE(restore_first.st_mode)!=0o700 or not empty:return _emit_error('RESTORE_ROOT_UNSAFE','restore root is invalid')
            if not _confirm(words):
                manifest_held.verify_edge('RESTORE_VERIFICATION_FAILED');archive_held.verify_edge('RESTORE_VERIFICATION_FAILED');config_held.verify_edge('RESTORE_VERIFICATION_FAILED');source_snap.verify();_verify_parent_authority(restore_authority,'RESTORE_ROOT_UNSAFE')
                return _emit_error('HUMAN_APPROVAL_REQUIRED','interactive confirmation is required')
            manifest_held.verify_edge('RESTORE_VERIFICATION_FAILED');archive_held.verify_edge('RESTORE_VERIFICATION_FAILED');config_held.verify_edge('RESTORE_VERIFICATION_FAILED');source_snap.verify();_verify_parent_authority(restore_authority,'RESTORE_ROOT_UNSAFE')
            named=Path(args.restore_root).lstat()
            if ((named.st_dev,named.st_ino,stat.S_IMODE(named.st_mode))!=(restore_first.st_dev,restore_first.st_ino,stat.S_IMODE(restore_first.st_mode))
                    or build_backup_manifest(args.source_root,_snapshot=source_snap)!=source_first
                    or read_regular_file(Path(args.archive),missing_code='BACKUP_ARCHIVE_INVALID',unsafe_code='BACKUP_ARCHIVE_INVALID',changed_code='BACKUP_ARCHIVE_INVALID',max_bytes=0xffffffff-1,limit_code='BACKUP_ARCHIVE_INVALID')!=archive_first):return _emit_error('RESTORE_VERIFICATION_FAILED','restore inputs changed after confirmation')
            result=restore_backup_archive(archive=args.archive,source_root=args.source_root,restore_root=args.restore_root,
                manifest=manifest,_source_snapshot=source_snap,_archive_authority=archive_held,_restore_fd=restore_fd)
            # Runtime projections are intentionally absent from the truth
            # archive.  Establish their private container descriptor-relative
            # before invoking the sole accepted rebuild path.
            try:os.mkdir('.vault-meta',0o700,dir_fd=restore_fd)
            except FileExistsError:pass
            try:
                meta_st=os.stat('.vault-meta',dir_fd=restore_fd,follow_symlinks=False)
                if not stat.S_ISDIR(meta_st.st_mode) or stat.S_IMODE(meta_st.st_mode)!=0o700:
                    raise ContractError('RESTORE_ROOT_UNSAFE','runtime projection directory is unsafe')
            except OSError as exc:raise ContractError('RESTORE_ROOT_UNSAFE','runtime projection directory is unsafe') from exc
            from video_paper_wiki.catalog_store import build_current_catalog
            catalog_result=build_current_catalog(vault_root=args.restore_root,upstream_root=root,retrieval_config=config_obj)
            from video_paper_wiki.restore_verification import verify_restored_vault
            result['retrieval_config']=catalog_result['retrieval_config']
            result['retrieval_config_sha256']=catalog_result['retrieval_config_sha256']
            result['verification']=verify_restored_vault(source_root=args.source_root,restore_root=args.restore_root,manifest=manifest,upstream_root=root,config=catalog_result['retrieval_config'])
            manifest_held.verify_edge('RESTORE_VERIFICATION_FAILED');archive_held.verify_edge('RESTORE_VERIFICATION_FAILED');config_held.verify_edge('RESTORE_VERIFICATION_FAILED');source_snap.verify()
            _verify_parent_authority(restore_authority,'RESTORE_ROOT_UNSAFE')
            named=Path(args.restore_root).lstat()
            if (named.st_dev,named.st_ino,stat.S_IMODE(named.st_mode))!=(restore_first.st_dev,restore_first.st_ino,stat.S_IMODE(restore_first.st_mode)):
                raise RuntimeError('restore root changed')
            sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n');return 0
        except Exception as exc:
            try:
                if manifest_held is not None:manifest_held.verify_edge('RESTORE_VERIFICATION_FAILED')
                if archive_held is not None:archive_held.verify_edge('RESTORE_VERIFICATION_FAILED')
                if config_held is not None:config_held.verify_edge('RESTORE_VERIFICATION_FAILED')
                if source_snap is not None:source_snap.verify()
                if restore_authority is not None:_verify_parent_authority(restore_authority,'RESTORE_ROOT_UNSAFE')
                if restore_fd is not None:
                    named=Path(args.restore_root).lstat()
                    if (named.st_dev,named.st_ino,stat.S_IMODE(named.st_mode))!=(restore_first.st_dev,restore_first.st_ino,stat.S_IMODE(restore_first.st_mode)):
                        raise RuntimeError('restore root changed')
            except Exception as drift:exc=drift
            return _emit_error(getattr(exc,'code','RESTORE_VERIFICATION_FAILED'),getattr(exc,'message','backup restore failed'))
        finally:
            if restore_authority is not None:restore_authority.close()
            if source_snap is not None:source_snap.close()
            if config_held is not None:config_held.close()
            if archive_held is not None:archive_held.close()
            if manifest_held is not None:manifest_held.close()
    if words[:2]==['catalog','build']:
        catalog=_Parser(prog='vpwiki-admin catalog build')
        catalog.add_argument('--vault-root',required=True);catalog.add_argument('--upstream-root',required=True);catalog.add_argument('--config',required=True)
        args=catalog.parse_args(words[2:])
        if ns.upstream_root is not None and Path(args.upstream_root).resolve()!=Path(ns.upstream_root).resolve():
            parser.error('catalog build upstream roots differ')
        config_held=None
        try:
            from video_paper_wiki.catalog_store import _RetainedFile,_config,build_current_catalog
            from video_paper_wiki.secure_io import parse_strict_json
            try:config_held=_RetainedFile(Path(args.config))
            except Exception as exc:raise _UsageError('retrieval policy or config is unsafe') from exc
            os.lseek(config_held.fd,0,os.SEEK_SET);raw=os.read(config_held.fd,1_048_577)
            if len(raw)>1_048_576:raise _UsageError('retrieval policy or config exceeds limit')
            cfg,_raw=_config(parse_strict_json(raw,invalid_code='CATALOG_STALE'),allow_policy=True)
            if not _confirm(words):
                config_held.verify_edge('CATALOG_STALE');return _emit_error('OPERATOR_CONFIRMATION_REQUIRED','interactive confirmation is required')
            config_held.verify_edge('CATALOG_STALE');root=_verified_root(args.upstream_root)
            result=build_current_catalog(vault_root=args.vault_root,upstream_root=root,retrieval_config=cfg)
            config_held.verify_edge('CATALOG_STALE')
            sys.stdout.write(json.dumps({'ok':True,'data':result},sort_keys=True,separators=(',',':'))+'\n')
            return 0
        except Exception as exc:
            try:
                if config_held is not None:config_held.verify_edge('CATALOG_STALE')
            except Exception as drift:exc=drift
            return _emit_error(getattr(exc,'code','CATALOG_STALE'),getattr(exc,'message','catalog build failed'))
        finally:
            if config_held is not None:config_held.close()
    if ns.upstream_root is None:parser.error('--upstream-root is required for upstream passthrough')
    root=_verified_root(ns.upstream_root)
    if words[0]=='index':
        normalized,action=_index_arguments(words)
        if action=='build':
            sys.stderr.write('index build is disabled; use catalog build with the managed lock and config\n');return 2
        command=[sys.executable,'-I','-B','-X','utf8',str(root/'scripts'/'bm25-index.py'),*normalized]
        readonly=action in {'query','stats'}
    else:
        command=[sys.executable,'-I','-B','-X','utf8',str(root/'scripts'/'claude-obsidian.py'),*words]
        readonly=any(tuple(words[:len(prefix)])==prefix for prefix in READ_ONLY)
    if not readonly and not _confirm(words): return _emit_error('OPERATOR_CONFIRMATION_REQUIRED','interactive confirmation is required')
    if readonly:return subprocess.run(command,check=False).returncode
    return _emit_child_json(subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False))

def main(argv:list[str]|None=None)->int:
    try:
        return _main(argv)
    except _UsageError as exc:
        return _emit_error('USAGE_INVALID',str(exc))

if __name__=='__main__': raise SystemExit(main())
