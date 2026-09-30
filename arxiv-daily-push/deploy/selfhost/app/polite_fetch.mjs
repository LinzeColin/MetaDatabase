// 对 arXiv 各主机（arxiv.org / export.arxiv.org / oaipmh.arxiv.org）的出站请求限速：任意两次请求的起点至少间隔 3 秒。
//
// 为什么自托管要自己做：Cloudflare Worker 有「每次调用 50 个子请求」的硬顶，worker_cloud.js 的分页/回填因此
// 天然很克制；搬到 Node 之后没有这个顶，代码里也没有请求间隔。arXiv 的 API 使用条款要求单连接每 3 秒至多 1 次请求，
// 违反会被封 IP（整个 VPS 出口，连带其它项目）。所以在进程内的 globalThis.fetch 外面包一层，worker 代码一字不改。
//
// 并发安全：多个请求同时发起时按「预约槽位」排队（每个槽位比上一个晚 minIntervalMs），不会一起冲出去。
// 只限 arXiv 主机，其它来源（RSS、bioRxiv、OpenAlex）不受影响。
const ARXIV_HOST = /(^|\.)arxiv\.org$/i;

export function makePoliteFetch(inner, { minIntervalMs = 3000, hostRe = ARXIV_HOST, now = () => Date.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
  let nextSlot = 0;
  const polite = async function politeFetch(input, init) {
    let host = '';
    try { host = new URL(typeof input === 'string' ? input : (input?.url ?? String(input))).hostname; } catch { /* 交给 inner 报错 */ }
    if (minIntervalMs > 0 && hostRe.test(host)) {
      const t = now();
      const slot = Math.max(t, nextSlot);
      nextSlot = slot + minIntervalMs;
      if (slot > t) await sleep(slot - t);
    }
    return inner(input, init);
  };
  polite.isPolite = true;
  return polite;
}

// 给当前进程的 globalThis.fetch 套上限速；返回还原函数。重复安装是空操作（不会套两层）。
export function installPoliteFetch(opts = {}) {
  const minIntervalMs = opts.minIntervalMs ?? Number(process.env.ADP_ARXIV_MIN_INTERVAL_MS ?? 3000);
  const orig = globalThis.fetch;
  if (orig?.isPolite || !(minIntervalMs > 0)) return () => { };
  const wrapped = makePoliteFetch((...a) => orig(...a), { ...opts, minIntervalMs });
  globalThis.fetch = wrapped;
  return () => { if (globalThis.fetch === wrapped) globalThis.fetch = orig; };
}
