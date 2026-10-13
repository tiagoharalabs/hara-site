#!/usr/bin/env python3
from pathlib import Path
import ast, hashlib, json, difflib
R = Path("/tmp_hara/commander-win50-utf8-20261012")
P = R / "apps/commander/public/install/linux.sh"
D = R / "docs/evidence/commander-full-acceptance-20261012/linux-clean/wrapper-54-candidate"
raw=P.read_bytes()
assert hashlib.sha256(raw).hexdigest()=="7600f844c24696c7d2e0113328fb39425fa3182ae4e93ab8573d7ce4b74926a2"
a=raw.decode();b=a
old='MANAGED_BODY=LEGACY_BODY.replace(b"#!/bin/sh\\n",b"#!/bin/sh\\n# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1\\n",1)\nMANAGED_SHA256=hashlib.sha256(MANAGED_BODY).hexdigest()'
new='''MANAGED53_BODY=LEGACY_BODY.replace(b"#!/bin/sh\\n",b"#!/bin/sh\\n# HARA_COMMANDER_MANAGED_HARA_WRAPPER_V1\\n",1)
MANAGED53_SHA256="c69151f87529aebc0ebbf5c54e7f5ad4ef1a897b37c47a9ec68d9a6959bf3953"
assert hashlib.sha256(MANAGED53_BODY).hexdigest()==MANAGED53_SHA256
MANAGED_BODY=MANAGED53_BODY.replace(b'exec "$HOME/.local/bin/hara-commander" "${1:-status}"\\n',b'if [ "$#" -eq 0 ]; then\\n  set -- status\\nfi\\nexec "$HOME/.local/bin/hara-commander" "$@"\\n',1)
MANAGED_SHA256=hashlib.sha256(MANAGED_BODY).hexdigest()'''
edits=[
(old,new),
('def preimage_target(pfd,legacy):\n    base="hara-wrapper-"+LEGACY_SHA256+".preimage" if legacy else "hara-wrapper-uninstall-"+secrets.token_hex(12)+".preimage"', '''def preimage_target(pfd,legacy,managed53=False):
    migrating=legacy or managed53
    known_sha=LEGACY_SHA256 if legacy else MANAGED53_SHA256
    known_body=LEGACY_BODY if legacy else MANAGED53_BODY
    base="hara-wrapper-"+known_sha+".preimage" if migrating else "hara-wrapper-uninstall-"+secrets.token_hex(12)+".preimage"'''),
('if legacy and kind=="OWNED_REGULAR" and raw==LEGACY_BODY and stat.S_IMODE(st.st_mode)==0o600:\n        return "hara-wrapper-"+LEGACY_SHA256+"-"+secrets.token_hex(12)+".preimage"', 'if migrating and kind=="OWNED_REGULAR" and raw==known_body and stat.S_IMODE(st.st_mode)==0o600:\n        return "hara-wrapper-"+known_sha+"-"+secrets.token_hex(12)+".preimage"'),
('sha=hashlib.sha256(raw).hexdigest();legacy=sha==LEGACY_SHA256;managed=sha==MANAGED_SHA256\n        if not legacy and not managed:return report("PRESERVED_UNRELATED")', '''sha=hashlib.sha256(raw).hexdigest()
        legacy=sha==LEGACY_SHA256 and raw==LEGACY_BODY
        managed53=sha==MANAGED53_SHA256 and raw==MANAGED53_BODY
        managed=sha==MANAGED_SHA256 and raw==MANAGED_BODY
        if not legacy and not managed53 and not managed:return report("PRESERVED_UNRELATED")'''),
('target=preimage_target(pfd,legacy)', 'target=preimage_target(pfd,legacy,managed53)'),
('return report("LEGACY_MIGRATED" if new_wrapper_at(wfd,path.name) else "PRESERVED_RACED_TARGET")', '''if not new_wrapper_at(wfd,path.name):return report("PRESERVED_RACED_TARGET")
            return report("LEGACY_MIGRATED" if legacy else "MANAGED53_MIGRATED")''')]
for old,new in edits:
 assert b.count(old)==1,(old,b.count(old));b=b.replace(old,new)
assert b.count('"agent_version":"0.3.53"')==2 and b.count('"agent_version": "0.3.53"')==1
b=b.replace('"agent_version":"0.3.53"','"agent_version":"0.3.54"').replace('"agent_version": "0.3.53"','"agent_version": "0.3.54"')
program=b.split("<<'PYHARAWRAPPER'\n",1)[1].split("\nPYHARAWRAPPER",1)[0];ast.parse(program)
ns={"__name__":"private_unit"};exec(compile(program,"helper","exec"),ns)
assert ns["MANAGED53_SHA256"]=="c69151f87529aebc0ebbf5c54e7f5ad4ef1a897b37c47a9ec68d9a6959bf3953"
assert 'os.replace(' not in program and 'os.unlink(' not in program
(D/"linux-install-053-baseline.sh").write_bytes(raw)
(D/"linux-install-wrapper-054-candidate.sh").write_text(b)
(D/"linux-install-wrapper-054-candidate.patch").write_text("".join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile="a/apps/commander/public/install/linux.sh",tofile="b/apps/commander/public/install/linux.sh")))
tests=(R/"apps/commander/scripts/test_linux_installer_wrapper_ownership.py").read_text()
tests=tests.replace("0.3.53","0.3.54").replace("metadata-is-053","metadata-is-054")
ast.parse(tests);(D/"test_wrapper_054_legacy43_real_fs.py").write_text(tests)
t=tests.replace('legacy=scope["LEGACY_BODY"]','legacy=scope["MANAGED53_BODY"]').replace('scope["LEGACY_SHA256"]','scope["MANAGED53_SHA256"]').replace('"LEGACY_MIGRATED"','"MANAGED53_MIGRATED"').replace('"LEGACY_REMOVED"','"MANAGED_REMOVED"').replace('legacy-content-pin-is-immutable-043','managed53-content-pin-is-immutable-053')
ast.parse(t);(D/"test_wrapper_054_managed53_real_fs.py").write_text(t)
print(json.dumps({"state":"CANDIDATE_PREPARED","candidate_sha256":hashlib.sha256(b.encode()).hexdigest(),"managed53_sha256":ns["MANAGED53_SHA256"],"managed54_sha256":ns["MANAGED_SHA256"],"directory":str(D)}))
