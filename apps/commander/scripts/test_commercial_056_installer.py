"""Native Bash lifecycle tests with temporary state and mocked downloads/systemctl."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'release-candidates/commercial-0.3.56-source/install/linux.sh'
TEXT=SOURCE.read_text()
PREFIX,DISPATCH=TEXT.split('case "$ACTION" in\n',1)

class InstallerLifecycleTests(unittest.TestCase):
    def update(self,scenario,active=True):
        with tempfile.TemporaryDirectory(prefix='hara-056-installer-') as d:
            root=Path(d);data=root/'data/hara-commander';cfg=root/'config/hara-commander';units=root/'config/systemd/user'
            for p in [data,cfg,units]:p.mkdir(parents=True)
            old=b'AGENT_VERSION = "0.3.55"\nprint(AGENT_VERSION)\n'
            agent=data/'hara-commander-agent';agent.write_bytes(old)
            (cfg/'device.env').write_text('HARA_COMMANDER_URL=https://commander.invalid\nHARA_DEVICE_ID=synthetic\nHARA_DEVICE_TOKEN=synthetic\n')
            (units/'hara-commander-agent.service').write_text('synthetic only')
            mocks='''
download_agent(){ printf 'AGENT_VERSION = "0.3.56"\\nprint(AGENT_VERSION)\\n' > "$AGENT"; }
install_cli(){ [ "$QA_SCENARIO" != cli-fails ]; }
wait_for_agent_startup(){ [ "$QA_SCENARIO" != startup-fails ]; }
sleep(){ :; }
restart_count=0
systemctl(){
 if [ "$2" = is-active ]; then
   if [ "$QA_SCENARIO" = inactive ]; then return 1; fi
   [ "$QA_ACTIVE" = TRUE ]; return
 fi
 if [ "$2" = daemon-reload ]; then [ "$QA_SCENARIO" != reload-fails ]; return; fi
 if [ "$2" = restart ]; then
   restart_count=$((restart_count+1))
   if [ "$QA_SCENARIO" = both-restarts-fail ]; then return 1; fi
   if [ "$QA_SCENARIO" = restart-fails ] && [ "$restart_count" -eq 1 ]; then return 1; fi
 fi
 return 0
}
'''
            script=root/'harness.sh';script.write_text(PREFIX+mocks+'\ncase "$ACTION" in\n'+DISPATCH)
            env=dict(os.environ,HOME=d,XDG_DATA_HOME=str(root/'data'),XDG_CONFIG_HOME=str(root/'config'),QA_SCENARIO=scenario,QA_ACTIVE='TRUE' if active else 'FALSE')
            p=subprocess.run(['bash',str(script),'update'],env=env,capture_output=True,text=True,timeout=15)
            content=agent.read_bytes()
            if scenario=='success':
                self.assertEqual(p.returncode,0,p.stderr);self.assertIn(b'0.3.56',content)
                self.assertIn('UPDATE=PASS',p.stdout)
            else:
                self.assertEqual(p.returncode,7,p.stdout+p.stderr)
                self.assertEqual(content,old)
                self.assertNotIn('AGENT_UPDATE=PASS',p.stdout)
            return p

    def test_cli_failure_restores_previous_agent(self):self.update('cli-fails')
    def test_reload_failure_preserves_manual_stop_and_restores_agent(self):self.update('reload-fails',active=False)
    def test_restart_failure_rolls_back_and_attests_recovery(self):
        p=self.update('restart-fails');self.assertIn('ROLLBACK=PASS',p.stderr)
    def test_rollback_restart_failure_is_not_claimed_as_success(self):
        p=self.update('both-restarts-fail');self.assertIn('SERVICE_RESTART_FAILED',p.stderr);self.assertNotIn('ROLLBACK=PASS',p.stderr)
    def test_failed_startup_attestation_restores_agent(self):self.update('startup-fails')
    def test_active_successful_update(self):self.update('success')
    def test_stopped_successful_update_does_not_connect(self):
        p=self.update('success',active=False);self.assertIn('SKIPPED_MANUAL_STOP',p.stdout)
    def test_first_install_refuses_unrelated_preexisting_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);owned=root/'data/hara-commander';owned.mkdir(parents=True)
            file=owned/'unrelated';file.write_bytes(b'preserve')
            p=subprocess.run(['bash',str(SOURCE),'install'],env=dict(os.environ,HOME=d,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data')),input='',capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,8);self.assertEqual(file.read_bytes(),b'preserve');self.assertNotIn('Pairing token:',p.stdout)

if __name__=='__main__':unittest.main(verbosity=2)
