import {
  DeleteObjectCommand,
  GetObjectCommand,
  HeadObjectCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";

type ObjectStoreConfig = {
  endpoint: string | null;
  accountId: string | null;
  accessKeyId: string | null;
  secretAccessKey: string | null;
  bucket: string | null;
  prefix: string;
};

export class ObjectStoreNotReadyError extends Error {
  code = "OBJECT_STORE_NOT_READY";

  constructor() {
    super("Personal Workbench object storage is not configured.");
  }
}

function value(name: string): string | null {
  return process.env[name]?.trim() || null;
}

function normalizePrefix(prefix: string | null): string {
  const trimmed = prefix?.replace(/^\/+|\/+$/g, "") ?? "";
  return trimmed ? `${trimmed}/` : "";
}

function isNotFound(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const status = (error as { $metadata?: { httpStatusCode?: number } }).$metadata?.httpStatusCode;
  const name = (error as { name?: string }).name;
  return status === 404 || name === "NoSuchKey" || name === "NotFound";
}

export function qualifyObjectKey(prefix: string, key: string): string {
  return `${normalizePrefix(prefix)}${key.replace(/^\/+/, "")}`;
}

export class R2S3Bucket {
  private client: S3Client | null = null;
  private readonly config: ObjectStoreConfig;

  constructor(config: ObjectStoreConfig) {
    this.config = config;
  }

  private ready(): { client: S3Client; bucket: string } {
    const endpoint = this.config.endpoint
      || (this.config.accountId ? `https://${this.config.accountId}.r2.cloudflarestorage.com` : null);
    if (!endpoint || !this.config.accessKeyId || !this.config.secretAccessKey || !this.config.bucket) {
      throw new ObjectStoreNotReadyError();
    }
    if (!this.client) {
      this.client = new S3Client({
        endpoint,
        region: "auto",
        credentials: {
          accessKeyId: this.config.accessKeyId,
          secretAccessKey: this.config.secretAccessKey,
        },
      });
    }
    return { client: this.client, bucket: this.config.bucket };
  }

  private key(key: string): string {
    return qualifyObjectKey(this.config.prefix, key);
  }

  async put(
    key: string,
    body: ArrayBuffer | ArrayBufferView | Blob | string,
    options?: { httpMetadata?: { contentType?: string }; customMetadata?: Record<string, string> },
  ) {
    const { client, bucket } = this.ready();
    let bytes: Uint8Array | string;
    if (typeof body === "string") bytes = body;
    else if (body instanceof Blob) bytes = new Uint8Array(await body.arrayBuffer());
    else if (body instanceof ArrayBuffer) bytes = new Uint8Array(body);
    else bytes = new Uint8Array(body.buffer, body.byteOffset, body.byteLength);

    const result = await client.send(new PutObjectCommand({
      Bucket: bucket,
      Key: this.key(key),
      Body: bytes,
      ContentType: options?.httpMetadata?.contentType,
      Metadata: options?.customMetadata,
    }));
    return {
      key,
      size: typeof bytes === "string" ? Buffer.byteLength(bytes) : bytes.byteLength,
      etag: result.ETag?.replaceAll('"', "") ?? "",
      httpEtag: result.ETag ?? "",
      uploaded: new Date(),
    } as unknown as R2Object;
  }

  async get(key: string): Promise<R2ObjectBody | null> {
    const { client, bucket } = this.ready();
    try {
      const result = await client.send(new GetObjectCommand({ Bucket: bucket, Key: this.key(key) }));
      if (!result.Body) return null;
      const body = result.Body.transformToWebStream() as ReadableStream<Uint8Array>;
      return {
        key,
        body,
        size: Number(result.ContentLength ?? 0),
        etag: result.ETag?.replaceAll('"', "") ?? "",
        httpEtag: result.ETag ?? "",
        uploaded: result.LastModified ?? new Date(0),
        httpMetadata: { contentType: result.ContentType },
        customMetadata: result.Metadata,
        bodyUsed: false,
        writeHttpMetadata(headers: Headers) {
          if (result.ContentType) headers.set("content-type", result.ContentType);
        },
      } as unknown as R2ObjectBody;
    } catch (error) {
      if (isNotFound(error)) return null;
      throw error;
    }
  }

  async head(key: string): Promise<R2Object | null> {
    const { client, bucket } = this.ready();
    try {
      const result = await client.send(new HeadObjectCommand({ Bucket: bucket, Key: this.key(key) }));
      return {
        key,
        size: Number(result.ContentLength ?? 0),
        etag: result.ETag?.replaceAll('"', "") ?? "",
        httpEtag: result.ETag ?? "",
        uploaded: result.LastModified ?? new Date(0),
        httpMetadata: { contentType: result.ContentType },
        customMetadata: result.Metadata,
        writeHttpMetadata(headers: Headers) {
          if (result.ContentType) headers.set("content-type", result.ContentType);
        },
      } as unknown as R2Object;
    } catch (error) {
      if (isNotFound(error)) return null;
      throw error;
    }
  }

  async delete(key: string | string[]): Promise<void> {
    const { client, bucket } = this.ready();
    const keys = Array.isArray(key) ? key : [key];
    for (const item of keys) {
      await client.send(new DeleteObjectCommand({ Bucket: bucket, Key: this.key(item) }));
    }
  }
}

let runtimeBucket: R2S3Bucket | null = null;

export function getVps3ObjectStore(): R2Bucket {
  if (!runtimeBucket) {
    runtimeBucket = new R2S3Bucket({
      endpoint: value("R2_ENDPOINT"),
      accountId: value("R2_ACCOUNT_ID"),
      accessKeyId: value("R2_ACCESS_KEY_ID"),
      secretAccessKey: value("R2_SECRET_ACCESS_KEY"),
      bucket: value("R2_BUCKET_NAME"),
      prefix: normalizePrefix(value("R2_OBJECT_PREFIX") || "personal-workbench"),
    });
  }
  return runtimeBucket as unknown as R2Bucket;
}
