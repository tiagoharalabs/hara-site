#!/usr/bin/env python3
"""Offline regression: ensure unsigned/legacy release cannot replace a newer agent.

Pure Python executes only the embedded standalone Linux version comparator.
Windows assertions are structural; PowerShell parser syntax is handled on Windows CI.
"""
from __future__ import annotations
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
LINUX=(ROOT/"apps/commander/public/install/linux.sh").read_text(encoding="utf-8")
WINDOWS=(ROOT/"apps/commander/public/install/windows.ps1").read_text(encoding="utf-8")
def linux_guard_code():
    marker="<<'PYVERSIONFLOOR'\n"
    assert LINUX.count(marker)==1
    start=LINUX.index(marker)+len(marker)
    end=LINUX.index("\nPYVERSIONFLOOR",start)
    code=LINUX[start:end]+"\n"
    compile(code,"linux_embedded_release_guard.py","exec")
    return code
class NoDowngradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="hara-release-floor-test-")
        self.addCleanup(self.temp.cleanup)
        self.path=pathlib.Path(self.temp.name)/"installed-agent.py"
    def verify(self,incoming,existing=None,symlink=False):
        if existing is not None:
            self.path.write_text('AGENT_VERSION = "'+existing+'"\n',encoding="utf-8")
        if symlink:
            self.path.symlink_to("/etc/hosts")
        return subprocess.run(["python3","-I","-B","-",incoming,str(self.path)],
              input=linux_guard_code(),text=True,capture_output=True,timeout=5)
    def test_embedded_python_syntax(self):
        self.assertTrue(linux_guard_code().startswith("from pathlib import Path"))
    def test_new_install_054_pass(self):
        self.assertEqual(self.verify("0.3.54").returncode,0)
    def test_new_install_055_pass(self):
        self.assertEqual(self.verify("0.3.55").returncode,0)
    def test_old_incoming_014_refused(self):
        p=self.verify("0.3.14")
        self.assertNotEqual(p.returncode,0)
        self.assertIn("BELOW_LINUX_FLOOR",p.stderr)
    def test_no_existing_downgrade_from_055(self):
        p=self.verify("0.3.54","0.3.55")
        self.assertNotEqual(p.returncode,0)
        self.assertIn("AGENT_DOWNGRADE_REFUSED",p.stderr)
    def test_equal_existing_054_pass(self):
        self.assertEqual(self.verify("0.3.54","0.3.54").returncode,0)
    def test_upgrade_existing_054_to_055_pass(self):
        self.assertEqual(self.verify("0.3.55","0.3.54").returncode,0)
    def test_malformed_semver_rejected(self):
        p=self.verify("0.3.54-foo")
        self.assertNotEqual(p.returncode,0)
    def test_unknown_installed_version_fails_closed(self):
        self.path.write_text('AGENT_VERSION = "UNKNOWN"\n')
        p=self.verify("0.3.55")
        self.assertNotEqual(p.returncode,0)
        self.assertIn("UNKNOWN",p.stderr)
    def test_symlink_existing_agent_refused(self):
        p=self.verify("0.3.55",symlink=True)
        self.assertNotEqual(p.returncode,0)
        self.assertIn("SYMLINK",p.stderr)
    def test_linux_called_before_agent_move(self):
        self.assertLess(LINUX.index("PYVERSIONFLOOR"),LINUX.index('mv -f "$tmp" "$AGENT"'))
        self.assertIn("AGENT_RELEASE_FLOOR_HOLD",LINUX)
    def test_windows_has_floor_and_monotonic_compare(self):
        self.assertIn('function Assert-AgentVersionFloor {',WINDOWS)
        self.assertIn('[Version]"0.3.55"',WINDOWS)
        self.assertIn('if ($candidate -lt $existing)',WINDOWS)
        self.assertIn('AGENT_DOWNGRADE_REFUSED',WINDOWS)
    def test_windows_update_checks_before_swap(self):
        name='Assert-AgentVersionFloor -IncomingVersion ([string]$meta.Version)'
        self.assertIn(name,WINDOWS)
        self.assertLess(WINDOWS.index(name),WINDOWS.index('Move-Item -Force $tmp $Agent'))
    def test_windows_install_checks_before_enrollment(self):
        block='if ($Action -eq "install") {\n  # Fail before enrollment/config changes'
        self.assertIn(block,WINDOWS)
        self.assertLess(WINDOWS.index(block),WINDOWS.index('if ($Action -eq "update")'))
        self.assertLess(WINDOWS.index(block),WINDOWS.index('$EnrollDeviceId'))
    def test_version_gate_is_not_signature_approval(self):
        manifest=(ROOT/"apps/commander/public/release/agent-manifest.json").read_text()
        self.assertIn('"agent_version": "0.3.14"',manifest)
        self.assertIn('AGENT_RELEASE_BELOW_LINUX_FLOOR',LINUX)
        self.assertIn('AGENT_RELEASE_BELOW_WINDOWS_FLOOR',WINDOWS)
        self.assertNotIn('SignedReleaseApproved = $true',WINDOWS)
if __name__=="__main__":
    unittest.main(verbosity=2)
