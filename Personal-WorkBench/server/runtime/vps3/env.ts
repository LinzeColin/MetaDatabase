import type { AuthRuntimeEnv } from "@/server/auth/runtime";
import { getVps3Database } from "./sqlite-d1";
import { getVps3ObjectStore } from "./r2-s3";

type Vps3RuntimeEnv = AuthRuntimeEnv & {
  DB: D1Database;
  FILES: R2Bucket;
  APP_TRUSTED_ORIGINS?: string;
};

const values = new Proxy({} as Vps3RuntimeEnv, {
  get(_target, property: string | symbol) {
    if (property === "DB") return getVps3Database();
    if (property === "FILES") return getVps3ObjectStore();
    if (typeof property !== "string") return undefined;
    return process.env[property];
  },
});

export const env = values;
