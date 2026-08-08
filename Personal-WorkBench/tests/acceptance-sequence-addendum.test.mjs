import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { validateAddendumShape } from "../scripts/validate-acceptance-sequence-addendum.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const addendum = JSON.parse(await readFile(resolve(ROOT, "ACCEPTANCE_SEQUENCE_ADDENDUM.json"), "utf8"));

test("acceptance sequence addendum retains a complete strict final gate", () => {
  assert.doesNotThrow(() => validateAddendumShape(addendum));
  assert.deepEqual(
    addendum.requirement_evidence_plan.map((entry) => entry.requirement_id),
    Array.from({ length: 15 }, (_, index) => `R-${String(index + 1).padStart(3, "0")}`),
  );
  assert.ok(addendum.nonnegotiable_invariants.some((entry) => entry.includes("UNKNOWN, NOT_RUN, and WAIVED")));
  assert.ok(addendum.sequence.find((entry) => entry.id === "S5-T1")?.must_not_claim.includes("public deployment"));
  assert.ok(addendum.sequence.find((entry) => entry.id === "S6-T2")?.must_not_claim.includes("GitHub upload before the overall taskpack is complete"));
});

test("addendum shape rejects an attempt to remove a frozen requirement mapping", () => {
  const invalid = structuredClone(addendum);
  invalid.requirement_evidence_plan.pop();
  assert.throws(() => validateAddendumShape(invalid), /Requirement evidence plan must contain each requirement exactly once/);
});

test("addendum shape rejects an early public-audience transition", () => {
  const invalid = structuredClone(addendum);
  invalid.sequence.find((entry) => entry.id === "S5-T3").audience = "public";
  assert.throws(() => validateAddendumShape(invalid), /S5-T3 must not expose a public audience/);
});
