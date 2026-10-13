#!/usr/bin/env python3
"""Deploy tested DEV OAuth/backend while retaining signed public .43 assets."""
from pathlib import Path
import json,os,subprocess,shutil,hashlib,datetime
ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
SOURCE=Path("/tmp_hara/commander-full-053-signed-stage-20261012-root-r2/apps/commander")
STAGE=Path("/tmp_hara/commander-dev-real-oauth-backend-20261012-root-r1")
OLD=Path("/tmp_hara/commander-win50-utf8-rollout-20261012-root-v11/public43")
TARGET=STAGE/"apps/commander";CFG=TARGET/"wrangler.dev.jsonc"
NODE="/home/sartorius/.nvm/versions/node/v24.15.0/bin/node"
WRANGLER=ROOT/"node_modules/wrangler/bin/wrangler.js"
EVIDENCE=ROOT/"docs/evidence/commander-full-acceptance-20261012/real-oauth"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def wr(args):
    env={**os.environ,"PATH":str(Path(NODE).parent)+":"+os.environ.get("PATH",""),"CI":"true"}
    p=subprocess.run([NODE,str(WRANGLER),*args,"--config",str(CFG)],cwd=TARGET,env=env,text=True,capture_output=True,timeout=180)
    if p.returncode:raise RuntimeError("DEV_BACKEND_"+args[0].upper()+"_FAILED")
    return p.stdout
def latest():return max(json.loads(wr(["deployments","list","--json"])),key=lambda x:x["created_on"])
def main():
    gate=ROOT/"docs/evidence/commander-full-acceptance-20261012/windows-event-v2/prelaunch-offline-gate-053-119-final.json"
    g=json.loads(gate.read_text());assert g["checked"]==g["passed"]==119 and g["failed"]==0
    assert sha(SOURCE/"src/auth.js")=="43d8ca2e269c85a6fbb2c3a344748e4923df2dd7f3f6b7f001a5832d949da725"
    assert sha(OLD/"release/agent-manifest.json")=="72711a1099503e9c728e38162a6cf8aea17c783313d85fa486387bc537111092"
    assert not STAGE.exists()
    TARGET.mkdir(parents=True,mode=0o700)
    for folder in ("src","migrations"):shutil.copytree(SOURCE/folder,TARGET/folder)
    shutil.copytree(OLD,TARGET/"public");shutil.copyfile(SOURCE/"wrangler.dev.jsonc",CFG)
    (STAGE/"node_modules").symlink_to(ROOT/"node_modules",target_is_directory=True)
    c=json.loads(CFG.read_text());assert c["name"]=="hara-commander-dev-v2" and c["vars"]["ENVIRONMENT"]=="DEV"
    assert c["d1_databases"][0]["database_id"]=="698afbb9-e4eb-4c4e-98f2-f5abe28219d3"
    assert set(c["vars"]["DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS"].split(","))=={"394859086664957956","394861028946477060"}
    prior=latest()
    names={x["name"] for x in json.loads(wr(["secret","list"]))}
    assert {"HARA_IDENTITY_MCP_DCR_PROJECT_AUD","HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_ID","HARA_IDENTITY_MCP_INTROSPECTION_CLIENT_SECRET"}<=names
    m=json.loads(wr(["d1","execute","hara-commander-product-dev","--remote","--json","--command","SELECT name FROM d1_migrations ORDER BY id;"]))
    known={r["name"] for item in m for r in item.get("results",[])}
    pending={p.name for p in (TARGET/"migrations").glob("*.sql")}-known
    assert pending <= {"0035_approval_async_call_metadata.sql"},"UNREVIEWED_DEV_MIGRATION"
    inputs={str(p.relative_to(TARGET)):sha(p) for p in TARGET.rglob("*") if p.is_file()}
    (STAGE/"inputs.json").write_text(json.dumps(inputs,indent=2,sort_keys=True)+"\n")
    (STAGE/"dryrun.log").write_text(wr(["deploy","--dry-run","--outdir",str(STAGE/"compiled-dryrun")]))
    assert latest()["versions"]==prior["versions"],"DEV_RUNTIME_DRIFT"
    (STAGE/"migrations.log").write_text(wr(["d1","migrations","apply","hara-commander-product-dev","--remote"]))
    (STAGE/"deploy.log").write_text(wr(["deploy","--outdir",str(STAGE/"compiled-live"),"--message","DEV real QA OAuth/signup opt-in; legacy signed public43 assets retained; 119 offline checks PASS"]))
    assert sha(STAGE/"compiled-dryrun/worker.js")==sha(STAGE/"compiled-live/worker.js"),"COMPILED_DRIFT"
    after=latest();assert len(after["versions"])==1 and after["versions"][0]["percentage"]==100
    report={"schema":"hara.real-oauth-dev-backend-deployment.v1","state":"DEPLOYED_READBACK_PENDING","at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"prior_deployment":prior,"deployment":after,"source_auth_sha256":sha(TARGET/"src/auth.js"),"inputs_sha256":sha(STAGE/"inputs.json"),"compiled_sha256":sha(STAGE/"compiled-live/worker.js"),"signed_public_release":"0.3.43","signed_manifest_sha256":sha(TARGET/"public/release/agent-manifest.json"),"checks_passed":119,"production_mutation":False,"new_rc_assets_promoted":False,"pending_dev_migrations_applied":sorted(pending)}
    EVIDENCE.mkdir(parents=True,exist_ok=True);(EVIDENCE/"dev-backend-deployment.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(json.dumps({"state":"FAIL","safe_code":str(e) if isinstance(e,(RuntimeError,AssertionError)) else type(e).__name__,"production_mutation":False}));raise SystemExit(1)
