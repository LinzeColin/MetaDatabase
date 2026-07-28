'use strict';
class MvpRuntime{
  constructor({server,supervisor,replyDispatcher,clock=()=>Date.now(),pollIntervalMs=1200,replyIntervalMs=250,onError=()=>{}}){Object.assign(this,{server,supervisor,replyDispatcher,clock,pollIntervalMs,replyIntervalMs,onError});this.stopped=true;this.timers=new Set();}
  schedule(fn,ms){if(this.stopped)return;const id=setTimeout(async()=>{this.timers.delete(id);if(this.stopped)return;try{await fn();}catch(e){this.onError(e);}finally{this.schedule(fn,ms);}},ms);id.unref?.();this.timers.add(id);}
  async start({host='127.0.0.1',port=8787}={}){if(!this.stopped)return;this.stopped=false;await new Promise((resolve,reject)=>{const onError=(e)=>{this.server.off('listening',onListen);reject(e);};const onListen=()=>{this.server.off('error',onError);resolve();};this.server.once('error',onError);this.server.once('listening',onListen);this.server.listen(port,host);});this.schedule(()=>this.supervisor.tick(),this.pollIntervalMs);this.schedule(()=>this.replyDispatcher.runOnce(),this.replyIntervalMs);return{host,port:this.server.address().port};}
  async stop(){if(this.stopped)return;this.stopped=true;for(const id of this.timers)clearTimeout(id);this.timers.clear();if(this.server.listening)await new Promise(resolve=>this.server.close(resolve));}
}
module.exports={MvpRuntime};
