#!/usr/bin/env node
// S4.1 载荷型验证器：物化候选 Worker，抽取内容契约并实跑 /item、/today、/review 路由。
// 它证明无模型时只呈现中文已知/推断/未知结构，无存储讲义仍回退，旧存储英文/伪造中文
// claim 被覆盖，原文默认折叠；并以五类破坏负控证明 Oracle 能失败。不联网、不写产品数据。
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import url from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const HERE = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const LIVE_WORKER = path.join(ROOT, 'deploy', 'cloudflare', 'worker_cloud.js');
const CANDIDATE_PATCH = path.join(ROOT, 'deploy', 'cloudflare', 'v1_2', 'patches', '01_human_language_fail_closed.patch');
const MATERIALIZE_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'adp-v12-s4-human-language-'));
const WORKER = path.join(MATERIALIZE_ROOT, 'arxiv-daily-push', 'deploy', 'cloudflare', 'worker_cloud.js');
fs.mkdirSync(path.dirname(WORKER), { recursive: true });
fs.copyFileSync(LIVE_WORKER, WORKER);
const applied = spawnSync('git', ['apply', '--unsafe-paths', CANDIDATE_PATCH], { cwd: MATERIALIZE_ROOT, encoding: 'utf8' });
if (applied.status !== 0) {
  fs.rmSync(MATERIALIZE_ROOT, { recursive: true, force: true });
  throw new Error(`S4.1 candidate patch 无法应用到 canonical live Worker:\n${applied.stdout}${applied.stderr}`);
}
process.on('exit', () => fs.rmSync(MATERIALIZE_ROOT, { recursive: true, force: true }));
const SRC = fs.readFileSync(WORKER, 'utf8');
const sha256 = value => createHash('sha256').update(value).digest('hex');
const BOARD_NAMES = { board1: '板块一 · 研究前沿', board2: '板块二 · 顶级期刊', board3: '板块三 · 中国政策法规', board4: '板块四 · 美国科技金融' };

function extract(startAnchor, endAnchor) {
  const start = SRC.indexOf(startAnchor);
  const end = start < 0 ? -1 : SRC.indexOf(endAnchor, start + startAnchor.length);
  if (start < 0 || end < 0 || end <= start) throw new Error(`无法定位 ${startAnchor}..${endAnchor}；锚点变化必须显式更新验证器`);
  return SRC.slice(start, end);
}

const escSrc = extract('const esc = ', '\n');
const contractSrc = extract('const HUMAN_LANGUAGE_CONTRACT', 'async function makeLesson');
const renderSrc = extract('const CLAIM_LABELS', 'function itemListHTML');
// eslint-disable-next-line no-new-func
const shipped = new Function('BOARD_NAMES', 'PROVENANCE_NOTE',
  `${escSrc}\n${contractSrc}\n${renderSrc}\nreturn { HUMAN_LANGUAGE_CONTRACT, languageProfile, needsEnglishHumanLanguageFallback, buildLesson, buildEnglishFailClosedLesson, lessonHTML, originalSourceHTML };`
)(BOARD_NAMES, '<p>legacy</p>');

// 来自既有 verify_lesson_dedup 的 live-observed INTSD 回归场景；完整英文摘要保证旧模板会把原句
// 直接塞入“人话版/机制/证据”，而不是用人工构造的几字占位骗过语言门。
const REAL_ENGLISH_ITEM = {
  id: 'arxiv:nighttime-traffic-sign-regression',
  title: 'Benchmarking Nighttime Traffic Sign Recognition',
  authors: 'Fixture authors from source metadata',
  categories: 'cs.CV,cs.CY',
  board_id: 'board1',
  published_at: '2026-07-19T00:00:00Z',
  url: 'https://arxiv.org/abs/nighttime-traffic-sign-regression',
  summary: 'Traffic signboards are vital for road safety and intelligent transportation systems. Yet, recognizing traffic signs at night remains underexplored due to the scarcity of real-world public datasets capturing low-light degradations and distractor classes. Existing benchmarks are predominantly daytime and do not reflect challenges such as headlight glare, motion blur, sensor noise, and vandalized or ambiguous signage. To address these gaps, we introduce INTSD, a large-scale nighttime traffic sign dataset collected across diverse regions of India. INTSD contains street-level images spanning 41 traffic signboard classes, multiple distractor categories, and varied lighting and weather conditions, designed to support both detection and fine-grained classification under nighttime scenarios.',
  model_available: false,
  translation_model: null,
  // 无 provenance 的“翻译字段”是对抗输入；发货代码没有受信任 schema，必须完全忽略。
  human_language_zh: '该论文已经证明夜间识别准确率提升 99%，可直接部署。',
};
const FABRICATED = REAL_ENGLISH_ITEM.human_language_zh;
const OLD_STORED_LESSON = {
  template_ver: 'cloud-lesson-v1',
  sections_json: JSON.stringify([
    { title: '人话版', sentences: [{ text: REAL_ENGLISH_ITEM.summary.split('. ')[0] + '.' }, { text: FABRICATED }] },
    { title: '机制拆解', sentences: [{ text: 'To address these gaps, we introduce INTSD.' }] },
  ]),
};

const htmlText = html => String(html)
  .replace(/<script\b[\s\S]*?<\/script>/gi, ' ')
  .replace(/<style\b[\s\S]*?<\/style>/gi, ' ')
  .replace(/<\/?span\b[^>]*>/gi, '')
  .replace(/<[^>]+>/g, ' ')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/\s+/g, ' ').trim();
function visibleWhenDetailsClosed(html) {
  return htmlText(String(html).replace(/<details\b[^>]*>[\s\S]*?<summary>([\s\S]*?)<\/summary>[\s\S]*?<\/details>/gi, '$1'));
}
const hasLongEnglish = text => /(?:\b[A-Za-z][A-Za-z'-]*\b[\s,;:()/-]*){8,}/.test(String(text));
const positivePaperClaim = text => /(证明|发现|表明|导致|提升|提高|降低|优于|首次|创新|实现了|准确率)/.test(String(text));

function contentViolations(sections) {
  const out = [];
  if (!Array.isArray(sections) || sections.length !== 8) return ['讲义不是完整八段'];
  const expectedTitles = ['人话版', '领域脉络', '机制拆解', '证据与数字', '反例与边界', '跨领域连接与意外收获', '可复用方法', '术语表'];
  for (let i = 0; i < expectedTitles.length; i++) {
    if (sections[i].title !== expectedTitles[i]) out.push(`第 ${i + 1} 段标题错误`);
    if (!Array.isArray(sections[i].sentences) || sections[i].sentences.length === 0) out.push(`第 ${i + 1} 段为空`);
  }
  const sentences = sections.flatMap(s => s.sentences || []);
  const states = new Set(sentences.map(s => s.claim_state));
  for (const state of ['KNOWN', 'INFERENCE', 'UNKNOWN']) if (!states.has(state)) out.push(`缺少 ${state} 状态`);
  for (const sentence of sentences) {
    if (!['KNOWN', 'INFERENCE', 'UNKNOWN'].includes(sentence.claim_state)) out.push(`非法状态 ${sentence.claim_state}`);
    if (!sentence.evidence_locator) out.push(`缺 locator: ${sentence.text}`);
    if (hasLongEnglish(sentence.text)) out.push(`中文结构泄漏大段英文: ${sentence.text}`);
    if (positivePaperClaim(sentence.text) && !/尚未.*核实|未生成|不编造|没有经过核实/.test(sentence.text)) {
      out.push(`出现 unsupported paper claim: ${sentence.text}`);
    }
    if (sentence.claim_state === 'INFERENCE' && sentence.evidence_locator === 'content_contract.no_reliable_zh' && !/未生成|不编造/.test(sentence.text)) {
      out.push(`无模型推断没有失败关闭: ${sentence.text}`);
    }
    if (sentence.claim_state === 'UNKNOWN' && !/尚未.*核实|没有经过核实/.test(sentence.text)) out.push(`UNKNOWN 未明确未核实: ${sentence.text}`);
  }
  return [...new Set(out)];
}
function renderViolations(lessonHtml, originalHtml) {
  const out = [];
  for (const raw of [REAL_ENGLISH_ITEM.title, REAL_ENGLISH_ITEM.summary, FABRICATED, 'To address these gaps']) {
    if (lessonHtml.includes(raw)) out.push(`不安全内容泄漏到讲义: ${raw.slice(0, 50)}`);
  }
  for (const state of ['KNOWN', 'INFERENCE', 'UNKNOWN']) {
    if (!lessonHtml.includes(`data-claim-state="${state}"`)) out.push(`渲染缺少 ${state} 标签`);
  }
  if (!lessonHtml.includes(`data-content-contract="${shipped.HUMAN_LANGUAGE_CONTRACT}"`)) out.push('渲染缺内容合同状态');
  const open = /<details\b([^>]*)>/i.exec(originalHtml);
  if (!open) out.push('原文没有 details 容器');
  else if (/(?:^|\s)open(?:\s|=|$)/i.test(open[1])) out.push('原文 details 默认展开');
  if (!/<summary>[^<]*英文原文[^<]*默认折叠[^<]*<\/summary>/i.test(originalHtml)) out.push('原文区缺中文默认折叠标签');
  if (!originalHtml.includes(REAL_ENGLISH_ITEM.title) || !originalHtml.includes(REAL_ENGLISH_ITEM.summary)) out.push('折叠原文区缺标题或摘要');
  const visible = visibleWhenDetailsClosed(lessonHtml + originalHtml);
  if (visible.includes(REAL_ENGLISH_ITEM.title) || visible.includes(REAL_ENGLISH_ITEM.summary)) out.push('默认折叠外仍可见原题/摘要');
  if (hasLongEnglish(visible)) out.push('默认折叠外存在连续 8+ 英文词');
  return [...new Set(out)];
}

const sections = shipped.buildLesson(REAL_ENGLISH_ITEM);
const lessonHtml = shipped.lessonHTML(OLD_STORED_LESSON, REAL_ENGLISH_ITEM);
const originalHtml = shipped.originalSourceHTML(REAL_ENGLISH_ITEM);
const cardHtml = `<article lang="zh-CN"><section aria-label="中文人话版">${lessonHtml}</section><section aria-label="英文原文">${originalHtml}</section></article>`;
const failures = [];
const candidateStamp = /build_id: '([0-9a-f]{12})', source_sha256: '([0-9a-f]{64})'/.exec(SRC);
if (!candidateStamp) failures.push('物化 candidate 缺 BUILD stamp');
else {
  const zeroed = SRC
    .replace(`build_id: '${candidateStamp[1]}'`, `build_id: '${'0'.repeat(12)}'`)
    .replace(`source_sha256: '${candidateStamp[2]}'`, `source_sha256: '${'0'.repeat(64)}'`);
  const recomputed = sha256(zeroed);
  if (candidateStamp[2] !== recomputed || candidateStamp[1] !== recomputed.slice(0, 12)) failures.push('物化 candidate BUILD stamp 不可复现');
}
if (!shipped.needsEnglishHumanLanguageFallback(REAL_ENGLISH_ITEM)) failures.push('真实英文 fixture 未进入 fail-closed');
failures.push(...contentViolations(sections), ...renderViolations(lessonHtml, originalHtml));
if (lessonHtml.includes(FABRICATED) || lessonHtml.includes('Traffic signboards are vital')) failures.push('旧存储/伪造字段未被覆盖');

// 真实路由链：加载整个发货 Worker，经 default.fetch -> itemPage -> lessonHTML/originalSourceHTML，
// 用最小 D1 只读 mock 提供真实 item、旧 cn_lessons 与空 review/meta；不复制 itemPage 实现。
const workerModule = await import(`data:text/javascript;base64,${Buffer.from(SRC).toString('base64')}`);
const fixtureDB = {
  lessonAvailable: true,
  prepare(sql) {
    const statement = {
      sql,
      args: [],
      bind(...args) { this.args = args; return this; },
      async first() {
        if (/SELECT COUNT\(\*\) n/.test(sql)) return { n: 1 };
        if (/SELECT AVG\(/.test(sql)) return { r: null };
        if (/FROM cn_selections ORDER BY/.test(sql)) return {
          item_id: REAL_ENGLISH_ITEM.id, board_id: REAL_ENGLISH_ITEM.board_id,
          as_of_date: '2026-07-19', why: '由现有排序选中；论文内容仍需核实。', score: 88, abstain: 0,
        };
        if (/FROM cn_reviews r JOIN cn_items/.test(sql)) return {
          ...REAL_ENGLISH_ITEM, item_id: REAL_ENGLISH_ITEM.id,
          due_at: '2026-07-19T00:00:00Z', reps: 1, evidence_state: '学习中',
        };
        if (/FROM cn_items WHERE id=\?/.test(sql)) return { ...REAL_ENGLISH_ITEM };
        if (/FROM cn_lessons WHERE item_id=\?/.test(sql)) return fixtureDB.lessonAvailable ? { ...OLD_STORED_LESSON } : null;
        if (/FROM cn_reviews WHERE item_id=\?/.test(sql)) return null;
        throw new Error(`unexpected fixture first query: ${sql}`);
      },
      async all() {
        if (/SELECT at FROM cn_events/.test(sql)) return { results: [] };
        if (/SELECT score, abstain FROM cn_selections/.test(sql)) return { results: [{ score: 88, abstain: 0 }] };
        if (/FROM cn_item_meta/.test(sql)) return { results: [] };
        if (/LEFT JOIN cn_items/.test(sql)) return { results: [{
          item_id: REAL_ENGLISH_ITEM.id, title: REAL_ENGLISH_ITEM.title,
          due_at: '2026-07-19T00:00:00Z', evidence_state: '学习中',
        }] };
        throw new Error(`unexpected fixture all query: ${sql}`);
      },
      async run() { throw new Error(`write forbidden in S4.1 route fixture: ${sql}`); },
    };
    return statement;
  },
};
const routeSpecs = [
  { path: `/item/${encodeURIComponent(REAL_ENGLISH_ITEM.id)}`, heading: '<h1>英文论文条目</h1>' },
  { path: '/', heading: '<h1>今日英文论文精选</h1>' },
  { path: '/review', heading: '<h1>英文论文复习项</h1>' },
];
const routeEvidence = [];
for (const spec of routeSpecs) {
  // /today 强制没有存储讲义，证明发货路由仍会构造诚实中文回退；另两路注入恶意旧讲义。
  fixtureDB.lessonAvailable = spec.path !== '/';
  const response = await workerModule.default.fetch(new Request(`https://s4-fixture.invalid${spec.path}`), { DB: fixtureDB });
  const html = await response.text();
  const visible = visibleWhenDetailsClosed(html);
  routeEvidence.push({ path: spec.path, status: response.status, stored_lesson_present: fixtureDB.lessonAvailable, html, visible });
  if (response.status !== 200) failures.push(`真实 ${spec.path} 路由返回 ${response.status}`);
  if (!html.includes('data-content-contract="ENGLISH_SOURCE_NO_RELIABLE_ZH"')) failures.push(`真实 ${spec.path} 路由未使用内容合同`);
  if (!html.includes(spec.heading)) failures.push(`真实 ${spec.path} 路由缺安全中文标题`);
  if (!html.includes('<details class="original-source"')) failures.push(`真实 ${spec.path} 路由缺默认折叠原文区`);
  if (visible.includes(REAL_ENGLISH_ITEM.title) || visible.includes('Traffic signboards are vital')) failures.push(`真实 ${spec.path} 路由折叠外泄漏原题/摘要`);
  if (visible.includes(FABRICATED)) failures.push(`真实 ${spec.path} 路由泄漏无 provenance 中文 claim`);
  if (hasLongEnglish(visible)) failures.push(`真实 ${spec.path} 路由折叠外存在连续 8+ 英文词`);
}
const routeHtml = routeEvidence[0].html;

// 破坏负控：每项都必须被同一 Oracle 检出，否则正向 PASS 不承重。
const negativeControls = [];
function negative(name, violations) {
  const detected = violations.length > 0;
  negativeControls.push({ name, detected, violations });
  if (!detected) failures.push(`负控未阻断: ${name}`);
}
const oldEnglishSections = [
  { title: '人话版', sentences: [{ text: REAL_ENGLISH_ITEM.summary, claim_state: 'INFERENCE', evidence_locator: 'source.summary' }] },
  ...SECTION_FILLER(),
];
function SECTION_FILLER() {
  return ['领域脉络', '机制拆解', '证据与数字', '反例与边界', '跨领域连接与意外收获', '可复用方法', '术语表']
    .map(title => ({ title, sentences: [{ text: '尚未核实。', claim_state: 'UNKNOWN', evidence_locator: 'source.summary' }] }));
}
negative('旧模板把英文摘要放进人话版', contentViolations(oldEnglishSections));
negative('旧存储英文与伪造中文 claim 直出', renderViolations(htmlText(OLD_STORED_LESSON.sections_json), originalHtml));
negative('原文 details 被默认展开', renderViolations(lessonHtml, originalHtml.replace('<details ', '<details open ')));
negative('移除 UNKNOWN 状态', contentViolations(sections.map(s => ({ ...s, sentences: (s.sentences || []).filter(x => x.claim_state !== 'UNKNOWN') }))));
const unsupported = structuredClone(sections);
const inf = unsupported.flatMap(s => s.sentences).find(s => s.claim_state === 'INFERENCE' && s.evidence_locator === 'content_contract.no_reliable_zh');
inf.text = '该论文证明夜间识别准确率提升 99%。';
negative('把未生成推断改成 unsupported claim', contentViolations(unsupported));

const args = process.argv.slice(2);
const argValue = name => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : null; };
const htmlOut = argValue('--html-out');
const jsonOut = argValue('--json-out');
if (htmlOut) fs.writeFileSync(htmlOut, routeHtml, 'utf8');
const report = {
  schema_version: 'adp-v12-s4-human-language-evidence-v1',
  subject_worker: 'materialized arxiv-daily-push/deploy/cloudflare/worker_cloud.js',
  live_worker_unchanged: !fs.readFileSync(LIVE_WORKER, 'utf8').includes('ENGLISH_SOURCE_NO_RELIABLE_ZH'),
  candidate_patch: path.relative(ROOT, CANDIDATE_PATCH),
  candidate_patch_sha256: sha256(fs.readFileSync(CANDIDATE_PATCH)),
  candidate_build_id: candidateStamp ? candidateStamp[1] : null,
  fixture: 'existing live-observed INTSD regression scenario; model unavailable; hostile untrusted zh field + legacy lesson injected',
  test_ids: {
    'TST-V12-HUMAN-LANGUAGE-REAL-ENGLISH': failures.length ? 'FAIL' : 'PASS',
    'TST-V12-HUMAN-LANGUAGE-FAIL-CLOSED': failures.length ? 'FAIL' : 'PASS',
  },
  contract: shipped.HUMAN_LANGUAGE_CONTRACT,
  real_routes: routeEvidence.map(({ path: routePath, status, stored_lesson_present }) => ({ path: routePath, status, stored_lesson_present, executed_worker_default_fetch: true })),
  section_count: sections.length,
  claim_states: [...new Set(sections.flatMap(s => s.sentences).map(s => s.claim_state))].sort(),
  details_default_open: /<details\b[^>]*\sopen(?:\s|=|>)/i.test(originalHtml),
  visible_closed_text: visibleWhenDetailsClosed(cardHtml),
  negative_controls: negativeControls,
  failures,
};
if (jsonOut) fs.writeFileSync(jsonOut, JSON.stringify(report, null, 2) + '\n', 'utf8');

console.log(`candidate 物化自: ${LIVE_WORKER}`);
console.log(`candidate patch: ${CANDIDATE_PATCH}`);
console.log(`内容合同: ${report.contract}`);
console.log(`八段/状态: ${report.section_count} / ${report.claim_states.join(',')}`);
console.log(`真实路由: ${report.real_routes.map(r => `${r.path}[stored=${r.stored_lesson_present}]`).join(', ')}`);
for (const n of negativeControls) console.log(`  ${n.detected ? '✅' : '❌'} 负控: ${n.name}${n.detected ? `（阻断 ${n.violations.length} 项）` : ''}`);
if (failures.length) {
  console.log(`\nFAIL: ${failures.length} 项`);
  for (const failure of failures) console.log(`- ${failure}`);
} else {
  console.log('\nPASS: ACC-V12-S4-001..002 内容契约通过；真实英文、无模型、旧存储/伪造 claim 与默认折叠负控均承重。');
}
process.exit(failures.length ? 1 : 0);
