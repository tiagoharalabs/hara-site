import importlib.util,json,unittest
from pathlib import Path
p=Path(__file__).with_name("commander_dev_safe_error_tail.py")
s=importlib.util.spec_from_file_location("dev_safe_tail_test",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class SafeTail(unittest.TestCase):
    def incident(self):
        return {"schema":"hara.dev-safe-error-incident.v1","environment":"DEV","incident_id":"12345678-1234-4234-8234-123456789012","route":"TRANSIENT_CALL","exception_class":"TypeError","safe_cause_class":"UNKNOWN","message_sha256":"a"*64,"stack_frames":[{"function":"fetch","line":12,"column":3,"path":"SECRET_PATH"}],"message":"SECRET_MESSAGE","authorization":"SECRET_BEARER","cookie":"SECRET_COOKIE"}
    def test_safe_incident_drops_extra_fields(self):
        result=m.safe_incident(self.incident());self.assertIsNotNone(result)
        self.assertNotIn("SECRET_",json.dumps(result));self.assertEqual(result["stack_frames"],[{"function":"fetch","line":12,"column":3}])
    def test_raw_logs_and_request_dropped(self):
        event={"event":{"request":{"url":"https://example.invalid/?SECRET_QUERY","body":"SECRET_BODY","headers":{"Authorization":"SECRET_HEADER"}}},"logs":[{"message":["SECRET_RAW",json.dumps(self.incident())]}]}
        result=m.incidents_from_event(event);self.assertEqual(len(result),1);self.assertNotIn("SECRET_",json.dumps(result))
    def test_invalid_contract_rejected(self):
        for field,value in (("environment","PROD"),("schema","wrong"),("incident_id","-"*36),("message_sha256","SECRET_DIGEST"),("exception_class","SECRET_CLASS"),("safe_cause_class","SECRET_CAUSE"),("route","SECRET_ROUTE")):
            with self.subTest(field=field):
                data=self.incident();data[field]=value;self.assertIsNone(m.safe_incident(data))
    def test_unknown_or_unbounded_frames_dropped(self):
        data=self.incident();data["stack_frames"]=[{"function":"SECRET_FUNCTION","line":2,"column":3},{"function":"fetch","line":0,"column":3},{"function":"fetch","line":2,"column":True},{"function":"fetch","line":1000001,"column":3}]
        self.assertEqual(m.safe_incident(data)["stack_frames"],[])
    def test_parser_does_not_subscribe_or_request(self):
        self.assertEqual(m.incidents_from_event({"logs":[{"message":["{}",'{"authorization":"SECRET"}',"invalid"]}]}),[])
if __name__=="__main__":unittest.main()
