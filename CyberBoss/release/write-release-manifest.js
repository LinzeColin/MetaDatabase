#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const PRODUCT_VERSION = "v0.0.0.5";
const COMMIT_PATTERN = /^[0-9a-f]{40}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const FIELDS = Object.freeze([
  "release-root",
  "release-commit",
  "source-tree",
  "source-archive-sha256",
  "node-version",
  "codex-version",
  "codex-auth-file-present",
]);

class ReleaseManifestError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

function parseArgs(argv) {
  const values = Object.create(null);
  if (!Array.isArray(argv) || argv.length !== FIELDS.length * 2) {
    throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_ARGUMENTS_INVALID");
  }
  for (let index = 0; index < argv.length; index += 2) {
    const flag = argv[index];
    const value = argv[index + 1];
    if (typeof flag !== "string" || !flag.startsWith("--")) {
      throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_ARGUMENTS_INVALID");
    }
    const field = flag.slice(2);
    if (!FIELDS.includes(field) || Object.hasOwn(values, field) || typeof value !== "string" || !value) {
      throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_ARGUMENTS_INVALID");
    }
    values[field] = value;
  }
  if (FIELDS.some((field) => !Object.hasOwn(values, field))) {
    throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_ARGUMENTS_INVALID");
  }
  return Object.freeze(values);
}

function writeReleaseManifest(input) {
  const values = typeof input === "object" && input !== null ? input : parseArgs(input);
  const releaseRoot = values["release-root"];
  const releaseCommit = values["release-commit"];
  const sourceTree = values["source-tree"];
  const sourceArchiveSha256 = values["source-archive-sha256"];
  const nodeVersion = values["node-version"];
  const codexVersion = values["codex-version"];
  const authFilePresent = values["codex-auth-file-present"];

  if (typeof releaseRoot !== "string" || !path.isAbsolute(releaseRoot)) {
    throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_ROOT_INVALID");
  }
  let rootStats;
  try {
    rootStats = fs.lstatSync(releaseRoot);
  } catch {
    throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_ROOT_INVALID");
  }
  if (!rootStats.isDirectory() || rootStats.isSymbolicLink()) {
    throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_ROOT_INVALID");
  }
  if (!COMMIT_PATTERN.test(releaseCommit) || !COMMIT_PATTERN.test(sourceTree) || !SHA256_PATTERN.test(sourceArchiveSha256)) {
    throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_IDENTITY_INVALID");
  }
  if (!isSafeVersion(nodeVersion) || !isSafeVersion(codexVersion) || !["true", "false"].includes(authFilePresent)) {
    throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_RUNTIME_INVALID");
  }

  const manifest = Object.freeze({
    schema_version: 1,
    product_version: PRODUCT_VERSION,
    release_commit: releaseCommit,
    source_tree: sourceTree,
    source_archive_sha256: sourceArchiveSha256,
    runtime: Object.freeze({
      node_version: nodeVersion,
      codex_version: codexVersion,
      codex_auth_file_present: authFilePresent === "true",
    }),
    immutable: true,
  });
  const manifestPath = path.join(releaseRoot, "release-manifest.json");
  let descriptor;
  try {
    descriptor = fs.openSync(manifestPath, "wx", 0o640);
    fs.writeFileSync(descriptor, `${JSON.stringify(manifest)}\n`, "utf8");
    fs.fsyncSync(descriptor);
  } catch (error) {
    if (error && error.code === "EEXIST") {
      throw new ReleaseManifestError("CB530_RELEASE_MANIFEST_EXISTS");
    }
    throw error;
  } finally {
    if (typeof descriptor === "number") {
      fs.closeSync(descriptor);
    }
  }
  return Object.freeze({ manifest, manifestPath });
}

function isSafeVersion(value) {
  return typeof value === "string" && value.length > 0 && value.length <= 256 && !/[\r\n\u0000]/.test(value);
}

function main(argv = process.argv.slice(2)) {
  const result = writeReleaseManifest(parseArgs(argv));
  process.stdout.write(`${JSON.stringify(Object.freeze({
    status: "passed",
    code: "CB530_RELEASE_MANIFEST_WRITTEN",
    release_commit: result.manifest.release_commit,
    product_version: result.manifest.product_version,
  }))}\n`);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    const code = error instanceof ReleaseManifestError ? error.code : "CB530_RELEASE_MANIFEST_WRITE_FAILED";
    process.stderr.write(`${JSON.stringify(Object.freeze({ status: "failed", code }))}\n`);
    process.exitCode = 2;
  }
}

module.exports = { PRODUCT_VERSION, ReleaseManifestError, parseArgs, writeReleaseManifest };
