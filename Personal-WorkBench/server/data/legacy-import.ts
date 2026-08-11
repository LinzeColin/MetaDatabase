import { sha256 } from "@/server/data/idempotency";
import { normalizeResourceInput, tenantResources, type TenantResource } from "@/server/data/resources";
import { requireAcceptedSensitiveCloudConsent } from "@/server/security/privacy-consent";

export type LegacyModule =
  | "habits"
  | "todos"
  | "ledger"
  | "food"
  | "exercise"
  | "weight"
  | "schedule"
  | "anniversaries"
  | "diary"
  | "savings"
  | "period";

export type WorkbenchLegacyEnvelope = {
  sourceInstanceId: string;
  sourceSchemaVersion: number;
  exportedAt: string;
  modules: Partial<Record<LegacyModule, readonly unknown[]>>;
  imageManifest: readonly {
    localId: string;
    module: "food" | "diary" | "profile" | "other";
    contentType: string;
    byteSize: number;
    sha256: string;
  }[];
};

export type ImportPreview = {
  payloadSha256: string;
  sourceInstanceId: string;
  counts: Readonly<Record<string, number>>;
  duplicateIds: readonly string[];
  invalidItems: readonly { module: string; index: number; reason: string }[];
  canApply: boolean;
};

type LegacyImportDb = Pick<D1Database, "batch" | "prepare">;
type LegacyImportRow = {
  id: string;
  values: Record<string, string | number | boolean | null>;
};

const SUPPORTED_LEGACY_SCHEMA_VERSION = 1;

export class LegacyImportError extends Error {
  status = 400;
  code = "INVALID_LEGACY_IMPORT";

  constructor(message = "legacy import payload is invalid") {
    super(message);
  }
}

export class LegacyImportConflictError extends Error {
  status = 409;
  code = "LEGACY_IMPORT_CONFLICT";

  constructor(message = "legacy import conflict") {
    super(message);
  }
}

type DbLegacyImportRecord = {
  id: string;
  user_id: string;
  source_instance_id: string;
  source_schema_version: number;
  payload_sha256: string;
  state: "previewed" | "applying" | "completed" | "failed";
  item_counts_json: string;
  error_code: string | null;
};

type LegacyImportMetadata = {
  version: 1;
  sourceInstanceId: string;
  sourceSchemaVersion: number;
  payloadSha256: string;
  preview: ImportPreview;
  expectedCounts: Record<string, number>;
  insertedCounts?: Record<string, number>;
  skippedCounts?: Record<string, number>;
  totalInserted?: number;
  errorCode?: string | null;
};

type LegacyImportResult = {
  importId: string;
  state: "previewed" | "applying" | "completed" | "failed";
  preview: ImportPreview;
  sourceInstanceId: string;
  sourceSchemaVersion: number;
  payloadSha256: string;
  insertedCounts?: Record<string, number>;
  skippedCounts?: Record<string, number>;
  totalInserted?: number;
  replayed?: boolean;
};

const MODULES: LegacyModule[] = [
  "habits",
  "todos",
  "ledger",
  "food",
  "exercise",
  "weight",
  "schedule",
  "anniversaries",
  "diary",
  "savings",
  "period",
];

const SENSITIVE_LEGACY_MODULES: readonly LegacyModule[] = ["ledger", "weight", "diary", "period"];

const LEGACY_MODULE_TO_RESOURCE: Record<LegacyModule, keyof typeof tenantResources> = {
  habits: "habits",
  todos: "todos",
  ledger: "ledger",
  food: "food",
  exercise: "exercise",
  weight: "weights",
  schedule: "schedule",
  anniversaries: "anniversaries",
  diary: "diary",
  savings: "savings-goals",
  period: "periods",
};

const IMAGE_MODULES = new Set(["food", "diary", "profile", "other"]);
const MIME_SET = new Set(["image/png", "image/jpeg", "image/webp", "image/heic"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isPlainString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isValidManifestItem(value: unknown): value is NonNullable<WorkbenchLegacyEnvelope["imageManifest"]>[number] {
  if (!isRecord(value)) return false;
  const manifestModule = value.module;
  return (
    isPlainString(value.localId)
    && typeof value.sha256 === "string"
    && value.sha256.length === 64
    && typeof value.byteSize === "number"
    && Number.isInteger(value.byteSize)
    && value.byteSize > 0
    && isPlainString(value.contentType)
    && MIME_SET.has(value.contentType)
    && isPlainString(manifestModule)
    && IMAGE_MODULES.has(manifestModule)
  );
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (!value || typeof value !== "object") return JSON.stringify(value);

  return `{${Object.keys(value as Record<string, unknown>)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson((value as Record<string, unknown>)[key])}`)
    .join(",")}}`;
}

function parseMetadata(value: string): LegacyImportMetadata | null {
  try {
    const parsed = JSON.parse(value) as LegacyImportMetadata;
    if (!parsed || typeof parsed !== "object" || !parsed.preview || !parsed.sourceInstanceId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function validateLegacyEnvelope(value: unknown): WorkbenchLegacyEnvelope {
  if (!isRecord(value)) throw new LegacyImportError("备份文件格式无效");

  if (typeof value.sourceInstanceId !== "string" || value.sourceInstanceId.length < 8) {
    throw new LegacyImportError("缺少来源实例标识");
  }
  if (!Number.isInteger(value.sourceSchemaVersion) || Number(value.sourceSchemaVersion) < 1) {
    throw new LegacyImportError("数据版本无效");
  }
  if (value.sourceSchemaVersion !== SUPPORTED_LEGACY_SCHEMA_VERSION) {
    throw new LegacyImportError(`不支持的数据版本：${value.sourceSchemaVersion}`);
  }
  if (typeof value.exportedAt !== "string" || value.exportedAt.length < 1) {
    throw new LegacyImportError("导出时间无效");
  }
  if (!isRecord(value.modules)) throw new LegacyImportError("缺少模块数据");
  if (!Array.isArray(value.imageManifest)) throw new LegacyImportError("图片清单无效");

  for (const moduleName of Object.keys(value.modules)) {
    if (!MODULES.includes(moduleName as LegacyModule)) {
      throw new LegacyImportError(`未知模块：${moduleName}`);
    }
    const rows = (value.modules as Record<string, unknown>)[moduleName];
    if (!Array.isArray(rows)) throw new LegacyImportError(`模块 ${moduleName} 不是数组`);
  }
  if (value.imageManifest.some((item) => !isValidManifestItem(item))) {
    throw new LegacyImportError("图片清单项无效");
  }

  return value as WorkbenchLegacyEnvelope;
}

export function legacyImportContainsSensitiveData(envelope: WorkbenchLegacyEnvelope): boolean {
  if (SENSITIVE_LEGACY_MODULES.some((moduleName) => (envelope.modules[moduleName]?.length ?? 0) > 0)) {
    return true;
  }
  return envelope.imageManifest.some((item) => item.module === "diary");
}

/** Blocks any D1 import-state write or data import until sensitive sync is enabled. */
export async function requireLegacyImportConsent(
  db: LegacyImportDb,
  userId: string,
  envelope: WorkbenchLegacyEnvelope,
): Promise<void> {
  if (!legacyImportContainsSensitiveData(envelope)) return;
  await requireAcceptedSensitiveCloudConsent(db, userId);
}

export function buildPreview(envelope: WorkbenchLegacyEnvelope, payloadSha256: string): ImportPreview {
  const duplicateIds: string[] = [];
  const invalidItems: { module: string; index: number; reason: string }[] = [];
  const counts: Record<string, number> = {};
  const seen = new Set<string>();

  for (const moduleName of MODULES) {
    const rows = envelope.modules[moduleName] ?? [];
    counts[moduleName] = rows.length;
    rows.forEach((row, index) => {
      if (!isRecord(row) || typeof row.id !== "string" || row.id.length < 8) {
        invalidItems.push({ module: moduleName, index, reason: "稳定 ID 缺失或无效" });
        return;
      }
      const compound = `${moduleName}:${row.id}`;
      if (seen.has(compound)) duplicateIds.push(compound);
      seen.add(compound);
    });
  }

  return {
    payloadSha256,
    sourceInstanceId: envelope.sourceInstanceId,
    counts,
    duplicateIds,
    invalidItems,
    canApply: duplicateIds.length === 0 && invalidItems.length === 0,
  };
}

function moduleResource(module: LegacyModule): TenantResource {
  const key = LEGACY_MODULE_TO_RESOURCE[module];
  const resource = tenantResources[key];
  if (!resource) throw new LegacyImportError(`不支持的模块映射：${module}`);
  return resource;
}

async function hashEnvelope(envelope: WorkbenchLegacyEnvelope): Promise<string> {
  return sha256(stableJson(envelope));
}

function rowAsRecord(resource: TenantResource, row: unknown): LegacyImportRow {
  if (!isRecord(row)) throw new LegacyImportError("记录格式无效");

  const entry = row as Record<string, unknown>;
  if (typeof entry.id !== "string" || entry.id.length < 8) {
    throw new LegacyImportError("记录 ID 无效");
  }

  const { id, ...record } = row as { id?: unknown };
  const normalized = normalizeResourceInput(resource, record as Record<string, unknown>, "create");
  return { id: String(id), values: normalized };
}

async function upsertLegacyImportState(
  db: LegacyImportDb,
  userId: string,
  sourceInstanceId: string,
  sourceSchemaVersion: number,
  payloadSha256: string,
  state: "previewed" | "applying" | "completed" | "failed",
  metadata: LegacyImportMetadata,
  existingId?: string,
) {
  const importId = existingId ?? crypto.randomUUID();
  const now = Date.now();
  const itemCountsJson = JSON.stringify(metadata);
  await db
    .prepare(
      `INSERT INTO legacy_imports
       (id, user_id, source_instance_id, source_schema_version, payload_sha256, state, item_counts_json, error_code, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
       ON CONFLICT(user_id, source_instance_id, payload_sha256)
       DO UPDATE SET
         source_schema_version = excluded.source_schema_version,
         payload_sha256 = excluded.payload_sha256,
         state = excluded.state,
         item_counts_json = excluded.item_counts_json,
         error_code = excluded.error_code,
         updated_at = excluded.updated_at`,
    )
    .bind(importId, userId, sourceInstanceId, sourceSchemaVersion, payloadSha256, state, itemCountsJson, now, now)
    .run();
  return importId;
}

async function readLegacyImportState(
  db: LegacyImportDb,
  userId: string,
  sourceInstanceId: string,
  payloadSha256: string,
): Promise<DbLegacyImportRecord | null> {
  return db
    .prepare(
      `SELECT id, user_id, source_instance_id, source_schema_version, payload_sha256, state, item_counts_json, error_code
       FROM legacy_imports WHERE user_id = ? AND source_instance_id = ? AND payload_sha256 = ? LIMIT 1`,
    )
    .bind(userId, sourceInstanceId, payloadSha256)
    .first<DbLegacyImportRecord>();
}

async function upsertLegacyImportRows(
  db: LegacyImportDb,
  userId: string,
  envelope: WorkbenchLegacyEnvelope,
  preview: ImportPreview,
): Promise<{
  insertedCounts: Record<string, number>;
  skippedCounts: Record<string, number>;
  totalInserted: number;
}> {
  const insertedCounts: Record<string, number> = {};
  const skippedCounts: Record<string, number> = {};
  const now = Date.now();
  const inserts: Array<{ moduleName: LegacyModule; statement: D1PreparedStatement }> = [];

  for (const moduleName of MODULES) {
    const resource = moduleResource(moduleName);
    const rows = envelope.modules[moduleName] ?? [];
    insertedCounts[moduleName] = 0;
    skippedCounts[moduleName] = 0;

    if (preview.counts[moduleName] !== rows.length) {
      throw new LegacyImportConflictError(`模块 ${moduleName} 的预览计数与实际数据不一致`);
    }

    for (const row of rows) {
      const normalized = rowAsRecord(resource, row);
      const fieldEntries = Object.entries(normalized.values);
      const fieldNames = fieldEntries.map(([field]) => field);
      const insertColumns = [
        "id",
        "user_id",
        ...fieldNames,
        "created_at",
        "updated_at",
      ];

      const insertValues = [
        normalized.id,
        userId,
        ...fieldEntries.map(([, value]) => value),
        now,
        now,
      ];
      const marks = insertColumns.map(() => "?").join(", ");
      inserts.push({
        moduleName,
        statement: db
          .prepare(
            `INSERT OR IGNORE INTO "${resource.table}" (${insertColumns.map((c) => `"${c}"`).join(", ")})
             VALUES (${marks})`,
          )
          .bind(...insertValues),
      });
    }
  }

  // D1 batch is transactional: an interrupted import cannot leave a partial
  // product-data batch behind. Stable record IDs make a retry safe if a
  // completed response was lost after the database committed.
  const results = inserts.length ? await db.batch(inserts.map(({ statement }) => statement)) : [];
  if (results.length !== inserts.length) throw new LegacyImportError("迁移批次结果不完整");

  let totalInserted = 0;
  for (let index = 0; index < inserts.length; index += 1) {
    const moduleName = inserts[index].moduleName;
    const changed = results[index]?.meta?.changes ?? 0;
    if (changed === 1) {
      insertedCounts[moduleName] += 1;
      totalInserted += 1;
    } else {
      skippedCounts[moduleName] += 1;
    }
  }

  return { insertedCounts, skippedCounts, totalInserted };
}

export async function previewLegacyImport(
  db: LegacyImportDb,
  userId: string,
  rawEnvelope: unknown,
): Promise<LegacyImportResult> {
  const envelope = validateLegacyEnvelope(rawEnvelope);
  await requireLegacyImportConsent(db, userId, envelope);
  const payloadSha256 = await hashEnvelope(envelope);
  const preview = buildPreview(envelope, payloadSha256);

  const existing = await readLegacyImportState(db, userId, envelope.sourceInstanceId, payloadSha256);
  if (existing?.state === "completed") {
    const parsed = parseMetadata(existing.item_counts_json);
    return {
      importId: existing.id,
      state: "completed",
      preview: parsed?.preview ?? preview,
      sourceInstanceId: envelope.sourceInstanceId,
      sourceSchemaVersion: envelope.sourceSchemaVersion,
      payloadSha256,
      insertedCounts: parsed?.insertedCounts,
      skippedCounts: parsed?.skippedCounts,
      totalInserted: parsed?.totalInserted,
      replayed: true,
    };
  }

  const metadata: LegacyImportMetadata = {
    version: 1,
    sourceInstanceId: envelope.sourceInstanceId,
    sourceSchemaVersion: envelope.sourceSchemaVersion,
    payloadSha256,
    preview,
    expectedCounts: preview.counts,
    totalInserted: 0,
    errorCode: null,
  };
  const importId = await upsertLegacyImportState(
    db,
    userId,
    envelope.sourceInstanceId,
    envelope.sourceSchemaVersion,
    payloadSha256,
    "previewed",
    metadata,
    existing?.id,
  );

  return {
    importId,
    state: "previewed",
    preview,
    sourceInstanceId: envelope.sourceInstanceId,
    sourceSchemaVersion: envelope.sourceSchemaVersion,
    payloadSha256,
    replayed: false,
  };
}

export async function applyLegacyImport(
  db: LegacyImportDb,
  userId: string,
  rawEnvelope: unknown,
): Promise<LegacyImportResult> {
  const envelope = validateLegacyEnvelope(rawEnvelope);
  await requireLegacyImportConsent(db, userId, envelope);
  const payloadSha256 = await hashEnvelope(envelope);
  const preview = buildPreview(envelope, payloadSha256);

  if (!preview.canApply) {
    throw new LegacyImportConflictError("存在重复ID或无效项，无法应用");
  }

  const existing = await readLegacyImportState(db, userId, envelope.sourceInstanceId, payloadSha256);
  if (existing?.state === "completed") {
    const parsed = parseMetadata(existing.item_counts_json);
    return {
      importId: existing.id,
      state: "completed",
      preview: parsed?.preview ?? preview,
      sourceInstanceId: envelope.sourceInstanceId,
      sourceSchemaVersion: envelope.sourceSchemaVersion,
      payloadSha256,
      replayed: true,
      insertedCounts: parsed?.insertedCounts,
      skippedCounts: parsed?.skippedCounts,
      totalInserted: parsed?.totalInserted,
    };
  }

  const importId = await upsertLegacyImportState(
    db,
    userId,
    envelope.sourceInstanceId,
    envelope.sourceSchemaVersion,
    payloadSha256,
    "applying",
    {
      version: 1,
      sourceInstanceId: envelope.sourceInstanceId,
      sourceSchemaVersion: envelope.sourceSchemaVersion,
      payloadSha256,
      preview,
      expectedCounts: preview.counts,
      totalInserted: 0,
      errorCode: null,
    },
    existing?.id,
  );

  try {
    const { insertedCounts, skippedCounts, totalInserted } = await upsertLegacyImportRows(
      db,
      userId,
      envelope,
      preview,
    );
    const metadata: LegacyImportMetadata = {
      version: 1,
      sourceInstanceId: envelope.sourceInstanceId,
      sourceSchemaVersion: envelope.sourceSchemaVersion,
      payloadSha256,
      preview,
      expectedCounts: preview.counts,
      insertedCounts,
      skippedCounts,
      totalInserted,
      errorCode: null,
    };

    await upsertLegacyImportState(
      db,
      userId,
      envelope.sourceInstanceId,
      envelope.sourceSchemaVersion,
      payloadSha256,
      "completed",
      metadata,
      importId,
    );

    return {
      importId,
      state: "completed",
      preview,
      sourceInstanceId: envelope.sourceInstanceId,
      sourceSchemaVersion: envelope.sourceSchemaVersion,
      payloadSha256,
      replayed: false,
      insertedCounts,
      skippedCounts,
      totalInserted,
    };
  } catch (error) {
    await upsertLegacyImportState(
      db,
      userId,
      envelope.sourceInstanceId,
      envelope.sourceSchemaVersion,
      payloadSha256,
      "failed",
      {
        version: 1,
        sourceInstanceId: envelope.sourceInstanceId,
        sourceSchemaVersion: envelope.sourceSchemaVersion,
        payloadSha256,
        preview,
        expectedCounts: preview.counts,
        errorCode: error instanceof LegacyImportError || error instanceof LegacyImportConflictError ? error.code : "UNKNOWN",
      },
      importId,
    ).catch(() => undefined);

    throw error;
  }
}

export async function getLegacyImportDebugState(
  db: LegacyImportDb,
  userId: string,
  sourceInstanceId: string,
  payloadSha256: string,
) {
  const row = await readLegacyImportState(db, userId, sourceInstanceId, payloadSha256);
  if (!row) return null;
  const parsed = parseMetadata(row.item_counts_json);
  if (!parsed) return null;
  return {
    importId: row.id,
    state: row.state,
    sourceInstanceId: parsed.sourceInstanceId,
    sourceSchemaVersion: parsed.sourceSchemaVersion,
    payloadSha256,
    preview: parsed.preview,
    expectedCounts: parsed.expectedCounts,
    insertedCounts: parsed.insertedCounts,
    skippedCounts: parsed.skippedCounts,
    totalInserted: parsed.totalInserted,
    errorCode: parsed.errorCode,
  };
}
