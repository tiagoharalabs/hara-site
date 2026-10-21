#!/usr/bin/env python3
"""Independent, fail-closed verifier for the one-device R22 Windows 0.3.55 canary.

Does not verify or approve a commercial Linux/Windows release; never deploys.
"""
from __future__ import annotations
import base64,hashlib,json
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding,rsa

ROOT=Path(__file__).resolve().parents[3]
CANARY=ROOT/"apps/commander/release-bundles/windows-founder-0.3.55-r22-canary"
EXPECTED_AGENT="07de45201052c6fbc98764dba619f1e83864b96eed0c998f1d007ad04bf5f57f"
EXPECTED_MANIFEST="0a7b63dbe5d286902ed155d5793c0bb22cb3d05c8b0fe95fcfb8edbf6daa18b9"
EXPECTED_PUB="93a595c5c7ee29d341fe0aee1a1625610e8015bf9df1ff64a3f4accdb39400b4"
EXPECTED_SIG="1fe5b5470f9edbbb56a42cbfe502a0142b1938a6f76e0c0e93dbcbd9a3a9b066"
TARGET="HARA-DEVICE-64adbd7a-02b1-4890-acdb-9543e8b48d00"
def h(b):return hashlib.sha256(b).hexdigest()
def dec(t):return base64.urlsafe_b64decode(t+"="*((-len(t))%4))
def verify() -> dict:
 agent=CANARY/"agent/windows.ps1"
 manifest=CANARY/"release/agent-manifest.json"
 signature=CANARY/"release/agent-manifest.sig.json"
 jwk=CANARY/"release/release-signing-public.jwk"
 for p in [agent,manifest,signature,jwk]:
  if not p.is_file() or p.is_symlink():raise ValueError("R22_CANARY_MISSING_OR_SYMLINK")
 a=agent.read_bytes();m=manifest.read_bytes();sig=signature.read_bytes()
 pub=json.loads(jwk.read_text());si=json.loads(sig);doc=json.loads(m)
 assert h(a)==EXPECTED_AGENT and h(m)==EXPECTED_MANIFEST and h(sig)==EXPECTED_SIG
 assert h(json.dumps(pub,sort_keys=True,separators=(',',':')).encode())==EXPECTED_PUB
 assert doc['schema']=='hara.commander-windows-founder-canary.v1'
 assert doc['agent_version']=='0.3.55' and doc['channel']=='FOUNDER_WINDOWS_CANARY'
 assert doc['device_id']==TARGET and doc['target_platform']=='WINDOWS'
 assert doc['files']==[{'path':'agent/windows.ps1','bytes':len(a),'sha256':EXPECTED_AGENT}]
 assert si['kid']==pub['kid']=='commander-release-v2'
 assert si['manifest_sha256']==h(m) and si['schema']=='hara.commander-release-signature.v1' and si['alg']=='RS256'
 assert all(k not in pub for k in ('d','p','q','dp','dq','qi'))
 key=rsa.RSAPublicNumbers(int.from_bytes(dec(pub['e']),'big'),int.from_bytes(dec(pub['n']),'big')).public_key()
 assert key.key_size==3072
 key.verify(dec(si['signature']),m,padding.PKCS1v15(),hashes.SHA256())
 assert (ROOT/'apps/commander/candidate/windows_agent_055.ps1').read_bytes()==a
 return {'schema':'hara.commander.windows-r22-signed-canary-verification.v1',
         'state':'PASS','version':'0.3.55','channel':'FOUNDER_WINDOWS_CANARY',
         'signed_agent_sha256':h(a),'manifest_sha256':h(m),'signature_sha256':h(sig),
         'alg':'RS256','key_size':key.key_size,'scope':'ONE_FOUNDER_WINDOWS_VM',
         'commercial_release_approved':False,'public_distribution_mutated':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
