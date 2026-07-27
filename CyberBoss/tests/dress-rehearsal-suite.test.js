"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const projectRoot = path.resolve(__dirname, "..");
const suite = path.join(projectRoot, "app/scripts/dress-rehearsal-suite.js");

function run(...args) {
  return spawnSync("node", [suite, ...args], {
    cwd: projectRoot,
    encoding: "utf8",
  });
}

test("local dress rehearsal CLI has a sealed local receipt", () => {
  const result = run("rehearse", "--mode=local");

  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /DRESS_REHEARSAL=PASS/);
  assert.match(result.stdout, /"status":"passed"/);
  assert.match(result.stdout, /"decision":"rehearsal_complete_external_activation_pending"/);
  assert.match(result.stdout, /"candidate_installation":"activation_pending"/);
  assert.match(result.stdout, /"network_or_provider_operations":0/);
});

test("activation plan is inspectable but cannot activate any external system", () => {
  const plan = run("rehearse", "--mode=activation-plan");

  assert.equal(plan.status, 0, plan.stdout + plan.stderr);
  assert.match(plan.stdout, /DRESS_REHEARSAL=PASS/);
  assert.match(plan.stdout, /"real_execution":"activation_pending"/);

  for (const mode of ["activate", "canary-live", "rollback-live", "promote"]) {
    const blocked = run("rehearse", "--mode=" + mode);
    assert.equal(blocked.status, 2);
    assert.match(blocked.stderr, /DRESS_REHEARSAL_EXTERNAL_EXECUTION_DISABLED/);
  }
});
