#!/usr/bin/env python3
"""Offline tests for hara-site Commander release floor; fixtures are ephemeral."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("floor", HERE/"release_floor_gate_r3.py")
floor=importlib.util.module_from_spec(spec);spec.loader.exec_module(floor)
class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="hara-floor-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.version="0.3.55"
        self.files={
          "agent/linux.py":b'AGENT_VERSION = "0.3.55"\n',
          "agent/windows.ps1":b'$AgentVersion = "0.3.55"\n',
          "install/linux.sh":b'#!/bin/sh\nexit 0\n',
          "install/windows.ps1":b'exit 0\n',
        }
        self.rebuild()
    def rebuild(self):
        paths=[]
        for name,data in self.files.items():
            p=self.root/"apps/commander/public"/name
            p.parent.mkdir(parents=True,exist_ok=True)
            if p.exists() or p.is_symlink():p.unlink()
            p.write_bytes(data)
            paths.append({"path":name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
        m={"schema":"hara.commander-agent-release.v1","channel":"stable",
           "product":"H.A.R.A. Commander","agent_version":self.version,
           "files":paths}
        p=self.root/"apps/commander/public/release/agent-manifest.json"
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(m),encoding="utf-8")
    def hold(self,reason):
        with self.assertRaises(floor.Hold) as err:floor.release_floor(self.root)
        self.assertEqual(str(err.exception),reason)
    def test_valid_digest_version_is_still_not_release_approval(self):
        s=floor.release_floor(self.root)
        self.assertEqual(s["state"],"PASS_VERSION_DIGEST_ONLY_NOT_RELEASE_APPROVAL")
        self.assertFalse(s["signed_release_independently_attested"])
        self.assertFalse(s["release_owner_approved"])
    def test_legacy_0_3_14_is_blocked(self):
        self.version="0.3.14"
        self.files["agent/linux.py"]=b'AGENT_VERSION = "0.3.14"\n'
        self.files["agent/windows.ps1"]=b'$AgentVersion = "0.3.14"\n'
        self.rebuild();self.hold("VERSION_BELOW_FLOOR_MANIFEST")
    def test_linux_floor(self):
        self.version="0.3.54"
        self.files["agent/linux.py"]=b'AGENT_VERSION = "0.3.43"\n'
        self.rebuild();self.hold("VERSION_BELOW_FLOOR_LINUX")
    def test_windows_floor(self):
        self.version="0.3.54"
        self.files["agent/windows.ps1"]=b'$AgentVersion = "0.3.52"\n'
        self.rebuild();self.hold("VERSION_BELOW_FLOOR_WINDOWS")
    def test_manifest_above_agent(self):
        self.version="0.3.56"
        self.rebuild();self.hold("MANIFEST_GREATER_THAN_AGENT")
    def test_digest_changed_without_manifest(self):
        p=self.root/"apps/commander/public/agent/linux.py"
        p.write_bytes(b'AGENT_VERSION = "0.3.14-invalid"\n')
        self.hold("ARTIFACT_SIZE_agent_linux.py")
    def test_same_length_bad_digest(self):
        p=self.root/"apps/commander/public/agent/linux.py"
        p.write_bytes(b'AGENT_VERSION = "0.3.54"\n')
        self.hold("ARTIFACT_SHA_agent_linux.py")
    def test_manifest_duplicate(self):
        p=self.root/"apps/commander/public/release/agent-manifest.json"
        m=json.loads(p.read_text());m["files"][-1]=m["files"][0];p.write_text(json.dumps(m))
        self.hold("MANIFEST_FILE_ALLOWLIST")
    def test_manifest_missing(self):
        p=self.root/"apps/commander/public/release/agent-manifest.json"
        p.unlink();self.hold("ARTIFACT_MISSING_OR_SYMLINK")
    def test_symlink_refusal(self):
        p=self.root/"apps/commander/public/agent/linux.py";p.unlink()
        p.symlink_to("/etc/hosts")
        self.hold("ARTIFACT_MISSING_OR_SYMLINK")
    def test_channel_guard(self):
        p=self.root/"apps/commander/public/release/agent-manifest.json"
        m=json.loads(p.read_text());m["channel"]="experimental"
        p.write_text(json.dumps(m))
        self.hold("UNREVIEWED_CHANNEL")
    def test_invalid_version(self):
        self.version="0.3.55-unsafe";self.rebuild()
        self.hold("INVALID_SEMVER")
if __name__=="__main__":unittest.main(verbosity=2)
