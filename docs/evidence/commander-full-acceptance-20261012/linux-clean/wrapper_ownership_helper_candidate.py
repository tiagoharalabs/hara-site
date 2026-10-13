import hashlib,json,os,stat,sys,tempfile
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

def report(state):
    print("HARA_COMMANDER_CLI_WRAPPER_STATE="+state)
    return state

def snapshot_identity(st):
    return (st.st_dev,st.st_ino,st.st_uid,st.st_mode,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def read_owned_regular(path):
    try:
        before=path.lstat()
    except FileNotFoundError:
        return None,None,"MISSING"
    if stat.S_ISLNK(before.st_mode):
        return None,before,"SYMLINK"
    if not stat.S_ISREG(before.st_mode):
        return None,before,"NONREGULAR"
    if before.st_uid!=os.getuid():
        return None,before,"UNOWNED"
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        opened=os.fstat(fd)
        if snapshot_identity(opened)!=snapshot_identity(before):
            return None,before,"RACED"
        if opened.st_size>16384:
            return None,before,"UNRELATED"
        with os.fdopen(fd,"rb",closefd=False) as handle:
            raw=handle.read(16385)
        after=os.fstat(fd)
    finally:
        os.close(fd)
    if len(raw)>16384 or snapshot_identity(after)!=snapshot_identity(before):
        return None,before,"RACED"
    return raw,before,"OWNED_REGULAR"

def still_same(path,before,expected_raw):
    try:
        raw,current,kind=read_owned_regular(path)
    except OSError:
        return False
    return kind=="OWNED_REGULAR" and snapshot_identity(current)==snapshot_identity(before) and raw==expected_raw

def preserve_legacy_preimage(root,raw,before):
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    st=root.lstat()
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700:
        raise RuntimeError("CLI_WRAPPER_PREIMAGE_DIRECTORY_UNSAFE")
    target=root/("hara-wrapper-"+LEGACY_SHA256+".preimage")
    try:
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        existing,old,kind=read_owned_regular(target)
        if kind!="OWNED_REGULAR" or existing!=raw or stat.S_IMODE(old.st_mode)!=0o600:
            raise RuntimeError("CLI_WRAPPER_PREIMAGE_COLLISION")
    else:
        with os.fdopen(fd,"wb") as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
    metadata=root/("hara-wrapper-"+LEGACY_SHA256+".json")
    record=json.dumps({"schema":"hara.commander-owned-cli-preimage.v1","preimage_sha256":LEGACY_SHA256,"target_sha256":MANAGED_SHA256,"owner_uid":os.getuid(),"original_mode":oct(stat.S_IMODE(before.st_mode))},sort_keys=True)+"\n"
    try:
        fd=os.open(metadata,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        old,st,kind=read_owned_regular(metadata)
        if kind!="OWNED_REGULAR" or old!=record.encode() or stat.S_IMODE(st.st_mode)!=0o600:
            raise RuntimeError("CLI_WRAPPER_PREIMAGE_METADATA_COLLISION")
    else:
        with os.fdopen(fd,"w") as handle:
            handle.write(record);handle.flush();os.fsync(handle.fileno())

def manage(mode,path,preimages,external_hara=False):
    if mode not in {"install","uninstall"}:
        raise ValueError("CLI_WRAPPER_MODE_INVALID")
    raw,before,kind=read_owned_regular(path)
    if kind not in {"MISSING","OWNED_REGULAR"}:
        return report("PRESERVED_"+kind)
    if kind=="MISSING":
        if mode=="uninstall":
            return report("NOT_PRESENT")
        if external_hara:
            return report("PRESERVED_EXTERNAL_COMMAND")
        fd,tmp=tempfile.mkstemp(prefix=".hara-cli-wrapper.",dir=path.parent)
        try:
            with os.fdopen(fd,"wb") as handle:
                handle.write(MANAGED_BODY);handle.flush();os.fsync(handle.fileno())
            os.chmod(tmp,0o700)
            try:
                # Link creates only when the destination is still absent.
                os.link(tmp,path,follow_symlinks=False)
            except FileExistsError:
                return report("PRESERVED_RACED")
        finally:
            os.unlink(tmp)
        return report("FRESH_CREATED")
    sha=hashlib.sha256(raw).hexdigest()
    legacy=sha==LEGACY_SHA256
    managed=sha==MANAGED_SHA256
    if not legacy and not managed:
        return report("PRESERVED_UNRELATED")
    if mode=="uninstall":
        if not still_same(path,before,raw):
            return report("PRESERVED_RACED")
        path.unlink()
        return report("LEGACY_REMOVED" if legacy else "MANAGED_REMOVED")
    if managed:
        return report("ALREADY_MANAGED")
    preserve_legacy_preimage(preimages,raw,before)
    fd,tmp=tempfile.mkstemp(prefix=".hara-cli-wrapper.",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as handle:
            handle.write(MANAGED_BODY);handle.flush();os.fsync(handle.fileno())
        os.chmod(tmp,0o700)
        if not still_same(path,before,raw):
            return report("PRESERVED_RACED")
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return report("LEGACY_MIGRATED")

if __name__=="__main__":
    manage(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4]=="TRUE")
