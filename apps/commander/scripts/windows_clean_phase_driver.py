#!/usr/bin/env python3
"""Real QA installer phases; secrets stay in mode-0600 staging files."""
import argparse, hashlib, json, os, shlex, stat, subprocess, time
from pathlib import Path
REPO=Path('/tmp_hara/commander-win50-utf8-20261012')
PRIVATE=REPO/'apps/commander/.generated/full-acceptance-20261012/windows-clean'
EVIDENCE=REPO/'docs/evidence/commander-full-acceptance-20261012/windows-clean'
DEV='https://hara-commander-dev-v2.tiago-sartori.workers.dev'
PHASES=['install','inspect','start','stop','update-stopped','update-running','negative-signature','uninstall']
REMOTE='/tmp_hara/commander-windows-clean-20261012-r1/phase-private.json'
def remote(action):
    command='python3 -I -B /tmp_hara/windows_clean_remote_phase.py '+shlex.quote(action)
    r=subprocess.run(['ssh','-o','BatchMode=yes','nucleo-a',command],capture_output=True,text=True,timeout=45)
    if r.returncode:raise RuntimeError('REMOTE_PHASE_TRANSPORT_FAILED')
    obj=json.loads(r.stdout)
    if obj.get('exit_code')!=0:raise RuntimeError('QGA_PHASE_SCRIPT_FAILED')
    return obj
def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=PHASES,required=True);p.add_argument('--pairing-file');p.add_argument('--attempt',default='r1');a=p.parse_args()
    assert a.attempt.replace('-','').isalnum(),'SAFE_ATTEMPT_REQUIRED'
    target=EVIDENCE/('real-'+a.phase+'-'+a.attempt+'.json')
    if target.exists():raise RuntimeError('EVIDENCE_ATTEMPT_COLLISION')
    PRIVATE.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(PRIVATE,0o700)
    data={'phase':a.phase,'dev_origin':DEV}
    if a.phase=='install':
        fixture=Path(a.pairing_file)
        assert not fixture.is_symlink() and stat.S_IMODE(fixture.stat().st_mode)==0o600,'PRIVATE_PAIRING_FILE_REQUIRED'
        f=json.loads(fixture.read_text());assert f['dev_origin']==DEV,'DEV_PAIRING_REQUIRED'
        assert f.get('pairing_token'),'ONE_TIME_PAIRING_REQUIRED'
        data['pairing_token']=f['pairing_token'];f=None
    file=PRIVATE/'phase-private.json'
    with open(file,'w',encoding='utf-8') as out:json.dump(data,out)
    os.chmod(file,0o600);data=None
    subprocess.run(['scp','-q',str(file),'nucleo-a:'+REMOTE],check=True,timeout=30)
    launch=remote('launch')
    assert launch.get('result',{}).get('state')=='QA_PHASE_STARTED','QA_PHASE_NOT_STARTED'
    print(json.dumps({'state':'QA_PHASE_STARTED','phase':a.phase,'real_installer_unchanged':True}),flush=True)
    deadline=time.monotonic()+230;last=0
    while time.monotonic()<deadline:
        r=remote('collect');result=r.get('result') or {}
        if result.get('schema')=='hara.windows-clean-real-installer-phase.v1':
            assert result.get('phase')==a.phase,'PHASE_RESULT_MISMATCH'
            EVIDENCE.mkdir(parents=True,exist_ok=True)
            if target.exists():raise RuntimeError('EVIDENCE_ATTEMPT_COLLISION')
            target.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
            print(json.dumps({'state':result['state'],'phase':a.phase,'error_code':result.get('error_code'),'evidence':str(target),'evidence_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'native_exit_code':result.get('native_exit_code'),'marker_count':len(result.get('markers',[]))}),flush=True)
            if result['state']!='PASS':raise SystemExit(1)
            file.unlink(missing_ok=True)
            subprocess.run(['ssh','-o','BatchMode=yes','nucleo-a','rm -f '+shlex.quote(REMOTE)],check=True,timeout=20)
            return
        if result.get('private_harness_error_present'):raise RuntimeError('QA_HARNESS_ERROR_PRIVATE_CUSTODY')
        if time.monotonic()-last>=12:
            print(json.dumps({'state':'QA_PHASE_WAITING','phase':a.phase,'task_state':result.get('task_state'),'task_last_result':result.get('task_last_result')}),flush=True);last=time.monotonic()
        time.sleep(1)
    raise RuntimeError('QA_PHASE_RESULT_TIMEOUT')
if __name__=='__main__':
    try:main()
    except Exception as e:
        code=str(e)
        print(json.dumps({'state':'HOLD','reason':code if code.replace('_','').isalnum() else type(e).__name__}),flush=True)
        raise SystemExit(1)
