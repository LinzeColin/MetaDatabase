"use strict";

// CB-710 / AC-022: a ZIP reader that decides everything from the central
// directory before inflating anything. Path traversal, symlinks, encryption,
// unsupported methods, oversized members, implausible compression ratios,
// excessive depth and duplicate normalised targets are all refused while the
// archive is still just bytes.

const zlib = require("node:zlib");
const { mergePolicy, safeArchivePath } = require("./upload-policy");

const EOCD_SIGNATURE = 0x06054b50;
const CENTRAL_SIGNATURE = 0x02014b50;
const LOCAL_SIGNATURE = 0x04034b50;
const MAX_EOCD_SEARCH = 65_557;
const MAX_COMPRESSION_RATIO = 200;
const SYMLINK_MODE = 0o120000;
const FILE_TYPE_MASK = 0o170000;

class SafeZipError extends Error {
  constructor(code) {
    super(code);
    this.name = "SafeZipError";
    this.code = code;
  }
}

let crcTable = null;

function crc32(buffer) {
  if (!crcTable) {
    crcTable = Array.from({ length: 256 }, (_unused, index) => {
      let value = index;
      for (let bit = 0; bit < 8; bit += 1) {
        value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
      }
      return value >>> 0;
    });
  }
  let value = 0xffffffff;
  for (const byte of buffer) {
    value = crcTable[(value ^ byte) & 0xff] ^ (value >>> 8);
  }
  return (value ^ 0xffffffff) >>> 0;
}

function findEndOfCentralDirectory(buffer) {
  const start = Math.max(0, buffer.length - MAX_EOCD_SEARCH);
  for (let index = buffer.length - 22; index >= start; index -= 1) {
    if (buffer.readUInt32LE(index) === EOCD_SIGNATURE) {
      return index;
    }
  }
  throw new SafeZipError("ZIP_EOCD_MISSING");
}

function inspectZip(buffer, policy = {}) {
  if (!Buffer.isBuffer(buffer)) {
    throw new SafeZipError("ARCHIVE_BUFFER_REQUIRED");
  }
  const config = mergePolicy(policy);
  if (buffer.length > config.maxArchiveBytes) {
    throw new SafeZipError("ARCHIVE_TOO_LARGE");
  }
  if (buffer.length < 22) {
    throw new SafeZipError("ZIP_EOCD_MISSING");
  }
  const eocd = findEndOfCentralDirectory(buffer);
  const count = buffer.readUInt16LE(eocd + 10);
  const centralSize = buffer.readUInt32LE(eocd + 12);
  const centralOffset = buffer.readUInt32LE(eocd + 16);
  if (count > config.maxFiles) {
    throw new SafeZipError("ARCHIVE_TOO_MANY_FILES");
  }
  if (centralOffset + centralSize > buffer.length) {
    throw new SafeZipError("ZIP_CENTRAL_BOUNDS");
  }

  const entries = [];
  const seenPaths = new Set();
  let cursor = centralOffset;
  let expanded = 0;

  for (let index = 0; index < count; index += 1) {
    if (cursor + 46 > buffer.length || buffer.readUInt32LE(cursor) !== CENTRAL_SIGNATURE) {
      throw new SafeZipError("ZIP_CENTRAL_INVALID");
    }
    const flags = buffer.readUInt16LE(cursor + 8);
    const method = buffer.readUInt16LE(cursor + 10);
    const crc = buffer.readUInt32LE(cursor + 16);
    const compressed = buffer.readUInt32LE(cursor + 20);
    const uncompressed = buffer.readUInt32LE(cursor + 24);
    const nameLength = buffer.readUInt16LE(cursor + 28);
    const extraLength = buffer.readUInt16LE(cursor + 30);
    const commentLength = buffer.readUInt16LE(cursor + 32);
    const externalAttributes = buffer.readUInt32LE(cursor + 38);
    const localOffset = buffer.readUInt32LE(cursor + 42);

    if (flags & 1) {
      throw new SafeZipError("ZIP_ENCRYPTED_ENTRY");
    }
    if (![0, 8].includes(method)) {
      throw new SafeZipError("ZIP_METHOD_UNSUPPORTED");
    }
    const nameStart = cursor + 46;
    const nameEnd = nameStart + nameLength;
    if (nameEnd > buffer.length) {
      throw new SafeZipError("ZIP_NAME_BOUNDS");
    }
    const rawName = buffer.subarray(nameStart, nameEnd).toString("utf8");
    // A symlink member could point outside the extraction root after writing.
    if (((externalAttributes >>> 16) & FILE_TYPE_MASK) === SYMLINK_MODE) {
      throw new SafeZipError("ZIP_SYMLINK_FORBIDDEN");
    }
    if (rawName.endsWith("/")) {
      cursor = nameEnd + extraLength + commentLength;
      continue;
    }

    const cleanPath = safeArchivePath(rawName, config);
    if (seenPaths.has(cleanPath)) {
      throw new SafeZipError("ARCHIVE_DUPLICATE_TARGET");
    }
    seenPaths.add(cleanPath);
    if (uncompressed > config.maxSingleFileBytes) {
      throw new SafeZipError("ARCHIVE_FILE_TOO_LARGE");
    }
    // Both halves of the zip-bomb check: an impossible zero-compressed entry,
    // and a ratio no real text corpus reaches.
    if (compressed === 0 && uncompressed > 0) {
      throw new SafeZipError("ZIP_RATIO_INVALID");
    }
    if (compressed > 0 && uncompressed / compressed > MAX_COMPRESSION_RATIO) {
      throw new SafeZipError("ZIP_RATIO_INVALID");
    }
    expanded += uncompressed;
    if (expanded > config.maxExpandedBytes) {
      throw new SafeZipError("ARCHIVE_EXPANSION_LIMIT");
    }
    entries.push(
      Object.freeze({
        path: cleanPath,
        flags,
        method,
        crc,
        compressed,
        uncompressed,
        localOffset,
      }),
    );
    cursor = nameEnd + extraLength + commentLength;
  }

  return Object.freeze({
    archiveBytes: buffer.length,
    expandedBytes: expanded,
    entryCount: entries.length,
    entries: Object.freeze(entries),
  });
}

// Only called after inspectZip has accepted every entry. maxOutputLength caps
// inflation so a lying central directory cannot exhaust memory.
function readZipEntries(buffer, policy = {}) {
  const info = inspectZip(buffer, policy);
  return info.entries.map((entry) => {
    const start = entry.localOffset;
    if (start + 30 > buffer.length || buffer.readUInt32LE(start) !== LOCAL_SIGNATURE) {
      throw new SafeZipError("ZIP_LOCAL_INVALID");
    }
    const nameLength = buffer.readUInt16LE(start + 26);
    const extraLength = buffer.readUInt16LE(start + 28);
    const dataStart = start + 30 + nameLength + extraLength;
    const dataEnd = dataStart + entry.compressed;
    if (dataEnd > buffer.length) {
      throw new SafeZipError("ZIP_DATA_BOUNDS");
    }
    const compressed = buffer.subarray(dataStart, dataEnd);
    const data =
      entry.method === 0
        ? Buffer.from(compressed)
        : zlib.inflateRawSync(compressed, { maxOutputLength: entry.uncompressed });
    if (data.length !== entry.uncompressed) {
      throw new SafeZipError("ZIP_SIZE_MISMATCH");
    }
    if (crc32(data) !== entry.crc) {
      throw new SafeZipError("ZIP_CRC_MISMATCH");
    }
    return Object.freeze({ path: entry.path, data });
  });
}

module.exports = {
  MAX_COMPRESSION_RATIO,
  SafeZipError,
  crc32,
  inspectZip,
  readZipEntries,
};
