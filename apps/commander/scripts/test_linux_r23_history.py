#!/usr/bin/env python3
"""R23 synthetic QA: Linux history 30 days and privileged clear contract."""
from __future__ import annotations
import contextlib,datetime,importlib.util,io,json,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]/"candidate/linux_agent_history_r23.py"
spec=importlib.util.spec_from_file_location("hara_commander_linux_history_r23",SRC)
agent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)
FIXED_NOW=datetime.datetime(2026,10,21,19,30,tzinfo=datetime.timezone.utc)
def stamp(delta):
    return (FIXED_NOW+datetime.timedelta(days=delta)).isoformat()

class HistoryPolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="hara-r23-history-qa-")
        self.root=Path(self.tmp.name)
        self.restore={}
        for var,value in {
            "DATA_DIR":self.root,"OPERATIONS_DB_FILE":self.root/"operations.sqlite3",
            "CONSOLE_EVENTS_FILE":self.root/"console-events.jsonl",
            "SESSION_FILE":self.root/"operator-session.json",
            "RECEIPT_DIR":self.root/"receipts",
            "CONFIG_FILE":self.root/"device.env",
        }.items():
            self.restore[var]=getattr(agent,var)
            setattr(agent,var,value)
        with agent._ops_connect() as db:
            db.execute("SELECT COUNT(*) FROM activity_events")
        self.addCleanup(self.cleanup)
    def cleanup(self):
        for k,v in self.restore.items():setattr(agent,k,v)
        self.tmp.cleanup()
    def insert(self,day,tool,event="TOOL_COMPLETED",summary="NEVER_PRINT_COMMAND_ARGUMENTS"):
        with agent._ops_connect() as db:
            cur=db.execute(
                "INSERT INTO activity_events(at_utc,event,state,tool_id,function_id,request_id,action_summary)"
                "VALUES (?,?,?,?,?,?,?)",
                (stamp(day),event,"PASS",tool,"filesystem.read",str(day),summary))
        return cur.lastrowid

    def test_last_30_days_and_only_commands(self):
        self.insert(-31,"hara.files.read")
        recent=self.insert(-29,"hara.files.read")
        other=self.insert(-1,None,"DEVICE_HEARTBEAT")
        latest=self.insert(0,"hara.ping")
        rows=agent.query_command_history(50,now_utc=FIXED_NOW)
        self.assertEqual([x["event_id"] for x in rows["items"]],[recent,latest])
        self.assertNotIn("action_summary",rows["items"][0])
        self.assertNotIn(other,[x["event_id"] for x in rows["items"]])

    def test_cursor_and_bounds(self):
        for d in [-5,-4,-3,-2,-1]:
            self.insert(d,"hara.files.read")
        a=agent.query_command_history(2,now_utc=FIXED_NOW)
        self.assertEqual(len(a["items"]),2)
        self.assertIsNotNone(a["next_before_id"])
        b=agent.query_command_history(2,before_id=a["next_before_id"],now_utc=FIXED_NOW)
        self.assertEqual(len(b["items"]),2)
        self.assertTrue(all(x["event_id"]<a["next_before_id"] for x in b["items"]))
        for limit in (0,201):
            with self.assertRaisesRegex(ValueError,"HISTORY_LIMIT_INVALID"):
                agent.query_command_history(limit,now_utc=FIXED_NOW)
        with self.assertRaisesRegex(ValueError,"HISTORY_CURSOR_INVALID"):
            agent.query_command_history(1,before_id=-1,now_utc=FIXED_NOW)

    def test_no_private_command_leak(self):
        self.insert(0,"hara.process.run",summary="PRIVATE_PASSWORD_NEVER_PRINT")
        text=io.StringIO()
        with contextlib.redirect_stdout(text):
            agent.show_command_history(50,now_utc=FIXED_NOW)
        self.assertIn("HARA_COMMANDER_HISTORY_WINDOW_DAYS=30",text.getvalue())
        self.assertNotIn("PRIVATE_PASSWORD_NEVER_PRINT",text.getvalue())

    def test_clear_preserves_receipts_and_other_db(self):
        (self.root/"receipts").mkdir(exist_ok=True)
        proof=self.root/"receipts/original-audit-receipt.json"
        proof.write_text('{"receipt":"preserve"}',encoding="utf-8")
        before=self.insert(0,"hara.files.write")
        agent.append_console_event("TOOL_COMPLETED",{"tool_id":"hara.ping"})
        result=agent.clear_local_history_data()
        self.assertGreaterEqual(result["cleared_event_rows"],2)
        self.assertEqual(proof.read_text(), '{"receipt":"preserve"}')
        marker=json.loads(agent.CONSOLE_EVENTS_FILE.read_text().strip())
        self.assertEqual(marker["event"],"HISTORY_CLEARED")
        self.assertEqual(stat.S_IMODE(agent.CONSOLE_EVENTS_FILE.stat().st_mode),0o600)
        self.assertEqual(agent.query_command_history(50,now_utc=FIXED_NOW)["items"],[])
        with agent._ops_connect() as db:
            self.assertIsNotNone(db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='completion_outbox'").fetchone())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM activity_events").fetchone()[0],1)
        receipts=list(agent.RECEIPT_DIR.glob("history-clear-*.json"))
        self.assertEqual(len(receipts),1)
        self.assertTrue(json.loads(receipts[0].read_text())["receipts_deleted"] is False)

    def test_clearing_denied_for_active_operator(self):
        self.insert(0,"hara.ping")
        agent.SESSION_FILE.write_text(json.dumps({
            "schema":"hara.commander-operator-session.v1",
            "owner_pid":os.getpid(),
            "owner_start_marker":agent._pid_start_marker(os.getpid()),
            "started_at_epoch":int(datetime.datetime.now().timestamp()),
            "started_at_utc":agent.utcnow(),
        }))
        with self.assertRaisesRegex(RuntimeError,"HISTORY_CLEAR_ACTIVE_SESSION_DENIED"):
            agent.clear_local_history_data()
        self.assertEqual(agent.query_command_history(2,now_utc=FIXED_NOW)["items"][0]["tool_id"],"hara.ping")

    def test_admin_only_no_unattended(self):
        with patch.object(agent.os,"geteuid",return_value=1000):
            with self.assertRaisesRegex(RuntimeError,"HISTORY_CLEAR_SUPERUSER_REQUIRED"):
                agent.history_clear_admin()
        with patch.object(agent.os,"geteuid",return_value=0),patch.object(agent.sys.stdin,"isatty",return_value=False):
            with self.assertRaisesRegex(RuntimeError,"HISTORY_CLEAR_LOCAL_TTY_REQUIRED"):
                agent.history_clear_admin()

    def test_existing_console_starts_at_eof(self):
        content=SRC.read_text()
        function=content[content.index("def start_operator_console():"):content.index("def session_status():")]
        self.assertIn("position = CONSOLE_EVENTS_FILE.stat().st_size",function)
        self.assertIn("handle.seek(position)",function)
        self.assertNotIn("position = 0",function)

if __name__=="__main__":
    unittest.main()
