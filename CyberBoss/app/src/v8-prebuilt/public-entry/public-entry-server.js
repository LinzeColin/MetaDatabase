'use strict';
const http=require('node:http');const fs=require('node:fs');const path=require('node:path');
const MAX_BODY=64*1024;const MIME={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.json':'application/json; charset=utf-8'};
function json(res,status,body,headers={}){const data=Buffer.from(JSON.stringify(body));res.writeHead(status,{'Content-Type':MIME['.json'],'Content-Length':data.length,'Cache-Control':'no-store',...headers});res.end(data);}
function securityHeaders(){return{'Content-Security-Policy':"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Permissions-Policy':'camera=(), microphone=(), geolocation=()','Cross-Origin-Opener-Policy':'same-origin'};}
async function readJson(req){let n=0;const chunks=[];for await(const chunk of req){n+=chunk.length;if(n>MAX_BODY)throw Object.assign(new Error('BODY_TOO_LARGE'),{code:'BODY_TOO_LARGE'});chunks.push(chunk);}if(!chunks.length)return{};try{return JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw Object.assign(new Error('BODY_INVALID'),{code:'BODY_INVALID'});}}
function safeAsset(root,urlPath){const name=urlPath==='/'?'index.html':urlPath.replace(/^\//,'');const resolved=path.resolve(root,name);if(!resolved.startsWith(path.resolve(root)+path.sep)&&resolved!==path.resolve(root))return null;return resolved;}
function createPublicEntryServer({entryService,webSessions,ownerActivation=null,authorizeOwner=()=>false,assetRoot,accountSummary=async()=>({}),exportHandler=async()=>({status:'queued'}),deleteHandler=async()=>({status:'queued'}),ready=()=>true,allowedHosts=[]}){
  if(!entryService||typeof entryService.summary!=='function')throw new TypeError('entryService required');
  const server=http.createServer(async(req,res)=>{Object.entries(securityHeaders()).forEach(([k,v])=>res.setHeader(k,v));try{const url=new URL(req.url,'http://local');if(allowedHosts.length&&!allowedHosts.includes(String(req.headers.host||'').split(':')[0]))return json(res,421,{error:'HOST_NOT_ALLOWED'});
    if(req.method==='GET'&&url.pathname==='/healthz')return json(res,200,{status:'ok'});if(req.method==='GET'&&url.pathname==='/readyz')return json(res,ready()?200:503,{status:ready()?'ready':'not_ready'});
    if(req.method==='GET'&&url.pathname==='/api/public-entry')return json(res,200,entryService.summary());

    if(url.pathname.startsWith('/api/ops/wechat/')){
      if(!ownerActivation||!authorizeOwner(req))return json(res,403,{error:'OWNER_ACCESS_REQUIRED'});
      if(req.method==='POST'&&url.pathname==='/api/ops/wechat/activation-sessions')return json(res,201,await ownerActivation.create());
      const match=url.pathname.match(/^\/api\/ops\/wechat\/activation-sessions\/([A-Za-z0-9_-]+)$/);
      if(req.method==='GET'&&match)return json(res,200,await ownerActivation.status(match[1]));
      return json(res,404,{error:'NOT_FOUND'});
    }

    if(req.method==='GET'&&url.pathname==='/api/session'){try{const s=webSessions.verify({cookieHeader:req.headers.cookie});return json(res,200,{authenticated:true,userId:s.userId});}catch{return json(res,200,{authenticated:false});}}
    if(req.method==='GET'&&url.pathname==='/api/me'){const s=webSessions.verify({cookieHeader:req.headers.cookie});return json(res,200,{userId:s.userId,csrf:s.csrf,...await accountSummary(s.userId)});}
    if(req.method==='POST'&&url.pathname==='/api/logout'){const body=await readJson(req);webSessions.verify({cookieHeader:req.headers.cookie,csrf:String(body.csrf||''),requireCsrf:true});webSessions.revoke({cookieHeader:req.headers.cookie});return json(res,200,{status:'signed_out'},{'Set-Cookie':webSessions.clearCookie()});}
    if(req.method==='POST'&&url.pathname==='/api/export'){const body=await readJson(req);const s=webSessions.verify({cookieHeader:req.headers.cookie,csrf:String(body.csrf||''),requireCsrf:true});return json(res,202,await exportHandler(s.userId));}
    if(req.method==='POST'&&url.pathname==='/api/delete'){const body=await readJson(req);const s=webSessions.verify({cookieHeader:req.headers.cookie,csrf:String(body.csrf||''),requireCsrf:true});return json(res,202,await deleteHandler(s.userId));}
    if(req.method!=='GET')return json(res,405,{error:'METHOD_NOT_ALLOWED'});
    const pages={'/home':'home.html','/account':'account.html','/privacy':'privacy.html','/source':'source.html','/ops/wechat':'ops-wechat.html'};
    if(url.pathname==='/ops/wechat'&&!authorizeOwner(req))return json(res,403,{error:'OWNER_ACCESS_REQUIRED'});
    const requested=pages[url.pathname]?`/${pages[url.pathname]}`:url.pathname;const file=safeAsset(assetRoot,requested);if(!file||!fs.existsSync(file)||!fs.statSync(file).isFile())return json(res,404,{error:'NOT_FOUND'});const data=fs.readFileSync(file);res.writeHead(200,{'Content-Type':MIME[path.extname(file)]||'application/octet-stream','Content-Length':data.length,'Cache-Control':file.endsWith('.html')?'no-store':'public, max-age=300'});res.end(data);
  }catch(error){const code=error?.code||'REQUEST_FAILED';const status=['SESSION_REQUIRED','SESSION_INVALID'].includes(code)?401:code==='CSRF_INVALID'?403:code==='BODY_TOO_LARGE'?413:400;json(res,status,{error:code,action:'请返回上一页后重试'});}});return server;
}
module.exports={createPublicEntryServer,securityHeaders};
