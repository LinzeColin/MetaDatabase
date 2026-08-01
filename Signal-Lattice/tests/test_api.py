import tempfile,threading,unittest,json,urllib.request
from pathlib import Path
from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.api import handler
from http.server import ThreadingHTTPServer
class T(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();p=Path(self.t.name);root=Path(__file__).resolve().parents[1]
  self.root=root;self.token='x'*48;self.token_file=p/'ingest-token';self.token_file.write_text(self.token);self.s=Settings(p,p/'artifacts',root/'web','127.0.0.1',0,recommendation_enabled=True,runtime_environment='production',decision_policy_path=root/'config/decision_policy.json',ingest_token_file=self.token_file)
  self.db=RuntimeDB(p/'r.db',root/'db/schema.sql');self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.s,self.db));self.port=self.server.server_address[1];self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.t.cleanup()
 def get(self,path):return urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}',timeout=3)
 def post(self,path,payload,headers=None):
  h={'Content-Type':'application/json',**(headers or {})};req=urllib.request.Request(f'http://127.0.0.1:{self.port}{path}',data=json.dumps(payload).encode(),headers=h,method='POST');return urllib.request.urlopen(req,timeout=3)
 def test_health_headers_and_runtime_contract(self):
  r=self.get('/api/v1/status');data=json.load(r);self.assertEqual(r.status,200);self.assertEqual(r.headers['X-Frame-Options'],'DENY');self.assertEqual(data['runtime_agent_dependency'],0);self.assertEqual(data['runtime_llm_tokens'],0);self.assertFalse(data['automatic_trading']);self.assertEqual(data['public_url'],'https://signal-lattice.linzezhang.com')
 def test_ui(self):
  text=self.get('/').read().decode();self.assertIn('最终投资建议',text);self.assertIn('内部协调',text)
 def test_research_and_job(self):
  data=json.load(self.post('/api/v1/research',{'symbol':'AAA','market':'US'},{'Idempotency-Key':'z'}));self.assertTrue(data['job_id'])
 def test_business_lines(self):self.assertEqual(len(json.load(self.get('/api/v1/business-lines'))['lines']),14)
 def test_ingest_endpoints(self):
  signal=json.loads((self.root/'fixtures/northstar/commercial_signal.json').read_text());market=json.loads((self.root/'fixtures/northstar/market_snapshot.json').read_text())

  with self.assertRaises(Exception): self.post('/api/v1/inputs/skill-signal',signal)
  auth={'Authorization':'Bearer '+self.token}
  self.assertEqual(self.post('/api/v1/inputs/skill-signal',signal,auth).status,201);self.assertEqual(self.post('/api/v1/inputs/market-snapshot',market,auth).status,201);self.assertEqual(len(json.load(self.get('/api/v1/skills'))['items']),1)
