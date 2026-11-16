#!/usr/bin/env python3
"""Isolated regression of Agent 0.3.83 filesystem.edit. No live enrollment."""
import os,sys,hashlib,runpy,tempfile,stat,json
from pathlib import Path
ROOT=Path(os.environ.get("HARA_MODEFIX_SOURCE_DIR",str(Path(__file__).resolve().parent)))
def digest(data): return hashlib.sha256(data).hexdigest()
def load(name,root):
    os.environ["XDG_DATA_HOME"]=str(root/"data")
    os.environ["XDG_CONFIG_HOME"]=str(root/"config")
    return runpy.run_path(str(ROOT/name),run_name="modefix_isolated_module")
def call(f,p,old="old",new="new",expected=None,replace_all=False):
    return f({"call_id":"modefix-regression"},str(p),old,new,replace_all,expected)
def check_failure(fn,code):
    try: fn()
    except ValueError as e:
        assert str(e)==code,(str(e),code)
        return
    raise AssertionError("expected "+code)
checks=[]
with tempfile.TemporaryDirectory(prefix="qa-",dir=ROOT) as tmp:
    d=Path(tmp)
    base=load("agent.original.py",d/"old")
    p=d/"baseline.sh";p.write_text("old\n");p.chmod(0o755)
    out=call(base["filesystem_edit"],p,expected=digest(b"old\n"))
    actual=stat.S_IMODE(p.lstat().st_mode)
    assert p.read_text()=="new\n" and actual!=0o755,oct(actual)
    checks.append({"case":"baseline_reproduced","pre":"0o755","post":oct(actual)})
    patched=load("agent.candidate.py",d/"new")
    edit=patched["filesystem_edit"]
    for mode in (0o600,0o644,0o755):
        p=d/("target-"+oct(mode)+".sh")
        p.write_text("old\n");p.chmod(mode)
        prev_uid,prev_gid=p.stat().st_uid,p.stat().st_gid
        result=call(edit,p,expected=digest(b"old\n"))
        obs=stat.S_IMODE(p.lstat().st_mode)
        assert p.read_text()=="new\n" and obs==mode,(mode,obs)
        assert (p.stat().st_uid,p.stat().st_gid)==(prev_uid,prev_gid)
        assert result["mode_before"]==oct(mode) and result["mode_after"]==oct(mode) and result["mode_preserved"]
        m,b=patched["_load_preimage"](result["preimage_id"])
        assert m["sha256"]==digest(b"old\n") and int(m["mode"])==mode and b==b"old\n"
        if mode==0o755:
            rollback=patched["filesystem_rollback"]({"call_id":"modefix-rollback"},result["preimage_id"])
            assert p.read_bytes()==b"old\n" and stat.S_IMODE(p.stat().st_mode)==mode and rollback["restored_sha256"]==digest(b"old\n")
        checks.append({"case":"edit_and_preimage_"+oct(mode),"passed":True})
    p=d/"cas.txt";p.write_text("old")
    check_failure(lambda:call(edit,p,expected="0"*64),"FILE_PRECONDITION_FAILED")
    assert p.read_text()=="old"; checks.append({"case":"wrong_cas_rejected","passed":True})
    s=d/"symlink";s.symlink_to(p)
    check_failure(lambda:call(edit,s),"SYMLINK_MUTATION_DENIED")
    assert p.read_text()=="old";checks.append({"case":"symlink_rejected","passed":True})
    p.write_text("old+old")
    check_failure(lambda:call(edit,p),"EDIT_MATCH_AMBIGUOUS")
    assert p.read_text()=="old+old";checks.append({"case":"ambiguous_rejected","passed":True})
    p.write_text("old")
    p.chmod(0o1755)
    check_failure(lambda:call(edit,p),"FILE_SPECIAL_MODE_DENIED")
    assert p.read_text()=="old" and stat.S_IMODE(p.stat().st_mode)==0o1755
    checks.append({"case":"special_mode_rejected","passed":True})
    if 65534 in os.getgroups():
        grp=d/"alternate-group";grp.write_text("old")
        try:
            os.chown(grp,-1,65534)
        except OSError:
            checks.append({"case":"nonprimary_group_preserved","skipped":"NAMESPACE_GID_UNMAPPED"})
        else:
            result=call(edit,grp)
            assert grp.stat().st_gid==65534 and result["group_gid"]==65534
            checks.append({"case":"nonprimary_group_preserved","passed":True})
print(json.dumps({"state":"PASS","cases":len(checks),"checks":checks,"candidate_sha256":digest((ROOT/"agent.candidate.py").read_bytes())},sort_keys=True))
