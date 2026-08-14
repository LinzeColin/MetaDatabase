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
  text('connection', '15秒实时更新');
  $('live-dot').className = 'ok';
}
async function fetchLatest() {
  const response = await fetch('/api/v1/report/latest', {headers:{Accept:'application/json'}, cache:'no-store'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  render(await response.json());
}
function connectStream() {
  const stream = new EventSource('/api/v1/stream');
  stream.addEventListener('report', event => {
    try { render(JSON.parse(event.data)); } catch (_) {}
  });
  stream.onopen = () => { text('connection','15秒实时更新'); $('live-dot').className='ok'; };
  stream.onerror = () => { text('connection','流连接重试中'); $('live-dot').className='warn'; };
}
setInterval(() => {
  remaining = Math.max(0, remaining - 1);
  text('countdown', `${remaining}s`);
  if (Date.now() - lastReportAt > 30000) {
    text('connection','结果可能滞后');
    $('live-dot').className='warn';
  }
}, 1000);
fetchLatest().catch(() => { text('connection','等待首轮报告'); $('live-dot').className='warn'; });
connectStream();
setInterval(() => fetchLatest().catch(() => {}), 15000);
