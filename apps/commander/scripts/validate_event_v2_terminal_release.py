#!/usr/bin/env python3
"""Static release invariants for the separate H.A.R.A. Event V2 v0.3.46 PTY fix.

No signing, private key access, network calls or service mutations.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "apps/commander/scripts"

def load(filename, module_name):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

v45=load("event_v2_telemetry_release_v2.py", "hara_pty_release_45")
v46=load("event_v2_terminal_release_v2.py", "hara_pty_release_46")
assert v45.VERSION=="0.3.45" and v46.VERSION=="0.3.46"
assert v45.KID==v46.KID and v45.FINGERPRINT==v46.FINGERPRINT
assert v45.CANARY_ID==v46.CANARY_ID
assert v45.FILES==v46.FILES and len(v46.FILES)==7
assert v45.MANIFEST==v46.MANIFEST and v45.SIGNATURE==v46.SIGNATURE
assert v45.PUBLIC==v46.PUBLIC and v45.PRIVATE==v46.PRIVATE

old_verify=(SCRIPTS/"verify_event_v2_telemetry_bundle_v2.py").read_text()
new_verify=(SCRIPTS/"verify_event_v2_terminal_bundle_v2.py").read_text()
assert 'agent_version") == "0.3.45"' in old_verify
assert 'agent_version") == "0.3.46"' in new_verify
assert 'AGENT_VERSION = "0.3.45"' in old_verify
assert 'AGENT_VERSION = "0.3.46"' in new_verify
assert 'HARA_EVENT_V2_V2_SEVEN_ARTIFACTS' in new_verify

old_fleet=(SCRIPTS/"event_v2_telemetry_fleet_release.py").read_text()
new_fleet=(SCRIPTS/"event_v2_terminal_fleet_release.py").read_text()
assert "import event_v2_telemetry_release_v2 as trusted" in old_fleet
assert "import event_v2_terminal_release_v2 as trusted" in new_fleet
assert '0.3.45-founder-telemetry-signed-v2' in old_fleet
assert '0.3.46-founder-pty-signed-v2' in new_fleet
assert 'verify_event_v2_terminal_bundle_v2.py' in new_fleet

agent=(ROOT/"apps/commander/public/agent/linux.py").read_text()
begin=agent.index("def _drain_completed_process_output(session):")
detect=agent.index("def _process_update_state(session):")
after=agent.index("def _drain_process(session,",detect)
drain=agent[begin:detect]
update=agent[detect:after]
assert "max_bytes=4*1024*1024" in drain
assert "deadline=time.monotonic()+0.25" in drain
assert "except BlockingIOError:" in drain
assert "errno.EIO" in drain
assert '_append_process_output(session,data.decode(' in drain
assert 'session["truncated"]=True' in drain
assert "_drain_completed_process_output(session)" in update
assert update.index("_drain_completed_process_output(session)") < update.index('os.close(int(session["fd"]))')
assert 'session["fd"]=-1' in update
assert "validate_process_terminal_drain.py" in (SCRIPTS/"commander_prelaunch_offline_gate.py").read_text()
print("HARA_EVENT_V2_PTY_SIGNED_RELEASE_SOURCE=PASS")
print("HARA_EVENT_V2_0_3_45_RELEASE_PATHS_UNMODIFIED=PASS")
print("HARA_EVENT_V2_0_3_46_SIGNATURE_ISOLATED=PASS")
print("HARA_EVENT_V2_PTY_DRAIN_BOUNDED=PASS")
