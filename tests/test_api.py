from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from fraudguard.api import MAX_BODY, make_server
from fraudguard.engine import Engine
from fraudguard.models import ValidationError
from helpers import event


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory()
        cls.engine=Engine(Path(cls.tmp.name)/"api.db")
        cls.server=make_server(cls.engine,port=0)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def call(self,path,method="GET",body=None,headers=None):
        conn=HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            raw=json.dumps(body).encode() if isinstance(body,(dict,list)) else body
            conn.request(method,path,body=raw,headers=headers or ({"Content-Type":"application/json"} if raw else {}))
            response=conn.getresponse()
            data=response.read()
            return response.status,data,dict(response.getheaders())
        finally:
            conn.close()

    def test_health_and_loopback_binding(self):
        status,raw,_=self.call("/api/health")
        self.assertEqual(status,200)
        self.assertTrue(json.loads(raw)["simulated"])
        self.assertEqual(self.server.server_address[0],"127.0.0.1")
        with self.assertRaises(ValidationError):
            make_server(self.engine,"0.0.0.0",0)

    def test_post_assessment_and_histories(self):
        status,raw,_=self.call("/api/events","POST",event("api-success",tenant="success"))
        self.assertEqual(status,201)
        self.assertEqual(json.loads(raw)["assessments"][0]["decision"],"APPROVE")
        status,raw,_=self.call("/api/assessment?tenant_id=success&user_id=u&device_id=d")
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)["risk_index"],0)
        for kind in ("events","assessments","decisions","blocks"):
            status,raw,_=self.call(f"/api/{kind}?tenant_id=success&limit=1&offset=0")
            self.assertEqual(status,200)
            self.assertIn("items",json.loads(raw))

    def test_demo_end_to_end_and_replay(self):
        for scenario,decision in (("normal","APPROVE"),("verify","VERIFY"),("freeze","FREEZE")):
            with self.subTest(scenario=scenario):
                status,raw,_=self.call(f"/api/demos/{scenario}","POST",{})
                self.assertIn(status,(200,201))
                first=json.loads(raw)
                self.assertEqual(first["assessments"][-1]["decision"],decision)
                status,raw,_=self.call(f"/api/demos/{scenario}","POST",{})
                self.assertEqual(status,200)
                again=json.loads(raw)
                self.assertEqual(again["accepted"],0)
                self.assertEqual(first["assessments"],again["assessments"])

    def test_validation_errors(self):
        for body in ({},[],None,{**event(),"simulated":False},{"events":[]},{"events":"wrong"}):
            with self.subTest(body=body):
                status,_,_=self.call("/api/events","POST",json.dumps(body),{"Content-Type":"application/json"})
                self.assertEqual(status,400)

    def test_invalid_and_ambiguous_json(self):
        for raw in ('{','{"a":1,"a":2}','{"a":NaN}',b'\xff'):
            with self.subTest(raw=raw):
                status,_,_=self.call("/api/events","POST",raw,{"Content-Type":"application/json"})
                self.assertEqual(status,400)

    def test_request_limits_and_content_type(self):
        status,_,_=self.call("/api/events","POST",b" "*(MAX_BODY+1),{"Content-Type":"application/json"})
        self.assertEqual(status,413)
        status,_,_=self.call("/api/events","POST",b"{}",{"Content-Type":"text/plain"})
        self.assertEqual(status,415)
        status,_,_=self.call("/api/events","POST",b"",{"Content-Type":"application/json"})
        self.assertEqual(status,413)
        status,_,_=self.call("/api/events","POST",b"{}",{"Content-Type":"application/json","Transfer-Encoding":"chunked"})
        self.assertEqual(status,400)

    def test_conflict_and_duplicate(self):
        value=event("conflict",tenant="api-conflict")
        self.assertEqual(self.call("/api/events","POST",value)[0],201)
        self.assertEqual(self.call("/api/events","POST",value)[0],200)
        value["data"]["amount_minor"]=2000
        self.assertEqual(self.call("/api/events","POST",value)[0],409)

    def test_query_errors_and_unknown_routes(self):
        for path in ("/api/assessment", "/api/events", "/api/events?tenant_id=t&limit=201",
                     "/api/events?tenant_id=t&offset=-1", "/api/events?tenant_id=t&tenant_id=x",
                     "/api/events?tenant_id=t&x=1", "/api/health?secret=no",
                     "/api/assessment?tenant_id=t&user_id=u&device_id=d&at=bad"):
            with self.subTest(path=path):
                self.assertEqual(self.call(path)[0],400)
        self.assertEqual(self.call("/does-not-exist")[0],404)
        self.assertEqual(self.call("/api/demos/missing","POST",{})[0],400)
        self.assertEqual(self.call("/api/not-real","POST",{})[0],404)

    def test_cross_origin_and_host_rejected(self):
        self.assertEqual(self.call("/api/events","POST",event(),
                         {"Content-Type":"application/json","Origin":"http://untrusted.example"})[0],403)
        self.assertEqual(self.call("/api/health",headers={"Host":"untrusted.example"})[0],403)

    def test_offline_assets_and_security_headers(self):
        for path,mime in (("/","text/html"),("/dashboard.js","text/javascript"),("/dashboard.css","text/css")):
            status,raw,headers=self.call(path)
            self.assertEqual(status,200)
            self.assertIn(mime,headers["Content-Type"])
            self.assertIn("frame-ancestors 'none'",headers["Content-Security-Policy"])
            self.assertNotIn(b"https://",raw)
            self.assertGreater(len(raw),100)
        self.assertEqual(self.call("/../AGENTS.md")[0],404)

    def test_concurrent_duplicate_submission(self):
        value=event("threaded",tenant="concurrency")
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.call("/api/events","POST",value),range(4)))
        self.assertEqual(sorted(status for status,_,_ in results),[200,200,200,201])
        self.assertEqual(len(self.engine.history("events","concurrency")),1)

    def test_current_block_and_expiry_api(self):
        self.call("/api/demos/freeze","POST",{})
        query="tenant_id=demo&user_id=fictional-freeze&device_id=device-freeze"
        self.assertEqual(json.loads(self.call("/api/assessment?"+query+"&at=2026-01-01T13:01:59Z")[1])["decision"],"FREEZE")
        self.assertEqual(json.loads(self.call("/api/assessment?"+query+"&at=2026-01-01T13:02:00Z")[1])["decision"],"APPROVE")
