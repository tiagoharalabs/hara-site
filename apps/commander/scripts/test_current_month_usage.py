#!/usr/bin/env python3
"""Commander month usage regression: UTC boundaries, scoping, no total leak."""
import pathlib,re,sqlite3,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
class CurrentMonthUsageTest(unittest.TestCase):
 def setUp(self):
  self.source=(APP/"src/worker.js").read_text()
  self.app=(APP/"public/app.js").read_text()
  self.html=(APP/"public/index.html").read_text()
  i=self.source.index("async function productTransactionHistory")
  j=self.source.index("async function dashboardForSubject",i)
  self.function=self.source[i:j]
  self.sql=self.function.split("WITH relay AS (",1)[1].split(chr(96),1)[0]
  self.sql="WITH relay AS ("+self.sql
 def test_sql_boundary_and_scope(self):
  c=sqlite3.connect(":memory:")
  c.executescript("""
CREATE TABLE commander_device_calls(call_id TEXT PRIMARY KEY,tenant_id TEXT,subject_id TEXT,created_at_utc TEXT);
CREATE TABLE commander_device_usage_daily(device_id TEXT,tenant_id TEXT,subject_id TEXT,day_key TEXT,units INT,PRIMARY KEY(device_id,day_key));
CREATE TABLE commander_device_usage_totals(device_id TEXT PRIMARY KEY,tenant_id TEXT,subject_id TEXT,lifetime_units INT);
""")
  c.executemany("INSERT INTO commander_device_calls VALUES(?,?,?,?)",[
   ("sept","t","u","2026-09-30T23:59:59.999Z"),
   ("oct","t","u","2026-10-01T00:00:00.000Z"),
   ("today","t","u","2026-10-21T12:00:00.000Z"),
   ("nov","t","u","2026-11-01T00:00:00.000Z"),
   ("other","t","v","2026-10-21T12:00:00.000Z")])
  c.executemany("INSERT INTO commander_device_usage_daily VALUES(?,?,?,?,?)",[
   ("d","t","u","2026-09-30",15),("d","t","u","2026-10-01",4),
   ("d","t","u","2026-10-21",7),("d","t","u","2026-11-01",20),
   ("x","t","v","2026-10-21",500)])
  c.execute("INSERT INTO commander_device_usage_totals VALUES(?,?,?,?)",("d","t","u",98))
  params=["t","u","2026-10-01T00:00:00.000Z","2026-11-01T00:00:00.000Z",
   "t","u","2026-10-01","2026-11-01","t","u","t","u"]
  prev=c.execute(self.sql,params).fetchone()
  self.assertEqual(prev,(13,102))
  c.execute("INSERT INTO commander_device_calls VALUES(?,?,?,?)",("next","t","u","2026-10-21T15:00:00.000Z"))
  self.assertEqual(c.execute(self.sql,params).fetchone()[0],14)
  c.execute("INSERT OR IGNORE INTO commander_device_calls VALUES(?,?,?,?)",("next","t","u","2026-10-21T15:00:00.000Z"))
  self.assertEqual(c.execute(self.sql,params).fetchone()[0],14)
 def test_explicit_month_window_not_rolling(self):
  self.assertIn("CURRENT_CALENDAR_MONTH_UTC",self.function)
  self.assertIn("Date.UTC(now.getUTCFullYear(), now.getUTCMonth()",self.source)
  self.assertNotIn("calls_7d",self.function)
  self.assertIn("day_key < ?",self.sql)
 def test_private_history_policy(self):
  self.assertIn('["OWNER", "ADMIN"]',self.source)
  self.assertIn('FOUNDER_INTERNAL',self.source)
  self.assertIn("if (includeLifetime) result.internal_lifetime_calls",self.function)
  self.assertIn('history.internal_lifetime_calls',self.app)
  self.assertIn('id="usageInternalHistory" hidden',self.html)
 def test_public_no_rolling_label(self):
  self.assertNotIn("Execuções governadas (7 dias)",self.html)
  self.assertNotIn("history.calls_7d",self.app)
  self.assertIn("hist",self.app.lower())
  self.assertIn("Transações no período",self.html)
 def test_billing_dates_are_source_bound(self):
  self.assertIn("billingConnection?.current_period_end_utc",self.source)
  self.assertIn("billing_summary",self.source)
  self.assertIn("Sem vencimento",self.app)
if __name__=="__main__":
 unittest.main(verbosity=2)
