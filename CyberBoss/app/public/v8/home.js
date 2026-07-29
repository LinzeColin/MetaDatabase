'use strict';
fetch('/api/me',{cache:'no-store'}).then(async r=>{if(r.status===401){location.replace('/');return;}const x=await r.json();document.getElementById('health-copy').textContent=x.channelStatus==='active'?'可以直接回微信使用':'需要重新连接微信';}).catch(()=>{document.getElementById('health-copy').textContent='暂时无法读取，请稍后刷新';});
