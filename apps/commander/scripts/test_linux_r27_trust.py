#!/usr/bin/env python3
"""R27: isolated Linux Commander one-time trust contract; never changes real device configuration."""
from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "candidate" / "linux_agent_history_r23.py"
spec = importlib.util.spec_from_file_location("hara_commander_r27_candidate", SRC)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class OneTimeTrustTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hara-r27-trust-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "device.env"
        self.initial = (
            "HARA_COMMANDER_URL=https://commander.invalid\n"
            "HARA_DEVICE_ID=HARA-DEVICE-TEST\n"
            "HARA_DEVICE_TOKEN=TEST_ONLY_NOT_REAL\n"
            "HARA_DEVICE_ARCH=x86_64\n"
            "HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION\n"
        )
        self.path.write_text(self.initial, encoding="utf-8")
        self.path.chmod(0o600)
        self.setting = patch.object(agent, "CONFIG_FILE", self.path)
        self.setting.start()
        self.addCleanup(self.setting.stop)
        self.session = patch.object(agent, "operator_session_active", return_value=False)
        self.session.start()
        self.addCleanup(self.session.stop)

    def mode(self):
        return next(x.split("=", 1)[1] for x in self.path.read_text().splitlines()
                    if x.startswith("HARA_COMMANDER_APPROVAL_MODE="))

    def invoke(self, requested, *, tty=False, response=None):
        fake_stdin = SimpleNamespace(isatty=lambda: tty)
        with patch.object(agent.sys, "stdin", fake_stdin), \
             patch("builtins.input", return_value=response) as prompt, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            agent.set_approval_mode(requested)
        return prompt, output.getvalue()

    def test_no_tty_cannot_establish_persistent_trust(self):
        with self.assertRaisesRegex(RuntimeError, "DEVICE_TRUST_LOCAL_TTY_REQUIRED"):
            self.invoke("always")
        self.assertEqual(self.path.read_text(), self.initial)

    def test_local_explicit_authorization_persists_without_reenrollment(self):
        prompt, output = self.invoke("always", tty=True, response="CONFIAR NESTE DISPOSITIVO")
        prompt.assert_called_once()
        self.assertIn("HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED", output)
        self.assertEqual(self.mode(), "PERSISTENT_TRUSTED")
        self.assertIn("HARA_DEVICE_ID=HARA-DEVICE-TEST", self.path.read_text())
        self.assertIn("HARA_DEVICE_TOKEN=TEST_ONLY_NOT_REAL", self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_wrong_consent_denies_without_writing(self):
        with self.assertRaisesRegex(RuntimeError, "DEVICE_TRUST_CONFIRMATION_DENIED"):
            self.invoke("persistent", tty=True, response="sim")
        self.assertEqual(self.path.read_text(), self.initial)

    def test_explicit_revocation_requires_no_second_prompt(self):
        self.invoke("always", tty=True, response="CONFIAR NESTE DISPOSITIVO")
        prompt, _ = self.invoke("ask", tty=False)
        prompt.assert_not_called()
        self.assertEqual(self.mode(), "ASK_EVERY_ACTION")

    def test_repeating_same_trust_does_not_prompt(self):
        self.invoke("always", tty=True, response="CONFIAR NESTE DISPOSITIVO")
        prompt, _ = self.invoke("always", tty=False)
        prompt.assert_not_called()
        self.assertEqual(self.mode(), "PERSISTENT_TRUSTED")

    def test_symlink_device_env_is_refused(self):
        target = Path(self.tmp.name) / "real.env"
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "DEVICE_CONFIG_SYMLINK_DENIED"):
            self.invoke("ask")
        self.assertEqual(target.read_text(), self.initial)

    def test_persistent_mode_approves_without_session_or_prompt(self):
        call = {"call_id": "R27-QA-PERSISTENT", "tool_id": "hara.process.run",
                "payload": {"command": "printf test"}}
        with patch.object(agent, "load_config", return_value={
            "HARA_COMMANDER_APPROVAL_MODE": "PERSISTENT_TRUSTED"
        }), patch.object(agent, "append_console_event") as log, \
            patch.object(agent, "read_operator_session",
                         side_effect=AssertionError("session must not be required")), \
            patch.object(agent, "_approval_paths",
                         side_effect=AssertionError("no approval files")):
            result = agent.request_local_approval(call)
        self.assertEqual(result["mode"], "PERSISTENT_TRUSTED")
        self.assertEqual(result["source"], "DEVICE_ENROLLMENT_POLICY")
        self.assertEqual(log.call_count, 1)

    def test_session_mode_approves_without_per_action_prompt(self):
        call = {"call_id": "R27-QA-SESSION", "tool_id": "hara.process.run",
                "payload": {"command": "printf test"}}
        with patch.object(agent, "load_config", return_value={
            "HARA_COMMANDER_APPROVAL_MODE": "SESSION_TRUSTED"
        }), patch.object(agent, "read_operator_session", return_value={
            "agent_version": agent.AGENT_VERSION, "approval_mode": "SESSION_TRUSTED"
        }), patch.object(agent, "append_console_event"), \
            patch.object(agent, "_approval_paths",
                         side_effect=AssertionError("no approval files")):
            result = agent.request_local_approval(call)
        self.assertEqual(result["mode"], "SESSION_TRUSTED")
        self.assertEqual(result["source"], "LOCAL_OPERATOR_SESSION")

    def test_console_help_does_not_claim_ctrl_c_revokes_persistent_trust(self):
        src = SRC.read_text(encoding="utf-8")
        self.assertIn("Ctrl+C fecha somente este console", src)
        self.assertIn("não revoga a confiança persistente", src)
        self.assertIn("Revogar: hara-commander approval-mode ask", src)
        self.assertIn('"PERSISTENT_TRUSTED":"dispositivo confiável"', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
