#!/usr/bin/env python3
"""Offline real-PTY check for pager isolation and managed session review."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

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

        agent.append_console_event=lambda *args,**kwargs: (_ for _ in ()).throw(OSError("SYNTHETIC_EVENT_STORE_FAULT"))
        first=agent.process_start("sleep 10",temporary,0)
        second=agent.process_start("sleep 10",temporary,0)
        assert second["capacity_warning_event_error_code"]=="SYNTHETIC_EVENT_STORE_FAULT"
        status=agent.process_sessions()
        assert next(row for row in status["sessions"] if row["session_id"]==second["session_id"])["capacity_warning_event_error_code"]=="SYNTHETIC_EVENT_STORE_FAULT"
        agent.process_kill(first["session_id"],True)
        agent.process_kill(second["session_id"],True)
        print("COMMANDER_CAPACITY_ALARM_STORE_FAILURE_VISIBLE=PASS")

        # Hold the first admission inside a synthetic fork. The second caller
        # must be rejected before it can fork, even though no session has yet
        # been inserted. No child or real command is started by this fixture.
        agent.MAX_PROCESS_ACTIVE_SESSIONS=1
        baseline=set(agent.PROCESS_SESSIONS)
        entered=threading.Event(); release=threading.Event(); fork_calls=[]
        def fake_fork():
            fork_calls.append(1)
            entered.set()
            assert release.wait(2),"SYNTHETIC_FORK_WAIT_TIMEOUT"
            return (100000+len(fork_calls),-1)
        def attempt():
            try: return ("OK",agent.process_start("printf synthetic",temporary,0))
            except Exception as exc: return ("ERROR",str(exc))
        try:
            with patch.object(agent.pty,"fork",side_effect=fake_fork), \
                 patch.object(agent.os,"set_blocking",return_value=None), \
                 patch.object(agent,"_process_update_state",return_value=None), \
                 patch.object(agent,"_collect_process_output",return_value=None), \
                 patch.object(agent,"_process_output_payload",side_effect=lambda session,**kw:{"session_id":session["session_id"]}):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first_call=pool.submit(attempt)
                    assert entered.wait(2),"FIRST_SYNTHETIC_FORK_NOT_REACHED"
                    second_call=pool.submit(attempt)
                    time.sleep(0.05)
                    release.set()
                    outcomes=[first_call.result(timeout=2),second_call.result(timeout=2)]
            assert [kind for kind,_ in outcomes].count("OK")==1,outcomes
            assert [value for kind,value in outcomes if kind=="ERROR"]==["PROCESS_SESSION_CAPACITY_EXCEEDED"],outcomes
            assert len(fork_calls)==1,fork_calls
            assert agent.PROCESS_STARTING==0
            print("COMMANDER_CONCURRENT_PROCESS_ADMISSION_ATOMIC=PASS")
        finally:
            release.set()
            for sid in set(agent.PROCESS_SESSIONS)-baseline:
                agent.PROCESS_SESSIONS.pop(sid,None)

        with patch.object(agent.pty,"fork",side_effect=OSError("SYNTHETIC_FORK_FAULT")):
            try: agent.process_start("printf synthetic",temporary,0)
            except OSError as exc: assert str(exc)=="SYNTHETIC_FORK_FAULT"
            else: raise AssertionError("FORK_FAILURE_NOT_PROPAGATED")
        assert agent.PROCESS_STARTING==0

        class FailedCollector:
            def __init__(self,*args,**kwargs): pass
            def start(self): raise RuntimeError("SYNTHETIC_COLLECTOR_FAULT")
        aborted=[]
        with patch.object(agent.pty,"fork",return_value=(100999,-1)), \
             patch.object(agent.os,"set_blocking",return_value=None), \
             patch.object(agent.threading,"Thread",FailedCollector), \
             patch.object(agent,"_abort_process_start",side_effect=lambda *args:aborted.append(args)):
            try: agent.process_start("printf synthetic",temporary,0)
            except RuntimeError as exc: assert str(exc)=="SYNTHETIC_COLLECTOR_FAULT"
            else: raise AssertionError("COLLECTOR_FAILURE_NOT_PROPAGATED")
        assert len(aborted)==1 and aborted[0][0]==100999
        assert agent.PROCESS_STARTING==0 and set(agent.PROCESS_SESSIONS)==baseline
        print("COMMANDER_PROCESS_FORK_AND_COLLECTOR_FAILURE_RELEASE_CAPACITY=PASS")

        real_abort=agent._abort_process_start
        aborted_pids=[]
        def tracking_abort(*args):
            aborted_pids.append(args[0])
            return real_abort(*args)
        with patch.object(agent,"_process_output_payload",side_effect=RuntimeError("SYNTHETIC_INITIAL_READ_FAULT")), \
             patch.object(agent,"_abort_process_start",side_effect=tracking_abort):
            try: agent.process_start("sleep 10",temporary,0)
            except RuntimeError as exc: assert str(exc)=="SYNTHETIC_INITIAL_READ_FAULT"
            else: raise AssertionError("INITIAL_READ_FAILURE_NOT_PROPAGATED")
        assert len(aborted_pids)==1 and agent.PROCESS_STARTING==0
        assert set(agent.PROCESS_SESSIONS)==baseline
        try: os.kill(aborted_pids[0],0)
        except ProcessLookupError: pass
        else: raise AssertionError("ABORTED_PROCESS_STILL_RUNNING")
        print("COMMANDER_FAILED_START_REAL_CHILD_TERMINATED=PASS")

        agent.MAX_PROCESS_ACTIVE_SESSIONS=16
        fork_calls=[]
        def fake_fleet_fork():
            fork_calls.append(1)
            time.sleep(0.03)
            return (200000+len(fork_calls),-1)
        with patch.object(agent.pty,"fork",side_effect=fake_fleet_fork), \
             patch.object(agent.os,"set_blocking",return_value=None), \
             patch.object(agent,"_process_update_state",return_value=None), \
             patch.object(agent,"_collect_process_output",return_value=None), \
             patch.object(agent,"_process_output_payload",side_effect=lambda session,**kw:{"session_id":session["session_id"]}):
            with ThreadPoolExecutor(max_workers=20) as pool:
                outcomes=list(pool.map(lambda _:attempt(),range(20)))
        assert [kind for kind,_ in outcomes].count("OK")==16,outcomes
        assert [kind for kind,_ in outcomes].count("ERROR")==4,outcomes
        assert len(fork_calls)==16 and agent.PROCESS_STARTING==0
        for sid in set(agent.PROCESS_SESSIONS)-baseline:
            agent.PROCESS_SESSIONS.pop(sid,None)
        print("COMMANDER_CONCURRENT_PROCESS_FLEET_LIMIT_16=PASS")
    finally:
        if "agent" in locals(): agent.cleanup_process_sessions()
        for key,value in prior.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
