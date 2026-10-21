#!/usr/bin/env python3
"""R16 — true function upload_version() but mocked network transport.

The fake Wrangler reads a temporarily modified stage asset while both real
preflight and postflight see pristine bytes. Demonstrates the TOCTOU window
in the reviewed source, not an observed Cloudflare incident.
"""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"apps/commander/scripts"))
import commander_versioned_prod_upload as upload
from stage_signed_commercial_assets import BUNDLES,ROLLBACK_RELEASE,require_signed_stage,stage

with tempfile.TemporaryDirectory(prefix="hara-r16-toctou-") as temp:
    staged=Path(temp)/"assets"
    bundle=BUNDLES[ROLLBACK_RELEASE]
    recorded=stage(staged,bundle,rollback_only=True)
    def checked(*args,**kwargs):
        return require_signed_stage(*args,expected_bundle=bundle,**kwargs)
    expected_digest=recorded["stage_tree_sha256"]
    source_tree=recorded["source_public_tree"]
    target=staged/"index.html"
    original=target.read_bytes()
    before_sha=hashlib.sha256(original).hexdigest()
    captured=[]
    def transient(_stage,_message):
        assert _stage==staged
        altered=original+b"\n<!--R16_UNAPPROVED_TRANSIENT_ASSET-->\n"
        target.write_bytes(altered)
        try:
            observed=target.read_bytes()
            captured.append({"asset_sha256":hashlib.sha256(observed).hexdigest(),
                             "asset_matches_approved":observed==original})
        finally:
            target.write_bytes(original)
        return subprocess.CompletedProcess([],0,"fake upload complete","")
    def permanent(_stage,_message):
        assert _stage==staged
        target.write_bytes(original+b"\n<!--R16_PERSISTENT_TAMPER-->\n")
        return subprocess.CompletedProcess([],0,"fake upload complete","")
    with patch.object(upload,"require_signed_stage",side_effect=checked):
        good=upload.upload_version(staged,expected_digest,source_tree,"R16 baseline",execute=False)
        assert good["state"]=="VERIFIED_NOT_UPLOADED"
        with patch.object(upload,"run_wrangler_upload",side_effect=transient):
            transient_result=upload.upload_version(staged,expected_digest,source_tree,
                                                  "R16 probe simulated",execute=True)
        assert target.read_bytes()==original
        with patch.object(upload,"run_wrangler_upload",side_effect=permanent):
            try:
                upload.upload_version(staged,expected_digest,source_tree,
                                      "R16 persistent mutation",execute=True)
                permanent_state="INCORRECTLY_ACCEPTED"
            except RuntimeError as exc:
                permanent_state=str(exc)
        target.write_bytes(original)
    assert captured and captured[0]["asset_matches_approved"] is False
    assert permanent_state=="SIGNED_UPLOAD_OUTCOME_UNKNOWN:STAGE_CHANGED"
    reproduced=(transient_result["state"]=="UPLOADED_VERSION_READBACK_REQUIRED" and
                captured[0]["asset_matches_approved"] is False)
    report={"schema":"hara.commander.peer-r16-upload-toctou.v1",
            "reviewed_head":"b99f97c2f7bf128390c750b89d22991f08443ef8",
            "checked_at_utc":datetime.now(timezone.utc).isoformat(),
            "signed_control_bundle":bundle.name,
            "signed_control_source_tree":source_tree,
            "signed_control_stage_digest":expected_digest,
            "baseline_status":good["state"],
            "persistent_mutation_detection":permanent_state,
            "transient_uploaded_asset_sha256":captured[0]["asset_sha256"],
            "approved_asset_sha256":before_sha,
            "transient_fake_upload_read_unapproved_bytes":not captured[0]["asset_matches_approved"],
            "transient_upload_reported_state":transient_result["state"],
            "reproduced":reproduced,
            "network_requests":0,"cloud_mutation":False,"production_mutation":False,
            "caveat":"fake Wrangler reads staged content while another writer briefly alters and restores it; shows local acceptance window, not proof deployed Worker differs"}
    (ROOT/"r16-upload-toctou-results.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    raise SystemExit(2 if reproduced else 1)
