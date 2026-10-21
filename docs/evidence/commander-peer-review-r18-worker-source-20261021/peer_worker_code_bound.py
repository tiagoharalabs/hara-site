#!/usr/bin/env python3
"""R18: prove signed static assets do NOT bind the Wrangler Worker source.
Local mock uploader only. No Cloudflare, no signing keys, no real devices.
Run ONLY inside a detached, disposable QA checkout.
"""
from __future__ import annotations
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
import sys
HERE=Path(os.environ.get('HARA_PEER_QA_ROOT',Path(__file__).resolve().parent)).resolve()
if HERE.parent!=Path('/tmp') or not HERE.name.startswith('hara-commander-r18-'):
    raise SystemExit('R18_QA_REFUSES_NON_ISOLATED_WORKTREE')
if subprocess.run(['git','symbolic-ref','--quiet','--short','HEAD'],cwd=HERE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
    raise SystemExit('R18_QA_REQUIRES_DETACHED_HEAD')
sys.path.insert(0,str(HERE/"apps/commander/scripts"))
import commander_versioned_prod_upload as upload
from stage_signed_commercial_assets import BUNDLES,ROLLBACK_RELEASE,require_signed_stage,stage
def h(data):return hashlib.sha256(data).hexdigest()
worker=HERE/"apps/commander/src/worker.js"
assert worker.is_file()
assert (HERE/".git").is_dir()
source_before=worker.read_bytes()
assert b"R18_QA_UNAPPROVED_WORKER_SOURCE_CHANGE" not in source_before
head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=HERE,text=True).strip()
public_tree=subprocess.check_output(["git","rev-parse","HEAD:apps/commander/public"],cwd=HERE,text=True).strip()
bundle=BUNDLES[ROLLBACK_RELEASE]
with tempfile.TemporaryDirectory(prefix="hara-commander-r18-static-source-") as tmp:
  stage_dir=Path(tmp)/"approved-assets"
  staged=stage(stage_dir,bundle,rollback_only=True)
  digest=staged["stage_tree_sha256"]
  assert staged["source_public_tree"]==public_tree
  def check(path,*,expected_tree_sha256=None):
    return require_signed_stage(path,expected_bundle=bundle,expected_tree_sha256=expected_tree_sha256)
  with patch.object(upload,"require_signed_stage",side_effect=check):
    baseline=upload.upload_version(stage_dir,digest,public_tree,"QA MOCK ONLY",execute=False)
    assert baseline["state"]=="VERIFIED_NOT_UPLOADED"
    # Single deliberate modification to the isolated QA checkout, NOT Codex.
    worker.write_bytes(source_before+b"\nconsole.log('R18_QA_UNAPPROVED_WORKER_SOURCE_CHANGE');\n")
    try:
      after=h(worker.read_bytes())
      assert after!=h(source_before)
      # Rechecked signed stage still passes: only apps/commander/public is pinned.
      after_checked=upload.upload_version(stage_dir,digest,public_tree,"QA MOCK ONLY",execute=False)
      observed=[]
      def fake_wrangler_read_assets_and_worker(snapshot,message):
        assert snapshot!=stage_dir
        observed.append({"worker_sha256":h(worker.read_bytes()),
                         "worker_matches_reviewed":worker.read_bytes()==source_before,
                         "stage_sha256":h((snapshot/"index.html").read_bytes()),
                         "snapshot_exists":snapshot.is_dir()})
        return subprocess.CompletedProcess([],0,"mock upload submitted","")
      with patch.object(upload,"run_wrangler_upload",side_effect=fake_wrangler_read_assets_and_worker):
        result=upload.upload_version(stage_dir,digest,public_tree,"QA MOCK ONLY",execute=True)
      assert len(observed)==1
      reproduced=(after_checked["state"]=="VERIFIED_NOT_UPLOADED"
        and result["state"]=="UPLOAD_SUBMITTED_VERSION_READBACK_REQUIRED"
        and not observed[0]["worker_matches_reviewed"])
      report={"schema":"hara.commander.r18-worker-source-not-pinned.v1",
        "qa_head":head,"frozen_public_tree":public_tree,
        "signed_historical_bundle_used_only_as_fixture":bundle.name,
        "approved_stage_tree_sha256":digest,
        "worker_before_sha256":h(source_before),"worker_after_sha256":after,
        "checked_stage_after_worker_change":after_checked["state"],
        "fake_wrangler_observed":observed[0],
        "upload_result_state":result["state"],
        "missing_gate_reproduced":reproduced,
        "recommends":"Pin/compare Worker source/import graph/config to immutable reviewed commit and upload from frozen project snapshot, not live mutable APP",
        "network_requests":0,"cloud_mutations":False,"real_secrets_used":False,
        "at_utc":datetime.now(timezone.utc).isoformat()}
      print(json.dumps(report,indent=2))
      (HERE/"r18-worker-source-gate-results.json").write_text(json.dumps(report,indent=2)+"\n")
    finally:
      worker.write_bytes(source_before)
assert h(worker.read_bytes())==h(source_before)
print("QA_WORKER_RESTORED=TRUE")
raise SystemExit(2 if reproduced else 1)
