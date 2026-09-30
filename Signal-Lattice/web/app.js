const app=document.querySelector('#main');
const statusDot=document.querySelector('#status-dot');
const runtimeMode=document.querySelector('#runtime-mode');
// 空值统一显示「—」：页面上不允许出现 undefined / NaN / null 这些字面量。
const blank=value=>value===undefined||value===null||value===''||(typeof value==='number'&&!Number.isFinite(value));
const txt=value=>blank(value)?'—':String(value);
const pct=value=>blank(value)||!Number.isFinite(Number(value))?'—':`${(Number(value)*100).toFixed(1)}%`;
const num=(value,digits=2)=>blank(value)||!Number.isFinite(Number(value))?'—':Number(value).toFixed(digits);
const time=value=>{if(blank(value))return '—';const date=new Date(value);return Number.isNaN(date.getTime())?'—':date.toLocaleString('zh-CN',{hour12:false})};
const billions=value=>blank(value)||!Number.isFinite(Number(value))?'—':`${(Number(value)/1e8).toFixed(1)} 亿美元`;
const money=(value,currency)=>blank(value)||!Number.isFinite(Number(value))?'—':`${Number(value).toFixed(2)} ${currency||'USD'}`.trim();
const list=value=>Array.isArray(value)?value:[];
function node(tag,text,attrs={}){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;for(const [key,value] of Object.entries(attrs)){item.setAttribute(key,value)}return item}
// 一手原文链接只允许 SEC 的 https 地址；其它一律显示成纯文字，不生成可点击链接。
function secLink(url,label){if(typeof url==='string'&&url.startsWith('https://www.sec.gov/')){return node('a',label||url,{href:url,rel:'noreferrer noopener',target:'_blank'})}return node('span',label||'—')}
function panel(title,description){const section=node('section',undefined,{class:'panel section-block'});const header=node('header');header.append(node('div'));header.firstChild.append(node('h2',title));if(description)header.firstChild.append(node('p',description));section.append(header);return section}
function table(headers,rows){const wrap=node('div',undefined,{class:'table-wrap',tabindex:'0'});const tableElement=node('table');const head=node('thead');const headRow=node('tr');headers.forEach(value=>headRow.append(node('th',value)));head.append(headRow);tableElement.append(head);const body=node('tbody');rows.forEach(row=>{const tr=node('tr');row.forEach(value=>{const td=node('td');if(value instanceof Node){td.append(value)}else{td.textContent=txt(value)}tr.append(td)});body.append(tr)});tableElement.append(body);wrap.append(tableElement);return wrap}
function fact(term,value,note){const box=node('div');box.append(node('dt',term));box.append(node('dd',txt(value)));if(note)box.append(node('small',note));return box}
function plainList(items){const ul=node('ul',undefined,{class:'plain-list'});items.forEach(([label,value])=>{if(blank(value))return;const li=node('li');li.append(node('strong',`${label}：`));li.append(value instanceof Node?value:document.createTextNode(String(value)));ul.append(li)});return ul}
const BRANCH_NAMES={'equity-event-atlas':'事件航图','bottleneck-serenity-skill':'瓶颈','stock-commercial-opportunities':'商业机会','equity-foresight-signal':'股势前瞻','global-equity-lead-lag-atlas':'全球联动'};
const branchName=id=>BRANCH_NAMES[id]||txt(id);

function degradedSummary(report){
  const degraded=report.degraded_symbols||{};
  const symbols=Object.keys(degraded);
  if(!symbols.length)return null;
  return `本轮有 ${symbols.length} 只候选的实时报价没通过时效门：${symbols.join('、')}。它们本轮不参与发布判断，其它候选与结论不受影响。`;
}
function renderDegraded(report){
  const degraded=report.degraded_symbols||{};
  const section=panel('本轮报价没通过时效门的候选','逐只列出原因；这些报价不作为当前价格展示。');
  const rows=Object.entries(degraded).map(([symbol,findings])=>{const item=(report.instruments||{})[symbol]||{};return [symbol,item.name,list(findings).join('；')]});
  if(!rows.length)section.append(node('p','本轮所有候选与 IWM 的实时报价均通过时效门。'));
  else section.append(table(['代码','名称','未通过原因'],rows));
  return section;
}
function statusText(decision){
  if(decision.state==='RECOMMENDATION')return `${decision.action||'研究跟进（看多）'} ${txt(decision.primary_symbol)}`;
  if(decision.state==='NO_ACTION')return '本轮无建议（NO_ACTION）';
  return '数据链路不完整，不出结论';
}
function renderDecisionHero(report){
  const decision=report.decision||{};
  const section=node('section',undefined,{class:'hero panel',id:'decision','aria-labelledby':'decision-title'});
  const main=node('div',undefined,{class:'hero-main'});
  const kicker=node('div',undefined,{class:'hero-kicker'});
  kicker.append(node('span','实时运行',{class:'live-pill pass'}));
  kicker.append(node('span',`本轮 ${time(report.generated_at)}`));
  main.append(kicker);
  main.append(node('p','最终研究结论',{class:'eyebrow'}));
  main.append(node('h1',statusText(decision),{id:'decision-title','data-action':decision.action_code||'NONE'}));
  main.append(node('p',decision.state==='RECOMMENDATION'?`${txt(decision.primary_symbol)}｜${txt(decision.primary_name)}`:'—',{class:'decision-symbol'}));
  main.append(node('p',decision.rationale||report.message||'—',{class:'lead'}));
  const degradedNotice=degradedSummary(report);
  if(degradedNotice)main.append(node('p',`数据覆盖：${degradedNotice}`,{class:'lead hero-delay-notice'}));
  const chips=node('div',undefined,{class:'chips'});
  ['每 60 秒运行','Agent 依赖 0','LLM Token 0','只做研究、不下单'].forEach(x=>chips.append(node('span',x)));
  main.append(chips);
  section.append(main);
  const support=decision.support||{};
  const invalidation=decision.invalidation||{};
  const facts=node('dl',undefined,{class:'decision-facts'});
  facts.append(fact('当前价格',money(decision.price),decision.quote_source_time?`来源时间 ${time(decision.quote_source_time)}`:''));
  facts.append(fact('市值',billions(decision.market_cap_usd)));
  facts.append(fact('支持度合计',blank(support.total)?'—':`${num(support.total)} / 门槛 ${num(support.threshold,1)}`,decision.weights_mode==='COLD_START_EQUAL'?'分支权重：记分簿样本不足，等权':'分支权重：按前向命中率'));
  facts.append(fact('失效条件',invalidation.status_text||'—',invalidation.published_at?`发布于 ${time(invalidation.published_at)}`:''));
  facts.append(fact('研究快照',report.data_cutoff,(report.research||{}).research_age_hours!==undefined?`${num((report.research||{}).research_age_hours,1)} 小时前确认`:''));
  facts.append(fact('下一轮','约 60 秒后'));
  section.append(facts);
  return section;
}
function renderCycle(report){
  const receipts=list(report.receipts);
  const passed=receipts.filter(r=>r.status==='PASS').length;
  const research=report.research||{};
  const accounting=report.collection_request_accounting||{};
  const grid=node('section',undefined,{class:'metric-grid',id:'cycle','aria-label':'本轮链路状态'});
  const card=(label,value,note)=>{const a=node('article',undefined,{class:'metric'});a.append(node('span',label));a.append(node('strong',txt(value)));a.append(node('small',note));return a};
  grid.append(card('分支收据',`${passed}/${receipts.length||5}`,'状态为 PASS 的分支数（ABSTAIN 也是正常出结论）'));
  grid.append(card('候选',list(report.candidates).length,'研究层 shortlist，最多 60 只'));
  grid.append(card('研究快照',research.snapshot_sha256?String(research.snapshot_sha256).slice(0,12):'—','所有分支收据读的是同一份'));
  grid.append(card('本日采集轮次',accounting.daily_round_count,`上限 ${txt(accounting.maximum_provider_requests_per_day)} 次请求/日`));
  return grid;
}
function conditionRow(condition){
  const state={OK:'未触发',TRIGGERED:'已触发',NOT_CHECKABLE:'暂无法核对',NOT_CHECKED:'尚未核对'}[condition.status]||txt(condition.status);
  return [condition.text,state,condition.detail];
}
function renderWhy(report){
  const decision=report.decision||{};
  const section=panel('为什么得出这个结论','每个支持分支一句话理由与 SEC 一手原文；失效条件在发布时写死，之后每轮自动核对。');
  section.setAttribute('id','evidence');
  section.append(plainList([['结论',decision.rationale],['支持度规则',decision.support_rule],['数据链',decision.state==='SYSTEM_BLOCKED'?decision.message:null]]));
  const reasons=list(decision.reasons);
  if(reasons.length){
    section.append(node('h3','支持它的分支与一手原文'));
    section.append(table(['分支','类型','理由','SEC 原文'],reasons.map(r=>[branchName(r.branch_id),r.kind==='PASS'?'PASS（1.0）':'排序支持（0.3）',r.sentence,secLink(r.link,'打开原文')])));
    const sources=list(decision.sources);
    if(sources.length){section.append(node('h3','一手原文清单'));section.append(table(['分支','日期','摘要','链接'],sources.map(s=>[branchName(s.branch_id),s.published_date,s.summary,secLink(s.url,'SEC 原文')])))}
  }
  const conflicts=list(decision.conflicts);
  section.append(node('h3','冲突（保留正反两面）'));
  section.append(conflicts.length?table(['类型','说明'],conflicts.map(c=>[c.kind==='VETO'?'一票否决':'其它分支的反对意见',c.text])):node('p','没有分支给出与该建议相反的结论。'));
  const invalidation=decision.invalidation;
  if(invalidation){
    section.append(node('h3',`失效条件：${txt(invalidation.status_text)}`));
    section.append(table(['条件','本轮核对','说明'],list(invalidation.conditions).map(conditionRow)));
    const unmonitored=list(invalidation.not_monitored);
    if(unmonitored.length)section.append(node('p',`暂未接入数据、无法自动核对：${unmonitored.map(x=>`${x.text}（${x.reason}）`).join('；')}`));
  }
  const invalidated=list(decision.invalidated_recommendations);
  if(invalidated.length){section.append(node('h3','已失效的历史建议'));section.append(table(['代码','发布时间','失效时间','触发的条件'],invalidated.map(x=>[x.symbol,time(x.published_at),time(x.invalidated_at),list(x.triggered).map(t=>t.detail||t.text).join('；')])))}
  const watch=list(decision.watchlist);
  if(watch.length){
    section.append(node('h3',decision.state==='NO_ACTION'?'观察名单（前 5）：差在哪一道门':'观察名单（前 5）'));
    section.append(table(['代码','名称','支持度','差在哪一道门','原文'],watch.map(w=>[w.symbol,w.name,num(w.support_total),w.sentence,list(w.links).length?secLink(w.links[0],'SEC 原文'):'—'])));
  }
  return section;
}
function renderBranches(report){
  const section=panel('分支独立结论与收据','每个分支在独立子进程里只读同一份不可变快照；下表是它们各自的收据。');
  section.setAttribute('id','skills');
  const rows=list(report.receipts).map(r=>[r.label||branchName(r.branch_id),r.status,`${txt((r.verdict_counts||{}).PASS)} / ${txt((r.verdict_counts||{}).ABSTAIN)} / ${txt((r.verdict_counts||{}).FAILED)}`,txt(r.snapshot_hash).slice(0,12),r.params_version,r.reason||'—']);
  section.append(table(['分支','收据状态','PASS / ABSTAIN / FAILED','快照 hash','参数版本','说明'],rows));
  const env=((report.decision||{}).market_environment)||{};
  if(env.regime)section.append(node('p',`全球联动只作市场环境输入（不选股）：${env.regime}。${txt(env.note)}`));
  return section;
}
function renderCandidates(report){
  const section=panel('候选比较','研究层 shortlist（最多 60 只）逐只过硬门：候选池、实时报价、流动性、一票否决、支持度。');
  section.setAttribute('id','candidates');
  const rows=list(report.candidates).map(c=>[c.rank,c.symbol,c.name,billions(c.market_cap_usd),money(c.price),num(c.support_total),list(c.support_branches).map(b=>`${b.label}${b.kind==='PASS'?' PASS':' 排序'}`).join('、')||'—',c.passes_all_gates?'全部通过':c.gate_summary]);
  if(!rows.length)section.append(node('p','本轮没有候选（研究层没有产出或数据链不完整）。'));
  else section.append(table(['#','代码','名称','市值','现价','支持度','支持它的分支','差在哪一道门'],rows));
  return section;
}
function ledgerBlock(ledger){
  const box=node('div');
  if(!ledger){box.append(node('p','前向记分簿还没有数据。'));return box}
  box.append(node('p',ledger.message||'—'));
  box.append(plainList([['起算日',ledger.inception_day],['已记录交易日',ledger.recorded_days],['其中建议 / NO_ACTION',`${txt(ledger.recommendation_days)} / ${txt(ledger.no_action_days)}`],['已结算（20 日 / 60 日）',`${txt((ledger.settled||{})['20'])} / ${txt((ledger.settled||{})['60'])}`],['说明',ledger.note]]));
  const horizons=ledger.horizons||{};
  const rows=Object.entries(horizons).filter(([,h])=>h.status==='SUFFICIENT').map(([k,h])=>[`${k} 日`,h.settled,pct(h.hit_rate),pct(h.mean_excess_vs_iwm),pct(h.median_excess_vs_iwm),pct(h.mean_excess_vs_control),pct(h.worst_excess_vs_iwm)]);
  if(rows.length)box.append(table(['持有期','已结算','命中率','相对 IWM 平均超额','中位超额','相对同档随机平均超额','最差一笔'],rows));
  const recent=list(ledger.recent);
  if(recent.length)box.append(table(['交易日','当日决策','代码','20 日已结算','60 日已结算'],recent.map(r=>[r.trading_day,r.state==='RECOMMENDATION'?'研究跟进（看多）':'NO_ACTION',r.symbol,r.settled_20?'是':'否',r.settled_60?'是':'否'])));
  return box;
}
function backtestBlock(bt){
  const box=node('div');
  const hub=((bt||{}).branches||{}).hub;
  const windows=hub&&hub.walk_forward?hub.walk_forward.windows:null;
  box.append(node('p',`中枢回测（时点正确、按月滚动、扣成本、含安慰剂）：样本外窗口 ${txt(windows)} / 门槛 ${txt(((bt||{}).method||{}).minimum_oos_windows_for_profitability)}。`));
  if(bt&&bt.why_not_published)box.append(node('p',`不公布收益数字：${bt.why_not_published}`));
  if(hub&&hub.stitched){const rows=Object.entries(hub.stitched).map(([k,v])=>[k,txt(v.windows),pct((v.excess_vs_iwm||{}).mean),pct((v.excess_vs_iwm||{}).hit_rate)]);box.append(table(['口径','窗口','平均净超额','命中率'],rows))}
  const assumptions=list(((bt||{}).method||{}).assumptions);
  if(assumptions.length){box.append(node('h3','回测假设与局限'));const ul=node('ul',undefined,{class:'plain-list'});assumptions.forEach(a=>ul.append(node('li',a)));box.append(ul)}
  return box;
}
function renderQuant(report){
  const section=panel('前向记分簿与回测','证据不足时不给收益数字：已结算样本 < 8 写「样本不足，暂不下结论」；回测样本外窗口 < 6 只公布窗口数。');
  section.setAttribute('id','quant');
  section.append(node('h3','前向记分簿（只追加、从上线日起算）'));
  section.append(ledgerBlock(report.ledger));
  section.append(node('h3','回测'));
  section.append(backtestBlock(report.backtest));
  return section;
}
function renderWeights(report){
  const weights=report.contribution_weights||{};
  const section=panel('分支权重','权重 = 前向记分簿里该分支已结算建议的命中率；样本不足 8 条用等权。权重上限 1.0，只会抬高门槛。');
  section.setAttribute('id','evolution');
  section.append(node('p',weights.formula||'—'));
  section.append(table(['分支','权重','模式','已结算样本','说明'],list(weights.branches).map(b=>[b.label||branchName(b.branch_id),num(b.weight),b.mode==='HIT_RATE'?'按命中率':'等权（冷启动）',b.sample_count,b.note])));
  return section;
}
function renderFreshness(report){
  const section=panel('报价来源时间','美股按交易时间口径判新鲜：开市看「来源时间 + TTL」且必须推进，休市不做推进检测。');
  const rows=Object.entries(report.quote_freshness||{}).filter(([symbol,item])=>symbol==='IWM'||item.status!=='FRESH'||item.advance_status==='FEED_STALLED').map(([symbol,item])=>[symbol,item.market_state,item.status,time(item.source_time),num(item.trading_age_seconds,0),item.advance_status]);
  const total=Object.keys(report.quote_freshness||{}).length;
  section.append(node('p',`共 ${total} 个报价（候选 + IWM）；下表只列 IWM 和未通过的。`));
  if(rows.length)section.append(table(['代码','市场状态','判定','来源时间','交易时间账龄(秒)','推进状态'],rows));
  return section;
}
function renderBlocked(report={}){
  app.setAttribute('aria-busy','false');app.replaceChildren();
  if(statusDot){statusDot.className='dot danger'}
  if(runtimeMode){runtimeMode.textContent=report.blocked_reason||report.state||'未就绪'}
  const decision=report.decision||{};
  const loopUnreachable=report.blocked_reason==='COLLECTION_LOOP_UNREACHABLE';
  const main=node('main',undefined,{id:'main-content',class:'blocked-page',tabindex:'-1'});
  main.append(node('p',decision.state||'SYSTEM_BLOCKED',{class:'eyebrow'}));
  main.append(node('h1',loopUnreachable?'采集循环失联，结论已过期':'数据链路不完整，不出结论',{id:'decision-title','data-action':decision.action_code||'SYSTEM_BLOCKED'}));
  main.append(node('p',report.message||decision.rationale||(loopUnreachable?'循环心跳或最新报告超过时效窗口，未复用旧结论。':'数据新鲜度门未通过，本轮不出结论。'),{class:'lead'}));
  const problems=list(((decision.details||{}).problems));
  if(problems.length)main.append(plainList([['具体原因',problems.join('；')]]));
  main.append(renderDegraded(report),renderFreshness(report));
  app.append(main);
}
function renderReady(report){
  app.setAttribute('aria-busy','false');
  app.replaceChildren();
  if(statusDot){statusDot.className='dot ok'}
  if(runtimeMode){runtimeMode.textContent=`${report.state}｜v${txt(report.application_version)}`}
  // 顺序就是阅读顺序：先给结论，再给依据，最后才是诊断。
  app.append(renderDecisionHero(report));
  app.append(renderCycle(report));
  app.append(renderWhy(report));
  app.append(renderBranches(report));
  app.append(renderCandidates(report));
  app.append(renderQuant(report));
  app.append(renderWeights(report));
  const lattice=panel('数据与时效','研究快照与实时报价的时效依据——支撑上面结论的原始记账。');
  lattice.setAttribute('id','lattice');
  const research=report.research||{};
  lattice.append(plainList([['研究快照日期',report.data_cutoff],['快照生成',time(research.snapshot_generated_at)],['研究层最后确认',time(research.research_checked_at)],['快照年龄（小时）',num(research.research_age_hours,1)],['过期上限（小时）',research.research_max_age_hours]]));
  app.append(lattice);
  app.append(renderDegraded(report));
  app.append(renderFreshness(report));
  const ops=panel('系统运行','无人保活，云端自动恢复。');
  ops.setAttribute('id','operations');
  const facts=node('dl',undefined,{class:'system-facts'});
  facts.append(fact('版本',report.application_version));
  facts.append(fact('本轮生成',time(report.generated_at)));
  facts.append(fact('报价观察',time(report.quote_observed_at)));
  facts.append(fact('自动交易','永久关闭'));
  ops.append(facts);
  app.append(ops);
}
async function refresh(){try{const response=await fetch('/api/v1/report/latest',{headers:{Accept:'application/json'},cache:'no-store'});const report=await response.json();if(!response.ok||report.state==='SYSTEM_BLOCKED'){renderBlocked(report);return}if(report.state==='DATA_READY'){renderReady(report);return}renderBlocked(report)}catch(_error){renderBlocked()}}
refresh();setInterval(refresh,30000);
