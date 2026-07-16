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

console.log("SMOKE_ASSERT_OK routes=15");
