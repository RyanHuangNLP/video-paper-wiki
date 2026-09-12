import os,fcntl,tempfile,json,sys,hashlib,datetime
from pathlib import Path
out=Path(sys.argv[1]);assert not out.exists()
checks={k:type(getattr(os,k,None)) is int and (getattr(os,k)!=0 or k=='O_RDONLY') for k in ['O_RDONLY','O_WRONLY','O_RDWR','O_CREAT','O_EXCL','O_NOFOLLOW','O_DIRECTORY','O_CLOEXEC','O_NONBLOCK']}
checks.update({f'dir_fd:{k}':getattr(os,k) in os.supports_dir_fd for k in ['open','stat','mkdir','link','unlink']})
checks.update({f'follow_symlinks:{k}':getattr(os,k) in os.supports_follow_symlinks for k in ['stat','link']})
checks['fd:scandir']=os.scandir in os.supports_fd
for k in ['fstat','read','lseek','write','fsync','dup','close']:checks['callable:'+k]=callable(getattr(os,k,None))
checks['callable:flock']=callable(getattr(fcntl,'flock',None))
for k,owner in [('SEEK_SET',os),('LOCK_EX',fcntl),('LOCK_NB',fcntl),('LOCK_UN',fcntl)]:checks[k]=type(getattr(owner,k,None)) is int
with tempfile.TemporaryDirectory(prefix='ciocap-',dir='/private/tmp') as scratch:
 fd=os.open(scratch,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
 duplicate=None
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);checks['actual_directory_flock']=True
  duplicate=os.dup(fd);checks['actual_lock_dup']=os.fstat(duplicate).st_ino==os.fstat(fd).st_ino
  os.fsync(fd);checks['actual_directory_fsync']=True
 finally:
  os.close(fd)
  if duplicate is not None:os.close(duplicate)
report={'schema':'full-todo.code-io-runtime-capability-probe.v1','recorded_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime':sys.executable,'version':sys.version,'checks':checks,'all_passed':all(checks.values()),'product_source_imported':False,'source_changed':False}
out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'path':str(out),'size_bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'all_passed':all(checks.values())}));assert all(checks.values())
