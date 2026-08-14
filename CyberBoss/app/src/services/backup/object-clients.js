"use strict";

// R2 与 OCI 的对象客户端。CB-800 的 DualCopyBackupCoordinator 需要两个能
// putObject/getObject 的东西；在此之前那两个位置一直是测试里的假对象，所以
// "双副本备份"从来没有真的往任何地方写过。这个文件是真的那两个。
//
// 两边都不引第三方 SDK：R2 用 S3 兼容接口 + AWS SigV4（用 node:crypto 现算），
// OCI 用预授权请求（PAR，本身就是一个带签名的 URL，不需要再签一次）。少一个
// 依赖就少一条供应链，而 AC-038 正是盯着这件事的。

const crypto = require("node:crypto");

class ObjectClientError extends Error {
  constructor(code, detail = null) {
    super(code);
    this.name = "ObjectClientError";
    this.code = code;
    this.detail = detail;
  }
}

function sha256Hex(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function hmac(key, value) {
  return crypto.createHmac("sha256", key).update(value).digest();
}

// AWS Signature V4。R2 实现的是 S3 兼容接口，区域固定 "auto"。
function signV4({
  method,
  url,
  headers,
  payloadHash,
  accessKeyId,
  secretAccessKey,
  region = "auto",
  service = "s3",
  now,
}) {
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const dateStamp = amzDate.slice(0, 8);
  const canonicalHeaders = Object.keys(headers)
    .map((name) => name.toLowerCase())
    .sort()
    .map((name) => `${name}:${String(headers[headerKey(headers, name)]).trim()}\n`)
    .join("");
  const signedHeaders = Object.keys(headers)
    .map((name) => name.toLowerCase())
    .sort()
    .join(";");
  const canonicalRequest = [
    method,
    url.pathname,
    url.searchParams.toString(),
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");
  const scope = `${dateStamp}/${region}/${service}/aws4_request`;
  const stringToSign = [
    "AWS4-HMAC-SHA256",
    amzDate,
    scope,
    sha256Hex(canonicalRequest),
  ].join("\n");
  const signingKey = hmac(
    hmac(hmac(hmac(`AWS4${secretAccessKey}`, dateStamp), region), service),
    "aws4_request",
  );
  const signature = crypto.createHmac("sha256", signingKey).update(stringToSign).digest("hex");
  return {
    amzDate,
    authorization:
      `AWS4-HMAC-SHA256 Credential=${accessKeyId}/${scope}, `
      + `SignedHeaders=${signedHeaders}, Signature=${signature}`,
  };
}

function headerKey(headers, lowercased) {
  return Object.keys(headers).find((name) => name.toLowerCase() === lowercased);
}

function requireText(value, code) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) {
    throw new ObjectClientError(code);
  }
  return text;
}

// Cloudflare R2。账号 id、bucket、access key、secret 都由 Owner 配置，用户永远
// 碰不到；每个对象都启用版本，返回的版本号是"这份副本确实落地了"的凭据。
class R2ObjectClient {
  constructor({ accountId, bucket, accessKeyId, secretAccessKey, fetchImpl = globalThis.fetch, now = () => new Date() }) {
    this.accountId = requireText(accountId, "R2_ACCOUNT_ID_REQUIRED");
    this.bucket = requireText(bucket, "R2_BUCKET_REQUIRED");
    this.accessKeyId = requireText(accessKeyId, "R2_ACCESS_KEY_ID_REQUIRED");
    this.secretAccessKey = requireText(secretAccessKey, "R2_SECRET_ACCESS_KEY_REQUIRED");
    this.fetchImpl = fetchImpl;
    this.now = now;
  }

  #url(key) {
    return new URL(
      `https://${this.accountId}.r2.cloudflarestorage.com/${this.bucket}/${key
        .split("/")
        .map((segment) => encodeURIComponent(segment))
        .join("/")}`,
    );
  }

  async #send({ method, key, body = null, extraHeaders = {} }) {
    const url = this.#url(key);
    const payload = body === null ? Buffer.alloc(0) : Buffer.from(body);
    const payloadHash = sha256Hex(payload);
    const headers = {
      Host: url.host,
      "x-amz-content-sha256": payloadHash,
      ...extraHeaders,
    };
    const now = this.now();
    const signed = signV4({
      method,
      url,
      headers: { ...headers, "x-amz-date": now.toISOString().replace(/[:-]|\.\d{3}/g, "") },
      payloadHash,
      accessKeyId: this.accessKeyId,
      secretAccessKey: this.secretAccessKey,
      now,
    });
    const response = await this.fetchImpl(url.toString(), {
      method,
      headers: {
        ...headers,
        "x-amz-date": signed.amzDate,
        Authorization: signed.authorization,
      },
      ...(method === "PUT" ? { body: payload } : {}),
    });
    if (!response.ok) {
      throw new ObjectClientError("R2_REQUEST_FAILED", `${method} ${response.status}`);
    }
    return response;
  }

  async putObject({ key, body, metadata = {} }) {
    const response = await this.#send({
      method: "PUT",
      key,
      body,
      extraHeaders: {
        "Content-Type": "application/octet-stream",
        "x-amz-storage-class": "STANDARD",
        // 元数据里只放长度和摘要，绝不放用户标识。
        "x-amz-meta-sha256": String(metadata.sha256 || ""),
        "x-amz-meta-release": String(metadata.releaseId || ""),
      },
    });
    const version = response.headers.get("x-amz-version-id");
    if (!version) {
      // 没有版本号就等于没有可回溯的副本，如实报失败而不是当成功。
      throw new ObjectClientError("R2_VERSION_MISSING", key);
    }
    return { versionId: version };
  }

  async getObject({ key }) {
    const response = await this.#send({ method: "GET", key });
    return Buffer.from(await response.arrayBuffer());
  }
}

// OCI 对象存储，走预授权请求（PAR）。PAR 本身就是一个带签名的 URL，所以这里
// 不需要 OCI 的 API 签名，也不需要在本机保存 OCI 的私钥。
class OciParObjectClient {
  constructor({ parUrl, fetchImpl = globalThis.fetch }) {
    const text = requireText(parUrl, "OCI_PAR_URL_REQUIRED");
    let url;
    try {
      url = new URL(text);
    } catch {
      throw new ObjectClientError("OCI_PAR_URL_INVALID");
    }
    if (url.protocol !== "https:") {
      throw new ObjectClientError("OCI_PAR_MUST_BE_HTTPS");
    }
    // PAR 必须是"目录型"的，末尾带 /，这样才能往里写任意 key。
    this.base = url.toString().endsWith("/") ? url.toString() : `${url.toString()}/`;
    this.fetchImpl = fetchImpl;
  }

  #url(key) {
    return `${this.base}${key.split("/").map((segment) => encodeURIComponent(segment)).join("/")}`;
  }

  async putObject({ key, body, metadata = {} }) {
    const response = await this.fetchImpl(this.#url(key), {
      method: "PUT",
      headers: {
        "Content-Type": "application/octet-stream",
        "opc-meta-sha256": String(metadata.sha256 || ""),
        "opc-meta-release": String(metadata.releaseId || ""),
      },
      body: Buffer.from(body),
    });
    if (!response.ok) {
      throw new ObjectClientError("OCI_REQUEST_FAILED", `PUT ${response.status}`);
    }
    // OCI 用 ETag 作为这一版的标识；协调器只要求"有一个版本标识"。
    const version = response.headers.get("etag") || response.headers.get("opc-content-md5");
    if (!version) {
      throw new ObjectClientError("OCI_VERSION_MISSING", key);
    }
    return { versionId: version.replaceAll('"', "") };
  }

  async getObject({ key }) {
    const response = await this.fetchImpl(this.#url(key), { method: "GET" });
    if (!response.ok) {
      throw new ObjectClientError("OCI_REQUEST_FAILED", `GET ${response.status}`);
    }
    return Buffer.from(await response.arrayBuffer());
  }
}

// 从配置里造出两个客户端。缺哪一边就返回哪一边为 null——上层据此如实报
// activation_pending，而不是拿一个假客户端把"双副本"糊过去。
function createObjectClients(config = {}, { fetchImpl = globalThis.fetch, now } = {}) {
  let r2 = null;
  let oci = null;
  const missing = [];
  if (config.r2AccountId && config.r2Bucket && config.r2AccessKeyId && config.r2SecretAccessKey) {
    r2 = new R2ObjectClient({
      accountId: config.r2AccountId,
      bucket: config.r2Bucket,
      accessKeyId: config.r2AccessKeyId,
      secretAccessKey: config.r2SecretAccessKey,
      fetchImpl,
      ...(now ? { now } : {}),
    });
  } else {
    missing.push("r2");
  }
  if (config.ociParUrl) {
    oci = new OciParObjectClient({ parUrl: config.ociParUrl, fetchImpl });
  } else {
    missing.push("oci");
  }
  return { r2, oci, missing: Object.freeze(missing), ready: missing.length === 0 };
}

module.exports = {
  ObjectClientError,
  OciParObjectClient,
  R2ObjectClient,
  createObjectClients,
  sha256Hex,
  signV4,
};
