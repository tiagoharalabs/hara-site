#!/usr/bin/env python3
"""Offline tests for H.A.R.A. Commander native Services task-status adapter."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import pathlib
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "services_tasks_readonly_adapter.py"
if not SOURCE.is_file():
    SOURCE = HERE / "services_tasks_readonly_v1.py"

spec = importlib.util.spec_from_file_location("hara_services_status_adapter", SOURCE)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

GOOD = {
    "schema": "hara.contact-tasks.result.v1",
    "authority": "HARA_SERVICES",
    "state": "READY",
    "mutation_performed": False,
    "mutation_possible": False,
    "domain_receipt_refs": [],
    "queue_counts": {"pending": 0, "running": 0, "complete": 3, "failed": 1},
    "allowed_nodes": ["nucleo-a"],
    "allowed_modes": ["read-only", "workspace-write"],
}


def native_json(record=None, host="services"):
    return host + "\n" + json.dumps(GOOD if record is None else record) + "\n"


class TaskStatusAdapterTests(unittest.TestCase):
    def run_adapter(self, args, *, native=None, exit_code=0):
        result = SimpleNamespace(
            returncode=exit_code,
            stdout=native if native is not None else native_json(),
            stderr="",
        )
        out = io.StringIO()
        with patch.object(mod.subprocess, "run", return_value=result) as run, \
             contextlib.redirect_stdout(out):
            status = mod.main(args)
        return status, json.loads(out.getvalue()), run

    def test_status_returns_original_canonical_schema(self):
        status, response, run = self.run_adapter(["status"])
        self.assertEqual(status, 0)
        self.assertEqual(response, GOOD)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], mod.SSH_COMMAND)
        self.assertIn("StrictHostKeyChecking=yes", mod.SSH_COMMAND)
        self.assertIn("ForwardAgent=no", mod.SSH_COMMAND)
        self.assertNotIn("sudo", " ".join(mod.SSH_COMMAND))
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_no_argument_is_read_only_status(self):
        status, response, run = self.run_adapter([])
        self.assertEqual(status, 0)
        self.assertEqual(response["state"], "READY")
        run.assert_called_once()

    def test_write_and_unrecognized_inputs_never_call_ssh(self):
        for args in [
            ["submit"], ["review-submit"], ["get"], ["review-get"],
            ["status", "submit"], ["bogus"], ["--version"],
        ]:
            with self.subTest(args=args):
                status, response, run = self.run_adapter(args)
                self.assertEqual(status, 2)
                self.assertEqual(response["state"], "HOLD_NATIVE_SERVICES_QUEUE_STATUS")
                self.assertEqual(response["blocker"]["code"], "READ_ONLY_STATUS_ONLY")
                self.assertFalse(response["mutation_performed"])
                run.assert_not_called()

    def test_invalid_host_identity_denied(self):
        status, response, run = self.run_adapter(["status"], native=native_json(host="nucleo-a"))
        self.assertEqual(status, 2)
        self.assertEqual(response["blocker"]["code"], "NATIVE_SERVICES_HOST_IDENTITY_INVALID")

    def test_schema_and_authority_denied(self):
        for replacement in [
            {"authority": "ANOTHER_AUTHORITY"},
            {"schema": "hara.legacy.queue.v1"},
            {"state": "BLOCKED"},
        ]:
            with self.subTest(replacement=replacement):
                status, response, _ = self.run_adapter(["status"], native=native_json({**GOOD, **replacement}))
                self.assertEqual(status, 2)
                self.assertFalse(response["mutation_performed"])

    def test_write_flags_denied(self):
        for name in ("mutation_performed", "mutation_possible"):
            with self.subTest(name=name):
                status, response, _ = self.run_adapter(["status"], native=native_json({**GOOD, name: True}))
                self.assertEqual(status, 2)
                self.assertFalse(response["mutation_performed"])

    def test_queue_counts_must_be_int_and_nonnegative(self):
        for bad in (-1, True, None, "9"):
            with self.subTest(bad=bad):
                row = {**GOOD, "queue_counts": {**GOOD["queue_counts"], "pending": bad}}
                status, response, _ = self.run_adapter(["status"], native=native_json(row))
                self.assertEqual(status, 2)
                self.assertEqual(response["blocker"]["code"], "QUEUE_COUNTS_INVALID")

    def test_native_nonzero_denied(self):
        status, response, _ = self.run_adapter(["status"], exit_code=255)
        self.assertEqual(status, 2)
        self.assertEqual(response["blocker"]["code"], "NATIVE_SSH_OR_CANONICAL_CLI_FAILED")

    def test_timeout_denied(self):
        out = io.StringIO()
        with patch.object(mod.subprocess, "run", side_effect=subprocess.TimeoutExpired(mod.SSH_COMMAND, 18)), \
             contextlib.redirect_stdout(out):
            rc = mod.main(["status"])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out.getvalue())["blocker"]["code"], "NATIVE_STATUS_TIMEOUT")


if __name__ == "__main__":
    unittest.main(verbosity=2)