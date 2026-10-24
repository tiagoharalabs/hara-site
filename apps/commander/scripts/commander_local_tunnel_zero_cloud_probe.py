#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, pathlib, re, shutil, subprocess, tempfile

ROOT=pathlib.Path(__file__).resolve().parents[3]
AGENT=ROOT/"apps/commander/public/agent/linux.py"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--execute",action="store_true")
    ap.add_argument("--seconds",type=int,default=4)
    args=ap.parse_args()
    if not AGENT.is_file():
        raise SystemExit("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_AGENT=MISSING")
    if not shutil.which("strace"):
        raise SystemExit("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_STRACE=MISSING")
    print("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_AGENT=PASS")
    print("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_STRACE=PASS")
    if not args.execute:
        print("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_MUTATION=FALSE")
        print("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_READY=PASS")
        return 0
    seconds=max(2,min(15,args.seconds))
    with tempfile.TemporaryDirectory(prefix="hara-local-tunnel-zero-cloud-") as td:
        root=pathlib.Path(td)
        config=root/"config/hara-commander"
        data=root/"data"
        config.mkdir(parents=True); data.mkdir()
        (config/"device.env").write_text(
            "HARA_COMMANDER_URL=https://commander.haralabs.com.br\n"
            "HARA_DEVICE_ID=HARA-DEVICE-ZERO-CLOUD-PROBE\n"
            "HARA_DEVICE_TOKEN=LOCAL_PROBE_TOKEN_NOT_REAL\n"
            "HARA_DEVICE_ARCH=x86_64\n"
            "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n"
            "HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL\n",
            encoding="utf-8",
        )
        os.chmod(config/"device.env",0o600)
        trace=root/"trace.log"
        env=os.environ.copy()
        env.update({
            "XDG_CONFIG_HOME":str(root/"config"),
            "XDG_DATA_HOME":str(data),
            "HARA_COMMANDER_LOCAL_PORT":"39246",
        })
        proc=subprocess.run(
            ["timeout",str(seconds),"strace","-f","-e","trace=connect","-s","180","-o",str(trace),"python3",str(AGENT)],
            env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,
        )
        if proc.returncode not in (0,124):
            raise SystemExit(f"COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_PROCESS=FAIL:{proc.returncode}")
        raw=trace.read_text(encoding="utf-8",errors="replace") if trace.exists() else ""
        ip=[line for line in raw.splitlines() if re.search(r"connect\([^,]+, \{sa_family=AF_INET6?",line)]
        if ip:
            print("COMMANDER_LOCAL_TUNNEL_ZERO_OUTBOUND_IP_CONNECT=FAIL")
            return 1
        event_file=data/"hara-commander/console-events.jsonl"
        events=event_file.read_text(encoding="utf-8",errors="replace") if event_file.exists() else ""
        if '"event":"AGENT_LOCAL_TUNNEL"' not in events or '"cloud_polling=disabled"' not in events:
            print("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_EVENT=FAIL")
            return 1
        print("COMMANDER_LOCAL_TUNNEL_ZERO_OUTBOUND_IP_CONNECT=PASS")
        print("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD_EVENT=PASS")
        print("COMMANDER_LOCAL_TUNNEL_ZERO_CLOUD=PASS")
        return 0

if __name__=="__main__":
    raise SystemExit(main())
