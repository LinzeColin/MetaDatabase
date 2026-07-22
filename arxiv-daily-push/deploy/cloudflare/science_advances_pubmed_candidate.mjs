/**
 * ADP v1.2 S3 Science Advances PubMed E-utilities candidate.
 *
 * Candidate-only: worker_cloud.js does not import this module. It performs at
 * most one ESearch and one EFetch, returns evidence/items only, and has no
 * D1/R2, scheduler, source-switch, or deployment capability.
 */

export const PUBMED_EUTILS_IDENTITY = Object.freeze({
  tool: 'adp_cloud',
  email: 'linzezhang35@gmail.com',
});

export const SCIENCE_ADVANCES_IDENTITY = Object.freeze({
  nlm_unique_id: '101653440',
  electronic_issn: '2375-2548',
  journal_title: 'Science advances',
  iso_abbreviation: 'Sci Adv',
});

export const SCIENCE_ADVANCES_PUBMED_SOURCE = Object.freeze({
  source_id: 'science-advances-pubmed-candidate',
  live_source_id: 'science-advances',
  board_id: 'board2',
  provider: 'NCBI PubMed E-utilities',
  state: 'candidate_not_live',
  live: false,
});

export const PUBMED_EUTILS_POLICY = Object.freeze({
  base_url: 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
  max_ids: 20,
  max_window_days: 7,
  max_external_subrequests: 2,
  min_request_start_interval_ms: 1000,
  timeout_ms: 15000,
  max_esearch_xml_bytes: 64 * 1024,
  max_efetch_xml_bytes: 2 * 1024 * 1024,
  redirect: 'manual_fail_closed',
  write_allowed: false,
  live_change_authorized: false,
});

const DAY_MS = 86_400_000;
const MAX_SUMMARY_CHARS = 800;
const defaultClock = () => Date.now();
const defaultSleeper = (delayMs) => new Promise((resolve) => setTimeout(resolve, delayMs));

class PubmedCandidateError extends Error {
  constructor(reasonCode, stage) {
    super(reasonCode);
    this.name = 'PubmedCandidateError';
    this.reasonCode = reasonCode;
    this.stage = stage;
  }
}

function candidateError(reasonCode, stage) {
  return new PubmedCandidateError(reasonCode, stage);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function byteLength(value) {
  return new TextEncoder().encode(String(value ?? '')).byteLength;
}

function escapeCdataText(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

function isValidXml10CodePoint(codePoint) {
  return codePoint === 0x09
    || codePoint === 0x0a
    || codePoint === 0x0d
    || (codePoint >= 0x20 && codePoint <= 0xd7ff)
    || (codePoint >= 0xe000 && codePoint <= 0xfffd)
    || (codePoint >= 0x10000 && codePoint <= 0x10ffff);
}

function validateLiteralXmlCharacters(value, stage) {
  for (const character of String(value)) {
    if (!isValidXml10CodePoint(character.codePointAt(0))) {
      throw candidateError(`${stage}_XML_MALFORMED`, stage);
    }
  }
}

function validateEntityReferences(value, stage) {
  // XML entity names are case-sensitive. Because this candidate deliberately
  // does not read DTDs, only XML's five predefined entities are accepted.
  if (/&(?!(?:amp|lt|gt|quot|apos);|#\d+;|#x[0-9A-Fa-f]+;)/.test(value)) {
    throw candidateError(`${stage}_XML_UNKNOWN_ENTITY`, stage);
  }
  for (const match of String(value).matchAll(/&#(?:x([0-9A-Fa-f]+)|(\d+));/g)) {
    const codePoint = Number.parseInt(match[1] || match[2], match[1] ? 16 : 10);
    if (!Number.isSafeInteger(codePoint) || !isValidXml10CodePoint(codePoint)) {
      throw candidateError(`${stage}_XML_ENTITY_INVALID`, stage);
    }
  }
}

function parseOpeningTagAttributes(token, tagName, stage) {
  const selfClosing = /\/\s*>$/.test(token);
  let body = token.slice(1, selfClosing ? -2 : -1).trim();
  body = body.slice(tagName.length);
  const attributes = Object.create(null);
  const seenCaseFolded = new Set();
  while (body) {
    const attribute = /^\s+([A-Za-z_][\w:.-]*)\s*=\s*(?:"([^"<]*)"|'([^'<]*)')/.exec(body);
    if (!attribute) throw candidateError(`${stage}_XML_MALFORMED`, stage);
    const normalizedName = attribute[1].toLowerCase();
    if (seenCaseFolded.has(normalizedName)) {
      throw candidateError(`${stage}_XML_MALFORMED`, stage);
    }
    seenCaseFolded.add(normalizedName);
    attributes[attribute[1]] = attribute[2] ?? attribute[3] ?? '';
    body = body.slice(attribute[0].length);
  }
  return attributes;
}

function findMarkupEnd(xml, startIndex, stage) {
  let quote = '';
  for (let index = startIndex; index < xml.length; index += 1) {
    const character = xml[index];
    if (quote) {
      if (character === quote) quote = '';
    } else if (character === '"' || character === "'") {
      quote = character;
    } else if (character === '>') {
      return index;
    }
  }
  throw candidateError(`${stage}_XML_MALFORMED`, stage);
}

function validateWellFormedXml(rawXml, expectedRoot, maxBytes, stage) {
  const xml = String(rawXml ?? '');
  if (!xml.trim()) throw candidateError(`${stage}_XML_EMPTY`, stage);
  if (byteLength(xml) > maxBytes) throw candidateError(`${stage}_XML_TOO_LARGE`, stage);
  validateLiteralXmlCharacters(xml, stage);

  const stack = [];
  const roots = [];
  let cursor = 0;
  let declarationSeen = false;
  let doctypeSeen = false;
  let rootClosed = false;

  while (cursor < xml.length) {
    if (xml[cursor] !== '<') {
      const next = xml.indexOf('<', cursor);
      const end = next < 0 ? xml.length : next;
      const text = xml.slice(cursor, end);
      if (text.includes(']]>')) throw candidateError(`${stage}_XML_MALFORMED`, stage);
      validateEntityReferences(text, stage);
      if (stack.length === 0 && text.trim()) {
        throw candidateError(`${stage}_XML_MALFORMED`, stage);
      }
      if (stack.length) stack[stack.length - 1].content.push(text);
      cursor = end;
      continue;
    }

    if (xml.startsWith('<!--', cursor)) {
      const end = xml.indexOf('-->', cursor + 4);
      if (end < 0) throw candidateError(`${stage}_XML_MALFORMED`, stage);
      const content = xml.slice(cursor + 4, end);
      if (content.includes('--')) throw candidateError(`${stage}_XML_MALFORMED`, stage);
      cursor = end + 3;
      continue;
    }

    if (xml.startsWith('<![CDATA[', cursor)) {
      if (stack.length === 0) throw candidateError(`${stage}_XML_MALFORMED`, stage);
      const end = xml.indexOf(']]>', cursor + 9);
      if (end < 0) throw candidateError(`${stage}_XML_MALFORMED`, stage);
      stack[stack.length - 1].content.push(escapeCdataText(xml.slice(cursor + 9, end)));
      cursor = end + 3;
      continue;
    }

    if (xml.startsWith('<?xml', cursor)) {
      if (declarationSeen || doctypeSeen || roots.length || stack.length) {
        throw candidateError(`${stage}_XML_MALFORMED`, stage);
      }
      const end = xml.indexOf('?>', cursor + 5);
      if (end < 0) throw candidateError(`${stage}_XML_MALFORMED`, stage);
      const declaration = xml.slice(cursor, end + 2);
      const declarationPattern = /^<\?xml\s+version\s*=\s*(?:"1\.[01]"|'1\.[01]')(?:\s+encoding\s*=\s*(?:"[A-Za-z][A-Za-z0-9._-]*"|'[A-Za-z][A-Za-z0-9._-]*'))?(?:\s+standalone\s*=\s*(?:"(?:yes|no)"|'(?:yes|no)'))?\s*\?>$/;
      if (!declarationPattern.test(declaration)) {
        throw candidateError(`${stage}_XML_MALFORMED`, stage);
      }
      declarationSeen = true;
      cursor = end + 2;
      continue;
    }

    if (xml.startsWith('<?', cursor)) {
      throw candidateError(`${stage}_XML_MALFORMED`, stage);
    }

    if (xml.startsWith('<!DOCTYPE', cursor)) {
      if (doctypeSeen || roots.length || stack.length) {
        throw candidateError(`${stage}_XML_UNSAFE_DECLARATION`, stage);
      }
      const end = findMarkupEnd(xml, cursor + 9, stage);
      const doctype = xml.slice(cursor, end + 1);
      const root = escapeRegExp(expectedRoot);
      const quoted = `(?:"[^"<>]*"|'[^'<>]*')`;
      const doctypePattern = new RegExp(
        `^<!DOCTYPE\\s+${root}(?:\\s+(?:SYSTEM\\s+${quoted}|PUBLIC\\s+${quoted}\\s+${quoted}))?\\s*>$`,
      );
      if (doctype.includes('[') || !doctypePattern.test(doctype)) {
        throw candidateError(`${stage}_XML_UNSAFE_DECLARATION`, stage);
      }
      doctypeSeen = true;
      cursor = end + 1;
      continue;
    }

    if (xml.startsWith('<!', cursor)) {
      throw candidateError(`${stage}_XML_UNSAFE_DECLARATION`, stage);
    }

    const end = findMarkupEnd(xml, cursor + 1, stage);
    const token = xml.slice(cursor, end + 1);
    if (/^<\//.test(token)) {
      const closing = /^<\/([A-Za-z_][\w:.-]*)\s*>$/.exec(token);
      if (!closing || !stack.length || stack[stack.length - 1].name !== closing[1]) {
        throw candidateError(`${stage}_XML_MALFORMED`, stage);
      }
      stack.pop();
      if (stack.length === 0) rootClosed = true;
    } else {
      const opening = /^<([A-Za-z_][\w:.-]*)(?:\s+[\s\S]*?)?\s*\/?>$/.exec(token);
      if (!opening) throw candidateError(`${stage}_XML_MALFORMED`, stage);
      const node = {
        name: opening[1],
        attributes: parseOpeningTagAttributes(token, opening[1], stage),
        content: [],
      };
      validateEntityReferences(token, stage);
      if (stack.length === 0) {
        if (roots.length || rootClosed) throw candidateError(`${stage}_XML_MALFORMED`, stage);
        roots.push(node);
      } else {
        stack[stack.length - 1].content.push(node);
      }
      const selfClosing = /\/\s*>$/.test(token);
      if (!selfClosing) stack.push(node);
      else if (stack.length === 0) rootClosed = true;
    }
    cursor = end + 1;
  }

  if (stack.length !== 0 || roots.length !== 1 || !rootClosed) {
    throw candidateError(`${stage}_XML_MALFORMED`, stage);
  }
  if (roots[0].name !== expectedRoot) throw candidateError(`${stage}_XML_WRONG_ROOT`, stage);
  return roots[0];
}

function decodeXmlText(value, stage) {
  return String(value ?? '')
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;|&#39;/g, "'")
    .replace(/&#x([0-9A-Fa-f]+);/g, (_, codePoint) => String.fromCodePoint(Number.parseInt(codePoint, 16)))
    .replace(/&#(\d+);/g, (_, codePoint) => String.fromCodePoint(Number(codePoint)))
    .replace(/&amp;/g, '&');
}

function childElements(node, name = null) {
  if (!node || !Array.isArray(node.content)) return [];
  return node.content.filter((part) => (
    part && typeof part === 'object' && (name === null || part.name === name)
  ));
}

function descendantElements(node, name) {
  const matches = [];
  for (const child of childElements(node)) {
    if (child.name === name) matches.push(child);
    matches.push(...descendantElements(child, name));
  }
  return matches;
}

function requireSingleChild(node, name, reasonCode, stage) {
  const matches = childElements(node, name);
  if (matches.length !== 1) throw candidateError(reasonCode, stage);
  return matches[0];
}

function optionalSingleChild(node, name, reasonCode, stage) {
  const matches = childElements(node, name);
  if (matches.length > 1) throw candidateError(reasonCode, stage);
  return matches[0] || null;
}

function requireAllowedChildren(node, allowedNames, reasonCode, stage) {
  const allowed = new Set(allowedNames);
  if (childElements(node).some((child) => !allowed.has(child.name))) {
    throw candidateError(reasonCode, stage);
  }
}

function rawNodeText(node) {
  if (!node || !Array.isArray(node.content)) return '';
  return node.content.map((part) => (
    typeof part === 'string' ? part : rawNodeText(part)
  )).join('');
}

function scalarNodeText(node, stage, reasonCode = `${stage}_XML_STRUCTURE_INVALID`) {
  if (!node) return '';
  if (childElements(node).length) throw candidateError(reasonCode, stage);
  return decodeXmlText(rawNodeText(node), stage).replace(/\s+/g, ' ').trim();
}

function mixedNodeText(node, stage) {
  if (!node) return '';
  return decodeXmlText(rawNodeText(node), stage).replace(/\s+/g, ' ').trim();
}

function attributeValue(node, attributeName, stage) {
  if (!node || !Object.hasOwn(node.attributes, attributeName)) return '';
  return decodeXmlText(node.attributes[attributeName], stage).trim();
}

function requiredScalarChildText(node, name, reasonCode, stage) {
  return scalarNodeText(
    requireSingleChild(node, name, reasonCode, stage),
    stage,
    reasonCode,
  );
}

function optionalScalarChildText(node, name, reasonCode, stage) {
  const child = optionalSingleChild(node, name, reasonCode, stage);
  return child ? scalarNodeText(child, stage, reasonCode) : '';
}

function normalizeJournalText(value) {
  return String(value ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function parsePositiveInteger(value, reasonCode, stage) {
  if (!/^[1-9]\d*$/.test(String(value))) throw candidateError(reasonCode, stage);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw candidateError(reasonCode, stage);
  return parsed;
}

function parseNonNegativeInteger(value, reasonCode, stage) {
  if (!/^\d+$/.test(String(value))) throw candidateError(reasonCode, stage);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw candidateError(reasonCode, stage);
  return parsed;
}

function normalizeDoi(value, stage = 'EFETCH') {
  const doi = decodeXmlText(value, stage)
    .trim()
    .toLowerCase()
    .replace(/^doi:\s*/i, '')
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '');
  if (!/^10\.\d{4,9}\/[a-z0-9._;()/:+-]+$/i.test(doi)) {
    throw candidateError('EFETCH_DOI_INVALID', 'EFETCH');
  }
  return doi;
}

function parseDateInput(value, fieldName) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? ''));
  if (!match) throw candidateError(`INPUT_${fieldName}_INVALID`, 'INPUT');
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    throw candidateError(`INPUT_${fieldName}_INVALID`, 'INPUT');
  }
  return { text: match[0], ms: date.getTime() };
}

function validateWindow(startDate, endDate) {
  const start = parseDateInput(startDate, 'START_DATE');
  const end = parseDateInput(endDate, 'END_DATE');
  if (end.ms < start.ms) throw candidateError('INPUT_DATE_ORDER_INVALID', 'INPUT');
  const inclusiveDays = ((end.ms - start.ms) / DAY_MS) + 1;
  if (inclusiveDays > PUBMED_EUTILS_POLICY.max_window_days) {
    throw candidateError('INPUT_DATE_WINDOW_TOO_LARGE', 'INPUT');
  }
  return { start, end, inclusiveDays };
}

function validateIdentity(identity) {
  if (!identity || typeof identity !== 'object') throw candidateError('INPUT_IDENTITY_INVALID', 'INPUT');
  if (Object.keys(identity).some((key) => key.toLowerCase() === 'api_key')) {
    throw candidateError('INPUT_API_KEY_FORBIDDEN', 'INPUT');
  }
  if (identity.tool !== PUBMED_EUTILS_IDENTITY.tool || identity.email !== PUBMED_EUTILS_IDENTITY.email) {
    throw candidateError('INPUT_IDENTITY_INVALID', 'INPUT');
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identity.email)) {
    throw candidateError('INPUT_IDENTITY_INVALID', 'INPUT');
  }
}

export function buildPubmedESearchUrl({ startDate, endDate, identity = PUBMED_EUTILS_IDENTITY } = {}) {
  const window = validateWindow(startDate, endDate);
  validateIdentity(identity);
  const url = new URL('esearch.fcgi', PUBMED_EUTILS_POLICY.base_url);
  const params = {
    db: 'pubmed',
    term: '"Science Advances"[jour]',
    datetype: 'pdat',
    mindate: window.start.text.replaceAll('-', '/'),
    maxdate: window.end.text.replaceAll('-', '/'),
    retmode: 'xml',
    retmax: String(PUBMED_EUTILS_POLICY.max_ids),
    tool: identity.tool,
    email: identity.email,
  };
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url.toString();
}

export function buildPubmedEFetchUrl({ pmids, identity = PUBMED_EUTILS_IDENTITY } = {}) {
  validateIdentity(identity);
  if (!Array.isArray(pmids) || pmids.length === 0 || pmids.length > PUBMED_EUTILS_POLICY.max_ids) {
    throw candidateError('INPUT_PMID_COUNT_INVALID', 'INPUT');
  }
  const normalized = pmids.map((pmid) => String(parsePositiveInteger(pmid, 'INPUT_PMID_INVALID', 'INPUT')));
  if (new Set(normalized).size !== normalized.length) throw candidateError('INPUT_PMID_DUPLICATE', 'INPUT');
  const url = new URL('efetch.fcgi', PUBMED_EUTILS_POLICY.base_url);
  const params = {
    db: 'pubmed',
    id: normalized.join(','),
    retmode: 'xml',
    tool: identity.tool,
    email: identity.email,
  };
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url.toString();
}

export function parsePubmedESearchXml(xml) {
  const stage = 'ESEARCH';
  const root = validateWellFormedXml(
    xml,
    'eSearchResult',
    PUBMED_EUTILS_POLICY.max_esearch_xml_bytes,
    stage,
  );
  if (descendantElements(root, 'ERROR').length || descendantElements(root, 'ErrorList').length) {
    throw candidateError('ESEARCH_REMOTE_ERROR', stage);
  }
  const count = parseNonNegativeInteger(
    scalarNodeText(
      requireSingleChild(root, 'Count', 'ESEARCH_COUNT_CARDINALITY_INVALID', stage),
      stage,
      'ESEARCH_COUNT_INVALID',
    ),
    'ESEARCH_COUNT_INVALID',
    stage,
  );
  const retMax = parseNonNegativeInteger(
    scalarNodeText(
      requireSingleChild(root, 'RetMax', 'ESEARCH_RETMAX_CARDINALITY_INVALID', stage),
      stage,
      'ESEARCH_RETMAX_INVALID',
    ),
    'ESEARCH_RETMAX_INVALID',
    stage,
  );
  const retStart = parseNonNegativeInteger(
    scalarNodeText(
      requireSingleChild(root, 'RetStart', 'ESEARCH_RETSTART_CARDINALITY_INVALID', stage),
      stage,
      'ESEARCH_RETSTART_INVALID',
    ),
    'ESEARCH_RETSTART_INVALID',
    stage,
  );
  if (retMax > PUBMED_EUTILS_POLICY.max_ids) throw candidateError('ESEARCH_RETMAX_EXCEEDED', stage);
  if (retStart !== 0) throw candidateError('ESEARCH_RETSTART_UNEXPECTED', stage);
  const idList = requireSingleChild(root, 'IdList', 'ESEARCH_ID_LIST_CARDINALITY_INVALID', stage);
  requireAllowedChildren(idList, ['Id'], 'ESEARCH_ID_LIST_STRUCTURE_INVALID', stage);
  const pmids = childElements(idList, 'Id').map((node) => (
    String(parsePositiveInteger(
      scalarNodeText(node, stage, 'ESEARCH_PMID_INVALID'),
      'ESEARCH_PMID_INVALID',
      stage,
    ))
  ));
  if (pmids.length > PUBMED_EUTILS_POLICY.max_ids) throw candidateError('ESEARCH_PMID_LIMIT_EXCEEDED', stage);
  if (new Set(pmids).size !== pmids.length) throw candidateError('ESEARCH_PMID_DUPLICATE', stage);
  if ((count === 0) !== (pmids.length === 0)) throw candidateError('ESEARCH_COUNT_ID_MISMATCH', stage);
  if (count < pmids.length) throw candidateError('ESEARCH_COUNT_ID_MISMATCH', stage);
  if (pmids.length !== Math.min(count, retMax)) {
    throw candidateError('ESEARCH_COUNT_RETMAX_ID_MISMATCH', stage);
  }
  return {
    count,
    retmax: retMax,
    retstart: retStart,
    pmids,
    truncated_by_bound: count > pmids.length,
  };
}

const MONTHS = Object.freeze({
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3,
  apr: 4, april: 4, may: 5, jun: 6, june: 6, jul: 7, july: 7,
  aug: 8, august: 8, sep: 9, sept: 9, september: 9, oct: 10,
  october: 10, nov: 11, november: 11, dec: 12, december: 12,
});

function parseCompletePubmedDate(block) {
  if (!block) throw candidateError('EFETCH_PUBLISHED_DATE_MISSING', 'EFETCH');
  const yearNode = optionalSingleChild(block, 'Year', 'EFETCH_PUBLISHED_DATE_INVALID', 'EFETCH');
  const monthNode = optionalSingleChild(block, 'Month', 'EFETCH_PUBLISHED_DATE_INVALID', 'EFETCH');
  const dayNode = optionalSingleChild(block, 'Day', 'EFETCH_PUBLISHED_DATE_INVALID', 'EFETCH');
  if (!yearNode || !monthNode || !dayNode) {
    throw candidateError('EFETCH_PUBLISHED_DATE_MISSING', 'EFETCH');
  }
  const yearText = scalarNodeText(yearNode, 'EFETCH', 'EFETCH_PUBLISHED_DATE_INVALID');
  const monthText = scalarNodeText(monthNode, 'EFETCH', 'EFETCH_PUBLISHED_DATE_INVALID');
  const dayText = scalarNodeText(dayNode, 'EFETCH', 'EFETCH_PUBLISHED_DATE_INVALID');
  const year = Number(yearText);
  const month = /^\d+$/.test(monthText) ? Number(monthText) : MONTHS[monthText.toLowerCase()];
  const day = Number(dayText);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    throw candidateError('EFETCH_PUBLISHED_DATE_INVALID', 'EFETCH');
  }
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) {
    throw candidateError('EFETCH_PUBLISHED_DATE_INVALID', 'EFETCH');
  }
  const date = parsed.toISOString().slice(0, 10);
  return { date, iso: `${date}T00:00:00.000Z`, ms: parsed.getTime() };
}

function extractPublishedDate(articleNode) {
  const completeArticleDates = [];
  for (const articleDate of childElements(articleNode, 'ArticleDate')) {
    try {
      completeArticleDates.push(parseCompletePubmedDate(articleDate));
    } catch (error) {
      if (!(error instanceof PubmedCandidateError)
        || error.reasonCode !== 'EFETCH_PUBLISHED_DATE_MISSING') {
        throw error;
      }
    }
  }
  if (completeArticleDates.length) {
    const uniqueDates = new Set(completeArticleDates.map((value) => value.date));
    if (uniqueDates.size !== 1) throw candidateError('EFETCH_PUBLISHED_DATE_CONFLICT', 'EFETCH');
    return completeArticleDates[0];
  }
  const journal = requireSingleChild(articleNode, 'Journal', 'EFETCH_JOURNAL_CARDINALITY_INVALID', 'EFETCH');
  const journalIssue = requireSingleChild(
    journal,
    'JournalIssue',
    'EFETCH_JOURNAL_ISSUE_CARDINALITY_INVALID',
    'EFETCH',
  );
  const pubDate = requireSingleChild(
    journalIssue,
    'PubDate',
    'EFETCH_PUBDATE_CARDINALITY_INVALID',
    'EFETCH',
  );
  return parseCompletePubmedDate(pubDate);
}

function extractJournalIdentity(citation, articleNode) {
  const journal = requireSingleChild(
    articleNode,
    'Journal',
    'EFETCH_JOURNAL_CARDINALITY_INVALID',
    'EFETCH',
  );
  const medlineJournal = requireSingleChild(
    citation,
    'MedlineJournalInfo',
    'EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID',
    'EFETCH',
  );
  const title = optionalScalarChildText(
    journal,
    'Title',
    'EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID',
    'EFETCH',
  );
  const abbreviation = optionalScalarChildText(
    journal,
    'ISOAbbreviation',
    'EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID',
    'EFETCH',
  );
  const nlmUniqueId = requiredScalarChildText(
    medlineJournal,
    'NlmUniqueID',
    'EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID',
    'EFETCH',
  );
  const issnLinking = optionalScalarChildText(
    medlineJournal,
    'ISSNLinking',
    'EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID',
    'EFETCH',
  );
  const electronicIssnNodes = childElements(journal, 'ISSN')
    .filter((node) => attributeValue(node, 'IssnType', 'EFETCH').toLowerCase() === 'electronic');
  if (electronicIssnNodes.length > 1) {
    throw candidateError('EFETCH_JOURNAL_IDENTITY_CARDINALITY_INVALID', 'EFETCH');
  }
  const electronicIssn = electronicIssnNodes.length
    ? scalarNodeText(electronicIssnNodes[0], 'EFETCH', 'EFETCH_JOURNAL_IDENTITY_INVALID')
    : '';
  const titleMatch = normalizeJournalText(title) === normalizeJournalText(SCIENCE_ADVANCES_IDENTITY.journal_title)
    || normalizeJournalText(abbreviation) === normalizeJournalText(SCIENCE_ADVANCES_IDENTITY.iso_abbreviation);
  const issnMatch = [issnLinking, electronicIssn].includes(SCIENCE_ADVANCES_IDENTITY.electronic_issn);
  if (nlmUniqueId !== SCIENCE_ADVANCES_IDENTITY.nlm_unique_id || !issnMatch || !titleMatch) {
    throw candidateError('EFETCH_JOURNAL_IDENTITY_MISMATCH', 'EFETCH');
  }
  return {
    nlm_unique_id: nlmUniqueId,
    electronic_issn: SCIENCE_ADVANCES_IDENTITY.electronic_issn,
    journal_title: title,
    iso_abbreviation: abbreviation,
  };
}

function extractDoi(articleNode, articleIdList) {
  const rawDois = [
    ...childElements(articleNode, 'ELocationID')
      .filter((node) => attributeValue(node, 'EIdType', 'EFETCH').toLowerCase() === 'doi')
      .map((node) => scalarNodeText(node, 'EFETCH', 'EFETCH_DOI_INVALID')),
    ...childElements(articleIdList, 'ArticleId')
      .filter((node) => attributeValue(node, 'IdType', 'EFETCH').toLowerCase() === 'doi')
      .map((node) => scalarNodeText(node, 'EFETCH', 'EFETCH_DOI_INVALID')),
  ].filter(Boolean);
  if (!rawDois.length) throw candidateError('EFETCH_DOI_MISSING', 'EFETCH');
  const normalized = [...new Set(rawDois.map((doi) => normalizeDoi(doi)))];
  if (normalized.length !== 1) throw candidateError('EFETCH_DOI_CONFLICT', 'EFETCH');
  return normalized[0];
}

function extractPubmedDataPmid(articleIdList) {
  const matches = childElements(articleIdList, 'ArticleId')
    .filter((node) => attributeValue(node, 'IdType', 'EFETCH').toLowerCase() === 'pubmed');
  if (matches.length !== 1) {
    throw candidateError('EFETCH_PMID_PROVENANCE_CARDINALITY_INVALID', 'EFETCH');
  }
  return scalarNodeText(matches[0], 'EFETCH', 'EFETCH_PMID_PROVENANCE_INVALID');
}

function extractSummary(articleNode) {
  const abstract = optionalSingleChild(
    articleNode,
    'Abstract',
    'EFETCH_ABSTRACT_CARDINALITY_INVALID',
    'EFETCH',
  );
  if (!abstract) return '';
  return childElements(abstract, 'AbstractText')
    .map((node) => mixedNodeText(node, 'EFETCH'))
    .filter(Boolean)
    .join(' ')
    .slice(0, MAX_SUMMARY_CHARS);
}

export function parsePubmedEFetchXml(xml, { requestedPmids, startDate, endDate } = {}) {
  const window = validateWindow(startDate, endDate);
  if (!Array.isArray(requestedPmids) || !requestedPmids.length) {
    throw candidateError('EFETCH_REQUESTED_PMIDS_MISSING', 'EFETCH');
  }
  const requested = requestedPmids.map((pmid) => (
    String(parsePositiveInteger(pmid, 'EFETCH_REQUESTED_PMID_INVALID', 'EFETCH'))
  ));
  if (requested.length > PUBMED_EUTILS_POLICY.max_ids || new Set(requested).size !== requested.length) {
    throw candidateError('EFETCH_REQUESTED_PMIDS_INVALID', 'EFETCH');
  }
  const root = validateWellFormedXml(
    xml,
    'PubmedArticleSet',
    PUBMED_EUTILS_POLICY.max_efetch_xml_bytes,
    'EFETCH',
  );
  requireAllowedChildren(root, ['PubmedArticle'], 'EFETCH_ARTICLE_SET_STRUCTURE_INVALID', 'EFETCH');
  const articles = childElements(root, 'PubmedArticle');
  if (!articles.length) throw candidateError('EFETCH_EMPTY', 'EFETCH');
  if (articles.length > PUBMED_EUTILS_POLICY.max_ids) throw candidateError('EFETCH_ARTICLE_LIMIT_EXCEEDED', 'EFETCH');

  const requestedSet = new Set(requested);
  const requestedOrder = new Map(requested.map((pmid, index) => [pmid, index]));
  const seenPmids = new Set();
  const seenDois = new Set();
  const returnedPmids = [];
  const records = [];
  let filteredOutsideWindow = 0;

  for (const article of articles) {
    const citation = requireSingleChild(
      article,
      'MedlineCitation',
      'EFETCH_CITATION_CARDINALITY_INVALID',
      'EFETCH',
    );
    const articleNode = requireSingleChild(
      citation,
      'Article',
      'EFETCH_ARTICLE_CARDINALITY_INVALID',
      'EFETCH',
    );
    const pubmedData = requireSingleChild(
      article,
      'PubmedData',
      'EFETCH_PUBMED_DATA_CARDINALITY_INVALID',
      'EFETCH',
    );
    const articleIdList = requireSingleChild(
      pubmedData,
      'ArticleIdList',
      'EFETCH_ARTICLE_ID_LIST_CARDINALITY_INVALID',
      'EFETCH',
    );
    requireAllowedChildren(
      articleIdList,
      ['ArticleId'],
      'EFETCH_ARTICLE_ID_LIST_STRUCTURE_INVALID',
      'EFETCH',
    );
    const citationPmids = childElements(citation, 'PMID');
    if (citationPmids.length !== 1) {
      throw candidateError('EFETCH_PMID_CARDINALITY_INVALID', 'EFETCH');
    }
    const pmid = String(parsePositiveInteger(
      scalarNodeText(citationPmids[0], 'EFETCH', 'EFETCH_PMID_INVALID'),
      'EFETCH_PMID_INVALID',
      'EFETCH',
    ));
    if (seenPmids.has(pmid)) throw candidateError('EFETCH_PMID_DUPLICATE', 'EFETCH');
    if (!requestedSet.has(pmid)) throw candidateError('EFETCH_UNREQUESTED_PMID', 'EFETCH');
    seenPmids.add(pmid);
    returnedPmids.push(pmid);

    const provenancePmid = extractPubmedDataPmid(articleIdList);
    if (!provenancePmid || provenancePmid !== pmid) {
      throw candidateError('EFETCH_PMID_PROVENANCE_CONFLICT', 'EFETCH');
    }
    const journal = extractJournalIdentity(citation, articleNode);
    const doi = extractDoi(articleNode, articleIdList);
    if (seenDois.has(doi)) throw candidateError('EFETCH_DOI_DUPLICATE', 'EFETCH');
    seenDois.add(doi);
    const published = extractPublishedDate(articleNode);
    const titleNode = optionalSingleChild(
      articleNode,
      'ArticleTitle',
      'EFETCH_TITLE_CARDINALITY_INVALID',
      'EFETCH',
    );
    if (!titleNode) throw candidateError('EFETCH_TITLE_MISSING', 'EFETCH');
    const title = mixedNodeText(titleNode, 'EFETCH');
    if (!title) throw candidateError('EFETCH_TITLE_MISSING', 'EFETCH');

    if (published.ms < window.start.ms || published.ms > window.end.ms) {
      filteredOutsideWindow += 1;
      continue;
    }
    const item = {
      guid: `pubmed:${pmid}`,
      title,
      link: `https://doi.org/${doi}`,
      summary: extractSummary(articleNode),
      published: published.iso,
    };
    records.push({
      item,
      provenance: {
        pmid,
        doi,
        ...journal,
        database: 'pubmed',
        endpoints: ['esearch', 'efetch'],
        query_window: { start_date: window.start.text, end_date: window.end.text },
      },
    });
  }

  const missing = requested.filter((pmid) => !seenPmids.has(pmid));
  if (missing.length) throw candidateError('EFETCH_REQUESTED_PMID_MISSING', 'EFETCH');
  if (!records.length) throw candidateError('EFETCH_DATE_FILTER_ZERO', 'EFETCH');
  records.sort((left, right) => (
    requestedOrder.get(left.provenance.pmid) - requestedOrder.get(right.provenance.pmid)
  ));
  return { records, returned_pmids: returnedPmids, filtered_outside_window: filteredOutsideWindow };
}

function isTimeout(error) {
  const name = String(error && error.name || '');
  const code = String(error && error.code || '');
  return name === 'AbortError' || name === 'TimeoutError' || code === 'ETIMEDOUT';
}

function timeoutSignal(timeoutMs, stage) {
  if (typeof AbortSignal === 'undefined' || typeof AbortSignal.timeout !== 'function') {
    throw candidateError(`${stage}_TIMEOUT_UNSUPPORTED`, stage);
  }
  return AbortSignal.timeout(timeoutMs);
}

function readClock(clock, reasonCode = 'RATE_LIMIT_CLOCK_INVALID') {
  const value = Number(clock());
  if (!Number.isFinite(value)) throw candidateError(reasonCode, 'RATE_LIMIT');
  return value;
}

function baseResult({ reasonCode, stage, trace, sleeps, records = [], search = null, filteredOutsideWindow = 0 }) {
  const success = reasonCode === 'SUCCESS';
  const items = success ? records.map((record) => record.item) : [];
  return {
    source_id: SCIENCE_ADVANCES_PUBMED_SOURCE.source_id,
    live_source_id: SCIENCE_ADVANCES_PUBMED_SOURCE.live_source_id,
    board_id: SCIENCE_ADVANCES_PUBMED_SOURCE.board_id,
    route_state: SCIENCE_ADVANCES_PUBMED_SOURCE.state,
    terminal_status: success ? 'SUCCESS' : 'FAIL_CLOSED',
    terminal_stage: stage,
    reason_code: reasonCode,
    items,
    records: success ? records : [],
    parsed_count: items.length,
    search_count: search ? search.count : null,
    search_truncated_by_bound: search ? search.truncated_by_bound : false,
    filtered_outside_window: success ? filteredOutsideWindow : 0,
    request_count: trace.length,
    external_subrequests: trace.length,
    request_trace: trace,
    rate_limit: {
      min_request_start_interval_ms: PUBMED_EUTILS_POLICY.min_request_start_interval_ms,
      sleeps_ms: [...sleeps],
      request_start_intervals_ms: trace.slice(1).map((entry, index) => (
        entry.started_at_ms - trace[index].started_at_ms
      )),
    },
    max_ids: PUBMED_EUTILS_POLICY.max_ids,
    api_key_used: false,
    bulk_download: false,
    write_allowed: false,
    persistence_action: 'NO_WRITE',
    live_change_authorized: false,
    decision_scope: 'CANDIDATE_EVIDENCE_ONLY',
  };
}

async function readResponseTextBounded(response, maxBytes, stage) {
  const contentLength = response && response.headers && typeof response.headers.get === 'function'
    ? response.headers.get('content-length')
    : null;
  if (/^\d+$/.test(String(contentLength ?? '')) && Number(contentLength) > maxBytes) {
    throw candidateError(`${stage}_XML_TOO_LARGE`, stage);
  }
  if (!response.body || typeof response.body.getReader !== 'function') {
    const body = await response.text();
    if (byteLength(body) > maxBytes) throw candidateError(`${stage}_XML_TOO_LARGE`, stage);
    return body;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const chunks = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        try { await reader.cancel('bounded XML limit exceeded'); } catch (_error) { /* no-op */ }
        throw candidateError(`${stage}_XML_TOO_LARGE`, stage);
      }
      chunks.push(decoder.decode(value, { stream: true }));
    }
    chunks.push(decoder.decode());
    return chunks.join('');
  } finally {
    try { reader.releaseLock(); } catch (_error) { /* no-op */ }
  }
}

async function fetchXmlStage({ stage, url, fetcher, startedAtMs, trace, maxBytes }) {
  const entry = {
    endpoint: stage.toLowerCase(),
    method: 'GET',
    url,
    started_at_ms: startedAtMs,
    http_status: null,
    reason_code: null,
    redirect: 'manual',
  };
  trace.push(entry);
  let response;
  try {
    const signal = timeoutSignal(PUBMED_EUTILS_POLICY.timeout_ms, stage);
    response = await fetcher(url, {
      method: 'GET',
      headers: { 'User-Agent': 'ADP/1.2 science-advances-pubmed-candidate' },
      redirect: 'manual',
      signal,
    });
  } catch (error) {
    if (error instanceof PubmedCandidateError) {
      entry.reason_code = error.reasonCode;
      throw error;
    }
    entry.reason_code = isTimeout(error) ? `${stage}_TIMEOUT` : `${stage}_FETCH_ERROR`;
    throw candidateError(entry.reason_code, stage);
  }
  const status = Number(response && response.status);
  if (!Number.isFinite(status)) {
    entry.reason_code = `${stage}_RESPONSE_INVALID`;
    throw candidateError(entry.reason_code, stage);
  }
  entry.http_status = status;
  if (status < 200 || status >= 300) {
    entry.reason_code = status === 429 ? `${stage}_RATE_LIMITED` : `${stage}_HTTP_STATUS`;
    throw candidateError(entry.reason_code, stage);
  }
  try {
    const body = await readResponseTextBounded(response, maxBytes, stage);
    entry.reason_code = `${stage}_RESPONSE_RECEIVED`;
    return body;
  } catch (error) {
    if (error instanceof PubmedCandidateError) {
      entry.reason_code = error.reasonCode;
      throw error;
    }
    entry.reason_code = `${stage}_BODY_READ_ERROR`;
    throw candidateError(entry.reason_code, stage);
  }
}

async function enforceRateLimit({ lastStartedAtMs, clock, sleeper, sleeps }) {
  const before = readClock(clock);
  if (before < lastStartedAtMs) throw candidateError('RATE_LIMIT_CLOCK_BACKWARD', 'RATE_LIMIT');
  const delayMs = Math.max(0, PUBMED_EUTILS_POLICY.min_request_start_interval_ms - (before - lastStartedAtMs));
  if (delayMs > 0) {
    try {
      await sleeper(delayMs);
    } catch (_error) {
      throw candidateError('RATE_LIMIT_SLEEP_ERROR', 'RATE_LIMIT');
    }
    sleeps.push(delayMs);
  }
  const nextStartedAtMs = readClock(clock);
  if (nextStartedAtMs < lastStartedAtMs) throw candidateError('RATE_LIMIT_CLOCK_BACKWARD', 'RATE_LIMIT');
  if (nextStartedAtMs - lastStartedAtMs < PUBMED_EUTILS_POLICY.min_request_start_interval_ms) {
    throw candidateError('RATE_LIMIT_NOT_ENFORCED', 'RATE_LIMIT');
  }
  return nextStartedAtMs;
}

/** Execute the bounded candidate path with deterministic dependency injection. */
export async function fetchScienceAdvancesPubmedCandidate({
  startDate,
  endDate,
  identity = PUBMED_EUTILS_IDENTITY,
  fetcher = globalThis.fetch,
  clock = defaultClock,
  sleeper = defaultSleeper,
} = {}) {
  const trace = [];
  const sleeps = [];
  let search = null;
  try {
    if (typeof fetcher !== 'function') throw candidateError('INPUT_FETCHER_INVALID', 'INPUT');
    if (typeof clock !== 'function') throw candidateError('INPUT_CLOCK_INVALID', 'INPUT');
    if (typeof sleeper !== 'function') throw candidateError('INPUT_SLEEPER_INVALID', 'INPUT');
    validateWindow(startDate, endDate);
    validateIdentity(identity);

    const esearchUrl = buildPubmedESearchUrl({ startDate, endDate, identity });
    const esearchStartedAt = readClock(clock);
    const esearchXml = await fetchXmlStage({
      stage: 'ESEARCH',
      url: esearchUrl,
      fetcher,
      startedAtMs: esearchStartedAt,
      trace,
      maxBytes: PUBMED_EUTILS_POLICY.max_esearch_xml_bytes,
    });
    search = parsePubmedESearchXml(esearchXml);
    if (!search.pmids.length) {
      return baseResult({ reasonCode: 'ESEARCH_EMPTY', stage: 'ESEARCH', trace, sleeps, search });
    }

    const efetchStartedAt = await enforceRateLimit({
      lastStartedAtMs: esearchStartedAt,
      clock,
      sleeper,
      sleeps,
    });
    const efetchUrl = buildPubmedEFetchUrl({ pmids: search.pmids, identity });
    const efetchXml = await fetchXmlStage({
      stage: 'EFETCH',
      url: efetchUrl,
      fetcher,
      startedAtMs: efetchStartedAt,
      trace,
      maxBytes: PUBMED_EUTILS_POLICY.max_efetch_xml_bytes,
    });
    const parsed = parsePubmedEFetchXml(efetchXml, {
      requestedPmids: search.pmids,
      startDate,
      endDate,
    });
    return baseResult({
      reasonCode: 'SUCCESS',
      stage: 'COMPLETE',
      trace,
      sleeps,
      records: parsed.records,
      search,
      filteredOutsideWindow: parsed.filtered_outside_window,
    });
  } catch (error) {
    const reasonCode = error instanceof PubmedCandidateError ? error.reasonCode : 'UNEXPECTED_ERROR';
    const stage = error instanceof PubmedCandidateError ? error.stage : 'UNEXPECTED';
    return baseResult({ reasonCode, stage, trace, sleeps, search });
  }
}
