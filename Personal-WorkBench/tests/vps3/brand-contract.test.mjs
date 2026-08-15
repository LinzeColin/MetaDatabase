import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const layout = await readFile(new URL("../../app/layout.tsx", import.meta.url), "utf8");
const home = await readFile(new URL("../../app/page.tsx", import.meta.url), "utf8");
const packageJson = JSON.parse(await readFile(new URL("../../package.json", import.meta.url), "utf8"));

test("public brand is Personal Workbench while technical compatibility paths remain unchanged", () => {
  assert.equal(packageJson.name, "personal-workbench");
  assert.match(layout, /个人工作台/);
  assert.match(home, /个人工作台/);
  assert.doesNotMatch(layout, /个人日程/);
  assert.doesNotMatch(home, /个人日程/);
  assert.match(home, /\/api\/mydairy|hrefFor/);
});
