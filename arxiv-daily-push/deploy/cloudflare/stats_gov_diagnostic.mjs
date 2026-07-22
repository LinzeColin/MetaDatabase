/**
 * ADP v1.2 S2 stats-gov read-only diagnostic candidate.
 *
 * This module is intentionally not imported by worker_cloud.js. It classifies
 * one bounded fetch and returns evidence only; it cannot write D1/R2 or alter
 * the live source state.
 */

export const STATS_GOV_DIAGNOSTIC_POLICY = Object.freeze({
  max_attempts: 1,
  timeout_ms: 15000,
  redirect: 'manual_fail_closed',
  write_allowed: false,
  live_change_authorized: false,
});

export const STATS_GOV_SOURCE = Object.freeze({
  source_id: 'stats-gov',
  board_id: 'board3',
  provider: '国家统计局',
  list_url: 'https://www.stats.gov.cn/sj/zxfb/',
  diagnostic_state: 'read_only_candidate_not_live',
});

const MAX_HTML_BYTES = 2_000_000;
const MAX_ITEMS = 20;

function stripTags(value) {
  return String(value ?? '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function decodeEntities(value) {
  return String(value ?? '')
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/&#(\d+);/g, (_, codePoint) => String.fromCharCode(Number(codePoint)));
}

/** Parse the current stats-gov list shape into the live A0 item shape. */
export function parseStatsGovList(html) {
  const boundedHtml = String(html ?? '').slice(0, MAX_HTML_BYTES);
  const items = [];
  const seen = new Set();
  const linkPattern = /<a\s([^>]{0,400})>([^<]{0,200})/g;
  let match;
  while ((match = linkPattern.exec(boundedHtml)) && items.length < MAX_ITEMS) {
    const attributes = match[1];
    const hrefMatch = /href=["']([^"']+)["']/.exec(attributes);
    if (!hrefMatch) continue;
    const href = hrefMatch[1].trim();
    if (!/^\.\/\d{6}\/t\d{8}_\d+\.html$/.test(href)) continue;
    const url = `https://www.stats.gov.cn/sj/zxfb/${href.slice(2)}`;
    if (seen.has(url)) continue;
    const titleMatch = /title=["']([^"']+)["']/.exec(attributes);
    const title = decodeEntities(stripTags(titleMatch ? titleMatch[1] : match[2]));
    if (title.length < 6) continue;
    const dateMatch = /t(\d{4})(\d{2})(\d{2})_/.exec(href);
    seen.add(url);
    items.push({
      title,
      url,
      published: dateMatch ? `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}` : null,
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

function diagnosticResult({ reasonCode, httpStatus = null, items = [], parserInvoked = false }) {
  return {
    source_id: STATS_GOV_SOURCE.source_id,
    board_id: STATS_GOV_SOURCE.board_id,
    url: STATS_GOV_SOURCE.list_url,
    diagnostic_state: STATS_GOV_SOURCE.diagnostic_state,
    classification: reasonCode,
    reason_code: reasonCode,
    terminal_http_status: httpStatus,
    parsed_count: items.length,
    items,
    parser_invoked: parserInvoked,
    attempt_count: 1,
    external_subrequests: 1,
    redirect_policy: STATS_GOV_DIAGNOSTIC_POLICY.redirect,
    write_allowed: false,
    persistence_action: 'NO_WRITE',
    live_change_authorized: false,
    decision_scope: 'DIAGNOSTIC_EVIDENCE_ONLY',
  };
}

/**
 * Execute one real diagnostic path with deterministic dependency injection.
 * Unexpected fetch/parser failures reject instead of being mislabeled as one
 * of the four evidence classes.
 */
export async function diagnoseStatsGov({
  url = STATS_GOV_SOURCE.list_url,
  fetcher = globalThis.fetch,
  parser = parseStatsGovList,
  timeoutMs = STATS_GOV_DIAGNOSTIC_POLICY.timeout_ms,
} = {}) {
  if (typeof fetcher !== 'function') throw new TypeError('fetcher must be a function');
  if (typeof parser !== 'function') throw new TypeError('parser must be a function');
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new TypeError('timeoutMs must be positive');

  let response;
  try {
    const signal = timeoutSignal(timeoutMs);
    response = await fetcher(url, {
      headers: { 'User-Agent': 'ADP/0.4 personal-learning (single-user cloud)' },
      redirect: 'manual',
      ...(signal ? { signal } : {}),
    });
  } catch (error) {
    if (isTimeout(error)) return diagnosticResult({ reasonCode: 'EDGE_TIMEOUT' });
    throw error;
  }

  const status = Number(response && response.status);
  if (!Number.isFinite(status)) throw new TypeError('fetcher returned a response without numeric status');
  if (!response.ok) {
    return diagnosticResult({ reasonCode: 'HTTP_STATUS', httpStatus: status });
  }

  let body;
  try {
    body = await response.text();
  } catch (error) {
    if (isTimeout(error)) {
      return diagnosticResult({ reasonCode: 'EDGE_TIMEOUT', httpStatus: status });
    }
    throw error;
  }

  const items = await parser(body);
  if (!Array.isArray(items)) throw new TypeError('parser must return an array');
  if (items.length === 0) {
    return diagnosticResult({
      reasonCode: 'PARSE_ZERO',
      httpStatus: status,
      parserInvoked: true,
    });
  }
  return diagnosticResult({
    reasonCode: 'SUCCESS',
    httpStatus: status,
    items,
    parserInvoked: true,
  });
}
