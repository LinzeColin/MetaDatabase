'use strict';
let csrf='';const feedback=document.getElementById('feedback');const usage=document.getElementById('usage-summary');
async function load(){const r=await fetch('/api/me',{cache:'no-store'});if(r.status===401){location.replace('/');return;}const x=await r.json();csrf=x.csrf||'';if(x.usage){usage.textContent=`今日已用 ${Number(x.usage.usedTokens||0).toLocaleString()} Token，剩余 ${Number(x.usage.remainingTokens||0).toLocaleString()} Token；已用名额 ${x.usage.activeOrdinarySeats||0}/5。`;}}
async function post(url){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf})});const x=await r.json();if(!r.ok)throw new Error(x.action||'操作没有成功');return x;}
document.querySelectorAll('[data-action="coming"]').forEach(b=>b.addEventListener('click',()=>{feedback.textContent='这一步会在微信里给你发送图文指引。';}));
document.getElementById('export-button').addEventListener('click',async()=>{try{await post('/api/export');feedback.textContent='已开始准备，完成后会在微信通知你。';}catch(e){feedback.textContent=e.message;}});
document.getElementById('delete-button').addEventListener('click',async()=>{if(!confirm('确定要申请删除账户吗？删除后无法恢复。'))return;try{await post('/api/delete');feedback.textContent='申请已提交，系统会在微信通知进度。';}catch(e){feedback.textContent=e.message;}});
document.getElementById('logout-button').addEventListener('click',async()=>{try{await post('/api/logout');location.replace('/');}catch(e){feedback.textContent=e.message;}});load().catch(()=>location.replace('/'));
