const app=document.querySelector('#main');
const statusDot=document.querySelector('#status-dot');
const runtimeMode=document.querySelector('#runtime-mode');
const pct=value=>Number.isFinite(Number(value))?`${(Number(value)*100).toFixed(1)}%`:'—';
const time=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'—';
function node(tag,text,attrs={}){const item=document.createElement(tag);if(text!==undefined)item.textContent=text;for(const [key,value] of Object.entries(attrs)){item.setAttribute(key,value)}return item}
function panel(title,description){const section=node('section',undefined,{class:'panel section-block'});const header=node('header');header.append(node('div'));header.firstChild.append(node('h2',title));if(description)header.firstChild.append(node('p',description));section.append(header);return section}
function table(headers,rows){const wrap=node('div',undefined,{class:'table-wrap',tabindex:'0'});const tableElement=node('table');const head=node('thead');const headRow=node('tr');headers.forEach(value=>headRow.append(node('th',value)));head.append(headRow);tableElement.append(head);const body=node('tbody');rows.forEach(row=>{const tr=node('tr');row.forEach(value=>tr.append(node('td',String(value))));body.append(tr)});tableElement.append(body);wrap.append(tableElement);return wrap}

function money(value,currency){return Number.isFinite(Number(value))?`${Number(value).toFixed(2)} ${currency||''}`.trim():'—'}
function fact(term,value,note){const box=node('div');box.append(node('dt',term));box.append(node('dd',value));if(note)box.append(node('small',note));return box}
function suggestedPosition(report,decision){
  // 仓位来自 S1 实际生效参数：top_n 只数 × 每只权重，再乘该标的的波动缩放。
  // 没有生效参数或没有该标的的分支证据时如实留空，不猜。
  const branches=(report.backtest&&report.backtest.branches)||[];
  const list=Array.isArray(branches)?branches:Object.values(branches);
  const s1=list.find(item=>item&&item.branch_id==='s1_momentum');
  const selection=s1&&s1.active_config&&s1.active_config.selection;
  if(!selection||!Number.isFinite(Number(selection.weight_each)))return['—','未取得生效选股参数'];
  const base=Number(selection.weight_each);
  const entry=(report.branches||[]).find(item=>item&&item.branch_id==='s1_momentum'&&item.symbol===decision.primary_symbol);
  const scalar=entry&&entry.evidence&&Number(entry.evidence.position_scalar);
  if(!Number.isFinite(scalar))return[pct(base),`top ${selection.top_n} 每只 ${pct(base)}`];
  return[pct(base*scalar),`top ${selection.top_n} 每只 ${pct(base)} × 波动缩放 ${scalar.toFixed(2)}`];
}
function degradedSummary(report){
  const degraded=report.degraded_symbols||{};
  const symbols=Object.keys(degraded);
  if(!symbols.length)return null;
  const names=symbols.map(symbol=>{const item=(report.instruments||{})[symbol]||{};return item.name?`${symbol}（${item.name}）`:symbol});
  return `本轮有 ${symbols.length} 个标的未通过数据门，已排除：${names.join('、')}。这些标的不参与任何分支计算，结论不受影响。`;
}
function renderDegraded(report){
  const degraded=report.degraded_symbols||{};
  const section=panel('本轮排除的标的','未通过数据门的标的逐个列出原因；它们的报价不作为当前价格展示。');
  const rows=Object.entries(degraded).map(([symbol,findings])=>{
    const item=(report.instruments||{})[symbol]||{};
    return [symbol,item.name||'—',item.market||'—','对结论零贡献',(findings||[]).join('；')];
  });
  if(!rows.length)section.append(node('p','本轮所有标的均通过数据门。'));
  else section.append(table(['标的','名称','市场','对结论的影响','未通过原因'],rows));
  return section;
}
function renderDecisionHero(report){
  const decision=report.decision||{};
  const symbol=decision.primary_symbol;
  const instrument=(report.instruments||{})[symbol]||{};
  const quote=(report.quotes||{})[symbol]||{};
  const section=node('section',undefined,{class:'hero panel',id:'decision','aria-labelledby':'decision-title'});
  const main=node('div',undefined,{class:'hero-main'});
  const kicker=node('div',undefined,{class:'hero-kicker'});
  kicker.append(node('span','实时运行',{class:'live-pill pass'}));
  kicker.append(node('span',`本轮 ${time(report.generated_at)}`));
  main.append(kicker);
  main.append(node('p','最终投资建议',{class:'eyebrow'}));
  main.append(node('h1',decision.action?`${decision.action} ${symbol||''}`.trim():'本轮未产出方向性结论',{id:'decision-title','data-action':decision.action_code||'NONE'}));
  main.append(node('p',instrument.name?`${symbol}｜${instrument.name}`:(symbol||'—'),{class:'decision-symbol'}));
  main.append(node('p',decision.rationale||'—',{class:'lead'}));
  // 港股延迟声明必须和结论待在一起。把它沉到页面底部等于让人先看到结论、
  // 很久之后才知道那份行情延迟 25 分钟；这里直接挂在结论下方。
  const heroNotice=marketDelayDisclosure(report);
  if(heroNotice)main.append(node('p',`行情时效：${heroNotice}`,{class:'lead hero-delay-notice'}));
  const degradedNotice=degradedSummary(report);
  if(degradedNotice)main.append(node('p',`数据覆盖：${degradedNotice}`,{class:'lead hero-delay-notice'}));
  const chips=node('div',undefined,{class:'chips'});
  ['每 60 秒全量运行','Agent 依赖 0','LLM Token 0','禁止自动交易'].forEach(x=>chips.append(node('span',x)));
  main.append(chips);
  section.append(main);

  const [position,positionNote]=suggestedPosition(report,decision);
  const gated=String(report.profitability_status||'').startsWith('OOS_HISTORY_INSUFFICIENT');
  const gateNote=gated?`样本外窗口 ${String(report.profitability_status).split(': ').pop()}，未达发布门`:'';
  const facts=node('dl',undefined,{class:'decision-facts'});
  facts.append(fact('当前价格',money(quote.price,quote.currency),quote.source_time?`来源时间 ${time(quote.source_time)}`:''));
  facts.append(fact('建议仓位',position,positionNote));
  facts.append(fact('持有期限','20 / 60 交易日','前向成熟窗口；偏离 3% 触发再平衡'));
  facts.append(fact('费用后预期',gated?'样本不足未发布':'见收益区块',gateNote||'扣除费用后的样本外超额'));
  facts.append(fact('压力下行',gated?'样本不足未发布':'见收益区块',gateNote||'样本外最大回撤'));
  facts.append(fact('综合置信度',pct(decision.conviction),decision.weight_mode==='COLD_START_EQUAL'?`冷启动等权（贡献样本 ${decision.weight_sample_count}）`:'按贡献度加权'));
  facts.append(fact('失效条件',decision.invalidation?'见下方':'—',decision.invalidation||''));
  facts.append(fact('下一轮','约 60 秒后',`数据截止 ${report.data_cutoff||'—'}`));
  section.append(facts);
  return section;
}
function renderCycle(report){
  const decision=report.decision||{};
  const participating=(decision.participating_branches||[]).length;
  const excluded=(decision.excluded_branches||[]).length;
  const accounting=report.collection_request_accounting||{};
  const grid=node('section',undefined,{class:'metric-grid',id:'cycle','aria-label':'本轮链路状态'});
  const card=(label,value,note)=>{const a=node('article',undefined,{class:'metric'});a.append(node('span',label));a.append(node('strong',String(value)));a.append(node('small',note));return a};
  grid.append(card('参与分支',participating,'权重为正且通过推广门'));
  grid.append(card('排除分支',excluded,'未实现、不在资产池或未过推广门'));
  grid.append(card('覆盖标的',Object.keys(report.instruments||{}).length,'四个市场的真实行情'));
  grid.append(card('本日采集轮次',accounting.daily_round_count??'—',`上限 ${accounting.maximum_provider_requests_per_day??'—'} 次请求/日`));
  return grid;
}
function renderBlocked(report={}){app.setAttribute('aria-busy','false');app.replaceChildren();if(statusDot){statusDot.className='dot danger'}if(runtimeMode){runtimeMode.textContent=report.blocked_reason||report.state||'未就绪'}const decision=report.decision||{};const loopUnreachable=report.blocked_reason==='COLLECTION_LOOP_UNREACHABLE';const main=node('main',undefined,{id:'main-content',class:'blocked-page',tabindex:'-1'});main.append(node('p',decision.state||'SYSTEM_BLOCKED',{class:'eyebrow'}));main.append(node('h1',loopUnreachable?'采集循环失联，结论已过期':'数据链路不完整，不出结论'));main.append(node('p',report.message||decision.rationale||(loopUnreachable?'循环心跳或最新报告超过时效窗口，未复用旧结论。':'数据新鲜度门未通过，未执行分支计算或方向协调。'),{class:'lead'}),renderMarketDataDisclosure(report),renderDegraded(report),renderSources(report),renderDataQuality(report),renderQuoteFreshness(report));app.append(main)}
function renderSources(report){const section=panel('行情数据覆盖','每个标的展示实际使用的日线来源、条数与截止。');const rows=Object.entries(report.bar_sources||{}).map(([symbol,source])=>{const instrument=(report.instruments||{})[symbol]||{};return [symbol,instrument.name||'—',source.source||'—',source.bar_count??'—',source.earliest_day||'—',source.latest_day||'—']});section.append(table(['标的','名称','日线来源','条数','最早','数据截止'],rows));return section}
function renderDataQuality(report){const section=panel('日线质量记账','语义错误 Bar 已从计算序列剔除；近期窗口、数量或比例越界仍会阻断。');const rows=Object.entries(report.bar_quality||{}).map(([symbol,item])=>[symbol,item.status||'—',`${item.dropped_invalid_bar_count??0}/${item.input_bar_count??0}`,pct(item.dropped_invalid_bar_ratio),item.recent_window_start||'—',item.recent_invalid_bar_count??0,(item.blocking_reasons||[]).join('、')||'无',(item.samples||[]).map(sample=>`${sample.day}（${(sample.violations||[]).join('、')}）`).join('；')||'—']);section.append(table(['标的','状态','剔除/输入','比例','近期窗口起点','近期异常数','阻断原因','样例'],rows));return section}
function marketDelayDisclosure(report){const instruments=Object.values(report.instruments||{});const hasHongKong=instruments.some(item=>item.market==='HK');if(!hasHongKong)return null;const declaredDelay=Math.max(...instruments.filter(item=>item.market==='HK').map(item=>Number(item.declared_feed_delay_minutes)||0));return `港股行情为交易所规定的延迟数据（约 ${declaredDelay} 分钟），非实时。`}
function renderMarketDataDisclosure(report){const section=panel('市场行情时效声明','每项结论都以实际市场的来源时效为准。');section.classList.add('market-delay-notice');section.append(node('p','A股行情为实时数据；港股行情为交易所规定的延迟数据（约 25 分钟），非实时；美股行情为实时数据，休市时显示最近收盘。'));const hongKongNotice=marketDelayDisclosure(report);if(hongKongNotice)section.append(node('p',hongKongNotice));return section}
function renderQuoteFreshness(report){const section=panel('报价来源时间','开市同时检查“声明延迟 + TTL”绝对上限与来源时间推进；休市不适用推进检测，本机观察时间不替代来源时间。');const rows=Object.entries(report.quote_freshness||{}).map(([symbol,item])=>[symbol,item.market_state||'—',item.basis||'—',item.declared_feed_delay_minutes??'—',item.observed_lag_minutes===null||item.observed_lag_minutes===undefined?'—':Number(item.observed_lag_minutes).toFixed(1),item.last_advance_at||'—',item.stalled_minutes===null||item.stalled_minutes===undefined?'—':Number(item.stalled_minutes).toFixed(1),item.status||'—',item.source_time||'—',item.allowed_source_age_seconds===undefined?(item.allowed_source_age_calendar_days===undefined?'—':`${item.allowed_source_age_calendar_days} 天`):`${(Number(item.allowed_source_age_seconds)/60).toFixed(1)} 分钟`]);section.append(table(['标的','市场状态','判定口径','声明延迟（分钟）','实测滞后（分钟）','最后推进','连续未推进（分钟）','结果','来源时间','允许上限'],rows));return section}
function branchText(item){return `${item.branch_id}｜${item.participation_status}｜${(item.symbols||[]).join('、')||'—'}${item.reason?`｜${item.reason}`:''}`}
function renderDecision(report){const decision=report.decision||{};const noEligible=decision.state==='NO_ELIGIBLE_BRANCH';const description=noEligible?'有数据但没有可用分支：这是权重门的结果，不是数据链路阻断。':'唯一组合建议由正权重分支计算；系统不自动交易，样本外收益与 Alpha 见下方回测区块。';const section=panel('最终投资建议',description);const card=node('article',undefined,{class:'signal-card'});card.append(node('h3',`${decision.state||'—'}｜${decision.action??'不出动作'}`));card.append(node('p',`关注标的：${decision.primary_symbol||'无'}｜信念强度：${pct(decision.conviction)}｜权重样本数：${decision.weight_sample_count??0}`));const hongKongNotice=marketDelayDisclosure(report);if(hongKongNotice)card.append(node('p',`行情时效：${hongKongNotice}`));if(decision.sample_sufficiency)card.append(node('p',`收益证据：${decision.sample_sufficiency}｜${decision.sample_sufficiency_message||'样本外历史不足，仅供研究参考，不构成收益证据。'}`));card.append(node('p',`依据：${decision.rationale||'—'}`));card.append(node('p',`最大反证：${decision.counter_evidence||'—'}`));card.append(node('p',`失效条件：${decision.invalidation||'—'}`));section.append(card);return section}
function renderAggregate(report){const section=panel('各标的汇总结论','每个标的只汇总 weight > 0 的分支；weight = 0 的结论逐项保留排除原因。');const list=node('div',undefined,{class:'card-list'});(report.aggregate||[]).forEach(item=>{const card=node('article',undefined,{class:'signal-card'});card.append(node('h3',`${item.symbol}｜${item.direction}`));card.append(node('p',`置信度 ${pct(item.confidence)}｜参与分支 ${item.participating_branch_count??0}｜排除分支 ${item.excluded_branch_count??0}｜权重样本数 ${item.weight_sample_count??0}`));card.append(node('p',`参与：${(item.participating_branches||[]).map(branch=>branch.branch_id).join('、')||'无'}`));const excluded=item.excluded_branches||[];if(excluded.length)card.append(node('p',`排除：${excluded.map(branch=>`${branch.branch_id}（${branch.reason}）`).join('；')}`));card.append(node('p',item.message||''));list.append(card)});section.append(list);return section}
function renderBranches(report){const section=panel('分支独立结论','每个分支各自保留证据、最大反证和可判定失效条件。未实现分支明确标注且权重为 0。');const groups=new Map();(report.branches||[]).forEach(item=>{const group=groups.get(item.branch_id)||[];group.push(item);groups.set(item.branch_id,group)});for(const [branchId,items] of groups){const card=node('article',undefined,{class:'branch-card'});card.append(node('h3',branchId));const rows=items.map(item=>[item.symbol,item.direction,pct(item.confidence),item.window_used,item.implemented?'已实现':'未实现',item.weight,item.participation_status,item.counter_evidence,item.invalidation]);card.append(table(['标的','方向','置信度','窗口','实现','权重','参与状态','最大反证','失效条件'],rows));section.append(card)}return section}
function decimal(value){return Number.isFinite(Number(value))?Number(value).toFixed(4):'—'}
function trajectoryText(item){const entries=item.weight_trajectory||[];if(!entries.length){const summary=item.weight_trajectory_summary||{};return `${pct(summary.start_weight)} → ${pct(summary.end_weight)}`}return entries.map(entry=>`${entry.window_label||`${entry.period_start} 至 ${entry.period_end}`}：${pct(entry.start_weight)} → ${pct(entry.end_weight)}（${entry.update_value===null?'无样本':decimal(entry.update_value)}，${entry.metric_source}）`).join('；')}
function renderContributionWeights(report){const weighting=report.contribution_weights||{};const mode=weighting.weight_mode||report.weight_mode||'COLD_START_EQUAL';const minimum=weighting.minimum_contribution_samples??'—';const section=panel('贡献度动态权重','Hedge 仅在已通过既有参与资格门的分支之间更新；样本不足分支保留冷启动等权份额。');section.append(node('p',`当前模式：${mode}｜有效贡献样本：${weighting.weight_sample_count??report.weight_sample_count??0}｜最低门槛：${minimum}｜η=${weighting.learning_rate??'—'}｜floor=${pct(weighting.weight_floor)}｜cap=${pct(weighting.weight_cap)}。`));const rows=(weighting.branches||[]).map(item=>[item.branch_id,pct(item.weight),`${item.usable_sample_count??item.sample_count??0}/${item.minimum_contribution_samples??minimum}`,decimal(item.cumulative_risk_adjusted_excess),decimal(item.cumulative_update_contribution),item.metric_source||'—',item.weight_status||'—',item.negative_contribution_message||'—',trajectoryText(item)]);section.append(table(['分支','当前权重','样本 N/M','累计风险调整超额','累计更新贡献','更新依据','权重状态','负贡献状态','逐期轨迹'],rows));return section}
function metric(value,suffix=''){return value===null||value===undefined?'—':Number(value).toFixed(4)+suffix}
function renderBacktest(report){const data=report.backtest||{};const section=panel('回测与超额收益','严格样本外结果：参数只在训练窗网格搜索，评价只使用紧随其后的完整 test 窗口；不展示全样本调参业绩。');const method=data.method||{};const sufficiency=data.sample_sufficiency||report.sample_sufficiency||'样本不足';const insufficient=String(sufficiency).startsWith('OOS_HISTORY_INSUFFICIENT:');section.append(node('p','状态：'+(data.status||'样本不足')+'｜训练 '+(method.train_months??'—')+' 个月｜测试 '+(method.test_months??'—')+' 个月｜结构性最低 '+(method.minimum_complete_windows??'—')+' 窗口｜收益证据最低 '+(method.minimum_oos_windows_for_profitability??'—')+' 窗口。'));if(insufficient)section.append(node('p',`${sufficiency}｜${data.sample_sufficiency_message||'样本外历史不足，仅供研究参考，不构成收益证据。'} 收益数字与逐窗口业绩在达到门槛前不展示。`));section.append(node('p','费用：每单佣金 '+metric(data.fees?.commission_usd_per_order,' USD')+'；卖出 SEC '+metric(data.fees?.sec_fee_rate_on_sell)+'；CAT '+metric(data.fees?.cat_fee_per_share,' USD/股')+'。'));const branches=data.branches||{};for(const branch of Object.values(branches)){if(branch.active_config)section.append(node('p',`${branch.branch_id} 当前参数来自 ${branch.config_source_window?.window_label||'—'}｜config_as_of ${branch.config_as_of||'—'}｜${JSON.stringify(branch.active_config)}`));else if(branch.config_status)section.append(node('p',`${branch.branch_id} 当前没有可绑定参数：${branch.config_status}。`))}const rows=Object.values(branches).map(branch=>{const stitched=branch.stitched||{};const displayed=insufficient?['未展示','未展示','未展示','未展示','未展示','未展示','未展示']:[metric(stitched.branch_return_pct,'%'),metric(stitched.benchmark_return_pct,'%'),metric(stitched.excess_return_pct,'%'),metric(stitched.information_ratio),metric(stitched.max_drawdown_pct,'%'),metric(stitched.win_rate_pct,'%'),metric(stitched.turnover_ratio)];return [branch.branch_id,branch.symbol||'—',branch.benchmark_symbol||'—',branch.status||'—',...displayed,branch.sample_sufficiency||branch.sample_status||branch.promotion?.reason||'—']});section.append(table(['分支','标的','基准','状态','策略收益','基准收益','超额收益','IR','最大回撤','胜率','换手率','样本或推广门'],rows));for(const branch of Object.values(branches)){const windows=branch.windows||[];if(!windows.length)continue;const card=node('article',undefined,{class:'branch-card'});card.append(node('h3',branch.branch_id+'｜逐窗口样本外结果'));if(insufficient)card.append(node('p','收益证据门尚未达到，逐窗口业绩不展示。'));else card.append(table(['窗口','训练期','测试期','超额收益','IR','最大回撤','费用'],windows.map(window=>[window.window_label,(window.train||[]).join(' 至 '),(window.test||[]).join(' 至 '),metric(window.test_metrics?.excess_return_pct,'%'),metric(window.test_metrics?.information_ratio),metric(window.test_metrics?.max_drawdown_pct,'%'),metric(window.test_fees_usd,' USD')])));section.append(card)}const contribution=data.contribution_summary||{};section.append(node('p','逐分支逐期贡献度样本：'+(contribution.sample_count??0)+' 条；风险调整超额公式：'+(method.risk_adjusted_excess_formula||'—')+'；聚合层消费状态：'+(method.dynamic_contribution_weighting||'—')+'。'));section.append(node('p','盈利状态：'+(data.profitability_status||report.profitability_status||'样本不足')+(insufficient?'。样本不足时不构成收益证据。':'。超额收益为负值时按实值显示，不挑选窗口。')));return section}
function renderCoordination(report){const section=panel('内部协调','显示分支间的裁决、参与权重、贡献度依据和排除原因。');const decision=report.decision||{};section.append(node('p',decision.internal_coordination||'—'));const facts=node('dl',undefined,{class:'system-facts'});const coordination=report.coordination||{};[['权重模式',report.weight_mode],['权重样本数',report.weight_sample_count],['盈利状态',report.profitability_status],['合成公式',coordination.rule],['平票规则',coordination.tie_break_rule],['中性观望阈值',pct(coordination.neutral_watch_confidence_threshold)],['排除结论数',coordination.excluded_branch_count],['动态权重',coordination.dynamic_contribution_weighting]].forEach(([label,value])=>{const row=node('div');row.append(node('dt',String(label)));row.append(node('dd',String(value??'—')));facts.append(row)});section.append(facts);const participating=decision.participating_branches||[];const excluded=decision.excluded_branches||[];section.append(node('h3','参与分支'));section.append(table(['分支','参与状态','标的','权重'],participating.map(item=>[item.branch_id,item.participation_status,(item.symbols||[]).join('、')||'—',item.weight??'—'])));section.append(node('h3','被排除分支'));section.append(table(['分支','参与状态','标的','排除原因'],excluded.map(item=>[item.branch_id,item.participation_status,(item.symbols||[]).join('、')||'—',item.reason||'—'])));return section}
function renderReady(report){
  app.setAttribute('aria-busy','false');
  app.replaceChildren();
  if(statusDot){statusDot.className='dot ok'}
  if(runtimeMode){runtimeMode.textContent=`${report.state}｜v${report.application_version}`}

  // 顺序就是阅读顺序：先给结论，再给依据，最后才是诊断。
  // 旧版把行情覆盖、日线质量、报价时效三张诊断表排在结论前面，
  // 近 50 行工程细节挡在结论之前——页面第一屏看不到任何结论。
  app.append(renderDecisionHero(report));
  app.append(renderCycle(report));

  const why=panel('为什么得出这个结论','加权投票、反面证据与失效条件。');
  why.setAttribute('id','evidence');
  const whyList=node('ul',undefined,{class:'plain-list'});
  const decision=report.decision||{};
  [['加权结论',decision.rationale],['内部协调',decision.internal_coordination],['反面证据',decision.counter_evidence],['失效条件',decision.invalidation]]
    .filter(([,value])=>value)
    .forEach(([label,value])=>{const li=node('li');li.append(node('strong',`${label}：`));li.append(document.createTextNode(value));whyList.append(li)});
  why.append(whyList);
  app.append(why);

  const branches=renderBranches(report);branches.setAttribute('id','skills');app.append(branches);
  const candidates=renderAggregate(report);candidates.setAttribute('id','candidates');app.append(candidates);
  const quant=renderBacktest(report);quant.setAttribute('id','quant');app.append(quant);
  const weights=renderContributionWeights(report);weights.setAttribute('id','evolution');app.append(weights);

  const lattice=panel('数据与时效','行情来源、日线质量与报价时间依据——支撑上面结论的原始记账。');
  lattice.setAttribute('id','lattice');
  app.append(lattice);
  app.append(renderDegraded(report));
  app.append(renderMarketDataDisclosure(report));
  app.append(renderSources(report));
  app.append(renderDataQuality(report));
  app.append(renderQuoteFreshness(report));

  const ops=panel('系统运行','无人保活，云端自动恢复。');
  ops.setAttribute('id','operations');
  const facts=node('dl',undefined,{class:'system-facts'});
  facts.append(fact('版本',report.application_version||'—'));
  facts.append(fact('本轮生成',time(report.generated_at)));
  facts.append(fact('报价观察',time(report.quote_observed_at)));
  facts.append(fact('自动交易','永久关闭'));
  ops.append(facts);
  app.append(ops);
  app.append(renderCoordination(report));
}
async function refresh(){try{const response=await fetch('/api/v1/report/latest',{headers:{Accept:'application/json'},cache:'no-store'});const report=await response.json();if(!response.ok||report.state==='SYSTEM_BLOCKED'){renderBlocked(report);return}if(report.state==='DATA_READY'){renderReady(report);return}renderBlocked(report)}catch(_error){renderBlocked()}}
refresh();setInterval(refresh,30000);
