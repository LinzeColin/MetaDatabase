"use strict";

// CB-830 acceptance: AC-036 (release rollback), AC-039 (real dual-user WeChat),
// AC-040 (recoverable install), AC-050 (Owner single-command lifecycle).
//
// AC-039 and the real halves of AC-040 need credentials and a target host that
// are not in scope here. Those are marked activation_pending in the evidence
// and are never simulated: no test below pretends a real WeChat sender or a
// real OVH install happened. What is proved here is everything the contract
// can be held to without them — the canary oracle, the rollback pointer, the
// operator dispatcher's guards and the lifecycle vocabulary.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  DEFAULT_CANARY,
  buildCanaryReceipt,
  evaluateRequestCountCanary,
  resolveReleasePointer,
} = require("../src/services/release/request-count-canary");
const {
  ACTION_TIMEOUT_MS,
  ALLOWED_ACTIONS,
  OperatorDispatchError,
  PASSTHROUGH_ENV,
  SAFE_ENV,
  buildSafeEnvironment,
  loadActionConfig,
  runOperatorAction,
  validateActionConfig,
  validateRootControlledFile,
} = require("../src/services/ops/operator-dispatcher");

const NOW = "2026-07-28T12:00:00.000Z";
const OPS_ROOT = path.join(__dirname, "../../ops");
const ACTION_CONFIG = JSON.parse(
  fs.readFileSync(path.join(OPS_ROOT, "config/operator-actions.json"), "utf8"),
);

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb830-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function healthySample(overrides = {}) {
  return {
    totalRequests: 100,
    errorCount: 1,
    p95Ms: 4_000,
    privacyViolations: 0,
    duplicateSideEffects: 0,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// AC-036 — request-count canary and immediate rollback
// ---------------------------------------------------------------------------

test("AC-036 the canary decides on request count and never on elapsed time", () => {
  const source = fs.readFileSync(
    path.join(__dirname, "../src/services/release/request-count-canary.js"),
    "utf8",
  );
  // Call forms, not prose: the file's own comments talk about elapsed time in
  // order to say it is not used.
  for (const marker of [
    "setTimeout(", "setInterval(", "Date.now(", "sleep(", "hrtime(", "performance.now(",
    "elapsedMs", "durationMs", "windowMs", "waitMs",
  ]) {
    assert.ok(!source.includes(marker), `the oracle does not consult ${marker}`);
  }
  assert.ok(!source.includes("require("), "the oracle imports nothing");
  // The only clock use is stamping the receipt, never gating the decision.
  assert.equal(source.split("new Date(").length - 1, 1);
  assert.ok(source.indexOf("new Date(") > source.indexOf("function buildCanaryReceipt"));

  const early = evaluateRequestCountCanary(healthySample({ totalRequests: 5 }));
  assert.equal(early.decision, "continue_by_request_count");
  assert.equal(early.remainingRequests, DEFAULT_CANARY.minRequests - 5);
  // Waiting longer changes nothing; only more requests do.
  assert.deepEqual(
    evaluateRequestCountCanary(healthySample({ totalRequests: 5 })),
    early,
  );
});

test("AC-036 a healthy sample promotes and an unhealthy one rolls back at once", () => {
  const promote = evaluateRequestCountCanary(healthySample());
  assert.equal(promote.decision, "promote");
  assert.equal(promote.reasonCode, "CANARY_PASS");
  assert.equal(promote.observedRequests, 100);

  const cases = [
    [{ errorCount: 10 }, "ERROR_RATIO_EXCEEDED"],
    [{ p95Ms: DEFAULT_CANARY.maxP95Ms + 1 }, "LATENCY_EXCEEDED"],
    [{ privacyViolations: 1 }, "PRIVACY_VIOLATION"],
    [{ duplicateSideEffects: 1 }, "DUPLICATE_SIDE_EFFECT"],
    [{ errorCount: 101 }, "CANARY_MEASUREMENT_INCONSISTENT"],
  ];
  for (const [overrides, reasonCode] of cases) {
    const decision = evaluateRequestCountCanary(healthySample(overrides));
    assert.equal(decision.decision, "rollback", reasonCode);
    assert.equal(decision.reasonCode, reasonCode);
  }
});

test("AC-036 one privacy violation outweighs every good number", () => {
  // A perfect sample except for a single privacy violation still rolls back:
  // privacy is not a rate to be tolerated.
  const decision = evaluateRequestCountCanary(
    healthySample({ totalRequests: 10_000, errorCount: 0, p95Ms: 100, privacyViolations: 1 }),
  );
  assert.equal(decision.decision, "rollback");
  assert.equal(decision.reasonCode, "PRIVACY_VIOLATION");
  // And it outranks the insufficient-request hold, so a violation seen early
  // is acted on rather than waited out.
  const early = evaluateRequestCountCanary(
    healthySample({ totalRequests: 1, privacyViolations: 1 }),
  );
  assert.equal(early.decision, "rollback");
  assert.equal(early.reasonCode, "PRIVACY_VIOLATION");
});

test("AC-036 an unmeasured canary rolls back rather than passing", () => {
  for (const field of ["totalRequests", "errorCount", "p95Ms"]) {
    const sample = healthySample();
    delete sample[field];
    const decision = evaluateRequestCountCanary(sample);
    assert.equal(decision.decision, "rollback", `${field} unmeasured`);
    assert.equal(decision.reasonCode, "CANARY_MEASUREMENT_INVALID");
    assert.deepEqual(decision.missing, [field]);
  }
  assert.equal(evaluateRequestCountCanary(null).decision, "rollback");
  assert.equal(
    evaluateRequestCountCanary(healthySample({ privacyViolations: "many" })).reasonCode,
    "CANARY_MEASUREMENT_INVALID",
  );
  assert.equal(
    evaluateRequestCountCanary(healthySample(), { minRequests: -1 }).reasonCode,
    "CANARY_THRESHOLD_INVALID",
  );
});

test("AC-036 rollback names the exact previous release, not a relative step", () => {
  const rollback = evaluateRequestCountCanary(healthySample({ privacyViolations: 1 }));
  const pointer = resolveReleasePointer({
    decision: rollback,
    releaseId: "release-candidate",
    previousReleaseId: "release-known-good",
  });
  assert.deepEqual(pointer, {
    action: "rollback",
    pointTo: "release-known-good",
    stopCandidate: true,
    modelCalls: 0,
  });
  // Rolling back twice cannot walk further back: the target is named, not
  // computed from the current pointer.
  assert.equal(
    resolveReleasePointer({
      decision: rollback,
      releaseId: "release-candidate",
      previousReleaseId: "release-known-good",
    }).pointTo,
    "release-known-good",
  );
  assert.throws(
    () => resolveReleasePointer({ decision: rollback, releaseId: "candidate" }),
    (error) => error.code === "ROLLBACK_TARGET_MISSING",
  );
  const promote = resolveReleasePointer({
    decision: evaluateRequestCountCanary(healthySample()),
    releaseId: "release-candidate",
    previousReleaseId: "release-known-good",
  });
  assert.equal(promote.action, "promote");
  assert.equal(promote.pointTo, "release-candidate");
  assert.equal(
    resolveReleasePointer({
      decision: evaluateRequestCountCanary(healthySample({ totalRequests: 1 })),
      releaseId: "c",
      previousReleaseId: "p",
    }).action,
    "hold",
  );
});

test("AC-036 the canary receipt carries counts and no identity", () => {
  const sample = healthySample();
  const decision = evaluateRequestCountCanary(sample);
  const receipt = buildCanaryReceipt({
    releaseId: "release-candidate",
    previousReleaseId: "release-known-good",
    sample,
    decision,
    decidedAt: NOW,
  });
  assert.equal(receipt.decision, "promote");
  assert.equal(receipt.timeBasedWait, false);
  assert.equal(receipt.modelCalls, 0);
  assert.deepEqual([...Object.keys(receipt.observed)].sort(), [
    "duplicateSideEffects", "errorCount", "p95Ms", "privacyViolations", "totalRequests",
  ]);
  const serialized = JSON.stringify(receipt);
  for (const marker of ["user", "wxid", "sender", "message", "prompt"]) {
    assert.ok(!serialized.toLowerCase().includes(marker), `${marker} is absent from the receipt`);
  }
});

// ---------------------------------------------------------------------------
// AC-050 — the Owner's single-command lifecycle
// ---------------------------------------------------------------------------

test("AC-050 the nine documented actions are exactly the implemented ones", () => {
  assert.deepEqual(ALLOWED_ACTIONS, [
    "install", "doctor", "start", "stop", "restart",
    "status", "backup", "restore", "rollback",
  ]);
  assert.deepEqual([...Object.keys(ACTION_CONFIG)].sort(), [...ALLOWED_ACTIONS].sort());
  assert.deepEqual([...Object.keys(ACTION_TIMEOUT_MS)].sort(), [...ALLOWED_ACTIONS].sort());
  // A documented action with no command is refused, not skipped.
  const incomplete = { ...ACTION_CONFIG };
  delete incomplete.rollback;
  assert.throws(
    () => validateActionConfig(incomplete),
    (error) => error.code === "OPERATOR_CONFIG_ACTION_MISSING" && error.target === "rollback",
  );
  assert.throws(
    () => validateActionConfig({ ...ACTION_CONFIG, deploy: ["/bin/true"] }),
    (error) => error.code === "OPERATOR_CONFIG_ACTION_NOT_ALLOWED",
  );
});

test("AC-050 every command is an absolute executable with bounded parts", () => {
  const validated = validateActionConfig(ACTION_CONFIG);
  for (const action of ALLOWED_ACTIONS) {
    const command = validated[action];
    assert.ok(path.isAbsolute(command[0]), `${action} runs an absolute executable`);
    assert.ok(command.length <= 12, `${action} has a bounded command`);
    assert.ok(Number.isInteger(ACTION_TIMEOUT_MS[action]), `${action} has a timeout`);
    assert.ok(ACTION_TIMEOUT_MS[action] > 0 && ACTION_TIMEOUT_MS[action] <= 900_000);
  }
  for (const bad of [
    { ...ACTION_CONFIG, start: ["systemctl", "start", "x"] },
    { ...ACTION_CONFIG, start: [] },
    { ...ACTION_CONFIG, start: ["/usr/bin/systemctl", "start; rm -rf /\n"] },
    { ...ACTION_CONFIG, start: ["/usr/bin/systemctl", 42] },
    { ...ACTION_CONFIG, start: ["/usr/bin/systemctl", ...Array(12).fill("x")] },
  ]) {
    assert.throws(() => validateActionConfig(bad), OperatorDispatchError);
  }
});

test("AC-050 the operator's word never reaches a shell", (t) => {
  const calls = [];
  const runner = (executable, args, options) => {
    calls.push({ executable, args, options });
    return { status: 0 };
  };
  const result = runOperatorAction({
    action: "backup",
    config: ACTION_CONFIG,
    runner,
    environment: process.env,
  });
  assert.equal(result.ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.shell, false);
  assert.equal(calls[0].executable, ACTION_CONFIG.backup[0]);
  assert.equal(calls[0].options.timeout, ACTION_TIMEOUT_MS.backup);
  assert.equal(calls[0].options.killSignal, "SIGTERM");
  // An action outside the allowlist never reaches the runner at all.
  for (const action of ["deploy", "shell", "backup; rm -rf /", "", null, undefined]) {
    assert.throws(
      () => runOperatorAction({ action, config: ACTION_CONFIG, runner }),
      (error) => error.code === "OPERATOR_ACTION_NOT_ALLOWED",
      `${action} must be refused`,
    );
  }
  assert.equal(calls.length, 1, "no refused action reached the runner");
});

test("AC-050 the child environment is sanitized, not inherited", () => {
  const hostile = {
    PATH: "/tmp/evil:/usr/bin",
    LD_PRELOAD: "/tmp/evil.so",
    NODE_OPTIONS: "--require /tmp/evil.js",
    HOME: "/tmp/evil",
    CYBERBOSS_RELEASE_ID: "release-candidate",
    CYBERBOSS_DATA_ROOT: "/var/lib/cyberboss",
  };
  const environment = buildSafeEnvironment(hostile);
  assert.equal(environment.PATH, SAFE_ENV.PATH, "PATH is the fixed safe value");
  assert.equal(environment.LD_PRELOAD, undefined);
  assert.equal(environment.NODE_OPTIONS, undefined);
  assert.equal(environment.HOME, undefined);
  assert.equal(environment.CYBERBOSS_RELEASE_ID, "release-candidate");
  assert.deepEqual(
    [...Object.keys(environment)].sort(),
    ["CYBERBOSS_DATA_ROOT", "CYBERBOSS_RELEASE_ID", "LANG", "LC_ALL", "PATH"],
  );
  // A pass-through variable carrying a control character is dropped rather
  // than sanitized in place.
  const dirty = buildSafeEnvironment({ CYBERBOSS_RELEASE_ID: "a\nb" });
  assert.equal(dirty.CYBERBOSS_RELEASE_ID, undefined);
  assert.equal(buildSafeEnvironment({ CYBERBOSS_DATA_ROOT: "x".repeat(501) }).CYBERBOSS_DATA_ROOT, undefined);
  assert.equal(PASSTHROUGH_ENV.length, 3);
});

test("AC-050 a timed-out action is stopped and reported, not left hanging", () => {
  const runner = () => ({ error: Object.assign(new Error("timeout"), { code: "ETIMEDOUT" }) });
  const result = runOperatorAction({ action: "restore", config: ACTION_CONFIG, runner });
  assert.equal(result.ok, false);
  assert.equal(result.timedOut, true);
  assert.equal(result.code, 124);
  assert.match(result.title, /已安全停止/);
  assert.match(result.next, /doctor/);
  assert.ok(!/retry|重试次数/.test(result.next) || result.next.includes("不要反复重试"));
});

test("AC-050 a non-root-owned, symlinked or group-writable config is refused", (t) => {
  const directory = temporaryDirectory(t);
  const configPath = path.join(directory, "operator-actions.json");
  fs.writeFileSync(configPath, JSON.stringify(ACTION_CONFIG), { mode: 0o644 });

  // Owned by this user, not root: refused when root ownership is required.
  assert.throws(
    () => validateRootControlledFile(configPath, { expectedUid: 0 }),
    (error) => error.code === "OPERATOR_FILE_OWNER_INVALID",
  );
  // With the expectation matched to this host's uid the same file passes, so
  // the guard is proved to be checking ownership rather than always failing.
  const ok = validateRootControlledFile(configPath, { expectedUid: process.getuid() });
  assert.equal(ok.uid, process.getuid());
  assert.equal(ok.mode, 0o644);

  // Group- or world-writable is refused even with the right owner.
  fs.chmodSync(configPath, 0o664);
  assert.throws(
    () => validateRootControlledFile(configPath, { expectedUid: process.getuid() }),
    (error) => error.code === "OPERATOR_FILE_WRITABLE_BY_NON_OWNER",
  );
  fs.chmodSync(configPath, 0o644);

  // A symlink is refused for the config, however good its target is.
  const linkPath = path.join(directory, "linked.json");
  fs.symlinkSync(configPath, linkPath);
  assert.throws(
    () => validateRootControlledFile(linkPath, { expectedUid: process.getuid() }),
    (error) => error.code === "OPERATOR_SYMLINK_NOT_ALLOWED",
  );
  // The same symlink is accepted for an executable, where /usr/bin/systemctl
  // is legitimately one, as long as its target is still owned correctly.
  const viaLink = validateRootControlledFile(linkPath, {
    expectedUid: process.getuid(),
    allowSymlink: true,
  });
  assert.equal(viaLink.resolved, fs.realpathSync(configPath));

  assert.throws(
    () => validateRootControlledFile("relative/path.json", { expectedUid: process.getuid() }),
    (error) => error.code === "OPERATOR_ABSOLUTE_PATH_REQUIRED",
  );
  assert.throws(
    () => validateRootControlledFile(directory, { expectedUid: process.getuid() }),
    (error) => error.code === "OPERATOR_FILE_REQUIRED",
  );
});

test("AC-050 loading a malformed config refuses rather than running anything", (t) => {
  const directory = temporaryDirectory(t);
  const configPath = path.join(directory, "operator-actions.json");
  fs.writeFileSync(configPath, "{not json", { mode: 0o644 });
  assert.throws(
    () => loadActionConfig(configPath, { expectedUid: process.getuid(), verifyExecutables: false }),
    (error) => error.code === "OPERATOR_CONFIG_NOT_JSON",
  );
  fs.writeFileSync(configPath, JSON.stringify({ start: ["/bin/true"] }), { mode: 0o644 });
  assert.throws(
    () => loadActionConfig(configPath, { expectedUid: process.getuid(), verifyExecutables: false }),
    (error) => error.code === "OPERATOR_CONFIG_ACTION_MISSING",
  );
  fs.writeFileSync(configPath, JSON.stringify(ACTION_CONFIG), { mode: 0o644 });
  const config = loadActionConfig(configPath, {
    expectedUid: process.getuid(),
    verifyExecutables: false,
  });
  assert.deepEqual([...Object.keys(config)].sort(), [...ALLOWED_ACTIONS].sort());
});

test("AC-050 the operator surface asks for no systemd, SQLite or cloud knowledge", () => {
  const ctl = fs.readFileSync(path.join(OPS_ROOT, "bin/cyberbossctl"), "utf8");
  for (const action of ALLOWED_ACTIONS) {
    assert.ok(ctl.includes(`cyberbossctl ${action}`), `${action} is documented in the help`);
  }
  // The help names the nine words and tells the operator what to do when
  // something breaks, without asking them to understand the machinery.
  assert.match(ctl, /不需要懂 systemd、SQLite 或云端目录/);
  assert.match(ctl, /不要反复重试/);
  // An unknown word and an extra argument are both refused, so the operator
  // never learns that flags might work.
  assert.ok(ctl.includes("不认识这个命令"));
  assert.ok(ctl.includes("这个命令不需要其它参数"));
});

// ---------------------------------------------------------------------------
// AC-040 — the install and recovery contract (structure here, host activation
// recorded as activation_pending in the evidence)
// ---------------------------------------------------------------------------

test("AC-040 every lifecycle verb in the contract has a command behind it", () => {
  const required = ["install", "start", "stop", "doctor", "backup", "restore", "rollback"];
  for (const verb of required) {
    assert.ok(ALLOWED_ACTIONS.includes(verb), `${verb} is part of the lifecycle`);
    assert.ok(Array.isArray(ACTION_CONFIG[verb]) && ACTION_CONFIG[verb].length > 0);
  }
  // The candidate is installed beside the current release, and the pointer is
  // what moves — so a rollback is a pointer change, not a reinstall.
  assert.ok(ACTION_CONFIG.install[0].startsWith("/opt/cyberboss-cloud/current/"));
  assert.ok(ACTION_CONFIG.rollback[0].startsWith("/opt/cyberboss-cloud/current/"));
});

test("AC-040 the release scripts referenced by the config exist in the repository", () => {
  // The installed paths live on the target host, which is not this machine.
  // What can be checked here is that the repository actually carries the
  // release assembly the install path is built from.
  const project = path.join(__dirname, "../..");
  for (const file of [
    "release/assemble-immutable-release.sh",
    "release/write-release-manifest.js",
    "ops/config/operator-actions.json",
    "ops/bin/cyberbossctl",
  ]) {
    assert.ok(fs.existsSync(path.join(project, file)), `${file} is present`);
  }
  const mode = fs.statSync(path.join(project, "ops/bin/cyberbossctl")).mode & 0o777;
  assert.equal(mode & 0o111, 0o111, "cyberbossctl is executable");
  assert.equal(mode & 0o022, 0, "cyberbossctl is not writable by group or other");
});
