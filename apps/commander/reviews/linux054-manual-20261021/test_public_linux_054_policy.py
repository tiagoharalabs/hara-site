#!/usr/bin/env python3
"""Static and isolated negative QA of proposed Commander Linux 0.3.54 installer."""
import hashlib
import pathlib
import re
import subprocess
import sys
import unittest
ROOT=pathlib.Path("/home/sartorius/.local/share/hara/codex-inbox/HARA_COMMANDER_054_ROLLOUT_20261021_R1/web_candidate")
SRC=ROOT/"linux.sh"
AGENT=ROOT/"linux.py"
CODE=SRC.read_text()

class Policy(unittest.TestCase):
    def test_integrity_preimage(self):
        self.assertEqual(hashlib.sha256(AGENT.read_bytes()).hexdigest(),"9f27d636fa8d0b2f012bdee08dfa5996eb15d896a0da9a8dd0ba1c8b0394c58c")
    def test_syntax(self):
        self.assertEqual(subprocess.run(["bash","-n",str(SRC)],capture_output=True).returncode,0)
    def test_agent_version(self):
        p=subprocess.run([sys.executable,"-B",str(AGENT),"--version"],capture_output=True,text=True)
        self.assertEqual(p.returncode,0)
        self.assertEqual(p.stdout.strip(),"0.3.54")
    def test_linux_independent_signed_channel(self):
        self.assertIn("/release/linux-agent-manifest.json",CODE)
        self.assertIn("/release/linux-agent-manifest.sig.json",CODE)
        self.assertNotIn("/release/agent-manifest.json",CODE)
        self.assertNotIn("/release/agent-manifest.sig.json",CODE)
    def test_persistent_trusted_customer_session(self):
        self.assertIn('mode="PERSISTENT_TRUSTED"',CODE)
        self.assertIn("HARA_COMMANDER_AGENT_AUTOSTART:-OFF",CODE)
        self.assertIn("MANUAL_START_POLICY_VIOLATED",CODE)
        self.assertIn("NEXT_STEP=Execute hara-commander start",CODE)
    def test_manual_off_branch_has_no_start(self):
        block=CODE.split('AGENT_AUTOSTART=',1)[1].split('esac',1)[0]
        self.assertIn('OFF)',block)
        self.assertNotIn('systemctl --user start "$SERVICE"',block.split('OFF)',1)[1])
    def test_active_founder_canary_guard(self):
        self.assertIn("HARA_COMMANDER_HOST_BOUND_V2_UPDATE_DENIED",CODE)
    def test_floor_regressions(self):
        part=CODE.split("check_version_floor() {",1)[1].split("\ndownload_agent() {",1)[0]
        fn="check_version_floor() {"+part
        for current,offered,should_pass in [
            ("0.3.43","0.3.54",True),
            ("0.3.54","0.3.54",True),
            ("0.3.55","0.3.54",False),
            ("banana","0.3.54",False),
        ]:
            r=subprocess.run(["bash","-c",fn+"\ncheck_version_floor "+current+" "+offered],
                             capture_output=True,text=True)
            self.assertEqual(r.returncode==0,should_pass,(current,offered,r.stderr))
    def test_agent_self_test(self):
        p=subprocess.run([sys.executable,"-B",str(AGENT),"--self-test"],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr[-400:])

if __name__=="__main__":
    unittest.main(verbosity=2)
