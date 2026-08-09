import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("source projection contract deterministically preserves the frozen project tree", () => {
  const result = spawnSync(process.execPath, ["scripts/verify-source-projection.mjs"], {
    cwd: ROOT,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });

  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.status, "PASS_SOURCE_PROJECTION_CONTRACT");
  assert.equal(report.product_pass_claimed, false);
  assert.equal(report.remote_action_taken, false);
  assert.equal(report.source.project_tree, "b831d4564fc01352edfa3f5f26020965f3825df4");
  assert.equal(report.projection.tree, report.source.project_tree);
  assert.equal(report.projection.commit, "3eaf351c2381c98b5fc49a3ed1c78d4c38e581b7");
  assert.equal(report.projection.parent, null);
});
