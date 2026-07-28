"use strict";

// CB-710 / AC-022: the bounds an uploaded archive must satisfy before a single
// byte is extracted. Every limit matches the frozen abuse/quota contract.

const path = require("node:path");

const DEFAULTS = Object.freeze({
  maxArchiveBytes: 256 * 1024 * 1024,
  maxExpandedBytes: 1024 * 1024 * 1024,
  maxFiles: 5000,
  maxDepth: 12,
  maxSingleFileBytes: 128 * 1024 * 1024,
  // Data formats only. An executable, script or archive-in-archive is refused
  // by extension before its bytes are ever touched.
  allowedExtensions: Object.freeze([".json", ".html", ".htm", ".md", ".txt", ".csv"]),
});

class UploadPolicyError extends Error {
  constructor(code) {
    super(code);
    this.name = "UploadPolicyError";
    this.code = code;
  }
}

function mergePolicy(policy = {}) {
  const merged = { ...DEFAULTS, ...policy };
  merged.allowedExtensions = new Set(merged.allowedExtensions);
  return merged;
}

// Normalises a stored archive path and refuses anything that could escape the
// extraction root, hide behind a Windows separator or exceed the depth bound.
function safeArchivePath(raw, config) {
  const candidate = String(raw || "").replaceAll("\\", "/");
  const normalized = path.posix.normalize(candidate);
  if (
    !candidate ||
    normalized === ".." ||
    normalized.startsWith("../") ||
    path.posix.isAbsolute(normalized) ||
    normalized.includes("\0")
  ) {
    throw new UploadPolicyError("ARCHIVE_PATH_FORBIDDEN");
  }
  if (normalized.split("/").filter(Boolean).length > config.maxDepth) {
    throw new UploadPolicyError("ARCHIVE_DEPTH_EXCEEDED");
  }
  if (!config.allowedExtensions.has(path.posix.extname(normalized).toLowerCase())) {
    throw new UploadPolicyError("ARCHIVE_FILE_TYPE_FORBIDDEN");
  }
  return normalized;
}

function validateArchiveManifest(manifest, policy = {}) {
  const config = mergePolicy(policy);
  if (!manifest || !Array.isArray(manifest.files)) {
    throw new UploadPolicyError("ARCHIVE_MANIFEST_INVALID");
  }
  if (Number(manifest.archiveBytes || 0) > config.maxArchiveBytes) {
    throw new UploadPolicyError("ARCHIVE_TOO_LARGE");
  }
  if (manifest.files.length > config.maxFiles) {
    throw new UploadPolicyError("ARCHIVE_TOO_MANY_FILES");
  }
  let expanded = 0;
  const seen = new Set();
  const normalized = [];
  for (const file of manifest.files) {
    const clean = safeArchivePath(file.path, config);
    // Two entries that normalise to the same target would let a later entry
    // silently overwrite an earlier one.
    if (seen.has(clean)) {
      throw new UploadPolicyError("ARCHIVE_DUPLICATE_TARGET");
    }
    seen.add(clean);
    const size = Number(file.uncompressedBytes || 0);
    if (!Number.isFinite(size) || size < 0 || size > config.maxSingleFileBytes) {
      throw new UploadPolicyError("ARCHIVE_FILE_TOO_LARGE");
    }
    expanded += size;
    normalized.push({ path: clean, uncompressedBytes: size });
  }
  if (expanded > config.maxExpandedBytes) {
    throw new UploadPolicyError("ARCHIVE_EXPANSION_LIMIT");
  }
  return Object.freeze({
    archiveBytes: Number(manifest.archiveBytes || 0),
    expandedBytes: expanded,
    files: normalized,
  });
}

module.exports = {
  DEFAULTS,
  UploadPolicyError,
  mergePolicy,
  safeArchivePath,
  validateArchiveManifest,
};
