"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { WorkspaceRegistry } = require("../src/core/workspace-registry");
const {
  mapCodexMessageToRuntimeEvent,
} = require("../src/adapters/runtime/codex/events");
const {
  RuntimeSpoolDatabase,
} = require("../src/services/db/database-adapter");
const {
  JobScheduler,
} = require("../src/services/jobs/job-scheduler");
const {
  ResourceReadinessGate,
} = require("../src/services/jobs/resource-readiness-gate");

const FIXTURE_KEY = Buffer.from(
  "902ed26a790b2bde3decebb7a36c639dc4e012260f6609df237cafa70f71ba9c",
  "hex",
);
const START = new Date("2026-07-27T01:00:00.000Z");

function fixtureEnvironment(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "cb220-scheduler-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const workspaceBase = path.join(directory, "workspaces");
  const workspaceRoot = path.join(workspaceBase, "cyberboss");
  const outsideRoot = path.join(directory, "outside");
  fs.mkdirSync(workspaceRoot, { recursive: true });
  fs.mkdirSync(outsideRoot, { recursive: true });
  const configPath = path.join(directory, "workspaces.json");
  fs.writeFileSync(
    configPath,
    `${JSON.stringify({
      schema_version: 1,
      default_alias: "cyberboss",
      workspace_base: workspaceBase,
      workspaces: {
        cyberboss: {
          repo: "LinzeColin/MetaDatabase",
          root: workspaceRoot,
          project_subpath: "CyberBoss",
          max_bytes: 4_294_967_296,
          sparse_paths: ["CyberBoss", ".github"],
          root_integration_paths: [".github"],
          root_integration_write: false,
          write_globs: ["CyberBoss/**"],
        },
      },
    })}\n`,
    { mode: 0o600 },
  );
  let nowMs = START.getTime();
  const clock = {
    now: () => new Date(nowMs),
    advance: (milliseconds) => {
      nowMs += milliseconds;
      return new Date(nowMs);
    },
  };
  const database = new RuntimeSpoolDatabase({
    databasePath: path.join(directory, "runtime.db"),
    encryptionKey: Buffer.from(FIXTURE_KEY),
    identityKey: Buffer.from(FIXTURE_KEY),
    now: clock.now,
  });
  const workspaceRegistry = new WorkspaceRegistry({
    configPath,
    workspaceBase,
  });
  return {
    directory,
    workspaceBase,
    workspaceRoot,
    outsideRoot,
    configPath,
    database,
    workspaceRegistry,
    clock,
  };
}

function normalizedPayload(index, text = `fixture ${index}`) {
  return {
    provider: "weixin",
    accountId: "fixture-account",
    workspaceId: "fixture-workspace",
    senderId: "fixture-sender",
    chatId: "fixture-sender",
    messageId: `fixture-${index}`,
    threadKey: "",
    text,
    attachments: [],
    receivedAt: START.toISOString(),
    policyDecision: {
      accepted: true,
      code: "accepted",
      inputBytes: 12,
      maxInputBytes: 32768,
    },
  };
}

function enqueue(database, index, {
  operationClass = "bounded_mutation",
  workspaceAlias = "cyberboss",
  maxAttempts = 1,
  text = `fixture ${index}`,
} = {}) {
  return database.acceptInbound({
    source: "weixin",
    sourceAccountRef: "fixture-account",
    sourceMessageId: `fixture-source-${index}`,
    userRef: "fixture-sender",
    messageType: operationClass === "command" ? "command" : "text",
    payload: normalizedPayload(index, text),
    contextToken: `context-${index}`,
    workspaceAlias,
    runtime: "codex",
    operationClass,
    maxAttempts,
  });
}

function readySnapshot({ poll, runtime, queue }) {
  return {
    poll,
    runtime,
    memory: { totalMb: 4096, availableMb: 3000 },
    storage: {
      freeMb: 25_000,
      usedPercent: 40,
      inodeUsedPercent: 10,
    },
    load: { oneMinute: 0.5, cpuCount: 2 },
    queue: {
      depth: queue.queuedTotal,
      oldestQueuedAt: queue.oldestQueuedAt,
      activeRuntime: queue.activeRuntimeJobs > 0,
    },
  };
}

function createScheduler(environment, {
  dispatchRuntime,
  dispatchControl = async () => ({ resultCode: "processed" }),
  ownerId = "scheduler_fixture",
  runtimeLeaseMs = 30_000,
  controlLeaseMs = 10_000,
  snapshotProvider = readySnapshot,
} = {}) {
  const scheduler = new JobScheduler({
    database: environment.database,
    workspaceRegistry: environment.workspaceRegistry,
    dispatchRuntime,
    dispatchControl,
    runtimeReadiness: () => ({ ready: true, reason: "ready" }),
    snapshotProvider,
    gate: new ResourceReadinessGate({
      now: environment.clock.now,
      pollStaleMs: 90_000,
      queueStuckMs: 300_000,
      queueLimit: 20,
    }),
    now: environment.clock.now,
    ownerId,
    bootId: "boot_fixture",
    pid: 4242,
    runtimeLeaseMs,
    controlLeaseMs,
  });
  scheduler.notePollSuccess(environment.clock.now());
  return scheduler;
}

function terminalEvent(run, status = "completed") {
  return {
    type: "runtime.turn.completed",
    payload: {
      threadId: run.threadId,
      turnId: run.turnId,
      status,
    },
  };
}

test("five Runtime jobs dispatch FIFO and never exceed one active lease", async (t) => {
  const environment = fixtureEnvironment(t);
  const accepted = [];
  for (let index = 0; index < 5; index += 1) {
    accepted.push(enqueue(environment.database, index));
    environment.clock.advance(1);
  }
  const dispatches = [];
  let activeTurns = 0;
  let maxActiveTurns = 0;
  const scheduler = createScheduler(environment, {
    async dispatchRuntime({ job, normalized }) {
      activeTurns += 1;
      maxActiveTurns = Math.max(maxActiveTurns, activeTurns);
      const run = {
        jobId: job.id,
        messageId: normalized.messageId,
        threadId: `thread-${dispatches.length + 1}`,
        turnId: `turn-${dispatches.length + 1}`,
      };
      dispatches.push(run);
      return run;
    },
  });

  for (let index = 0; index < 5; index += 1) {
    const cycle = await scheduler.runCycle();
    assert.equal(cycle.runtime.dispatched, true);
    assert.equal(environment.database.queueMetrics().activeRuntimeLeases, 1);
    assert.equal((await scheduler.runCycle()).runtime.reason, "active_job");
    activeTurns -= 1;
    const handled = await scheduler.handleRuntimeEvent(
      terminalEvent(dispatches[index]),
    );
    assert.equal(handled.terminalStatus, "succeeded");
    assert.equal(environment.database.queueMetrics().activeRuntimeLeases, 0);
  }

  assert.equal(maxActiveTurns, 1);
  assert.deepEqual(
    dispatches.map((row) => row.jobId),
    accepted.map((row) => row.jobId),
  );
  assert.deepEqual(
    accepted.map((row) => environment.database.getJob(row.jobId).status),
    ["succeeded", "succeeded", "succeeded", "succeeded", "succeeded"],
  );
  environment.database.close();
});

test("contending database owners cannot claim a second Runtime lease", (t) => {
  const environment = fixtureEnvironment(t);
  enqueue(environment.database, "claim-a");
  environment.clock.advance(1);
  enqueue(environment.database, "claim-b");
  const secondConnection = new RuntimeSpoolDatabase({
    databasePath: path.join(environment.directory, "runtime.db"),
    encryptionKey: Buffer.from(FIXTURE_KEY),
    identityKey: Buffer.from(FIXTURE_KEY),
    now: environment.clock.now,
  });
  const first = environment.database.claimNextRuntimeJob({
    ownerId: "owner_a",
    leaseMs: 1_000,
    bootId: "boot_a",
    pid: 1001,
  });
  const second = secondConnection.claimNextRuntimeJob({
    ownerId: "owner_b",
    leaseMs: 1_000,
    bootId: "boot_b",
    pid: 1002,
  });
  assert.equal(first.claimed, true);
  assert.equal(second.claimed, false);
  assert.equal(second.reason, "active_job");
  assert.equal(environment.database.queueMetrics().activeRuntimeLeases, 1);
  secondConnection.close();
  environment.database.close();
});

test("lease heartbeat fences stale owners and recovery never replays ambiguous mutation", (t) => {
  const environment = fixtureEnvironment(t);
  const preDispatch = enqueue(environment.database, "pre-dispatch");
  const first = environment.database.claimNextRuntimeJob({
    ownerId: "owner_a",
    leaseMs: 100,
    bootId: "boot_a",
    pid: 1001,
  });
  assert.equal(first.claimed, true);
  environment.clock.advance(101);
  assert.throws(
    () => environment.database.heartbeatManagedLease(preDispatch.jobId, {
      ownerId: "owner_a",
      leaseMs: 100,
    }),
    { code: "LEASE_EXPIRED" },
  );
  assert.deepEqual(environment.database.recoverExpiredRuntimeLease(), {
    recovered: true,
    classification: "safe_before_dispatch",
    requeued: true,
    jobId: preDispatch.jobId,
  });
  assert.equal(environment.database.getJob(preDispatch.jobId).status, "queued");

  const second = environment.database.claimNextRuntimeJob({
    ownerId: "owner_b",
    leaseMs: 100,
    expectedJobId: preDispatch.jobId,
    bootId: "boot_b",
    pid: 1002,
  });
  assert.equal(second.claimed, true);
  environment.database.markRuntimeDispatchStarted(preDispatch.jobId, {
    ownerId: "owner_b",
  });
  environment.database.bindRuntimeRun(preDispatch.jobId, {
    ownerId: "owner_b",
    threadId: "thread-ambiguous",
    turnId: "turn-ambiguous",
  });
  environment.clock.advance(101);
  const recovered = environment.database.recoverExpiredRuntimeLease();
  assert.equal(recovered.classification, "ambiguous_after_dispatch");
  assert.equal(recovered.requeued, false);
  assert.equal(
    environment.database.getJob(preDispatch.jobId).status,
    "failed_terminal",
  );
  assert.equal(environment.database.peekNextRuntimeJob(), null);
  environment.database.close();
});

test("late event cannot release a newer fenced lease", async (t) => {
  const environment = fixtureEnvironment(t);
  const firstJob = enqueue(environment.database, "late-a");
  environment.clock.advance(1);
  const secondJob = enqueue(environment.database, "late-b");
  const firstRuns = [];
  const scheduler = createScheduler(environment, {
    ownerId: "owner_a",
    runtimeLeaseMs: 100,
    async dispatchRuntime() {
      const run = {
        threadId: "thread-late-a",
        turnId: "turn-late-a",
      };
      firstRuns.push(run);
      return run;
    },
  });
  await scheduler.runCycle();
  environment.clock.advance(101);
  const recovery = environment.database.recoverExpiredRuntimeLease();
  assert.equal(recovery.jobId, firstJob.jobId);
  const newer = environment.database.claimNextRuntimeJob({
    ownerId: "owner_b",
    leaseMs: 1_000,
    expectedJobId: secondJob.jobId,
    bootId: "boot_b",
    pid: 1002,
  });
  assert.equal(newer.claimed, true);
  const late = await scheduler.handleRuntimeEvent(
    terminalEvent(firstRuns[0]),
  );
  assert.equal(late.handled, false);
  assert.ok(["stale_binding", "late_or_unmatched"].includes(late.reason));
  assert.equal(environment.database.getJob(secondJob.jobId).status, "running");
  assert.equal(environment.database.getJob(secondJob.jobId).lease_owner, "owner_b");
  environment.database.close();
});

test("only proven read-only retry is requeued; bounded mutation is terminal", async (t) => {
  for (const [operationClass, expected] of [
    ["read_only", "queued"],
    ["bounded_mutation", "failed_terminal"],
  ]) {
    const environment = fixtureEnvironment(t);
    const accepted = enqueue(environment.database, `retry-${operationClass}`, {
      operationClass,
      maxAttempts: 2,
    });
    let run;
    const scheduler = createScheduler(environment, {
      async dispatchRuntime() {
        run = {
          threadId: `thread-${operationClass}`,
          turnId: `turn-${operationClass}`,
        };
        return run;
      },
    });
    await scheduler.runCycle();
    await scheduler.handleRuntimeEvent({
      type: "runtime.turn.failed",
      payload: {
        threadId: run.threadId,
        turnId: run.turnId,
        text: "fixture unavailable",
        errorClass: "runtime_overloaded",
        retryable: true,
      },
    });
    assert.equal(environment.database.getJob(accepted.jobId).status, expected);
    assert.equal(environment.database.getJob(accepted.jobId).attempt_count, 1);
    environment.database.close();
  }
});

test("control plane processes stop beside active Runtime lease and records truthful terminal", async (t) => {
  for (const [runtimeStatus, expectedStatus] of [
    ["interrupted", "cancelled"],
    ["completed", "succeeded"],
    ["failed", "failed_terminal"],
  ]) {
    const environment = fixtureEnvironment(t);
    const active = enqueue(environment.database, `active-${runtimeStatus}`);
    const dispatches = [];
    const controlCalls = [];
    const scheduler = createScheduler(environment, {
      async dispatchRuntime() {
        const run = {
          threadId: `thread-${runtimeStatus}`,
          turnId: `turn-${runtimeStatus}`,
        };
        dispatches.push(run);
        return run;
      },
      async dispatchControl({ command, activeRun }) {
        controlCalls.push({
          command: command.name,
          active: Boolean(activeRun),
          runBound: activeRun?.runBound === true,
        });
        return { resultCode: "cancel_acknowledged" };
      },
    });
    await scheduler.runCycle();
    environment.clock.advance(1);
    const stop = enqueue(environment.database, `stop-${runtimeStatus}`, {
      operationClass: "command",
      text: "/stop",
    });
    await scheduler.runCycle();
    assert.deepEqual(controlCalls, [{
      command: "stop",
      active: true,
      runBound: true,
    }]);
    assert.equal(environment.database.getJob(stop.jobId).status, "succeeded");
    assert.ok(environment.database.getJob(active.jobId).cancel_requested_at);
    assert.equal(environment.database.getJob(active.jobId).status, "running");
    assert.equal(environment.database.queueMetrics().activeRuntimeLeases, 1);

    if (runtimeStatus === "failed") {
      await scheduler.handleRuntimeEvent({
        type: "runtime.turn.failed",
        payload: {
          threadId: dispatches[0].threadId,
          turnId: dispatches[0].turnId,
          text: "fixture terminal",
          retryable: false,
        },
      });
    } else {
      await scheduler.handleRuntimeEvent(
        terminalEvent(dispatches[0], runtimeStatus),
      );
    }
    assert.equal(environment.database.getJob(active.jobId).status, expectedStatus);
    assert.equal(environment.database.queueMetrics().activeRuntimeLeases, 0);
    environment.database.close();
  }
});

test("absolute, unknown and symlink workspace jobs fail without Runtime dispatch", async (t) => {
  for (const [name, workspaceAlias, mutateWorkspace] of [
    ["absolute", "/etc", null],
    ["unknown", "missing", null],
    ["symlink", "cyberboss", "symlink"],
  ]) {
    const environment = fixtureEnvironment(t);
    if (mutateWorkspace === "symlink") {
      fs.rmdirSync(environment.workspaceRoot);
      fs.symlinkSync(environment.outsideRoot, environment.workspaceRoot);
    }
    const before = fs.readdirSync(environment.outsideRoot).sort();
    const accepted = enqueue(environment.database, `workspace-${name}`, {
      workspaceAlias,
    });
    let runtimeCalls = 0;
    const scheduler = createScheduler(environment, {
      async dispatchRuntime() {
        runtimeCalls += 1;
        return { threadId: "forbidden", turnId: "forbidden" };
      },
    });
    const cycle = await scheduler.runCycle();
    assert.equal(cycle.runtime.reason, "workspace_alias_rejected");
    assert.equal(runtimeCalls, 0);
    assert.equal(
      environment.database.getJob(accepted.jobId).status,
      "failed_terminal",
    );
    assert.deepEqual(fs.readdirSync(environment.outsideRoot).sort(), before);
    environment.database.close();
  }
});

test("resource protect leaves mutation queued and dispatches after recover", async (t) => {
  const environment = fixtureEnvironment(t);
  const accepted = enqueue(environment.database, "resource-protect");
  let protectedState = true;
  let runtimeCalls = 0;
  const scheduler = createScheduler(environment, {
    snapshotProvider(facts) {
      const value = readySnapshot(facts);
      if (protectedState) {
        value.memory.availableMb = 400;
      }
      return value;
    },
    async dispatchRuntime() {
      runtimeCalls += 1;
      return { threadId: "thread-recovered", turnId: "turn-recovered" };
    },
  });
  const blocked = await scheduler.runCycle();
  assert.equal(blocked.runtime.reason, "memory_pressure");
  assert.equal(runtimeCalls, 0);
  assert.equal(environment.database.getJob(accepted.jobId).status, "queued");
  protectedState = false;
  const recovered = await scheduler.runCycle();
  assert.equal(recovered.runtime.dispatched, true);
  assert.equal(runtimeCalls, 1);
  environment.database.close();
});

test("Codex terminal and approval events preserve status, retryability and turn binding", () => {
  assert.deepEqual(
    mapCodexMessageToRuntimeEvent({
      method: "turn/completed",
      params: {
        threadId: "thread-1",
        turnId: "turn-1",
        turn: { id: "turn-1", status: "interrupted" },
      },
    }),
    {
      type: "runtime.turn.completed",
      payload: {
        threadId: "thread-1",
        turnId: "turn-1",
        status: "interrupted",
        cancelled: true,
      },
    },
  );
  const failed = mapCodexMessageToRuntimeEvent({
    method: "turn/failed",
    params: {
      threadId: "thread-1",
      turnId: "turn-1",
      turn: {
        id: "turn-1",
        status: "failed",
        error: {
          code: "runtime_overloaded",
          message: "fixture failure",
          retryable: true,
        },
      },
    },
  });
  assert.equal(failed.payload.retryable, true);
  assert.equal(failed.payload.errorClass, "runtime_overloaded");
  const approval = mapCodexMessageToRuntimeEvent({
    id: "approval-1",
    method: "item/commandExecution/requestApproval",
    params: {
      threadId: "thread-1",
      turnId: "turn-1",
      command: ["printf", "fixture"],
    },
  });
  assert.equal(approval.payload.turnId, "turn-1");
});
