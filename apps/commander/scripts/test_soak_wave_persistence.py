#!/usr/bin/env python3
"""Offline regression: failed waves survive failure with correlation metadata."""
import importlib.util,json,tempfile,time,unittest
from pathlib import Path
SCRIPT=Path(__file__).with_name("commander_full_acceptance_real_dev_soak.py")
spec=importlib.util.spec_from_file_location("soak_wave_persistence_test",SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class WavePersistence(unittest.TestCase):
    def make_runner(self,folder):
        r=m.Runner.__new__(m.Runner);r.ev=Path(folder);r.start=time.monotonic();r.http_calls=0;r.d1_commands=0
        r.audit={"state":"PILOT_RUNNING","probe_waves":[]};return r
    def test_http_failure_persisted_before_raise(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.make_runner(folder);calls=[]
            def health(row,request_id):
                pending=json.loads((r.ev/"status.json").read_text())
                self.assertEqual(pending["probe_waves"][0]["state"],"RUNNING")
                self.assertTrue(all(a["state"]=="PENDING" and a["request_id_known_before_dispatch"] and a["request_id"] for a in pending["probe_waves"][0]["attempts"]))
                calls.append(request_id)
                if row["index"]==1:raise m.probe.ProbeError("INTERNAL_ERROR",http_status=500,cf_ray="0123456789abcdef-GRU",incident_id="12345678-1234-4234-8234-123456789012")
                return {"success":True,"latency_ms":100,"request_id":request_id}
            r.health=health
            rows=[{"index":i,"device_id":"QA-"+str(i)} for i in (1,2)]
            with self.assertRaisesRegex(RuntimeError,"^SOAK_PROBE_ERROR__INTERNAL_ERROR$"):r.wave(rows)
            saved=json.loads((r.ev/"status.json").read_text());wave=saved["probe_waves"][0]
            self.assertEqual(len(calls),2);self.assertEqual(len(set(calls)),2)
            self.assertEqual(saved["failed_wave_sequence"],1);self.assertEqual(wave["state"],"FAIL")
            failed=next(a for a in wave["attempts"] if a["index"]==1)
            self.assertEqual(failed["http_diagnostics"]["http_status"],500)
            self.assertEqual(failed["http_diagnostics"]["incident_id"],"12345678-1234-4234-8234-123456789012")
            self.assertEqual(failed["error_code"],"INTERNAL_ERROR")
            self.assertEqual(wave["summary"]["successful"],1)
            self.assertTrue(all(a.get("completed_at_utc") and a["elapsed_ms"]>=0 for a in wave["attempts"]))
    def test_latency_failure_survives_assertion(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.make_runner(folder);count=[]
            def health(row,request_id):
                count.append(request_id);return {"success":True,"latency_ms":7000,"request_id":request_id}
            r.health=health
            with self.assertRaisesRegex(RuntimeError,"^SOAK_LATENCY_SLO$"):r.wave([{"index":1,"device_id":"QA-1"}])
            saved=json.loads((r.ev/"status.json").read_text())
            self.assertEqual(saved["probe_waves"][0]["state"],"FAIL")
            self.assertEqual(saved["probe_waves"][0]["summary"]["errors"],[])
            self.assertEqual(saved["failed_wave_sequence"],1);self.assertEqual(len(count),1)
    def test_success_is_still_success(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.make_runner(folder)
            r.health=lambda row,request_id:{"success":True,"latency_ms":100,"request_id":request_id}
            summary=r.wave([{"index":1,"device_id":"QA-1"}])
            saved=json.loads((r.ev/"status.json").read_text())
            self.assertEqual(summary["success_fraction"],1)
            self.assertEqual(saved["probe_waves"][0]["state"],"PASS")
            self.assertNotIn("failed_wave_sequence",saved)
if __name__=="__main__":unittest.main()
