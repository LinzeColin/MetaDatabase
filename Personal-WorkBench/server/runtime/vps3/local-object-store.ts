import { createReadStream } from "node:fs";
import { mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

export class ObjectStoreNotReadyError extends Error {
  code = "OBJECT_STORE_NOT_READY";

  constructor() {
    super("Personal Workbench object storage is not configured.");
  }
}

type StoredMetadata = {
  contentType?: string;
  customMetadata?: Record<string, string>;
  uploaded: string;
};

function safeKey(key: string): string {
  const normalized = key.replaceAll("\\", "/").replace(/^\/+/, "");
  if (!normalized || normalized.split("/").some((part) => !part || part === "." || part === "..")) {
    throw new Error("Invalid object key.");
  }
  return normalized;
}

function toBytes(body: ArrayBuffer | ArrayBufferView | Blob | string): Promise<Uint8Array> | Uint8Array {
  if (typeof body === "string") return new TextEncoder().encode(body);
  if (body instanceof Blob) return body.arrayBuffer().then((value) => new Uint8Array(value));
  if (body instanceof ArrayBuffer) return new Uint8Array(body);
  return new Uint8Array(body.buffer, body.byteOffset, body.byteLength);
}

export class LocalObjectBucket implements ObjectBucket {
  private readonly root: string;

  constructor(root: string) {
    const resolved = path.resolve(root);
    if (!resolved) throw new ObjectStoreNotReadyError();
    this.root = resolved;
  }

  private paths(key: string): { objectPath: string; metadataPath: string } {
    const normalized = safeKey(key);
    const objectPath = path.resolve(this.root, normalized);
    if (objectPath !== this.root && !objectPath.startsWith(`${this.root}${path.sep}`)) {
      throw new Error("Object key escapes the configured storage root.");
    }
    return { objectPath, metadataPath: `${objectPath}.pwb-meta.json` };
  }

  private async metadata(metadataPath: string): Promise<StoredMetadata> {
    try {
      return JSON.parse(await readFile(metadataPath, "utf8")) as StoredMetadata;
    } catch {
      return { uploaded: new Date(0).toISOString() };
    }
  }

  async put(
    key: string,
    body: ArrayBuffer | ArrayBufferView | Blob | string,
    options?: { httpMetadata?: { contentType?: string }; customMetadata?: Record<string, string> },
  ): Promise<StoredObject> {
    const { objectPath, metadataPath } = this.paths(key);
    const bytes = await toBytes(body);
    await mkdir(path.dirname(objectPath), { recursive: true });
    const nonce = `${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const tempObject = `${objectPath}.${nonce}.tmp`;
    const tempMetadata = `${metadataPath}.${nonce}.tmp`;
    const uploaded = new Date();
    const metadata: StoredMetadata = {
      contentType: options?.httpMetadata?.contentType,
      customMetadata: options?.customMetadata,
      uploaded: uploaded.toISOString(),
    };
    await writeFile(tempObject, bytes);
    await writeFile(tempMetadata, JSON.stringify(metadata), "utf8");
    await rename(tempObject, objectPath);
    await rename(tempMetadata, metadataPath);
    return {
      key,
      size: bytes.byteLength,
      etag: `${bytes.byteLength}-${uploaded.getTime()}`,
      httpEtag: `"${bytes.byteLength}-${uploaded.getTime()}"`,
      uploaded,
      httpMetadata: { contentType: metadata.contentType },
      customMetadata: metadata.customMetadata,
    };
  }

  async get(key: string): Promise<ObjectBody | null> {
    const head = await this.head(key);
    if (!head) return null;
    const { objectPath } = this.paths(key);
    return {
      ...head,
      body: Readable.toWeb(createReadStream(objectPath)) as ReadableStream<Uint8Array>,
      bodyUsed: false,
    };
  }

  async head(key: string): Promise<StoredObject | null> {
    const { objectPath, metadataPath } = this.paths(key);
    try {
      const [details, metadata] = await Promise.all([stat(objectPath), this.metadata(metadataPath)]);
      const uploaded = Number.isFinite(new Date(metadata.uploaded).getTime())
        ? new Date(metadata.uploaded)
        : details.mtime;
      return {
        key,
        size: details.size,
        etag: `${details.size}-${details.mtimeMs}`,
        httpEtag: `"${details.size}-${details.mtimeMs}"`,
        uploaded,
        httpMetadata: { contentType: metadata.contentType },
        customMetadata: metadata.customMetadata,
        writeHttpMetadata(headers: Headers) {
          if (metadata.contentType) headers.set("content-type", metadata.contentType);
        },
      };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }
  }

  async delete(key: string | string[]): Promise<void> {
    for (const item of Array.isArray(key) ? key : [key]) {
      const { objectPath, metadataPath } = this.paths(item);
      await Promise.all([rm(objectPath, { force: true }), rm(metadataPath, { force: true })]);
    }
  }
}

let runtimeBucket: LocalObjectBucket | null = null;

export function getVps3ObjectStore(): ObjectBucket {
  if (!runtimeBucket) {
    runtimeBucket = new LocalObjectBucket(process.env.OBJECT_STORAGE_PATH?.trim() || "/data/objects");
  }
  return runtimeBucket;
}
