#!/usr/bin/env node
/** Deterministic executable verification for ADP-V12-S2-T001. */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  diagnoseStatsGov,
  parseStatsGovList,
  STATS_GOV_DIAGNOSTIC_POLICY,
  STATS_GOV_SOURCE,
} from '../deploy/cloudflare/stats_gov_diagnostic.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const SAMPLE_HTML = fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'stats_gov_list_sample.html'), 'utf8');
const EMPTY_HTML = fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'stats_gov_list_empty.html'), 'utf8');
const WORKER_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'worker_cloud.js');
const WRANGLER_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'wrangler_cloud.jsonc');
const MODULE_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'stats_gov_diagnostic.mjs');

function timeoutError() {
  const error = new Error('deterministic edge timeout');
  error.name = 'TimeoutError';
  return error;
}

async function runScenario(event, body = SAMPLE_HTML) {
  let fetchCalls = 0;
  let parserCalls = 0;
  const fetcher = async () => {
    fetchCalls += 1;
    if (event === 'timeout') throw timeoutError();
    return new Response(event === 200 ? body : '', {
      status: event,
      headers: { 'content-type': 'text/html; charset=utf-8' },
    });
  };
  const result = await diagnoseStatsGov({
    fetcher,
    parser: (html) => {
      parserCalls += 1;
      return parseStatsGovList(html);
    },
  });
  return { fetch_calls: fetchCalls, parser_calls: parserCalls, result };
}

function parseJsonc(text) {
  return JSON.parse(text.replace(/^\s*\/\/.*$/gm, '').replace(/,\s*([}\]])/g, '$1'));
}

function extractLiveRegistry(workerSource) {
  const startNeedle = 'const REGISTRY = ';
  const endNeedle = ';\nconst BOARD_NAMES';
  const start = workerSource.indexOf(startNeedle);
  const end = workerSource.indexOf(endNeedle, start);
  if (start < 0 || end < 0) throw new Error('cannot extract live Worker REGISTRY');
  return new Function(`"use strict"; return (${workerSource.slice(start + startNeedle.length, end)});`)();
}

function extractWorkerStatsParser(workerSource) {
  const maxMatch = workerSource.match(/const MAX_ITEMS_PER_FEED = (\d+);/);
  const helperStart = workerSource.indexOf('function stripTags');
  const helperEnd = workerSource.indexOf('function tag(', helperStart);
  const parserStart = workerSource.indexOf('const pad2 = ');
  const parserEnd = workerSource.indexOf('// ───────────────────────── 讲义', parserStart);
  if (!maxMatch || helperStart < 0 || helperEnd < 0 || parserStart < 0 || parserEnd < 0) {
    throw new Error('cannot extract live Worker stats-gov parser');
  }
  const helpers = workerSource.slice(helperStart, helperEnd);
  const parserBlock = workerSource.slice(parserStart, parserEnd);
  return new Function(
    `"use strict"; const MAX_ITEMS_PER_FEED = ${Number(maxMatch[1])};\n${helpers}\n${parserBlock}\n`
    + `return (html) => parseA0(html, 'stats-gov');`,
  )();
}

const scenarios = {
  edge_timeout: await runScenario('timeout'),
  http_status: await runScenario(503),
  parse_zero: await runScenario(200, EMPTY_HTML),
  success: await runScenario(200, SAMPLE_HTML),
};

const workerSource = fs.readFileSync(WORKER_PATH, 'utf8');
const moduleSource = fs.readFileSync(MODULE_PATH, 'utf8');
const wrangler = parseJsonc(fs.readFileSync(WRANGLER_PATH, 'utf8'));
const liveRegistry = extractLiveRegistry(workerSource);
const liveStats = liveRegistry.flatMap((board) => board.sources).find((source) => source.id === 'stats-gov');
if (!liveStats) throw new Error('live stats-gov source not found');
const workerParseStats = extractWorkerStatsParser(workerSource);
const candidateSample = parseStatsGovList(SAMPLE_HTML);
const workerSample = workerParseStats(SAMPLE_HTML);
const candidateEmpty = parseStatsGovList(EMPTY_HTML);
const workerEmpty = workerParseStats(EMPTY_HTML);

const classifications = Object.fromEntries(
  Object.entries(scenarios).map(([name, scenario]) => [name, scenario.result.reason_code]),
);
const distinctClassifications = new Set(Object.values(classifications));
const expectedClassifications = ['EDGE_TIMEOUT', 'HTTP_STATUS', 'PARSE_ZERO', 'SUCCESS'];

const noSideEffectResult = Object.values(scenarios).every(({ fetch_calls: fetchCalls, result }) => (
  fetchCalls === 1
  && result.attempt_count === 1
  && result.external_subrequests === 1
  && result.write_allowed === false
  && result.persistence_action === 'NO_WRITE'
  && result.live_change_authorized === false
  && result.decision_scope === 'DIAGNOSTIC_EVIDENCE_ONLY'
));

const prohibitedDependencyPatterns = [
  /from\s+['"](?:axios|playwright|puppeteer)['"]/,
  /https?:\/\/(?:api\.)?(?:scraperapi|brightdata|oxylabs)\./i,
  /process\.env\.(?:.*PROXY|.*API_KEY)/,
];

const checks = {
  'TST-V12-STATS-CLASSIFICATION': Object.values(classifications).every((value, index) => value === expectedClassifications[index])
    && distinctClassifications.size === 4,
  'TST-V12-STATS-EDGE-TIMEOUT': scenarios.edge_timeout.fetch_calls === 1
    && scenarios.edge_timeout.parser_calls === 0
    && scenarios.edge_timeout.result.terminal_http_status === null,
  'TST-V12-STATS-HTTP-STATUS': scenarios.http_status.fetch_calls === 1
    && scenarios.http_status.parser_calls === 0
    && scenarios.http_status.result.terminal_http_status === 503,
  'TST-V12-STATS-PARSE-ZERO': scenarios.parse_zero.parser_calls === 1
    && scenarios.parse_zero.result.parsed_count === 0,
  'TST-V12-STATS-SUCCESS': scenarios.success.parser_calls === 1
    && scenarios.success.result.parsed_count === 2
    && scenarios.success.result.items[0].url === 'https://www.stats.gov.cn/sj/zxfb/202607/t20260716_1964142.html'
    && scenarios.success.result.items[0].published === '2026-07-16',
  'TST-V12-STATS-PRODUCTION-PARSER-PARITY': JSON.stringify(candidateSample) === JSON.stringify(workerSample)
    && JSON.stringify(candidateEmpty) === JSON.stringify(workerEmpty),
  'TST-V12-STATS-DIAGNOSIS-DECISION': STATS_GOV_SOURCE.diagnostic_state === 'read_only_candidate_not_live'
    && STATS_GOV_DIAGNOSTIC_POLICY.live_change_authorized === false
    && !workerSource.includes('stats_gov_diagnostic.mjs'),
  'TST-V12-STATS-COST-BOUNDARY': noSideEffectResult
    && STATS_GOV_DIAGNOSTIC_POLICY.max_attempts === 1
    && STATS_GOV_DIAGNOSTIC_POLICY.redirect === 'manual_fail_closed'
    && prohibitedDependencyPatterns.every((pattern) => !pattern.test(moduleSource))
    && wrangler.main === 'worker_cloud.js'
    && wrangler.triggers.crons.length === 3
    && liveStats.list === STATS_GOV_SOURCE.list_url,
};

const failures = Object.entries(checks).filter(([, passed]) => !passed).map(([testId]) => testId);
const report = {
  model_id: 'adp-v12-s2-stats-gov-diagnostic-verification-v1',
  task_id: 'ADP-V12-S2-T001',
  implementation_path: 'deploy/cloudflare/stats_gov_diagnostic.mjs',
  status: failures.length ? 'fail' : 'pass',
  checks,
  failures,
  classifications,
  scenarios,
  parser_parity: {
    candidate_items: candidateSample,
    worker_items: workerSample,
    empty_candidate_count: candidateEmpty.length,
    empty_worker_count: workerEmpty.length,
  },
  boundary: {
    source_id: liveStats.id,
    list_url: liveStats.list,
    worker_imports_candidate: workerSource.includes('stats_gov_diagnostic.mjs'),
    cron_count: wrangler.triggers.crons.length,
    max_attempts: STATS_GOV_DIAGNOSTIC_POLICY.max_attempts,
    write_allowed: STATS_GOV_DIAGNOSTIC_POLICY.write_allowed,
    live_change_authorized: STATS_GOV_DIAGNOSTIC_POLICY.live_change_authorized,
  },
};

process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
if (failures.length) process.exitCode = 1;
