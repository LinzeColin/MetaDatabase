'use strict';
const path = require('node:path');

const DEFAULTS = Object.freeze({
  maxArchiveBytes: 256 * 1024 * 1024,
  maxExpandedBytes: 1024 * 1024 * 1024,
  maxFiles: 5000,
  maxDepth: 12,
  maxSingleFileBytes: 128 * 1024 * 1024,
  allowedExtensions: new Set(['.json', '.html', '.htm', '.md', '.txt', '.csv']),
});

function validateArchiveManifest(manifest, policy = {}) {
  const cfg = { ...DEFAULTS, ...policy };
  if (!manifest || !Array.isArray(manifest.files)) throw new TypeError('manifest files required');
  if (manifest.archiveBytes > cfg.maxArchiveBytes) throw error('ARCHIVE_TOO_LARGE');
  if (manifest.files.length > cfg.maxFiles) throw error('ARCHIVE_TOO_MANY_FILES');
  let expanded = 0;
  const normalized = [];
  for (const file of manifest.files) {
    const raw = String(file.path || '').replaceAll('\\', '/');
    const clean = path.posix.normalize(raw);
    if (!raw || clean.startsWith('../') || clean === '..' || path.posix.isAbsolute(clean) || clean.includes('\0')) {
      throw error('ARCHIVE_PATH_FORBIDDEN');
    }
    const depth = clean.split('/').filter(Boolean).length;
    if (depth > cfg.maxDepth) throw error('ARCHIVE_DEPTH_EXCEEDED');
    const size = Number(file.uncompressedBytes || 0);
    if (!Number.isFinite(size) || size < 0 || size > cfg.maxSingleFileBytes) {
      throw error('ARCHIVE_FILE_TOO_LARGE');
    }
    const ext = path.posix.extname(clean).toLowerCase();
    if (!cfg.allowedExtensions.has(ext)) throw error('ARCHIVE_FILE_TYPE_FORBIDDEN');
    expanded += size;
    normalized.push({ path: clean, uncompressedBytes: size });
  }
  if (expanded > cfg.maxExpandedBytes) throw error('ARCHIVE_EXPANSION_LIMIT');
  return { archiveBytes: Number(manifest.archiveBytes || 0), expandedBytes: expanded, files: normalized };
}

function error(code) {
  return Object.assign(new Error(code), { code });
}

module.exports = { DEFAULTS, validateArchiveManifest };
