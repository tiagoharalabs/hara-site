#!/usr/bin/env python3
"""Offline mount-aware disk proof for immutable-root Linux hosts."""

import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[1] / "public/agent/linux.py"


def load_agent(root, source):
    prior = {key: os.environ.get(key) for key in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME")}
    try:
        for key in prior:
            os.environ[key] = str(root)
        spec = importlib.util.spec_from_file_location("hara_mount_resources_agent", source)
        agent = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = agent
        spec.loader.exec_module(agent)
        return agent
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main(source):
    with tempfile.TemporaryDirectory(prefix="hara-mount-resource-") as temporary:
        root = Path(temporary)
        data_mount = root / "var/home"
        data_mount.mkdir(parents=True)
        agent = load_agent(root, source)
        calls = []

        def usage(path):
            calls.append(str(path))
            assert str(path).startswith(str(data_mount)), path
            return SimpleNamespace(total=2_000_000, used=400_000, free=1_600_000)

        mountinfo = (
            "1 0 0:1 / / ro,relatime - composefs none ro\n"
            f"2 1 0:2 / {data_mount} rw,relatime - btrfs /dev/qa rw\n"
        )
        snapshot = agent._storage_mount_snapshot(mountinfo, data_mount / "user/agent", usage)
        assert snapshot["root_mount_fstype"] == "composefs" and snapshot["root_mount_read_only"] is True
        assert snapshot["agent_data_mount_path"] == str(data_mount)
        assert snapshot["agent_data_mount_fstype"] == "btrfs"
        assert snapshot["agent_data_mount_read_only"] is False
        assert snapshot["agent_data_disk_free_bytes"] == 1_600_000
        assert snapshot["agent_data_disk_status"] == "MOUNT_READ_WRITE"
        assert calls == [str(data_mount)], calls
        print("COMMANDER_IMMUTABLE_ROOT_USES_AGENT_DATA_MOUNT=PASS")

        calls.clear()
        readonly = mountinfo.replace(f"{data_mount} rw,relatime", f"{data_mount} ro,relatime")
        blocked = agent._storage_mount_snapshot(readonly, data_mount / "user/agent", usage)
        assert blocked["agent_data_disk_status"] == "MOUNT_READ_ONLY"
        assert blocked["agent_data_disk_free_bytes"] is None and calls == []
        print("COMMANDER_READ_ONLY_DATA_MOUNT_NOT_REPORTED_HEALTHY=PASS")

        unavailable = agent._storage_mount_snapshot("invalid\n", data_mount, usage)
        assert unavailable["agent_data_disk_status"] == "MOUNT_UNKNOWN"
        assert unavailable["agent_data_disk_free_bytes"] is None
        print("COMMANDER_MOUNTINFO_UNAVAILABLE_STAYS_UNKNOWN=PASS")

        actual = agent.system_resources()
        assert actual["cpu_logical"] >= 1
        assert actual["root_disk_total_bytes"] > 0
        assert "agent_data_disk_status" in actual
        print("COMMANDER_SYSTEM_RESOURCES_INCLUDES_MOUNT_STATUS=PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args()
    main(args.source.resolve(strict=True))
