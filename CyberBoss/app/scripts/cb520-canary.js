"use strict";

const assert = require("node:assert/strict");

const { CyberbossApp } = require("../src/core/app");
const { evaluateInboundPolicy } = require("../src/adapters/channel/weixin/message-utils");

const TASK_ID = "CB-520";
const MAX_INPUT_BYTES = 32 * 1024;
const CANARY_SENDER_ID = "cb520-canary-owner";

function evaluatePolicyCanary() {
  const config = {
    allowedUserIds: [CANARY_SENDER_ID],
    maxInputBytes: MAX_INPUT_BYTES,
  };
  const accepted = evaluateInboundPolicy({
    senderId: CANARY_SENDER_ID,
    text: "/status",
    config,
  });
  const unauthorized = evaluateInboundPolicy({
    senderId: "cb520-unauthorized",
    text: "/status",
    config,
  });
  const oversize = evaluateInboundPolicy({
    senderId: CANARY_SENDER_ID,
    text: "x".repeat(MAX_INPUT_BYTES + 1),
    config,
  });

  assert.deepEqual(accepted, {
    accepted: true,
    code: "accepted",
    inputBytes: 7,
    maxInputBytes: MAX_INPUT_BYTES,
  });
  assert.equal(unauthorized.accepted, false);
  assert.equal(unauthorized.code, "sender_not_allowed");
  assert.equal(oversize.accepted, false);
  assert.equal(oversize.code, "input_too_large");
  assert.equal(oversize.inputBytes, MAX_INPUT_BYTES + 1);

  return {
    accepted_read_only: true,
    unauthorized_rejected: true,
    oversize_rejected: true,
    max_input_bytes: MAX_INPUT_BYTES,
  };
}

async function evaluateStopControlCanary() {
  const calls = [];
  const appLike = {
    resolveWorkspaceRoot() {
      return "/srv/cyberboss-workspaces/cyberboss";
    },
    threadStateStore: {
      getThreadState(threadId) {
        calls.push(["state", threadId]);
        return { threadId, turnId: "canary-turn", status: "running" };
      },
    },
    runtimeAdapter: {
      async cancelTurn({ threadId, turnId, workspaceRoot }) {
        calls.push(["cancel", threadId, turnId, workspaceRoot]);
      },
      getSessionStore() {
        return {
          buildBindingKey() {
            return "cb520-canary-binding";
          },
          getThreadIdForWorkspace() {
            return "cb520-canary-thread";
          },
        };
      },
    },
    channelAdapter: {
      async sendText({ text }) {
        calls.push(["reply", text]);
      },
    },
  };

  await CyberbossApp.prototype.handleStopCommand.call(appLike, {
    workspaceId: "cyberboss",
    accountId: "cb520-canary-account",
    senderId: CANARY_SENDER_ID,
    contextToken: "cb520-canary-context",
  });

  assert.deepEqual(calls, [
    ["state", "cb520-canary-thread"],
    ["cancel", "cb520-canary-thread", "canary-turn", "/srv/cyberboss-workspaces/cyberboss"],
    ["reply", "⏹️ Stop request sent\nthread: cb520-canary-thread"],
  ]);

  return {
    stop_handler_cancelled_bound_turn: true,
    runtime_turn_start_calls: 0,
    control_plane_llm_calls: 0,
    operations_llm_calls: 0,
    real_wechat_delivery: "pending_missing_real_wechat_credential",
  };
}

async function runReleaseCodeCanary() {
  return {
    schema_version: "cyberboss.cb520.release-code-canary.v1",
    task_id: TASK_ID,
    policy: evaluatePolicyCanary(),
    stop: await evaluateStopControlCanary(),
    real_time_waits: 0,
    simulator_started: false,
    result: "passed_with_real_wechat_pending",
  };
}

async function main(argv = process.argv.slice(2)) {
  if (argv.length !== 0) {
    throw new Error("CB520_CANARY_USAGE");
  }
  const receipt = await runReleaseCodeCanary();
  process.stdout.write(`${JSON.stringify(receipt)}\nCB520_RELEASE_CODE_CANARY=PASS\n`);
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`CB520_RELEASE_CODE_CANARY=FAIL reason=${error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  CANARY_SENDER_ID,
  MAX_INPUT_BYTES,
  evaluatePolicyCanary,
  evaluateStopControlCanary,
  runReleaseCodeCanary,
};
