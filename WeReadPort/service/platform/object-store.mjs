import { createHash, createHmac, randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fetchWithPolicy } from "./network.mjs";

export class MemoryObjectStore {
  constructor() { this.objects = new Map(); }
  async put(key, bytes, metadata = {}) { this.objects.set(key, { bytes: Buffer.from(bytes), metadata: { ...metadata } }); return { key, size: Buffer.byteLength(bytes) }; }
  async get(key) { const value = this.objects.get(key); return value ? { bytes: Buffer.from(value.bytes), metadata: { ...value.metadata } } : null; }
  async delete(key) { return this.objects.delete(key); }
  async exists(key) { return this.objects.has(key); }
  async healthCheck(prefix = "_system/readiness") { return activeProbe(this, prefix); }
}

export class FileObjectStore {
  constructor(root) { this.root = path.resolve(root); }
  resolve(key) {
    const normalized = String(key).replaceAll("\\", "/").replace(/^\/+/, "");
    if (!normalized || normalized.split("/").some(part => !part || part === "." || part === "..")) throw new Error("对象键无效。");
    const resolved = path.resolve(this.root, normalized);
    if (resolved !== this.root && !resolved.startsWith(`${this.root}${path.sep}`)) throw new Error("对象键越界。");
    return resolved;
  }
  async put(key, bytes) { const target = this.resolve(key); await mkdir(path.dirname(target), { recursive: true, mode: 0o700 }); await writeFile(target, bytes, { mode: 0o600 }); return { key, size: Buffer.byteLength(bytes) }; }
  async get(key) { try { return { bytes: await readFile(this.resolve(key)), metadata: {} }; } catch (error) { if (error?.code === "ENOENT") return null; throw error; } }
  async delete(key) { await rm(this.resolve(key), { force: true }); return true; }
  async exists(key) { return Boolean(await this.get(key)); }
  async healthCheck(prefix = "_system/readiness") { return activeProbe(this, prefix); }
}

export class R2ObjectStore {
  constructor({ endpoint, bucket, accessKeyId, secretAccessKey, region = "auto", fetchImpl = fetch, timeoutMs = 15_000, attempts = 2, probePrefix = "_system/readiness" }) {
    if (!endpoint || !bucket || !accessKeyId || !secretAccessKey) throw new Error("R2 对象存储配置不完整。");
    this.endpoint = new URL(endpoint);
    this.bucket = bucket;
    this.accessKeyId = accessKeyId;
    this.secretAccessKey = secretAccessKey;
    this.region = region;
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
    this.attempts = attempts;
    this.probePrefix = probePrefix;
  }
  async put(key, bytes, metadata = {}) {
    const body = Buffer.from(bytes);
    const headers = {
      "x-amz-storage-class": "STANDARD",
      ...Object.fromEntries(Object.entries(metadata).map(([name, value]) => [`x-amz-meta-${safeHeader(name)}`, String(value)])),
    };
    const response = await this.request("PUT", key, body, headers);
    if (!response.ok) throw Object.assign(new Error(`R2 写入失败：HTTP ${response.status}`), { code: "R2_WRITE", status: response.status });
    return { key, size: body.length };
  }
  async get(key) {
    const response = await this.request("GET", key);
    if (response.status === 404) return null;
    if (!response.ok) throw Object.assign(new Error(`R2 读取失败：HTTP ${response.status}`), { code: "R2_READ", status: response.status });
    return { bytes: Buffer.from(await response.arrayBuffer()), metadata: {} };
  }
  async delete(key) {
    const response = await this.request("DELETE", key);
    if (!response.ok && response.status !== 404) throw Object.assign(new Error(`R2 删除失败：HTTP ${response.status}`), { code: "R2_DELETE", status: response.status });
    return true;
  }
  async exists(key) {
    const response = await this.request("HEAD", key);
    if (response.status === 404) return false;
    if (!response.ok) throw Object.assign(new Error(`R2 探测失败：HTTP ${response.status}`), { code: "R2_PROBE", status: response.status });
    return true;
  }
  async healthCheck(prefix = this.probePrefix) { return activeProbe(this, prefix); }
  async request(method, key, body = Buffer.alloc(0), extraHeaders = {}) {
    const now = new Date();
    const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
    const dateStamp = amzDate.slice(0, 8);
    const payloadHash = sha256Hex(body);
    const url = new URL(this.endpoint);
    url.pathname = `/${encodeURIComponent(this.bucket)}/${encodeKey(key)}`;
    const headers = { host: url.host, "x-amz-content-sha256": payloadHash, "x-amz-date": amzDate, ...extraHeaders };
    const signedNames = Object.keys(headers).map(name => name.toLowerCase()).sort();
    const normalizedHeaders = Object.fromEntries(Object.entries(headers).map(([name, value]) => [name.toLowerCase(), value]));
    const canonicalHeaders = signedNames.map(name => `${name}:${String(normalizedHeaders[name]).trim()}\n`).join("");
    const signedHeaders = signedNames.join(";");
    const canonicalRequest = [method, url.pathname, "", canonicalHeaders, signedHeaders, payloadHash].join("\n");
    const scope = `${dateStamp}/${this.region}/s3/aws4_request`;
    const stringToSign = ["AWS4-HMAC-SHA256", amzDate, scope, sha256Hex(canonicalRequest)].join("\n");
    const signingKey = hmac(hmac(hmac(hmac(Buffer.from(`AWS4${this.secretAccessKey}`), dateStamp), this.region), "s3"), "aws4_request");
    const signature = createHmac("sha256", signingKey).update(stringToSign).digest("hex");
    normalizedHeaders.Authorization = `AWS4-HMAC-SHA256 Credential=${this.accessKeyId}/${scope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;
    return fetchWithPolicy(this.fetchImpl, url, {
      method,
      headers: normalizedHeaders,
      body: ["GET", "HEAD"].includes(method) ? undefined : body,
      redirect: "manual",
    }, { timeoutMs: this.timeoutMs, attempts: this.attempts, retry: true });
  }
}

export function createObjectStore(config, options = {}) {
  if (config.objectStoreMode === "memory") return new MemoryObjectStore();
  if (config.objectStoreMode === "file") {
    if (config.production) throw new Error("生产环境不得把用户笔记长期存储在本机文件系统。");
    return new FileObjectStore(config.fileObjectRoot);
  }
  if (config.objectStoreMode === "r2") return new R2ObjectStore({
    ...config.r2,
    fetchImpl: options.fetchImpl,
    timeoutMs: config.upstreamTimeoutMs,
    attempts: config.upstreamRetryAttempts,
    probePrefix: config.objectHealthProbePrefix,
  });
  throw new Error(`未知对象存储模式：${config.objectStoreMode}`);
}

async function activeProbe(store, prefix) {
  const key = `${String(prefix || "_system/readiness").replace(/\/+$/, "")}/${randomUUID()}.probe`;
  const expected = Buffer.from(`weread-port-readiness:${randomUUID()}`, "utf8");
  try {
    await store.put(key, expected, { purpose: "readiness", version: "v0.0.0.1.9" });
    const read = await store.get(key);
    const ok = Boolean(read && Buffer.compare(read.bytes, expected) === 0);
    return { ok, mode: store.constructor.name, writeReadDelete: ok };
  } finally {
    await store.delete(key).catch(() => undefined);
  }
}

function encodeKey(key) { return String(key).split("/").map(part => encodeURIComponent(part)).join("/"); }
function sha256Hex(value) { return createHash("sha256").update(value).digest("hex"); }
function hmac(key, value) { return createHmac("sha256", key).update(value).digest(); }
function safeHeader(value) { return String(value).toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 40); }
