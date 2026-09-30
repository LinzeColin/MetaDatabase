// Publication-gate smoke (Owner ruling 2026-09-30, 官方单来源可上图).
//
// Runs AFTER smoke_assert.mjs against the same wrangler dev instance. It publishes
// a parent/child pair backed by ONE official first-hand source (GLEIF) through the
// real internal publish channel - the same route the OVH publisher uses - and
// asserts the worker serves it as evidence_tier=single_official with the original
// link, and that the score explanation counts one official source as meeting its
// threshold. Kept separate so the base seed and its counts stay untouched.
import assert from "node:assert/strict";

const base = process.argv[2] ?? "http://127.0.0.1:8787";
const token = process.env.EEI_SMOKE_PUBLISH_TOKEN;
assert.ok(token, "EEI_SMOKE_PUBLISH_TOKEN must be set (wrangler dev --var)");

const NVIDIA = "00000000-0000-4000-8000-000000000002";
const ACME_PARENT = "00000000-0000-4000-8000-000000000004";
const ACME_CHILD = "00000000-0000-4000-8000-000000000005";
const ACME_REL = "00000000-0000-4000-9000-000000000003";
const ACME_SUPPLY_REL = "00000000-0000-4000-9000-000000000004";
const GLEIF_URL = "https://api.gleif.org/api/v1/lei-records/549300ACMEHOLDINGS00/direct-children";

async function getJson(path, init) {
  const response = await fetch(`${base}${path}`, init);
  return { status: response.status, body: await response.json() };
}

const publish = await getJson("/v1/internal/publish/exec", {
  method: "POST",
  headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
  body: JSON.stringify({
    statements: [
      "INSERT INTO entities(id, canonical_name, entity_type, status) VALUES" +
        ` ('${ACME_PARENT}', 'ACME Holdings plc', 'legal_entity', 'research_target'),` +
        ` ('${ACME_CHILD}', 'ACME Trading Ltd', 'legal_entity', 'research_target');`,
      "INSERT INTO relationships(id, subject_entity_id, object_entity_id, relationship_type," +
        " relationship_family, status, confidence, observed_at, published_at, qualifiers_json," +
        " evidence_tier) VALUES" +
        ` ('${ACME_REL}', '${ACME_CHILD}', '${ACME_PARENT}', 'subsidiary_of',` +
        " 'corporate_structure', 'reported', 0.95, '2026-07-14T00:00:00+00:00'," +
        " '2026-07-15T00:00:00+00:00'," +
        ` '{"source_threshold_policy": {"minimum_independent_sources": 1,` +
        ` "independent_source_count": 1, "policy": "official_single_source"}}',` +
        " 'single_official');",
      "INSERT INTO relationship_evidence(relationship_id, source_document_id, role, locator," +
        " support_excerpt, source_url, source_title, publisher, document_date) VALUES" +
        ` ('${ACME_REL}', 'doc-gleif-acme', 'supports', 'GLEIF direct-children relationship',` +
        " 'ACME Trading Ltd is a direct subsidiary of ACME Holdings plc per GLEIF.'," +
        ` '${GLEIF_URL}', 'GLEIF relationship for ACME Holdings plc',` +
        " 'Global LEI Foundation', '2026-07-14');",
      "INSERT INTO relationships(id, subject_entity_id, object_entity_id, relationship_type," +
        " relationship_family, status, confidence, observed_at, published_at, qualifiers_json," +
        " evidence_tier) VALUES" +
        ` ('${ACME_SUPPLY_REL}', '${ACME_CHILD}', '${ACME_PARENT}', 'foundry_supply',` +
        " 'supply_chain_operations', 'reported', 0.9, '2026-07-14T00:00:00+00:00'," +
        " '2026-07-15T00:00:00+00:00', NULL, 'single_official');",
      "INSERT INTO relationship_evidence(relationship_id, source_document_id, role," +
        " source_url, publisher) VALUES" +
        ` ('${ACME_SUPPLY_REL}', 'doc-10k-acme', 'context', 'ftp://example.test/ignored',` +
        " 'Aaa Non Supporting')," +
        ` ('${ACME_SUPPLY_REL}', 'doc-10k-acme', 'supports',` +
        " 'https://www.sec.gov/Archives/edgar/data/1/acme-10k.htm', 'SEC EDGAR');",
      "INSERT OR REPLACE INTO publication_meta(key, value) VALUES" +
        " ('published_relationship_count', '4')," +
        " ('relationships_as_of', '2026-07-14T00:00:00+00:00');",
      "UPDATE relationships SET evidence_tier = 'multi_source'" +
        " WHERE id IN ('00000000-0000-4000-9000-000000000001'," +
        " '00000000-0000-4000-9000-000000000002');"
    ]
  })
});
assert.equal(publish.status, 200, JSON.stringify(publish.body));
assert.equal(publish.body.ok, true);

const explore = (focus) =>
  getJson("/v1/explore", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      focus: { object_type: "entity", object_id: focus },
      active_layers: [],
      direction: "both",
      hops: 1,
      filters: {},
      budget: { max_nodes: 42, max_edges: 64, expand_nodes: 12 }
    })
  });

// One official source is enough: the edge is on the graph, labelled, and linked.
const official = await explore(ACME_PARENT);
assert.equal(official.status, 200);
assert.equal(official.body.edges.length, 2);
const edge = official.body.edges.find((item) => item.id === ACME_REL);
assert.equal(edge.evidence_tier, "single_official");
assert.equal(edge.evidence_count, 1);
assert.equal(edge.source_url, GLEIF_URL);
assert.equal(edge.source_publisher, "Global LEI Foundation");

// The link on the edge is the SUPPORTING http(s) original, never a context row that
// merely sorts first.
const supplyEdge = official.body.edges.find((item) => item.id === ACME_SUPPLY_REL);
assert.equal(supplyEdge.source_url, "https://www.sec.gov/Archives/edgar/data/1/acme-10k.htm");
assert.equal(supplyEdge.source_publisher, "SEC EDGAR");

// The reviewed multi-source edges keep their own tier.
const reviewed = await explore(NVIDIA);
assert.ok(reviewed.body.edges.length >= 1);
assert.ok(reviewed.body.edges.every((item) => item.evidence_tier === "multi_source"));

const evidence = await getJson(`/v1/evidence/relationship/${ACME_REL}`);
assert.equal(evidence.status, 200);
assert.equal(evidence.body.evidence_tier, "single_official");
assert.equal(evidence.body.evidence_count, 1);
assert.equal(evidence.body.evidence[0].source_url, GLEIF_URL);

// One official source meets ITS threshold: not reported as a missing-source gap.
const explanation = await getJson(`/v1/scoring/relationship/${ACME_REL}/explanation`);
assert.equal(explanation.status, 200);
assert.equal(explanation.body.evidence_tier, "single_official");
assert.equal(explanation.body.source_threshold.minimum_independent_sources, 1);
assert.equal(explanation.body.source_threshold.independent_source_count, 1);
assert.equal(explanation.body.source_threshold.met, true);
assert.equal(
  explanation.body.missing_inputs.some((item) => item.startsWith("independent_source_threshold")),
  false
);

// The policy the surface advertises matches what the publisher enforces, and the
// count/as-of come from what the publisher recorded (no per-request table scan).
const policy = official.body.production_context.publication_policy;
assert.equal(policy.official_single_source_publishable, true);
assert.equal(policy.official_source_tier_max, 1);
assert.equal(policy.official_requires_openable_original, true);
assert.equal(policy.non_official_minimum_independent_sources, 2);
assert.equal(policy.non_official_requires_human_review, true);
assert.equal(policy.minimum_independent_sources, 2, "the non-official rule is unchanged");
assert.equal(official.body.production_context.record_modes.published_relationships.total, 4);
assert.equal(
  official.body.production_context.active_analysis_context.relationships_as_of,
  "2026-07-14T00:00:00+00:00"
);

// The control overview no longer calls a single-official edge "owner signed".
const control = await getJson("/v1/control/overview");
const acme = control.body.relationships.find((row) => row.id === ACME_REL);
assert.equal(acme.evidence_tier, "single_official");
assert.equal(acme.owner_signed_published, false);

// The supply-chain view stamps the tier too (it was calling everything owner-signed).
const supply = await getJson("/v1/supply-chain/overview");
const supplyRow = supply.body.relationships.find((row) => row.id === ACME_SUPPLY_REL);
assert.equal(supplyRow.evidence_tier, "single_official");
assert.equal(supplyRow.owner_signed_published, false);

console.log("OFFICIAL_SINGLE_SOURCE_GATE ok");
