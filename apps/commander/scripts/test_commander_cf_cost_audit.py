#!/usr/bin/env python3
"""Offline arithmetic and reporting guards; no Cloudflare requests."""
import unittest
from decimal import Decimal
import commander_cf_cost_audit as audit

def measured(**values):return {'state':'MEASURED','rows':[{'sum':values}]}
class CostAuditTests(unittest.TestCase):
 def test_cpu_microseconds_to_milliseconds(self):
  r=audit.calculate({'worker':measured(requests=1000000,cpuTimeUs=1000000)})
  self.assertAlmostEqual(r['items']['worker_cpu']['units'],1000)
  self.assertAlmostEqual(r['items']['worker_cpu']['usd'],0.00002)
  self.assertAlmostEqual(r['items']['worker_requests']['usd'],0.3)
 def test_d1_rows_not_queries(self):
  r=audit.calculate({'d1':measured(rowsRead=1000000,rowsWritten=1000000,readQueries=1,writeQueries=1)})
  self.assertEqual(r['items']['d1_reads']['usd'],0.001)
  self.assertEqual(r['items']['d1_writes']['usd'],1)
 def test_do_duration_already_gb_seconds(self):
  r=audit.calculate({'do_periodic':measured(duration=1000000)})
  self.assertEqual(r['items']['do_duration']['usd'],12.5)
 def test_unavailable_is_unknown_not_zero(self):
  r=audit.calculate({})
  self.assertIsNone(r['items']['worker_cpu']['usd'])
  self.assertIsNone(r['variable_list_rate_upper_estimate_usd'])
 def test_empty_dataset_is_unknown(self):
  self.assertIsNone(audit.total({'worker':{'state':'MEASURED','rows':[]}},'worker','requests'))
 def test_observed_zero_remains_zero(self):
  r=audit.calculate({'worker':measured(requests=0,cpuTimeUs=0)})
  self.assertEqual(r['items']['worker_cpu']['usd'],0)
 def test_no_invoice_or_shared_allowance_claim(self):
  r=audit.calculate({'worker':measured(requests=1,cpuTimeUs=1)})
  self.assertFalse(r['invoice_verified']);self.assertFalse(r['monthly_allowances_applied']);self.assertIsNone(r['billed_total_usd'])
 def test_websocket_bound_not_all_invocations_divided_by_twenty(self):
  r=audit.calculate({'do_invocations':measured(requests=100),'do_periodic':measured(inboundWebsocketMsgCount=20)})
  self.assertAlmostEqual(r['do_requests_conservative_list_rate_upper_bound_usd'],120*0.00000015)
 def test_invalid_metrics_rejected(self):
  for value in [-1,float('nan'),float('inf')]:
   with self.assertRaises(ValueError):audit.total({'worker':measured(requests=value)},'worker','requests')
 def test_graphql_scope_and_half_open_time_window(self):
  q=audit.make_queries('2026-10-10T14:30:00Z','2026-10-11T14:30:00Z','test-db',[{'id':'test-ns'}])
  for text in q.values():
   self.assertIn('datetime_geq:',text);self.assertIn('datetime_lt:',text);self.assertNotIn('mutation',text)
  self.assertIn('scriptName:"hara-commander"',q['worker'])
  self.assertIn('databaseId:"test-db"',q['d1'])
  self.assertIn('namespaceId_in:["test-ns"]',q['do_periodic'])
 def test_subrequests_are_not_extra_worker_billable_requests(self):
  a=audit.calculate({'worker':measured(requests=1,cpuTimeUs=0,subrequests=1000000)})
  self.assertEqual(a['items']['worker_requests']['usd'],0.0000003)
 def test_no_sampling_double_multiplication(self):
  raw={'worker':{'state':'MEASURED','sample_interval_max':10,'rows':[{'sum':{'requests':100,'cpuTimeUs':1000},'avg':{'sampleInterval':10}}]}}
  self.assertEqual(audit.calculate(raw)['items']['worker_requests']['units'],100)
if __name__=='__main__':unittest.main(verbosity=2)
