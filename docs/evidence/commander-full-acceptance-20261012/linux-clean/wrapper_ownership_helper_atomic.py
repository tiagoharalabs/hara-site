import ctypes,errno,hashlib,json,os,secrets,stat,sys
from pathlib import Path

LEGACY_SHA256="f2e30d042dd00e894c5916afb81ed193ff46f0949bd048a98c3c51722e42acaf"
LEGACY_BODY=b'''#!/bin/sh
set -eu
if [ "${1:-}" != "commander" ]; then
  echo "Usage: hara commander [start|status|stop|mcp|doctor|support|approval-mode]" >&2
  exit 64
fi
shift
exec "$HOME/.local/bin/hara-commander" "${1:-status}"
'''
MANAGED_BODY=LEGACY_BODY.replace(b"#!/bin/sh\n",b"#!/bin/sh\n# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1\n",1)
MANAGED_SHA256=hashlib.sha256(MANAGED_BODY).hexdigest()
assert hashlib.sha256(LEGACY_BODY).hexdigest()==LEGACY_SHA256
_RACE_ERRORS={errno.ENOENT,errno.ELOOP,errno.ENOTDIR,errno.ESTALE,errno.ENXIO}
_libc=ctypes.CDLL(None,use_errno=True)
_native_rename=getattr(_libc,"renameat2",None)
if _native_rename is not None:
    _native_rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    _native_rename.restype=ctypes.c_int

def report(state):
    print("HARA_COMMANDER_CLI_WRAPPER_STATE="+state)
    return state

def identity(st):
    # rename changes ctime; inode, owner, mode, content and mtime remain bound.
    return (st.st_dev,st.st_ino,st.st_uid,st.st_mode,st.st_size,st.st_mtime_ns,st.st_nlink)

def open_owned_directory(path,create_leaf=False,private=False):
    path=Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeError("CLI_WRAPPER_DIRECTORY_PATH_INVALID")
    fd=os.open("/",os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for n,part in enumerate(path.parts[1:]):
            last=n==len(path.parts[1:])-1
            if last and create_leaf:
                try:
                    os.mkdir(part,0o700,dir_fd=fd)
                    sync_fd=os.open(".",os.O_RDONLY|os.O_DIRECTORY,dir_fd=fd)
                    try:os.fsync(sync_fd)
                    finally:os.close(sync_fd)
                except FileExistsError:pass
            child=os.open(part,(os.O_RDONLY if last else os.O_PATH)|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        st=os.fstat(fd)
        if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o022 or (private and stat.S_IMODE(st.st_mode)!=0o700):
            raise RuntimeError("CLI_WRAPPER_DIRECTORY_OWNER_OR_MODE_INVALID")
        return fd
    except BaseException:
        os.close(fd);raise

def read_owned_regular_at(dfd,name):
    try:before=os.stat(name,dir_fd=dfd,follow_symlinks=False)
    except FileNotFoundError:return None,None,"MISSING"
    if stat.S_ISLNK(before.st_mode):return None,before,"SYMLINK"
    if not stat.S_ISREG(before.st_mode):return None,before,"NONREGULAR"
    if before.st_uid!=os.getuid():return None,before,"UNOWNED"
    if before.st_nlink!=1:return None,before,"HARDLINK"
    try:fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=dfd)
    except OSError as error:
        if error.errno in _RACE_ERRORS:return None,before,"RACED"
        raise
    try:
        opened=os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid!=os.getuid() or identity(opened)!=identity(before):
            return None,before,"RACED"
        if opened.st_size>16384:return None,before,"UNRELATED"
        with os.fdopen(fd,"rb",closefd=False) as handle:raw=handle.read(16385)
        after=os.fstat(fd)
    finally:os.close(fd)
    if len(raw)>16384 or identity(after)!=identity(before):return None,before,"RACED"
    return raw,before,"OWNED_REGULAR"

def rename_noreplace(sfd,source,tfd,target):
    if _native_rename is None:raise RuntimeError("CLI_WRAPPER_ATOMIC_COMMIT_UNSUPPORTED")
    if _native_rename(sfd,os.fsencode(source),tfd,os.fsencode(target),1)!=0:
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code))

def write_new_file_at(dfd,name,body,mode):
    fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode,dir_fd=dfd)
    with os.fdopen(fd,"wb") as handle:
        os.fchmod(handle.fileno(),mode)
        handle.write(body);handle.flush();os.fsync(handle.fileno())

def restore_if_empty(wfd,captured,name):
    try:rename_noreplace(wfd,captured,wfd,name)
    except OSError as error:
        if error.errno==errno.EEXIST:
            # Keep the actual displaced inode; never overwrite the new target.
            os.fsync(wfd)
            print("HARA_COMMANDER_CLI_WRAPPER_RETAINED="+json.dumps({"retained_name":captured,"requested_name":name},sort_keys=True))
            return False
        raise
    os.fsync(wfd);return True

def new_wrapper_at(wfd,name):
    # The staged inode has no pathname to swap or unlink.
    fd=os.open(".",os.O_WRONLY|os.O_TMPFILE,0o700,dir_fd=wfd)
    try:
        with os.fdopen(fd,"wb",closefd=False) as handle:
            os.fchmod(fd,0o700)
            handle.write(MANAGED_BODY);handle.flush();os.fsync(fd)
        linkat=getattr(_libc,"linkat",None)
        if linkat is None:raise RuntimeError("CLI_WRAPPER_ATOMIC_COMMIT_UNSUPPORTED")
        linkat.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_int]
        linkat.restype=ctypes.c_int
        # /proc refers to this open descriptor; AT_SYMLINK_FOLLOW binds that inode.
        if linkat(-100,os.fsencode("/proc/self/fd/"+str(fd)),wfd,os.fsencode(name),0x400)!=0:
            code=ctypes.get_errno()
            if code==errno.EEXIST:return False
            raise OSError(code,os.strerror(code))
        os.fsync(wfd);return True
    finally:os.close(fd)

def preimage_target(pfd,legacy):
    base="hara-wrapper-"+LEGACY_SHA256+".preimage" if legacy else "hara-wrapper-uninstall-"+secrets.token_hex(12)+".preimage"
    raw,st,kind=read_owned_regular_at(pfd,base)
    if kind=="MISSING":return base
    if legacy and kind=="OWNED_REGULAR" and raw==LEGACY_BODY and stat.S_IMODE(st.st_mode)==0o600:
        return "hara-wrapper-"+LEGACY_SHA256+"-"+secrets.token_hex(12)+".preimage"
    raise RuntimeError("CLI_WRAPPER_PREIMAGE_COLLISION")

def manage(mode,path,preimages,external_hara=False):
    if mode not in {"install","uninstall"}:raise ValueError("CLI_WRAPPER_MODE_INVALID")
    path=Path(path);preimages=Path(preimages)
    try:wfd=open_owned_directory(path.parent)
    except (OSError,RuntimeError):return report("PRESERVED_PARENT_UNSAFE")
    pfd=None
    try:
        raw,before,kind=read_owned_regular_at(wfd,path.name)
        if kind not in {"MISSING","OWNED_REGULAR"}:return report("PRESERVED_"+kind)
        if kind=="MISSING":
            if mode=="uninstall":return report("NOT_PRESENT")
            if external_hara:return report("PRESERVED_EXTERNAL_COMMAND")
            return report("FRESH_CREATED" if new_wrapper_at(wfd,path.name) else "PRESERVED_RACED")
        sha=hashlib.sha256(raw).hexdigest();legacy=sha==LEGACY_SHA256;managed=sha==MANAGED_SHA256
        if not legacy and not managed:return report("PRESERVED_UNRELATED")
        if mode=="install" and managed:return report("ALREADY_MANAGED")
        # Both reviewed directories are bound before any namespace mutation.
        bfd=open_owned_directory(preimages.parent,create_leaf=True,private=True)
        os.close(bfd)
        pfd=open_owned_directory(preimages,create_leaf=True,private=True)
        if os.fstat(wfd).st_dev!=os.fstat(pfd).st_dev:
            raise RuntimeError("CLI_WRAPPER_CROSS_FILESYSTEM_UNSUPPORTED")
        target=preimage_target(pfd,legacy)
        captured=".hara-cli-wrapper-displaced-"+secrets.token_hex(12)
        try:rename_noreplace(wfd,path.name,wfd,captured)
        except OSError as error:
            if error.errno in _RACE_ERRORS:return report("PRESERVED_RACED")
            raise
        try:moved,moved_st,moved_kind=read_owned_regular_at(wfd,captured)
        except BaseException:
            restore_if_empty(wfd,captured,path.name)
            raise
        if moved_kind!="OWNED_REGULAR" or identity(moved_st)!=identity(before) or moved!=raw:
            restored=restore_if_empty(wfd,captured,path.name)
            return report("PRESERVED_RACED" if restored else "PRESERVED_RACED_DISPLACED")
        try:
            # Retain the exact displaced inode, not just an earlier byte copy.
            rename_noreplace(wfd,captured,pfd,target)
        except OSError:
            restore_if_empty(wfd,captured,path.name)
            raise
        owned_fd=None
        try:
            owned_fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=pfd)
            if identity(os.fstat(owned_fd))!=identity(moved_st):
                raise RuntimeError("CLI_WRAPPER_PREIMAGE_IDENTITY_CHANGED")
            os.fchmod(owned_fd,0o600);os.fsync(owned_fd)
            os.fsync(pfd);os.fsync(wfd)
            metadata=target.rsplit(".",1)[0]+".json"
            record=json.dumps({"schema":"hara.commander-owned-cli-preimage.v2","preimage_sha256":sha,"target_sha256":MANAGED_SHA256 if mode=="install" else None,"owner_uid":os.getuid(),"original_mode":oct(stat.S_IMODE(before.st_mode)),"displaced_inode":moved_st.st_ino,"preimage_name":target},sort_keys=True).encode()+b"\n"
            write_new_file_at(pfd,metadata,record,0o600);os.fsync(pfd)
            if mode=="uninstall":
                try:os.stat(path.name,dir_fd=wfd,follow_symlinks=False)
                except FileNotFoundError:return report("LEGACY_REMOVED" if legacy else "MANAGED_REMOVED")
                return report("PRESERVED_RACED_TARGET")
            return report("LEGACY_MIGRATED" if new_wrapper_at(wfd,path.name) else "PRESERVED_RACED_TARGET")
        except BaseException:
            # Preserve availability on downstream errors without clobbering a new name.
            if owned_fd is not None and os.fstat(owned_fd).st_ino==moved_st.st_ino:
                os.fchmod(owned_fd,stat.S_IMODE(before.st_mode));os.fsync(owned_fd)
            try:rename_noreplace(pfd,target,wfd,path.name)
            except OSError as error:
                if error.errno!=errno.EEXIST:raise
                print("HARA_COMMANDER_CLI_WRAPPER_RETAINED="+json.dumps({"retained_name":target,"relative_directory":"installer-preimages","requested_name":path.name},sort_keys=True))
            os.fsync(pfd);os.fsync(wfd)
            raise
        finally:
            if owned_fd is not None:os.close(owned_fd)
    finally:
        if pfd is not None:os.close(pfd)
        os.close(wfd)

if __name__=="__main__":
    manage(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4]=="TRUE")