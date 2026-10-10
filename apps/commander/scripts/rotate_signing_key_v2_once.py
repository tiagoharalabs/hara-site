#!/usr/bin/env python3
"""One-time guarded RSA release-key v2 generation.

Creates new independent signing identity without altering v1 or printing secret
values. The public signing key can be distributed; the private key never enters
the source tree or installer bundle.
"""
from pathlib import Path
import base64
import hashlib
import json
import os
import stat
from cryptography.hazmat.primitives.asymmetric import rsa

HOME=Path.home()
SECRET_DIR=HOME/".config/hara-commander-release/v2"
PRIVATE=SECRET_DIR/"release-signing-private.jwk"
PUBLIC=Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/apps/commander/public/release/v2/release-signing-public.jwk")
KID="commander-release-v2"

def b64u(i):
    return base64.urlsafe_b64encode(int(i).to_bytes((int(i).bit_length()+7)//8,"big")).decode().rstrip("=")

if PRIVATE.exists():
    raise SystemExit("KEY_V2_ALREADY_EXISTS_FAIL_CLOSED")
assert os.geteuid()==os.getuid()
SECRET_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
SECRET_DIR.chmod(0o700)
PUBLIC.parent.mkdir(parents=True,exist_ok=True)
assert not PUBLIC.exists(),"PUBLIC_V2_ALREADY_EXISTS_FAIL_CLOSED"
key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
p=key.private_numbers()
pub={
    "kty":"RSA","alg":"RS256","use":"sig","kid":KID,
    "n":b64u(p.public_numbers.n),"e":b64u(p.public_numbers.e),
}
private={**pub,"d":b64u(p.d),"p":b64u(p.p),"q":b64u(p.q),
         "dp":b64u(p.dmp1),"dq":b64u(p.dmq1),"qi":b64u(p.iqmp)}
fd=os.open(PRIVATE,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
try:
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(private,f,sort_keys=True,indent=2)
        f.write("\n")
        f.flush();os.fsync(f.fileno())
    PRIVATE.chmod(0o600)
    assert (PRIVATE.stat().st_mode & 0o777)==0o600
    PUBLIC.write_text(json.dumps(pub,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    digest=hashlib.sha256(json.dumps(pub,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    print("NEW_RELEASE_KEY_KID="+KID)
    print("NEW_RELEASE_PUBLIC_FINGERPRINT_SHA256="+digest)
    print("NEW_RELEASE_KEY_STRENGTH_BITS=3072")
    print("NEW_PRIVATE_KEY_PERMISSIONS=0600")
    print("NEW_PRIVATE_KEY_EXPOSED=FALSE")
    print("V1_SIGNING_TRUST_ANCHOR=UNCHANGED")
except BaseException:
    try:PRIVATE.unlink()
    except FileNotFoundError:pass
    raise
