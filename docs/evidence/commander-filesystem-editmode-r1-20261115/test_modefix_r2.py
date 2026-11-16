#!/usr/bin/env python3
"""Offline-only Agent R2 regression. All target files live in disposable QA directories."""
import errno, hashlib, json, os, runpy, stat, tempfile
from pathlib import Path
ROOT=Path(os.environ.get("HARA_MODEFIX_SOURCE_DIR","/home/sartorius/hara-commander-modefix-20261115"))
def sha(b): return hashlib.sha256(b).hexdigest()
def must_reject(fn,expected):
    try: fn()
    except Exception as exc:
        assert str(exc)==expected,(type(exc).__name__,str(exc),expected)
        return
    raise AssertionError("expected rejection: "+expected)
def no_tmp(p):
    assert not list(p.parent.glob("."+p.name+".hara-tmp-*"))
def edit_fn(module):
    return module["filesystem_edit"]
def call(edit,p,old="old",new="new",expected=None,replace_all=False):
    return edit({"call_id":"r2-isolated"},str(p),old,new,replace_all,expected)
results=[]
with tempfile.TemporaryDirectory(prefix="qa-r2-",dir=ROOT) as temp:
    area=Path(temp)
    os.environ["XDG_DATA_HOME"]=str(area/"data")
    os.environ["XDG_CONFIG_HOME"]=str(area/"config")
    original=runpy.run_path(str(ROOT/"agent.original.py"),run_name="r2_isolated_original")
    corrected=runpy.run_path(str(ROOT/"agent.candidate.r2.py"),run_name="r2_isolated_fixed")
    old=edit_fn(original);edit=edit_fn(corrected)
    p=area/"baseline";p.write_text("old");p.chmod(0o755)
    call(old,p)
    assert stat.S_IMODE(p.stat().st_mode)!=0o755
    results.append("BASELINE_MODE_LOSS_REPRODUCED")
    for mode in (0o600,0o644,0o755):
        p=area/("mode-"+oct(mode));p.write_text("old");p.chmod(mode)
        before=(p.stat().st_uid,p.stat().st_gid)
        receipt=call(edit,p,expected=sha(b"old"))
        assert p.read_text()=="new" and stat.S_IMODE(p.stat().st_mode)==mode
        assert (p.stat().st_uid,p.stat().st_gid)==before
        assert receipt["mode_before"]==oct(mode) and receipt["mode_after"]==oct(mode)
        assert receipt["xattrs_preserved"] and receipt["xattr_count"]==0
        meta,data=corrected["_load_preimage"](receipt["preimage_id"])
        assert data==b"old" and meta["mode"]==mode
        if mode==0o755:
            corrected["filesystem_rollback"]({"call_id":"r2-rollback"},receipt["preimage_id"])
            assert p.read_bytes()==b"old" and stat.S_IMODE(p.stat().st_mode)==mode
        no_tmp(p)
        results.append("MODE_AND_PREIMAGE_"+oct(mode))
    p=area/"mismatch";p.write_text("old")
    must_reject(lambda:call(edit,p,expected="0"*64),"FILE_PRECONDITION_FAILED")
    assert p.read_text()=="old";results.append("CAS_DENIED")
    sym=area/"symlink";sym.symlink_to(p)
    must_reject(lambda:call(edit,sym),"SYMLINK_MUTATION_DENIED")
    assert p.read_text()=="old";results.append("SYMLINK_DENIED")
    p.write_text("old old")
    must_reject(lambda:call(edit,p),"EDIT_MATCH_AMBIGUOUS")
    assert p.read_text()=="old old";results.append("AMBIGUOUS_DENIED")
    p.write_text("old");p.chmod(0o1755)
    must_reject(lambda:call(edit,p),"FILE_SPECIAL_MODE_DENIED")
    assert p.read_text()=="old" and stat.S_IMODE(p.stat().st_mode)==0o1755
    results.append("SPECIAL_MODE_DENIED")
    ax=area/"xattrs";ax.write_text("old");ax.chmod(0o755)
    try: os.setxattr(ax,"user.hara_modefix",b"A",follow_symlinks=False)
    except OSError as exc: raise AssertionError("xattr support required for R2 QA") from exc
    info=call(edit,ax,expected=sha(b"old"))
    assert ax.read_text()=="new" and os.getxattr(ax,"user.hara_modefix")==b"A"
    assert stat.S_IMODE(ax.stat().st_mode)==0o755 and info["xattr_count"]==1
    results.append("XATTR_PRESERVED")
    failing=area/"failed-xattr";failing.write_text("old");failing.chmod(0o755)
    os.setxattr(failing,"user.hara_modefix",b"A")
    setreal=os.setxattr
    def failed_set(path,name,value,*args,**kwargs):
        if ".hara-tmp-" in str(path): raise PermissionError(errno.EPERM,"injected")
        return setreal(path,name,value,*args,**kwargs)
    os.setxattr=failed_set
    try: must_reject(lambda:call(edit,failing),"FILE_XATTR_PRESERVATION_DENIED")
    finally: os.setxattr=setreal
    assert failing.read_text()=="old" and os.getxattr(failing,"user.hara_modefix")==b"A"
    assert stat.S_IMODE(failing.stat().st_mode)==0o755
    no_tmp(failing);results.append("XATTR_COPY_FAIL_CLOSED")
    xrace=area/"xattr-race";xrace.write_text("old");os.setxattr(xrace,"user.hara_modefix",b"A")
    oldassert=edit.__globals__["_assert_path_matches_preimage"]
    count=[0]
    def insert_xattr_change(path,preimage):
        result=oldassert(path,preimage)
        count[0]+=1
        if count[0]==2: os.setxattr(path,"user.hara_modefix",b"B")
        return result
    edit.__globals__["_assert_path_matches_preimage"]=insert_xattr_change
    try: must_reject(lambda:call(edit,xrace),"FILE_XATTR_PREIMAGE_CHANGED")
    finally: edit.__globals__["_assert_path_matches_preimage"]=oldassert
    assert count[0]==2 and xrace.read_text()=="old" and os.getxattr(xrace,"user.hara_modefix")==b"B"
    no_tmp(xrace);results.append("XATTR_RACE_FAIL_CLOSED")
    replace_me=area/"replace-error";replace_me.write_text("old");replace_me.chmod(0o755)
    os.setxattr(replace_me,"user.hara_modefix",b"A")
    real_replace=os.replace
    def fail_replace(src,dst):
        if str(dst)==str(replace_me) and ".hara-tmp-" in str(src): raise PermissionError(errno.EPERM,"injected")
        return real_replace(src,dst)
    os.replace=fail_replace
    try:
        try: call(edit,replace_me)
        except PermissionError as exc: assert exc.errno==errno.EPERM
        else: raise AssertionError("injected replace should fail")
    finally: os.replace=real_replace
    assert replace_me.read_text()=="old" and stat.S_IMODE(replace_me.stat().st_mode)==0o755
    assert os.getxattr(replace_me,"user.hara_modefix")==b"A";no_tmp(replace_me)
    results.append("REPLACE_FAILURE_NO_MUTATION")
    too_many=area/"xattr-limit";too_many.write_text("old")
    for i in range(33): os.setxattr(too_many,"user.hara_limit_"+str(i),b"x")
    must_reject(lambda:call(edit,too_many),"FILE_XATTR_LIMIT_EXCEEDED")
    assert too_many.read_text()=="old";no_tmp(too_many)
    results.append("XATTR_COUNT_LIMIT_FAIL_CLOSED")
    if os.geteuid()==0:
        p=area/"nonprimary-gid";p.write_text("old");p.chmod(0o755)
        gid=1000 if os.getegid()!=1000 else 65534
        os.chown(p,-1,gid)
        info=call(edit,p)
        assert p.stat().st_gid==gid and info["group_gid"]==gid
        results.append("NONPRIMARY_GID_ROOT_PASS")
    else: results.append("NONPRIMARY_GID_NOT_TESTED_NONROOT")
print(json.dumps({"state":"PASS","checks":results,"total":len(results),"positive_gid":("NONPRIMARY_GID_ROOT_PASS" in results),"candidate_sha256":sha((ROOT/"agent.candidate.r2.py").read_bytes())},sort_keys=True))
