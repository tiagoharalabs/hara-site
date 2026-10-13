#!/usr/bin/env python3
"""Literal PRAGMA repair proof against own SQLite fixtures; no DEV calls."""
import hashlib,importlib.util,json,sqlite3,unittest
from pathlib import Path
p=Path(__file__).with_name("commander_real_1000_cleanup_repair.py")
spec=importlib.util.spec_from_file_location("repair_under_test",p);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
RUN="cap1k-smoke-vm-20261013-r1"
prefix=hashlib.sha256(RUN.encode()).hexdigest()[:12]
OWN="HARA-CAP1K-T-"+prefix+"-0-own"
SUB="HARA-CAP1K-S-"+prefix+"-0-own"
ROW=dict(tenant_id=OWN,subject_id=SUB,device_id="HARA-DEVICE-own",collision_checked=True)
class Repair(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(":memory:");self.db.row_factory=sqlite3.Row;self.calls=[]
  self.db.executescript("""
CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);
CREATE TABLE users(subject_id TEXT PRIMARY KEY,tenant_id TEXT);
CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT);
CREATE TABLE extra_owned_events(tenant_id TEXT,event TEXT);
CREATE TABLE portal_sessions(subject_id TEXT);
CREATE TABLE metadata(key TEXT);
CREATE TABLE _cf_private(tenant_id TEXT);
""")
  for tenant,subject,device in ((OWN,SUB,"HARA-DEVICE-own"),("CUSTOMER-T","CUSTOMER-S","HARA-DEVICE-customer")):
   self.db.execute("INSERT INTO tenants VALUES(?)",(tenant,))
   self.db.execute("INSERT INTO users VALUES(?,?)",(subject,tenant))
   self.db.execute("INSERT INTO commander_devices VALUES(?,?)",(device,tenant))
   self.db.execute("INSERT INTO extra_owned_events VALUES(?,?)",(tenant,"metadata-only"))
   self.db.execute("INSERT INTO portal_sessions VALUES(?)",(subject,))
  self.db.execute("INSERT INTO _cf_private VALUES(?)",(OWN,));self.db.execute("INSERT INTO metadata VALUES('preserve')")
 def tearDown(self):self.db.close()
 def d1(self,sql):
  if "pragma_table_info(" in sql.lower():raise RuntimeError("D1_UNSUPPORTED_TABLE_VALUED_PRAGMA")
  self.calls.append(sql);out=[]
  for stmt in sql.split(";"):
   if not stmt.strip():continue
   cur=self.db.execute(stmt);out.append({"results":[dict(x) for x in cur.fetchall()]})
  return out
 def test_literal_batches_preserve_every_schema_result(self):
  cols=r.schema(self.d1)
  self.assertIn("tenant_id",cols["tenants"]);self.assertIn("subject_id",cols["portal_sessions"])
  self.assertNotIn("_cf_private",cols);self.assertTrue(any("PRAGMA table_info(" in x for x in self.calls))
  self.assertFalse(any("pragma_table_info(" in x.lower() for x in self.calls))
 def test_old_query_rejected_before_mutation(self):
  with self.assertRaisesRegex(RuntimeError,"D1_UNSUPPORTED_TABLE_VALUED_PRAGMA"):
   self.d1("SELECT t.name,p.name FROM sqlite_master t JOIN pragma_table_info(t.name) p;")
  self.assertEqual(self.db.execute("SELECT count(*) FROM tenants").fetchone()[0],2)
 def test_exact_deletes_and_separate_counts_preserve_other_customer(self):
  cols=r.schema(self.d1);deletes,counts,tables=r.scoped_sql(cols,[ROW],RUN)
  self.assertNotIn("metadata",tables);self.assertNotIn("_cf_private",tables)
  self.assertFalse(any("UNION" in x for x in counts))
  self.d1("\n".join(deletes));remaining=r.flatten(self.d1("\n".join(counts)))
  self.assertEqual(len(remaining),len(tables));self.assertTrue(all(x["n"]==0 for x in remaining))
  self.assertEqual(self.db.execute("SELECT tenant_id FROM tenants").fetchone()[0],"CUSTOMER-T")
  self.assertEqual(self.db.execute("SELECT subject_id FROM users").fetchone()[0],"CUSTOMER-S")
  self.assertEqual(self.db.execute("SELECT device_id FROM commander_devices").fetchone()[0],"HARA-DEVICE-customer")
  self.assertEqual(self.db.execute("SELECT count(*) FROM _cf_private").fetchone()[0],1)
  self.assertEqual(self.db.execute("SELECT key FROM metadata").fetchone()[0],"preserve")
 def test_unchecked_collision_cannot_be_deleted(self):
  with self.assertRaisesRegex(RuntimeError,"CAPACITY_REPAIR_EXACT_SCOPE"):r.scoped_sql(r.schema(self.d1),[dict(ROW,collision_checked=False)],RUN)
 def test_other_run_cannot_be_deleted(self):
  with self.assertRaisesRegex(RuntimeError,"CAPACITY_REPAIR_EXACT_SCOPE"):r.scoped_sql(r.schema(self.d1),[ROW],"cap1k-different-run-20261013")
 def test_flatten_preserves_all_counts_not_only_last(self):
  self.assertEqual(r.flatten([{"results":[{"n":0}]},{"results":[{"n":1}]}]),[{"n":0},{"n":1}])
 def test_empty_or_malformed_schema_result_rejected(self):
  with self.assertRaisesRegex(RuntimeError,"CAPACITY_REPAIR_D1_RESULTS"):r.flatten([{"results":None}])
 def test_device_id_scope_rejected(self):
  with self.assertRaisesRegex(RuntimeError,"CAPACITY_REPAIR_DEVICE_SCOPE"):r.scoped_sql(r.schema(self.d1),[dict(ROW,device_id="wrong")],RUN)

if __name__=="__main__":
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Repair);result=unittest.TextTestRunner(verbosity=1).run(suite)
 print(json.dumps(dict(state="PASS" if result.wasSuccessful() else "FAIL",checks=result.testsRun,
 failures=len(result.failures),errors=len(result.errors),DEV_calls=0,fixtures_SQLite_only=True)))
 raise SystemExit(0 if result.wasSuccessful() else 1)
