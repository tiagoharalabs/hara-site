#!/usr/bin/env python3
"""Offline HTTP failure correlation must retain only whitelisted metadata."""
from pathlib import Path
import importlib.util,io,json
from email.message import Message
from urllib.error import HTTPError
p=Path(__file__).with_name("commander_event_v2_transient_live_probe.py")
spec=importlib.util.spec_from_file_location("probe_metadata_test",p)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
checks=0
def equal(a,b):
 global checks
 assert a==b,(a,b);checks+=1
secret="UNIT_SECRET_COOKIE_HEADER_PAYLOAD"
headers=Message();headers["CF-Ray"]="0123456789abcdef-GRU";headers["x-hara-dev-incident-id"]="12345678-1234-1234-1234-123456789abc";headers["set-cookie"]=secret
def fail(req,timeout):
 raise HTTPError(req.full_url,500,"owned-unit-fault",headers,io.BytesIO(json.dumps({"code":"INTERNAL_ERROR","private":secret}).encode()))
probe.urlopen=fail
try:probe.post_json("/api/internal/device/transient-call",secret,{"payload":secret})
except probe.ProbeError as error:
 equal(str(error),"INTERNAL_ERROR")
 equal(error.safe_diagnostics,{"http_status":500,"cf_ray":"0123456789abcdef-GRU","incident_id":"12345678-1234-1234-1234-123456789abc"})
 equal(secret in json.dumps(error.safe_diagnostics),False)
else:raise AssertionError("EXPECTED_OFFLINE_HTTP_ERROR")
for value in (secret,"https://private.invalid/"+secret,"\r\n"+secret):
 error=probe.ProbeError("INTERNAL_ERROR",http_status="500",cf_ray=value,incident_id=value)
 equal(error.safe_diagnostics,{})
equal(probe.ProbeError("LEGACY").safe_diagnostics,{})
equal(str(probe.ProbeError("LEGACY")),"LEGACY")
# Each stage wraps the same HTTP error once, with no retry or metadata loss.
original_require = probe.require_transient_common
original_call = probe.transient_call
probe.require_transient_common = lambda result: None
for failing_call, stage in ((1,"HEALTH"),(2,"INVOKE_FIRST"),(3,"INVOKE_REPLAY")):
 calls = []
 original_error = probe.ProbeError("INTERNAL_ERROR", http_status=500,
     cf_ray="0123456789abcdef-GRU",
     incident_id="12345678-1234-1234-1234-123456789abc")
 def offline_call(*args):
  calls.append(args[2])
  if len(calls) == failing_call:
   raise original_error
  return {"state":"COMPLETED","device_id":"OWN_UNIT_DEVICE",
          "execution_mode":"EXECUTE_OR_REPLAY","usage":{"state":"COMMITTED"},
          "receipt_sha256":"a"*64}
 probe.transient_call = offline_call
 try: probe.run(secret,"OWN_UNIT_SUBJECT","OWN_UNIT_DEVICE",20)
 except probe.ProbeError as error:
  equal(str(error),"STAGE_"+stage+"__INTERNAL_ERROR")
  equal(error.safe_diagnostics,original_error.safe_diagnostics)
  equal(error.__cause__ is original_error,True)
  equal(len(calls),failing_call)
  equal(secret in json.dumps(error.safe_diagnostics),False)
 else: raise AssertionError("EXPECTED_STAGE_HTTP_ERROR")
probe.require_transient_common = original_require
probe.transient_call = original_call
# Revalidate fields instead of accepting arbitrary metadata on a wrapper.
dirty = probe.ProbeError("INTERNAL_ERROR")
dirty.safe_diagnostics = {"http_status":"500","cf_ray":secret,
                          "incident_id":secret,"set-cookie":secret}
equal(probe.stage_error("STAGE_HEALTH__",dirty).safe_diagnostics,{})
print(json.dumps({"state":"PASS","checks":checks,"scope":"OFFLINE_NO_NETWORK","raw_headers_payloads_exported":False}))
