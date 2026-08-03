import { NotAccessibleError } from "@/server/security/tenant";
import { type TenantResource } from "./resources";

type TenantDb = Pick<D1Database, "prepare">;
type DatabaseRow = Record<string, unknown>;
export type NormalizedResourceValues = Record<string, string | number | boolean | null>;

function columns(resource: TenantResource): string[] {
  return ["id", ...Object.values(resource.fields).map((field) => field.column), "created_at", "updated_at"];
}

function selectColumns(resource: TenantResource): string {
  return columns(resource)
    .map((column) => `"${column}"`)
    .join(", ");
}

export async function listTenantRecords(
  db: TenantDb,
  resource: TenantResource,
  userId: string,
): Promise<DatabaseRow[]> {
  const result = await db
    .prepare(
      `SELECT ${selectColumns(resource)} FROM "${resource.table}"
       WHERE user_id = ? ORDER BY ${resource.orderBy} LIMIT 100`,
    )
    .bind(userId)
    .all<DatabaseRow>();
  return result.results;
}

export async function getTenantRecord(
  db: TenantDb,
  resource: TenantResource,
  userId: string,
  id: string,
): Promise<DatabaseRow | null> {
  return db
    .prepare(
      `SELECT ${selectColumns(resource)} FROM "${resource.table}"
       WHERE id = ? AND user_id = ? LIMIT 1`,
    )
    .bind(id, userId)
    .first<DatabaseRow>();
}

export async function createTenantRecord(
  db: TenantDb,
  resource: TenantResource,
  userId: string,
  id: string,
  values: NormalizedResourceValues,
): Promise<void> {
  const now = Date.now();
  const fieldColumns = Object.keys(values);
  const recordColumns = ["id", "user_id", ...fieldColumns, "created_at", "updated_at"];
  const params = [id, userId, ...fieldColumns.map((column) => values[column]), now, now];
  const marks = recordColumns.map(() => "?").join(", ");

  await db
    .prepare(
      `INSERT INTO "${resource.table}" (${recordColumns.map((column) => `"${column}"`).join(", ")})
       VALUES (${marks})`,
    )
    .bind(...params)
    .run();
}

export async function updateTenantRecord(
  db: TenantDb,
  resource: TenantResource,
  userId: string,
  id: string,
  values: NormalizedResourceValues,
): Promise<void> {
  const fieldColumns = Object.keys(values);
  const assignments = [...fieldColumns.map((column) => `"${column}" = ?`), '"updated_at" = ?'];
  const result = await db
    .prepare(
      `UPDATE "${resource.table}" SET ${assignments.join(", ")}
       WHERE id = ? AND user_id = ?`,
    )
    .bind(...fieldColumns.map((column) => values[column]), Date.now(), id, userId)
    .run();

  if (!result.meta.changes) throw new NotAccessibleError();
}

export async function deleteTenantRecord(
  db: TenantDb,
  resource: TenantResource,
  userId: string,
  id: string,
): Promise<void> {
  const result = await db
    .prepare(`DELETE FROM "${resource.table}" WHERE id = ? AND user_id = ?`)
    .bind(id, userId)
    .run();
  if (!result.meta.changes) throw new NotAccessibleError();
}
