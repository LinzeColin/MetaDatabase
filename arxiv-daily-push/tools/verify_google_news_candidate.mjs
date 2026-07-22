#!/usr/bin/env node
/** Deterministic executable verification for ADP-V12-S1-T001. */

import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  fetchGoogleNewsCandidate,
  GOOGLE_NEWS_CANDIDATE_SOURCE,
  GOOGLE_NEWS_FETCH_POLICY,
} from '../deploy/cloudflare/google_news_candidate.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const SAMPLE_XML = fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'google_news_rss_sample.xml'), 'utf8');
const EMPTY_XML = fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'google_news_rss_empty.xml'), 'utf8');
const WORKER_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'worker_cloud.js');
const WRANGLER_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'wrangler_cloud.jsonc');
const REGISTRY_PATH = path.join(ROOT, 'config', 'cloudflare_source_candidates_v1_2.json');

function timeoutError() {
  const error = new Error('deterministic timeout');
  error.name = 'TimeoutError';
  return error;
}

async function runScenario(events, body = SAMPLE_XML) {
  let fetchCalls = 0;
  const sleeps = [];
  const fetcher = async () => {
    const event = events[fetchCalls++];
    if (event === 'timeout') throw timeoutError();
    if (typeof event !== 'number') throw new Error(`missing deterministic event at call ${fetchCalls}`);
    return new Response(event === 200 ? body : '', {
      status: event,
      headers: { 'content-type': 'application/rss+xml' },
    });
  };
  const result = await fetchGoogleNewsCandidate({
    fetcher,
    sleeper: async (delayMs) => { sleeps.push(delayMs); },
  });
  return { fetch_calls: fetchCalls, sleeps_ms: sleeps, result };
}

async function runRedirectScenario() {
  let networkRequests = 0;
  const server = http.createServer((request, response) => {
    networkRequests += 1;
    if (request.url === '/redirect') {
      response.writeHead(302, { location: '/feed' });
      response.end();
      return;
    }
    response.writeHead(200, { 'content-type': 'application/rss+xml' });
    response.end(SAMPLE_XML);
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  try {
    const address = server.address();
    if (!address || typeof address === 'string') throw new Error('local redirect server has no TCP address');
    const result = await fetchGoogleNewsCandidate({
      url: `http://127.0.0.1:${address.port}/redirect`,
      sleeper: async () => {},
    });
    return { network_requests: networkRequests, result };
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

function extractConstant(source, name) {
  const match = source.match(new RegExp(`const ${name} = (\\d+);`));
  if (!match) throw new Error(`missing Worker constant ${name}`);
  return Number(match[1]);
}

function extractLiveRegistry(workerSource) {
  const startNeedle = 'const REGISTRY = ';
  const endNeedle = ';\nconst BOARD_NAMES';
  const start = workerSource.indexOf(startNeedle);
  const end = workerSource.indexOf(endNeedle, start);
  if (start < 0 || end < 0) throw new Error('cannot extract live Worker REGISTRY');
  const expression = workerSource.slice(start + startNeedle.length, end);
  // This evaluates the actual shipped object literal, not a copied registry.
  return new Function(`"use strict"; return (${expression});`)();
}

function parseJsonc(text) {
  return JSON.parse(text.replace(/^\s*\/\/.*$/gm, '').replace(/,\s*([}\]])/g, '$1'));
}

function sameArray(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

const scenarios = {
  '502_to_200': await runScenario([502, 200]),
  '503_to_200': await runScenario([503, 200]),
  '503_to_503_to_200': await runScenario([503, 503, 200]),
  '504_to_200': await runScenario([504, 200]),
  '400_terminal': await runScenario([400]),
  '401_terminal': await runScenario([401]),
  '403_terminal': await runScenario([403]),
  '404_terminal': await runScenario([404]),
  '503_exhausted': await runScenario([503, 503, 503]),
  'timeout_exhausted': await runScenario(['timeout', 'timeout', 'timeout']),
  'parse_zero': await runScenario([200], EMPTY_XML),
  'redirect_manual': await runRedirectScenario(),
};

const workerSource = fs.readFileSync(WORKER_PATH, 'utf8');
const wrangler = parseJsonc(fs.readFileSync(WRANGLER_PATH, 'utf8'));
const candidateRegistry = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
const liveRegistry = extractLiveRegistry(workerSource);
const liveGnews = liveRegistry.flatMap((board) => board.sources).find((source) => source.id === 'gnews-us-tech');
if (!liveGnews) throw new Error('live gnews-us-tech source not found');

const feedPerBoard = extractConstant(workerSource, 'FEED_PER_BOARD');
const rssByBoard = liveRegistry.map((board) => board.sources.filter((source) => source.method === 'rss').length);
const rotatedRssMax = rssByBoard.reduce((total, count) => total + Math.min(count, feedPerBoard), 0);
const a0SourceCount = liveRegistry.flatMap((board) => board.sources).filter((source) => source.method === 'a0').length;
const currentLiveMax = extractConstant(workerSource, 'ARXIV_PAGES')
  + 1 // fetchBiorxiv performs exactly one external fetch.
  + rotatedRssMax
  + Math.min(a0SourceCount, extractConstant(workerSource, 'A0_PER_RUN'))
  + extractConstant(workerSource, 'META_PER_RUN');
const retryIncrementMax = GOOGLE_NEWS_FETCH_POLICY.max_attempts - 1;
const projectedMax = currentLiveMax + retryIncrementMax;
const budget = candidateRegistry.subrequest_budget;

const candidateRecord = candidateRegistry.candidate_routes[0];
const sync = {
  worker_main: wrangler.main,
  cron_count: wrangler.triggers.crons.length,
  live_source_id: liveGnews.id,
  live_provider: liveGnews.platform,
  live_feed_url: liveGnews.feed,
  candidate_source_id: candidateRecord.source_id,
  candidate_state: candidateRecord.state,
  candidate_live: candidateRecord.live,
  candidate_module_imported_by_worker: workerSource.includes('google_news_candidate.mjs'),
  live_change_authorized: candidateRegistry.live_change_authorized,
};

const checks = {
  'TST-V12-GNEWS-RETRY-ALLOWLIST': scenarios['502_to_200'].fetch_calls === 2
    && scenarios['502_to_200'].result.reason_code === 'SUCCESS'
    && scenarios['504_to_200'].fetch_calls === 2
    && scenarios['504_to_200'].result.reason_code === 'SUCCESS',
  'TST-V12-GNEWS-CLIENT-ERROR-DENYLIST': scenarios['400_terminal'].fetch_calls === 1
    && scenarios['400_terminal'].result.reason_code === 'HTTP_400'
    && scenarios['401_terminal'].fetch_calls === 1
    && scenarios['401_terminal'].result.reason_code === 'HTTP_401',
  'TST-V12-GNEWS-503-200': scenarios['503_to_200'].fetch_calls === 2
    && sameArray(scenarios['503_to_200'].sleeps_ms, [1000])
    && scenarios['503_to_200'].result.reason_code === 'SUCCESS'
    && scenarios['503_to_200'].result.attempt_count === 2,
  'TST-V12-GNEWS-503-503-200': scenarios['503_to_503_to_200'].fetch_calls === 3
    && sameArray(scenarios['503_to_503_to_200'].sleeps_ms, [1000, 3000])
    && scenarios['503_to_503_to_200'].result.reason_code === 'SUCCESS'
    && scenarios['503_to_503_to_200'].result.attempt_count === 3,
  'TST-V12-GNEWS-403': scenarios['403_terminal'].fetch_calls === 1
    && scenarios['403_terminal'].result.reason_code === 'HTTP_403'
    && scenarios['403_terminal'].result.terminal_status === 'HTTP_ERROR',
  'TST-V12-GNEWS-404': scenarios['404_terminal'].fetch_calls === 1
    && scenarios['404_terminal'].result.reason_code === 'HTTP_404'
    && scenarios['404_terminal'].result.terminal_status === 'HTTP_ERROR',
  'TST-V12-GNEWS-503-EXHAUSTED': scenarios['503_exhausted'].fetch_calls === 3
    && sameArray(scenarios['503_exhausted'].sleeps_ms, [1000, 3000])
    && scenarios['503_exhausted'].result.reason_code === 'HTTP_503_EXHAUSTED'
    && scenarios['503_exhausted'].result.attempt_count === 3,
  'TST-V12-GNEWS-TIMEOUT-EXHAUSTED': scenarios['timeout_exhausted'].fetch_calls === 3
    && sameArray(scenarios['timeout_exhausted'].sleeps_ms, [1000, 3000])
    && scenarios['timeout_exhausted'].result.reason_code === 'TIMEOUT_EXHAUSTED'
    && scenarios['timeout_exhausted'].result.attempt_count === 3,
  'TST-V12-GNEWS-PARSE-ZERO': scenarios['parse_zero'].fetch_calls === 1
    && scenarios['parse_zero'].result.reason_code === 'PARSE_ZERO'
    && scenarios['parse_zero'].result.write_allowed === false
    && scenarios['parse_zero'].result.persistence_action === 'NO_WRITE',
  'TST-V12-GNEWS-SYNC': candidateRegistry.live_route.source_id === liveGnews.id
    && candidateRegistry.live_route.feed_url === liveGnews.feed
    && candidateRecord.source_id === GOOGLE_NEWS_CANDIDATE_SOURCE.source_id
    && candidateRecord.feed_url === GOOGLE_NEWS_CANDIDATE_SOURCE.feed_url
    && candidateRecord.fallback_source_id === GOOGLE_NEWS_FETCH_POLICY.fallback_source_id
    && candidateRecord.fetch_policy.max_attempts === GOOGLE_NEWS_FETCH_POLICY.max_attempts
    && sameArray(candidateRecord.fetch_policy.retry_statuses, GOOGLE_NEWS_FETCH_POLICY.retry_statuses)
    && sameArray(candidateRecord.fetch_policy.delays_ms, GOOGLE_NEWS_FETCH_POLICY.delays_ms),
  'TST-V12-GNEWS-NO-LIVE-SWITCH': wrangler.main === 'worker_cloud.js'
    && wrangler.triggers.crons.length === 3
    && liveGnews.feed.startsWith('https://www.bing.com/news/search?')
    && candidateRecord.state === 'candidate_not_live'
    && candidateRecord.live === false
    && candidateRegistry.live_change_authorized === false
    && !workerSource.includes('google_news_candidate.mjs')
    && !workerSource.includes(candidateRecord.source_id),
  'TST-V12-GNEWS-SUBREQUEST-BUDGET': rotatedRssMax === budget.rotated_rss_max
    && currentLiveMax === budget.current_live_max
    && retryIncrementMax === budget.candidate_retry_increment_max
    && projectedMax === budget.projected_max_if_enabled
    && projectedMax < budget.cloudflare_workers_free_limit
    && budget.projected_headroom === budget.cloudflare_workers_free_limit - projectedMax
    && budget.redirect_subrequests_per_attempt_max === 1
    && candidateRecord.fetch_policy.redirect === 'manual_fail_closed'
    && scenarios['redirect_manual'].network_requests === 1
    && scenarios['redirect_manual'].result.attempt_count === 1
    && scenarios['redirect_manual'].result.external_subrequests === 1
    && scenarios['redirect_manual'].result.reason_code === 'HTTP_302',
};

const fallbackEvidenceComplete = Object.values(scenarios).every(({ result }) => (
  result.fallback.source_id === 'gnews-us-tech'
  && result.fallback.state === 'active_live'
  && result.fallback_used === false
  && result.external_subrequests === result.attempt_count
  && result.write_allowed === false
  && Array.isArray(result.attempts)
  && result.attempts.length === result.attempt_count
));
checks['TST-V12-GNEWS-RESULT-EVIDENCE'] = fallbackEvidenceComplete;

const failures = Object.entries(checks).filter(([, passed]) => !passed).map(([testId]) => testId);
const report = {
  model_id: 'adp-v12-s1-google-news-candidate-verification-v1',
  task_id: 'ADP-V12-S1-T001',
  implementation_path: path.relative(ROOT, path.join(ROOT, 'deploy', 'cloudflare', 'google_news_candidate.mjs')),
  status: failures.length === 0 ? 'pass' : 'fail',
  scenarios,
  sync,
  budget: {
    arxiv_oai_max: extractConstant(workerSource, 'ARXIV_PAGES'),
    biorxiv_max: 1,
    rss_sources_by_board: rssByBoard,
    rotated_rss_max: rotatedRssMax,
    a0_source_count: a0SourceCount,
    a0_max: Math.min(a0SourceCount, extractConstant(workerSource, 'A0_PER_RUN')),
    openalex_max: extractConstant(workerSource, 'META_PER_RUN'),
    current_live_max: currentLiveMax,
    candidate_retry_increment_max: retryIncrementMax,
    projected_max_if_enabled: projectedMax,
    cloudflare_workers_free_limit: budget.cloudflare_workers_free_limit,
    projected_headroom: budget.cloudflare_workers_free_limit - projectedMax,
    redirect_policy: candidateRecord.fetch_policy.redirect,
    redirect_network_requests_observed: scenarios['redirect_manual'].network_requests,
  },
  checks,
  failures,
};

process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
process.exitCode = failures.length === 0 ? 0 : 1;
