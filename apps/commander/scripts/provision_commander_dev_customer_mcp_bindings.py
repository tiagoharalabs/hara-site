#!/usr/bin/env python3
"""Provision only missing DEV customer-MCP bindings from existing custody."""
from pathlib import Path
import json,os,subprocess,datetime
ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
CONFIG=APP/"wrangler.dev.jsonc"
NODE="/home/sartorius/.nvm/versions/node/v24.15.0/bin/node"
WRANGLER=ROOT/"node_modules/wrangler/bin/wrangler.js"
NAMES=("HARA_IDENTITY_MCP_DCR_PROJECT_AUD","HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_ID","HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_SECRET")
def wr(args,input_text=None):
    env={**os.environ,"PATH":str(Path(NODE).parent)+":"+os.environ.get("PATH",""),"CI":"true"}
    p=subprocess.run([NODE,str(WRANGLER),*args,"--config",str(CONFIG)],cwd=APP,env=env,input=input_text,text=True,capture_output=True,timeout=120)
    if p.returncode:raise RuntimeError("DEV_BINDINGS_WRANGLER_"+args[0].upper()+"_FAILED")
    return p.stdout
def main():
    cfg=json.loads(CONFIG.read_text())
    assert cfg["name"]=="hara-commander-dev-v2" and cfg["vars"]["ENVIRONMENT"]=="DEV"
    assert cfg["d1_databases"][0]["database_id"]=="698afbb9-e4eb-4c4e-98f2-f5abe28219d3"
    before=json.loads(wr(["secret","list"]))
    present={x["name"] for x in before}
    if set(NAMES)&present:raise RuntimeError("DEV_CUSTOMER_BINDINGS_EXIST_REVIEW_BEFORE_CHANGE")
    prior=json.loads(wr(["deployments","list","--json"]))
    program="""import json,pathlib,stat,os
p=pathlib.Path("/srv/hara/identity/secrets/mcp-introspection-client.json")
s=p.lstat()
assert stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600
v=json.loads(p.read_text())
assert v["client_id"]=="392945565756882947" and len(v["client_secret"])>=20
print(json.dumps({"client_id":v["client_id"],"client_secret":v["client_secret"]}))
"""
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=6","storage","sudo","-n","/usr/bin/python3","-I","-B","-"],input=program,text=True,capture_output=True,timeout=30)
    if p.returncode:raise RuntimeError("PRIVATE_EXISTING_INTROSPECTION_CUSTODY_UNAVAILABLE")
    v=json.loads(p.stdout)
    body={NAMES[0]:"392794504962310147",NAMES[1]:v["client_id"],NAMES[2]:v["client_secret"]}
    wr(["secret","bulk"],json.dumps(body));del body,v,p
    after=json.loads(wr(["secret","list"]));names={x["name"] for x in after}
    assert set(NAMES)<=names and present<=names
    deployments=json.loads(wr(["deployments","list","--json"]))
    report={"schema":"hara.dev-customer-mcp-bindings.v1","state":"PASS","environment":"DEV","names_added":list(NAMES),"existing_names_preserved":True,"source":"existing_custodied_identity_client","credentials_rotated":False,"values_printed":False,"production_mutation":False,"at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"prior_deployment":max(prior,key=lambda x:x["created_on"]),"deployment":max(deployments,key=lambda x:x["created_on"])}
    dest=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth/dev-binding-provisioning.json"
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(json.dumps({"state":"FAIL","safe_code":str(e) if isinstance(e,(RuntimeError,AssertionError)) else type(e).__name__,"values_printed":False}));raise SystemExit(1)
