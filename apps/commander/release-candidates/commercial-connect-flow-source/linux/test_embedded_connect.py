"""Source integration fixtures; embedded Python and installer mutations stubbed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / "linux.source-only-candidate.sh"
CONTROLLER = HERE / "commander_connect.py"
EXPECTED = "a696a233e81b1b89b536fd4097af7b571762c953e54266cba49349308db74c1d"
DELIMITER = "PYHARA_COMMANDER_CONNECT_A696A233"
spec = importlib.util.spec_from_file_location("embedded_controller_test", CONTROLLER)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class EmbeddedConnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "python-calls.jsonl"
        self.config = self.root / "config"
        self.config.mkdir()
        self.data = self.root / "data"
        self.data.mkdir()
        self.bin = self.root / "stub-bin"
        self.bin.mkdir()
        stub = self.bin / "python3"
        stub.write_text("#!" + sys.executable + "\n" +
                        "import hashlib,json,os,sys\n" +
                        "raw=sys.stdin.buffer.read()\n" +
                        "with open(os.environ['HARA_TEST_PYTHON_LOG'],'a') as f:\n" +
                        " f.write(json.dumps({'argv':sys.argv[1:],'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})+'\\n')\n")
        stub.chmod(0o700)
        self.environment = os.environ.copy()
        self.environment.update({"PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
                                 "XDG_CONFIG_HOME": str(self.config), "XDG_DATA_HOME": str(self.data),
                                 "HARA_TEST_PYTHON_LOG": str(self.log),
                                 "HARA_COMMANDER_URL": "https://synthetic.invalid"})

    def run_candidate(self, arguments):
        result = subprocess.run(["bash", str(CANDIDATE), *arguments], env=self.environment, capture_output=True, text=True)
        calls = [json.loads(row) for row in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def test_exact_frozen_controller_bytes_embedded_once(self):
        source = CANDIDATE.read_bytes()
        header = ("    python3 - connect <<'" + DELIMITER + "'\n").encode()
        self.assertEqual(source.count(header), 1)
        embedded = source.split(header, 1)[1].split((DELIMITER + "\n").encode(), 1)[0]
        self.assertEqual(embedded, CONTROLLER.read_bytes())
        self.assertEqual(hashlib.sha256(embedded).hexdigest(), EXPECTED)

    def test_default_action_dispatches_connect_with_explicit_python_argv(self):
        result, calls = self.run_candidate([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1]["argv"], ["-", "connect"])
        self.assertEqual(calls[-1]["sha256"], EXPECTED)

    def test_connect_alias_normalizes_shell_action_without_forwarding_it(self):
        result, calls = self.run_candidate(["conectar"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-1]["argv"], ["-", "connect"])
        self.assertEqual(calls[-1]["sha256"], EXPECTED)

    def test_explicit_install_keeps_existing_enrollment_guard_no_connect(self):
        directory = self.config / "hara-commander"
        directory.mkdir()
        (directory / "device.env").write_text("SYNTHETIC_EXISTING_CONFIG=TRUE\n")
        result, calls = self.run_candidate(["install"])
        self.assertEqual(result.returncode, 8)
        self.assertIn("DEVICE_ALREADY_ENROLLED", result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0]["sha256"], EXPECTED)

    def test_explicit_update_keeps_unpaired_guard_no_connect(self):
        result, calls = self.run_candidate(["update"])
        self.assertEqual(result.returncode, 5)
        self.assertIn("DEVICE_NOT_ENROLLED", result.stderr)
        self.assertEqual(len(calls), 1)

    def test_controller_child_actions_are_explicit_no_default_recursion(self):
        flow = c.Connect()
        release = SimpleNamespace(url="https://synthetic.invalid/releases/0.3.57")
        for action in ("install", "update", "pair-existing", "re-enroll"):
            with self.subTest(action=action), patch.object(c.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
                flow.invoke_installer(Path("synthetic-installer.sh"), action, "https://synthetic.invalid", release)
                self.assertEqual(run.call_args.args[0], ["bash", "synthetic-installer.sh", action])
                self.assertEqual(run.call_args.kwargs["env"]["HARA_COMMANDER_RELEASE_URL"], release.url)

    def test_candidate_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(CANDIDATE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
