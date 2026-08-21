const $ = id => document.getElementById(id);
const META = ['运行时间','提示词版本','运行状态','市场覆盖','数据截止','状态连续性','裁决完整性','技能适用覆盖率'];
const FIRST = ['唯一操作','唯一平台','唯一标的','代码','唯一方向','可观察回撤','风险调整回撤','剩余回撤预算','预期研究窗口','相对宽基','相对现金','现在怎么做','核心依据','最大反证','失效条件','下一正式复核'];
const SECOND = ['适用技能','实际参与','适用覆盖率','原生参与','原生覆盖率','中央定量审查','权重说明'];
let remaining = 15;
let lastReportAt = 0;

function text(id, value) { const node = $(id); if (node) node.textContent = value ?? '—'; }
function conclusionClass(value) { return value === '支持' ? 'support' : value === '反对' ? 'oppose' : 'neutral'; }
function render(report) {
  META.forEach(key => text(key, report[key]));
  const first = report['第一板块'] || {};
  FIRST.forEach(key => text(key, first[key]));
  const second = report['第二板块'] || {};
  SECOND.forEach(key => text(key, second[key]));
  const body = $('技能矩阵');
  body.innerHTML = '';
  for (const row of second['矩阵'] || []) {
    const tr = document.createElement('tr');
    const keys = ['技能','适用状态','运行方式','弃权主原因','方法家族','原始权重','家族内权重','总体权重','结论','独立性'];
    for (const key of keys) {
      const td = document.createElement('td');
      td.textContent = row[key] ?? '—';
      if (key === '结论') td.className = conclusionClass(row[key]);
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  if (!body.children.length) body.innerHTML = '<tr><td colspan="10">六技能矩阵尚未形成</td></tr>';
  lastReportAt = Date.now();
  remaining = 15;
}

async function jsonGet(path) {
  const response = await fetch(path, {headers:{Accept:'application/json'}, cache:'no-store'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function fetchLatest() { render(await jsonGet('/api/v1/report/latest')); }

async function fetchHeartbeat() {
  const heartbeat = await jsonGet('/api/v1/heartbeat');
  text('api_state', heartbeat.api_state);
  text('report_state', heartbeat.report_state);
  text('application_version', heartbeat.application_version);
  text('quote_observed_at', heartbeat.quote_observed_at);
  text('last_decision_id', heartbeat.last_decision_id);
  text('observation_count', heartbeat.observation_count);
  text('decision_count', heartbeat.decision_count);
  text('unchanged_observations', heartbeat.unchanged_observations);
  text('heartbeat_next_review', heartbeat.next_formal_review);
  text('profitability_status', heartbeat.profitability_status);
  text('connection', heartbeat.report_state === '通' ? 'API每秒已确认' : 'API通，报告不确定');
  $('live-dot').className = heartbeat.report_state === '通' ? 'ok' : 'warn';
}

async function fetchSkillHistory() {
  const payload = await jsonGet('/api/v1/whitebox/skills');
  const body = $('whitebox-skills');
  body.innerHTML = '';
  for (const row of payload.items || []) {
    const tr = document.createElement('tr');
    const values = [
      row.display_name,
      row.matured_count,
      row.correct_count,
      row.opposite_count,
      row.invalid_count,
      `${Number(row.value_score_pct || 0).toFixed(1)}%`,
      row.trend,
      `${Number(row.shadow_weight_pct || 0).toFixed(1)}%`,
    ];
    for (const value of values) {
      const td = document.createElement('td');
      td.textContent = value ?? '—';
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  if (!body.children.length) body.innerHTML = '<tr><td colspan="8">白箱Skill账本尚未形成</td></tr>';
}

function connectStream() {
  const stream = new EventSource('/api/v1/stream');
  stream.addEventListener('report', event => {
    try { render(JSON.parse(event.data)); } catch (_) {}
  });
  stream.onerror = () => { text('connection','流连接重试中，API仍每秒确认'); $('live-dot').className='warn'; };
}

setInterval(() => {
  remaining = Math.max(0, remaining - 1);
  text('countdown', `${remaining}s`);
  if (Date.now() - lastReportAt > 30000) $('live-dot').className='warn';
}, 1000);

fetchLatest().catch(() => text('connection','等待首轮报告'));
fetchHeartbeat().catch(() => { text('connection','API未确认'); $('live-dot').className='warn'; });
fetchSkillHistory().catch(() => {});
connectStream();
setInterval(() => fetchHeartbeat().catch(() => { text('connection','API未确认'); $('live-dot').className='warn'; }), 1000);
setInterval(() => { fetchLatest().catch(() => {}); fetchSkillHistory().catch(() => {}); }, 15000);
