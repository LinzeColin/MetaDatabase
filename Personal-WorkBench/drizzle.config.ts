import { defineConfig } from "drizzle-kit";

export default defineConfig({
  out: "./drizzle",
  schema: "./db/schema.ts",
  dialect: "sqlite",
  dbCredentials: {
    url: process.env.RUNTIME_DB_PATH || "./.runtime/personal-workbench.sqlite3",
  },
});
