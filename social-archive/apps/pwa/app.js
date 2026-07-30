const savedView = localStorage.getItem('sa-view');
const state = { items: [], view: savedView === 'list' ? 'feed' : (savedView === 'feed' || savedView === 'grid' ? savedView : 'grid') };
const $ = (id) => document.getElementById(id);
const escapeHtml = (s='') => String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const platformNames = {'generic-web':'通用网页','x':'X','reddit':'Reddit','instagram':'Instagram','tiktok':'TikTok','xiaohongshu':'小红书','douyin':'抖音','kuaishou':'快手','bilibili':'哔哩哔哩'};
const relationNames = {manual_save:'手动保存',bookmark:'书签',saved:'收藏',favorite:'喜欢/收藏',like:'点赞',upvoted:'赞同',watch_later:'稍后看',history:'历史',collection:'收藏夹'};
const needsUrl = new Set(['generic-web','tiktok','xiaohongshu','douyin','kuaishou']);

async function api(path, options={}) {
  const response = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
  if (!response.ok) {
    const body = await response.json().catch(()=>({detail:'请求失败'}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function dateText(value) {
  if (!value) return '时间未知';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium'}).format(date);
}

function renderItems(items) {
  state.items = items;
  const library = $('library');
  library.className = `library ${state.view}`;
  $('resultSummary').textContent = `${items.length} 条内容 · 默认 L0 / L1 / L3`;
  $('emptyState').classList.toggle('hidden', items.length !== 0);
  library.innerHTML = items.map(item => `
    <button class="card" data-id="${escapeHtml(item.id)}" aria-label="打开 ${escapeHtml(item.title || item.canonical_url)}">
      <div class="card-cover"><span class="platform-tag">${escapeHtml(platformNames[item.platform] || item.platform)}</span></div>
      <div class="card-body">
        <h3>${escapeHtml(item.title || '未命名内容')}</h3>
        <p>${escapeHtml(item.author_name || item.canonical_url || '')}</p>
        <div class="card-meta"><span>${escapeHtml(relationNames[item.relation_type] || item.relation_type || '已保存')} · ${dateText(item.last_observed_at)}</span>
          <span class="level-badges"><span class="level">L0</span><span class="level">L1</span>${Number(item.artifact_count)>1?'<span class="level">L3</span>':''}</span>
        </div>
      </div>
    </button>`).join('');
  library.querySelectorAll('.card').forEach(card => card.addEventListener('click', () => openDetail(card.dataset.id)));
}

async function loadLibrary() {
  const params = new URLSearchParams();
  const q = $('search').value.trim();
  const platform = $('platformFilter').value;
  const relation = $('relationFilter').value;
  const collection = $('collectionFilter').value.trim();
  const observedFrom = $('observedFrom').value;
  const observedTo = $('observedTo').value;
  if (q) params.set('q', q); if (platform) params.set('platform', platform); if (relation) params.set('relation', relation);
  if (collection) params.set('collection', collection); if (observedFrom) params.set('observed_from', observedFrom); if (observedTo) params.set('observed_to', observedTo);
  try { const data = await api(`/v1/library?${params}`); renderItems(data.items || []); }
  catch (error) { $('resultSummary').textContent = `读取失败：${error.message}`; renderItems([]); }
}

async function runConnector(id, stateValue, button) {
  const body = {limit:20, requested_levels:['L0','L1','L3']};
  if (needsUrl.has(id)) {
    const value = window.prompt(`粘贴${platformNames[id] || id}中你本人可访问的链接`);
    if (!value) return;
    body.url = value;
  }
  if (id === 'x') body.relation_type = 'bookmark';
  if (id === 'reddit') body.relation_type = 'saved';
  button.disabled = true; button.textContent = '读取中…';
  try {
    const data = await api(`/v1/connectors/${encodeURIComponent(id)}/run`, {method:'POST', body:JSON.stringify(body)});
    alert(data.next_action_zh || `已导入 ${data.imported || 0} 条`);
    await Promise.all([loadLibrary(),loadConnectors(),loadQuota()]);
  } catch (error) {
    alert(`暂时不能读取：${error.message}\n你仍可使用浏览器扩展“保存当前页面”。`);
  } finally { button.disabled = false; button.textContent = stateValue === 'healthy' ? '读取/保存' : '尝试读取'; }
}

async function loadConnectors() {
  try {
    const data = await api('/v1/connectors');
    const items = data.items || [];
    const healthy = items.filter(x=>x.state==='healthy').length;
    $('connectorSummary').textContent = `${healthy}/${items.length} 可用`;
    $('connectors').innerHTML = items.map(x=>`<div class="connector" title="${escapeHtml(x.next_action_zh)}"><span class="dot ${escapeHtml(x.state)}"></span><span><strong>${escapeHtml(x.display_name)}</strong><small>${escapeHtml(x.next_action_zh)}</small></span><button class="connector-run" data-connector="${escapeHtml(x.connector_id)}" data-state="${escapeHtml(x.state)}">${x.state==='healthy'?'读取/保存':'尝试读取'}</button></div>`).join('');
    $('connectors').querySelectorAll('.connector-run').forEach(button => button.addEventListener('click', () => runConnector(button.dataset.connector, button.dataset.state, button)));
  } catch (error) { $('connectors').innerHTML = `<p class="muted">状态读取失败：${escapeHtml(error.message)}</p>`; }
}

async function loadQuota() {
  try {
    const data = await api('/v1/storage/status');
    const banner = $('quotaBanner');
    banner.textContent = data.message_zh || '';
    banner.classList.toggle('hidden', data.l3_allowed && !String(data.message_zh).includes('接近'));
  } catch (_) {}
}

async function openDetail(id) {
  try {
    const item = await api(`/v1/library/${encodeURIComponent(id)}`);
    const relations = Array.isArray(item.relations) ? item.relations : [];
    const relationPills = relations.length ? relations.map(relation => {
      const label = relationNames[relation.relation_type] || relation.relation_type || '已保存';
      const collection = relation.collection_key ? ` · ${relation.collection_key}` : '';
      return `<span class="pill">${escapeHtml(label + collection)}</span>`;
    }).join('') : '<span class="pill">已保存</span>';
    const relationHistory = relations.length ? `<section class="relation-history" aria-label="关系历史"><h3>关系历史</h3><ul>${relations.map(relation => {
      const label = relationNames[relation.relation_type] || relation.relation_type || '已保存';
      const collection = relation.collection_key ? ` · ${relation.collection_key}` : '';
      const status = relation.status === 'closed' ? '已关闭' : (relation.status === 'active' ? '生效中' : (relation.status || '状态未知'));
      const missing = Number(relation.missing_complete_scan_count || 0);
      const facts = [`首次 ${dateText(relation.first_observed_at)}`, `最近 ${dateText(relation.last_observed_at)}`];
      if (missing) facts.push(`完整扫描缺失 ${missing} 次`);
      if (relation.closed_at) facts.push(`关闭 ${dateText(relation.closed_at)}`);
      return `<li><strong>${escapeHtml(label + collection)}</strong><span>${escapeHtml(status)}</span><small>${escapeHtml(facts.join(' · '))}</small></li>`;
    }).join('')}</ul></section>` : '';
    let metadata = {};
    try { metadata = JSON.parse(item.metadata_json || '{}'); } catch (_) {}
    $('detailContent').innerHTML = `<div class="detail-header"><p class="eyebrow">${escapeHtml(platformNames[item.platform]||item.platform)}</p><h2>${escapeHtml(item.title||'未命名内容')}</h2><div class="detail-meta">${relationPills}<span class="pill">${(item.artifacts||[]).length} 个制品</span><span class="pill">${escapeHtml(item.availability||'observed')}</span></div><a class="detail-link" href="${escapeHtml(item.canonical_url)}" target="_blank" rel="noopener noreferrer">打开原始页面</a>${relationHistory}<div class="detail-text">${escapeHtml(metadata.text || item.author_name || '正文已归档在 L1 制品中。')}</div></div>`;
    $('detailDialog').showModal();
    history.replaceState(null,'',`/item/${id}`);
  } catch (error) { alert(`无法打开：${error.message}`); }
}


async function importSocialArchiverBundle() {
  const input = $('archiveFile');
  const file = input.files && input.files[0];
  const message = $('importMessage');
  if (!file) { message.textContent = '请先选择 ZIP 导出包。'; return; }
  if (!file.name.toLowerCase().endsWith('.zip')) { message.textContent = '只接受 ZIP 导出包。'; return; }
  const button = $('importArchive');
  button.disabled = true; button.textContent = '导入中…'; message.textContent = '正在安全读取 Markdown…';
  try {
    const response = await fetch('/v1/import/social-archiver', {
      method: 'POST',
      headers: {'X-Archive-Filename': file.name},
      body: file,
    });
    const result = await response.json().catch(()=>({detail:'导入失败'}));
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    message.textContent = result.message_zh || `已导入 ${result.imported || 0} 条。`;
    await Promise.all([loadLibrary(), loadConnectors(), loadQuota()]);
  } catch (error) {
    message.textContent = `导入失败：${error.message}`;
  } finally {
    button.disabled = false; button.textContent = '开始导入';
  }
}

function showWizard(){ $('wizardDialog').showModal(); }

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.view === state.view);
    button.addEventListener('click', () => { state.view=button.dataset.view; localStorage.setItem('sa-view',state.view); document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('active',x===button)); renderItems(state.items); });
  });
  $('searchButton').addEventListener('click', loadLibrary);
  $('search').addEventListener('keydown', e => { if(e.key==='Enter') loadLibrary(); });
  $('platformFilter').addEventListener('change', loadLibrary); $('relationFilter').addEventListener('change', loadLibrary);
  $('collectionFilter').addEventListener('change', loadLibrary); $('observedFrom').addEventListener('change', loadLibrary); $('observedTo').addEventListener('change', loadLibrary);
  $('refreshAll').addEventListener('click', () => Promise.all([loadLibrary(),loadConnectors(),loadQuota()]));
  $('openImport').addEventListener('click', ()=>$('importDialog').showModal());
  $('closeImport').addEventListener('click', ()=>$('importDialog').close());
  $('importArchive').addEventListener('click', importSocialArchiverBundle);
  $('openWizard').addEventListener('click', showWizard); $('emptyWizard').addEventListener('click', showWizard);
  $('closeWizard').addEventListener('click', ()=>$('wizardDialog').close()); $('closeDetail').addEventListener('click', ()=>$('detailDialog').close());
  $('detailDialog').addEventListener('close',()=>history.replaceState(null,'','/'));
  Promise.all([loadLibrary(),loadConnectors(),loadQuota()]);
  if('serviceWorker' in navigator) navigator.serviceWorker.register('/assets/sw.js').catch(()=>{});
});
