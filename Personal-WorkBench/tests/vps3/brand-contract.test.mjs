import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const layout = await readFile(new URL("../../app/layout.tsx", import.meta.url), "utf8");
const home = await readFile(new URL("../../app/page.tsx", import.meta.url), "utf8");
const packageJson = JSON.parse(await readFile(new URL("../../package.json", import.meta.url), "utf8"));
const dockerfile = await readFile(new URL("../../Dockerfile.vps3", import.meta.url), "utf8");
const runtime = await readFile(new URL("../../server/runtime/vps3/postgres-sql.ts", import.meta.url), "utf8");

test("public brand remains Personal Workbench", () => {
  assert.equal(packageJson.name, "personal-workbench");
  assert.match(layout, /个人工作台/);
  assert.match(home, /个人工作台/);
  assert.doesNotMatch(layout, /个人日程/);
  assert.doesNotMatch(home, /个人日程/);
});

test("production build is VPS3 Node plus PostgreSQL, not ChatGPT Sites or Workers", () => {
  assert.equal(packageJson.scripts.build, "next build");
  assert.equal(packageJson.scripts.start, "next start -H 0.0.0.0 -p 3000");
  assert.ok(packageJson.dependencies.pg);
  for (const name of ["vinext", "wrangler", "@cloudflare/vite-plugin", "@cloudflare/workers-types"]) {
    assert.equal(packageJson.dependencies?.[name] || packageJson.devDependencies?.[name], undefined);
  }
  assert.match(dockerfile, /DATABASE_URL/);
  assert.match(runtime, /new Pool/);
});
