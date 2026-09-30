// 测试夹具：脚本化的 fetch（不联网）、OAI/RSS/bioRxiv 假数据、临时数据目录、零等待计时器。
// 所有假数据都是自造的，不含真实论文或私人信息。
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const today = () => new Date().toISOString().slice(0, 10);

export function tmpDataDir() {
  const dir = mkdtempSync(join(tmpdir(), 'adp-selfhost-'));
  return { dir, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

// 让 worker 内部「每页 2s→4s」的退避与任务级退避在测试里不真等。只在测试进程里改，不属于产品代码。
export function fastTimers() {
  const orig = globalThis.setTimeout;
  // 只压缩 50ms~10s 的退避（worker 页内退避最长 8s）；任务级 20 分钟的看门狗计时器保持真实。
  globalThis.setTimeout = (fn, ms, ...a) => orig(fn, ms > 50 && ms <= 10000 ? 0 : ms, ...a);
  return () => { globalThis.setTimeout = orig; };
}

export function oaiXml(n, { token = null, prefix = '2609' } = {}) {
  const d = today();
  const recs = Array.from({ length: n }, (_, i) => `<record><header><identifier>oai:arXiv.org:${prefix}.${String(10000 + i)}</identifier><datestamp>${d}</datestamp></header>
<metadata><arXiv><id>${prefix}.${String(10000 + i)}</id><created>${d}</created><authors><author><keyname>Tester${i}</keyname><forenames>A</forenames></author></authors>
<title>Fixture paper ${i} on sparse attention and retrieval</title><categories>cs.AI cs.LG</categories>
<abstract>We study fixture problem ${i}. We propose a method and show it improves accuracy on a synthetic benchmark. Limitations are discussed.</abstract></arXiv></metadata></record>`).join('\n');
  return `<?xml version="1.0"?><OAI-PMH><ListRecords>${recs}${token ? `<resumptionToken>${token}</resumptionToken>` : ''}</ListRecords></OAI-PMH>`;
}

export function rssXml(tag) {
  const d = new Date().toUTCString();
  return `<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel><title>${tag}</title>` +
    [1, 2, 3].map((i) => `<item><title>${tag} fixture story ${i}</title><link>https://example.test/${tag}/${i}</link><description>Summary ${i} for ${tag}.</description><pubDate>${d}</pubDate><guid>${tag}-${i}</guid></item>`).join('') +
    '</channel></rss>';
}

export const biorxivJson = () => JSON.stringify({ collection: [1, 2, 3].map((i) => ({ doi: `10.1101/2609.0000${i}`, title: `bioRxiv fixture ${i}`, abstract: 'A synthetic abstract.', category: 'neuroscience', authors: 'Nobody, A.', date: today() })) });

// 按 URL 分流的 fetch 桩。arxiv: 'ok' | 'fail503' | 'timeout' | 函数(callIndex)；其余来源固定。
export function installFetch({ arxiv = 'ok', arxivItems = 30 } = {}) {
  const orig = globalThis.fetch;
  const calls = { arxiv: 0, other: 0, urls: [] };
  globalThis.fetch = async (input, init = {}) => {
    const url = String(input?.url || input);
    calls.urls.push(url);
    if (url.includes('oaipmh.arxiv.org') || url.includes('export.arxiv.org')) {
      calls.arxiv++;
      const mode = typeof arxiv === 'function' ? arxiv(calls.arxiv) : arxiv;
      if (mode === 'fail503') return new Response('busy', { status: 503 });
      if (mode === 'timeout') { const e = new Error('The operation was aborted due to timeout'); e.name = 'TimeoutError'; throw e; }
      return new Response(oaiXml(arxivItems), { status: 200, headers: { 'content-type': 'text/xml' } });
    }
    calls.other++;
    if (url.includes('api.biorxiv.org')) return new Response(biorxivJson(), { status: 200 });
    if (url.includes('api.openalex.org')) return new Response(JSON.stringify({ results: [], meta: {} }), { status: 200 });
    if (/gov\.cn|ndrc|cac\./.test(url)) return new Response('nope', { status: 404 });
    return new Response(rssXml(new URL(url).hostname), { status: 200, headers: { 'content-type': 'application/rss+xml' } });
  };
  return { calls, restore: () => { globalThis.fetch = orig; } };
}
