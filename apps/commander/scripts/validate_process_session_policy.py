#!/usr/bin/env python3
"""Offline real-PTY check for pager isolation and managed session review."""
from __future__ import annotations

import argparse
import importlib.util
import os
import tempfile
import time
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--source",type=Path,default=Path(__file__).resolve().parents[1]/"public/agent/linux.py")
source=parser.parse_args().source

with tempfile.TemporaryDirectory(prefix="hara-process-session-policy-") as temporary:
    prior={key:os.environ.get(key) for key in ("HOME","XDG_DATA_HOME","XDG_CONFIG_HOME","PAGER","GIT_PAGER","PSQL_PAGER")}
    try:
        for key,leaf in (("HOME","home"),("XDG_DATA_HOME","data"),("XDG_CONFIG_HOME","config")):
            path=Path(temporary)/leaf
            path.mkdir()
            os.environ[key]=str(path)
        for key in ("PAGER","GIT_PAGER","PSQL_PAGER"):
            os.environ[key]="more"
        spec=importlib.util.spec_from_file_location("hara_process_session_policy",source)
        assert spec and spec.loader
        agent=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent)
        command="printf '%s,%s,%s\\n' \"$PAGER\" \"$GIT_PAGER\" \"$PSQL_PAGER\""
        one=agent.process_run(command,temporary,1500,20)
        assert "cat,cat,cat" in one["text"],one
        assert one["session_retained"] is False
        assert all(os.environ[key]=="more" for key in ("PAGER","GIT_PAGER","PSQL_PAGER"))
        print("COMMANDER_NONINTERACTIVE_PAGERS_DISABLED_IN_CHILD_ONLY=PASS")

        interactive=agent.process_start(command,temporary,500)
        page=agent._process_output_payload(agent._process_get(interactive["session_id"]),0,20,100)
        assert "more,more,more" in page["text"],page
        print("COMMANDER_INTERACTIVE_PROCESS_ENVIRONMENT_PRESERVED=PASS")

        assert not agent._process_capacity_warning(11)
        assert agent._process_capacity_warning(12)
        events=[]
        agent.append_console_event=lambda *args,**kwargs: events.append((args,kwargs))
        agent.MAX_PROCESS_ACTIVE_SESSIONS=2
        first=agent.process_start("sleep 10",temporary,0,
                                  owner_request_id="REQ-ONE",owner_subject_id="SUBJECT-ONE")
        second=agent.process_start("sleep 10",temporary,0,
                                   owner_request_id="REQ-TWO",owner_subject_id="SUBJECT-TWO")
        agent.PROCESS_SESSIONS[first["session_id"]]["last_client_activity_monotonic"]-=agent.PROCESS_IDLE_REVIEW_SECONDS+1
        status=agent.process_sessions()
        entries={row["session_id"]:row for row in status["sessions"]}
        assert status["active_count"]==2 and status["active_capacity"]==2 and status["capacity_warning"]
        assert len(events)==1 and events[0][0][0]=="PROCESS_CAPACITY_WARNING"
        assert entries[first["session_id"]]["owner_request_id"]=="REQ-ONE"
        assert entries[first["session_id"]]["owner_subject_id"]=="SUBJECT-ONE"
        assert entries[first["session_id"]]["owner_review_required"]
        assert entries[first["session_id"]]["blocking_reason"]=="NO_CLIENT_ACTIVITY"
        assert agent.PROCESS_SESSIONS[first["session_id"]]["exit_code"] is None
        assert not entries[second["session_id"]]["owner_review_required"]
        print("COMMANDER_SESSION_OWNER_IDLE_REVIEW_AND_CAPACITY_VISIBLE=PASS")

        try:
            agent.process_start("printf denied",temporary,0)
        except ValueError as exc:
            assert str(exc)=="PROCESS_SESSION_CAPACITY_EXCEEDED"
        else:
            raise AssertionError("ACTIVE_CAPACITY_NOT_ENFORCED")
        assert agent.PROCESS_SESSIONS[first["session_id"]]["exit_code"] is None
        agent.process_kill(first["session_id"],True)
        agent.process_kill(second["session_id"],True)
        assert agent.process_sessions()["active_count"]==0
        print("COMMANDER_IDLE_LONG_JOB_NOT_AUTO_KILLED_MANUAL_RELEASE=PASS")
    finally:
        if "agent" in locals(): agent.cleanup_process_sessions()
        for key,value in prior.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
