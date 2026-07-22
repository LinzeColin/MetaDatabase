/**
 * ADP v1.2 S1 Google News candidate fetch path.
 *
 * This module is intentionally not imported by worker_cloud.js. Bing remains the
 * live source until a later Run Contract authorizes an edge canary and live switch.
 */

export const GOOGLE_NEWS_FETCH_POLICY = Object.freeze({
  max_attempts: 3,
  retry_statuses: Object.freeze([502, 503, 504]),
  delays_ms: Object.freeze([1000, 3000]),
  timeout_ms: 15000,
  fallback_source_id: 'gnews-us-tech',
});

export const GOOGLE_NEWS_CANDIDATE_SOURCE = Object.freeze({
  source_id: 'gnews-us-tech-google-candidate',
  board_id: 'board4',
  provider: 'Google News RSS',
  feed_url: 'https://news.google.com/rss/search?q=FTC+antitrust&hl=en-US&gl=US&ceid=US%3Aen',
  state: 'candidate_not_live',
  live: false,
  fallback: Object.freeze({
    source_id: 'gnews-us-tech',
    provider: 'Bing News RSS',
    feed_url: 'https://www.bing.com/news/search?q=FTC+antitrust&format=rss&mkt=en-US',
    state: 'active_live',
  }),
});

const MAX_RSS_BYTES = 2_000_000;
const MAX_ITEMS = 20;

const defaultSleeper = (delayMs) => new Promise((resolve) => setTimeout(resolve, delayMs));

function decodeXml(value) {
  return String(value ?? '')
    .replace(/^<!\[CDATA\[([\s\S]*)\]\]>$/, '$1')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/&#(\d+);/g, (_, codePoint) => String.fromCodePoint(Number(codePoint)));
}

function stripMarkup(value) {
  return decodeXml(value).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function tagValue(block, tagName) {
  const match = block.match(new RegExp(`<${tagName}(?:\\s[^>]*)?>([\\s\\S]*?)</${tagName}>`, 'i'));
  return match ? decodeXml(match[1]).trim() : '';
}

/** Parse the actual Google News RSS shape into the existing feed item shape. */
export function parseGoogleNewsRss(xml) {
  const boundedXml = String(xml ?? '').slice(0, MAX_RSS_BYTES);
  const blocks = boundedXml.match(/<item[\s>][\s\S]*?<\/item>/gi) || [];
  const items = [];
  for (const block of blocks.slice(0, MAX_ITEMS)) {
    const title = stripMarkup(tagValue(block, 'title'));
    const link = tagValue(block, 'link').trim();
    if (!title || !/^https:\/\//i.test(link)) continue;
    const rawDate = tagValue(block, 'pubDate');
    const parsedDate = rawDate ? Date.parse(rawDate) : NaN;
    items.push({
      guid: tagValue(block, 'guid') || link,
      title,
      link,
      summary: stripMarkup(tagValue(block, 'description')).slice(0, 800),
      published: Number.isNaN(parsedDate) ? null : new Date(parsedDate).toISOString(),
    });
  }
  return items;
}

function isTimeout(error) {
  const name = String(error && error.name || '');
  const code = String(error && error.code || '');
  return name === 'AbortError' || name === 'TimeoutError' || code === 'ETIMEDOUT';
}

function timeoutSignal(timeoutMs) {
  return typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
    ? AbortSignal.timeout(timeoutMs)
    : undefined;
}

function resultPayload({ items = [], attempts, delays, terminalStatus, terminalHttpStatus = null, reasonCode }) {
  const success = reasonCode === 'SUCCESS';
  return {
    source_id: GOOGLE_NEWS_CANDIDATE_SOURCE.source_id,
    route_state: GOOGLE_NEWS_CANDIDATE_SOURCE.state,
    items,
    attempt_count: attempts.length,
    terminal_status: terminalStatus,
    terminal_http_status: terminalHttpStatus,
    reason_code: reasonCode,
    delays_ms: [...delays],
    fallback: { ...GOOGLE_NEWS_CANDIDATE_SOURCE.fallback },
    fallback_used: false,
    external_subrequests: attempts.length,
    write_allowed: false,
    persistence_action: success ? 'RETURN_ITEMS_NO_PERSIST' : 'NO_WRITE',
    attempts,
  };
}

function retryDelay(attemptNumber) {
  return GOOGLE_NEWS_FETCH_POLICY.delays_ms[attemptNumber - 1];
}

/**
 * Execute the real candidate path with deterministic dependency injection.
 * The function returns items/evidence only; it has no D1/R2 or live-route side effect.
 */
export async function fetchGoogleNewsCandidate({
  url = GOOGLE_NEWS_CANDIDATE_SOURCE.feed_url,
  fetcher = globalThis.fetch,
  sleeper = defaultSleeper,
  parser = parseGoogleNewsRss,
} = {}) {
  if (typeof fetcher !== 'function') throw new TypeError('fetcher must be a function');
  if (typeof sleeper !== 'function') throw new TypeError('sleeper must be a function');
  if (typeof parser !== 'function') throw new TypeError('parser must be a function');

  const attempts = [];
  const delays = [];
  for (let attempt = 1; attempt <= GOOGLE_NEWS_FETCH_POLICY.max_attempts; attempt++) {
    let response;
    try {
      const signal = timeoutSignal(GOOGLE_NEWS_FETCH_POLICY.timeout_ms);
      response = await fetcher(url, {
        headers: { 'User-Agent': 'ADP/1.2 google-news-candidate' },
        // Cloudflare counts every redirect hop as a subrequest. Fail closed on
        // 3xx so one attempt is provably one external subrequest.
        redirect: 'manual',
        ...(signal ? { signal } : {}),
      });
    } catch (error) {
      if (!isTimeout(error)) {
        attempts.push({ attempt, http_status: null, reason_code: 'FETCH_ERROR', retry_scheduled: false, delay_ms: null });
        return resultPayload({ attempts, delays, terminalStatus: 'FETCH_ERROR', reasonCode: 'FETCH_ERROR' });
      }
      const canRetry = attempt < GOOGLE_NEWS_FETCH_POLICY.max_attempts;
      const delayMs = canRetry ? retryDelay(attempt) : null;
      attempts.push({
        attempt,
        http_status: null,
        reason_code: canRetry ? 'TIMEOUT_RETRY' : 'TIMEOUT_EXHAUSTED',
        retry_scheduled: canRetry,
        delay_ms: delayMs,
      });
      if (!canRetry) {
        return resultPayload({ attempts, delays, terminalStatus: 'RETRY_EXHAUSTED', reasonCode: 'TIMEOUT_EXHAUSTED' });
      }
      delays.push(delayMs);
      await sleeper(delayMs);
      continue;
    }

    const status = Number(response && response.status);
    if (!response || !response.ok) {
      const retryable = GOOGLE_NEWS_FETCH_POLICY.retry_statuses.includes(status);
      const canRetry = retryable && attempt < GOOGLE_NEWS_FETCH_POLICY.max_attempts;
      const delayMs = canRetry ? retryDelay(attempt) : null;
      const exhausted = retryable && !canRetry;
      const reasonCode = exhausted ? `HTTP_${status}_EXHAUSTED` : (canRetry ? `HTTP_${status}_RETRY` : `HTTP_${status}`);
      attempts.push({ attempt, http_status: Number.isFinite(status) ? status : null, reason_code: reasonCode, retry_scheduled: canRetry, delay_ms: delayMs });
      if (!canRetry) {
        return resultPayload({
          attempts,
          delays,
          terminalStatus: exhausted ? 'RETRY_EXHAUSTED' : 'HTTP_ERROR',
          terminalHttpStatus: Number.isFinite(status) ? status : null,
          reasonCode,
        });
      }
      delays.push(delayMs);
      await sleeper(delayMs);
      continue;
    }

    let body;
    try {
      body = await response.text();
    } catch (error) {
      if (!isTimeout(error)) {
        attempts.push({ attempt, http_status: status, reason_code: 'BODY_READ_ERROR', retry_scheduled: false, delay_ms: null });
        return resultPayload({ attempts, delays, terminalStatus: 'FETCH_ERROR', terminalHttpStatus: status, reasonCode: 'BODY_READ_ERROR' });
      }
      const canRetry = attempt < GOOGLE_NEWS_FETCH_POLICY.max_attempts;
      const delayMs = canRetry ? retryDelay(attempt) : null;
      attempts.push({ attempt, http_status: status, reason_code: canRetry ? 'TIMEOUT_RETRY' : 'TIMEOUT_EXHAUSTED', retry_scheduled: canRetry, delay_ms: delayMs });
      if (!canRetry) {
        return resultPayload({ attempts, delays, terminalStatus: 'RETRY_EXHAUSTED', terminalHttpStatus: status, reasonCode: 'TIMEOUT_EXHAUSTED' });
      }
      delays.push(delayMs);
      await sleeper(delayMs);
      continue;
    }

    let items;
    try {
      items = await parser(body);
    } catch (_error) {
      attempts.push({ attempt, http_status: status, reason_code: 'PARSE_ERROR', retry_scheduled: false, delay_ms: null });
      return resultPayload({ attempts, delays, terminalStatus: 'PARSE_ERROR', terminalHttpStatus: status, reasonCode: 'PARSE_ERROR' });
    }
    if (!Array.isArray(items) || items.length === 0) {
      attempts.push({ attempt, http_status: status, reason_code: 'PARSE_ZERO', retry_scheduled: false, delay_ms: null });
      return resultPayload({ attempts, delays, terminalStatus: 'PARSE_ZERO', terminalHttpStatus: status, reasonCode: 'PARSE_ZERO' });
    }
    attempts.push({ attempt, http_status: status, reason_code: 'SUCCESS', retry_scheduled: false, delay_ms: null });
    return resultPayload({ items, attempts, delays, terminalStatus: 'SUCCESS', terminalHttpStatus: status, reasonCode: 'SUCCESS' });
  }

  throw new Error('unreachable retry loop');
}
