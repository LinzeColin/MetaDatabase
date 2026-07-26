import {
  FIXED_ZIP_DOS_DATE,
  FIXED_ZIP_DOS_TIME,
  MAX_ARCHIVE_BYTES,
  MAX_ARCHIVE_FILES,
  MAX_PREVIOUS_ARCHIVE_BYTES,
} from "./constants.js";
import { WeReadPortError } from "./errors.js";
import { assertSafeArchivePath, decodeUtf8, utf8 } from "./util.js";

const CRC_TABLE = buildCrcTable();
const UINT16_MAX = 0xffff;
const UINT32_MAX = 0xffffffff;

/** @param {Uint8Array} bytes */
export function crc32(bytes) {
  let crc = UINT32_MAX;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ UINT32_MAX) >>> 0;
}

function buildCrcTable() {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let value = n;
    for (let bit = 0; bit < 8; bit += 1) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    table[n] = value >>> 0;
  }
  return table;
}

/** Create a deterministic UTF-8, STORE-only classic ZIP. @param {Array<{path:string,data:string|Uint8Array}>} inputEntries */
export function createDeterministicZip(inputEntries) {
  if (!Array.isArray(inputEntries) || inputEntries.length === 0) throw new WeReadPortError("ARCHIVE", "归档不能为空。");
  if (inputEntries.length > MAX_ARCHIVE_FILES || inputEntries.length >= UINT16_MAX) throw new WeReadPortError("ARCHIVE", "归档文件数超过安全上限。");

  const seen = new Set();
  const entries = inputEntries.map(entry => {
    const path = assertSafeArchivePath(entry.path);
    if (seen.has(path)) throw new WeReadPortError("ARCHIVE", `归档路径重复：${path}`);
    seen.add(path);
    const name = utf8(path);
    const data = typeof entry.data === "string" ? utf8(entry.data) : entry.data;
    if (!(data instanceof Uint8Array)) throw new WeReadPortError("ARCHIVE", `归档内容类型无效：${path}`);
    if (name.byteLength > UINT16_MAX) throw new WeReadPortError("ARCHIVE", `归档路径过长：${path}`);
    if (data.byteLength >= UINT32_MAX) throw new WeReadPortError("ARCHIVE", `归档文件过大：${path}`);
    return { path, name, data, crc: crc32(data) };
  }).sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);

  const payloadSize = entries.reduce((sum, entry) => sum + entry.data.byteLength, 0);
  if (payloadSize > MAX_ARCHIVE_BYTES) throw new WeReadPortError("ARCHIVE", "归档内容超过安全上限。");

  let localOffset = 0;
  const locals = [];
  const centrals = [];
  for (const entry of entries) {
    if (localOffset >= UINT32_MAX) throw new WeReadPortError("ARCHIVE", "归档偏移超过 classic ZIP 上限。");
    const local = new Uint8Array(30 + entry.name.byteLength + entry.data.byteLength);
    const view = new DataView(local.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, 0x0800, true); // UTF-8
    view.setUint16(8, 0, true); // STORE
    view.setUint16(10, FIXED_ZIP_DOS_TIME, true);
    view.setUint16(12, FIXED_ZIP_DOS_DATE, true);
    view.setUint32(14, entry.crc, true);
    view.setUint32(18, entry.data.byteLength, true);
    view.setUint32(22, entry.data.byteLength, true);
    view.setUint16(26, entry.name.byteLength, true);
    view.setUint16(28, 0, true);
    local.set(entry.name, 30);
    local.set(entry.data, 30 + entry.name.byteLength);
    locals.push(local);

    const central = new Uint8Array(46 + entry.name.byteLength);
    const centralView = new DataView(central.buffer);
    centralView.setUint32(0, 0x02014b50, true);
    centralView.setUint16(4, 0x0314, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0x0800, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint16(12, FIXED_ZIP_DOS_TIME, true);
    centralView.setUint16(14, FIXED_ZIP_DOS_DATE, true);
    centralView.setUint32(16, entry.crc, true);
    centralView.setUint32(20, entry.data.byteLength, true);
    centralView.setUint32(24, entry.data.byteLength, true);
    centralView.setUint16(28, entry.name.byteLength, true);
    centralView.setUint16(30, 0, true);
    centralView.setUint16(32, 0, true);
    centralView.setUint16(34, 0, true);
    centralView.setUint16(36, 0, true);
    centralView.setUint32(38, 0, true);
    centralView.setUint32(42, localOffset, true);
    central.set(entry.name, 46);
    centrals.push(central);
    localOffset += local.byteLength;
  }

  const centralSize = centrals.reduce((sum, item) => sum + item.byteLength, 0);
  if (localOffset >= UINT32_MAX || centralSize >= UINT32_MAX) throw new WeReadPortError("ARCHIVE", "归档超过 classic ZIP 上限。");
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(4, 0, true);
  endView.setUint16(6, 0, true);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, localOffset, true);
  endView.setUint16(20, 0, true);

  const result = concatBytes([...locals, ...centrals, end]);
  if (result.byteLength > MAX_ARCHIVE_BYTES) throw new WeReadPortError("ARCHIVE", "最终 ZIP 超过安全上限。");
  return result;
}

/** Read an existing ZIP safely. Supports classic STORE and raw DEFLATE. @param {Uint8Array|ArrayBuffer} input */
export async function readZipEntries(input) {
  const bytes = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (bytes.byteLength > MAX_PREVIOUS_ARCHIVE_BYTES) throw new WeReadPortError("ARCHIVE", "旧导出压缩包 超过安全上限。");
  if (bytes.byteLength < 22) throw new WeReadPortError("ARCHIVE", "压缩包文件过短。");

  const eocd = findEocd(bytes);
  requireRange(bytes, eocd, 22);
  const endView = new DataView(bytes.buffer, bytes.byteOffset + eocd, 22);
  const disk = endView.getUint16(4, true);
  const centralDisk = endView.getUint16(6, true);
  const diskCount = endView.getUint16(8, true);
  const count = endView.getUint16(10, true);
  const centralSize = endView.getUint32(12, true);
  const centralOffset = endView.getUint32(16, true);
  const commentLength = endView.getUint16(20, true);
  if (disk !== 0 || centralDisk !== 0 || diskCount !== count) throw new WeReadPortError("ARCHIVE", "不支持多卷 ZIP。");
  if (count === UINT16_MAX || centralSize === UINT32_MAX || centralOffset === UINT32_MAX) throw new WeReadPortError("ARCHIVE", "不支持 ZIP64。");
  if (count > MAX_ARCHIVE_FILES) throw new WeReadPortError("ARCHIVE", "压缩包文件数超过安全上限。");
  requireRange(bytes, eocd + 22, commentLength);
  if (centralOffset + centralSize > eocd) throw new WeReadPortError("ARCHIVE", "ZIP 中央目录范围无效。");

  const result = new Map();
  let offset = centralOffset;
  let totalUncompressed = 0;
  for (let index = 0; index < count; index += 1) {
    requireRange(bytes, offset, 46);
    const centralView = new DataView(bytes.buffer, bytes.byteOffset + offset, 46);
    if (centralView.getUint32(0, true) !== 0x02014b50) throw new WeReadPortError("ARCHIVE", "ZIP 中央目录签名无效。");

    const flags = centralView.getUint16(8, true);
    const method = centralView.getUint16(10, true);
    const expectedCrc = centralView.getUint32(16, true);
    const compressedSize = centralView.getUint32(20, true);
    const uncompressedSize = centralView.getUint32(24, true);
    const nameLength = centralView.getUint16(28, true);
    const extraLength = centralView.getUint16(30, true);
    const commentLengthEntry = centralView.getUint16(32, true);
    const localOffset = centralView.getUint32(42, true);
    if (flags & 1) throw new WeReadPortError("ARCHIVE", "不支持加密 ZIP。");
    if (compressedSize === UINT32_MAX || uncompressedSize === UINT32_MAX || localOffset === UINT32_MAX) throw new WeReadPortError("ARCHIVE", "不支持 ZIP64 条目。");
    if (![0, 8].includes(method)) throw new WeReadPortError("ARCHIVE", `不支持 ZIP 压缩方法 ${method}。`);
    requireRange(bytes, offset + 46, nameLength + extraLength + commentLengthEntry);
    const centralName = bytes.subarray(offset + 46, offset + 46 + nameLength);
    const path = assertSafeArchivePath(decodeUtf8(centralName));
    if (result.has(path)) throw new WeReadPortError("ARCHIVE", `ZIP 路径重复：${path}`);

    requireRange(bytes, localOffset, 30);
    const localView = new DataView(bytes.buffer, bytes.byteOffset + localOffset, 30);
    if (localView.getUint32(0, true) !== 0x04034b50) throw new WeReadPortError("ARCHIVE", "ZIP 本地文件头无效。");
    const localFlags = localView.getUint16(6, true);
    const localMethod = localView.getUint16(8, true);
    const localNameLength = localView.getUint16(26, true);
    const localExtraLength = localView.getUint16(28, true);
    if (localMethod !== method || localFlags !== flags) throw new WeReadPortError("ARCHIVE", `ZIP 本地头与中央目录不一致：${path}`);
    requireRange(bytes, localOffset + 30, localNameLength + localExtraLength);
    const localName = bytes.subarray(localOffset + 30, localOffset + 30 + localNameLength);
    if (!equalBytes(localName, centralName)) throw new WeReadPortError("ARCHIVE", `压缩包文件名记录不一致：${path}`);
    const dataOffset = localOffset + 30 + localNameLength + localExtraLength;
    requireRange(bytes, dataOffset, compressedSize);
    const compressed = bytes.slice(dataOffset, dataOffset + compressedSize);
    const data = method === 0 ? compressed : await inflateRaw(compressed);
    if (data.byteLength !== uncompressedSize || crc32(data) !== expectedCrc) throw new WeReadPortError("ARCHIVE", `压缩包文件校验失败：${path}`);
    totalUncompressed += data.byteLength;
    if (totalUncompressed > MAX_ARCHIVE_BYTES) throw new WeReadPortError("ARCHIVE", "ZIP 解压后超过安全上限。");
    result.set(path, data);
    offset += 46 + nameLength + extraLength + commentLengthEntry;
  }
  if (offset !== centralOffset + centralSize) throw new WeReadPortError("ARCHIVE", "ZIP 中央目录长度不一致。");
  return result;
}

/** @param {Uint8Array} compressed */
async function inflateRaw(compressed) {
  if (typeof DecompressionStream !== "function") throw new WeReadPortError("ARCHIVE", "当前运行环境无法解压 DEFLATE ZIP；请使用本工具生成的 STORE ZIP。");
  try {
    const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  } catch (error) {
    throw new WeReadPortError("ARCHIVE", "无法解压旧 ZIP。", { cause: error });
  }
}

/** @param {Uint8Array} bytes */
function findEocd(bytes) {
  const min = Math.max(0, bytes.byteLength - 65_557);
  for (let offset = bytes.byteLength - 22; offset >= min; offset -= 1) {
    if (bytes[offset] === 0x50 && bytes[offset + 1] === 0x4b && bytes[offset + 2] === 0x05 && bytes[offset + 3] === 0x06) return offset;
  }
  throw new WeReadPortError("ARCHIVE", "未找到有效 ZIP 结束记录。");
}

/** @param {Uint8Array} bytes @param {number} offset @param {number} length */
function requireRange(bytes, offset, length) {
  if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(length) || offset < 0 || length < 0 || offset + length > bytes.byteLength) {
    throw new WeReadPortError("ARCHIVE", "ZIP 数据越界。");
  }
}

/** @param {Uint8Array} left @param {Uint8Array} right */
function equalBytes(left, right) {
  if (left.byteLength !== right.byteLength) return false;
  for (let index = 0; index < left.byteLength; index += 1) if (left[index] !== right[index]) return false;
  return true;
}

/** @param {Uint8Array[]} arrays */
function concatBytes(arrays) {
  const total = arrays.reduce((sum, array) => sum + array.byteLength, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const array of arrays) {
    out.set(array, offset);
    offset += array.byteLength;
  }
  return out;
}
