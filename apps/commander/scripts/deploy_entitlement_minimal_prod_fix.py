#!/usr/bin/env python3
"""Apply the reviewed entitlement hash fix over the exact current PROD inputs."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,shutil,subprocess,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parents[3]
STAGE=Path("/tmp_hara/commander-entitlement-prod-fix-20261013-root-r5")
TARGET=STAGE/"app";CFG=TARGET/"wrangler.jsonc"
BASE=Path("/tmp_hara/commander-win50-utf8-rollout-20261012-root-v11/app")
REF="e2606d9f6aa643f521e025794e68ac060e83f8a5"
EXPECTED_VERSION="99a19edb-d2cf-4806-8c98-861e4513a2f7"
ORIGIN="https://commander.haralabs.com.br"
NODE="/home/sartorius/.nvm/versions/node/v24.15.0/bin/node"
WRANGLER=ROOT/"node_modules/wrangler/bin/wrangler.js"
EVIDENCE=ROOT/"docs/evidence/commander-full-acceptance-20261012/client-quota"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read_git(rel):return subprocess.check_output(["git","show",REF+":"+rel],cwd=ROOT)
def run(args,limit=180):
    env={**os.environ,"PATH":str(Path(NODE).parent)+":"+os.environ.get("PATH",""),"CI":"true"}
    p=subprocess.run([NODE,str(WRANGLER),*args,"--config",str(CFG)],cwd=TARGET,env=env,capture_output=True,text=True,timeout=limit)
    if p.returncode:raise RuntimeError("PROD_ENTITLEMENT_"+args[0].upper()+"_FAILED")
    return p.stdout
def latest():
    rows=json.loads(run(["deployments","list","--json"]))
    return max(rows,key=lambda r:r["created_on"])
def evidence(name,obj):
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    (EVIDENCE/name).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def guard():
    c=json.loads(CFG.read_text())
    assert c["name"]=="hara-commander" and c["vars"]["ENVIRONMENT"]=="PROD"
    assert c["d1_databases"][0]["database_id"]=="2c6473ff-9f65-4ee3-b9aa-a68996d47c46"
    assert "DEV_ACCEPTANCE_SELF_SERVICE_SUBJECTS" not in c["vars"]
def check_assets(rows):
    out=[]
    for row in rows:
        rel=row["path"];req=urllib.request.Request(ORIGIN+("/" if rel=="index.html" else "/"+rel),headers={"Cache-Control":"no-cache","User-Agent":"HARA-Commander-Owned-Product-Validation/1"})
        with urllib.request.urlopen(req,timeout=20) as response:
            raw=response.read();digest=hashlib.sha256(raw).hexdigest()
            transform=None
            if rel=="index.html" and digest!=row["sha256"]:
                clean,count=re.subn(rb'<script type="module" src="https://static[.]cloudflareinsights[.]com/beacon[.]min[.]js/[^"]+"[^>]*></script>\n',b'',raw)
                assert count==1,"UNEXPECTED_HTML_TRANSFORM"
                digest=hashlib.sha256(clean).hexdigest();transform="ONE_CLOUDFLARE_BEACON_REMOVED"
            assert response.status==200 and digest==row["sha256"],"PROD_ASSET_DRIFT"
            assert sha(TARGET/"public"/rel)==digest,"STAGE_ASSET_DRIFT"
            out.append({"path":rel,"sha256":digest,"status":200,"transport_transform":transform})
    return out
def prepare():
    assert not STAGE.exists(),"IMMUTABLE_STAGE_EXISTS"
    TARGET.mkdir(parents=True);(STAGE/"node_modules").symlink_to(ROOT/"node_modules",target_is_directory=True)
    for name in ("src","migrations"):shutil.copytree(BASE/name,TARGET/name)
    shutil.copytree(ROOT/"apps/commander/public",TARGET/"public")
    public43=Path("/tmp_hara/commander-win50-utf8-rollout-20261012-root-v11/public43")
    for p in public43.rglob("*"):
        if p.is_file():
            dest=TARGET/"public"/p.relative_to(public43);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    for name in ("wrangler.jsonc","package.json"):shutil.copyfile(BASE/name,TARGET/name)
    for rel in ("src/worker.js","src/approval-async-relay.mjs"):
        (TARGET/rel).write_bytes(read_git("apps/commander/"+rel))
    meta=json.loads(read_git("docs/evidence/commander-win52-product-validation-20261012-root/metadata-rollout-inputs.json"))
    for row in meta["files"]:assert sha(TARGET/row["path"])==row["sha256"],"PROD_BASE_INPUT_DRIFT"
    guard()
    prior=latest()
    assert prior["versions"]==[{"version_id":EXPECTED_VERSION,"percentage":100}],"PROD_VERSION_DRIFT"
    validation=json.loads(read_git("docs/evidence/commander-win52-product-validation-20261012-root/metadata-rollout-production-validation.json"))
    assets=check_assets(validation["public_assets"])
    raw=run(["deploy","--dry-run","--outdir",str(STAGE/"compiled-base")])
    (STAGE/"dryrun-base.log").write_text(raw)
    assert sha(STAGE/"compiled-base/worker.js")=="1111cf277f3ab2dbc9041f4b90ce7c64c0ca6c7e4edfd68cc5d8d6a26c902150","PROD_BASE_COMPILED_DRIFT"
    p=TARGET/"src/auth.js";text=p.read_text()
    old='const entitlementId = "HARA-ENTITLEMENT-" + fingerprint.slice(40, 64).toUpperCase();'
    new='const entitlementId = "HARA-ENTITLEMENT-" + fingerprint;'
    assert text.count(old)==1
    p.write_text(text.replace(old,new))
    for row in meta["files"]:
        if row["path"]!="src/auth.js":assert sha(TARGET/row["path"])==row["sha256"],"NON_AUTH_INPUT_CHANGED"
    raw=run(["deploy","--dry-run","--outdir",str(STAGE/"compiled-patched")])
    (STAGE/"dryrun-patched.log").write_text(raw)
    frozen={"schema":"hara.entitlement-minimal-prod-inputs.v1","at_utc":now(),"prior":prior,"files":{str(p.relative_to(TARGET)):sha(p) for p in sorted(TARGET.rglob("*")) if p.is_file()},"public_assets":assets,"compiled_sha256":sha(STAGE/"compiled-patched/worker.js")}
    (STAGE/"inputs.json").write_text(json.dumps(frozen,indent=2,sort_keys=True)+"\n")
    report={"state":"PASS_DRY_RUN","at_utc":now(),"prior":prior,"inputs_sha256":sha(STAGE/"inputs.json"),"compiled_sha256":frozen["compiled_sha256"],"auth_sha256":sha(p),"changed_inputs":["src/auth.js"],"all_public_assets_preserved":True,"d1_mutation":False,"production_mutation":False}
    report["auth_sha256"]=sha(TARGET/"src/auth.js")
    evidence("entitlement-minimal-prod-preflight.json",report)
    print(json.dumps(report))
def deploy():
    guard();f=json.loads((STAGE/"inputs.json").read_text())
    for rel,digest in f["files"].items():assert sha(TARGET/rel)==digest,"PROD_FROZEN_DRIFT"
    assert latest()["versions"]==f["prior"]["versions"],"PROD_DEPLOYMENT_DRIFT"
    check_assets(f["public_assets"])
    raw=run(["deploy","--outdir",str(STAGE/"compiled-live"),"--message","Commander: preserve full entitlement fingerprint for new identities; minimal auth-only fix"])
    (STAGE/"deploy.log").write_text(raw)
    assert sha(STAGE/"compiled-live/worker.js")==f["compiled_sha256"],"PROD_COMPILED_DRIFT"
    after=latest();assert len(after["versions"])==1 and after["versions"][0]["percentage"]==100
    assets=check_assets(f["public_assets"])
    with urllib.request.urlopen(urllib.request.Request(ORIGIN+"/api/health",headers={"User-Agent":"HARA-Commander-Owned-Product-Validation/1"}),timeout=20) as r:
        assert r.status==200 and json.loads(r.read())=={"ok":True,"service":"hara-commander"}
    report={"schema":"hara.entitlement-minimal-prod-deployment.v1","state":"PASS","at_utc":now(),"prior":f["prior"],"deployment":after,"inputs_sha256":sha(STAGE/"inputs.json"),"compiled_sha256":f["compiled_sha256"],"changed_inputs":["src/auth.js"],"all_public_assets_preserved":True,"public_assets":assets,"d1_mutation":False,"agents_modified":False,"dev_modified":False}
    evidence("entitlement-minimal-prod-deployment.json",report);print(json.dumps(report))
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=["prepare","deploy"])
    args=parser.parse_args()
    try:{"prepare":prepare,"deploy":deploy}[args.action]()
    except Exception as exc:
        print(json.dumps({"state":"FAIL","safe_code":str(exc) if isinstance(exc,(RuntimeError,AssertionError)) else type(exc).__name__}));raise SystemExit(1)