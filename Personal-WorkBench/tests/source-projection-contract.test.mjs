import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

test("source projection contract deterministically preserves the frozen project tree", () => {
  const contract = JSON.parse(readFileSync(resolve(ROOT, "SOURCE_PROJECTION_CONTRACT.json"), "utf8"));
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
  assert.equal(report.source.project_tree, contract.source.project_tree);
  assert.equal(report.content_projection.tree, report.source.project_tree);
  assert.equal(report.content_projection.commit, contract.projection.content_projection.commit);
  assert.equal(report.content_projection.parent, null);
  assert.equal(report.source_channel.tree, report.source.project_tree);
  assert.equal(report.source_channel.commit, contract.projection.source_channel.commit);
  assert.equal(report.source_channel.parent, contract.projection.source_channel.parent);
  assert.equal(report.source_channel.post_push_source_readback_required, true);
});
