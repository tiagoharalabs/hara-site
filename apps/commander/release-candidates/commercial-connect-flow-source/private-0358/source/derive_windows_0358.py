#!/usr/bin/env python3
"""Derive new .58 Windows source; never modify an admitted .56/.57 artifact."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

AGENT_PIN = 'a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'
INSTALLER_PIN = '68f0a76958e14f8f2830b6eb68d748bbad41e662b27b381dbf3a69e78bca03fd'
CONTROLLER_PIN = '2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da'
PAIRING_PIN = '9b024e3f648d9d78b36ed92f6f534f01b5158749dc81e775fd7274d33271ef5e'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_once(source, before, after):
    assert source.count(before) == 1, 'DERIVATION_ANCHOR_CHANGED'
    return source.replace(before, after, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', type=Path, required=True)
    parser.add_argument('--connect-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    old_agent = args.agent.read_bytes()
    old_install = (args.connect_source/'windows/windows.source-only-candidate.ps1').read_bytes()
    controller = (args.connect_source/'windows/Connect-Commander.ps1').read_bytes()
    pairing = (args.connect_source/'windows/Preserved-Pairing.ps1').read_bytes()
    assert sha(old_agent) == AGENT_PIN and sha(old_install) == INSTALLER_PIN
    assert sha(controller) == CONTROLLER_PIN and sha(pairing) == PAIRING_PIN
    agent = replace_once(old_agent.decode(),
        '  Set-Acl -LiteralPath $folder -AclObject $acl\n',
        '''  # Persist only the DACL. Reapplying owner/group from Get-Acl can demand
  # SeRestorePrivilege on an existing enrollment directory in a limited session.
  # The intended protected QA/SYSTEM access rules above remain unchanged.
  $accessOnly=New-Object Security.AccessControl.DirectorySecurity
  $accessOnly.SetSecurityDescriptorSddlForm(
    $acl.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]::Access),
    [Security.AccessControl.AccessControlSections]::Access)
  [IO.Directory]::SetAccessControl($folder,$accessOnly)
''')
    assert agent.count('0.3.56') == 1
    agent = agent.replace('0.3.56', '0.3.58')
    install = old_install.decode()
    helpers = '''
function Stop-AgentTaskAndWait([int]$Seconds=15) {
  $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\\' -ErrorAction Stop
  if([string]$task.State -in @('Ready','Disabled')){return}
  Stop-ScheduledTask -TaskName $TaskName -TaskPath '\\' -ErrorAction Stop
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt $Seconds){
    $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\\' -ErrorAction Stop
    if([string]$task.State -in @('Ready','Disabled')){return}
    Start-Sleep -Milliseconds 250
  }
  throw 'AGENT_TASK_STOP_UNCONFIRMED'
}

function Wait-AgentTaskStartup([string]$ExpectedVersion,[string]$PreviousStarted,[int]$Seconds=15) {
  $clock=[Diagnostics.Stopwatch]::StartNew()
  while($clock.Elapsed.TotalSeconds -lt $Seconds){
    $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\\' -ErrorAction Stop
    if([string]$task.State -ceq 'Running' -and (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf)){
      try{
        $status=Get-Content -LiteralPath $RuntimeStatus -Raw|ConvertFrom-Json
        if([string]$status.agent_version -ceq $ExpectedVersion -and $status.started_at_utc -and
           [string]$status.started_at_utc -cne $PreviousStarted){return $true}
      }catch{}
    }
    Start-Sleep -Milliseconds 250
  }
  return $false
}
'''
    install = replace_once(install, '\nfunction Convert-Base64UrlBytes', helpers+'\nfunction Convert-Base64UrlBytes')
    install = replace_once(install,
        '    if ($UpdateTaskWasRunning) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop }',
        '    if ($UpdateTaskWasRunning) { Stop-AgentTaskAndWait }')
    install = replace_once(install,
        '''      Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
      Start-Sleep -Seconds 2
      $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
      if (-not $task -or [string]$task.State -ne "Running" -or -not (Wait-AgentStartup $ExpectedVersion $PreviousStarted 10)) {''',
        '''      Start-ScheduledTask -TaskName $TaskName -TaskPath '\\' -ErrorAction Stop
      if (-not (Wait-AgentTaskStartup $ExpectedVersion $PreviousStarted 15)) {''')
    install = replace_once(install,
        '      if ($UpdateTaskWasRunning) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }',
        '      if ($UpdateTaskWasRunning) { Stop-AgentTaskAndWait }')
    install = replace_once(install,
        '''        Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $restoredTask=Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $RollbackState="STARTUP_ATTESTATION_FAILED"
        if ($restoredTask -and [string]$restoredTask.State -eq "Running" -and
            (Wait-AgentStartup $PreviousVersion $RollbackPreviousStarted 10)) { $RollbackState="PASS" }''',
        '''        Start-ScheduledTask -TaskName $TaskName -TaskPath '\\' -ErrorAction Stop
        $RollbackState="STARTUP_ATTESTATION_FAILED"
        if (Wait-AgentTaskStartup $PreviousVersion $RollbackPreviousStarted 15) { $RollbackState="PASS" }''')
    assert install.count('0.3.56') == 5
    install = install.replace('0.3.56', '0.3.58')
    core = controller[controller.index(b"$ErrorActionPreference='Stop'"):controller.index(b"\nif($MyInvocation.InvocationName -ne '.'){")]
    updated = {'windows-agent.ps1': agent.encode(), 'windows.source-only-candidate.ps1': install.encode()}
    assert updated['windows.source-only-candidate.ps1'].count(core) == 1
    assert updated['windows.source-only-candidate.ps1'].count(pairing) == 1
    args.output.mkdir(exist_ok=True)
    for name, raw in updated.items():
        with (args.output/name).open('xb') as stream:
            stream.write(raw)
    for name, before, after in [('windows-agent.patch',old_agent.decode(),agent),('windows-installer.patch',old_install.decode(),install)]:
        patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='frozen-source',tofile='private-0358/'+name))
        with (args.output/name).open('x') as stream:
            stream.write(patch)
    report={'schema':'hara.commander.windows-0358-derivation.v1','state':'SOURCE_ONLY_NOT_YET_SIGNED_OR_NATIVE_VALIDATED',
            'version':'0.3.58','original_agent_sha256':AGENT_PIN,'original_installer_sha256':INSTALLER_PIN,
            'controller_sha256':CONTROLLER_PIN,'pairing_helper_sha256':PAIRING_PIN,
            'embedded_controller_unchanged':True,'embedded_pairing_helper_unchanged':True,
            'version_literal_substitutions':{'agent':1,'installer':5},'frozen_artifacts_changed':False,
            'outputs':{name:{'sha256':sha(raw),'bytes':len(raw)} for name,raw in updated.items()}}
    with (args.output/'DERIVATION-REPORT.json').open('x') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
