#!/usr/bin/env node
/** Deterministic executable verification for ADP-V12-S3-T001. */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  fetchScienceAdvancesPubmedCandidate,
  PUBMED_EUTILS_IDENTITY,
  PUBMED_EUTILS_POLICY,
  SCIENCE_ADVANCES_IDENTITY,
  SCIENCE_ADVANCES_PUBMED_SOURCE,
} from '../deploy/cloudflare/science_advances_pubmed_candidate.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const FIXTURES = path.join(ROOT, 'tests', 'fixtures');
const ESEARCH = fs.readFileSync(path.join(FIXTURES, 'pubmed_science_advances_esearch.xml'), 'utf8');
const ESEARCH_EMPTY = fs.readFileSync(path.join(FIXTURES, 'pubmed_science_advances_esearch_empty.xml'), 'utf8');
const EFETCH = fs.readFileSync(path.join(FIXTURES, 'pubmed_science_advances_efetch.xml'), 'utf8');
const WORKER_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'worker_cloud.js');
const WRANGLER_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'wrangler_cloud.jsonc');
const MODULE_PATH = path.join(ROOT, 'deploy', 'cloudflare', 'science_advances_pubmed_candidate.mjs');
const REGISTRY_PATH = path.join(ROOT, 'config', 'cloudflare_source_candidates_v1_2.json');

function timeoutError() {
  const error = new Error('deterministic timeout');
  error.name = 'TimeoutError';
  return error;
}

function fetchError() {
  return new Error('deterministic fetch error');
}

function bodyReadErrorResponse(status = 200) {
  return {
    status,
    text: async () => { throw new Error('deterministic body read error'); },
  };
}

async function runScenario({
  events,
  startDate = '2024-01-10',
  endDate = '2024-01-12',
  clockValues = null,
  advanceClockOnSleep = true,
  identity = PUBMED_EUTILS_IDENTITY,
}) {
  const calls = [];
  const sleeps = [];
  let now = 0;
  let clockIndex = 0;
  const clock = () => {
    if (clockValues) {
      const value = clockValues[Math.min(clockIndex, clockValues.length - 1)];
      clockIndex += 1;
      return value;
    }
    return now;
  };
  const sleeper = async (delayMs) => {
    sleeps.push(delayMs);
    if (advanceClockOnSleep) now += delayMs;
  };
  const fetcher = async (url, options) => {
    const event = events[calls.length];
    calls.push({ url, method: options.method, redirect: options.redirect });
    if (event instanceof Error) throw event;
    if (event && event.body_read_error) return bodyReadErrorResponse(event.status || 200);
    return new Response(event && Object.hasOwn(event, 'body') ? event.body : '', {
      status: event && event.status || 200,
      headers: { 'content-type': 'application/xml; charset=utf-8' },
    });
  };
  const result = await fetchScienceAdvancesPubmedCandidate({
    startDate,
    endDate,
    identity,
    fetcher,
    clock,
    sleeper,
  });
  return { calls, sleeps_ms: sleeps, result };
}

async function runWithoutAbortSignalTimeout() {
  const original = AbortSignal.timeout;
  try {
    AbortSignal.timeout = undefined;
    return await runScenario({ events: [] });
  } finally {
    AbortSignal.timeout = original;
  }
}

function withoutSecondArticle(xml) {
  const articles = xml.match(/<PubmedArticle>[\s\S]*?<\/PubmedArticle>/g) || [];
  return articles.length === 2 ? xml.replace(articles[1], '') : xml;
}

function singlePmidEsearch(innerIdList = '<Id>99000001</Id>') {
  return `<?xml version="1.0" encoding="UTF-8"?>
<eSearchResult>
  <Count>1</Count><RetMax>1</RetMax><RetStart>0</RetStart>
  <IdList>${innerIdList}</IdList>
</eSearchResult>`;
}

function withoutFirstDoi(xml) {
  return xml
    .replace('<ELocationID EIdType="doi" ValidYN="Y">10.1126/sciadv.fixture01</ELocationID>', '')
    .replace('<ArticleId IdType="doi">10.1126/sciadv.fixture01</ArticleId>', '');
}

function withoutFirstDate(xml) {
  return xml
    .replace('<PubDate><Year>2024</Year><Month>Jan</Month><Day>12</Day></PubDate>', '<PubDate><Year>2024</Year><Month>Jan</Month></PubDate>')
    .replace('<ArticleDate DateType="Electronic"><Year>2024</Year><Month>01</Month><Day>12</Day></ArticleDate>', '');
}

const malformedEsearch = ESEARCH.replace('</eSearchResult>', '');
const malformedEfetch = EFETCH.replace('</PubmedArticleSet>', '');
const tooLargeEsearch = `<eSearchResult><Count>0</Count><RetMax>20</RetMax><IdList></IdList>${' '.repeat(PUBMED_EUTILS_POLICY.max_esearch_xml_bytes)}</eSearchResult>`;
const tooLargeEfetch = `<PubmedArticleSet>${' '.repeat(PUBMED_EUTILS_POLICY.max_efetch_xml_bytes)}</PubmedArticleSet>`;

const scenarios = {
  happy_path: await runScenario({ events: [{ body: ESEARCH }, { body: EFETCH }] }),
  legal_truncated_search: await runScenario({
    events: [
      { body: singlePmidEsearch().replace('<Count>1</Count>', '<Count>2</Count>') },
      { body: withoutSecondArticle(EFETCH) },
    ],
  }),
  empty_search: await runScenario({ events: [{ body: ESEARCH_EMPTY }] }),
  esearch_bad_xml: await runScenario({ events: [{ body: malformedEsearch }] }),
  efetch_bad_xml: await runScenario({ events: [{ body: ESEARCH }, { body: malformedEfetch }] }),
  esearch_too_large: await runScenario({ events: [{ body: tooLargeEsearch }] }),
  efetch_too_large: await runScenario({ events: [{ body: ESEARCH }, { body: tooLargeEfetch }] }),
  duplicate_esearch_pmid: await runScenario({
    events: [{ body: ESEARCH.replace('<Id>99000002</Id>', '<Id>99000001</Id>') }],
  }),
  esearch_count_id_mismatch: await runScenario({
    events: [{ body: ESEARCH.replace('<Count>2</Count>', '<Count>1</Count>') }],
  }),
  esearch_retmax_id_mismatch: await runScenario({
    events: [{ body: ESEARCH.replace('<RetMax>2</RetMax>', '<RetMax>1</RetMax>') }],
  }),
  esearch_missing_claimed_id: await runScenario({
    events: [{ body: ESEARCH.replace('\n    <Id>99000002</Id>', '') }],
  }),
  esearch_count_overflow: await runScenario({
    events: [{ body: ESEARCH.replace('<Count>2</Count>', `<Count>${'9'.repeat(400)}</Count>`) }],
  }),
  esearch_retstart_unexpected: await runScenario({
    events: [{ body: ESEARCH.replace('<RetStart>0</RetStart>', '<RetStart>1</RetStart>') }],
  }),
  esearch_comment_injected_id: await runScenario({
    events: [{ body: singlePmidEsearch('<!-- <Id>99000001</Id> -->') }],
  }),
  esearch_cdata_injected_id: await runScenario({
    events: [{ body: singlePmidEsearch('<![CDATA[<Id>99000001</Id>]]>') }],
  }),
  esearch_nested_id_under_wrapper: await runScenario({
    events: [{ body: singlePmidEsearch('<Wrapper><Id>99000001</Id></Wrapper>') }],
  }),
  esearch_unsafe_declaration: await runScenario({
    events: [{ body: ESEARCH.replace('<eSearchResult>', '<!DOCTYPE eSearchResult [<!ENTITY unsafe "x">]><eSearchResult>') }],
  }),
  duplicate_efetch_pmid: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replaceAll('99000002', '99000001') }],
  }),
  duplicate_doi: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replaceAll('10.1126/sciadv.fixture02', '10.1126/sciadv.fixture01') }],
  }),
  conflicting_doi: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replace(
      '<ELocationID EIdType="doi" ValidYN="Y">10.1126/sciadv.fixture01</ELocationID>',
      '<ELocationID EIdType="doi" ValidYN="Y">10.1126/sciadv.conflict01</ELocationID>',
    ) }],
  }),
  missing_doi: await runScenario({ events: [{ body: ESEARCH }, { body: withoutFirstDoi(EFETCH) }] }),
  unrequested_pmid: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replaceAll('99000002', '99000003') }],
  }),
  missing_requested_pmid: await runScenario({
    events: [{ body: ESEARCH }, { body: withoutSecondArticle(EFETCH) }],
  }),
  wrong_journal: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replace('<NlmUniqueID>101653440</NlmUniqueID>', '<NlmUniqueID>999999999</NlmUniqueID>') }],
  }),
  wrong_issn: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replaceAll('2375-2548', '0000-0000') }],
  }),
  wrong_title_and_abbreviation: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH
      .replaceAll('<Title>Science advances</Title>', '<Title>Different journal</Title>')
      .replaceAll('<ISOAbbreviation>Sci Adv</ISOAbbreviation>', '<ISOAbbreviation>Different J</ISOAbbreviation>') }],
  }),
  pmid_provenance_conflict: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replace(
      '<ArticleId IdType="pubmed">99000001</ArticleId>',
      '<ArticleId IdType="pubmed">99000003</ArticleId>',
    ) }],
  }),
  duplicate_conflicting_citation_pmid: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH).replace(
      '<PMID Version="1">99000001</PMID>',
      '<PMID Version="1">99000001</PMID><PMID Version="1">99000099</PMID>',
    ) }],
  }),
  duplicate_conflicting_pubmed_provenance_id: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH).replace(
      '<ArticleId IdType="pubmed">99000001</ArticleId>',
      '<ArticleId IdType="pubmed">99000001</ArticleId><ArticleId IdType="pubmed">99000099</ArticleId>',
    ) }],
  }),
  duplicate_conflicting_nlm_identity: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH).replace(
      '<NlmUniqueID>101653440</NlmUniqueID>',
      '<NlmUniqueID>101653440</NlmUniqueID><NlmUniqueID>999999999</NlmUniqueID>',
    ) }],
  }),
  nested_fake_pubmed_provenance_id: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH).replace(
      '<ArticleId IdType="pubmed">99000001</ArticleId>',
      '<Ignored><ArticleId IdType="pubmed">99000001</ArticleId></Ignored>',
    ) }],
  }),
  case_colliding_attribute_names: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH).replace(
      'IdType="pubmed"',
      'IdType="pubmed" idtype="doi"',
    ) }],
  }),
  missing_title: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replace(
      '<ArticleTitle>Fixture record inside the requested publication window.</ArticleTitle>',
      '',
    ) }],
  }),
  efetch_empty: await runScenario({
    events: [{ body: ESEARCH }, { body: '<PubmedArticleSet></PubmedArticleSet>' }],
  }),
  efetch_unquoted_attribute: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace('EIdType="doi"', 'EIdType=doi') }],
  }),
  efetch_comment_inside_attribute: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace('EIdType="doi"', 'EIdType="doi<!-- injected -->"') }],
  }),
  efetch_cdata_inside_attribute: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace('EIdType="doi"', 'EIdType="doi<![CDATA[injected]]>"') }],
  }),
  efetch_nested_doctype: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace('<PubmedArticleSet>', '<PubmedArticleSet><!DOCTYPE PubmedArticleSet>') }],
  }),
  efetch_nested_xml_declaration: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace('<PubmedArticleSet>', '<PubmedArticleSet><?xml version="1.0"?>') }],
  }),
  efetch_undefined_entity: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace('<PubmedArticleSet>', '<PubmedArticleSet><Ignored>&undefined;</Ignored>') }],
  }),
  efetch_invalid_xml10_character: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace(
        'Fixture record inside the requested publication window.',
        `Fixture${String.fromCodePoint(1)} record inside the requested publication window.`,
      ) }],
  }),
  efetch_undeclared_named_entity: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace(
        'Fixture record inside the requested publication window.',
        'Fixture&nbsp;record inside the requested publication window.',
      ) }],
  }),
  efetch_case_folded_predefined_entity: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace(
        'Fixture record inside the requested publication window.',
        'Fixture &AMP; record inside the requested publication window.',
      ) }],
  }),
  incomplete_article_date_fallback: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace('<ArticleDate DateType="Electronic"><Year>2024</Year><Month>01</Month><Day>12</Day></ArticleDate>', '<ArticleDate DateType="Electronic"><Year>2024</Year><Month>01</Month></ArticleDate>') }],
  }),
  cdata_title_literal: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace(
        '<ArticleTitle>Fixture record inside the requested publication window.</ArticleTitle>',
        '<ArticleTitle><![CDATA[Fixture record inside the requested publication window.]]></ArticleTitle>',
      ) }],
  }),
  predefined_entities_title: await runScenario({
    events: [{ body: singlePmidEsearch() }, { body: withoutSecondArticle(EFETCH)
      .replace(
        'Fixture record inside the requested publication window.',
        'Fixture &amp; &lt; &gt; &quot; &apos; record inside the requested publication window.',
      ) }],
  }),
  outside_window_only: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH }],
    startDate: '2024-01-13',
    endDate: '2024-01-13',
  }),
  missing_date: await runScenario({ events: [{ body: ESEARCH }, { body: withoutFirstDate(EFETCH) }] }),
  invalid_date: await runScenario({
    events: [{ body: ESEARCH }, { body: EFETCH.replace('<Day>12</Day></ArticleDate>', '<Day>32</Day></ArticleDate>') }],
  }),
  esearch_429: await runScenario({ events: [{ status: 429 }] }),
  esearch_503: await runScenario({ events: [{ status: 503 }] }),
  efetch_429: await runScenario({ events: [{ body: ESEARCH }, { status: 429 }] }),
  efetch_503: await runScenario({ events: [{ body: ESEARCH }, { status: 503 }] }),
  esearch_timeout: await runScenario({ events: [timeoutError()] }),
  efetch_timeout: await runScenario({ events: [{ body: ESEARCH }, timeoutError()] }),
  esearch_fetch_error: await runScenario({ events: [fetchError()] }),
  efetch_fetch_error: await runScenario({ events: [{ body: ESEARCH }, fetchError()] }),
  esearch_body_error: await runScenario({ events: [{ status: 200, body_read_error: true }] }),
  efetch_body_error: await runScenario({
    events: [{ body: ESEARCH }, { status: 200, body_read_error: true }],
  }),
  clock_backward: await runScenario({
    events: [{ body: ESEARCH }],
    clockValues: [1000, 500],
  }),
  sleeper_no_advance: await runScenario({
    events: [{ body: ESEARCH }],
    advanceClockOnSleep: false,
  }),
  api_key_forbidden: await runScenario({
    events: [],
    identity: { ...PUBMED_EUTILS_IDENTITY, api_key: 'forbidden-placeholder' },
  }),
  abortsignal_timeout_missing: await runWithoutAbortSignalTimeout(),
};

const expectedFailures = {
  empty_search: 'ESEARCH_EMPTY',
  esearch_bad_xml: 'ESEARCH_XML_MALFORMED',
  efetch_bad_xml: 'EFETCH_XML_MALFORMED',
  esearch_too_large: 'ESEARCH_XML_TOO_LARGE',
  efetch_too_large: 'EFETCH_XML_TOO_LARGE',
  duplicate_esearch_pmid: 'ESEARCH_PMID_DUPLICATE',
  esearch_count_id_mismatch: 'ESEARCH_COUNT_ID_MISMATCH',
  esearch_retmax_id_mismatch: 'ESEARCH_COUNT_RETMAX_ID_MISMATCH',
  esearch_missing_claimed_id: 'ESEARCH_COUNT_RETMAX_ID_MISMATCH',
  esearch_count_overflow: 'ESEARCH_COUNT_INVALID',
  esearch_retstart_unexpected: 'ESEARCH_RETSTART_UNEXPECTED',
  esearch_comment_injected_id: 'ESEARCH_COUNT_ID_MISMATCH',
  esearch_cdata_injected_id: 'ESEARCH_COUNT_ID_MISMATCH',
  esearch_nested_id_under_wrapper: 'ESEARCH_ID_LIST_STRUCTURE_INVALID',
  esearch_unsafe_declaration: 'ESEARCH_XML_UNSAFE_DECLARATION',
  duplicate_efetch_pmid: 'EFETCH_PMID_DUPLICATE',
  duplicate_doi: 'EFETCH_DOI_DUPLICATE',
  conflicting_doi: 'EFETCH_DOI_CONFLICT',
  missing_doi: 'EFETCH_DOI_MISSING',
  unrequested_pmid: 'EFETCH_UNREQUESTED_PMID',
  missing_requested_pmid: 'EFETCH_REQUESTED_PMID_MISSING',
  wrong_journal: 'EFETCH_JOURNAL_IDENTITY_MISMATCH',
  wrong_issn: 'EFETCH_JOURNAL_IDENTITY_MISMATCH',
  wrong_title_and_abbreviation: 'EFETCH_JOURNAL_IDENTITY_MISMATCH',
  pmid_provenance_conflict: 'EFETCH_PMID_PROVENANCE_CONFLICT',
  duplicate_conflicting_citation_pmid: 'EFETCH_PMID_CARDINALITY_INVALID',
  duplicate_conflicting_pubmed_provenance_id: 'EFETCH_PMID_PROVENANCE_CARDINALITY_INVALID',
  duplicate_conflicting_nlm_identity: 'EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID',
  nested_fake_pubmed_provenance_id: 'EFETCH_ARTICLE_ID_LIST_STRUCTURE_INVALID',
  case_colliding_attribute_names: 'EFETCH_XML_MALFORMED',
  missing_title: 'EFETCH_TITLE_MISSING',
  efetch_empty: 'EFETCH_EMPTY',
  efetch_unquoted_attribute: 'EFETCH_XML_MALFORMED',
  efetch_comment_inside_attribute: 'EFETCH_XML_MALFORMED',
  efetch_cdata_inside_attribute: 'EFETCH_XML_MALFORMED',
  efetch_nested_doctype: 'EFETCH_XML_UNSAFE_DECLARATION',
  efetch_nested_xml_declaration: 'EFETCH_XML_MALFORMED',
  efetch_undefined_entity: 'EFETCH_XML_UNKNOWN_ENTITY',
  efetch_invalid_xml10_character: 'EFETCH_XML_MALFORMED',
  efetch_undeclared_named_entity: 'EFETCH_XML_UNKNOWN_ENTITY',
  efetch_case_folded_predefined_entity: 'EFETCH_XML_UNKNOWN_ENTITY',
  outside_window_only: 'EFETCH_DATE_FILTER_ZERO',
  missing_date: 'EFETCH_PUBLISHED_DATE_MISSING',
  invalid_date: 'EFETCH_PUBLISHED_DATE_INVALID',
  esearch_429: 'ESEARCH_RATE_LIMITED',
  esearch_503: 'ESEARCH_HTTP_STATUS',
  efetch_429: 'EFETCH_RATE_LIMITED',
  efetch_503: 'EFETCH_HTTP_STATUS',
  esearch_timeout: 'ESEARCH_TIMEOUT',
  efetch_timeout: 'EFETCH_TIMEOUT',
  esearch_fetch_error: 'ESEARCH_FETCH_ERROR',
  efetch_fetch_error: 'EFETCH_FETCH_ERROR',
  esearch_body_error: 'ESEARCH_BODY_READ_ERROR',
  efetch_body_error: 'EFETCH_BODY_READ_ERROR',
  clock_backward: 'RATE_LIMIT_CLOCK_BACKWARD',
  sleeper_no_advance: 'RATE_LIMIT_NOT_ENFORCED',
  api_key_forbidden: 'INPUT_API_KEY_FORBIDDEN',
  abortsignal_timeout_missing: 'ESEARCH_TIMEOUT_UNSUPPORTED',
};

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

const workerSource = fs.readFileSync(WORKER_PATH, 'utf8');
const moduleSource = fs.readFileSync(MODULE_PATH, 'utf8');
const wrangler = parseJsonc(fs.readFileSync(WRANGLER_PATH, 'utf8'));
const registry = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
const liveRegistry = extractLiveRegistry(workerSource);
const liveScience = liveRegistry.flatMap((board) => board.sources)
  .find((source) => source.id === SCIENCE_ADVANCES_PUBMED_SOURCE.live_source_id);
const pubmedRoute = (registry.pubmed_routes || [])[0];
const pubmedBudget = registry.pubmed_subrequest_budget || {};
const happy = scenarios.happy_path;
const legalTruncation = scenarios.legal_truncated_search;
const happyItem = happy.result.items[0] || {};
const happyRecord = happy.result.records[0] || { provenance: {} };
const fallbackDate = scenarios.incomplete_article_date_fallback;
const cdataTitle = scenarios.cdata_title_literal;
const predefinedEntityTitle = scenarios.predefined_entities_title;

const failureMatrixPass = Object.entries(expectedFailures).every(([name, reasonCode]) => {
  const scenario = scenarios[name];
  return scenario.result.reason_code === reasonCode
    && scenario.result.terminal_status === 'FAIL_CLOSED'
    && scenario.result.items.length === 0
    && scenario.result.records.length === 0
    && scenario.result.write_allowed === false
    && scenario.result.persistence_action === 'NO_WRITE';
});

const identityAndRatePass = happy.result.request_count === 2
  && happy.sleeps_ms.length === 1
  && happy.sleeps_ms[0] === 1000
  && happy.result.rate_limit.request_start_intervals_ms[0] >= 1000
  && happy.calls.every((call) => {
    const url = new URL(call.url);
    return url.origin === 'https://eutils.ncbi.nlm.nih.gov'
      && url.searchParams.get('tool') === PUBMED_EUTILS_IDENTITY.tool
      && url.searchParams.get('email') === PUBMED_EUTILS_IDENTITY.email
      && !url.searchParams.has('api_key')
      && call.method === 'GET'
      && call.redirect === 'manual';
  })
  && new URL(happy.calls[0].url).searchParams.get('retmax') === '20'
  && new URL(happy.calls[1].url).searchParams.get('id').split(',').length === 2;

const ownerPages = [
  '用户中心/数据源与板块健康.md',
  '用户中心/README.md',
  '用户中心/一看三查.md',
  '用户中心/关键结论与用户决策.md',
  'docs/owner/SOURCE_CATALOG.md',
  'docs/HANDOFF.md',
];
const ownerPhrases = [
  'ADP-V12-S3-T001',
  SCIENCE_ADVANCES_PUBMED_SOURCE.source_id,
  'candidate_not_live',
  '101653440',
  '2375-2548',
  '35/50',
];
const ownerSyncPass = ownerPages.every((relative) => {
  const text = fs.readFileSync(path.join(ROOT, relative), 'utf8');
  return ownerPhrases.every((phrase) => text.includes(phrase));
});

const prohibitedDependencyPatterns = [
  /from\s+['"](?:axios|playwright|puppeteer)['"]/,
  /https?:\/\/(?:api\.)?(?:scraperapi|brightdata|oxylabs)\./i,
  /process\.env\.(?:.*PROXY|.*API_KEY)/,
];

const checks = {
  'TST-V12-PUBMED-HAPPY-PATH': happy.result.reason_code === 'SUCCESS'
    && happy.result.parsed_count === 1
    && happy.result.filtered_outside_window === 1
    && JSON.stringify(Object.keys(happyItem)) === JSON.stringify(['guid', 'title', 'link', 'summary', 'published'])
    && happyItem.guid === 'pubmed:99000001'
    && happyItem.link === 'https://doi.org/10.1126/sciadv.fixture01'
    && happyItem.published === '2024-01-12T00:00:00.000Z'
    && happyRecord.provenance.pmid === '99000001'
    && happyRecord.provenance.doi === '10.1126/sciadv.fixture01'
    && happyRecord.provenance.nlm_unique_id === SCIENCE_ADVANCES_IDENTITY.nlm_unique_id
    && happyRecord.provenance.electronic_issn === SCIENCE_ADVANCES_IDENTITY.electronic_issn
    && fallbackDate.result.reason_code === 'SUCCESS'
    && fallbackDate.result.parsed_count === 1
    && fallbackDate.result.items[0].published === '2024-01-12T00:00:00.000Z'
    && cdataTitle.result.reason_code === 'SUCCESS'
    && cdataTitle.result.items[0].title === 'Fixture record inside the requested publication window.'
    && predefinedEntityTitle.result.reason_code === 'SUCCESS'
    && predefinedEntityTitle.result.items[0].title === 'Fixture & < > " \' record inside the requested publication window.'
    && legalTruncation.result.reason_code === 'SUCCESS'
    && legalTruncation.result.search_count === 2
    && legalTruncation.result.search_truncated_by_bound === true
    && legalTruncation.result.parsed_count === 1,
  'TST-V12-PUBMED-NEGATIVE-MATRIX': failureMatrixPass,
  'TST-V12-PUBMED-RATE-AND-IDENTITY': identityAndRatePass
    && PUBMED_EUTILS_POLICY.min_request_start_interval_ms === 1000
    && PUBMED_EUTILS_POLICY.max_ids === 20
    && PUBMED_EUTILS_POLICY.max_external_subrequests === 2,
  'TST-V12-PUBMED-NO-BULK-OR-PAID': happy.result.bulk_download === false
    && happy.result.api_key_used === false
    && happy.result.external_subrequests === 2
    && prohibitedDependencyPatterns.every((pattern) => !pattern.test(moduleSource)),
  'TST-V12-PUBMED-REGISTRY-AND-BUDGET': Boolean(pubmedRoute)
    && pubmedRoute.task_id === 'ADP-V12-S3-T001'
    && pubmedRoute.source_id === SCIENCE_ADVANCES_PUBMED_SOURCE.source_id
    && pubmedRoute.state === 'candidate_not_live'
    && pubmedRoute.live === false
    && pubmedRoute.journal_identity.nlm_unique_id === SCIENCE_ADVANCES_IDENTITY.nlm_unique_id
    && pubmedRoute.journal_identity.electronic_issn === SCIENCE_ADVANCES_IDENTITY.electronic_issn
    && pubmedRoute.request_policy.max_ids === 20
    && pubmedRoute.request_policy.min_request_start_interval_ms === 1000
    && pubmedBudget.current_live_max === 32
    && pubmedBudget.pubmed_candidate_net_increment_max === 1
    && pubmedBudget.projected_max_with_s1_and_s3 === 35
    && pubmedBudget.cloudflare_workers_free_limit === 50
    && pubmedBudget.projected_headroom_with_s1_and_s3 === 15,
  'TST-V12-PUBMED-NO-LIVE-WIRING': Boolean(liveScience)
    && liveScience.feed === 'https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv'
    && !workerSource.includes('science_advances_pubmed_candidate.mjs')
    && !workerSource.includes(SCIENCE_ADVANCES_PUBMED_SOURCE.source_id)
    && wrangler.main === 'worker_cloud.js'
    && wrangler.triggers.crons.length === 3,
  'TST-V12-PUBMED-OWNER-SYNC': ownerSyncPass,
};

const failures = Object.entries(checks).filter(([, passed]) => !passed).map(([testId]) => testId);
const report = {
  model_id: 'adp-v12-s3-science-advances-pubmed-verification-v1',
  task_id: 'ADP-V12-S3-T001',
  implementation_path: 'deploy/cloudflare/science_advances_pubmed_candidate.mjs',
  status: failures.length ? 'fail' : 'pass',
  checks,
  failures,
  scenarios,
  expected_failures: expectedFailures,
  boundary: {
    live_source_id: liveScience && liveScience.id,
    live_feed_url: liveScience && liveScience.feed,
    candidate_source_id: SCIENCE_ADVANCES_PUBMED_SOURCE.source_id,
    worker_imports_candidate: workerSource.includes('science_advances_pubmed_candidate.mjs'),
    cron_count: wrangler.triggers.crons.length,
    max_ids: PUBMED_EUTILS_POLICY.max_ids,
    max_external_subrequests: PUBMED_EUTILS_POLICY.max_external_subrequests,
    min_request_start_interval_ms: PUBMED_EUTILS_POLICY.min_request_start_interval_ms,
    api_key_used: false,
    bulk_download: false,
    write_allowed: false,
    live_change_authorized: false,
  },
  budget: pubmedBudget,
};

process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
if (failures.length) process.exitCode = 1;
