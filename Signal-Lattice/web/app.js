const app=document.querySelector('#main');
const statusDot=document.querySelector('#status-dot');
const runtimeMode=document.querySelector('#runtime-mode');
// 空值统一显示「—」：页面上不允许出现 undefined / NaN / null 这些字面量。
const blank=value=>value===undefined||value===null||value===''||(typeof value==='number'&&!Number.isFinite(value));
const txt=value=>blank(value)?'—':String(value);
const spct=value=>blank(value)||!Number.isFinite(Number(value))?'—':`${Number(value)>=0?'+':'\u2212'}${Math.abs(Number(value)*100).toFixed(1)}%`;
const pct=value=>blank(value)||!Number.isFinite(Number(value))?'—':`${(Number(value)*100).toFixed(1)}%`;
const num=(value,digits=2)=>blank(value)||!Number.isFinite(Number(value))?'—':Number(value).toFixed(digits);
const time=value=>{if(blank(value))return '—';const date=new Date(value);return Number.isNaN(date.getTime())?'—':date.toLocaleString('zh-CN',{hour12:false})};
const yi=value=>blank(value)||!Number.isFinite(Number(value))?'—':`${(Number(value)/1e8).toFixed(1)} 亿`;
const billions=value=>blank(value)||!Number.isFinite(Number(value))?'—':`${(Number(value)/1e8).toFixed(1)} 亿美元`;
const money=(value,currency)=>blank(value)||!Number.isFinite(Number(value))?'—':`${Number(value).toFixed(2)} ${currency||'USD'}`.trim();
const list=value=>Array.isArray(value)?value:[];
function node(tag,text,attrs={}){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;for(const [key,value] of Object.entries(attrs)){item.setAttribute(key,value)}return item}
// 一手原文链接只允许 SEC 的 https 地址；其它一律显示成纯文字，不生成可点击链接。
function secLink(url,label){if(typeof url==='string'&&url.startsWith('https://www.sec.gov/')){return node('a',label||url,{href:url,rel:'noreferrer noopener',target:'_blank'})}return node('span',label||'—')}
function panel(title,description){const section=node('section',undefined,{class:'panel section-block'});const header=node('header');header.append(node('div'));header.firstChild.append(node('h2',title));if(description)header.firstChild.append(node('p',description));section.append(header);return section}
function table(headers,rows,options={}){const wrap=node('div',undefined,{class:'table-wrap',tabindex:'0'});const tableElement=node('table');if(options.minWidth)tableElement.style.minWidth=`${options.minWidth}px`;const head=node('thead');const headRow=node('tr');headers.forEach(value=>headRow.append(node('th',value)));head.append(headRow);tableElement.append(head);const body=node('tbody');rows.forEach(row=>{const tr=node('tr');row.forEach((value,index)=>{const td=node('td',undefined,{'data-label':headers[index]||''});if(value instanceof Node){td.append(value)}else{td.textContent=txt(value)}tr.append(td)});body.append(tr)});tableElement.append(body);wrap.append(tableElement);return wrap}
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
  if(decision.state==='RECOMMENDATION')return decision.action||'研究跟进（看多）';
  if(decision.state==='NO_ACTION')return '本轮不给建议';
  return '数据链路不完整，不出结论';
}
const KIND_TEXT={PASS:'通过',RANK:'排序支持',FAILED:'不通过'};
function kindCell(kind){const label=KIND_TEXT[kind];if(!label)return '—';return node('span',label,{class:`cell ${kind==='PASS'?'pass':kind==='FAILED'?'blocked':'degraded'}`})}
function branchList(items){const parts=list(items).map(b=>`${b.label||branchName(b.branch_id)} ${KIND_TEXT[b.kind]||''}`.trim());return parts.length?parts.join(' + '):'—'}
function statusRow(pillText,pillClass,text){const row=node('div',undefined,{class:'status-row'});row.append(node('span',pillText,{class:`live-pill ${pillClass}`}));row.append(node('span',text,{class:'status-text'}));return row}
// 影子候选的前向成绩：样本 < 8 只写「样本不足」，不出收益数字（数字在后端就没有，这里只是不再去拼）。
function shadowRecord(ledger){
  const shadow=(ledger||{}).shadow;
  if(!shadow)return '前向成绩：还没有记录。';
  const settled=(shadow.settled||{})['20'];
  const h20=(shadow.horizons||{})['20']||{};
  if(shadow.sample_status==='SUFFICIENT'&&h20.status==='SUFFICIENT')return `前向成绩：已结算 ${txt(settled)} 条，命中率 ${pct(h20.hit_rate)}，20 日平均超额 ${spct(h20.mean_excess_vs_iwm)}（相对 IWM）。`;
  return `前向成绩：样本不足（已结算 ${txt(settled)}/${txt(shadow.min_settled_for_conclusion)} 条），暂不下结论。`;
}
function renderProofRow(proof){
  if(!proof)return statusRow('规则自证门','','本轮没有拿到规则自证门的判定。');
  return statusRow(`规则自证门 ${proof.open?'开':'关'}`,proof.open?'pass':'',proof.evidence||proof.line||'—');
}
function renderShadowRow(decision,report){
  if(decision.state!=='NO_ACTION')return null;
  const shadow=decision.shadow_candidate;
  if(!shadow){return decision.shadow_note?statusRow('影子候选','',`${decision.shadow_note} ${shadowRecord(report.ledger)}`):null}
  const text=`今天如果发布，会是 ${txt(shadow.symbol)}（${txt(shadow.name)}，市值 ${billions(shadow.market_cap_usd)}；${branchList(shadow.support_branches)}，支持度 ${num(shadow.support_total)}）。为什么还不发布：规则自证门没开，只记录、不发布。${shadowRecord(report.ledger)}`;
  return statusRow('影子候选','',text);
}
const GLOSSARY=[
  ['IWM','美国小盘股指数基金，用作比较基准'],
  ['超额','这只股的收益减去 IWM 同期收益'],
  ['回测','把规则放回过去每个月末重放一遍，看当时会选谁、之后 20 个交易日表现如何'],
  ['安慰剂','把事件日期往后挪 60 个交易日再重放；成绩不比它好，说明不是规则本身的功劳'],
  ['影子候选','规则没开门时「如果发布会选谁」，只记录、不发布，事后照样算成绩']];
function renderGlossary(){const box=node('dl',undefined,{class:'glossary'});GLOSSARY.forEach(([term,text])=>{const item=node('div');item.append(node('dt',term));item.append(node('dd',text));box.append(item)});return box}
function heroFacts(decision,report){
  const facts=node('dl',undefined,{class:'decision-facts'});
  const support=decision.support||{};
  const invalidation=decision.invalidation||{};
  if(decision.state==='RECOMMENDATION'){
    facts.append(fact('当前价格',money(decision.price),decision.quote_source_time?`来源时间 ${time(decision.quote_source_time)}`:''));
    facts.append(fact('市值',billions(decision.market_cap_usd)));
    facts.append(fact('支持度合计',blank(support.total)?'—':`${num(support.total)} / 门槛 ${num(support.threshold,1)}`,decision.weights_mode==='COLD_START_EQUAL'?'分支权重：记分簿样本不足，等权':'分支权重：按前向命中率'));
    facts.append(fact('失效条件',invalidation.status_text||'—',invalidation.published_at?`发布于 ${time(invalidation.published_at)}`:''));
  }else{
    const shadow=decision.shadow_candidate;
    facts.append(fact('候选',`${list(report.candidates).length} 只`,'研究层 shortlist'));
    facts.append(fact('过门槛候选',`${txt(decision.qualifying_candidates)} 只`,'候选池、报价、流动性、一票否决、支持度五道门'));
    facts.append(fact('影子候选',shadow?`${txt(shadow.symbol)}｜${billions(shadow.market_cap_usd)}`:'今天没有',shadow?money(shadow.price):''));
  }
  facts.append(fact('研究快照',report.data_cutoff,(report.research||{}).research_age_hours!==undefined?`${num((report.research||{}).research_age_hours,1)} 小时前确认`:''));
  facts.append(fact('下一轮','约 60 秒后'));
  return facts;
}
function renderDecisionHero(report){
  const decision=report.decision||{};
  const proof=report.proof_gate||decision.proof_gate;
  const section=node('section',undefined,{class:'hero panel',id:'decision','aria-labelledby':'decision-title'});
  const main=node('div',undefined,{class:'hero-main'});
  const kicker=node('div',undefined,{class:'hero-kicker'});
  kicker.append(node('span','实时运行',{class:'live-pill pass'}));
  kicker.append(node('span',`本轮 ${time(report.generated_at)}`));
  if(report.us_market&&report.us_market.text)kicker.append(node('span',report.us_market.text,{class:`live-pill ${report.us_market.state==='OPEN'?'pass':''}`,'data-market-state':report.us_market.state}));
  main.append(kicker);
  main.append(node('p','最终研究结论',{class:'eyebrow'}));
  main.append(node('h1',statusText(decision),{id:'decision-title','data-action':decision.action_code||'NONE'}));
  if(decision.state==='RECOMMENDATION')main.append(node('p',`${txt(decision.primary_name)}（${txt(decision.primary_symbol)}）｜市值 ${billions(decision.market_cap_usd)}`,{class:'decision-symbol'}));
  main.append(node('p',decision.rationale||report.message||'—',{class:'lead'}));
  const rows=node('div',undefined,{class:'status-rows'});
  rows.append(renderProofRow(proof));
  const shadowRow=renderShadowRow(decision,report);
  if(shadowRow)rows.append(shadowRow);
  main.append(rows);
  const degradedNotice=degradedSummary(report);
  if(degradedNotice)main.append(node('p',`数据覆盖：${degradedNotice}`,{class:'lead hero-delay-notice'}));
  main.append(renderGlossary());
  const chips=node('div',undefined,{class:'chips'});
  ['每 60 秒运行','Agent 依赖 0','LLM Token 0','只做研究、不下单'].forEach(x=>chips.append(node('span',x)));
  main.append(chips);
  section.append(main);
  section.append(heroFacts(decision,report));
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
function reasonRows(reasons){return list(reasons).map(r=>[branchName(r.branch_id),r.kind==='PASS'?'通过（1.0）':'排序支持（0.3）',r.sentence,secLink(r.link,'打开原文')])}
function renderWhy(report){
  const decision=report.decision||{};
  const proof=report.proof_gate||decision.proof_gate||{};
  const section=panel('为什么得出这个结论','每个支持分支一句话理由与 SEC 一手原文；失效条件在发布时写死，之后每轮自动核对。');
  section.setAttribute('id','evidence');
  section.append(plainList([['结论',decision.rationale],['支持度规则',decision.support_rule],['数据链',decision.state==='SYSTEM_BLOCKED'?decision.message:null]]));
  if(proof.rule){
    section.append(node('h3',`规则自证门：${proof.open?'开':'关'}`));
    section.append(node('p',proof.rule));
    if(list(proof.reasons).length){const ul=node('ul',undefined,{class:'plain-list bullets'});list(proof.reasons).forEach(r=>ul.append(node('li',r)));section.append(ul)}
  }
  const shadow=decision.shadow_candidate;
  if(shadow){
    section.append(node('h3',`影子候选：${txt(shadow.symbol)}（${txt(shadow.name)}）`));
    section.append(node('p',shadow.sentence));
    section.append(node('p',shadow.why_not_published));
    if(list(shadow.reasons).length)section.append(table(['分支','类型','理由','SEC 原文'],reasonRows(shadow.reasons)));
  }
  const reasons=list(decision.reasons);
  if(reasons.length){
    section.append(node('h3','支持它的分支与一手原文'));
    section.append(table(['分支','类型','理由','SEC 原文'],reasonRows(reasons)));
    const sources=list(decision.sources);
    if(sources.length){section.append(node('h3','一手原文清单'));section.append(table(['分支','日期','摘要','链接'],sources.map(s=>[branchName(s.branch_id),s.published_date,s.summary,secLink(s.url,'SEC 原文')])))}
  }
  const conflicts=list(decision.conflicts);
  if(decision.state==='RECOMMENDATION'){
    section.append(node('h3','冲突（保留正反两面）'));
    section.append(conflicts.length?table(['类型','说明'],conflicts.map(c=>[c.kind==='VETO'?'一票否决':'其它分支的反对意见',c.text])):node('p','没有分支给出与该建议相反的结论。'));
  }
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
    section.append(node('h3',decision.state==='NO_ACTION'?'观察名单（前 5）：支持它的分支，和差在哪一道门':'观察名单（前 5）'));
    section.append(table(['代码','公司','支持它的分支','差在哪','SEC 原文'],watch.map(w=>[w.is_shadow_candidate?`${txt(w.symbol)}（影子候选）`:w.symbol,w.name,branchList(w.support_branches),w.sentence,list(w.links).length?secLink(w.links[0],'SEC 原文'):'—'])));
  }
  return section;
}
const STATUS_TEXT={PASS:'已出结论',ABSTAIN:'整分支弃权',FAILED:'运行失败'};
function branchCard(r){
  const env=r.role==='MARKET_ENVIRONMENT';
  const card=node('article',undefined,{class:env?'skill-card env':'skill-card'});
  const head=node('header');
  head.append(node('h3',r.label||branchName(r.branch_id)));
  head.append(node('span',env?'环境输入':(STATUS_TEXT[r.status]||txt(r.status)),{class:`badge ${r.status==='PASS'?'pass':r.status==='ABSTAIN'?'warning':'blocked'}`}));
  card.append(head);
  const counts=r.verdict_counts||{};
  const dl=node('dl');
  [['通过',counts.PASS],['弃权',counts.ABSTAIN],['失败',counts.FAILED]].forEach(([label,value])=>{const box=node('div');box.append(node('dt',label));box.append(node('dd',txt(value)));dl.append(box)});
  card.append(dl);
  card.append(node('p',`Skill 参数版本 ${txt(r.params_version)}｜快照 ${blank(r.snapshot_hash)?'—':String(r.snapshot_hash).slice(0,12)}`,{class:'meta'}));
  card.append(node('p',r.note||r.reason||'—',{class:'note'}));
  return card;
}
function renderBranches(report){
  const section=panel('分支独立判断','每个分支在独立子进程里只读同一份不可变快照，本轮运行时互相看不到对方的输出（同一系统用户下，这是防误读，不是安全边界）。「通过 / 弃权 / 失败」是它对全池每家公司各自的结论数；一句话说明取自它自己的收据与逐股原因。');
  section.setAttribute('id','skills');
  const grid=node('div',undefined,{class:'skill-grid'});
  list(report.receipts).forEach(r=>grid.append(branchCard(r)));
  if(!list(report.receipts).length)grid.append(node('p','本轮没有分支收据。'));
  section.append(grid);
  return section;
}
let showAllCandidates=false;
const BRANCH_COLUMNS=[['equity-event-atlas','事件航图'],['bottleneck-serenity-skill','瓶颈'],['stock-commercial-opportunities','商业机会'],['equity-foresight-signal','股势前瞻']];
function candidateCard(c){
  const card=node('article',undefined,{class:'cand-card'});
  const head=node('header');
  const title=node('div');
  title.append(node('strong',`#${txt(c.rank)} ${txt(c.symbol)}`));
  title.append(node('span',`${txt(c.name)}｜市值 ${yi(c.market_cap_usd)}美元`));
  head.append(title);
  head.append(node('span',`支持度 ${num(c.support_total)}`,{class:'badge muted'}));
  card.append(head);
  const grid=node('dl',undefined,{class:'cand-branches'});
  BRANCH_COLUMNS.forEach(([id,label])=>{const box=node('div');box.append(node('dt',label));const dd=node('dd');dd.append(kindCell((c.branch_kinds||{})[id]));box.append(dd);grid.append(box)});
  card.append(grid);
  card.append(node('p',c.passes_all_gates?'全部门通过':c.gate_summary,{class:'gap'}));
  if(list(c.links).length)card.append(secLink(c.links[0],'打开 SEC 原文'));
  return card;
}
function renderCandidates(report){
  const section=panel('候选比较','研究层 shortlist（最多 60 只）逐只比较。各分支一栏：通过＝该分支给出 PASS；排序支持＝分数进全池前 10% 但未达 PASS；—＝没有支持。支持度＝通过 1.0 + 排序支持 0.3（乘分支权重），合计 ≥ 1.3 且过完全部硬门才会发布。');
  section.setAttribute('id','candidates');
  const all=list(report.candidates);
  if(!all.length){section.append(node('p','本轮没有候选（研究层没有产出或数据链不完整）。'));return section}
  const shown=showAllCandidates?all:all.slice(0,15);
  const rows=shown.map(c=>[c.rank,c.symbol,c.name,yi(c.market_cap_usd),...BRANCH_COLUMNS.map(([id])=>kindCell((c.branch_kinds||{})[id])),num(c.support_total),c.passes_all_gates?'全部通过':c.gate_summary,list(c.links).length?secLink(c.links[0],'SEC 原文'):'—']);
  const desktop=table(['#','代码','公司','市值（美元）',...BRANCH_COLUMNS.map(([,label])=>label),'支持度','差在哪','SEC 原文'],rows,{minWidth:1180});
  desktop.classList.add('cand-table');
  section.append(desktop);
  const cards=node('div',undefined,{class:'cand-cards'});
  shown.forEach(c=>cards.append(candidateCard(c)));
  section.append(cards);
  if(all.length>15){
    const button=node('button',showAllCandidates?'只看前 15 只':`显示全部 ${all.length} 只`,{type:'button',class:'more-button'});
    button.addEventListener('click',()=>{showAllCandidates=!showAllCandidates;const fresh=renderCandidates(report);section.replaceWith(fresh);fresh.scrollIntoView({block:'start'})});
    section.append(button);
  }
  return section;
}
function ledgerBlock(ledger,title){
  const box=node('div',undefined,{class:'ledger-block'});
  box.append(node('h3',title));
  if(!ledger){box.append(node('p','还没有数据。'));return box}
  box.append(node('p',ledger.message||'—'));
  box.append(plainList([['起算日',ledger.inception_day],['已记录交易日',ledger.recorded_days],...(ledger.recommendation_days!==undefined?[['其中建议 / NO_ACTION',`${txt(ledger.recommendation_days)} / ${txt(ledger.no_action_days)}`]]:[]),['已结算（20 日 / 60 日）',`${txt((ledger.settled||{})['20'])} / ${txt((ledger.settled||{})['60'])}`],['说明',ledger.note]]));
  const horizons=ledger.horizons||{};
  const rows=Object.entries(horizons).filter(([,h])=>h.status==='SUFFICIENT').map(([k,h])=>[`${k} 日`,h.settled,pct(h.hit_rate),spct(h.mean_excess_vs_iwm),spct(h.median_excess_vs_iwm),spct(h.mean_excess_vs_control),spct(h.worst_excess_vs_iwm)]);
  if(rows.length)box.append(table(['持有期','已结算','命中率','相对 IWM 平均超额','中位超额','相对同档随机平均超额','最差一笔'],rows));
  const recent=list(ledger.recent);
  if(recent.length)box.append(table(['交易日','当日决策','代码','20 日已结算','60 日已结算'],recent.map(r=>[r.trading_day,r.state==='RECOMMENDATION'?'研究跟进（看多）':(r.state==='NO_ACTION'?'NO_ACTION':'影子候选'),r.symbol,r.settled_20?'是':'否',r.settled_60?'是':'否'])));
  return box;
}
function findHub(bt){const branches=(bt||{}).branches;if(Array.isArray(branches))return branches.find(b=>b.branch_id==='hub');return (branches||{}).hub}
function backtestBlock(bt){
  const box=node('div',undefined,{class:'ledger-block'});
  box.append(node('h3','回测（时点正确、按月滚动、扣成本、含安慰剂）'));
  const hub=findHub(bt);
  const windows=hub?(hub.oos_windows!==undefined?hub.oos_windows:(hub.walk_forward||{}).windows):null;
  const min=((bt||{}).method||{}).minimum_oos_windows_for_profitability||((bt||{}).profitability_disclosure||{}).minimum_oos_windows_for_profitability;
  const published=!!(hub&&hub.stitched);
  const grid=node('div',undefined,{class:'quant-grid fit'});
  [['样本外窗口',`${txt(windows)} / 门槛 ${txt(min)}`],['是否公布收益数字',published?'公布（含亏损）':'不公布'],['比较基准','IWM（小盘基金）']].forEach(([label,value])=>{const cell=node('div');cell.append(node('span',label));cell.append(node('strong',value));grid.append(cell)});
  box.append(grid);
  if(bt&&bt.why_not_published)box.append(node('p',`不公布收益数字：${bt.why_not_published}`));
  else if(bt&&(bt.profitability_disclosure||{}).why_not_published)box.append(node('p',`不公布收益数字：${bt.profitability_disclosure.why_not_published}`));
  else if(!hub)box.append(node('p',(bt||{}).message||'中枢回测还没有产出。'));
  if(published){
    const st=hub.stitched;
    const row=(label,block)=>block?[label,txt(block.windows),spct((block.excess_vs_iwm||{}).mean),pct((block.excess_vs_iwm||{}).hit_rate),spct((block.excess_vs_control||{}).mean),spct((block.excess_vs_iwm||{}).worst)]:[label,'—','—','—','—','—'];
    box.append(table(['对象','窗口（月）','相对 IWM 净超额均值','命中率（跑赢 IWM 的月份占比）','相对同档随机均值','最差一个月'],[
      row('正式：唯一建议，持有 20 日',st.pick_20),
      row('正式：唯一建议，持有 60 日',st.pick_60),
      row('安慰剂：事件日期后移 60 日，持有 20 日',st.placebo_pick_20),
      ['IWM：小盘基准（比较的零点）','—','0（基准）','—','—','—']]));
    box.append(node('p','读法：正式结果要同时跑赢 IWM、跑赢同市值档随机抽样，并且明显好于安慰剂，规则才算有信息量。数字为扣完交易成本后的净超额。',{class:'section-note'}));
  }
  const assumptions=list(((bt||{}).method||{}).assumptions);
  if(assumptions.length){const details=node('details',undefined,{class:'assumptions'});details.append(node('summary','回测假设与局限（点开）'));const ul=node('ul',undefined,{class:'plain-list bullets'});assumptions.forEach(a=>ul.append(node('li',a)));details.append(ul);box.append(details)}
  return box;
}
const GATE_ROWS=[['pool','候选池','在研究层候选池内（市值 3–50 亿美元、美国本土申报人等）'],['quote','实时报价','报价按交易时间口径新鲜'],['liquidity','流动性','价格 ≥ 3 美元、20 日成交额中位数 ≥ 300 万美元、按最新价市值 ≤ 50 亿'],['veto','一票否决','没有生效的失效条件：事件航图 FAILED（近 90 天增发/ATM 或股数大增）、此前发布后已失效的建议'],['support','支持度','加权支持度 ≥ 1.3'],['proof','规则自证门','规则先用回测或前向成绩证明自己有信息量']];
function hardGateBlock(report){
  const box=node('div',undefined,{class:'ledger-block'});
  box.append(node('h3','六道硬门（候选逐一过，全过才可能发布）'));
  const all=list(report.candidates);
  if(!all.length){box.append(node('p','本轮没有候选。'));return box}
  const ul=node('ul',undefined,{class:'gate-list'});
  GATE_ROWS.forEach(([key,name,text])=>{
    const ok=all.filter(c=>((c.gates||{})[key]||{}).ok===true).length;
    const li=node('li');
    const head=node('div',undefined,{class:'gate-head'});
    head.append(node('strong',name));
    head.append(node('span',`${ok} / ${all.length} 只通过`,{class:`cell ${ok===all.length?'pass':ok===0?'blocked':'degraded'}`}));
    li.append(head);
    li.append(node('small',text));
    ul.append(li);
  });
  box.append(ul);
  const notWired=list((report.decision||{}).not_wired_vetoes);
  if(notWired.length){
    const small=node('ul',undefined,{class:'plain-list bullets'});
    notWired.forEach(v=>small.append(node('li',`${txt(v.text)}：暂未接入（${txt(v.reason)}）`)));
    box.append(node('p','以下否决项暂未接入，不在硬门里，也不会生效：'));
    box.append(small);
  }
  return box;
}
function renderQuant(report){
  const section=panel('收益与硬门','证据不足时不给收益数字：回测样本外窗口 < 6 只公布窗口数；前向已结算样本 < 8 写「样本不足，暂不下结论」。数字一律公开，亏损也不藏。');
  section.setAttribute('id','quant');
  section.append(hardGateBlock(report));
  section.append(backtestBlock(report.backtest));
  const two=node('div',undefined,{class:'two-column ledgers'});
  two.append(ledgerBlock(report.ledger,'前向记分簿：正式建议（只追加、从上线日起算）'));
  two.append(ledgerBlock((report.ledger||{}).shadow,'前向记分簿：影子候选（单独统计）'));
  section.append(two);
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
