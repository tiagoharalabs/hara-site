#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
R=Path("/tmp_hara/commander-win50-utf8-20261012");E=R/"docs/evidence/commander-full-acceptance-20261012/linux-clean"
def result(name):
 return json.loads((E/name).read_text())
files={"upgrade":"native-053-upgrade.json","fresh_install":"native-053-install.json","fresh_core":"native-053-core.json","rollback":"native-053-rollback.json","reenroll":"native-053-re-enroll.json","fresh_mcp":"native-053-mcp.json","upgrade_uninstall":"native-053-uninstall.json","wrapper_unit_fs":"wrapper-atomic-real-fs-uid2000.json"}
rows={}
for label,name in files.items():
 data=result(name);ok=str(data.get("state","")).startswith("PASS")
 if not ok:raise RuntimeError("QA_EVIDENCE_NOT_PASS_"+label)
 rows[label]={"state":data["state"],"evidence_file":name,"evidence_sha256":hashlib.sha256((E/name).read_bytes()).hexdigest()}
 if data.get("device_id"):rows[label]["device_id"]=data["device_id"]
 if isinstance(data.get("checks"),list):rows[label]["checks"]=len(data["checks"])
 if isinstance(data.get("checks"),int):rows[label]["checks"]=data["checks"]
report={"schema":"hara.commander-linux-clean-real-053-lifecycle-summary.v1","state":"PASS_REAL_053_LIFECYCLE_PENDING_24H_SOAK","vm_uuid":"27acff5d-dd62-4426-99e8-4f73400bc8b2","vm_hostname":"commander-linux-clean","os":"Ubuntu 24.04.5 LTS","native_uid":2000,"systemctl_backend":"real","backend_enrollment":"real_remote_DEV","mcp_scope":"actual_installed_local_stdio_with_real_DEV_enrollment","signed_release":"commercial-0.3.53-v13-rc-r3","signed_installer_sha256":"dae0a39f12a02920261a8051834d5b8426866a07e8a0d0acb9676c6605c8e3f8","signed_agent_sha256":"db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e","signed_manifest_sha256":"eebd7f4b209158b4a9a02b986365291c14e70bcad45106271078b2a373b6a257","qa_device_for_soak":rows["reenroll"]["device_id"],"default_mode":"ASK_EVERY_ACTION","qa_mutation_mode":"SESSION_TRUSTED_only_during_explicit_QA_CLI","human_ASK_acceptance_generated":False,"agent_autostart":False,"VM_autostart":False,"signed_product_source_modified":False,"backend_mock_used":False,"systemctl_shim_used":False,"founder_workloads_changed":False,"customer_secrets_exposed":False,"evidence":rows,"known_functional_defects":[{"code":"MANAGED_START_PROCESS_MAX_LINES_IGNORED","release":"0.3.53","managed_initial_cap":200,"bounded_max_lines_20_test":"PASS","managed_configurable_cap_20_test":"FAIL_preserved","next_action":"isolated_candidate_for_root_54_versioning"}],"pending":["24-hour real VM transport with rotated actual CLI sessions","root-incorporated signed54 and external acceptance for both functional fixes","final own-fixture cleanup coordinated by root"]}
report["known_functional_defects"].append({"code":"PUBLIC_HARA_WRAPPER_DROPS_REMAINING_ARGV","release":"0.3.53","command_trigger":"hara commander approval-mode session","observed_effect":"session argument omitted; mode getter only","scope_of_existing_session_tests":"Agent CLI invoked directly with correct arguments","next_action":"isolated_wrapper54_candidate_32_native_and61plus61FS_passed; root_versioning_pending"})
pilot=result("soak-cloud-pilot20.json")
if pilot.get("state")!="PASS" or pilot.get("calls")!=20 or pilot.get("success")!=20:raise RuntimeError("QA_CLOUD_PILOT_NOT_PASS")
report["cloud_pilot20"]=pilot
report["cloud_probe_scope"]="normal_DEV_internal_bridge_to_actual_enrolled_VM_Agent; real quota call metadata, fixture portal cookie expired, not customer OAuth proof"
(E/"native-053-lifecycle-summary.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({"state":report["state"],"evidence_count":len(rows),"qa_device_for_soak":report["qa_device_for_soak"],"known_functional_defects":len(report["known_functional_defects"]),"soak_pass_claimed":False}))