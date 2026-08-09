/**
 * Performs a deliberately data-free runtime check of the declared storage
 * bindings. It never selects from product tables and never reads, lists,
 * writes, or deletes an R2 object.
 */
export type StorageBindingEnv = {
  DB: Pick<D1Database, "prepare">;
  FILES: Pick<R2Bucket, "head">;
};

export type StorageBindingHealth = {
  d1: "available";
  r2: "available";
};

export async function probeStorageBindings(env: StorageBindingEnv): Promise<StorageBindingHealth> {
  // A constant query proves the runtime D1 binding without accessing a table.
  await env.DB.prepare("SELECT 1 AS storage_binding_probe").first();

  // A fresh internal key makes collision with an application object infeasible.
  // The metadata result is intentionally discarded.
  await env.FILES.head(`__mydairy_binding_probe__/${crypto.randomUUID()}`);

  return { d1: "available", r2: "available" };
}
