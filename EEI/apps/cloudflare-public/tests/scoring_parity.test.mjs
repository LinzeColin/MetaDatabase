// S10PAT01 scoring parity: the JS port must reproduce every Python output
// field exactly over the generated grid. Run via `make test-cloud-parity`
// (regenerates the fixture first) or `node --test` after generation.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { relationshipScoreMetrics } from "../src/scoring.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(
  readFileSync(join(here, "scoring_parity_fixture.json"), "utf8")
);

test("relationship_score_metrics parity across the Python grid", () => {
  assert.equal(fixture.schema_version, "scoring-parity-fixture-v1");
  assert.ok(fixture.cases.length >= 1000, "parity grid unexpectedly small");
  let checked = 0;
  for (const { inputs, expected } of fixture.cases) {
    const actual = relationshipScoreMetrics({
      confidence: inputs.confidence,
      independentSourceCount: inputs.independent_source_count,
      sourceThresholdMet: inputs.source_threshold_met,
      reviewStatus: inputs.review_status,
      publicationStatus: inputs.publication_status,
      factVersionPresent: inputs.fact_version_present,
      evidencePresent: inputs.evidence_present,
      minimumIndependentSources: inputs.minimum_independent_sources
    });
    assert.deepEqual(
      actual,
      expected,
      `parity mismatch for inputs=${JSON.stringify(inputs)}`
    );
    checked += 1;
  }
  assert.equal(checked, fixture.cases.length);
});
