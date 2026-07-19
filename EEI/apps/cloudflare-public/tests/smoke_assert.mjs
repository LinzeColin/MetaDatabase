// Contract assertions for the cloud worker smoke (S10PAT01). Runs against
// a wrangler dev instance seeded with tests/smoke_seed.sql.
import assert from "node:assert/strict";

const base = process.argv[2] ?? "http://127.0.0.1:8787";
const TSMC = "00000000-0000-4000-8000-000000000001";
const NVIDIA = "00000000-0000-4000-8000-000000000002";
const FOUNDRY_REL = "00000000-0000-4000-9000-000000000001";

async function getJson(path, init) {
  const response = await fetch(`${base}${path}`, init);
  const body = await response.json();
  return { status: response.status, body };
}

const health = await getJson("/health");
assert.equal(health.status, 200);
assert.equal(health.body.status, "ok");
assert.equal(health.body.snapshot_key, "smoke-publication-snapshot");

const explore = await getJson("/v1/explore", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    focus: { object_type: "entity", object_id: NVIDIA },
    active_layers: ["supply_chain_operations"],
    direction: "both",
    hops: 2,
    filters: {},
    budget: { max_nodes: 42, max_edges: 64, expand_nodes: 12 }
  })
});
assert.equal(explore.status, 200);
assert.equal(explore.body.production_context.schema_version, "production-context-v1");
assert.equal(explore.body.focus.canonical_name, "NVIDIA Corporation");
assert.equal(explore.body.nodes.length, 3, "2-hop from NVIDIA must reach TSMC and ASML");
assert.equal(explore.body.edges.length, 2);
assert.ok(explore.body.edges.every((edge) => edge.evidence_count === 2));
assert.equal(explore.body.coverage.source_count, 4);
assert.equal(explore.body.coverage.synthetic_fixture_edges, 0);
assert.equal(explore.body.truncated, false);
assert.equal(
  explore.body.production_context.record_modes.published_relationships.fixture,
  0
);

const reroot = await getJson("/v1/explore/reroot", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    session_id: explore.body.session_id,
    new_focus_entity_id: TSMC,
    direction: "both",
    hops: 1
  })
});
assert.equal(reroot.status, 200);
assert.equal(reroot.body.focus.id, TSMC);
assert.equal(reroot.body.session_id, explore.body.session_id, "session id echoes through reroot");
assert.equal(reroot.body.edges.length, 2, "TSMC touches both published facts at 1 hop");

const expand = await getJson("/v1/explore/expand", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    session_id: explore.body.session_id,
    anchor_entity_id: TSMC,
    direction: "upstream",
    budget: { expand_nodes: 12 }
  })
});
assert.equal(expand.status, 200);
assert.equal(expand.body.edges.length, 1, "upstream of TSMC is the ASML equipment edge");
assert.equal(expand.body.edges[0].relationship_type, "equipment_supply");

const explanation = await getJson(`/v1/scoring/relationship/${FOUNDRY_REL}/explanation`);
assert.equal(explanation.status, 200);
assert.equal(explanation.body.publication_status, "published");
assert.equal(explanation.body.review_status, "human_verified");
assert.equal(explanation.body.raw_score, 88);
assert.equal(explanation.body.evidence_quality, 100);
assert.equal(explanation.body.adjusted_score, 88);
assert.equal(explanation.body.source_threshold.independent_source_count, 2);
assert.equal(explanation.body.source_threshold.met, true);
assert.equal(explanation.body.missing_inputs.length, 0);
assert.equal(explanation.body.evidence.length, 2);
assert.equal(explanation.body.scoring_service_version, "candidate-score-explanation-v1");

const evidence = await getJson(`/v1/evidence/relationship/${FOUNDRY_REL}`);
assert.equal(evidence.status, 200);
assert.equal(evidence.body.evidence_count, 2);
assert.ok(evidence.body.evidence.every((item) => item.source_url.startsWith("https://")));

const search = await getJson("/v1/entities?q=nvidia");
assert.equal(search.status, 200);
assert.equal(search.body.entities.length, 1);
assert.equal(search.body.entities[0].id, NVIDIA);

// R-002/S-003 hardening: a fuzzed long term must fail closed (200, empty, no
// leak) instead of the raw 500 SQLITE_ERROR the fault harness found.
const fuzzSearch = await getJson(`/v1/entities?q=${"A".repeat(5000)}`);
assert.equal(fuzzSearch.status, 200, "over-long search term must not 500");
assert.deepEqual(fuzzSearch.body.entities, []);
// A user wildcard is a literal, not an injected pattern.
const wildcardSearch = await getJson("/v1/entities?q=%25");
assert.equal(wildcardSearch.status, 200);

const missing = await getJson(`/v1/scoring/relationship/00000000-0000-4000-9000-00000000dead/explanation`);
assert.equal(missing.status, 404);

// --- user-state flow (S10PBT01): saved view create -> conflict -> update
// -> restore; watchlist; exploration log. Cloud is the source of truth.
const created = await getJson("/v1/saved-views", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    name: "smoke view",
    workspace_key: "mvp",
    state: { subject: "nvidia", lens: "all", zoom: "L1" },
    schema_version: "saved-view-v1",
    change_note: "smoke create",
    metadata: { origin: "smoke" }
  })
});
assert.equal(created.status, 201);
assert.equal(created.body.schema_version, "saved-view-v1");
assert.equal(created.body.current_version, 1);

const conflict = await getJson(`/v1/saved-views/${created.body.id}`, {
  method: "PUT",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ expected_version: 99, state: { subject: "tsmc" } })
});
assert.equal(conflict.status, 409);
assert.equal(conflict.body.detail.reason, "saved_view_version_conflict");

const updated = await getJson(`/v1/saved-views/${created.body.id}`, {
  method: "PUT",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    expected_version: 1,
    state: { subject: "tsmc", lens: "supply_chain", zoom: "L2" },
    change_note: "smoke update"
  })
});
assert.equal(updated.status, 200);
assert.equal(updated.body.current_version, 2);
assert.equal(updated.body.version_count, 2);

const restored = await getJson(`/v1/saved-views/${created.body.id}`);
assert.equal(restored.status, 200);
assert.equal(restored.body.state.subject, "tsmc");

const watchlist = await getJson("/v1/watchlists", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ name: "smoke watchlist" })
});
assert.equal(watchlist.status, 201);
const item = await getJson(`/v1/watchlists/${watchlist.body.id}/items`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ entity_id: NVIDIA })
});
assert.equal(item.status, 201);
const lists = await getJson("/v1/watchlists");
assert.equal(lists.status, 200);
const smokeList = lists.body.find((entry) => entry.id === watchlist.body.id);
assert.equal(smokeList.items.length, 1);
assert.equal(smokeList.items[0].entity_id, NVIDIA);

const logged = await getJson("/v1/exploration-log", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    session_id: explore.body.session_id,
    action: "reroot",
    focus_entity_id: TSMC,
    payload: { source: "smoke" }
  })
});
assert.equal(logged.status, 201);
const logList = await getJson("/v1/exploration-log?limit=5");
assert.equal(logList.status, 200);
assert.ok(logList.body.some((entry) => entry.id === logged.body.id));

const policyOverview = await getJson("/v1/policy/overview");
assert.equal(policyOverview.status, 200);
assert.equal(policyOverview.body.regulatory_filings.source, "sec_edgar");
assert.equal(policyOverview.body.regulatory_filings.by_year.length, 3);
assert.deepEqual(policyOverview.body.regulatory_filings.by_year[0], { year: 2016, filings: 120 });
// module audit: /policy also needs policy_relationships[] + policy_models[] or
// the page rejects a 200 as policy_overview_http_200.
assert.ok(Array.isArray(policyOverview.body.policy_relationships));
assert.ok(Array.isArray(policyOverview.body.policy_models));

// --- module audit: family + empire surfaces (control/ma/signals/structure) ---
for (const fam of ["control", "ma", "signals"]) {
  const ov = await getJson(`/v1/${fam}/overview`);
  assert.equal(ov.status, 200, `${fam} overview must be 200 (was family_http_404)`);
  assert.ok(Array.isArray(ov.body.relationships), `${fam} relationships[]`);
  assert.equal(typeof ov.body.summary, "object");
  assert.equal(typeof ov.body.abstentions, "object");
}
const maOv = await getJson("/v1/ma/overview");
assert.ok(Array.isArray(maOv.body.events));
const sigOv = await getJson("/v1/signals/overview");
assert.ok(Array.isArray(sigOv.body.signal_models));
const empire = await getJson(`/v1/entities/${NVIDIA}/empire`);
assert.equal(empire.status, 200, "empire route must exist (structure page)");
assert.equal(typeof empire.body.focus, "object");
assert.equal(typeof empire.body.structure, "object");
assert.equal(empire.body.data_mode, "cloud_publication");
assert.equal(empire.body.focus.canonical_name, "NVIDIA Corporation");
const badEmpire = await getJson(`/v1/entities/00000000-0000-4000-9000-00000000dead/empire`);
assert.equal(badEmpire.status, 404, "empire fails closed for unknown entity");

// --- EEI-F01: routes the shipped UI declares must exist in the cloud ---
const activeContext = await getJson("/v1/scoring/active-context");
assert.equal(activeContext.status, 200);
assert.equal(activeContext.body.schema_version, "active-analysis-context-v1");
assert.equal(activeContext.body.context_key, "global");
assert.equal(activeContext.body.client_state, "current");
assert.equal(activeContext.body.refresh_generation, 7);
assert.equal(activeContext.body.model_version, "business-empire-model-v2@2");
const staleContext = await getJson(
  "/v1/scoring/active-context?client_refresh_token=not-the-current-token"
);
assert.equal(staleContext.body.client_state, "stale");

const supplyChain = await getJson("/v1/supply-chain/overview");
assert.equal(supplyChain.status, 200);
assert.equal(supplyChain.body.stages.length, 2);
assert.equal(supplyChain.body.relationships.length, 2);
assert.ok(supplyChain.body.relationships.every((row) => row.owner_signed_published));
assert.ok(supplyChain.body.relationships.every((row) => row.fixture_flag === false));
assert.equal(supplyChain.body.summary.published_fact_count, 2);
assert.equal(supplyChain.body.summary.demo_or_candidate_count, 0);

const changes = await getJson("/v1/changes");
assert.equal(changes.status, 200);
assert.ok(Array.isArray(changes.body));
assert.equal(changes.body.length, 2);
assert.equal(changes.body[0].change_type, "relationship_published");

// --- EEI-F07 (acceptance F-007): Capital River routes serve honest empty ---
const events = await getJson("/v1/events?entity=00000000-0000-4000-8000-000000000006");
assert.equal(events.status, 200);
assert.ok(Array.isArray(events.body));
assert.equal(events.body.length, 0, "no synthetic capital events reach the public surface");
const amountSummary = await getJson("/v1/events/amount-summary?currency=USD");
assert.equal(amountSummary.status, 200);
assert.equal(amountSummary.body.schema_version, "event-amount-semantics-v1");
assert.equal(amountSummary.body.event_count, 0);
assert.equal(amountSummary.body.bucket_count, 0);
assert.equal(amountSummary.body.cross_bucket_summation_performed, false);
assert.equal(amountSummary.body.comparable_reported_total_available, false);
assert.deepEqual(amountSummary.body.buckets, []);
assert.equal(amountSummary.body.filters.currency, "USD", "filters echo the request");
const changesSince = await getJson("/v1/changes?since=2026-07-16T00:00:00Z");
assert.equal(changesSince.body.length, 0, "since filter must exclude older publications");
const changesBad = await getJson("/v1/changes?since=not-a-date");
assert.equal(changesBad.status, 400);

// --- EEI-F02: one snapshot/model identity on the explore surface ---
assert.equal(
  explore.body.production_context.active_scoring_profile_version_id,
  "00000000-0000-4000-a000-000000000001"
);
assert.equal(
  explore.body.production_context.active_scoring_profile.model_version,
  "business-empire-model-v2@2"
);
assert.equal(
  explanation.body.model_version,
  "business-empire-model-v2@2",
  "score explanation carries the published model identity"
);

// --- EEI-F05: no contact identifiers on the public scoring surface ---
// (model_version legitimately uses "@" for version pins; only email-shaped
// tokens are forbidden.)
const explanationText = JSON.stringify(explanation.body);
assert.ok(
  !/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/.test(explanationText),
  "no email addresses in public explanation"
);
assert.ok(!("owner_actor" in (explanation.body.qualifiers ?? {})));

// --- EEI-F07/F08: build binding + security headers on every response ---
const headerProbe = await fetch(`${base}/health`);
assert.ok(headerProbe.headers.get("x-eei-build"), "x-eei-build header present");
assert.equal(headerProbe.headers.get("x-content-type-options"), "nosniff");
assert.ok(headerProbe.headers.get("content-security-policy"));
assert.ok(headerProbe.headers.get("strict-transport-security"));
const buildMeta = await getJson("/v1/meta/build");
assert.equal(buildMeta.status, 200);
assert.equal(buildMeta.body.repo, "LinzeColin/MetaDatabase");
assert.ok("commit" in buildMeta.body);

console.log("SMOKE_ASSERT_OK routes=27 (+module surfaces)");
