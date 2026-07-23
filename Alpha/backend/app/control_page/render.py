"""看盘页 HTML 渲染(纯函数:overview dict -> HTML 字符串)。

设计基准来自公开竞品反向分析(2026-07-23 调研):
- Ghostfolio:英雄数字(总净值+涨跌)压顶 + 一条主净值曲线;
- FreqUI(freqtrade):机器人运维面板 = 状态徽章 + 持仓盈亏 + 动作流水;
- moomoo/futu:持仓行(现价/成本/市值/浮动盈亏)+ 红涨绿跌(中国惯例);
- TradingView:深海军蓝底 + 等宽数字排版。
本页只读、公开(owner 裁定)、全中文人话、悉尼时间、无任何外链资源。
涨跌色遵循 moomoo 中国惯例:红涨绿跌,并叠加 +/− 与 ▲▼ 双通道防歧义。
"""

from __future__ import annotations

import html as _html

_CSS = """
*{box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;margin:0;
  background:#0a0e17;color:#e8edf4;font-variant-numeric:tabular-nums}
a{color:#e3c06b;text-decoration:none}
.wrap{max-width:980px;margin:0 auto;padding:14px 14px 40px}
.top{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:6px 2px 12px}
.logo{font-weight:800;font-size:20px;letter-spacing:2px;color:#e3c06b}
.badge{font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid #2a3348;color:#aeb7c7}
.badge.on{border-color:#265c40;color:#3dd68c}
.badge.off{border-color:#3a4258;color:#8a93a5}
.clock{margin-left:auto;font-size:12px;color:#8a93a5}
.banner{padding:12px 16px;border-radius:12px;font-size:15px;font-weight:600;margin-bottom:12px}
.banner.ok{background:#0d2b1c;border:1px solid #1d5c3c}
.banner.halted{background:#3a2a05;border:1px solid #7a5a10}
.banner.warn{background:#3a1414;border:1px solid #7a2a2a}
.grid{display:grid;gap:12px;grid-template-columns:1fr}
@media(min-width:840px){.grid{grid-template-columns:1fr 1fr}.span2{grid-column:1/-1}}
.card{background:#111726;border:1px solid #1e2637;border-radius:14px;padding:14px 16px}
.card h2{font-size:13px;color:#8a93a5;margin:0 0 10px;font-weight:500;letter-spacing:1px}
.hero-num{font-size:38px;font-weight:800;letter-spacing:0.5px;line-height:1.1}
.hero-sub{display:flex;gap:18px;flex-wrap:wrap;margin-top:6px;font-size:14px}
.up{color:#e5484d}.dn{color:#30a46c}.flat{color:#8a93a5}
.kpis{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;font-size:12.5px;color:#8a93a5}
.kpis b{color:#cfd6e2;font-weight:600}
.expo{height:8px;border-radius:99px;background:#1a2233;margin-top:10px;overflow:hidden}
.expo>i{display:block;height:100%;background:linear-gradient(90deg,#e3c06b,#c99b3f)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{color:#67718a;font-weight:500;font-size:11.5px;text-align:left;padding:2px 6px 8px}
td{border-top:1px solid #1a2233;padding:9px 6px;vertical-align:top}
.num{text-align:right}th.num{text-align:right}
.sym{font-weight:700}.symcn{color:#8a93a5;font-size:11.5px}
.pnl{font-weight:700}
.lights{display:grid;gap:8px}
.light{display:flex;gap:10px;align-items:flex-start;font-size:13.5px}
.dot{width:10px;height:10px;border-radius:99px;margin-top:4px;flex:none}
.dot.g{background:#3dd68c;box-shadow:0 0 8px #3dd68c66}
.dot.r{background:#e5484d;box-shadow:0 0 8px #e5484d66}
.light small{display:block;color:#8a93a5;font-size:11.5px;margin-top:1px}
.verdict{margin-top:10px;padding:9px 12px;border-radius:10px;font-size:13px;
  background:#1a2233;color:#cfd6e2}
.tl{list-style:none;margin:0;padding:0;font-size:13.5px}
.tl li{display:flex;gap:10px;padding:8px 0;border-top:1px solid #1a2233}
.tl li:first-child{border-top:0}
.tl time{color:#67718a;font-size:12px;white-space:nowrap;padding-top:1px}
.tl .ic{flex:none}
.hb{display:flex;gap:8px;flex-wrap:wrap}
.hb span{font-size:12px;padding:4px 10px;border-radius:8px;background:#1a2233;color:#aeb7c7}
.hb i{display:inline-block;width:7px;height:7px;border-radius:99px;margin-right:6px}
.hb .ok i{background:#3dd68c}.hb .bad i{background:#e5484d}
.muted{color:#8a93a5;font-size:12px;line-height:1.7}
.big{font-size:20px;font-weight:700}
details{margin-top:16px}summary{color:#4a5568;font-size:11px;cursor:pointer}
footer{margin-top:16px}
.chart{width:100%;height:auto;display:block;margin-top:8px}
"""

_JS = """
function tick(){var el=document.querySelector('[data-clock]');if(el){
  el.textContent=new Intl.DateTimeFormat('zh-CN',{timeZone:'Australia/Sydney',
  month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})
  .format(new Date())+' 悉尼';}}
setInterval(tick,1000);tick();
setInterval(async function(){try{
  var r=await fetch(location.pathname,{cache:'no-store'});
  if(!r.ok)return;var t=await r.text();
  var d=new DOMParser().parseFromString(t,'text/html');
  if(d.querySelector('.wrap'))document.body.replaceChild(d.querySelector('.wrap'),document.querySelector('.wrap'));
  tick();
}catch(e){}},30000);
"""


def _esc(x) -> str:
    return _html.escape(str(x), quote=True)


def _pnl_cls(v: float) -> str:
    return "up" if v > 0 else ("dn" if v < 0 else "flat")


def _pnl_txt(v: float, suffix: str = "") -> str:
    arrow = "▲" if v > 0 else ("▼" if v < 0 else "")
    return f"{arrow}{v:+,.2f}{suffix}" if v else f"0.00{suffix}"


def _svg_curve(curve: list[dict], capital: float) -> str:
    """净值曲线:金色主线+渐变面积+本金虚线。点少也画(如实反映样本量)。"""
    if not curve:
        return ""
    w, h, pad = 640, 170, 14
    ys = [p["equity_aud"] for p in curve] + [capital]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1.0
    lo -= span * 0.25
    hi += span * 0.25
    n = len(curve)

    def px(idx):
        return pad + (w - 2 * pad) * (idx / (n - 1) if n > 1 else 0.5)

    def py(v):
        return pad + (h - 2 * pad) * (1 - (v - lo) / (hi - lo))

    pts = [(px(i), py(p["equity_aud"])) for i, p in enumerate(curve)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{h - pad} " + line + f" {pts[-1][0]:.1f},{h - pad}"
    ticks = "".join(
        f'<text x="{px(i):.0f}" y="{h - 1}" font-size="9" fill="#67718a" '
        f'text-anchor="middle">{p["date"][5:]}{"·实时" if p.get("live") else ""}</text>'
        for i, p in enumerate(curve) if n <= 10 or i % max(1, n // 8) == 0 or i == n - 1)
    base_y = py(capital)
    last = curve[-1]["equity_aud"]
    return f"""<svg class="chart" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="净值曲线">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#e3c06b" stop-opacity="0.32"/>
<stop offset="1" stop-color="#e3c06b" stop-opacity="0"/></linearGradient></defs>
<line x1="{pad}" y1="{base_y:.1f}" x2="{w - pad}" y2="{base_y:.1f}" stroke="#2a3348" stroke-dasharray="4 4"/>
<text x="{w - pad}" y="{base_y - 4:.1f}" font-size="9" fill="#67718a" text-anchor="end">本金 {capital:,.0f} 澳元</text>
<polygon points="{area}" fill="url(#g)"/>
<polyline points="{line}" fill="none" stroke="#e3c06b" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5" fill="#e3c06b"/>
<text x="{pts[-1][0] - 6:.1f}" y="{pts[-1][1] - 8:.1f}" font-size="10" fill="#e8edf4" text-anchor="end">{last:,.2f}</text>
{ticks}</svg>"""


_KIND_ICON = {"fill": "✅", "order": "📝", "block": "🛡️", "mail": "✉️"}

_NAV_CSS = """
.nav{display:flex;gap:6px;margin:0 0 12px;flex-wrap:wrap}
.nav a{font-size:13px;padding:7px 14px;border-radius:10px;color:#aeb7c7;
  border:1px solid #1e2637;background:#111726}
.nav a.on{color:#0a0e17;background:#e3c06b;border-color:#e3c06b;font-weight:700}
.ok-badge{color:#3dd68c}.bad-badge{color:#e5484d}
.pill{font-size:11.5px;padding:2px 9px;border-radius:99px;border:1px solid #2a3348;color:#aeb7c7;white-space:nowrap}
.pill.auto{border-color:#265c40;color:#3dd68c}
.pill.manual{border-color:#7a5a10;color:#e3c06b}
.pill.fault{border-color:#7a2a2a;color:#e5484d}
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


def render_strategy_html(d: dict) -> str:
    ch = d["champion"]
    limits = "".join(f"<li>{_esc(x)}</li>" for x in d["hard_limits"])
    gates = "".join(
        f"<div class=light><i class='dot g'></i><div><b>{_esc(g['name'])}</b>"
        f"<small>{_esc(g['rule'])}</small></div></div>"
        for g in d["gates"])
    research = "".join(
        f"<tr><td><b>{_esc(r['name'])}</b></td><td>{_esc(r['result'])}</td>"
        f"<td class=symcn>{_esc(r['verdict'])}</td></tr>"
        for r in d["research"])
    body = f"""
<div class=grid>
<div class="card span2"><h2>当前生产策略</h2>
<div class=big>{_esc(ch['name_cn'])}</div>
<div class=muted style="margin-top:8px;line-height:1.8">
<b>怎么赚钱:</b>{_esc(ch['logic_cn'])}<br>
<b>节拍:</b>{_esc(ch['cadence'])}<br>
<b>持仓范围:</b>{_esc(ch['universe'])}<br>
<b>历史成绩:</b>{_esc(ch['record'])}</div></div>
<div class=card><h2>硬风控约束(写死在代码与契约,页面无权改)</h2>
<ul class=muted style="line-height:2;margin:0;padding-left:18px">{limits}</ul></div>
<div class=card><h2>晋级实盘的四道门(实时读契约配置)</h2><div class=lights>{gates}</div></div>
<div class="card span2"><h2>候选策略研究史(同一把尺子,全部证据公开可复验)</h2>
<table><tr><th>结构</th><th>滚动前推成绩</th><th>裁定</th></tr>{research}</table>
<div class=muted style="margin-top:10px">{_esc(d['research_note'])}</div></div>
</div>
<footer class=muted>· {_esc(d['honesty_note'])}<br>
· 回测不代表未来收益;本系统不向任何人承诺回报。更新于 {_esc(d['updated_at_syd'])}(悉尼)。</footer>"""
    return _shell("Alpha 投资策略", "/strategy", body)


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
        f"<span class='{'ok' if c['ok'] else 'bad'}'><i></i>{_esc(c['name'])}"
        f" · {c['age_s']}秒前</span>"
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
<div class="card span2">
  <h2>管理资金净值(澳元口径,本金 {hero['capital_aud']:,.0f})</h2>
  <div class=hero-num>{hero['equity_aud']:,.2f}</div>
  <div class=hero-sub>
    <span class="{_pnl_cls(total)}">累计 {_pnl_txt(total)}({hero['total_pnl_pct']:+.2f}%)</span>
    <span class="{_pnl_cls(today)}">今日 {_pnl_txt(today)}</span>
  </div>
  {_svg_curve(d['curve'], hero['capital_aud'])}
  <div class=kpis>
    <span>现金 <b>{hero['cash_usd']:,.2f} 美元</b></span>
    <span>持仓市值 <b>{hero['invested_usd']:,.2f} 美元</b></span>
    <span>敞口占上限 <b>{hero['exposure_pct']}%</b></span>
    <span>{_esc(d['meta']['note_fx'])}</span>
  </div>
  <div class=expo><i style="width:{min(100, hero['exposure_pct'])}%"></i></div>
</div>
<div class=card>
  <h2>现在持有</h2>
  {positions_block}
</div>
<div class=card>
  <h2>三日模拟盘考核</h2>
  {exam_block}
</div>
<div class=card>
  <h2>下一次决策</h2>
  <div class=big>{_esc(nd['at_syd'])}(周{_esc(nd['weekday_syd'])},悉尼)</div>
  <div class=muted style="margin-top:6px">{_esc(nd['kind'])}。其余时间只盯不动;到点有动作会出现在动作记录里,并邮件通知你。</div>
  <div class=muted style="margin-top:6px">{_esc(mkt['next'])}</div>
</div>
<div class=card>
  <h2>系统健康</h2>
  <div class=hb>{hb_rows}</div>
  <div class=muted style="margin-top:10px">
    紧急刹车:{'<b style="color:#f5a524">已拉下</b>' if health['kill_switch'] else '待命(未触发)'} ·
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
· 这是<b>{_esc(d['mode_cn'])}</b>:用券商模拟账户和真实行情演练,不动真钱;moomoo 手机应用里看不到这个模拟账户,本页就是唯一窗口。<br>
· 要动真钱必须:三日考核全绿 + 你的书面授权 + 实盘总开关打开,三道门缺一不可;本页永远只读,没有任何下单能力。<br>
· 页面约每 30 秒自动更新;数据更新于 {_esc(d['meta']['updated_at_syd'])}(悉尼)。机器可读版:<a href="/api/overview">/api/overview</a>
</footer>
<details><summary>技术细节(给维护者看的)</summary><div class=muted>
{''.join(f"<div>{_esc(c['raw'])}:{_esc(c['status'])}({c['age_s']}秒前)</div>" for c in health['components']) or '无'}
{f"<div>历史估值缺收盘价已跳过:{_esc(','.join(d['curve_skipped_days']))}</div>" if d['curve_skipped_days'] else ''}
</div></details>
</div>
<script>{_JS}</script>"""
    return html
