#!/usr/bin/env python3
import argparse, importlib.util, json, subprocess, time, xml.etree.ElementTree as ET
VM='hara-win51-clean-20261012-r1'
UUID='d35599c8-b9ea-45e5-9ae9-fa047e84b8ba'
BASE='/tmp_hara/commander-windows-clean-20261012-r1'
def bridge():
    raw=subprocess.check_output(['virsh','--connect','qemu:///system','dumpxml',VM])
    assert ET.fromstring(raw).findtext('uuid')==UUID,'CLONE_UUID_REQUIRED'
    s=importlib.util.spec_from_file_location('b','/tmp_hara/windows_clean_qga_bridge.py')
    b=importlib.util.module_from_spec(s);s.loader.exec_module(b);return b
def bounded_result(b,pid,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        r=b.status(VM,pid)
        if r.get('state')=='EXITED':return r
        time.sleep(.3)
    raise RuntimeError('QGA_RESULT_WAIT_TIMEOUT')
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['launch','collect']);a=p.parse_args();b=bridge()
    if a.action=='launch':
        b.stage(VM,BASE+'/phase-private.json',b.CLEAN+'\\phase-private.json')
        pid=b.execute(VM,b.CLEAN+'\\windows_clean_schedule_phase.ps1')['pid']
    else:pid=b.execute(VM,b.CLEAN+'\\windows_clean_collect_phase.ps1')['pid']
    r=bounded_result(b,pid)
    print(json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
