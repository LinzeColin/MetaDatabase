import assert from "node:assert/strict";
import test from "node:test";
import {
  assetSetSha256,
  evaluateOwnerAssetRightsAttestation,
  localEntries,
} from "../scripts/verify-assets.mjs";

function validAttestation() {
  const entries = localEntries();
  return {
    schema_version: "1.0.0",
    record_type: "OWNER_NONCOMMERCIAL_HELLO_KITTY_ASSET_RIGHTS_ATTESTATION",
    record_id: "TEST-NONCOMMERCIAL-ATTESTATION",
    project: "Personal-WorkBench",
    owner_decision: "APPROVED",
    rights_statement: "Owner attests to noncommercial public use.",
    source_record: "Exact checked-in asset set.",
    evidence_origin: "Owner attestation for this test.",
    scope: {
      target: "Personal-WorkBench",
      non_commercial_public_use: true,
      commercial_use: "NOT_AUTHORIZED",
      public_distribution_of_exact_assets: true,
      exact_asset_bytes_only: true,
    },
    authorized_asset_set: {
      asset_count: entries.length,
      sha256: assetSetSha256(entries),
      container_paths_unchanged: true,
    },
    first_party_license_included: false,
    independent_legal_verification: "NOT_PERFORMED",
  };
}

test("owner noncommercial attestation must bind the exact current asset set", () => {
  const decision = evaluateOwnerAssetRightsAttestation(validAttestation());

  assert.equal(decision.approved, true);
  assert.equal(decision.asset_count, 37);
  assert.equal(decision.reasons.length, 0);
});

test("attestation cannot approve commercial scope or a changed asset fingerprint", () => {
  const commercial = validAttestation();
  commercial.scope.commercial_use = "AUTHORIZED";
  assert.equal(evaluateOwnerAssetRightsAttestation(commercial).approved, false);

  const changedFingerprint = validAttestation();
  changedFingerprint.authorized_asset_set.sha256 = "0".repeat(64);
  const decision = evaluateOwnerAssetRightsAttestation(changedFingerprint);
  assert.equal(decision.approved, false);
  assert.ok(decision.reasons.includes("authorized_asset_set.sha256"));

  const wrongProject = validAttestation();
  wrongProject.project = "Other-Project";
  assert.equal(evaluateOwnerAssetRightsAttestation(wrongProject).approved, false);
});
