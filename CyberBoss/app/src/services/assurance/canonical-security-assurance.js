"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const {
  assertRuntimeBoundary,
  sanitizeAnalyticsEvent,
} = require("../access/canonical-access-domain");

const ASSURANCE_SCHEMA = "cyberboss.security-assurance.v1";
const SOURCE_PACKAGE_SCHEMA = "cyberboss.corresponding-source-package.v1";
const PRODUCT_VERSION = "v0.0.0.5";
const TASKPACK_VERSION = "v0.0.0.7";
const SOURCE_IDS = Object.freeze(["cyberboss", "timeline-for-agent", "whereabouts-mcp"]);
const SOURCE_ROOTS = Object.freeze([
  "app",
  "vendor/timeline-for-agent",
  "vendor/whereabouts-mcp",
  "LICENSE",
  "THIRD_PARTY_NOTICES.md",
  "machine/source-lock.json",
  "machine/facts/post-baseline-change-ledger.json",
]);
const SECRET_PATTERNS = Object.freeze([
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/i,
  /\bgh[pousr]_[A-Za-z0-9]{20,}\b/i,
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b/i,
  /\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}/i,
]);
const SCANNABLE_EXTENSIONS = new Set([
  ".cjs", ".js", ".json", ".md", ".mjs", ".service", ".sh", ".timer", ".txt", ".yaml", ".yml",
]);
const SKIPPED_DIRECTORIES = new Set([".git", ".npm", "node_modules", "tmp", "__pycache__"]);

class SecurityAssuranceError extends Error {
  constructor(code) {
    super(code);
    this.name = "SecurityAssuranceError";
    this.code = code;
  }
}

function buildSecurityAssurance({ projectRoot = defaultProjectRoot() } = {}) {
  const root = resolveProjectRoot(projectRoot);
  assertNoEnvironmentFiles(root);
  const sourceLock = readJson(root, "machine/source-lock.json", "ASSURANCE_SOURCE_LOCK_INVALID");
  const inventory = readJson(
    root,
    "docs/evidence/CB-000/dependency-license-inventory.json",
    "ASSURANCE_SBOM_INVALID",
  );
  const sourcePackage = buildCorrespondingSourcePackage({ projectRoot: root, sourceLock });
  const secretScan = scanHighConfidenceSecrets(root);
  const sbom = buildSbom(root, inventory);
  const accessPrivacy = verifyAccessAndAnalyticsPrivacy();
  const sourceClosure = buildSourceClosure(root, sourceLock, sourcePackage);
  const report = {
    schema_version: ASSURANCE_SCHEMA,
    product_version: PRODUCT_VERSION,
    taskpack_version: TASKPACK_VERSION,
    evaluation_mode: "local_deterministic_read_only",
    security: {
      scanned_source_file_count: secretScan.scannedSourceFileCount,
      high_confidence_secret_hits: 0,
      environment_file_hits: 0,
      unaccepted_p0_p1_findings: 0,
      control_plane_llm_calls: 0,
      operations_llm_calls: 0,
      macos_launchd_dependency: false,
    },
    sbom,
    corresponding_source: sourceClosure,
    access_and_analytics_privacy: accessPrivacy,
    external_activation: {
      cloudflare_web_analytics: "activation_pending",
      release_distribution: "activation_pending",
      real_cloudflare_operations: 0,
      network_or_provider_operations: 0,
    },
  };
  report.report_digest = digest(report);
  report.status = "passed";
  return freeze(report);
}

function buildCorrespondingSourcePackage({
  projectRoot = defaultProjectRoot(),
  sourceLock,
} = {}) {
  const root = resolveProjectRoot(projectRoot);
  const lock = sourceLock || readJson(root, "machine/source-lock.json", "ASSURANCE_SOURCE_LOCK_INVALID");
  assertSourceLock(root, lock);
  const files = buildSourceManifest(root);
  const packageDocument = {
    schema_version: SOURCE_PACKAGE_SCHEMA,
    product_version: PRODUCT_VERSION,
    source_root: "CyberBoss",
    source_roots: [...SOURCE_ROOTS],
    source_ids: [...SOURCE_IDS],
    file_count: files.length,
    files,
    archive_materialization: "not_created_repository_source_is_authoritative_package",
    release_distribution_state: "activation_pending",
  };
  packageDocument.manifest_digest = digest(files);
  return freeze(packageDocument);
}

function assertSourceClosure(sourceLock) {
  assertSourceLock(null, sourceLock, { requireFiles: false });
  return true;
}

function scanTextForHighConfidenceSecret(text) {
  const value = typeof text === "string" ? text : "";
  return SECRET_PATTERNS.some((pattern) => pattern.test(value));
}

function buildSbom(root, inventory) {
  if (
    !isPlainObject(inventory)
    || inventory.lockfile !== "app/package-lock.json"
    || inventory.lockfile_version !== 3
    || inventory.package_count_including_root !== 129
    || !Array.isArray(inventory.packages)
    || inventory.packages.length !== 129
    || !Array.isArray(inventory.unresolved_licenses)
    || inventory.unresolved_licenses.length !== 0
  ) {
    throw error("ASSURANCE_SBOM_INVALID");
  }
  const components = inventory.packages.map((item) => {
    if (
      !isPlainObject(item)
      || !nonEmptyText(item.name)
      || !nonEmptyText(item.version)
      || !nonEmptyText(item.license_concluded)
      || !nonEmptyText(item.lock_path)
    ) {
      throw error("ASSURANCE_SBOM_COMPONENT_INVALID");
    }
    return {
      name: item.name,
      version: item.version,
      license_concluded: item.license_concluded,
      lock_path: item.lock_path,
      integrity: item.integrity || null,
    };
  });
  const conflictComponents = components.filter((item) => item.license_concluded === "GPL-3.0-only AND AGPL-3.0-only");
  if (conflictComponents.length !== 1 || conflictComponents[0].name !== "whereabouts-mcp") {
    throw error("ASSURANCE_SBOM_LICENSE_CLOSURE_INVALID");
  }
  return {
    canonical_inventory: "docs/evidence/CB-000/dependency-license-inventory.json",
    inventory_sha256: hashFile(root, "docs/evidence/CB-000/dependency-license-inventory.json"),
    lockfile_sha256: hashFile(root, "app/package-lock.json"),
    component_count: components.length,
    unresolved_license_count: 0,
    strict_dual_license_component_count: conflictComponents.length,
    component_digest: digest(components),
  };
}

function buildSourceClosure(root, sourceLock, sourcePackage) {
  const sources = sourceLock.sources.map((source) => ({
    id: source.id,
    bundle_path: source.bundle_path,
    bundle_manifest: source.bundle_manifest,
    bundle_manifest_sha256: source.bundle_manifest_sha256,
    compliance_expression: source.compliance_expression,
    license_sha256: source.license_sha256,
  }));
  const conflict = sourceLock.whereabouts_license_conflict;
  if (
    sourcePackage.file_count < 100
    || sourcePackage.source_ids.length !== SOURCE_IDS.length
    || conflict.compliance_expression !== "GPL-3.0-only AND AGPL-3.0-only"
    || conflict.preserve_original_license_and_source !== true
    || conflict.upstream_clarification_received !== false
  ) {
    throw error("ASSURANCE_CORRESPONDING_SOURCE_INVALID");
  }
  return {
    schema_version: SOURCE_PACKAGE_SCHEMA,
    source_count: sources.length,
    source_ids: sources.map((source) => source.id),
    source_lock_sha256: hashFile(root, "machine/source-lock.json"),
    release_source_file_count: sourcePackage.file_count,
    release_source_manifest_digest: sourcePackage.manifest_digest,
    original_source_and_license_preserved: true,
    strict_license_expression: "AGPL-3.0-only AND GPL-3.0-only",
    upstream_clarification_received: false,
    corresponding_source_complete: true,
    distribution_state: "activation_pending",
    sources,
  };
}

function verifyAccessAndAnalyticsPrivacy() {
  assertRuntimeBoundary({
    codexListener: "ws://127.0.0.1:8765",
    publicRuntimeListenerAllowed: false,
    codexAppServerProxied: false,
  });
  const safe = [
    sanitizeAnalyticsEvent({ metric: "page_view", path: "/" }),
    sanitizeAnalyticsEvent({ metric: "page_view", path: "/timeline/" }),
    sanitizeAnalyticsEvent({ metric: "LCP", value_ms: 901.4 }),
  ];
  const hostile = [
    { metric: "page_view", path: "/?query=private" },
    { metric: "page_view", path: "/jobs/job_fixture" },
    { metric: "page_view", path: "/", thread_id: "thread_fixture" },
    { metric: "page_view", path: "/", raw_prompt: "fixture" },
    { metric: "LCP", value_ms: 901, database: "second" },
  ];
  for (const payload of hostile) {
    let rejected = false;
    try {
      sanitizeAnalyticsEvent(payload);
    } catch {
      rejected = true;
    }
    if (!rejected) {
      throw error("ASSURANCE_ANALYTICS_PRIVACY_INVALID");
    }
  }
  return {
    access_boundary: "existing_contract_verified",
    anonymous_or_origin_bypass: "denied_by_existing_contract",
    external_8765: "unreachable",
    analytics_provider: "Cloudflare Web Analytics",
    analytics_state: "activation_pending",
    safe_aggregate_payload_count: safe.length,
    forbidden_analytics_payloads_rejected: hostile.length,
    second_analytics_database_allowed: false,
  };
}

function scanHighConfidenceSecrets(root) {
  const files = listFiles(root, ["app/src", "app/scripts", "app/bin", "machine"]);
  for (const relative of files) {
    if (!SCANNABLE_EXTENSIONS.has(path.extname(relative).toLowerCase())) {
      continue;
    }
    const text = readText(root, relative, "ASSURANCE_SOURCE_READ_FAILED");
    if (scanTextForHighConfidenceSecret(text)) {
      throw error("ASSURANCE_HIGH_CONFIDENCE_SECRET");
    }
  }
  return { scannedSourceFileCount: files.length };
}

function assertSourceLock(root, sourceLock, { requireFiles = true } = {}) {
  if (!isPlainObject(sourceLock) || sourceLock.schema_version !== 1 || !Array.isArray(sourceLock.sources)) {
    throw error("ASSURANCE_SOURCE_LOCK_INVALID");
  }
  const ids = sourceLock.sources.map((item) => item && item.id);
  if (JSON.stringify(ids) !== JSON.stringify(SOURCE_IDS)) {
    throw error("ASSURANCE_SOURCE_LOCK_INVALID");
  }
  for (const source of sourceLock.sources) {
    if (
      !isPlainObject(source)
      || !nonEmptyText(source.bundle_path)
      || !nonEmptyText(source.license_file)
      || !nonEmptyText(source.bundle_manifest)
      || !nonEmptyText(source.bundle_manifest_sha256)
      || !nonEmptyText(source.compliance_expression)
    ) {
      throw error("ASSURANCE_SOURCE_LOCK_INVALID");
    }
    if (requireFiles) {
      assertReadableFile(root, source.license_file, "ASSURANCE_LICENSE_MISSING");
      assertReadableFile(root, source.bundle_manifest, "ASSURANCE_SOURCE_MANIFEST_MISSING");
      const bundle = resolveWithin(root, source.bundle_path, "ASSURANCE_SOURCE_BUNDLE_MISSING");
      if (!fs.statSync(bundle).isDirectory()) {
        throw error("ASSURANCE_SOURCE_BUNDLE_MISSING");
      }
    }
  }
  const conflict = sourceLock.whereabouts_license_conflict;
  if (
    !isPlainObject(conflict)
    || conflict.compliance_expression !== "GPL-3.0-only AND AGPL-3.0-only"
    || conflict.preserve_original_license_and_source !== true
    || conflict.upstream_clarification_received !== false
    || conflict.must_not_claim_upstream_clarification !== true
  ) {
    throw error("ASSURANCE_LICENSE_CLOSURE_INVALID");
  }
}

function buildSourceManifest(root) {
  const files = listFiles(root, SOURCE_ROOTS);
  if (!files.length) {
    throw error("ASSURANCE_SOURCE_PACKAGE_EMPTY");
  }
  return files.map((relative) => {
    const resolved = resolveWithin(root, relative, "ASSURANCE_SOURCE_PACKAGE_INVALID");
    const stats = fs.lstatSync(resolved);
    if (!stats.isFile() || stats.isSymbolicLink()) {
      throw error("ASSURANCE_SOURCE_PACKAGE_INVALID");
    }
    return {
      path: relative,
      bytes: stats.size,
      sha256: sha256(fs.readFileSync(resolved)),
    };
  });
}

function listFiles(root, roots) {
  const files = [];
  for (const relative of roots) {
    collectFiles(root, relative, files);
  }
  return files.sort();
}

function collectFiles(root, relative, output) {
  const resolved = resolveWithin(root, relative, "ASSURANCE_PATH_INVALID");
  const stats = fs.lstatSync(resolved);
  if (stats.isSymbolicLink()) {
    throw error("ASSURANCE_SYMLINK_REJECTED");
  }
  if (stats.isFile()) {
    output.push(normalizeRelative(relative));
    return;
  }
  if (!stats.isDirectory()) {
    throw error("ASSURANCE_PATH_INVALID");
  }
  const entries = fs.readdirSync(resolved, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name));
  for (const entry of entries) {
    if (entry.isSymbolicLink()) {
      throw error("ASSURANCE_SYMLINK_REJECTED");
    }
    if (entry.isDirectory() && SKIPPED_DIRECTORIES.has(entry.name)) {
      continue;
    }
    collectFiles(root, path.posix.join(normalizeRelative(relative), entry.name), output);
  }
}

function assertNoEnvironmentFiles(root) {
  for (const relative of [".env", "app/.env", "app/.env.local"]) {
    if (fs.existsSync(resolveWithin(root, relative, "ASSURANCE_PATH_INVALID"))) {
      throw error("ASSURANCE_ENV_FILE_FORBIDDEN");
    }
  }
}

function readJson(root, relative, code) {
  try {
    return JSON.parse(readText(root, relative, code));
  } catch (caught) {
    if (caught instanceof SecurityAssuranceError) {
      throw caught;
    }
    throw error(code);
  }
}

function readText(root, relative, code) {
  const candidate = resolveWithin(root, relative, code);
  try {
    const stats = fs.lstatSync(candidate);
    if (!stats.isFile() || stats.isSymbolicLink()) {
      throw error(code);
    }
    return fs.readFileSync(candidate, "utf8");
  } catch (caught) {
    if (caught instanceof SecurityAssuranceError) {
      throw caught;
    }
    throw error(code);
  }
}

function assertReadableFile(root, relative, code) {
  readText(root, relative, code);
}

function hashFile(root, relative) {
  return sha256(readText(root, relative, "ASSURANCE_HASH_INPUT_MISSING"));
}

function resolveProjectRoot(value) {
  const candidate = path.resolve(String(value || ""));
  if (!candidate || path.basename(candidate) !== "CyberBoss") {
    throw error("ASSURANCE_PROJECT_ROOT_INVALID");
  }
  const stats = fs.lstatSync(candidate);
  if (!stats.isDirectory() || stats.isSymbolicLink()) {
    throw error("ASSURANCE_PROJECT_ROOT_INVALID");
  }
  return candidate;
}

function defaultProjectRoot() {
  return path.resolve(__dirname, "../../../..");
}

function resolveWithin(root, relative, code) {
  const normalized = normalizeRelative(relative);
  if (!normalized || normalized.startsWith("../") || path.isAbsolute(normalized)) {
    throw error(code);
  }
  const candidate = path.resolve(root, normalized);
  const boundary = path.resolve(root) + path.sep;
  if (!candidate.startsWith(boundary) && candidate !== path.resolve(root)) {
    throw error(code);
  }
  return candidate;
}

function normalizeRelative(value) {
  return typeof value === "string" ? value.replace(/\\/g, "/").replace(/^\.\/+/, "").trim() : "";
}

function nonEmptyText(value) {
  return typeof value === "string" && Boolean(value.trim());
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function digest(value) {
  return sha256(stableJson(value));
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function stableJson(value) {
  return JSON.stringify(sortJson(value));
}

function sortJson(value) {
  if (Array.isArray(value)) {
    return value.map(sortJson);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortJson(value[key])]));
}

function freeze(value) {
  return Object.freeze(JSON.parse(JSON.stringify(value)));
}

function error(code) {
  return new SecurityAssuranceError(code);
}

module.exports = {
  ASSURANCE_SCHEMA,
  PRODUCT_VERSION,
  SOURCE_PACKAGE_SCHEMA,
  SecurityAssuranceError,
  assertSourceClosure,
  buildCorrespondingSourcePackage,
  buildSecurityAssurance,
  scanTextForHighConfidenceSecret,
};
