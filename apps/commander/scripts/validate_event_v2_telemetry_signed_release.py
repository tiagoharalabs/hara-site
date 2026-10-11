#!/usr/bin/env python3
"""Offline static contract for additive signed Event V2 telemetry release."""
from pathlib import Path
import importlib.util
import sys

ROOT=Path(__file__).resolve().parents[3]
SCRIPTS=ROOT/"apps/commander/scripts"
def load(name,relative):
    spec=importlib.util.spec_from_file_location(name,SCRIPTS/relative)
    obj=importlib.util.module_from_spec(spec)
    sys.modules[name]=obj
    spec.loader.exec_module(obj)
    return obj

old=load("hara_signer_v44_verify","event_v2_signed_release_v2.py")
new=load("hara_signer_v45_verify","event_v2_telemetry_release_v2.py")
assert old.VERSION=="0.3.44" and new.VERSION=="0.3.45"
assert old.KID==new.KID
assert old.FINGERPRINT==new.FINGERPRINT
assert old.CANARY_ID==new.CANARY_ID
assert len(old.FILES)==6 and len(new.FILES)==7
assert set(new.FILES)-set(old.FILES)=={"experimental/event_v2_telemetry.py"}
assert old.MANIFEST==new.MANIFEST and old.SIGNATURE==new.SIGNATURE
old_signer=(SCRIPTS/"event_v2_founder_fleet_release.py").read_text()
new_signer=(SCRIPTS/"event_v2_telemetry_fleet_release.py").read_text()
assert 'import event_v2_signed_release_v2 as trusted' in old_signer
assert 'import event_v2_telemetry_release_v2 as trusted' in new_signer
assert 'commander-event-v2-0.3.44-founder-signed-v2' in old_signer
assert 'commander-event-v2-0.3.45-founder-telemetry-signed-v2' in new_signer
old_verify=(SCRIPTS/"verify_event_v2_bundle_v2.py").read_text()
new_verify=(SCRIPTS/"verify_event_v2_telemetry_bundle_v2.py").read_text()
assert 'HARA_EVENT_V2_V2_SIX_ARTIFACTS' in old_verify
assert 'HARA_EVENT_V2_V2_SEVEN_ARTIFACTS' in new_verify
assert '"experimental/event_v2_telemetry.py"' in new_verify
assert 'AGENT_VERSION = "0.3.45"' in new_verify
assert 'AGENT_VERSION = "0.3.44"' in old_verify
assert (ROOT/"apps/commander/experimental/event_v2_telemetry.py").is_file()
assert (ROOT/"apps/commander/candidate/event_v2_full_agent.py").read_text().count(
    "return RESTRICTED.open_telemetry()")==1
print("EVENT_V2_TELEMETRY_SIGNED_RELEASE_SOURCE=PASS")
print("EVENT_V2_TELEMETRY_HISTORICAL_SIGNATURE_AND_VERIFIER=UNMODIFIED")
print("EVENT_V2_TELEMETRY_SIGNED_RELEASE_FILES=7")
