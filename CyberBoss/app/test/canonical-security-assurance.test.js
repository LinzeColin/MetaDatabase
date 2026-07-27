"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  ASSURANCE_SCHEMA,
  SOURCE_PACKAGE_SCHEMA,
  SecurityAssuranceError,
  assertSourceClosure,
  buildCorrespondingSourcePackage,
  buildSecurityAssurance,
  scanTextForHighConfidenceSecret,
} = require("../src/services/assurance/canonical-security-assurance");

const projectRoot = path.resolve(__dirname, "../..");
const sourceLockPath = path.join(projectRoot, "machine/source-lock.json");

test("security assurance is deterministic, secret-free, source-complete, and activation-pending", () => {
  const first = buildSecurityAssurance({ projectRoot });
  const second = buildSecurityAssurance({ projectRoot });
  assert.deepEqual(second, first);
  assert.equal(first.schema_version, ASSURANCE_SCHEMA);
  assert.equal(first.product_version, "v0.0.0.5");
  assert.equal(first.evaluation_mode, "local_deterministic_read_only");
  assert.equal(first.status, "passed");
  assert.match(first.report_digest, /^[0-9a-f]{64}$/);
  assert.equal(first.security.high_confidence_secret_hits, 0);
  assert.equal(first.security.environment_file_hits, 0);
  assert.equal(first.security.unaccepted_p0_p1_findings, 0);
  assert.equal(first.security.control_plane_llm_calls, 0);
  assert.equal(first.security.operations_llm_calls, 0);
  assert.equal(first.security.macos_launchd_dependency, false);
  assert.equal(first.sbom.component_count, 129);
  assert.equal(first.sbom.unresolved_license_count, 0);
  assert.equal(first.sbom.strict_dual_license_component_count, 1);
  assert.equal(first.corresponding_source.corresponding_source_complete, true);
  assert.equal(first.corresponding_source.source_count, 3);
  assert.equal(first.corresponding_source.strict_license_expression, "AGPL-3.0-only AND GPL-3.0-only");
  assert.equal(first.corresponding_source.distribution_state, "activation_pending");
  assert.equal(first.access_and_analytics_privacy.external_8765, "unreachable");
  assert.equal(first.access_and_analytics_privacy.forbidden_analytics_payloads_rejected, 5);
  assert.equal(first.access_and_analytics_privacy.second_analytics_database_allowed, false);
  assert.equal(first.external_activation.cloudflare_web_analytics, "activation_pending");
  assert.equal(first.external_activation.real_cloudflare_operations, 0);
});

test("corresponding source package is an exact, source-tree manifest without a parallel archive", () => {
  const sourcePackage = buildCorrespondingSourcePackage({ projectRoot });
  assert.equal(sourcePackage.schema_version, SOURCE_PACKAGE_SCHEMA);
  assert.equal(sourcePackage.source_root, "CyberBoss");
  assert.deepEqual(sourcePackage.source_ids, ["cyberboss", "timeline-for-agent", "whereabouts-mcp"]);
  assert.ok(sourcePackage.file_count >= 100);
  assert.match(sourcePackage.manifest_digest, /^[0-9a-f]{64}$/);
  assert.equal(sourcePackage.archive_materialization, "not_created_repository_source_is_authoritative_package");
  assert.equal(sourcePackage.release_distribution_state, "activation_pending");
  assert.ok(sourcePackage.files.some((entry) => entry.path === "app/package-lock.json"));
  assert.ok(sourcePackage.files.every((entry) => /^[0-9a-f]{64}$/.test(entry.sha256)));
});

test("secret-like content and license closure mutation fail closed without retaining the content", () => {
  assert.equal(scanTextForHighConfidenceSecret("const safe = true;"), false);
  assert.equal(scanTextForHighConfidenceSecret("ghp_" + "a".repeat(24)), true);

  const tampered = JSON.parse(fs.readFileSync(sourceLockPath, "utf8"));
  tampered.whereabouts_license_conflict.preserve_original_license_and_source = false;
  assert.throws(
    () => assertSourceClosure(tampered),
    (error) => error instanceof SecurityAssuranceError && error.code === "ASSURANCE_LICENSE_CLOSURE_INVALID",
  );
});
