import importlib.util,json
s=importlib.util.spec_from_file_location("q","/tmp_hara/commander-win11-qga-readiness-20261011.py");q=importlib.util.module_from_spec(s);s.loader.exec_module(q);q.VM="hara-win51-clean-20261012-r1"
code=r"""
$ErrorActionPreference='Stop'
if((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'QA_UUID_REQUIRED'}
$t=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
$listener=@(Get-NetTCPConnection -LocalPort 18553 -State Listen -ErrorAction SilentlyContinue).Count
$h=Get-ScheduledTask -TaskName 'HARA Commander Clean QA Harness' -ErrorAction SilentlyContinue
if($t -or $listener -gt 0 -or ($h -and [string]$h.State -eq 'Running')){throw 'QA_LIFECYCLE_CLEANUP_INCOMPLETE'}
[ordered]@{state='PASS';schema='hara.windows-clean-post-uninstall.v1';clone_uuid='d35599c8-b9ea-45e5-9ae9-fa047e84b8ba';product_task_present=[bool]$t;loopback_fixture_listener_count=$listener;harness_running=([bool]$h -and [string]$h.State -eq 'Running');config_values_read=$false;credential_material_printed=$false}|ConvertTo-Json -Compress
"""
rc,out,err=q.powershell(code,wait=25)
assert rc==0 and not err,"POST_UNINSTALL_CHECK_FAILED"
print(out.strip())
