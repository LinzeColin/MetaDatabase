// 对 arXiv 各主机（arxiv.org / export.arxiv.org / oaipmh.arxiv.org）的出站请求限速：任意两次请求的起点至少间隔 3 秒。
//
// 为什么自托管要自己做：Cloudflare Worker 有「每次调用 50 个子请求」的硬顶，worker_cloud.js 的分页/回填因此
// 天然很克制；搬到 Node 之后没有这个顶，代码里也没有请求间隔。arXiv 的 API 使用条款要求单连接每 3 秒至多 1 次请求，
// 违反会被封 IP（整个 VPS 出口，连带其它项目）。所以在进程内的 globalThis.fetch 外面包一层，worker 代码一字不改。
//
// 并发安全：所有 arXiv 请求串成一条 promise 链——每个请求等上一个请求「真正放行」之后，再等到「上一次实际放行时刻 + minIntervalMs」才放行。
// 间隔按【实际放行时刻】算，不按预约槽位算：定时器晚醒一点，后面的请求也跟着顺延，真实间隔永远 ≥ minIntervalMs（不会被抖动吃掉）。
// 放行与调用 inner 之间没有任何 await，所以记录的放行时刻就是请求真正发出的时刻。
// 只限 arXiv 主机，其它来源（RSS、bioRxiv、OpenAlex）不受影响。
const ARXIV_HOST = /(^|\.)arxiv\.org$/i;

export function makePoliteFetch(inner, { minIntervalMs = 3000, hostRe = ARXIV_HOST, now = () => Date.now(), sleep = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
  let chain = Promise.resolve();
  let lastStart = -Infinity;
  const polite = async function politeFetch(input, init) {
    let host = '';
    try { host = new URL(typeof input === 'string' ? input : (input?.url ?? String(input))).hostname; } catch { /* 交给 inner 报错 */ }
    if (!(minIntervalMs > 0 && hostRe.test(host))) return inner(input, init);
    const prev = chain;
    let release; chain = new Promise((r) => { release = r; });
    try {
      await prev;
      // 循环而不是睡一次：定时器可能略早醒，醒来必须再核对一次真实时钟
      for (let wait = lastStart + minIntervalMs - now(); wait > 0; wait = lastStart + minIntervalMs - now()) await sleep(wait);
      lastStart = now();
    } finally { release(); }
    return inner(input, init);   // 与 lastStart = now() 同一个同步片段里发出
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
