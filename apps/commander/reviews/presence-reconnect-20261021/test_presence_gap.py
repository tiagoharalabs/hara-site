#!/usr/bin/env python3
"""Read-only negative test for HARA Commander Event V2 presence/reconnect gap.

Use --expect-red to show a verified counterexample (exit 0 on detected bug).
Without it, this is a safety invariant asserting no offline gap and should
FAIL on current sources; Codex integrates its corrected runtime logic separately.
No sockets, credentials, cloud writes, or fleet mutations.
"""
import argparse
import json
import pathlib
import re
import sys

SITE = pathlib.Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/apps/commander/src")
AGENT = pathlib.Path("/home/sartorius/.local/share/hara-commander/releases/0.3.54-event-v2-fleet-20261013-1639-r2/experimental")

def check(text, pattern, label):
    if not re.search(pattern, text):
        raise RuntimeError(f"SOURCE_PREIMAGE_DRIFT:{label}")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--expect-red", action="store_true")
    args=p.parse_args()
    worker=(SITE/"worker.js").read_text()
    channel=(SITE/"device-channel.mjs").read_text()
    loop=(AGENT/"event_v2_agent_loop.py").read_text()
    transport=(AGENT/"event_v2_websocket.py").read_text()
    check(worker,r'\?\s*7\s*\*\s*60\s*\*\s*60\s*\*\s*1000',"online_ttl_7h")
    check(channel,r'CONNECT_REFRESH_MS\s*=\s*5\s*\*\s*60\s*\*\s*60\s*\*\s*1000',"connect_refresh_5h")
    check(loop,r'last_liveness\s*=\s*connected_at',"reconnect_resets_liveness")
    check(loop,r'LIVENESS_JITTER_SECONDS\s*=\s*15\s*\*\s*60',"jitter_15m")
    check(transport,r'DURABLE_LIVENESS_SECONDS\s*=\s*6\s*\*\s*60\s*\*\s*60',"liveness_6h")
    online_window=7*3600
    reconnect_age=5*3600-1
    max_next_liveness_age=reconnect_age+6*3600+15*60
    gap=max_next_liveness_age-online_window
    state="RED_GAP_REPRODUCED" if gap>0 else "PASS_SAFE_PRESENCE_WINDOW"
    print(json.dumps(dict(schema="hara.commander-presence-gap-negative.v1",state=state,online_window_seconds=online_window,age_at_reconnect_seconds=reconnect_age,next_liveness_age_seconds=max_next_liveness_age,offline_gap_seconds=max(gap,0),source_scoped=True,prod_parity_unproven=True),sort_keys=True))
    if args.expect_red:
        return 0 if gap>0 else 2
    return 0 if gap<=0 else 1

if __name__=="__main__":
    sys.exit(main())
