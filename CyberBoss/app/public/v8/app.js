'use strict';
(() => {
  const $=(id)=>document.getElementById(id); const card=$('login-card'), image=$('qr-image'), placeholder=$('qr-placeholder'), dot=$('status-dot'), statusText=$('status-text'), retry=$('retry-button'), repair=$('repair-text');
  function show(state,text=''){dot.className=`status-dot ${state}`;statusText.textContent=text||'正在连接';card.setAttribute('aria-busy',state==='loading'?'true':'false');repair.hidden=true;if(state==='ready'){placeholder.hidden=true;image.hidden=false;retry.hidden=true;}if(state==='pending'||state==='failed'){image.hidden=true;placeholder.hidden=true;retry.hidden=false;repair.hidden=false;repair.textContent='点击“重新读取”即可继续。';}}
  async function load(){retry.hidden=true;placeholder.hidden=false;image.hidden=true;show('loading','正在读取微信入口');const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),12000);try{const response=await fetch('/api/public-entry',{cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error('request failed');const entry=await response.json();if(entry.ready&&entry.qrDataUri){image.src=entry.qrDataUri;show('ready','微信入口已准备好');return;}show('pending',entry.message||'微信入口正在准备中');}catch{show('failed','暂时无法读取微信入口');}finally{clearTimeout(timer);}}
  retry.addEventListener('click',load); load();
})();
