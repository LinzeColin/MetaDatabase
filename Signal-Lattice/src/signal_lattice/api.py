from __future__ import annotations
import json, mimetypes, re, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .config import Settings
from .db import RuntimeDB
from .status import default_matrix

SECURITY_HEADERS={
 'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
 'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
 'Permissions-Policy':'camera=(), microphone=(), geolocation=()','Cache-Control':'no-store'
}

def handler(settings:Settings,db:RuntimeDB):
 class H(BaseHTTPRequestHandler):
  server_version='SignalLattice/0.0.0.1.39'
  protocol_version='HTTP/1.1'
  def setup(self):
   super().setup(); self.connection.settimeout(settings.request_timeout_seconds)
  def log_message(self,fmt,*args): pass
  def _send(self,status:int,payload:object,ctype='application/json; charset=utf-8'):
   body=(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode() if not isinstance(payload,(bytes,bytearray)) else bytes(payload))
   self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body)))
   for k,v in SECURITY_HEADERS.items():self.send_header(k,v)
   self.send_header('Connection','close'); self.end_headers(); self.wfile.write(body); self.close_connection=True
  def _json(self):
   ctype=self.headers.get_content_type()
   if ctype!='application/json':return None
   try:n=int(self.headers.get('Content-Length','0'))
   except ValueError:return None
   if n<=0 or n>settings.max_request_bytes:return None
   try:return json.loads(self.rfile.read(n))
   except Exception:return None
  def do_GET(self):
   p=urlparse(self.path).path
   if p=='/health/live':return self._send(200,{'status':'alive'})
   if p=='/health/ready':return self._send(200,{'status':'ready','mode':'RESEARCH_AND_NO_ACTION'})
   if p=='/api/v1/status':return self._send(200,{'state':'DEGRADED','live_action':False,'agent_dependency':0,'llm_tokens':0})
   if p=='/api/v1/business-lines':return self._send(200,default_matrix())
   if p=='/api/v1/actions':return self._send(200,{'items':db.actions()})
   m=re.fullmatch(r'/api/v1/jobs/([A-Za-z0-9-]+)',p)
   if m:
    item=db.get_job(m.group(1)); return self._send(200,item) if item else self._send(404,{'error':'NOT_FOUND'})
   file='index.html' if p in ('/','') else p.lstrip('/')
   target=(settings.web_dir/file).resolve()
   if settings.web_dir.resolve() not in target.parents and target!=settings.web_dir.resolve():return self._send(403,{'error':'FORBIDDEN'})
   if target.is_file():return self._send(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
   return self._send(404,{'error':'NOT_FOUND'})
  def do_POST(self):
   p=urlparse(self.path).path
   if p!='/api/v1/research':return self._send(404,{'error':'NOT_FOUND'})
   data=self._json()
   if not isinstance(data,dict):return self._send(400,{'error':'INVALID_JSON_OR_SIZE'})
   if len(data)>32:return self._send(400,{'error':'TOO_MANY_FIELDS'})
   key=self.headers.get('Idempotency-Key') or str(uuid.uuid4())
   job,created=db.enqueue(data,key)
   return self._send(202 if created else 200,{'job_id':job,'created':created,'state':'QUEUED' if created else 'EXISTING'})
 return H

def serve(settings:Settings,db:RuntimeDB):
 server=ThreadingHTTPServer((settings.host,settings.port),handler(settings,db));server.daemon_threads=True;server.serve_forever()
