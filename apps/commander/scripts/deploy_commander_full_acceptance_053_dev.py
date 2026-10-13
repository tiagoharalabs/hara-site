#!/usr/bin/env python3
"""Freeze and deploy the tested DEV-only .53 acceptance stage."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,subprocess,urllib.request
ROOT=Path(__file__).resolve().parents[3];APP=ROOT/"apps/commander"
STAGE=Path("/tmp_hara/commander-full-053-signed-stage-20261012-root-r3")
TARGET=STAGE/"apps/commander";CFG=TARGET/"wrangler.dev.jsonc"
NODE="/home/sartorius/.nvm/versions/node/v24.15.0/bin/node"
WRANGLER=ROOT/"node_modules/wrangler/bin/wrangler.js"
ORIGIN="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
EVIDENCE=ROOT/"docs/evidence/commander-full-acceptance-20261012/full-053"
MANIFEST="eebd7f4b209158b4a9a02b986365291c14e70bcad45106271078b2a373b6a257"
BUNDLE=APP/"release-bundles/commercial-0.3.53-v13-rc-r3"
NAMES=("HARA_IDENTITY_MCP_DCR_PROJECT_AUD","HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_ID","HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_SECRET")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(name,obj):
    EVIDENCE.mkdir(parents=True,exist_ok=True);(EVIDENCE/name).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def run(args,limit=120):
    env={**os.environ,"PATH":str(Path(NODE).parent)+":"+os.environ.get("PATH",""),"CI":"true"}
    p=subprocess.run([NODE,str(WRANGLER),*args,"--config",str(CFG)],cwd=TARGET,env=env,text=True,capture_output=True,timeout=limit)
    if p.returncode:raise RuntimeError("DEV053_WRANGLER_"+args[0].upper()+"_FAILED")
    return p.stdout
def guard():
    assert sha(TARGET/"src/auth.js")=="0abad1978968c676c8500dc9ff27323c862a202cd74ff1fc4d8fbca59dfe45ca","AUTH_ENTITLEMENT_PATCH_DRIFT"
    c=json.loads(CFG.read_text());assert c["name"]=="hara-commander-dev-v2" and c["vars"]["ENVIRONMENT"]=="DEV"
    assert c["d1_databases"][0]["database_id"]=="698afbb9-e4eb-4c4e-98f2-f5abe28219d3"
    assert c["vars"]["CUSTOMER_MCP_EDGE_DEV_ACCEPTANCE_ENABLED"]=="true"
    assert set(c["vars"]["DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS"].split(","))=={"394859086664957956","394861028946477060"}
    assert sha(TARGET/"public/release/agent-manifest.json")==MANIFEST
    for row in json.loads((BUNDLE/"release/agent-manifest.json").read_bytes())["files"]:
        assert sha(TARGET/"public"/row["path"])==row["sha256"]
def latest():
    ds=json.loads(run(["deployments","list","--json"]));return max(ds,key=lambda x:x["created_on"])
def prepare():
    assert not (STAGE/"dev-inputs.json").exists(),"DEV_INPUTS_ALREADY_FROZEN"
    old=TARGET/"src";old.rename(TARGET/"src-before-dev-freeze")
    shutil.copytree(APP/"src",TARGET/"src");shutil.copytree(APP/"migrations",TARGET/"migrations",dirs_exist_ok=True)
    shutil.copyfile(APP/"wrangler.dev.jsonc",CFG);guard()
    for name in NAMES:assert name in {x["name"] for x in json.loads(run(["secret","list"]))}
    files=[CFG,*sorted((TARGET/"src").rglob("*")),*sorted((TARGET/"migrations").glob("*.sql")),*sorted((TARGET/"public").rglob("*"))]
    rows={str(p.relative_to(TARGET)):sha(p) for p in files if p.is_file()}
    frozen={"schema":"hara.dev053-frozen-inputs.v1","at_utc":now(),"files":rows,"prior_deployment":latest(),"manifest_sha256":MANIFEST,"scope":"DEV_ONLY"}
    (STAGE/"dev-inputs.json").write_text(json.dumps(frozen,sort_keys=True,indent=2)+"\n")
    raw=run(["deploy","--dry-run","--outdir",str(STAGE/"dev-compiled-dryrun")],180)
    (STAGE/"dev-dryrun.log").write_text(raw)
    save("dev-preflight-r3.json",{"state":"PASS_DRY_RUN","at_utc":now(),"snapshot_sha256":sha(STAGE/"dev-inputs.json"),"compiled_sha256":sha(STAGE/"dev-compiled-dryrun/worker.js"),"prior_deployment":frozen["prior_deployment"],"scope":"DEV_ONLY","production_mutation":False})
    print(json.dumps({"state":"PASS_DRY_RUN","snapshot_sha256":sha(STAGE/"dev-inputs.json"),"production_mutation":False}))
def deploy():
    guard();f=json.loads((STAGE/"dev-inputs.json").read_text())
    for rel,digest in f["files"].items():assert sha(TARGET/rel)==digest,"FROZEN_INPUT_DRIFT"
    assert latest()["versions"]==f["prior_deployment"]["versions"],"DEV_DEPLOYMENT_DRIFT"
    migrations=run(["d1","execute","hara-commander-product-dev","--remote","--json","--command","SELECT name FROM d1_migrations ORDER BY id;"])
    migration_rows=json.loads(migrations)
    known={row["name"] for item in migration_rows for row in item.get("results",[])}
    pending={p.name for p in (TARGET/"migrations").glob("*.sql")}-known
    assert pending <= {"0035_approval_async_call_metadata.sql"}, "UNREVIEWED_DEV_MIGRATION"
    save("dev-migrations-before-r3.json",{"at_utc":now(),"response":migrations,"scope":"DEV_ONLY"})
    applied=run(["d1","migrations","apply","hara-commander-product-dev","--remote"],180)
    (STAGE/"dev-migrations-apply.log").write_text(applied)
    raw=run(["deploy","--outdir",str(STAGE/"dev-compiled-live"),"--message","Commander53 full acceptance RC; signed Linux wrapper migration/PTY and Windows Unicode; DEV QA OAuth opt-in"],180)
    (STAGE/"dev-deploy.log").write_text(raw)
    assert sha(STAGE/"dev-compiled-live/worker.js")==sha(STAGE/"dev-compiled-dryrun/worker.js"),"COMPILED_DRIFT"
    after=latest();assert len(after["versions"])==1 and after["versions"][0]["percentage"]==100
    save("dev-deployment-r3.json",{"schema":"hara.dev053-deployment.v1","state":"DEPLOYED_READBACK_PENDING","at_utc":now(),"prior_deployment":f["prior_deployment"],"deployment":after,"snapshot_sha256":sha(STAGE/"dev-inputs.json"),"compiled_sha256":sha(STAGE/"dev-compiled-live/worker.js"),"manifest_sha256":MANIFEST,"production_mutation":False,"scope":"DEV_ONLY"})
    print(json.dumps({"state":"DEPLOYED_READBACK_PENDING","deployment":after,"production_mutation":False}))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["prepare","deploy"]);a=p.parse_args()
    try:{"prepare":prepare,"deploy":deploy}[a.action]()
    except Exception as e:
        print(json.dumps({"state":"FAIL","safe_code":str(e) if isinstance(e,(RuntimeError,AssertionError)) else type(e).__name__,"production_mutation":False}));raise SystemExit(1)