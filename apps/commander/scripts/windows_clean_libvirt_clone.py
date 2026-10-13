#!/usr/bin/env python3
"""Bounded live clone for isolated Commander Windows acceptance.

Never pivots, freezes, stops or redefines the source. The new VM starts with no
network interfaces. Guest sanitization and DEV enrollment are separate gates.
"""
import argparse
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCE = "commander-win11"
SOURCE_UUID = "4c76007a-1c12-445d-b1d5-3d94cca68856"
SOURCE_DISK = "/media/sartorius/MISC_2TB/hara_misc/VMs/commander-windows11/disks/commander-win11.qcow2"
CLONE = "hara-win51-clean-20261012-r1"
POOL = "default"
VOLUME = CLONE + ".qcow2"
DEST = "/var/lib/libvirt/images/" + VOLUME
BASE = Path("/tmp_hara/commander-windows-clean-20261012-r1")
STATE = BASE / "control-state.json"


def emit(value):
    print(json.dumps(value, sort_keys=True), flush=True)


def virsh(*args, timeout=30, check=True):
    result = subprocess.run(["virsh", "--connect", "qemu:///system", *args],
                            capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("LIBVIRT_" + args[0].upper().replace("-", "_") + "_FAILED")
    return result


def private_base():
    BASE.mkdir(mode=0o700, exist_ok=True)
    info = BASE.lstat()
    if BASE.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("CLONE_PRIVATE_BASE_UNSAFE")


def write_state(value):
    private_base()
    temp = BASE / ("state-" + uuid.uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(value, file, sort_keys=True)
        file.write("\n")
    os.replace(temp, STATE)


def state():
    value = json.loads(STATE.read_text())
    if value.get("source_uuid") != SOURCE_UUID or value.get("clone_name") != CLONE or value.get("destination") != DEST:
        raise RuntimeError("CLONE_CONTROL_IDENTITY_MISMATCH")
    return value


def source_xml(inactive=False):
    args = ["dumpxml", SOURCE] + (["--inactive"] if inactive else [])
    root = ET.fromstring(virsh(*args).stdout)
    if root.findtext("uuid") != SOURCE_UUID:
        raise RuntimeError("SOURCE_UUID_CHANGED")
    disks = [disk for disk in root.findall("./devices/disk") if disk.get("device") == "disk"]
    if len(disks) != 1 or disks[0].find("source").get("file") != SOURCE_DISK or disks[0].find("target").get("dev") != "sda":
        raise RuntimeError("SOURCE_DISK_CHANGED")
    if root.find("./devices/disk/mirror") is not None:
        raise RuntimeError("SOURCE_ALREADY_HAS_BLOCK_MIRROR")
    return root


def startcopy():
    private_base()
    if STATE.exists():
        raise RuntimeError("CLONE_STATE_EXISTS_NO_RETRY")
    root = source_xml(inactive=True)
    source_xml()
    if virsh("dominfo", CLONE, check=False).returncode == 0 or virsh("vol-info", VOLUME, "--pool", POOL, check=False).returncode == 0:
        raise RuntimeError("CLONE_DOMAIN_OR_VOLUME_COLLISION")
    if virsh("domstate", SOURCE).stdout.strip() != "running":
        raise RuntimeError("SOURCE_NOT_RUNNING")
    original = ET.tostring(root, encoding="utf-8")
    (BASE / "source-inactive.xml").write_bytes(original)
    os.chmod(BASE / "source-inactive.xml", 0o600)
    capacity = 171798691840
    vol = f"<volume><name>{VOLUME}</name><capacity unit='bytes'>{capacity}</capacity><allocation unit='bytes'>0</allocation><target><path>{DEST}</path><format type='qcow2'/><permissions><mode>0600</mode><owner>64055</owner><group>109</group></permissions></target></volume>"
    volfile = BASE / "volume.xml"
    volfile.write_text(vol)
    os.chmod(volfile, 0o600)
    virsh("vol-create", POOL, str(volfile))
    control = {"schema": "hara.windows-clean-clone-control.v1", "state": "COPY_STARTING", "source_name": SOURCE,
               "source_uuid": SOURCE_UUID, "source_disk": SOURCE_DISK, "source_inactive_xml_sha256": hashlib.sha256(original).hexdigest(),
               "clone_name": CLONE, "clone_uuid": str(uuid.uuid4()), "destination": DEST, "volume": VOLUME,
               "pool": POOL, "bandwidth_mib_per_second": 128, "pivot_requested": False, "source_freeze_requested": False,
               "source_redefined": False, "network_enabled_on_clone": False, "created_at_epoch": time.time()}
    write_state(control)
    emit({"state": "COPY_STARTING", "clone_name": CLONE, "bandwidth_mib_per_second": 128, "pivot": False})
    def interrupted(_signum, _frame):
        raise RuntimeError("COPY_CONTROLLER_INTERRUPTED")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        result = virsh("blockcopy", SOURCE, "sda", DEST, "--format", "qcow2", "--reuse-external",
                       "--transient-job", "--bandwidth", "128", "--wait", "--finish", "--timeout", "1800",
                       timeout=1830, check=False)
        if result.returncode:
            raise RuntimeError("LIVE_BLOCKCOPY_FAILED")
        source_xml()
        if virsh("domstate", SOURCE).stdout.strip() != "running":
            raise RuntimeError("SOURCE_NOT_RUNNING_AFTER_COPY")
        copied = Path(DEST).stat()
        if stat.S_IMODE(copied.st_mode) != 0o600:
            raise RuntimeError("CLONE_VOLUME_NOT_PRIVATE")
        control.update(state="COPY_COMPLETE_SOURCE_UNCHANGED", copied_at_epoch=time.time(),
                       destination_mode="0600", destination_allocated_bytes=copied.st_blocks * 512,
                       source_still_running=True, source_disk_unchanged=True)
        write_state(control)
        emit(control)
    except BaseException:
        # Only abort our mirror, and never pivot. Preserve the source and record
        # the incomplete private destination so cleanup is reviewable.
        live = ET.fromstring(virsh("dumpxml", SOURCE, check=False).stdout or "<domain/>")
        mirror = live.find("./devices/disk/mirror")
        mirror_source = mirror.find("source") if mirror is not None else None
        ours = mirror is not None and (mirror.get("file") == DEST or (mirror_source is not None and mirror_source.get("file") == DEST))
        if ours:
            virsh("blockjob", SOURCE, "sda", "--abort", check=False)
        control.update(state="COPY_FAILED_RECONCILE_PRIVATE_DESTINATION", failed_at_epoch=time.time())
        write_state(control)
        raise


def inspect():
    control = state()
    live = ET.fromstring(virsh("dumpxml", SOURCE).stdout)
    mirror = live.find("./devices/disk/mirror")
    emit({"state": control["state"], "clone_name": CLONE, "mirror_present": mirror is not None,
          "blockjob": virsh("blockjob", SOURCE, "sda", "--info", check=False).stdout.strip(),
          "source_state": virsh("domstate", SOURCE).stdout.strip(),
          "source_uuid_preserved": live.findtext("uuid") == SOURCE_UUID,
          "source_disk_preserved": live.find("./devices/disk/source").get("file") == SOURCE_DISK})


def defineclone():
    control = state()
    if control["state"] != "COPY_COMPLETE_SOURCE_UNCHANGED":
        raise RuntimeError("CLONE_COPY_NOT_COMPLETE")
    source_xml()
    root = ET.fromstring((BASE / "source-inactive.xml").read_bytes())
    root.find("name").text = CLONE
    root.find("uuid").text = control["clone_uuid"]
    for tag in ("memory", "currentMemory"):
        element = root.find(tag)
        if element is not None:
            element.text = "8388608"
            element.set("unit", "KiB")
    root.find("vcpu").text = "4"
    for element in list(root.findall("seclabel")) + list(root.findall("metadata")) + list(root.findall("cputune")) + list(root.findall("vcpus")) + list(root.findall("numatune")):
        root.remove(element)
    cpu = root.find("cpu")
    if cpu is not None:
        for topology in list(cpu.findall("topology")) + list(cpu.findall("numa")):
            cpu.remove(topology)
    nvram = root.find("./os/nvram")
    if nvram is not None:
        # libvirtd copies the original vars through its authorized API; the
        # clone has a separate private destination and new TPM state/UUID.
        nvram.set("template", nvram.text)
        nvram.text = "/var/lib/libvirt/qemu/nvram/" + CLONE + "_VARS.fd"
        os_element=root.find("os")
        os_element.attrib.pop("firmware",None)
        for auto_features in list(os_element.findall("firmware")):
            os_element.remove(auto_features)
    devices = root.find("devices")
    for interface in list(devices.findall("interface")):
        devices.remove(interface)
    for disk in list(devices.findall("disk")):
        if disk.get("device") == "disk":
            disk.find("source").set("file", DEST)
        else:
            devices.remove(disk)
    for channel in devices.findall("channel"):
        target = channel.find("target")
        if target is not None:
            target.attrib.pop("state", None)
            if target.get("name") == "org.qemu.guest_agent.0":
                for source in list(channel.findall("source")):
                    channel.remove(source)
    for element in devices.findall("graphics"):
        element.set("autoport", "yes")
        if "port" in element.attrib:
            element.set("port", "-1")
        if "tlsPort" in element.attrib:
            element.set("tlsPort", "-1")
    if root.findall("./devices/interface"):
        raise RuntimeError("CLONE_NETWORK_NOT_ABSENT")
    xmlfile = BASE / "clone-offline.xml"
    xmlfile.write_bytes(ET.tostring(root, encoding="utf-8"))
    os.chmod(xmlfile, 0o600)
    virsh("define", str(xmlfile))
    reread = ET.fromstring(virsh("dumpxml", CLONE, "--inactive").stdout)
    if reread.findtext("uuid") != control["clone_uuid"] or reread.findall("./devices/interface"):
        raise RuntimeError("DEFINED_CLONE_IDENTITY_OR_NETWORK_MISMATCH")
    control.update(state="CLONE_DEFINED_OFFLINE", clone_has_network_interfaces=False,
                   clone_memory_mib=8192, clone_vcpus=4)
    write_state(control)
    emit(control)


def bootclone():
    control = state()
    if control["state"] != "CLONE_DEFINED_OFFLINE":
        raise RuntimeError("CLONE_NOT_DEFINED_OFFLINE")
    xml = ET.fromstring(virsh("dumpxml", CLONE, "--inactive").stdout)
    if xml.findtext("uuid") != control["clone_uuid"] or xml.findall("./devices/interface"):
        raise RuntimeError("CLONE_BOOT_GUARD_FAILED")
    virsh("start", CLONE)
    control.update(state="CLONE_BOOTED_WITHOUT_NETWORK", booted_at_epoch=time.time())
    write_state(control)
    emit(control)


def cleanupclone():
    control = state()
    source_xml()
    found = virsh("dominfo", CLONE, check=False).returncode == 0
    if found:
        xml = ET.fromstring(virsh("dumpxml", CLONE).stdout)
        if xml.findtext("uuid") != control["clone_uuid"] or CLONE == SOURCE:
            raise RuntimeError("CLEANUP_CLONE_UUID_MISMATCH")
        if virsh("domstate", CLONE).stdout.strip() == "running":
            virsh("shutdown", CLONE, "--mode", "agent", check=False)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and virsh("domstate", CLONE).stdout.strip() == "running":
                time.sleep(1)
            if virsh("domstate", CLONE).stdout.strip() == "running":
                virsh("destroy", CLONE)
        virsh("undefine", CLONE, "--nvram", "--tpm")
    volume = virsh("vol-dumpxml", VOLUME, "--pool", POOL, check=False)
    if volume.returncode == 0:
        if ET.fromstring(volume.stdout).findtext("./target/path") != DEST:
            raise RuntimeError("CLEANUP_VOLUME_PATH_MISMATCH")
        virsh("vol-delete", VOLUME, "--pool", POOL)
    source_xml()
    control.update(state="CLEANUP_COMPLETE_SOURCE_UNCHANGED", cleaned_at_epoch=time.time(),
                   clone_domain_removed=True, clone_volume_removed=True, source_still_running=virsh("domstate", SOURCE).stdout.strip() == "running")
    write_state(control)
    emit(control)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["startcopy", "inspect", "defineclone", "bootclone", "cleanupclone"])
    args = parser.parse_args()
    try:
        globals()[args.action]()
    except Exception as error:
        emit({"state": "HOLD", "reason": str(error) if str(error).replace("_", "").isalnum() else type(error).__name__,
              "source_stop_requested": False, "source_pivot_requested": False})
        sys.exit(1)


if __name__ == "__main__":
    main()
