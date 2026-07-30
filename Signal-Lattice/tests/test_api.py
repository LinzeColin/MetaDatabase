import tempfile,threading,time,unittest,json,urllib.request
from pathlib import Path
from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.api import handler
from http.server import ThreadingHTTPServer
class T(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();p=Path(self.t.name);root=Path(__file__).resolve().parents[1]
  self.s=Settings(p,p/'artifacts',root/'web','127.0.0.1',0)
  self.db=RuntimeDB(p/'r.db',root/'db/schema.sql');self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.s,self.db));self.port=self.server.server_address[1];self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.t.cleanup()
 def get(self,path):return urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}',timeout=3)
 def test_health_headers(self):
  r=self.get('/health/live');self.assertEqual(r.status,200);self.assertEqual(r.headers['X-Frame-Options'],'DENY')
 def test_ui(self):self.assertIn('NO_ACTION',self.get('/').read().decode())
 def test_research_and_job(self):
  req=urllib.request.Request(f'http://127.0.0.1:{self.port}/api/v1/research',data=json.dumps({'symbol':'AAA','market':'US'}).encode(),headers={'Content-Type':'application/json','Idempotency-Key':'z'},method='POST');data=json.load(urllib.request.urlopen(req));self.assertTrue(data['job_id'])
 def test_business_lines(self):self.assertEqual(len(json.load(self.get('/api/v1/business-lines'))['lines']),13)
