// EEI cloud product API (S10PAT01): Cloudflare Worker reading the
// eei-publication D1 database directly. Read path only - the publication
// surface carries owner-signed published facts exclusively, so every
// relationship served here is published by construction. Exploration is
// stateless in the cloud read path (session ids are echoed, not stored);
// user-state persistence is S10PBT01.
import {
  CANDIDATE_SOURCE_THRESHOLD_MIN,
  SCORING_SERVICE_VERSION,
  relationshipScoreMetrics
} from "./scoring.mjs";
import {
  addWatchlistItem,
  appendExplorationLog,
  createSavedView,
  createWatchlist,
  getSavedView,
  listExplorationLog,
  listWatchlists,
  updateSavedView
} from "./user_state.mjs";
import { listCloudRuns, runCloudSync, runHealthHeartbeat } from "./cloud_sync.mjs";

const GRAPH_QUERY_VERSION = "cloud-d1-graph-v1";
const DEFAULT_GRAPH_BUDGET = { max_nodes: 42, max_edges: 64, expand_nodes: 12 };
const GRAPH_HARD_LIMITS = { max_hops: 2, max_nodes: 500, max_edges: 2000, max_path_length: 8 };

const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, PUT, OPTIONS",
  "access-control-allow-headers": "content-type"
};

// EEI-F08 baseline: defense-in-depth headers on every response (API and
// static assets). CSP keeps Next inline bootstrap scripts and the Cloudflare
// Insights beacon working; frame embedding is denied outright.
const SECURITY_HEADERS = {
  "strict-transport-security": "max-age=31536000; includeSubDomains",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "strict-origin-when-cross-origin",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()",
  "content-security-policy":
    "default-src 'self'; script-src 'self' 'unsafe-inline'" +
    " https://static.cloudflareinsights.com; style-src 'self' 'unsafe-inline';" +
    " img-src 'self' data:; font-src 'self' data:; connect-src 'self'" +
    " https://cloudflareinsights.com https://static.cloudflareinsights.com;" +
    " frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
};

// EEI-F07: immutable build binding. EEI_BUILD_SHA / EEI_BUILD_TIME /
// EEI_DEPLOY_ID are injected at deploy time (wrangler deploy --var) by
// scripts/build_cloud_frontend.sh so production is provably mapped to a
// commit; "unbound" means a deploy skipped the pipeline.
function buildInfo(env) {
  return {
    repo: "LinzeColin/MetaDatabase",
    commit: env.EEI_BUILD_SHA ?? "unbound",
    built_at: env.EEI_BUILD_TIME ?? null,
    deploy_id: env.EEI_DEPLOY_ID ?? null
  };
}

function applyEdgeHeaders(response, env) {
  const decorated = new Response(response.body, response);
  for (const [key, value] of Object.entries(SECURITY_HEADERS)) {
    decorated.headers.set(key, value);
  }
  decorated.headers.set("x-eei-build", env.EEI_BUILD_SHA ?? "unbound");
  return decorated;
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      // 数据接口一律不缓存：部署新路由前的 404 曾被浏览器缓存住，
      // 刷新也带不回来（时间轴空态假象）。no-store 保证每次都问源。
      "cache-control": "no-store",
      ...CORS_HEADERS
    }
  });
}

function notFound(detail) {
  return json({ detail }, 404);
}

function badRequest(detail) {
  return json({ detail }, 400);
}

function normalizeBudget(raw) {
  const budget = raw && typeof raw === "object" ? raw : {};
  return {
    max_nodes: Math.min(
      Number.parseInt(budget.max_nodes ?? DEFAULT_GRAPH_BUDGET.max_nodes, 10) || DEFAULT_GRAPH_BUDGET.max_nodes,
      GRAPH_HARD_LIMITS.max_nodes
    ),
    max_edges: Math.min(
      Number.parseInt(budget.max_edges ?? DEFAULT_GRAPH_BUDGET.max_edges, 10) || DEFAULT_GRAPH_BUDGET.max_edges,
      GRAPH_HARD_LIMITS.max_edges
    ),
    expand_nodes: Math.min(
      Number.parseInt(budget.expand_nodes ?? DEFAULT_GRAPH_BUDGET.expand_nodes, 10) || DEFAULT_GRAPH_BUDGET.expand_nodes,
      GRAPH_HARD_LIMITS.max_nodes
    )
  };
}

function normalizeDirection(raw) {
  const direction = typeof raw === "string" ? raw : "both";
  if (["both", "upstream", "downstream", "in", "out"].includes(direction)) {
    return direction;
  }
  return "both";
}

function placeholders(count) {
  return Array.from({ length: count }, () => "?").join(", ");
}

async function publicationMeta(env) {
  const { results } = await env.EEI_PUB.prepare(
    "SELECT key, value FROM publication_meta ORDER BY key"
  ).all();
  return Object.fromEntries((results ?? []).map((row) => [row.key, row.value]));
}

async function activeSnapshot(env) {
  return await env.EEI_PUB.prepare(
    "SELECT snapshot_key, scope, record_mode, status, as_of, activated_at" +
      " FROM snapshot_meta ORDER BY activated_at DESC LIMIT 1"
  ).first();
}

// EEI-F01/F02: the published analysis-context identity, exported atomically
// with the rest of the publication surface. One identity per publish; every
// screen and score reads this same record.
async function publishedAnalysisContext(env) {
  const row = await env.EEI_PUB.prepare(
    "SELECT value FROM publication_meta WHERE key = 'active_analysis_context'"
  ).first();
  if (!row?.value) return null;
  try {
    return JSON.parse(row.value);
  } catch {
    return null;
  }
}

async function publishedRelationshipCount(env) {
  const row = await env.EEI_PUB.prepare(
    "SELECT COUNT(*) AS n FROM relationships"
  ).first();
  return Number(row?.n ?? 0);
}

async function productionContext(env, requestAsOf) {
  const [meta, snapshot, publishedCount, analysisContext] = await Promise.all([
    publicationMeta(env),
    activeSnapshot(env),
    publishedRelationshipCount(env),
    publishedAnalysisContext(env)
  ]);
  return {
    schema_version: "production-context-v1",
    request_as_of: requestAsOf ?? null,
    graph_query_version: GRAPH_QUERY_VERSION,
    scoring_service_version: SCORING_SERVICE_VERSION,
    active_scoring_profile_version_id:
      analysisContext?.active_scoring_profile_version_id ?? null,
    active_scoring_profile: analysisContext
      ? {
          model_version: analysisContext.model_version,
          profile_version: analysisContext.profile_version
        }
      : null,
    active_analysis_context: {
      surface: "cloud_publication",
      snapshot_key: snapshot?.snapshot_key ?? null,
      snapshot_status: snapshot?.status ?? null,
      as_of: snapshot?.as_of ?? null,
      published_at: meta.published_at ?? null,
      publisher_version: meta.publisher_version ?? null,
      data_snapshot_key: analysisContext?.active_data_snapshot_key ?? null,
      score_snapshot_id: analysisContext?.active_scoring_run_id ?? null,
      model_version: analysisContext?.model_version ?? null,
      profile_version: analysisContext?.profile_version ?? null,
      refresh_generation: analysisContext?.refresh_generation ?? null
    },
    record_modes: {
      published_relationships: {
        database: publishedCount,
        fixture: 0,
        total: publishedCount
      }
    },
    candidate_fact_summary: {
      total: publishedCount,
      published: publishedCount,
      unpublished: 0,
      source_threshold_open: 0,
      review_open: 0,
      reason:
        "cloud publication surface carries owner-signed published facts only;" +
        " candidates and review queues stay local"
    },
    publication_policy: {
      relationship_fact_candidates_in_graph_edges: false,
      minimum_independent_sources: CANDIDATE_SOURCE_THRESHOLD_MIN,
      publish_requires_source_threshold: true,
      publish_requires_human_review: true
    }
  };
}

async function loadEntity(env, entityId) {
  return await env.EEI_PUB.prepare(
    "SELECT id, canonical_name, entity_type, status FROM entities WHERE id = ?"
  )
    .bind(entityId)
    .first();
}

function directionClause(direction) {
  if (direction === "out" || direction === "downstream") {
    return "subject_entity_id IN";
  }
  if (direction === "in" || direction === "upstream") {
    return "object_entity_id IN";
  }
  return null;
}

async function relationshipsTouching(env, frontier, direction, limit) {
  const marks = placeholders(frontier.length);
  const clause = directionClause(direction);
  const where = clause
    ? `${clause} (${marks})`
    : `subject_entity_id IN (${marks}) OR object_entity_id IN (${marks})`;
  const binds = clause ? frontier : [...frontier, ...frontier];
  const { results } = await env.EEI_PUB.prepare(
    "SELECT id, subject_entity_id, object_entity_id, relationship_type," +
      " relationship_family, status, confidence, observed_at, published_at," +
      " qualifiers_json" +
      ` FROM relationships WHERE ${where} ORDER BY id LIMIT ?`
  )
    .bind(...binds, limit)
    .all();
  return results ?? [];
}

async function evidenceCounts(env, relationshipIds) {
  if (relationshipIds.length === 0) return new Map();
  const { results } = await env.EEI_PUB.prepare(
    "SELECT relationship_id, COUNT(*) AS n," +
      " COUNT(DISTINCT source_document_id) AS source_documents" +
      ` FROM relationship_evidence WHERE relationship_id IN (${placeholders(relationshipIds.length)})` +
      " GROUP BY relationship_id"
  )
    .bind(...relationshipIds)
    .all();
  return new Map((results ?? []).map((row) => [row.relationship_id, row]));
}

async function distinctSourceDocuments(env, relationshipIds) {
  if (relationshipIds.length === 0) return 0;
  const row = await env.EEI_PUB.prepare(
    "SELECT COUNT(DISTINCT source_document_id) AS n FROM relationship_evidence" +
      ` WHERE relationship_id IN (${placeholders(relationshipIds.length)})`
  )
    .bind(...relationshipIds)
    .first();
  return Number(row?.n ?? 0);
}

async function exploreGraph(env, { sessionId, focusEntityId, direction, hops, budget, activeLayers, filters, asOf }) {
  const focus = await loadEntity(env, focusEntityId);
  if (!focus) {
    return notFound(`Entity not found: ${focusEntityId}`);
  }
  const boundedHops = Math.min(Math.max(Number.parseInt(hops ?? 1, 10) || 1, 1), GRAPH_HARD_LIMITS.max_hops);
  const seenEdges = new Map();
  const seenNodes = new Set([focus.id]);
  let frontier = [focus.id];
  let fetchedEdgeCount = 0;
  let edgeBudgetHit = false;
  let nodeBudgetHit = false;
  for (let hop = 0; hop < boundedHops && frontier.length > 0; hop += 1) {
    const rows = await relationshipsTouching(env, frontier, direction, budget.max_edges + 1);
    // Later hops legitimately re-fetch edges already collected (both
    // endpoints in earlier frontiers); only unseen edges count toward the
    // budget or the truncation verdict.
    const fresh = rows.filter((row) => !seenEdges.has(row.id));
    fetchedEdgeCount += fresh.length;
    const nextFrontier = new Set();
    for (const row of fresh) {
      if (seenEdges.size >= budget.max_edges) {
        edgeBudgetHit = true;
        break;
      }
      seenEdges.set(row.id, row);
      for (const endpoint of [row.subject_entity_id, row.object_entity_id]) {
        if (seenNodes.has(endpoint)) continue;
        if (seenNodes.size >= budget.max_nodes) {
          nodeBudgetHit = true;
          continue;
        }
        seenNodes.add(endpoint);
        nextFrontier.add(endpoint);
      }
    }
    frontier = [...nextFrontier];
  }
  const edgeRows = [...seenEdges.values()];
  const nodeIds = [...seenNodes];
  const { results: nodeRows } =
    nodeIds.length > 0
      ? await env.EEI_PUB.prepare(
          "SELECT id, canonical_name, entity_type, status FROM entities" +
            ` WHERE id IN (${placeholders(nodeIds.length)}) ORDER BY canonical_name`
        )
          .bind(...nodeIds)
          .all()
      : { results: [] };
  const evidence = await evidenceCounts(env, edgeRows.map((row) => row.id));
  const sourceCount = await distinctSourceDocuments(env, edgeRows.map((row) => row.id));
  const familyCount = new Set(edgeRows.map((row) => row.relationship_family)).size;
  const truncated = edgeBudgetHit || nodeBudgetHit;
  const reasons = [];
  if (edgeBudgetHit) reasons.push("edge_budget");
  if (nodeBudgetHit) reasons.push("node_budget");
  const context = await productionContext(env, asOf ?? null);
  return json({
    session_id: sessionId ?? crypto.randomUUID(),
    focus: {
      id: focus.id,
      canonical_name: focus.canonical_name,
      entity_type: focus.entity_type
    },
    query: {
      focus: { object_type: "entity", object_id: focus.id },
      direction,
      hops: boundedHops,
      as_of: asOf ?? null,
      scoring_profile_version_id: null,
      active_layers: activeLayers ?? [],
      filters: filters ?? {},
      budget,
      hard_limits: GRAPH_HARD_LIMITS
    },
    nodes: (nodeRows ?? []).map((row) => ({
      id: row.id,
      canonical_name: row.canonical_name,
      entity_type: row.entity_type,
      fixture_notice: null,
      synthetic: false
    })),
    edges: edgeRows.map((row) => ({
      id: row.id,
      subject_id: row.subject_entity_id,
      object_id: row.object_entity_id,
      relationship_type: row.relationship_type,
      relationship_family: row.relationship_family,
      status: row.status,
      confidence: row.confidence,
      valid_from: null,
      valid_to: null,
      evidence_count: Number(evidence.get(row.id)?.n ?? 0),
      synthetic: false,
      fixture_notice: null
    })),
    truncated,
    truncation: {
      applied: truncated,
      reasons,
      message: truncated
        ? "graph truncated by budget; raise budget or expand from an anchor"
        : "",
      fetched_edge_count: fetchedEdgeCount,
      returned_edge_count: edgeRows.length,
      returned_node_count: (nodeRows ?? []).length
    },
    continuation: {
      available: truncated,
      expand_endpoint: truncated ? "/v1/explore/expand" : null,
      anchor_entity_id: truncated ? focus.id : null,
      direction: truncated ? direction : null,
      expand_nodes: truncated ? budget.expand_nodes : null
    },
    warnings: [],
    coverage: {
      visible_nodes: (nodeRows ?? []).length,
      visible_edges: edgeRows.length,
      source_count: sourceCount,
      relationship_family_count: familyCount,
      synthetic_fixture_edges: 0
    },
    production_context: context
  });
}

async function scoreExplanation(env, relationshipId) {
  const row = await env.EEI_PUB.prepare(
    "SELECT r.id, r.subject_entity_id, subject.canonical_name AS subject_name," +
      " r.object_entity_id, object.canonical_name AS object_name," +
      " r.relationship_type, r.relationship_family, r.status, r.confidence," +
      " r.observed_at, r.published_at, r.qualifiers_json" +
      " FROM relationships r" +
      " JOIN entities subject ON subject.id = r.subject_entity_id" +
      " JOIN entities object ON object.id = r.object_entity_id" +
      " WHERE r.id = ?"
  )
    .bind(relationshipId)
    .first();
  if (!row) {
    return notFound(`Relationship not found: ${relationshipId}`);
  }
  const { results: evidenceRows } = await env.EEI_PUB.prepare(
    "SELECT relationship_id, source_document_id, role, locator, support_excerpt," +
      " source_url, source_title, publisher, document_date" +
      " FROM relationship_evidence WHERE relationship_id = ?" +
      " ORDER BY role, publisher, source_url"
  )
    .bind(relationshipId)
    .all();
  const evidence = evidenceRows ?? [];
  let qualifiers = {};
  try {
    qualifiers = row.qualifiers_json ? JSON.parse(row.qualifiers_json) : {};
  } catch {
    qualifiers = {};
  }
  const policy = qualifiers.source_threshold_policy ?? {};
  const minimumSources = Math.max(
    Number.parseInt(policy.minimum_independent_sources ?? CANDIDATE_SOURCE_THRESHOLD_MIN, 10) ||
      CANDIDATE_SOURCE_THRESHOLD_MIN,
    1
  );
  const distinctDocuments = new Set(evidence.map((item) => item.source_document_id)).size;
  const independentSourceCount = Number.parseInt(
    policy.independent_source_count ?? distinctDocuments,
    10
  );
  const sourceThresholdMet =
    independentSourceCount >= minimumSources || Boolean(policy.met_by_review_override);
  // Publication invariants: every relationship in the D1 surface was
  // published through the owner-signed pipeline, which requires a fact
  // version; review status derives from the signed decision set exactly
  // like the local payload does.
  const publicationStatus = "published";
  const reviewStatus = qualifiers.decision_set_key ? "human_verified" : "unreviewed";
  const factVersionPresent = true;
  const snapshot = await activeSnapshot(env);
  const analysisContext = await publishedAnalysisContext(env);
  const metrics = relationshipScoreMetrics({
    confidence: Number(row.confidence),
    independentSourceCount,
    sourceThresholdMet,
    reviewStatus,
    publicationStatus,
    factVersionPresent,
    evidencePresent: evidence.length > 0,
    minimumIndependentSources: minimumSources
  });
  const context = await productionContext(env, null);
  return json({
    object_type: "relationship",
    object_id: row.id,
    relationship_type: row.relationship_type,
    relationship_family: row.relationship_family,
    record_mode: snapshot?.record_mode ?? "database",
    fact_status: row.status,
    publication_status: publicationStatus,
    relationship_status: row.status,
    source_threshold: metrics.source_threshold,
    review_status: reviewStatus,
    parser_version: qualifiers.parser_version ?? null,
    raw_score: metrics.raw_score,
    evidence_quality: metrics.evidence_quality,
    adjusted_score: metrics.adjusted_score,
    coverage: metrics.coverage,
    contributions: metrics.contributions,
    missing_inputs: metrics.missing_inputs,
    model_version: analysisContext?.model_version ?? "cloud-publication-surface",
    profile_version: analysisContext?.profile_version ?? "cloud-publication-surface",
    profile_version_id: analysisContext?.active_scoring_profile_version_id ?? null,
    structured_fact: qualifiers.structured_fact ?? {},
    counter_evidence: [],
    qualifiers,
    fact_version: {
      id: null,
      version_no: null,
      snapshot_key: snapshot?.snapshot_key ?? null,
      snapshot_scope: snapshot?.scope ?? null,
      snapshot_status: snapshot?.status ?? null,
      record_mode: snapshot?.record_mode ?? null,
      parser_version: qualifiers.parser_version ?? null
    },
    subject: {
      entity_id: row.subject_entity_id,
      canonical_name: row.subject_name
    },
    object: {
      entity_id: row.object_entity_id,
      canonical_name: row.object_name
    },
    evidence,
    review_queue: [],
    production_context: context,
    scoring_service_version: SCORING_SERVICE_VERSION
  });
}

async function evidenceIndex(env, relationshipId) {
  const relationship = await env.EEI_PUB.prepare(
    "SELECT id FROM relationships WHERE id = ?"
  )
    .bind(relationshipId)
    .first();
  if (!relationship) {
    return notFound(`Relationship not found: ${relationshipId}`);
  }
  const { results } = await env.EEI_PUB.prepare(
    "SELECT relationship_id, source_document_id, role, locator, support_excerpt," +
      " source_url, source_title, publisher, document_date" +
      " FROM relationship_evidence WHERE relationship_id = ?" +
      " ORDER BY role, publisher, source_url"
  )
    .bind(relationshipId)
    .all();
  return json({
    object_type: "relationship",
    object_id: relationshipId,
    evidence: results ?? [],
    evidence_count: (results ?? []).length
  });
}

// R-002/S-003 fault-injection hardening. A fuzzed long search term made D1's
// LIKE pattern-complexity limit throw ("LIKE or GLOB pattern too complex",
// SQLITE_ERROR), which surfaced as an unhandled 500 leaking the internal error.
// Three layers of defense:
//   1. cap the term for UX (entity names are short),
//   2. escape LIKE metacharacters so user %/_ are literals, not patterns,
//   3. treat a still-too-complex pattern as "no matches" (no entity name is
//      that structurally complex) instead of a 500.
const MAX_SEARCH_TERM = 64;
function escapeLike(value) {
  return value.replace(/[\\%_]/g, (ch) => `\\${ch}`);
}
async function searchEntities(env, query) {
  const trimmed = query.trim().slice(0, MAX_SEARCH_TERM);
  const term = `%${escapeLike(trimmed)}%`;
  try {
    const { results } = await env.EEI_PUB.prepare(
      "SELECT id, canonical_name, entity_type, status FROM entities" +
        " WHERE canonical_name LIKE ? ESCAPE '\\' COLLATE NOCASE" +
        " ORDER BY canonical_name LIMIT 20"
    )
      .bind(term)
      .all();
    return json({ query: trimmed, entities: results ?? [] });
  } catch {
    // An over-complex LIKE pattern matches nothing real — fail closed to an
    // empty result set, never a 500 that leaks the engine error.
    return json({ query: trimmed, entities: [] });
  }
}

async function readJsonBody(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

// Mirror of the local API's relationship_type -> stage mapping
// (apps/api/app/domain_repository.py SUPPLY_TYPE_STAGE_MAP).
const SUPPLY_TYPE_STAGE_MAP = {
  material_provider_to: "SC-02",
  licenses_ip_to: "SC-03",
  equipment_provider_to: "SC-04",
  wafer_foundry_for: "SC-06",
  packages_tests_for: "SC-07",
  system_integrator_for: "SC-09",
  energy_provider_to: "SC-10",
  logistics_provider_to: "SC-10",
  cloud_provider_to: "SC-11",
  distributor_for: "SC-11",
  customer_of: "SC-12",
  supplier_to: "SC-06",
  capacity_commitment: "SC-06",
  compute_provider_to: "SC-11"
};

// Owner-signed published relationships filtered by family (control/M&A/signals/
// policy module surfaces). Every row here is published by construction, so
// owner_signed_published is true and fixture_flag is false.
async function familyRelationships(env, families) {
  const marks = families.map(() => "?").join(", ");
  const { results } = await env.EEI_PUB.prepare(
    "SELECT r.id, r.relationship_type, r.relationship_family, r.status," +
      " r.confidence, r.observed_at," +
      " subject.canonical_name AS subject_name," +
      " object.canonical_name AS object_name" +
      " FROM relationships r" +
      " JOIN entities subject ON subject.id = r.subject_entity_id" +
      " JOIN entities object ON object.id = r.object_entity_id" +
      ` WHERE r.relationship_family IN (${marks})` +
      " ORDER BY r.relationship_type, r.id LIMIT 300"
  )
    .bind(...families)
    .all();
  return (results ?? []).map((row) => ({
    id: row.id,
    relationship_type: row.relationship_type,
    relationship_family: row.relationship_family,
    status: row.status,
    confidence: row.confidence === null ? null : Number(row.confidence),
    observed_at: row.observed_at,
    owner_signed_published: true,
    subject_name: row.subject_name,
    object_name: row.object_name,
    fixture_flag: false
  }));
}

// EEI structure/empire module (/structure): entity-scoped corporate structure.
// The publication surface carries relationships, not a full legal hierarchy, so
// structure sections are honestly empty; the page renders its no-structure
// state instead of empire_http_404 / focus_entity_not_resolved.
async function entityEmpire(env, entityId) {
  const focus = await loadEntity(env, entityId);
  if (!focus) {
    return notFound(`Entity not found: ${entityId}`);
  }
  const meta = await publicationMeta(env);
  const snapshot = await activeSnapshot(env);
  return json({
    as_of: snapshot?.as_of ?? meta.published_at ?? null,
    focus: {
      id: focus.id,
      canonical_name: focus.canonical_name,
      entity_type: focus.entity_type,
      status: focus.status
    },
    structure: {},
    coverage: {
      published_structure_sections: 0,
      note:
        "The publication surface carries owner-signed relationships, not a" +
        " full legal-group hierarchy; structure sections appear here only when" +
        " group/segment/brand/product/facility facts are published."
    },
    data_mode: "cloud_publication",
    fixture_notice: null
  });
}

// EEI-F01: cloud twin of the local /v1/supply-chain/overview. Every
// relationship on this surface is owner-signed published by construction;
// fixture rows never leave the machine, so fixture_flag is honestly false.
async function supplyChainOverview(env) {
  const { results: stageRows } = await env.EEI_PUB.prepare(
    "SELECT stage_id, stage_order, slug, name_zh, name_en, default_direction," +
      " examples FROM supply_chain_stages ORDER BY stage_order"
  ).all();
  const stages = (stageRows ?? []).map((row) => ({
    ...row,
    stage_order: Number(row.stage_order)
  }));
  const { results: relationshipRows } = await env.EEI_PUB.prepare(
    "SELECT r.id, r.relationship_type, r.status, r.confidence, r.observed_at," +
      " subject.canonical_name AS subject_name," +
      " object.canonical_name AS object_name" +
      " FROM relationships r" +
      " JOIN entities subject ON subject.id = r.subject_entity_id" +
      " JOIN entities object ON object.id = r.object_entity_id" +
      " WHERE r.relationship_family = 'supply_chain_operations'" +
      " ORDER BY r.relationship_type, r.id LIMIT 300"
  ).all();
  const relationships = (relationshipRows ?? []).map((row) => ({
    id: row.id,
    relationship_type: row.relationship_type,
    status: row.status,
    confidence: row.confidence === null ? null : Number(row.confidence),
    observed_at: row.observed_at,
    owner_signed_published: true,
    subject_name: row.subject_name,
    object_name: row.object_name,
    fixture_flag: false,
    stage_id: SUPPLY_TYPE_STAGE_MAP[row.relationship_type] ?? null
  }));
  const mappedStageIds = new Set(
    relationships.map((row) => row.stage_id).filter(Boolean)
  );
  return json({
    stages,
    relationships,
    summary: {
      published_fact_count: relationships.length,
      demo_or_candidate_count: 0,
      stages_total: stages.length,
      stages_with_relationships: mappedStageIds.size
    },
    abstentions: {
      coverage:
        "Stages without relationships mean no assertion exists in the" +
        " published graph for that stage - not that the stage is empty in the" +
        " real world.",
      labeling:
        "The cloud publication surface carries owner-signed published facts" +
        " only; demo and candidate rows never leave the local machine."
    }
  });
}

// EEI-F07/acceptance F-007: the empty amount-summary shape, matching the
// local API's event_amount_summary contract (event-amount-semantics-v1) for
// zero published events. filters echoes the request so the client validator's
// isRecord(filters) check passes.
function emptyAmountSummary(searchParams) {
  const filters = {};
  for (const [key, value] of searchParams.entries()) {
    if (key !== "limit") filters[key] = value;
  }
  return {
    schema_version: "event-amount-semantics-v1",
    event_count: 0,
    reported_event_count: 0,
    unreported_event_count: 0,
    unclassified_event_count: 0,
    bucket_count: 0,
    buckets: [],
    unreported_event_ids: [],
    unclassified_event_ids: [],
    incomparable_dimensions: [],
    cross_bucket_summation_performed: false,
    comparable_reported_total_available: false,
    comparable_reported_total: null,
    comparable_reported_total_complete: false,
    semantics: {
      unknown_amount_is_zero: false,
      unknown_amount_has_visual_weight: false,
      aggregation_key: ["currency", "amount_kind", "period_start", "period_end"],
      incomparable_buckets_are_summed: false
    },
    filters
  };
}

// EEI-F01: cloud twin of the local /v1/changes. The publication surface's
// change feed is derived from publication events (relationships.published_at);
// internal review-queue changes stay local.
async function listChanges(env, sinceRaw) {
  let since = null;
  if (sinceRaw) {
    const parsed = new Date(sinceRaw);
    if (Number.isNaN(parsed.getTime())) {
      return badRequest("since must be an ISO-8601 timestamp");
    }
    since = parsed.toISOString();
  }
  const query =
    "SELECT r.id, r.relationship_type, r.relationship_family, r.status," +
    " r.published_at, subject.canonical_name AS subject_name," +
    " object.canonical_name AS object_name" +
    " FROM relationships r" +
    " JOIN entities subject ON subject.id = r.subject_entity_id" +
    " JOIN entities object ON object.id = r.object_entity_id" +
    (since ? " WHERE r.published_at >= ?" : "") +
    " ORDER BY r.published_at DESC, r.id DESC LIMIT 100";
  const statement = env.EEI_PUB.prepare(query);
  const { results } = await (since ? statement.bind(since) : statement).all();
  return json(
    (results ?? []).map((row) => ({
      id: row.id,
      change_type: "relationship_published",
      object_type: "relationship",
      object_id: row.id,
      old_value: null,
      new_value: {
        relationship_type: row.relationship_type,
        relationship_family: row.relationship_family,
        status: row.status,
        subject_name: row.subject_name,
        object_name: row.object_name
      },
      review_required: false,
      created_at: row.published_at,
      trigger_source: null
    }))
  );
}

async function handleFetch(request, env) {
    const url = new URL(request.url);
    const { pathname } = url;
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (pathname === "/health") {
      const snapshot = await activeSnapshot(env);
      return json({
        status: "ok",
        surface: "cloud_publication",
        snapshot_key: snapshot?.snapshot_key ?? null,
        graph_query_version: GRAPH_QUERY_VERSION,
        build: buildInfo(env)
      });
    }

    if (pathname === "/v1/publication/meta" && request.method === "GET") {
      const [meta, snapshot, publishedCount] = await Promise.all([
        publicationMeta(env),
        activeSnapshot(env),
        publishedRelationshipCount(env)
      ]);
      return json({
        publication_meta: meta,
        snapshot,
        published_relationship_count: publishedCount
      });
    }

    if (pathname === "/v1/policy/overview" && request.method === "GET") {
      // S12PB: the vertical timeline's per-year official filing depth.
      // Serves published aggregates from D1; an empty table returns an empty
      // list so the frontend keeps its honest not-connected state.
      const { results } = await env.EEI_PUB.prepare(
        "SELECT year, filings FROM filing_year_counts ORDER BY year"
      ).all();
      // The /policy page (policy-client) requires policy_relationships[] and
      // policy_models[] in addition to regulatory_filings.by_year; without them
      // it rejected a 200 as policy_overview_http_200. government_policy family
      // relationships are served from the publication surface (0 published now
      // -> honest empty); scored policy models stay local.
      const policyRelationships = await familyRelationships(env, ["government_policy"]);
      return json({
        schema_version: "cloud-policy-overview-v1",
        policy_relationships: policyRelationships,
        regulatory_filings: {
          source: "sec_edgar",
          by_year: (results ?? []).map((row) => ({
            year: Number(row.year),
            filings: Number(row.filings)
          }))
        },
        policy_models: [],
        abstentions: {
          coverage:
            "Policy edges and filings are what the published graph and the SEC" +
            " EDGAR source assert; absence of an edge means no assertion, not" +
            " the absence of policy exposure in the real world."
        }
      });
    }

    // EEI module pages (/control /ma /signals): family-overview surfaces. Each
    // serves owner-signed published relationships filtered by family (0 now, so
    // honest empty) so the page renders its no-published-facts state instead of
    // the raw family_http_404 the module audit found.
    if (pathname === "/v1/control/overview" && request.method === "GET") {
      const relationships = await familyRelationships(env, [
        "ownership_control",
        "corporate_structure"
      ]);
      const byType = {};
      for (const r of relationships) {
        byType[r.relationship_type] = (byType[r.relationship_type] ?? 0) + 1;
      }
      return json({
        relationships,
        summary: {
          published_fact_count: relationships.length,
          relationship_count: relationships.length,
          by_type: byType
        },
        abstentions: {
          semantics:
            "Control edges are legal/governance assertions and are never merged" +
            " with commercial dependency; absence of an edge means no assertion," +
            " not independence."
        }
      });
    }
    if (pathname === "/v1/ma/overview" && request.method === "GET") {
      const relationships = await familyRelationships(env, ["mergers_acquisitions"]);
      return json({
        relationships,
        events: [],
        summary: {
          published_fact_count: relationships.length,
          relationship_count: relationships.length,
          event_count: 0
        },
        abstentions: {
          coverage:
            "M&A coverage is what the published graph asserts; deal candidates" +
            " enter through the candidate -> dual-source -> owner sign-off chain" +
            " and stay local until published."
        }
      });
    }
    if (pathname === "/v1/signals/overview" && request.method === "GET") {
      const relationships = await familyRelationships(env, ["strategic_signal"]);
      return json({
        relationships,
        signal_models: [],
        summary: {
          published_fact_count: relationships.length,
          relationship_count: relationships.length
        },
        abstentions: {
          research_orientation:
            "Strategic signals are research prioritization aids derived from" +
            " disclosed themes; they are NOT investment advice, price predictions" +
            " or trading signals.",
          scoring:
            "Signal models without a scored run report has_scored_run=false; no" +
            " synthetic scores are shown."
        }
      });
    }

    const empireMatch = pathname.match(
      /^\/v1\/entities\/([0-9a-fA-F-]{36})\/empire$/
    );
    if (empireMatch && request.method === "GET") {
      return entityEmpire(env, empireMatch[1]);
    }

    if (pathname === "/v1/entities" && request.method === "GET") {
      const query = url.searchParams.get("q") ?? "";
      if (!query.trim()) {
        return badRequest("q query parameter is required");
      }
      return searchEntities(env, query);
    }

    if (pathname === "/v1/explore" && request.method === "POST") {
      const body = await readJsonBody(request);
      const focusEntityId = body?.focus?.object_id;
      if (!focusEntityId) {
        return badRequest("focus.object_id is required");
      }
      return exploreGraph(env, {
        sessionId: body.session_id,
        focusEntityId,
        direction: normalizeDirection(body.direction),
        hops: body.hops,
        budget: normalizeBudget(body.budget),
        activeLayers: Array.isArray(body.active_layers) ? body.active_layers : [],
        filters: body.filters ?? {},
        asOf: body.as_of ?? null
      });
    }

    if (pathname === "/v1/explore/reroot" && request.method === "POST") {
      const body = await readJsonBody(request);
      const newFocus = body?.new_focus_entity_id;
      if (!newFocus) {
        return badRequest("new_focus_entity_id is required");
      }
      return exploreGraph(env, {
        sessionId: body.session_id ?? crypto.randomUUID(),
        focusEntityId: newFocus,
        direction: normalizeDirection(body.direction ?? "both"),
        hops: body.hops ?? 1,
        budget: normalizeBudget(body.budget),
        activeLayers: Array.isArray(body.active_layers) ? body.active_layers : [],
        filters: body.filters ?? {},
        asOf: body.as_of ?? null
      });
    }

    if (pathname === "/v1/explore/expand" && request.method === "POST") {
      const body = await readJsonBody(request);
      const anchor = body?.anchor_entity_id;
      if (!anchor) {
        return badRequest("anchor_entity_id is required");
      }
      const budget = normalizeBudget(body.budget);
      budget.max_nodes = Math.min(
        budget.expand_nodes,
        GRAPH_HARD_LIMITS.max_nodes
      );
      return exploreGraph(env, {
        sessionId: body.session_id ?? crypto.randomUUID(),
        focusEntityId: anchor,
        direction: normalizeDirection(body.direction ?? "both"),
        hops: 1,
        budget,
        activeLayers: Array.isArray(body.active_layers) ? body.active_layers : [],
        filters: body.filters ?? {},
        asOf: body.as_of ?? null
      });
    }

    // --- user-state routes (S10PBT01): cloud is the source of truth ---
    if (pathname === "/v1/saved-views" && request.method === "POST") {
      return createSavedView(env, await readJsonBody(request), json, badRequest);
    }
    const savedViewMatch = pathname.match(/^\/v1\/saved-views\/([0-9a-fA-F-]{36})$/);
    if (savedViewMatch && request.method === "GET") {
      return getSavedView(env, savedViewMatch[1], json, notFound);
    }
    if (savedViewMatch && request.method === "PUT") {
      return updateSavedView(
        env,
        savedViewMatch[1],
        await readJsonBody(request),
        json,
        badRequest,
        notFound
      );
    }
    if (pathname === "/v1/watchlists" && request.method === "GET") {
      return listWatchlists(env, json);
    }
    if (pathname === "/v1/watchlists" && request.method === "POST") {
      return createWatchlist(env, await readJsonBody(request), json, badRequest);
    }
    const watchlistItemsMatch = pathname.match(
      /^\/v1\/watchlists\/([0-9a-fA-F-]{36})\/items$/
    );
    if (watchlistItemsMatch && request.method === "POST") {
      return addWatchlistItem(
        env,
        watchlistItemsMatch[1],
        await readJsonBody(request),
        json,
        badRequest,
        notFound
      );
    }
    if (pathname === "/v1/exploration-log" && request.method === "POST") {
      return appendExplorationLog(env, await readJsonBody(request), json, badRequest);
    }
    if (pathname === "/v1/exploration-log" && request.method === "GET") {
      return listExplorationLog(env, url.searchParams.get("limit"), json);
    }
    if (pathname === "/v1/cloud/runs" && request.method === "GET") {
      return listCloudRuns(env, url.searchParams.get("limit"), json, url.searchParams.get("since"));
    }
    if (pathname === "/v1/cloud/runs/trigger" && request.method === "POST") {
      // Drill hook: requires the CLOUD_SYNC_TRIGGER_TOKEN secret so the
      // public surface cannot burn SEC quota; the daily cron needs no token.
      const token = request.headers.get("authorization") ?? "";
      if (!env.CLOUD_SYNC_TRIGGER_TOKEN || token !== `Bearer ${env.CLOUD_SYNC_TRIGGER_TOKEN}`) {
        return json({ detail: "trigger token required" }, 401);
      }
      return json(await runCloudSync(env, "manual"));
    }

    // --- EEI-F01: routes the shipped UI declares (were 404 in production) ---
    if (pathname === "/v1/scoring/active-context" && request.method === "GET") {
      const context = await publishedAnalysisContext(env);
      if (!context) {
        return notFound(
          "publication surface carries no analysis context yet; republish required"
        );
      }
      const clientToken = url.searchParams.get("client_refresh_token");
      const clientState =
        clientToken !== null && clientToken !== context.refresh_token
          ? "stale"
          : "current";
      return json({
        ...context,
        client_state: clientState,
        stale_client_semantics:
          "Clients with a different refresh_token must discard cached graph," +
          " score, model and module state and refetch the active context."
      });
    }

    if (pathname === "/v1/supply-chain/overview" && request.method === "GET") {
      return supplyChainOverview(env);
    }

    if (pathname === "/v1/changes" && request.method === "GET") {
      return listChanges(env, url.searchParams.get("since"));
    }

    // EEI-F07/acceptance F-007: the Capital River module (/capital) calls
    // these two routes. The CF-L2 publication surface carries owner-signed
    // published FACTS only; the local capital events are all synthetic demos
    // (derivation_rule NULL, titles "Synthetic ...") and must never reach the
    // public surface. So both routes serve an honest, well-formed EMPTY set -
    // the page then renders its graceful no-published-events state instead of
    // the raw http_404 error the acceptance flagged. When an owner-signed
    // published capital event exists, publish_to_cloud_channel.py would carry
    // it here exactly like relationships.
    if (pathname === "/v1/events" && request.method === "GET") {
      return json([]);
    }
    if (pathname === "/v1/events/amount-summary" && request.method === "GET") {
      return json(emptyAmountSummary(url.searchParams));
    }

    if (pathname === "/v1/meta/build" && request.method === "GET") {
      const meta = await publicationMeta(env);
      return json({
        ...buildInfo(env),
        publisher_version: meta.publisher_version ?? null,
        published_at: meta.published_at ?? null
      });
    }

    const explanationMatch = pathname.match(
      /^\/v1\/scoring\/relationship\/([0-9a-fA-F-]{36})\/explanation$/
    );
    if (explanationMatch && request.method === "GET") {
      return scoreExplanation(env, explanationMatch[1]);
    }

    const evidenceMatch = pathname.match(
      /^\/v1\/evidence\/relationship\/([0-9a-fA-F-]{36})$/
    );
    if (evidenceMatch && request.method === "GET") {
      return evidenceIndex(env, evidenceMatch[1]);
    }

    if (pathname.startsWith("/v1/")) {
      return notFound(`No cloud route for ${request.method} ${pathname}`);
    }
    // Non-API paths fall through to static assets via the assets binding.
    return env.ASSETS.fetch(request);
}

export default {
  async fetch(request, env) {
    let response;
    try {
      response = await handleFetch(request, env);
    } catch (err) {
      // Global fail-closed boundary: any unhandled error (e.g. a D1 limit hit
      // by a fuzzed input) returns a structured 500 that never leaks a stack
      // trace or internal engine error to the client (R-002/S-003 hardening).
      response = json(
        { detail: "internal error", request_id: crypto.randomUUID() },
        500
      );
    }
    return applyEdgeHeaders(response, env);
  },

  // S10PBT02: daily incremental SEC polling with an honest run_log row per
  // run - the 7x24 cloud heartbeat. Deep backfills remain a local-factory
  // job; publication stays owner-gated.
  async scheduled(event, env, ctx) {
    // Hourly = uptime heartbeat (no external fetches); daily 18:00 UTC =
    // SEC incremental sync with rotation/quota discipline.
    if (event.cron === "0 * * * *") {
      ctx.waitUntil(runHealthHeartbeat(env, `cron:${event.cron}`));
      return;
    }
    ctx.waitUntil(runCloudSync(env, `cron:${event.cron}`));
  }
};
