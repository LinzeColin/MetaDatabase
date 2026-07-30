from __future__ import annotations
import hashlib,json,os,subprocess,tempfile,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path.startswith('/api/v1/status'):
   body=json.dumps({'project_id':'signal-lattice','version':'0.0.0.1.40','state':'PASS','mode':'HUMAN_DECISION_SUPPORT','recommendation_mode':'HUMAN_DECISION_SUPPORT','runtime_agent_dependency':0,'runtime_llm_tokens':0,'automatic_trading':False,'human_execution_only':True,'current_action':'NO_ACTION','public_url':'https://signal-lattice.linzezhang.com'}).encode();ctype='application/json'
  elif self.path.startswith('/api/v1/recommendations'):
   body=json.dumps({'items':[],'mode':'HUMAN_DECISION_SUPPORT'}).encode();ctype='application/json'
  else:
   body='Signal Lattice 股票信号格阵 最终投资建议 内部协调'.encode();ctype='text/html; charset=utf-8'
  self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'self'");self.send_header('X-Frame-Options','DENY');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)

class PublicReleaseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.root=Path(__file__).resolve().parents[1]
 def test_public_release_receipt_and_delivery_result(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with tempfile.TemporaryDirectory() as t:
    r=Path(t);url=f'http://127.0.0.1:{server.server_address[1]}'
    env=os.environ.copy();env['PYTHONPATH']=str(self.root/'src')
    verify=subprocess.run([os.sys.executable,str(self.root/'scripts/verify_public_release.py'),'--url',url,'--version','0.0.0.1.40','--output',str(r/'public.json'),'--allow-local-test'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    self.assertEqual(verify.returncode,0,verify.stdout+verify.stderr)
    closure={'schema_version':'1.0.0','state':'PASS','line_count':13,'cell_count':117}
    closure['receipt_sha256']=hashlib.sha256(json.dumps(closure,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();(r/'closure.json').write_text(json.dumps(closure))
    result=subprocess.run([os.sys.executable,str(self.root/'scripts/build_delivery_result.py'),'--public-receipt',str(r/'public.json'),'--status-closure',str(r/'closure.json'),'--version','0.0.0.1.40','--output',str(r/'DELIVERY_RESULT.json'),'--markdown',str(r/'DELIVERY_RESULT.md')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(json.loads((r/'DELIVERY_RESULT.json').read_text())['completion_claim'],'DEPLOYED_AND_PUBLICLY_VERIFIED')
  finally:server.shutdown();server.server_close()
