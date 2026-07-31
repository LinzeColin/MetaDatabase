from __future__ import annotations
import hashlib,json,os,subprocess,tempfile,threading,unittest
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

NOW=datetime.now(timezone.utc).isoformat()
SKILLS=[{"skill_id":f"skill-{i}","state":"PASS","output_digest":str(i)*64} for i in range(1,7)]
CURRENT={
 "schema_version":"2.0.0","state":"PASS","action":"BUY","symbol":"AAPL","market":"US",
 "full_cycle_completed":True,"effective_skill_count":5,"market_data_production_eligible":True,
 "market_data_license_ok":True,"market_data_source":"MOOMOO_OPEND_QUOTE_ONLY","reasons":[],
 "human_execution_only":True,"automatic_execution_allowed":False
}
CYCLE={"cycle_id":"cycle-1","state":"COMPLETED","completed_at":NOW,"active_skill_count":6,"completed_skill_count":6,"failed_skill_count":0,"skill_runs":SKILLS}
class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path.startswith('/api/v1/system/status') or self.path.startswith('/api/v1/status'):
   payload={'project_id':'signal-lattice','version':'0.0.0.1.41','state':'PASS','mode':'HUMAN_DECISION_SUPPORT','runtime_agent_dependency':0,'runtime_llm_tokens':0,'automatic_trading':False,'human_execution_only':True,'public_url':'https://signal-lattice.linzezhang.com'}
  elif self.path.startswith('/api/v1/cycles/latest'):payload=CYCLE
  elif self.path.startswith('/api/v1/recommendations'):payload={'current':CURRENT,'items':[CURRENT],'mode':'HUMAN_DECISION_SUPPORT'}
  elif self.path.startswith('/api/v1/skills'):payload={'active_count':6,'items':SKILLS}
  else:
   body='Signal Lattice 股票信号格阵 唯一投资建议 每分钟 Skill 隔离判断 中枢协调'.encode();self._write(200,body,'text/html; charset=utf-8');return
  self._write(200,json.dumps(payload).encode(),'application/json')
 def _write(self,status,body,ctype):
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Content-Security-Policy',"default-src 'self'");self.send_header('X-Frame-Options','DENY');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)


class EmptyH(H):
 def do_GET(self):
  if self.path.startswith('/api/v1/system/status') or self.path.startswith('/api/v1/status'):
   payload={'project_id':'signal-lattice','version':'0.0.0.1.41','state':'PASS','mode':'HUMAN_DECISION_SUPPORT','runtime_agent_dependency':0,'runtime_llm_tokens':0,'automatic_trading':False,'human_execution_only':True,'public_url':'https://signal-lattice.linzezhang.com'}
  elif self.path.startswith('/api/v1/cycles/latest'):
   payload={'cycle_id':'empty','state':'FAILED','completed_at':NOW,'active_skill_count':0,'completed_skill_count':0,'failed_skill_count':0,'skill_runs':[]}
  elif self.path.startswith('/api/v1/recommendations'):
   payload={'current':None,'items':[],'mode':'HUMAN_DECISION_SUPPORT'}
  elif self.path.startswith('/api/v1/skills'):
   payload={'active_count':0,'items':[]}
  else:
   body='Signal Lattice 股票信号格阵 唯一投资建议 每分钟 Skill 隔离判断 中枢协调'.encode();self._write(200,body,'text/html; charset=utf-8');return
  self._write(200,json.dumps(payload).encode(),'application/json')

class PublicReleaseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.root=Path(__file__).resolve().parents[1]
 def test_public_release_receipt_and_delivery_result(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with tempfile.TemporaryDirectory() as t:
    r=Path(t);url=f'http://127.0.0.1:{server.server_address[1]}'
    env=os.environ.copy();env['PYTHONPATH']=str(self.root/'src')
    verify=subprocess.run([os.sys.executable,str(self.root/'scripts/verify_public_release.py'),'--url',url,'--version','0.0.0.1.41','--output',str(r/'public.json'),'--allow-local-test'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    self.assertEqual(verify.returncode,0,verify.stdout+verify.stderr)
    receipt=json.loads((r/'public.json').read_text());self.assertTrue(receipt['north_star_chain_verified']);self.assertEqual(receipt['diagnostics']['recommendation_count'],1)
    closure={'schema_version':'1.0.0','state':'PASS','line_count':14,'cell_count':126}
    closure['receipt_sha256']=hashlib.sha256(json.dumps(closure,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();(r/'closure.json').write_text(json.dumps(closure))
    result=subprocess.run([os.sys.executable,str(self.root/'scripts/build_delivery_result.py'),'--public-receipt',str(r/'public.json'),'--status-closure',str(r/'closure.json'),'--version','0.0.0.1.41','--output',str(r/'DELIVERY_RESULT.json'),'--markdown',str(r/'DELIVERY_RESULT.md')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(json.loads((r/'DELIVERY_RESULT.json').read_text())['completion_claim'],'NORTH_STAR_DEPLOYED_AND_PUBLICLY_VERIFIED')
  finally:server.shutdown();server.server_close()

 def test_empty_shell_cannot_pass_public_release(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),EmptyH);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with tempfile.TemporaryDirectory() as t:
    r=Path(t);url=f'http://127.0.0.1:{server.server_address[1]}'
    env=os.environ.copy();env['PYTHONPATH']=str(self.root/'src')
    verify=subprocess.run([os.sys.executable,str(self.root/'scripts/verify_public_release.py'),'--url',url,'--version','0.0.0.1.41','--output',str(r/'public.json'),'--allow-local-test'],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    self.assertEqual(verify.returncode,2,verify.stdout+verify.stderr)
    receipt=json.loads((r/'public.json').read_text())
    self.assertEqual(receipt['state'],'BLOCKED')
    self.assertFalse(receipt['north_star_chain_verified'])
    self.assertFalse(receipt['checks']['active_skills_minimum'])
    self.assertFalse(receipt['checks']['exactly_one_recommendation'])
  finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
