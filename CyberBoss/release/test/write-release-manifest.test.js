"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  PRODUCT_VERSION,
  ReleaseManifestError,
  parseArgs,
  writeReleaseManifest,
} = require("../write-release-manifest");

const RELEASE_COMMIT = "a".repeat(40);
const SOURCE_TREE = "b".repeat(40);
const SOURCE_ARCHIVE_SHA256 = "c".repeat(64);

function argumentsFor(root) {
  return [
    "--release-root", root,
    "--release-commit", RELEASE_COMMIT,
    "--source-tree", SOURCE_TREE,
    "--source-archive-sha256", SOURCE_ARCHIVE_SHA256,
    "--node-version", "v24.18.0",
    "--codex-version", "codex 0.0.0",
    "--codex-auth-file-present", "true",
  ];
}

test("CB-530 release manifest is valid JSON with a real newline terminator and fixed product version", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb530-manifest-"));
  t.after(() => fs.rmSync(root, { force: true, recursive: true }));

  const result = writeReleaseManifest(parseArgs(argumentsFor(root)));
  const text = fs.readFileSync(result.manifestPath, "utf8");
  const parsed = JSON.parse(text);

  assert.equal(text.endsWith("\n"), true);
  assert.equal(text.includes("\\n"), false);
  assert.equal(parsed.product_version, PRODUCT_VERSION);
  assert.equal(parsed.release_commit, RELEASE_COMMIT);
  assert.equal(parsed.source_tree, SOURCE_TREE);
  assert.equal(parsed.source_archive_sha256, SOURCE_ARCHIVE_SHA256);
  assert.equal(parsed.runtime.codex_auth_file_present, true);
  assert.equal(parsed.immutable, true);
});

test("CB-530 release manifest is create-once and rejects malformed identities", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cb530-manifest-"));
  const invalidRoot = fs.mkdtempSync(path.join(os.tmpdir(), "cb530-manifest-invalid-"));
  t.after(() => fs.rmSync(root, { force: true, recursive: true }));
  t.after(() => fs.rmSync(invalidRoot, { force: true, recursive: true }));
  const parsed = parseArgs(argumentsFor(root));

  writeReleaseManifest(parsed);
  assert.throws(
    () => writeReleaseManifest(parsed),
    (error) => error instanceof ReleaseManifestError && error.code === "CB530_RELEASE_MANIFEST_EXISTS",
  );
  assert.throws(
    () => writeReleaseManifest(parseArgs(argumentsFor(invalidRoot).map((value) => (value === RELEASE_COMMIT ? "UPPERCASE" : value)))),
    (error) => error instanceof ReleaseManifestError && error.code === "CB530_RELEASE_MANIFEST_IDENTITY_INVALID",
  );
});
