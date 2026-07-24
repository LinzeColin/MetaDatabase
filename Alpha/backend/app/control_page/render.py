"""看盘页 HTML 渲染(纯函数:overview dict -> HTML 字符串)。

设计基准来自公开竞品反向分析(2026-07-23 调研,2026-07-24 改版为浅色):
- Koyfin / Stripe Dashboard:纯白底 + 极细边框 + 克制留白,机构级观感;
- Ghostfolio:英雄数字(总净值+涨跌)压顶 + 一条主净值曲线;
- FreqUI(freqtrade):机器人运维面板 = 状态徽章 + 持仓盈亏 + 动作流水;
- moomoo/futu:持仓行(现价/成本/市值/浮动盈亏)+ 红涨绿跌(中国惯例);
- TradingView:等宽数字排版。
本页只读、公开(owner 裁定)、全中文人话、悉尼时间、无任何外链资源。
涨跌色遵循 moomoo 中国惯例:红涨绿跌,并叠加 +/− 与 ▲▼ 双通道防歧义。
"""

from __future__ import annotations

import html as _html

_CSS = """
*{box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:0;
  background:#f4f5f7;color:#1a2130;font-variant-numeric:tabular-nums;
  -webkit-font-smoothing:antialiased}
a{color:#9a6b16;text-decoration:none}
.wrap{max-width:1040px;margin:0 auto;padding:16px 16px 48px}
.top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:4px 2px 14px}
.logo{font-weight:800;font-size:21px;letter-spacing:3px;color:#1a2130}
.logo b{color:#b8860b}
.badge{font-size:12px;padding:3px 11px;border-radius:999px;border:1px solid #d7dbe2;
  color:#5a6472;background:#fff}
.badge.on{border-color:#bfe4cd;color:#0f7a37;background:#eefaf1}
.badge.off{border-color:#dde1e8;color:#8a93a5;background:#fff}
.clock{margin-left:auto;font-size:12px;color:#8a93a5}
.banner{padding:13px 17px;border-radius:12px;font-size:15px;font-weight:600;margin-bottom:14px;
  border:1px solid transparent}
.banner.ok{background:#eefaf1;border-color:#bfe4cd;color:#0f7a37}
.banner.halted{background:#fff5e5;border-color:#f3d9a3;color:#8a5a06}
.banner.warn{background:#fdecec;border-color:#f3c0c0;color:#b1283a}
.grid{display:grid;gap:14px;grid-template-columns:1fr}
@media(min-width:860px){.grid{grid-template-columns:1fr 1fr}.span2{grid-column:1/-1}}
.card{background:#fff;border:1px solid #e4e7ec;border-radius:14px;padding:16px 18px;
  box-shadow:0 1px 2px rgba(16,24,40,.04)}
.card h2{font-size:11.5px;color:#8a93a5;margin:0 0 12px;font-weight:600;
  letter-spacing:.8px;text-transform:uppercase}
.hero-num{font-size:40px;font-weight:800;letter-spacing:.5px;line-height:1.05;color:#101828}
.hero-sub{display:flex;gap:18px;flex-wrap:wrap;margin-top:8px;font-size:14px}
/* 涨跌色:owner 2026-07-24 指定改用美股惯例——绿涨红跌(原为 moomoo 中国惯例红涨绿跌) */
.up{color:#0f8a3c}.dn{color:#d1293d}.flat{color:#8a93a5}
/* 总盈亏染卡片背景 */
.card.gainbg{background:linear-gradient(180deg,#f1fbf5,#fff);border-color:#bfe4cd}
.card.lossbg{background:linear-gradient(180deg,#fdf3f3,#fff);border-color:#f3c0c0}
/* 目标进度横框:满额=本日历年应达本金;蓝竖线=本月应达本金;左侧气泡=当前净值 */
.prog{position:relative;height:26px;border-radius:9px;background:#eef0f3;
  border:1px solid #e4e7ec;margin-top:14px}
.prog>i{display:block;height:100%;border-radius:8px 0 0 8px;transition:width .4s}
.prog.gain>i{background:linear-gradient(90deg,#8fdcae,#12a150)}
.prog.loss>i{background:linear-gradient(90deg,#f5b5b5,#d1293d)}
.prog>b{position:absolute;top:-5px;bottom:-5px;width:3px;background:#1d6fe0;
  border-radius:2px;box-shadow:0 0 0 3px rgba(29,111,224,.16)}
.proglegend{display:flex;gap:16px;flex-wrap:wrap;font-size:11.5px;color:#6b7480;margin-top:9px}
.proglegend em{font-style:normal;color:#1a2130;font-weight:600}
.proglegend s{text-decoration:none;display:inline-block;width:10px;height:10px;
  border-radius:3px;margin-right:5px;vertical-align:-1px}
.kpis{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:12.5px;color:#6b7480}
.kpis b{color:#1a2130;font-weight:700}
.expo{height:8px;border-radius:99px;background:#eef0f3;margin-top:11px;overflow:hidden}
.expo>i{display:block;height:100%;background:linear-gradient(90deg,#d8ab45,#b8860b)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{color:#8a93a5;font-weight:600;font-size:11px;text-align:left;padding:2px 8px 9px;
  letter-spacing:.3px;white-space:nowrap}
td{border-top:1px solid #eef0f3;padding:10px 8px;vertical-align:top}
.num{text-align:right}th.num{text-align:right}
.sym{font-weight:700}.symcn{color:#8a93a5;font-size:11.5px}
.pnl{font-weight:700}
.lights{display:grid;gap:9px}
.light{display:flex;gap:10px;align-items:flex-start;font-size:13.5px}
.dot{width:10px;height:10px;border-radius:99px;margin-top:4px;flex:none}
.dot.g{background:#12a150;box-shadow:0 0 0 3px #12a15022}
.dot.r{background:#e5484d;box-shadow:0 0 0 3px #e5484d22}
.light small{display:block;color:#8a93a5;font-size:11.5px;margin-top:1px}
.verdict{margin-top:11px;padding:10px 13px;border-radius:10px;font-size:13px;
  background:#f4f5f7;color:#3a4453;border:1px solid #e9ebef}
.tl{list-style:none;margin:0;padding:0;font-size:13.5px}
.tl li{display:flex;gap:10px;padding:9px 0;border-top:1px solid #eef0f3}
.tl li:first-child{border-top:0}
.tl time{color:#8a93a5;font-size:12px;white-space:nowrap;padding-top:1px}
.tl .ic{flex:none}
.hb{display:flex;gap:8px;flex-wrap:wrap}
.hb span{font-size:12px;padding:4px 11px;border-radius:8px;background:#f4f5f7;color:#5a6472;
  border:1px solid #e9ebef}
.hb i{display:inline-block;width:7px;height:7px;border-radius:99px;margin-right:6px}
.hb .ok i{background:#12a150}.hb .bad i{background:#e5484d}
.muted{color:#6b7480;font-size:12px;line-height:1.7}
.big{font-size:22px;font-weight:800;color:#101828}
details{margin-top:16px}summary{color:#98a1af;font-size:11px;cursor:pointer}
footer{margin-top:18px}
.chartwrap{position:relative;margin-top:14px}
.chartbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.ranges{display:inline-flex;gap:3px;background:#f2f4f7;border-radius:10px;padding:3px}
.ranges button{border:0;background:transparent;font:inherit;font-size:12px;color:#5a6472;
  padding:6px 13px;border-radius:8px;cursor:pointer}
.ranges button:hover{color:#101828}
.ranges button.on{background:#fff;color:#101828;font-weight:700;box-shadow:0 1px 2px rgba(16,24,40,.10)}
.customrange{display:flex;gap:6px;align-items:center;font-size:12px;color:#8a93a5}
.customrange input{font:inherit;font-size:12px;padding:5px 8px;border:1px solid #d7dbe2;
  border-radius:8px;color:#1a2130;background:#fff}
.chart{width:100%}
.chart svg{display:block;width:100%;height:auto}
.charttip{position:absolute;pointer-events:none;background:#101828;color:#fff;font-size:12px;
  line-height:1.55;padding:8px 11px;border-radius:9px;white-space:nowrap;z-index:6;
  box-shadow:0 8px 22px rgba(16,24,40,.22);transform:translate(-50%,-118%)}
.charttip b{color:#f6cf72;font-size:13.5px}
.chartempty{padding:30px 0;text-align:center;color:#8a93a5;font-size:12.5px}
.fxline{font-size:11.5px;color:#8a93a5;margin-top:9px}
"""

_JS = """
function tick(){var el=document.querySelector('[data-clock]');if(el){
  el.textContent=new Intl.DateTimeFormat('zh-CN',{timeZone:'Australia/Sydney',
  month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})
  .format(new Date())+' 悉尼';}}
setInterval(tick,1000);tick();
function ages(){var ns=document.querySelectorAll('.hb span[data-beat]');
  for(var i=0;i<ns.length;i++){var t=ns[i].getAttribute('data-beat');if(!t)continue;
    var b=new Date(t);if(isNaN(b))continue;
    var a=Math.max(0,Math.round((Date.now()-b.getTime())/1000));
    var el=ns[i].querySelector('[data-age]');if(el)el.textContent=a;
    ns[i].className=(a<150)?'ok':'bad';}}
function alphaChart(){
  var host=document.getElementById('chart'),node=document.getElementById('curve-data');
  if(!host||!node)return;
  var all=[];try{all=JSON.parse(node.textContent||'[]');}catch(e){all=[];}
  var base=parseFloat(host.getAttribute('data-baseline')||'0');
  var tip=document.getElementById('chartTip'),wrap=host.parentNode;
  var range=sessionStorage.getItem('alphaRange')||'all';
  var cs=document.getElementById('cstart'),ce=document.getElementById('cend');
  if(cs&&sessionStorage.getItem('alphaCS'))cs.value=sessionStorage.getItem('alphaCS');
  if(ce&&sessionStorage.getItem('alphaCE'))ce.value=sessionStorage.getItem('alphaCE');
  var pts=[],W=760,H=250,L=62,R=18,T=16,B=30;
  function money(v){return v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
  function sel(){var b=wrap.querySelectorAll('.ranges button');
    for(var i=0;i<b.length;i++)b[i].className=(b[i].getAttribute('data-r')===range)?'on':'';
    var cr=wrap.querySelector('.customrange');
    if(cr){if(range==='custom')cr.removeAttribute('hidden');else cr.setAttribute('hidden','');}}
  function pick(){
    if(!all.length)return[];
    if(range==='custom'){var a=cs&&cs.value,z=ce&&ce.value;
      return all.filter(function(p){return(!a||p.date>=a)&&(!z||p.date<=z);});}
    if(range==='7'||range==='30'){var n=parseInt(range,10);
      var d=new Date(all[all.length-1].date+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-(n-1));
      var f=d.toISOString().slice(0,10);
      return all.filter(function(p){return p.date>=f;});}
    return all;}
  function draw(){
    var d=pick();pts=[];
    if(!d.length){host.innerHTML='<div class=chartempty>该区间暂无净值数据</div>';return;}
    var vs=d.map(function(p){return p.v;}).concat([base]);
    var lo=Math.min.apply(null,vs),hi=Math.max.apply(null,vs);
    var sp=(hi-lo)||Math.max(1,Math.abs(hi)*0.02);lo-=sp*0.2;hi+=sp*0.2;
    function X(i){return d.length>1?L+(W-L-R)*(i/(d.length-1)):L+(W-L-R)/2;}
    function Y(v){return T+(H-T-B)*(1-(v-lo)/(hi-lo));}
    var g='';
    for(var k=0;k<=3;k++){var v=lo+(hi-lo)*k/3,y=Y(v);
      g+='<line x1="'+L+'" y1="'+y.toFixed(1)+'" x2="'+(W-R)+'" y2="'+y.toFixed(1)+'" stroke="#eef0f3"/>';
      g+='<text x="'+(L-9)+'" y="'+(y+3.5).toFixed(1)+'" font-size="10" fill="#98a1af" text-anchor="end">'+Math.round(v).toLocaleString('en-US')+'</text>';}
    var by=Y(base);
    g+='<line x1="'+L+'" y1="'+by.toFixed(1)+'" x2="'+(W-R)+'" y2="'+by.toFixed(1)+'" stroke="#b6bdc8" stroke-dasharray="5 4"/>';
    g+='<text x="'+(L+5)+'" y="'+(by-7).toFixed(1)+'" font-size="10" fill="#8a93a5">本金基准 '+money(base)+'</text>';
    var line='';
    for(var i=0;i<d.length;i++){var x=X(i),y=Y(d[i].v);pts.push({x:x,y:y,p:d[i]});line+=(i?' ':'')+x.toFixed(1)+','+y.toFixed(1);}
    if(d.length===1){var y0=Y(d[0].v).toFixed(1);line=L+','+y0+' '+(W-R)+','+y0;}
    var up=d[d.length-1].v>=base,col=up?'#12a150':'#d1293d';
    g='<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="'+col+'" stop-opacity="0.18"/><stop offset="1" stop-color="'+col+'" stop-opacity="0"/></linearGradient></defs>'+g;
    g+='<polygon points="'+L+','+(H-B)+' '+line+' '+(W-R)+','+(H-B)+'" fill="url(#cg)"/>';
    g+='<polyline points="'+line+'" fill="none" stroke="'+col+'" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>';
    var st=Math.max(1,Math.ceil(d.length/6));
    for(var i=0;i<d.length;i+=st)
      g+='<text x="'+X(i).toFixed(0)+'" y="'+(H-8)+'" font-size="10" fill="#98a1af" text-anchor="middle">'+d[i].date.slice(5)+'</text>';
    var lx=X(d.length-1),ly=Y(d[d.length-1].v);
    g+='<circle cx="'+lx.toFixed(1)+'" cy="'+ly.toFixed(1)+'" r="4" fill="'+col+'"/>';
    g+='<line id="cx" x1="0" y1="'+T+'" x2="0" y2="'+(H-B)+'" stroke="#98a1af" stroke-dasharray="3 3" opacity="0"/>';
    g+='<circle id="cd" r="5" fill="#fff" stroke="'+col+'" stroke-width="2.5" opacity="0"/>';
    g+='<rect id="chit" x="'+L+'" y="'+T+'" width="'+(W-L-R)+'" height="'+(H-T-B)+'" fill="transparent"/>';
    host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="净值曲线">'+g+'</svg>';
    bind();}
  function bind(){
    var svg=host.querySelector('svg');if(!svg)return;
    var hit=svg.querySelector('#chit'),cx=svg.querySelector('#cx'),cd=svg.querySelector('#cd');
    function mv(ev){
      var r=svg.getBoundingClientRect();
      var clx=(ev.touches&&ev.touches[0])?ev.touches[0].clientX:ev.clientX;
      var vx=(clx-r.left)/r.width*W,best=null,bd=1e9;
      for(var i=0;i<pts.length;i++){var dd=Math.abs(pts[i].x-vx);if(dd<bd){bd=dd;best=pts[i];}}
      if(!best)return;
      cx.setAttribute('x1',best.x);cx.setAttribute('x2',best.x);cx.setAttribute('opacity','1');
      cd.setAttribute('cx',best.x);cd.setAttribute('cy',best.y);cd.setAttribute('opacity','1');
      var df=best.p.v-base,sg=df>=0?'+':'−';
      tip.innerHTML=best.p.date+(best.p.live?' · 实时':'')+'<br><b>'+money(best.p.v)+'</b> 澳元<br>较本金 '+sg+money(Math.abs(df));
      tip.removeAttribute('hidden');
      tip.style.left=(host.offsetLeft+best.x/W*r.width)+'px';
      tip.style.top=(host.offsetTop+best.y/H*r.height)+'px';}
    function lv(){cx.setAttribute('opacity','0');cd.setAttribute('opacity','0');tip.setAttribute('hidden','');}
    hit.addEventListener('mousemove',mv);hit.addEventListener('mouseleave',lv);
    hit.addEventListener('touchmove',mv,{passive:true});hit.addEventListener('touchend',lv);}
  var bs=wrap.querySelectorAll('.ranges button');
  for(var i=0;i<bs.length;i++)bs[i].onclick=function(){
    range=this.getAttribute('data-r');sessionStorage.setItem('alphaRange',range);sel();draw();};
  if(cs)cs.onchange=function(){sessionStorage.setItem('alphaCS',cs.value);if(range==='custom')draw();};
  if(ce)ce.onchange=function(){sessionStorage.setItem('alphaCE',ce.value);if(range==='custom')draw();};
  sel();draw();}
setInterval(ages,1000);

alphaChart();ages();
setInterval(async function(){try{
  var r=await fetch(location.pathname,{cache:'no-store'});
  if(!r.ok)return;var t=await r.text();
  var d=new DOMParser().parseFromString(t,'text/html');
  if(d.querySelector('.wrap'))document.body.replaceChild(d.querySelector('.wrap'),document.querySelector('.wrap'));
  tick();alphaChart();ages();
}catch(e){}},30000);
"""


def _esc(x) -> str:
    return _html.escape(str(x), quote=True)


def _pnl_cls(v: float) -> str:
    return "up" if v > 0 else ("dn" if v < 0 else "flat")


def _pnl_txt(v: float, suffix: str = "") -> str:
    arrow = "▲" if v > 0 else ("▼" if v < 0 else "")
    return f"{arrow}{v:+,.2f}{suffix}" if v else f"0.00{suffix}"


def _chart_block(curve: list[dict], baseline: float) -> str:
    """净值图表容器:数据以 JSON 内嵌,由前端脚本绘制。
    支持 7天/30天/全部/自定义区间、hover 十字准星与金额气泡;涨绿跌红(美股惯例)。
    本金基准线标注左对齐,避免与末点数值重叠(owner 2026-07-24 反馈的重叠问题)。"""
    import json as _json
    data = _json.dumps(
        [{"date": p["date"], "v": round(float(p["equity_aud"]), 2),
          "live": bool(p.get("live"))} for p in (curve or [])],
        ensure_ascii=False).replace("<", "\\u003c")
    return f"""<div class=chartwrap>
<div class=chartbar>
  <div class=ranges>
    <button type=button data-r="7">7天</button>
    <button type=button data-r="30">30天</button>
    <button type=button data-r="all">全部</button>
    <button type=button data-r="custom">自定义</button>
  </div>
  <div class=customrange hidden><input type=date id=cstart><span>→</span><input type=date id=cend></div>
</div>
<div id=chart class=chart data-baseline="{baseline:.2f}"></div>
<div id=chartTip class=charttip hidden></div>
<script type="application/json" id="curve-data">{data}</script>
</div>"""


_KIND_ICON = {"fill": "✅", "order": "📝", "block": "🛡️", "mail": "✉️"}

_NAV_CSS = """
.nav{display:flex;gap:7px;margin:0 0 14px;flex-wrap:wrap}
.nav a{font-size:13px;padding:8px 15px;border-radius:10px;color:#5a6472;
  border:1px solid #e4e7ec;background:#fff;font-weight:500}
.nav a.on{color:#fff;background:#1a2130;border-color:#1a2130;font-weight:700}
.ok-badge{color:#0f8a3c}.bad-badge{color:#d1293d}
.pill{font-size:11.5px;padding:2px 9px;border-radius:99px;border:1px solid #d7dbe2;
  color:#5a6472;white-space:nowrap;background:#fff}
.pill.auto{border-color:#bfe4cd;color:#0f7a37;background:#eefaf1}
.pill.manual{border-color:#f3d9a3;color:#8a5a06;background:#fff7ea}
.pill.fault{border-color:#f3c0c0;color:#b1283a;background:#fdecec}
/* 投资策略页:现役英雄卡 + 宽研究表 */
.live-hero{background:linear-gradient(180deg,#fffdf6,#fff);border:1px solid #ecd9a6}
.live-hero .tag{display:inline-block;font-size:11.5px;font-weight:700;letter-spacing:.5px;
  color:#8a5a06;background:#fff2d4;border:1px solid #f0dca8;border-radius:999px;padding:3px 11px}
.live-name{font-size:24px;font-weight:800;color:#101828;margin:10px 0 2px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin-top:12px;font-size:13.5px}
.kv b{color:#8a93a5;font-weight:600;white-space:nowrap}
.kv span{color:#2a3345;line-height:1.6}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:2px -4px 0;
  border:1px solid #eef0f3;border-radius:10px}
table.wide{font-size:12.5px;min-width:1180px}
table.wide th{background:#f7f8fa;padding:10px 10px;position:sticky;top:0;border-bottom:1px solid #e4e7ec}
table.wide td{padding:11px 10px;border-top:1px solid #eef0f3}
table.wide tr.live td{background:#fffdf3}
/* 首列(策略名)横向滑动时钉住,否则滑到"年均收益率"就不知道在看哪条策略了 */
table.wide th:first-child,table.wide td:first-child{position:sticky;left:0;z-index:2;
  background:#fff;box-shadow:1px 0 0 #e4e7ec}
table.wide th:first-child{background:#f7f8fa;z-index:3}
table.wide tr.live td:first-child{background:#fffdf3}
.scrollhint{font-size:11.5px;color:#8a93a5;margin:0 0 7px;display:flex;
  align-items:center;gap:6px}
table.wide .name{font-weight:700;color:#101828;min-width:150px}
table.wide .wraptxt{min-width:180px;max-width:280px;white-space:normal;line-height:1.55;color:#3a4453}
table.wide .verd{min-width:170px;max-width:260px;white-space:normal;line-height:1.55;color:#5a6472;font-size:12px}
table.wide .metric{text-align:right;white-space:nowrap;font-weight:600;color:#1a2130}
table.wide .freq{white-space:nowrap;color:#3a4453}
.livemark{display:inline-block;font-size:10.5px;font-weight:700;color:#8a5a06;
  background:#fff2d4;border:1px solid #f0dca8;border-radius:5px;padding:1px 6px;margin-left:6px}
.dl{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;
  padding:8px 14px;border-radius:10px;border:1px solid #d7dbe2;background:#fff;color:#1a2130;margin-top:12px}
"""


def _nav(active: str) -> str:
    items = [("/", "驾驶舱"), ("/ops", "运维记录"), ("/strategy", "投资策略")]
    return "<nav class=nav>" + "".join(
        f'<a href="{href}"{" class=on" if href == active else ""}>{label}</a>'
        for href, label in items) + "</nav>"


def _shell(title: str, active: str, body: str) -> str:
    return f"""<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<meta http-equiv=refresh content="300">
<title>{_esc(title)}</title>
<style>{_CSS}{_NAV_CSS}</style>
<div class=wrap>
<div class=top><span class=logo>ALPHA</span>
<span class=clock data-clock></span></div>
{_nav(active)}
{body}
</div>
<script>{_JS}</script>"""


def render_ops_html(d: dict) -> str:
    caps = "".join(
        f"<div class=light><i class='dot g'></i><div><b>{_esc(n)}</b><small>{_esc(desc)}</small></div></div>"
        for n, desc in d["caps"])
    ledger = "".join(
        f"<tr><td>{_esc(r['date'])}</td><td class=num>{_esc(r['downtime_human'])}</td>"
        f"<td>{_esc(r['reason'])}</td></tr>"
        for r in d["ledger"]) or "<tr><td colspan=3 class=muted>无停机记录</td></tr>"
    events = "".join(
        f"<li><time>{_esc(e['at_syd'])}</time>"
        f"<span class='pill {_esc(e['kind'])}'>{'自动' if e['kind'] == 'auto' else ('人工' if e['kind'] == 'manual' else '故障')}</span>"
        f"<span><b>{_esc(e['title'])}</b>"
        f"<div class=symcn>{_esc(e['mail'])} · "
        f"<span class='{'ok-badge' if e['resolved'] else 'bad-badge'}'>{_esc(e['state_cn'])}</span></div></span></li>"
        for e in d["events"]) or "<li><span class=muted>暂无运维事件</span></li>"
    head = ("✅ 当前系统健康,无待处理故障" if d["healthy_now"] and d["open_faults"] == 0
            else f"⚠️ 待处理故障 {d['open_faults']} 项" if d["open_faults"]
            else "⚠️ 系统当前非健康态,详见驾驶舱")
    body = f"""
<div class="banner {'ok' if d['healthy_now'] and d['open_faults'] == 0 else 'warn'}">{_esc(head)}</div>
<div class=grid>
<div class=card><h2>自愈能力(长在服务器上,不依赖任何人在场)</h2><div class=lights>{caps}</div></div>
<div class=card><h2>停机事故台账(诚实口径,公开仓可审计)</h2>
<table><tr><th>日期</th><th class=num>停机时长</th><th>原因</th></tr>{ledger}</table></div>
<div class="card span2"><h2>运维事件流(故障 · 修复 · 邮件是否送达 · 是否待处理)</h2>
<ul class=tl>{events}</ul></div>
</div>
<footer class=muted>· 每一条故障与修复都会自动邮件通知;"待处理"表示尚无对应的恢复记录,需要人工或代理介入。<br>
· 数据来源:停机台账 + 通知发件箱 + 组件心跳,全部只读呈现;更新于 {_esc(d['updated_at_syd'])}(悉尼)。</footer>"""
    return _shell("Alpha 运维记录", "/ops", body)


#: 研究表列 -> CSS 类(数值列右对齐不换行;长文本列换行)
_STRAT_COL_CLS = {
    "策略": "name", "结构": "wraptxt", "交易频率": "freq",
    "月均收益率": "metric", "年均收益率": "metric", "最大回撤": "metric",
    "回撤修复时间": "metric", "策略规则": "wraptxt", "判定状态": "verd",
    "盈亏比": "metric", "胜率": "metric",
}


def render_strategy_html(d: dict) -> str:
    ch = d["champion"]
    limits = "".join(f"<li>{_esc(x)}</li>" for x in d["hard_limits"])
    gates = "".join(
        f"<div class=light><i class='dot g'></i><div><b>{_esc(g['name'])}</b>"
        f"<small>{_esc(g['rule'])}</small></div></div>"
        for g in d["gates"])

    cols = d.get("research_cols", [])
    thead = "".join(f"<th class={_STRAT_COL_CLS.get(c, '')}>{_esc(c)}</th>" for c in cols)
    trows = ""
    for r in d.get("research", []):
        live = r.get("现役") == "是"
        tds = ""
        for c in cols:
            cls = _STRAT_COL_CLS.get(c, "")
            val = _esc(r.get(c, ""))
            if c == "策略" and live:
                val = f"{val}<span class=livemark>● 现役</span>"
            tds += f"<td class={cls}>{val}</td>"
        trows += f"<tr class={'live' if live else ''}>{tds}</tr>"
    hint = ("<div class=scrollhint>↔ 表格可左右滑动:共 "
            f"{len(cols)} 列(月均收益率、<b>年均收益率</b>、最大回撤、回撤修复时间、"
            "盈亏比、胜率等);策略名会固定在左侧不动。</div>")
    table = (f"{hint}<div class=scroll><table class=wide><thead><tr>{thead}</tr></thead>"
             f"<tbody>{trows}</tbody></table></div>") if cols and trows else \
        "<div class=muted>研究史 CSV 暂不可读。</div>"

    body = f"""
<div class="card span2 live-hero">
  <span class=tag>● 当前实盘策略</span>
  <div class=live-name>{_esc(ch['name_cn'])}</div>
  <div class=kv>
    <b>怎么赚钱</b><span>{_esc(ch['logic_cn'])}</span>
    <b>节拍</b><span>{_esc(ch['cadence'])}</span>
    <b>持仓范围</b><span>{_esc(ch['universe'])}</span>
    <b>历史成绩</b><span>{_esc(ch['record'])}</span>
  </div>
</div>
<div class=grid>
<div class=card><h2>硬风控约束(写死在代码与契约,页面无权改)</h2>
<ul class=muted style="line-height:2;margin:0;padding-left:18px">{limits}</ul></div>
<div class=card><h2>晋级实盘的四道门(实时读契约配置)</h2><div class=lights>{gates}</div></div>
<div class="card span2"><h2>候选策略研究史(同一把尺子,全部证据公开可复验)</h2>
{table}
<a class=dl href="{_esc(d.get('research_csv_url', '/strategy/history.csv'))}" download>⬇ 下载全部策略 CSV</a>
<span class=muted style="margin-left:10px">同一份 CSV 也存于公开仓 configs/strategies/strategy_research_history.csv</span>
<div class=muted style="margin-top:12px">{_esc(d['research_note'])}</div></div>
</div>
<footer class=muted>· {_esc(d['honesty_note'])}<br>
· 回测不代表未来收益;本系统不向任何人承诺回报。更新于 {_esc(d['updated_at_syd'])}(悉尼)。</footer>"""
    return _shell("Alpha 投资策略", "/strategy", body)


def _progress_bar(p: dict) -> str:
    """目标进度横框(owner 2026-07-24 指定):
    满额 = 本日历年年末应达本金;蓝竖线 = 本月应达本金;左侧气泡 = 当前净值。
    气泡低于蓝线显红、达到或超过显绿;各段 hover 可看具体金额。
    目标线按回测月均复利推算,是尺子不是承诺。"""
    cls = "gain" if p["ahead"] else "loss"
    gap = p["gap_aud"]
    gap_txt = (f"已超出本月目标 {gap:,.2f} 澳元" if gap >= 0
               else f"距本月目标还差 {abs(gap):,.2f} 澳元")
    dot = "#12a150" if p["ahead"] else "#d1293d"
    return f"""<div class="prog {cls}">
<i style="width:{p['fill_pct']}%" title="当前净值 {p['equity_aud']:,.2f} 澳元 · {gap_txt}"></i>
<b style="left:{p['mark_pct']}%" title="本月应达本金 {p['month_target_aud']:,.2f} 澳元 = 3000 × (1+{p['monthly_rate_pct']}%) 的 {p['months_elapsed']} 次方"></b>
</div>
<div class=proglegend>
<span title="当前净值 = 账户实际到位资金 + 持仓市值"><s style="background:{dot}"></s>当前净值 <em>{p['equity_aud']:,.2f}</em> 澳元</span>
<span title="按当前策略月回报率 {p['monthly_rate_pct']}%,自 2026 年 7 月起复利推算的应达线"><s style="background:#1d6fe0"></s>本月应达 <em>{p['month_target_aud']:,.2f}</em> 澳元</span>
<span title="横框满额 = {p['year_label']} 年年末应达本金;距该目标还差 {p['to_year_gap_aud']:,.2f} 澳元"><s style="background:#cfd5de"></s>{p['year_label']} 年末目标 <em>{p['year_target_aud']:,.2f}</em> 澳元</span>
</div>"""


def render_dashboard_html(d: dict) -> str:
    hero, mkt, nd, health = d["hero"], d["market"], d["next_decision"], d["health"]

    pos_rows = "".join(
        f"<tr><td><span class=sym>{_esc(p['symbol'])}</span> "
        f"<span class=symcn>{_esc(p['name_cn'])}</span>"
        f"{'' if p['priced'] else '<div class=symcn>行情暂不可用,按成本估值</div>'}</td>"
        f"<td class=num>{p['qty']} 股<div class=symcn>成本 {p['avg_cost_usd']:,.2f}</div></td>"
        f"<td class=num>{p['last_usd']:,.2f}<div class=symcn>市值 {p['market_value_usd']:,.2f}</div></td>"
        f"<td class='num pnl {_pnl_cls(p['upl_usd'])}'>{_pnl_txt(p['upl_usd'])}"
        f"<div class=symcn>{p['upl_pct']:+.2f}%</div></td></tr>"
        for p in d["positions"])
    positions_block = (
        f"<table><tr><th>标的</th><th class=num>持有</th><th class=num>现价(美元)</th>"
        f"<th class=num>浮动盈亏(美元)</th></tr>{pos_rows}</table>"
        if d["positions"] else
        "<div class=big>空仓</div><div class=muted>钱都在手里,还没出手——按纪律,到下一个决策时间才会动。</div>")

    exam = d["exam"]
    if exam:
        lights = "".join(
            f"<div class=light><i class='dot {'g' if li['ok'] else 'r'}'></i>"
            f"<div><b>{_esc(li['name'])}</b> {'达标' if li['ok'] else '未达标'}"
            f"<small>{_esc(li['note'])}</small></div></div>"
            for li in exam["lights"])
        exam_block = (
            f"<div class=lights>{lights}</div>"
            f"<div class=verdict>结论:{_esc(exam['decision'])}</div>"
            f"<div class=muted style='margin-top:8px'>合格交易日 {exam['days_qualified']}/"
            f"{exam['days_required']};报告与证据哈希已存档公开仓({_esc(exam['report_date'])})。</div>")
    else:
        exam_block = "<div class=muted>三日模拟盘考核还没出报告;跑满三个合格交易日后自动生成。</div>"

    tl_rows = "".join(
        f"<li><time>{_esc(ev['at_syd'])}</time>"
        f"<span class=ic>{_KIND_ICON.get(ev['kind'], '·')}</span>"
        f"<span>{_esc(ev['text'])}</span></li>"
        for ev in d["timeline"]) or "<li><span class=muted>还没有任何动作;第一次动作后这里会一条条记。</span></li>"

    hb_rows = "".join(
        f"<span class='{'ok' if c['ok'] else 'bad'}' data-beat=\"{_esc(c.get('beat_at', ''))}\">"
        f"<i></i>{_esc(c['name'])} · <b data-age>{c['age_s']}</b> 秒前</span>"
        for c in health["components"]) or "<span class=muted>暂无心跳数据</span>"
    last_mail = health["last_mail"]

    today = hero["today_pnl_aud"]
    total = hero["total_pnl_aud"]
    html = f"""<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<meta http-equiv=refresh content="300">
<title>Alpha 驾驶舱</title>
<style>{_CSS}{_NAV_CSS}</style>
<div class=wrap>
<div class=top>
  <span class=logo>ALPHA</span>
  <span class="badge on">{_esc(d['mode_cn'])}</span>
  <span class="badge {'on' if mkt['open'] else 'off'}">{_esc(mkt['label'])}</span>
  <span class=clock data-clock>{_esc(d['meta']['updated_at_syd'])} 悉尼</span>
</div>
{_nav('/')}
<div class="banner {_esc(d['banner']['kind'])}">{_esc(d['banner']['text'])}</div>
<div class=grid>
<div class="card span2 {'gainbg' if total > 0 else ('lossbg' if total < 0 else '')}">
  <h2>管理资金净值(澳元口径,本金 {hero['baseline_aud']:,.0f})</h2>
  <div class=hero-num>{hero['equity_aud']:,.2f}</div>
  <div class=hero-sub>
    <span class="{_pnl_cls(total)}">累计 {_pnl_txt(total)}({hero['total_pnl_pct']:+.2f}%)</span>
    <span class="{_pnl_cls(today)}">今日 {_pnl_txt(today)}</span>
  </div>
  {_chart_block(d['curve'], hero['baseline_aud'])}
  <div class=kpis>
    <span>账户可用现金 <b>{hero['cash_usd']:,.2f} 美元</b></span>
    <span>持仓市值 <b>{hero['invested_usd']:,.2f} 美元</b></span>
    <span>授权上限 <b>{hero['authorized_usd']:,.2f} 美元</b></span>
    <span>敞口占上限 <b>{hero['exposure_pct']}%</b></span>
  </div>
  <div class=fxline>💱 {_esc(d['meta']['note_fx'])}</div>
  {f'<div class=verdict>💰 资金未全额到位:授权上限 {hero["authorized_usd"]:,.2f} 美元,账户实际可动用 {hero["funded_usd"]:,.2f} 美元,缺口 {hero["funding_gap_usd"]:,.2f} 美元。系统按<b>实际到位资金</b>下单与计算盈亏,绝不按授权额度虚报。</div>' if hero.get('funded_known') and hero['funding_gap_usd'] > 0.01 else ''}
  {'' if hero.get('funded_known') else '<div class=verdict>⚠️ 暂时读不到券商真实购买力,以下金额按授权额度显示(如实标注,非账户实有)。</div>'}
  {_progress_bar(d['progress'])}
</div>
<div class=card>
  <h2>现在持有</h2>
  {positions_block}
</div>
<div class=card>
  <h2>下一次决策</h2>
  <div class=big>{_esc(nd['at_syd'])}(周{_esc(nd['weekday_syd'])},悉尼)</div>
  <div class=muted style="margin-top:6px">{_esc(nd['kind'])}。其余时间只盯不动;到点有动作会出现在动作记录里,并邮件通知你。</div>
  <div class=muted style="margin-top:6px">{_esc(mkt['next'])}</div>
</div>
<div class=card>
  <h2>三日模拟盘考核(历史存档,已进入实盘)</h2>
  {exam_block}
</div>
<div class=card>
  <h2>系统健康</h2>
  <div class=hb>{hb_rows}</div>
  <div class=muted style="margin-top:10px">
    紧急刹车:{'<b style="color:#c0870f">已拉下</b>' if health['kill_switch'] else '待命(未触发)'} ·
    服务器:{_esc(health['server'])}<br>
    {f"最近邮件:{_esc(last_mail['at_syd'])} {_esc(last_mail['text'])}" if last_mail else '最近邮件:暂无'}
  </div>
</div>
<div class="card span2">
  <h2>动作记录(风控拦截也如实记)</h2>
  <ul class=tl>{tl_rows}</ul>
</div>
</div>
<footer class=muted>
{'· 这是<b>微实盘</b>:真实资金、真实订单,每一笔买卖都会原生出现在你的 moomoo 应用里;总敞口上限 3000 澳元,单笔不超 60%,失败关闭。<br>' if '微实盘' in d['mode_cn'] else '· 这是<b>模拟盘</b>:用券商模拟账户和真实行情演练,不动真钱;moomoo 手机应用里看不到这个模拟账户,本页就是唯一窗口。<br>'}
· 本页永远只读,没有任何下单能力;紧急停机用你手里的控制令牌。<br>
· 页面约每 30 秒自动更新;数据更新于 {_esc(d['meta']['updated_at_syd'])}(悉尼)。机器可读版:<a href="/api/overview">/api/overview</a>
</footer>
<details><summary>技术细节(给维护者看的)</summary><div class=muted>
{''.join(f"<div>{_esc(c['raw'])}:{_esc(c['status'])}({c['age_s']}秒前)</div>" for c in health['components']) or '无'}
{f"<div>历史估值缺收盘价已跳过:{_esc(','.join(d['curve_skipped_days']))}</div>" if d['curve_skipped_days'] else ''}
</div></details>
</div>
<script>{_JS}</script>"""
    return html
