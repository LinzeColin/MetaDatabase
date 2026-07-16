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

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...CORS_HEADERS }
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

async function publishedRelationshipCount(env) {
  const row = await env.EEI_PUB.prepare(
    "SELECT COUNT(*) AS n FROM relationships"
  ).first();
  return Number(row?.n ?? 0);
}

async function productionContext(env, requestAsOf) {
  const [meta, snapshot, publishedCount] = await Promise.all([
    publicationMeta(env),
    activeSnapshot(env),
    publishedRelationshipCount(env)
  ]);
  return {
    schema_version: "production-context-v1",
    request_as_of: requestAsOf ?? null,
    graph_query_version: GRAPH_QUERY_VERSION,
    scoring_service_version: SCORING_SERVICE_VERSION,
    active_scoring_profile_version_id: null,
    active_scoring_profile: null,
    active_analysis_context: {
      surface: "cloud_publication",
      snapshot_key: snapshot?.snapshot_key ?? null,
      snapshot_status: snapshot?.status ?? null,
      as_of: snapshot?.as_of ?? null,
      published_at: meta.published_at ?? null,
      publisher_version: meta.publisher_version ?? null
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
    model_version: "cloud-publication-surface",
    profile_version: "cloud-publication-surface",
    profile_version_id: null,
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

async function searchEntities(env, query) {
  const term = `%${query.trim()}%`;
  const { results } = await env.EEI_PUB.prepare(
    "SELECT id, canonical_name, entity_type, status FROM entities" +
      " WHERE canonical_name LIKE ? COLLATE NOCASE ORDER BY canonical_name LIMIT 20"
  )
    .bind(term)
    .all();
  return json({ query: query.trim(), entities: results ?? [] });
}

async function readJsonBody(request) {
  try {
    return await request.json();
  } catch {
    return null;
  }
}

export default {
  async fetch(request, env) {
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
        graph_query_version: GRAPH_QUERY_VERSION
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
      return json({
        schema_version: "cloud-policy-overview-v1",
        regulatory_filings: {
          source: "sec_edgar",
          by_year: (results ?? []).map((row) => ({
            year: Number(row.year),
            filings: Number(row.filings)
          }))
        }
      });
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
