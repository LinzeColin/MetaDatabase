import { NotAccessibleError } from "../security/tenant.ts";
import { requireSensitiveCloudConsent } from "../security/privacy-consent.ts";

export const privateFileModules = ["food", "diary", "profile", "other"] as const;
export type PrivateFileModule = (typeof privateFileModules)[number];

const maxFileBytes = 10 * 1024 * 1024;
const maxImagePixels = 40_000_000;
const supportedMimeTypes = ["image/jpeg", "image/png", "image/webp"] as const;

type FilesEnv = { DB: SqlDatabase; FILES: ObjectBucket };

type FileRow = {
  id: string;
  object_key: string;
  module: PrivateFileModule;
  content_type: string;
  byte_size: number;
};

export class PrivateFileInputError extends Error {
  status = 400;
  code = "INVALID_FILE";

  constructor() {
    super("The uploaded file is invalid.");
  }
}

export function isPrivateFileModule(value: string): value is PrivateFileModule {
  return (privateFileModules as readonly string[]).includes(value);
}

function startsWith(bytes: Uint8Array, signature: number[]): boolean {
  return signature.every((value, index) => bytes[index] === value);
}

export function detectImageMime(bytes: Uint8Array): (typeof supportedMimeTypes)[number] | null {
  if (bytes.length >= 8 && startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) {
    return "image/png";
  }
  if (bytes.length >= 3 && startsWith(bytes, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (
    bytes.length >= 12 &&
    String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" &&
    String.fromCharCode(...bytes.slice(8, 12)) === "WEBP"
  ) {
    return "image/webp";
  }
  return null;
}

function readU32(bytes: Uint8Array, offset: number, littleEndian = false): number {
  if (littleEndian) {
    return bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16) | (bytes[offset + 3] << 24);
  }
  return (bytes[offset] << 24) | (bytes[offset + 1] << 16) | (bytes[offset + 2] << 8) | bytes[offset + 3];
}

function imageDimensions(bytes: Uint8Array, mime: string): { width: number; height: number } | null {
  if (mime === "image/png") {
    if (bytes.length < 24 || String.fromCharCode(...bytes.slice(12, 16)) !== "IHDR") return null;
    return { width: readU32(bytes, 16), height: readU32(bytes, 20) };
  }
  if (mime === "image/jpeg") {
    for (let offset = 2; offset + 9 < bytes.length; ) {
      if (bytes[offset] !== 0xff) {
        offset += 1;
        continue;
      }
      const marker = bytes[offset + 1];
      const length = (bytes[offset + 2] << 8) | bytes[offset + 3];
      if (length < 2) return null;
      if ([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf].includes(marker)) {
        return { width: (bytes[offset + 7] << 8) | bytes[offset + 8], height: (bytes[offset + 5] << 8) | bytes[offset + 6] };
      }
      offset += length + 2;
    }
    return null;
  }
  if (bytes.length >= 30 && String.fromCharCode(...bytes.slice(12, 16)) === "VP8X") {
    const width = 1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16);
    const height = 1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16);
    return { width, height };
  }
  return null;
}

async function sha256Bytes(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function validatePrivateImageUpload(
  declaredContentType: string,
  buffer: ArrayBuffer,
): Promise<{ contentType: (typeof supportedMimeTypes)[number]; byteSize: number; sha256: string; width: number; height: number }> {
  const bytes = new Uint8Array(buffer);
  if (!supportedMimeTypes.includes(declaredContentType as (typeof supportedMimeTypes)[number])) {
    throw new PrivateFileInputError();
  }
  const detectedMime = detectImageMime(bytes);
  const dimensions = detectedMime ? imageDimensions(bytes, detectedMime) : null;
  if (
    bytes.byteLength < 1 ||
    bytes.byteLength > maxFileBytes ||
    detectedMime !== declaredContentType ||
    !dimensions ||
    dimensions.width < 1 ||
    dimensions.height < 1 ||
    dimensions.width * dimensions.height > maxImagePixels
  ) {
    throw new PrivateFileInputError();
  }
  return {
    contentType: declaredContentType as (typeof supportedMimeTypes)[number],
    byteSize: bytes.byteLength,
    sha256: await sha256Bytes(buffer),
    width: dimensions.width,
    height: dimensions.height,
  };
}

export function buildPrivateObjectKey(
  userId: string,
  module: PrivateFileModule,
  objectId: string,
): string {
  if (!/^[A-Za-z0-9_-]{1,160}$/.test(userId) || !/^[A-Za-z0-9_-]{1,160}$/.test(objectId)) {
    throw new PrivateFileInputError();
  }
  return `users/${userId}/${module}/${objectId}`;
}

export async function createPrivateFile(
  env: FilesEnv,
  input: {
    userId: string;
    id: string;
    module: PrivateFileModule;
    buffer: ArrayBuffer;
    validated: { contentType: string; byteSize: number; sha256: string; width: number; height: number };
  },
): Promise<void> {
  await requireSensitiveCloudConsent(env.DB, input.userId, input.module);
  const now = Date.now();
  const objectKey = buildPrivateObjectKey(input.userId, input.module, input.id);
  await env.DB.prepare(
    `INSERT INTO file_objects
      (id, user_id, object_key, module, content_type, byte_size, sha256, width, height, state, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)`,
  )
    .bind(
      input.id,
      input.userId,
      objectKey,
      input.module,
      input.validated.contentType,
      input.validated.byteSize,
      input.validated.sha256,
      input.validated.width,
      input.validated.height,
      now,
      now,
    )
    .run();

  try {
    await env.FILES.put(objectKey, input.buffer, {
      httpMetadata: { contentType: input.validated.contentType },
    });
  } catch (error) {
    await env.DB.prepare("DELETE FROM file_objects WHERE id = ? AND user_id = ?")
      .bind(input.id, input.userId)
      .run()
      .catch(() => undefined);
    throw error;
  }
}

async function ownedFile(env: FilesEnv, userId: string, id: string): Promise<FileRow> {
  const row = await env.DB.prepare(
    `SELECT id, object_key, module, content_type, byte_size FROM file_objects
     WHERE id = ? AND user_id = ? AND state = 'active' LIMIT 1`,
  )
    .bind(id, userId)
    .first<FileRow>();
  if (!row) throw new NotAccessibleError();
  return row;
}

/**
 * Allows a route to deny a sensitive replacement before reading its request
 * body or creating an idempotency row. The object metadata remains tenant
 * scoped and no object body is read here.
 */
export async function requirePrivateFileCloudConsent(env: FilesEnv, userId: string, id: string): Promise<void> {
  const row = await ownedFile(env, userId, id);
  await requireSensitiveCloudConsent(env.DB, userId, row.module);
}

export async function getPrivateFile(env: FilesEnv, userId: string, id: string) {
  const row = await ownedFile(env, userId, id);
  await requireSensitiveCloudConsent(env.DB, userId, row.module);
  const object = await env.FILES.get(row.object_key);
  if (!object) throw new NotAccessibleError();
  return { object, contentType: row.content_type, byteSize: row.byte_size };
}

export async function privateFileExists(env: FilesEnv, userId: string, id: string): Promise<boolean> {
  const row = await env.DB.prepare(
    "SELECT id, module FROM file_objects WHERE id = ? AND user_id = ? AND state = 'active' LIMIT 1",
  )
    .bind(id, userId)
    .first<Pick<FileRow, "id" | "module">>();
  if (row) await requireSensitiveCloudConsent(env.DB, userId, row.module);
  return Boolean(row);
}

export async function replacePrivateFile(
  env: FilesEnv,
  input: {
    userId: string;
    id: string;
    buffer: ArrayBuffer;
    validated: { contentType: string; byteSize: number; sha256: string; width: number; height: number };
  },
): Promise<void> {
  const row = await ownedFile(env, input.userId, input.id);
  await requireSensitiveCloudConsent(env.DB, input.userId, row.module);
  await env.FILES.put(row.object_key, input.buffer, {
    httpMetadata: { contentType: input.validated.contentType },
  });
  await env.DB.prepare(
    `UPDATE file_objects SET content_type = ?, byte_size = ?, sha256 = ?, width = ?, height = ?, updated_at = ?
     WHERE id = ? AND user_id = ? AND state = 'active'`,
  )
    .bind(
      input.validated.contentType,
      input.validated.byteSize,
      input.validated.sha256,
      input.validated.width,
      input.validated.height,
      Date.now(),
      input.id,
      input.userId,
    )
    .run();
}

export async function deletePrivateFile(env: FilesEnv, userId: string, id: string): Promise<void> {
  const row = await ownedFile(env, userId, id);
  // Account and record erasure remain available even after a consent withdrawal.
  await env.DB.prepare(
    `UPDATE file_objects SET state = 'pending_delete', updated_at = ?
     WHERE id = ? AND user_id = ? AND state = 'active'`,
  )
    .bind(Date.now(), id, userId)
    .run();

  try {
    await env.FILES.delete(row.object_key);
    await env.DB.prepare("DELETE FROM file_objects WHERE id = ? AND user_id = ?")
      .bind(id, userId)
      .run();
  } catch (error) {
    await env.DB.prepare(
      `UPDATE file_objects SET state = 'active', updated_at = ?
       WHERE id = ? AND user_id = ? AND state = 'pending_delete'`,
    )
      .bind(Date.now(), id, userId)
      .run()
      .catch(() => undefined);
    throw error;
  }
}
