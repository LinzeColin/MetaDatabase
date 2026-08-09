import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_ADDENDUM = join(ROOT, "ACCEPTANCE_SEQUENCE_ADDENDUM.json");
const REQUIRED_SEQUENCE = ["S4-T3A", "S5-T1", "S5-T2", "S5-T3", "S5-T4", "S6-T1", "S6-T2"];
const CYCLE_REQUIREMENTS = ["R-003", "R-009", "R-012", "R-014", "R-015"];
const ORIGIN_BOOTSTRAP_FORBIDDEN_CLAIMS = [
  "public release or public audience",
  "S5-T3 completion or real-auth evidence",
  "rollback completion",
  "final independent acceptance",
];

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sameStrings(left, right) {
  return Array.isArray(left) &&
    Array.isArray(right) &&
    left.length === right.length &&
    left.every((entry, index) => entry === right[index]);
}

function parseCsvRow(line) {
  const values = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const current = line[index];
    if (current === '"') {
      if (quoted && line[index + 1] === '"') {
        value += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (current === "," && !quoted) {
      values.push(value);
      value = "";
    } else {
      value += current;
    }
  }
  invariant(!quoted, "TRACEABILITY_MATRIX.csv contains an unterminated quoted field");
  values.push(value);
  return values;
}

function traceabilityTasks(csv) {
  const [header, ...rows] = csv.trim().split(/\r?\n/);
  const columns = parseCsvRow(header);
  const requirementIndex = columns.indexOf("requirement_id");
  const taskIndex = columns.indexOf("tasks");
  invariant(requirementIndex >= 0 && taskIndex >= 0, "TRACEABILITY_MATRIX.csv is missing requirement_id or tasks");

  return new Map(rows.map((row) => {
    const values = parseCsvRow(row);
    return [values[requirementIndex], values[taskIndex].split("|").filter(Boolean)];
  }));
}

function taskById(taskDag, id) {
  const task = taskDag.tasks?.find((candidate) => candidate?.id === id);
  invariant(task, `TASK_DAG.json is missing ${id}`);
  return task;
}

export function validateAddendumShape(addendum) {
  invariant(addendum?.schema_version === "1.1.0", "Unsupported addendum schema_version");
  invariant(addendum.addendum_id === "PWB-S4-S5-SEQUENCE-001", "Unexpected addendum_id");
  invariant(addendum.status === "OWNER_AUTHORIZED_EXECUTION_ORDER", "Addendum is not an active execution-order record");
  invariant(typeof addendum.purpose === "string" && addendum.purpose.length > 0, "Addendum purpose is missing");
  invariant(Array.isArray(addendum.nonnegotiable_invariants) && addendum.nonnegotiable_invariants.length >= 8, "Nonnegotiable invariants are incomplete");
  invariant(Array.isArray(addendum.sequence) && addendum.sequence.length === REQUIRED_SEQUENCE.length, "Sequence is incomplete");
  invariant(sameStrings(addendum.sequence.map((entry) => entry.id), REQUIRED_SEQUENCE), "Sequence order drifted");
  invariant(
    Array.isArray(addendum.requirement_evidence_plan) &&
      addendum.requirement_evidence_plan.length === 15 &&
      new Set(addendum.requirement_evidence_plan.map((entry) => entry?.requirement_id)).size === 15,
    "Requirement evidence plan must contain each requirement exactly once",
  );
  invariant(addendum.final_independent_acceptance?.task_id === "S6-T1", "Final acceptance must be S6-T1");
  invariant(addendum.final_independent_acceptance?.requirement_count === 15, "Final acceptance must require all fifteen requirements");
  invariant(
    typeof addendum.final_independent_acceptance?.failure_rule === "string" &&
      ["UNKNOWN", "NOT_RUN", "WAIVED", "P0", "P1"].every((token) => addendum.final_independent_acceptance.failure_rule.includes(token)),
    "Final acceptance does not fail closed for incomplete or severe evidence",
  );

  const sequence = new Map(addendum.sequence.map((entry) => [entry.id, entry]));
  invariant(sameStrings(sequence.get("S4-T3A")?.deps, ["S4-T1", "S4-T2"]), "S4-T3A dependencies drifted");
  invariant(sameStrings(sequence.get("S5-T1")?.deps, ["S4-T3A"]), "S5-T1 must follow readiness, not final acceptance");
  invariant(sequence.get("S5-T1")?.audience === "private", "S5-T1 must remain private");
  invariant(sameStrings(sequence.get("S5-T2")?.deps, ["S5-T1"]), "S5-T2 dependencies drifted");
  invariant(sameStrings(sequence.get("S5-T3")?.deps, ["S5-T2"]), "S5-T3 dependencies drifted");
  invariant(sequence.get("S5-T3")?.audience === "controlled_private", "S5-T3 must not expose a public audience");
  invariant(sameStrings(sequence.get("S5-T4")?.deps, ["S5-T3"]), "S5-T4 dependencies drifted");
  invariant(sameStrings(sequence.get("S6-T1")?.deps, ["S5-T4"]), "S6-T1 must follow all real-evidence phases");
  invariant(sameStrings(sequence.get("S6-T2")?.deps, ["S6-T1"]), "Public release must follow final acceptance");
  invariant(sequence.get("S6-T2")?.audience === "public", "Only S6-T2 may expose a public audience");

  const originBootstrap = addendum.origin_bootstrap;
  invariant(originBootstrap?.id === "S5-T2-ORIGIN-BOOTSTRAP-001", "Origin bootstrap identity is missing");
  invariant(originBootstrap?.phase === "S5-T2", "Origin bootstrap must stay in S5-T2");
  invariant(originBootstrap?.status === "OWNER_AUTHORIZED_PRIVATE_ORIGIN_ALLOCATION", "Origin bootstrap is not owner-authorized");
  invariant(originBootstrap?.audience === "controlled_private", "Origin bootstrap must remain controlled-private");
  invariant(Array.isArray(originBootstrap?.preconditions) && originBootstrap.preconditions.length >= 5, "Origin bootstrap preconditions are incomplete");
  invariant(Array.isArray(originBootstrap?.after_allocation) && originBootstrap.after_allocation.some((entry) => entry.includes("S5-T3 remains unavailable")), "Origin bootstrap must return to S5-T2");
  invariant(
    Array.isArray(originBootstrap?.must_not_claim) &&
      ORIGIN_BOOTSTRAP_FORBIDDEN_CLAIMS.every((claim) => originBootstrap.must_not_claim.includes(claim)),
    "Origin bootstrap weakened a final-release boundary",
  );
}

export async function validateAcceptanceSequence({ taskpackRoot, addendumPath = DEFAULT_ADDENDUM }) {
  invariant(taskpackRoot, "TASKPACK_ROOT is required; the validator never guesses a taskpack location");
  const resolvedTaskpack = resolve(taskpackRoot);
  const resolvedAddendum = resolve(addendumPath);
  const addendum = JSON.parse(await readFile(resolvedAddendum, "utf8"));
  validateAddendumShape(addendum);

  const sourceFiles = new Map(addendum.source_taskpack?.frozen_files?.map((entry) => [entry.path, entry]));
  invariant(sourceFiles.size === 5, "Frozen source file binding is incomplete");
  for (const [relativePath, binding] of sourceFiles) {
    invariant(typeof binding.sha256 === "string" && /^[a-f0-9]{64}$/.test(binding.sha256), `Invalid SHA-256 binding for ${relativePath}`);
    const actual = sha256(await readFile(join(resolvedTaskpack, relativePath)));
    invariant(actual === binding.sha256, `Frozen taskpack drift: ${relativePath}`);
  }

  const [acceptance, oracles, taskDag, traceability, ownerApproval] = await Promise.all([
    readFile(join(resolvedTaskpack, "07_acceptance", "ACCEPTANCE_CONTRACT.json"), "utf8").then(JSON.parse),
    readFile(join(resolvedTaskpack, "07_acceptance", "ORACLES.json"), "utf8").then(JSON.parse),
    readFile(join(resolvedTaskpack, "06_tasks", "TASK_DAG.json"), "utf8").then(JSON.parse),
    readFile(join(resolvedTaskpack, "07_acceptance", "TRACEABILITY_MATRIX.csv"), "utf8"),
    readFile(join(resolvedTaskpack, "OWNER_APPROVAL.json"), "utf8").then(JSON.parse),
  ]);

  invariant(acceptance?.frozen === true && taskDag?.frozen === true, "Taskpack is not frozen");
  invariant(acceptance.product_version === addendum.source_taskpack.product_version, "Product version drifted");
  invariant(taskDag.taskpack_version === addendum.source_taskpack.taskpack_version, "Taskpack version drifted");
  invariant(ownerApproval?.owner_decision === "APPROVED", "Frozen owner approval is not APPROVED");
  invariant(ownerApproval?.production_side_effect_authorization === true, "Frozen owner approval does not permit controlled production-side effects");
  invariant(ownerApproval?.taskpack_version === taskDag.taskpack_version, "Owner approval taskpack version drifted");
  const s4t3 = taskById(taskDag, "S4-T3");
  const s5t1 = taskById(taskDag, "S5-T1");
  invariant(s4t3.threshold?.includes("15/15") && s4t3.threshold?.includes("UNKNOWN/NOT_RUN/WAIVED"), "Original S4-T3 strict threshold drifted");
  invariant(s5t1.deps?.includes("S4-T3"), "Original S5-T1 dependency drifted");

  const requirements = acceptance.requirements;
  invariant(Array.isArray(requirements) && requirements.length === 15, "Frozen acceptance contract must contain fifteen requirements");
  const expectedIds = requirements.map((requirement) => requirement.id);
  const plans = new Map(addendum.requirement_evidence_plan.map((entry) => [entry.requirement_id, entry]));
  invariant(plans.size === requirements.length, "Requirement evidence plan must contain each requirement exactly once");
  const trace = traceabilityTasks(traceability);

  for (const requirement of requirements) {
    const plan = plans.get(requirement.id);
    invariant(plan, `Missing addendum plan for ${requirement.id}`);
    invariant(plan.frozen_oracle === requirement.oracle && typeof oracles[requirement.oracle] === "string", `Oracle drift for ${requirement.id}`);
    invariant(sameStrings(plan.source_tasks, trace.get(requirement.id)), `Traceability task drift for ${requirement.id}`);
    invariant(REQUIRED_SEQUENCE.includes(plan.earliest_real_candidate_phase), `Invalid candidate phase for ${requirement.id}`);
    invariant(plan.final_acceptance_phase === "S6-T1", `Final acceptance drift for ${requirement.id}`);
  }

  for (const requirementId of CYCLE_REQUIREMENTS) {
    const plan = plans.get(requirementId);
    invariant(plan && plan.source_tasks.some((taskId) => taskId.startsWith("S5-T")), `Cycle evidence was not recorded for ${requirementId}`);
  }

  return {
    status: "PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY",
    verdict: "NOT_PRODUCT_ACCEPTANCE",
    addendum_id: addendum.addendum_id,
    source_taskpack_version: taskDag.taskpack_version,
    requirement_count: expectedIds.length,
    requirement_ids: expectedIds,
    final_acceptance_phase: addendum.final_independent_acceptance.task_id,
    public_release_phase: "S6-T2",
  };
}

function cliOptions(argv) {
  const options = { taskpackRoot: process.env.TASKPACK_ROOT, addendumPath: DEFAULT_ADDENDUM };
  for (let index = 0; index < argv.length; index += 1) {
    const option = argv[index];
    if (option === "--taskpack") {
      options.taskpackRoot = argv[index + 1];
      index += 1;
    } else if (option === "--addendum") {
      options.addendumPath = argv[index + 1];
      index += 1;
    } else if (option === "--help") {
      options.help = true;
    } else {
      throw new Error(`Unknown option: ${option}`);
    }
  }
  return options;
}

export async function main(argv = process.argv.slice(2)) {
  try {
    const options = cliOptions(argv);
    if (options.help) {
      console.log("Usage: TASKPACK_ROOT=/path/to/taskpack node scripts/validate-acceptance-sequence-addendum.mjs");
      return null;
    }
    const report = await validateAcceptanceSequence(options);
    console.log(JSON.stringify(report, null, 2));
    return report;
  } catch (error) {
    console.error(`FAIL_SEQUENCE_ADDENDUM_INTEGRITY_ONLY: ${error instanceof Error ? error.message : "unknown error"}`);
    process.exitCode = 1;
    return null;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main();
}
