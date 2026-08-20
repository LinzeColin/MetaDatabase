import { env } from "@/server/runtime/vps3/env";
import { drizzle } from "drizzle-orm/d1";
import { authSchema } from "./schema";

export function getDb() {
  if (!env.DB) {
    throw new Error(
      "PostgreSQL is unavailable. Set DATABASE_URL in the VPS3/Coolify runtime before using the database."
    );
  }

  return drizzle(env.DB, { schema: authSchema });
}
