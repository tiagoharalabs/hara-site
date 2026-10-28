#!/usr/bin/env python3
"""Derive .59 from immutable .58 sources; preserve consumer validation."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

AGENT_PIN='bcc6538243573ce35f8ad54cb40bbe9d87c194913a54fc81241e94f5b7018f1d'
INSTALLER_PIN='27c856bb2b8ce8a100d8b258c8de544d99eb076ae8a0c6494110b17574ccfbc2'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source058',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    old_agent=(a.source058/'windows-agent.ps1').read_bytes()
    old_installer=(a.source058/'windows.source-only-candidate.ps1').read_bytes()
    assert sha(old_agent)==AGENT_PIN and sha(old_installer)==INSTALLER_PIN
    old_line="  $seeds=if($Role -ceq 'executor'){@($State.abandoned.Values)}else{@()}\n"
    new_lines="  # An empty if-output becomes null at the next function boundary.\n  # Keep an actual array so the handshake carries [] instead of [null].\n  [object[]]$seeds=@()\n  if($Role -ceq 'executor'){$seeds=@($State.abandoned.Values)}\n"
    text=old_agent.decode();assert text.count(old_line)==1 and text.count('0.3.58')==1
    agent=text.replace(old_line,new_lines,1).replace('0.3.58','0.3.59')
    install=old_installer.decode();assert install.count('0.3.58')==5
    install=install.replace('0.3.58','0.3.59')
    consumer_start='function Restore-WindowsRelayClaims('
    consumer_end='function Get-WindowsRelayPollSleep('
    before=text[text.index(consumer_start):text.index(consumer_end)]
    after=agent[agent.index(consumer_start):agent.index(consumer_end)]
    assert before==after, 'CONSUMER_VALIDATION_CHANGED'
    assert agent.replace('0.3.59','0.3.58').replace(new_lines,old_line,1)==text
    assert install.replace('0.3.59','0.3.58')==old_installer.decode()
    a.output.mkdir(exist_ok=True)
    outputs={'windows-agent.ps1':agent.encode(),'windows.source-only-candidate.ps1':install.encode()}
    for name,raw in outputs.items():
        with (a.output/name).open('xb') as f:f.write(raw)
    for name,old,new in [('windows-agent.patch',text,agent),('windows-installer.patch',old_installer.decode(),install)]:
        diff=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='frozen-0358',tofile='private-0359/'+name))
        with (a.output/name).open('x') as f:f.write(diff)
    report={'schema':'hara.commander.windows-0359-derivation.v1','state':'SOURCE_ONLY_NATIVE_REGRESSION_PENDING',
            'version':'0.3.59','original_agent_sha256':AGENT_PIN,'original_installer_sha256':INSTALLER_PIN,
            'consumer_validation_unchanged':True,'consumer_region_sha256':sha(before.encode()),
            'frozen_artifacts_changed':False,'installer_nonversion_bytes_unchanged':True,
            'agent_change':'Explicit object[] producer seeds; empty-state handshake remains an empty array across parameter binding.',
            'outputs':{name:{'sha256':sha(raw),'bytes':len(raw)} for name,raw in outputs.items()}}
    with (a.output/'DERIVATION-REPORT.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
