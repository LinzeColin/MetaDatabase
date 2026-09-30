"""把日报数据渲染成单文件 HTML（内联 CSS/JS，无外部依赖，浅色/深色自适应，手机优先）。

第一屏只回答三件事：今天有没有新报告、数据截至何时、没有的话为什么。
失败时如实显示；旧报告会被标成「旧的」，不会冒充新的。
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import config

SYD = ZoneInfo(config.REPORT_TZ)
E = html.escape

CSS = """
:root{--bg:#f6f8fc;--card:#fff;--fg:#0f1b33;--mute:#5b677f;--line:#dbe3f0;--pri:#1d4ed8;--pri-soft:#e6eefc;
--home:#1d4ed8;--draw:#94a3b8;--away:#c2410c;--ok:#047857;--ok-bg:#e3f6ee;--warn:#92400e;--warn-bg:#fdf1d6;
--bad:#b91c1c;--bad-bg:#fde8e8;--low:#047857;--mid:#92400e;--high:#b91c1c;--r:12px}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0b1220;--card:#121c31;--fg:#e6ecf8;--mute:#9aa8c2;
--line:#243252;--pri:#7aa2ff;--pri-soft:#182a52;--home:#6d97ff;--draw:#64748b;--away:#f59e5b;--ok:#4ade9d;--ok-bg:#0f2e25;
--warn:#f8c66d;--warn-bg:#33270c;--bad:#ff8a8a;--bad-bg:#3a1414;--low:#4ade9d;--mid:#f8c66d;--high:#ff8a8a}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",
"Microsoft YaHei","Noto Sans CJK SC",system-ui,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:0 16px 56px}
header.top{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;justify-content:space-between;padding:18px 0 8px}
h1{font-size:20px;margin:0;letter-spacing:.2px}h2{font-size:18px;margin:34px 0 10px}h3{font-size:15px;margin:0 0 6px}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;background:var(--pri-soft);color:var(--pri);font-size:13px;font-weight:600}
.hero{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:18px;margin-top:8px}
.hero .state{display:flex;gap:10px;align-items:flex-start}
.dot{flex:none;width:12px;height:12px;border-radius:50%;margin-top:9px}
.hero.fresh .dot{background:var(--ok)}.hero.failed .dot,.hero.stale .dot{background:var(--bad)}.hero.archive .dot{background:var(--warn)}
.hero .big{font-size:22px;font-weight:700;line-height:1.35;margin:0}
.hero .sub{color:var(--mute);margin:4px 0 0}
.banner{margin-top:12px;padding:10px 12px;border-radius:8px;font-size:14px}
.banner.warn{background:var(--warn-bg);color:var(--warn)}.banner.bad{background:var(--bad-bg);color:var(--bad)}
.banner.ok{background:var(--ok-bg);color:var(--ok)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:14px}
.fact{border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.fact dt{font-size:12px;color:var(--mute);margin:0}.fact dd{margin:2px 0 0;font-weight:600;font-variant-numeric:tabular-nums}
.fact small{display:block;color:var(--mute);font-weight:400}
.strip{display:flex;gap:4px;margin-top:12px;flex-wrap:wrap}
.strip i{width:18px;height:18px;border-radius:4px;background:var(--line)}
.strip i.ok{background:var(--ok)}.strip i.fail{background:var(--bad)}.strip i.miss{background:var(--warn)}
.strip-label{font-size:12px;color:var(--mute);margin-top:6px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.chip{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12.5px;border:1px solid var(--line);color:var(--mute);background:transparent}
button.chip{cursor:pointer;font:inherit;font-size:13px;padding:4px 12px;min-height:32px;color:var(--fg)}
button.chip[aria-pressed=true]{background:var(--pri);color:#fff;border-color:var(--pri)}
button:focus-visible,summary:focus-visible,a:focus-visible{outline:2px solid var(--pri);outline-offset:2px}
.day{font-size:15px;font-weight:700;margin:20px 0 8px;color:var(--mute)}
.fx{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px;margin:0 0 10px}
.fx-top{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;font-size:13px;color:var(--mute)}
.fx-top time{margin-left:auto;font-variant-numeric:tabular-nums;color:var(--fg);font-weight:600}
.teams{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;margin:10px 0}
.team{font-weight:700;font-size:17px;line-height:1.3}.team small{display:block;font-weight:400;font-size:12px;color:var(--mute)}
.team.r{text-align:right}.vs{color:var(--mute);font-size:13px}
.bar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--line)}
.bar i{display:block;height:100%}.bar .h{background:var(--home)}.bar .d{background:var(--draw)}.bar .a{background:var(--away)}
.nums{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px;text-align:center;font-variant-numeric:tabular-nums}
.nums b{display:block;font-size:20px;line-height:1.2}.nums span{font-size:12px;color:var(--mute)}
.nums .h b{color:var(--home)}.nums .a b{color:var(--away)}
.mini{font-size:13px;color:var(--mute);margin-top:8px;font-variant-numeric:tabular-nums}
.risk{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;align-items:center}
.g-低{color:var(--low);border-color:var(--low)}.g-中{color:var(--mid);border-color:var(--mid)}.g-高{color:var(--high);border-color:var(--high)}
details{margin-top:8px}summary{cursor:pointer;font-size:13px;color:var(--pri);min-height:28px}
details ul{margin:6px 0 0;padding-left:20px;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--mute);font-weight:600}
.tw{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:4px 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}
.muted{color:var(--mute);font-size:14px}.hit{color:var(--ok);font-weight:700}.miss{color:var(--bad);font-weight:700}
.empty{padding:16px;border:1px dashed var(--line);border-radius:var(--r);color:var(--mute)}
footer{margin-top:40px;color:var(--mute);font-size:13px}
.fact.wide{grid-column:1/-1}
@media (max-width:520px){.facts{grid-template-columns:1fr 1fr;gap:8px}.fact{padding:8px 10px}.fact dd{font-size:15px}.fact small{font-size:12px}.hero{padding:14px}
.team{font-size:15px}.hero .big{font-size:19px}.fx-top time{margin-left:0;width:100%}}
@media (prefers-reduced-motion:no-preference){.bar i{transition:width .3s}}
"""

JS = """
(function(){
  var g=document.getElementById('gen');if(!g)return;
  var t=Date.parse(g.getAttribute('data-utc'));var lim=parseFloat(g.getAttribute('data-stale-h'))||30;
  var b=document.getElementById('stale');
  if(b&&t){var h=(Date.now()-t)/36e5;
    if(h>lim&&g.getAttribute('data-archive')!=='1'){b.hidden=false;
      b.textContent='注意：这份报告生成于约 '+Math.round(h)+' 小时前，超过 '+lim+' 小时没有更新。定时任务可能没跑成，请以「今天有没有新报告」一栏和下面的数据截至时间为准，不要把它当成最新。';}}
  document.querySelectorAll('[data-kick]').forEach(function(el){
    var k=Date.parse(el.getAttribute('data-kick'));if(!k)return;var m=Math.round((k-Date.now())/6e4);
    if(m<-180){el.textContent='已开球';return}if(m<0){el.textContent='进行中或刚结束';return}
    var d=Math.floor(m/1440),hh=Math.floor(m%1440/60);
    el.textContent='距开球 '+(d?d+' 天 ':'')+hh+' 小时'+(d?'':' '+(m%60)+' 分');});
  var btns=document.querySelectorAll('button[data-comp]');
  btns.forEach(function(bt){bt.addEventListener('click',function(){
    btns.forEach(function(x){x.setAttribute('aria-pressed',x===bt?'true':'false')});
    var c=bt.getAttribute('data-comp');
    document.querySelectorAll('article.fx').forEach(function(a){a.hidden=!(c==='all'||a.getAttribute('data-comp')===c)});
    document.querySelectorAll('.daygroup').forEach(function(d){d.hidden=!d.querySelector('article.fx:not([hidden])')});});});
})();
"""


def _fmt_syd(iso_utc: str | None) -> str:
    if not iso_utc:
        return "—"
    dt = datetime.strptime(iso_utc[:19].rstrip("Z"), "%Y-%m-%dT%H:%M:%S" if len(iso_utc) > 17 else "%Y-%m-%dT%H:%M")
    return dt.replace(tzinfo=timezone.utc).astimezone(SYD).strftime("%Y-%m-%d %H:%M")


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _round_zh(r: str) -> str:
    m = re.match(r"^(?:League, )?Matchday (\d+)$", r.strip())
    return f"第 {m.group(1)} 轮" if m else r


def _team(t: dict, right: bool = False) -> str:
    zh, en = t.get("zh"), t["name"]
    main, sub = (zh, en) if zh else (en, "")
    small = f"<small>{E(sub)}</small>" if sub else ""
    return f'<div class="team{" r" if right else ""}">{E(main)}{small}</div>'


def _fixture(f: dict) -> str:
    p, iv = f["p"], f["interval"]
    h, d, a = round(p["home"] * 100), round(p["draw"] * 100), round(p["away"] * 100)
    d = max(0, 100 - h - a) if h + d + a != 100 else d
    time_txt = f["kickoff_syd"][11:16] if f["time_known"] else "时间待定"
    kick = f'data-kick="{E(f["kickoff_utc"])}"' if f.get("kickoff_utc") else ""
    flags = [x for x in f["risk"]["flags"] if x["code"] not in ("unmodelled",)]
    short = {"no_history": "无历史记录", "small_sample": "样本少", "short_rest": "休息短", "moved_league": "跨级别",
             "cross_league": "跨联赛", "wide_interval": "不确定度高", "heavy_favourite": "一边倒"}
    chips = "".join(f'<span class="chip">{E(short.get(x["code"], x["code"]))}</span>' for x in flags)
    lis = "".join(f"<li>{E(x['text'])}</li>" for x in f["risk"]["flags"])
    top = " / ".join(f'{s["score"]}（{_pct(s["p"])}）' for s in f["top_scores"])
    rnd = f'<span>{E(_round_zh(f["round"]))}</span>' if f.get("round") else ""

    def rng(k: str) -> str:
        lo, hi = iv[k]
        return f"区间 {lo * 100:.0f}–{hi * 100:.0f}%"

    aria = f"主胜 {h}%，平 {d}%，客胜 {a}%"
    st_h, st_a = f["home"].get("n_eff"), f["away"].get("n_eff")
    return f"""<article class="fx" data-comp="{E(f['comp'])}">
<div class="fx-top"><span class="pill">{E(f['comp_zh'])}</span>{rnd}<span {kick}></span><time>{E(f['syd_weekday'])} {E(time_txt)} 悉尼</time></div>
<div class="teams">{_team(f['home'])}<div class="vs">对</div>{_team(f['away'], True)}</div>
<div class="bar" role="img" aria-label="{aria}"><i class="h" style="width:{h}%"></i><i class="d" style="width:{d}%"></i><i class="a" style="width:{a}%"></i></div>
<div class="nums"><div class="h"><b>{h}%</b><span>主胜 · {rng('home')}</span></div><div><b>{d}%</b><span>平 · {rng('draw')}</span></div><div class="a"><b>{a}%</b><span>客胜 · {rng('away')}</span></div></div>
<div class="mini">预期进球 {f['exp_goals'][0]:.1f} : {f['exp_goals'][1]:.1f} · 大于 2.5 球 {_pct(f['p_over25'])} · 双方进球 {_pct(f['p_btts'])} · 最可能比分 {E(top)}</div>
<div class="risk"><span class="chip g-{E(f['risk']['grade'])}">风险 {E(f['risk']['grade'])}</span>{chips}</div>
<details><summary>风险提示与盘口对比</summary><ul>{lis}<li>盘口对比：{E(f['market']['note'])}。</li>
<li>模型样本量：主队加权约 {st_h} 场，客队约 {st_a} 场（越大越稳）。</li></ul></details>
</article>"""


def _fixtures(report: dict) -> str:
    fx = report["fixtures"]
    if not fx:
        return '<div class="empty">未来 14 天里，覆盖的赛事没有比赛。</div>'
    comps = sorted({(f["comp"], f["comp_zh"]) for f in fx}, key=lambda x: x[0])
    btns = '<button class="chip" type="button" data-comp="all" aria-pressed="true">全部 %d 场</button>' % len(fx)
    for c, z in comps:
        n = sum(1 for f in fx if f["comp"] == c)
        btns += f'<button class="chip" type="button" data-comp="{E(c)}" aria-pressed="false">{E(z)} {n}</button>'
    out = [f'<div class="chips" role="group" aria-label="按赛事筛选">{btns}</div>']
    days: dict[str, list[dict]] = {}
    for f in fx:
        days.setdefault(f["syd_date"], []).append(f)
    for day, items in days.items():
        wd, ahead = items[0]["syd_weekday"], items[0]["days_ahead"]
        rel = "今天" if ahead == 0 else ("明天" if ahead == 1 else f"{ahead} 天后")
        out.append(f'<div class="daygroup"><div class="day">{E(day)} {E(wd)}（悉尼）· {rel} · {len(items)} 场</div>'
                   + "".join(_fixture(f) for f in items) + "</div>")
    return "".join(out)


def _recent(report: dict) -> str:
    rows = report["recent_results"]
    if not rows:
        return '<div class="empty">最近没有已收录的赛果。</div>'
    names = ["主胜", "平", "客胜"]
    body = ""
    for r in rows[:40]:
        if r["predicted"]:
            pr = r["predicted"]
            mark = ('<span class="hit">命中</span>' if r["hit"] else '<span class="miss">未中</span>')
            pred = f"{_pct(pr[0])} / {_pct(pr[1])} / {_pct(pr[2])}　{mark}"
        else:
            pred = '<span class="muted">当时没有赛前预测（开球后才收录或系统尚未运行）</span>'
        body += (f"<tr><td>{E(r['date'])}</td><td>{E(r['comp_zh'])}</td><td>{E(r['home'])} {r['score'][0]}–{r['score'][1]} "
                 f"{E(r['away'])}</td><td>{names[r['outcome']]}</td><td>{pred}</td></tr>")
    return ('<div class="tw"><table><thead><tr><th>日期</th><th>赛事</th><th>比分</th><th>结果</th>'
            f"<th>赛前预测 主/平/客</th></tr></thead><tbody>{body}</tbody></table></div>")


def _scorecard(report: dict) -> str:
    bt, lt = report.get("backtest") or {}, report.get("live_track") or {}
    parts = []
    if bt.get("n"):
        gain, se = bt["logloss_gain"], bt["logloss_gain_se"]
        cal = "".join(f"<tr><td>{E(c['bin'])}</td><td>{c['n']}</td><td>{_pct(c['predicted'])}</td><td>{_pct(c['actual'])}</td></tr>"
                      for c in bt["calibration"])
        parts.append(f"""<div class="card"><h3>回测：拿过去的比赛考模型</h3>
<p class="muted">每隔 {config.BACKTEST_STEP_DAYS} 天设一个截止日，只用截止日之前的数据拟合，再预测其后已经踢完的比赛；共 {bt['n']} 场（近 {bt['window_days']} 天，覆盖赛事）。
对照基线 = 什么都不看、只按该赛事历史主胜/平/客胜频率给概率。</p>
<table><tbody><tr><th>对数损失（越低越好）</th><td>模型 {bt['logloss_model']:.3f} ／ 基线 {bt['logloss_base']:.3f}</td></tr>
<tr><th>Brier 分数（越低越好）</th><td>模型 {bt['brier_model']:.3f} ／ 基线 {bt['brier_base']:.3f}</td></tr>
<tr><th>模型比基线好多少</th><td>对数损失每场少 {gain:.3f}（标准误 {se:.3f}，约 {gain / se if se else 0:.1f} 倍）</td></tr>
<tr><th>最可能结果命中率</th><td>{_pct(bt['accuracy'])}</td></tr></tbody></table>
<details><summary>校准表：说 X% 的事，实际发生了多少</summary><table><thead><tr><th>预测档</th><th>样本</th><th>平均预测</th><th>实际发生</th></tr></thead><tbody>{cal}</tbody></table></details></div>""")
    if lt.get("n"):
        parts.append(f"""<div class="card"><h3>实战：每天真实发出去的预测，事后对不对</h3>
<table><tbody><tr><th>已打分场数</th><td>{lt['n']}（另有 {lt['pending']} 场等赛果）</td></tr>
<tr><th>对数损失</th><td>模型 {lt['logloss']:.3f} ／ 基线 {lt['logloss_base']:.3f}</td></tr>
<tr><th>命中率</th><td>{_pct(lt['accuracy'])}</td></tr></tbody></table></div>""")
    else:
        parts.append(f"""<div class="card"><h3>实战：每天真实发出去的预测，事后对不对</h3>
<p class="muted">还没有已经踢完的赛前预测可打分（当前等赛果 {lt.get('pending', 0)} 场）。从第一份报告起每场赛前预测都会冻结存档，赛果收录后自动打分。上游赛果每周更新一次，所以打分会滞后几天。</p></div>""")
    return '<div class="grid2">' + "".join(parts) + "</div>"


def _strength(report: dict) -> str:
    out = []
    for c in report["coverage"]["covered"]:
        rows = report["strength"].get(c["code"], [])
        if not rows:
            continue
        body = "".join(f"<tr><td>{i}</td><td>{E(r['zh'] or r['name'])}</td><td>{r['rating']:+.2f}</td><td>{r['goals_for']:.2f}</td>"
                       f"<td>{r['goals_against']:.2f}</td><td>{r['n_eff']:.0f}</td></tr>" for i, r in enumerate(rows, 1))
        out.append(f"<details><summary>{E(c['zh'])}（{len(rows)} 队）</summary><div class=\"tw\"><table><thead><tr><th>#</th><th>球队</th>"
                   f"<th>实力值</th><th>预期进球</th><th>预期失球</th><th>样本</th></tr></thead><tbody>{body}</tbody></table></div></details>")
    return ('<p class="muted">实力值 = 对「本页覆盖球队的平均水平」、中立场、每场预期净胜球；由同一个模型估出，欧冠比赛把各国联赛连在一起。'
            "样本 = 时间加权后的有效场数。</p>" + "".join(out))


def _sources(report: dict) -> str:
    rows = ""
    for s in report["sources"]:
        state = "正常" if not s["failed"] else f"{len(s['failed'])} 个文件失败"
        extra = []
        if s["absent"]:
            extra.append(f"{s['absent']} 个文件上游尚未发布（不算故障）")
        if s["stale_cache"]:
            extra.append("使用了上次成功抓取的缓存：" + "、".join(E(x["name"]) for x in s["stale_cache"][:3]))
        if s["upstream_updated"]:
            extra.append("上游最近修订 " + E(_fmt_syd(s["upstream_updated"])) + "（悉尼）")
        rows += (f"<tr><td>{E(s['label'])}</td><td>{state}</td><td>{E(s['latest_result'] or '—')}</td>"
                 f"<td>{E(_fmt_syd(s['fetched_at']))}</td><td>{'；'.join(extra) or '—'}</td></tr>")
    rev = "".join(f"<tr><td>{E(r['name'])}</td><td><b>{E(r['verdict'])}</b></td><td>{E(r['why'])}</td></tr>"
                  for r in report["source_review"])
    cov = "".join(f"<li><b>{E(c['zh'])}</b>：{E(c['why'])}</li>" for c in report["coverage"]["covered"])
    tr = "、".join(E(c["zh"]) for c in report["coverage"]["training_only"])
    nc = "".join(f"<li><b>{E(c['zh'])}</b>：{E(c['why'])}</li>" for c in report["coverage"]["not_covered"])
    return f"""<h3>数据新鲜度</h3><div class="tw"><table><thead><tr><th>来源</th><th>状态</th><th>最新赛果日</th><th>本次抓取（悉尼）</th><th>备注</th></tr></thead><tbody>{rows}</tbody></table></div>
<h3 style="margin-top:16px">覆盖哪些赛事、为什么</h3><ul>{cov}</ul>
<p class="muted">只用来估计球队实力、不出预测：{tr}（让刚升级的球队和欧冠里的外围球队有历史可依）。</p>
<h3>没有覆盖</h3><ul>{nc}</ul>
<h3>数据源合规审查（2026-09-30 实测）</h3><div class="tw"><table><thead><tr><th>来源</th><th>结论</th><th>依据</th></tr></thead><tbody>{rev}</tbody></table></div>"""


def render(report: dict, status: dict, *, archive: bool = False) -> str:
    today = status.get("today") or report["report_date"]
    ok = status.get("ok", True)
    is_today = report["report_date"] == today
    refresh_failed_but_fresh = (not ok) and is_today and status.get("fresh_today") and not archive
    if refresh_failed_but_fresh:
        ok = True
    if archive:
        cls, big = "archive", f"这是 {report['report_date']} 的存档报告"
        sub = "存档只用于回看当时的预测，赛程与概率不再更新。最新报告见首页。"
    elif ok and is_today:
        cls, big = "fresh", "今天的新报告已生成"
        sub = f"报告日 {report['report_date']}（悉尼）。每天两次自动生成，无人值守。"
    else:
        cls, big = "failed", "今天没有新报告"
        why = status.get("error") or "最近一次运行没有产出新报告"
        sub = f"原因：{why}。下面显示的是 {report['report_date']} 的旧报告，赛程和概率可能已过时，不要当成最新。"
    banners = ""
    if refresh_failed_but_fresh:
        banners += f'<div class="banner warn">最近一次刷新失败（{E(status.get("error") or "未知原因")}），下面沿用的是今天早些时候成功生成的报告。</div>'
    for d in status.get("degraded", []):
        banners += f'<div class="banner warn">{E(d)}</div>'
    if status.get("missed_days"):
        banners += ('<div class="banner warn">最近缺跑的日期：' + "、".join(E(x) for x in status["missed_days"][-7:]) +
                    "。缺的天数不会补发当天的「赛前预测」（那会变成事后诸葛），下一次运行会直接覆盖所有未来赛程，赛果到了自动打分。</div>")

    fx = report["fixtures"]
    nxt = fx[0] if fx else None
    if report["matches_today"]:
        today_line = f"今天（悉尼）有 {report['matches_today']} 场覆盖赛事的比赛"
    else:
        today_line = "今天（悉尼）覆盖的赛事没有比赛"
    nxt_txt = "未来 14 天没有"
    if nxt:
        nm = f"{nxt['home'].get('zh') or nxt['home']['name']} 对 {nxt['away'].get('zh') or nxt['away']['name']}"
        nxt_txt = (f"{nxt['kickoff_syd'][5:10]} {nxt['syd_weekday']} {nxt['kickoff_syd'][11:16] if nxt['time_known'] else '时间待定'}"
                   f"<small>{E(nxt['comp_zh'])}：{E(nm)}</small>")
    if not report["matches_today"] and nxt and nxt["days_ahead"] >= 3:
        banners += (f'<div class="banner ok">这不是系统坏了：覆盖的赛事最近没有比赛（通常是国际比赛日/赛程空窗），'
                    f"下一个比赛日在 {nxt['days_ahead']} 天后。报告照常生成，先给出赛前预测。</div>")

    lr = report.get("latest_result_by_comp", {})
    by_date: dict[str, list[str]] = {}
    for k, v in lr.items():
        by_date.setdefault(v[5:], []).append(k)
    lr_txt = "；".join(f"{'、'.join(ks)} {d}" for d, ks in sorted(by_date.items(), reverse=True)) or "—"
    src = {s["id"]: s for s in report["sources"]}
    up = src.get("wikipedia-cl", {}).get("upstream_updated")
    facts = f"""<dl class="facts">
<div class="fact"><dt>报告日（悉尼）</dt><dd>{E(report['report_date'])}<small>生成于 {E(_fmt_syd(report['generated_at']))}</small></dd></div>
<div class="fact"><dt>今天有没有新报告</dt><dd>{'有' if (ok and is_today and not archive) else ('存档' if archive else '没有')}<small>{E(today_line)}</small></dd></div>
<div class="fact wide"><dt>数据截至（最新已收录赛果）</dt><dd>{E(report['newest_result'] or '—')}<small>{E(lr_txt)}；联赛数据每周更新一次，赛果最多滞后约一周{'；欧冠上游修订 ' + E(_fmt_syd(up)) if up else ''}</small></dd></div>
<div class="fact"><dt>下一场</dt><dd>{nxt_txt}<small data-kick="{E(nxt['kickoff_utc'] or '')}"></small></dd></div>
</dl>""" if nxt else f"""<dl class="facts">
<div class="fact"><dt>报告日（悉尼）</dt><dd>{E(report['report_date'])}<small>生成于 {E(_fmt_syd(report['generated_at']))}</small></dd></div>
<div class="fact"><dt>今天有没有新报告</dt><dd>{'有' if (ok and is_today and not archive) else ('存档' if archive else '没有')}<small>{E(today_line)}</small></dd></div>
<div class="fact wide"><dt>数据截至（最新已收录赛果）</dt><dd>{E(report['newest_result'] or '—')}<small>{E(lr_txt)}</small></dd></div>
<div class="fact"><dt>下一场</dt><dd>{nxt_txt}</dd></div></dl>"""

    strip = "".join(f'<i class="{E(r["state"])}" title="{E(r["date"])}：{E(r["label"])}"></i>' for r in status.get("strip", []))
    strip_html = (f'<div class="strip" aria-hidden="true">{strip}</div><div class="strip-label">最近 14 天运行记录：绿=成功，红=失败，黄=缺跑，灰=更早/无记录</div>'
                  if strip else "")

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="robots" content="noindex">
<title>FIFA 足球研究日报</title><style>{CSS}</style></head>
<body><div class="wrap">
<header class="top"><h1>FIFA 足球研究日报</h1><span class="pill">只研究 · 不下注 · 零付费</span></header>
<section class="hero {cls}" aria-live="polite">
<div class="state"><span class="dot"></span><div><p class="big">{E(big)}</p><p class="sub">{E(sub)}</p></div></div>
<div id="stale" class="banner bad" hidden></div>{banners}{facts}{strip_html}
<span id="gen" data-utc="{E(report['generated_at'])}" data-stale-h="{config.STALE_AFTER_HOURS}" data-archive="{1 if archive else 0}" hidden></span>
</section>
<h2>未来 14 天的比赛与模型概率</h2>
<p class="muted">概率来自带时间衰减的泊松进球模型；每个概率下面的「区间」是参数不确定度的 10%–90% 范围。
时间为悉尼时间（自动处理夏令时切换）。</p>
{_fixtures(report)}
<h2>盘口对比</h2>
<div class="empty"><b>暂无合法盘口源。</b>唯一免费的赔率数据集禁止自动化访问，其他要么要注册 key、要么是 TAB 官网（被判定拒绝 AI 受控访问，按硬边界失败关闭）。
所以本页不做盘口对比，也不计算期望值、凯利比例和任何投注金额。详见页尾的数据源审查。</div>
<h2>最近赛果与模型当时怎么说</h2>
{_recent(report)}
{('<p class="muted">上游还没收录这些已开球的比赛赛果：' + "；".join(E(f"{p['date']} {p['comp_zh']} {p['home']} 对 {p['away']}") for p in report["pending_results"][:12]) + "</p>") if report["pending_results"] else ""}
<h2>模型成绩单</h2>
{_scorecard(report)}
<h2>实力榜</h2>
{_strength(report)}
<h2>覆盖范围与数据源</h2>
{_sources(report)}
<footer>
<p><b>硬边界</b>：只研究，不下注；不点赔率、不改投注单、不绕过任何网站的访问控制（TAB 公共盘口保持失败关闭）；零付费、不注册账号。
本页内容不构成投注建议；模型看不到伤病、首发、天气和动机。</p>
<p>数据：openfootball（CC0）、Wikipedia（CC BY-SA 4.0，页面：2026–27 UEFA Champions League league phase）。
模型 {E(report['model_version'])}，训练 {report['model']['n_matches']} 场，时间半衰期 {report['model']['half_life_days']:.0f} 天，主场优势系数 {report['model']['home_advantage']}。</p>
<p>机器可读：<a href="status.json">status.json</a> · <a href="latest.json">latest.json</a> · 代码：仓库 LinzeColin/MetaDatabase 的 FIFA/daily-research。</p>
</footer></div><script>{JS}</script></body></html>"""


def render_empty(status: dict) -> str:
    """从没成功生成过任何报告时的页面：只如实说明状态。"""
    why = status.get("error") or "还没有成功生成过报告"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="robots" content="noindex"><title>FIFA 足球研究日报</title><style>{CSS}</style></head>
<body><div class="wrap"><header class="top"><h1>FIFA 足球研究日报</h1><span class="pill">只研究 · 不下注 · 零付费</span></header>
<section class="hero failed"><div class="state"><span class="dot"></span><div><p class="big">今天没有新报告</p>
<p class="sub">原因：{E(why)}。目前还没有任何一份成功生成的报告可以显示。</p></div></div></section></div></body></html>"""
