import type { AuthRuntimeEnv } from "@/server/auth/runtime";
import { getVps3Database } from "./postgres-sql";
import { getVps3ObjectStore } from "./local-object-store";

type Vps3RuntimeEnv = AuthRuntimeEnv & {
  DB: SqlDatabase;
  FILES: ObjectBucket;
  APP_TRUSTED_ORIGINS?: string;
};

const values = new Proxy({} as Vps3RuntimeEnv, {
  get(_target, property: string | symbol) {
    if (property === "DB") return process.env.DATABASE_URL?.trim() ? getVps3Database() : undefined;
    if (property === "FILES") return getVps3ObjectStore();
    if (typeof property !== "string") return undefined;
    return process.env[property];
  },
});

export const env = values;
