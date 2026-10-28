"""Synthetic local filesystem rollback fixtures; server revoke is stubbed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / "linux.source-only-candidate.sh").read_text()


def function(name):
    start = SOURCE.index(name + "() {\n")
    end = SOURCE.index("\n}\n", start) + 3
    return SOURCE[start:end]


class RollbackTests(unittest.TestCase):
    def fixture(self, *, old_config=False, revoke_exit=0):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_dir = root / "config"
            config_dir.mkdir(mode=0o700)
            config = config_dir / "device.env"
            backup = config_dir / "old.env"
            old = b"OLD_CONFIG_SYNTHETIC_REJECTED_CREDENTIAL\n"
            if old_config:
                backup.write_bytes(old)
                backup.chmod(0o600)
            config.write_bytes(b"NEW_CONFIG_SYNTHETIC_CREDENTIAL\n")
            config.chmod(0o600)
            agent = root / "agent"
            unit = root / "unit.service"
            agent.write_bytes(b"EXISTING_AGENT_BYTES\n")
            unit.write_bytes(b"EXISTING_UNIT_BYTES\n")
            cli = root / "commander-cli"
            cli.symlink_to(agent)
            before = (agent.read_bytes(), unit.read_bytes(), os.readlink(cli))
            environment = os.environ.copy()
            environment.update({
                "INSTALL_ENROLLED": "TRUE", "REENROLL_CONFIG_REPLACED": "TRUE",
                "REENROLL_CONFIG_EXISTED": "TRUE" if old_config else "FALSE",
                "REENROLL_BACKUP": str(backup) if old_config else "",
                "REENROLL_SERVICE_WAS_ACTIVE": "FALSE", "CONFIG_FILE": str(config),
                "CONFIG_DIR": str(config_dir), "BASE_URL": "https://synthetic.invalid",
                "DEVICE_ID": "synthetic-new-device", "DEVICE_TOKEN": "synthetic-new-secret-not-real",
                "SERVICE": "synthetic.service", "SYSTEMCTL_LOG": str(root / "systemctl.log"),
                "MOCK_REVOKE_EXIT": str(revoke_exit),
            })
            script = "set -euo pipefail\n" + function("record_pending_revoke") + "\n" + function("cleanup_failed_reenroll") + "\n"
            script += 'rollback_enrolled_device(){ return "$MOCK_REVOKE_EXIT"; }\n'
            script += 'systemctl(){ printf "%s\\n" "$*" >> "$SYSTEMCTL_LOG"; return 0; }\n'
            script += 'trap cleanup_failed_reenroll EXIT\nexit 23\n'
            result = subprocess.run(["bash", "-c", script], env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 23)
            self.assertEqual(before, (agent.read_bytes(), unit.read_bytes(), os.readlink(cli)))
            self.assertTrue(config_dir.is_dir())
            self.assertNotIn(environment["DEVICE_TOKEN"], result.stdout + result.stderr)
            if old_config:
                self.assertEqual(config.read_bytes(), old)
            else:
                self.assertFalse(config.exists())
            self.assertIn("--user stop synthetic.service", (root / "systemctl.log").read_text())
            pending = list(config_dir.glob(".pending-device-revoke-*.json"))
            if revoke_exit:
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0].stat().st_mode & 0o777, 0o600)
                receipt = json.loads(pending[0].read_text())
                self.assertEqual(receipt["device_id"], environment["DEVICE_ID"])
                self.assertEqual(receipt["device_token"], environment["DEVICE_TOKEN"])
                self.assertIn("HARA_COMMANDER_PENDING_REVOKE_RECOVERY_SAVED=TRUE", result.stdout)
                self.assertIn("SERVER_DEVICE_REVOKE_PENDING=TRUE", result.stderr)
            else:
                self.assertEqual(pending, [])
                self.assertIn("HARA_COMMANDER_FAILED_REENROLL_ROLLBACK=PASS", result.stderr)

    def test_failed_attach_removes_only_new_config(self):
        self.fixture()

    def test_failed_reenroll_restores_previous_config(self):
        self.fixture(old_config=True)

    def test_unavailable_revoke_retains_private_recovery(self):
        self.fixture(revoke_exit=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
