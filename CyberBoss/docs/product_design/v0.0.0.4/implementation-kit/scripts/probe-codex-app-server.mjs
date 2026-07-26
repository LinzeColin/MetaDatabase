#!/usr/bin/env node

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const CLIENT_INFO = {
  name: "cyberboss_agent",
  title: "Cyberboss Agent",
  version: "0.1.0",
};
const EXPECTED_ENDPOINT = "ws://127.0.0.1:8765";

function fail(message) {
  throw new Error(message);
}

function parseArgs(argv) {
  const options = {
    codexCommand: "",
    endpoint: EXPECTED_ENDPOINT,
    output: "",
    readyMarker: "",
    releaseMarker: "",
  };
  for (let index = 0; index < argv.length; index += 1) {
    const name = argv[index];
    if (!["--codex-command", "--endpoint", "--output", "--ready-marker", "--release-marker"].includes(name)) {
      fail(`unknown_arg:${name}`);
    }
    const value = argv[index + 1];
    if (!value) {
      fail(`missing_value:${name}`);
    }
    index += 1;
    if (name === "--codex-command") options.codexCommand = value;
    if (name === "--endpoint") options.endpoint = value;
    if (name === "--output") options.output = value;
    if (name === "--ready-marker") options.readyMarker = value;
    if (name === "--release-marker") options.releaseMarker = value;
  }
  if (!path.isAbsolute(options.codexCommand)) fail("codex_command_must_be_absolute");
  if (!path.isAbsolute(options.output)) fail("output_must_be_absolute");
  if (options.endpoint !== EXPECTED_ENDPOINT) fail("endpoint_must_be_exact_loopback");
  if (options.readyMarker && !path.isAbsolute(options.readyMarker)) {
    fail("ready_marker_must_be_absolute");
  }
  if (options.releaseMarker && !path.isAbsolute(options.releaseMarker)) {
    fail("release_marker_must_be_absolute");
  }
  if (Boolean(options.readyMarker) !== Boolean(options.releaseMarker)) {
    fail("ready_and_release_markers_must_be_paired");
  }
  return options;
}

function writeExclusive(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
    mode: 0o600,
  });
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForPredicate(predicate, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const value = await predicate();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await delay(50);
  }
  const detail = lastError instanceof Error ? `:${lastError.message}` : "";
  fail(`${label}_timeout${detail}`);
}

async function probeReadyz(endpoint) {
  const readyUrl = endpoint.replace(/^ws:/, "http:") + "/readyz";
  return waitForPredicate(async () => {
    const response = await fetch(readyUrl, { signal: AbortSignal.timeout(500) });
    if (!response.ok) return null;
    const body = (await response.text()).trim();
    if (body && body !== "ready") return null;
    return {
      status: response.status,
      body_classification: body === "ready" ? "ready" : "empty_success",
    };
  }, 15_000, "readyz");
}

async function initializeProtocol(endpoint) {
  const socket = await waitForPredicate(async () => {
    const candidate = new WebSocket(endpoint);
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("open_pending")), 500);
        candidate.addEventListener("open", () => {
          clearTimeout(timer);
          resolve();
        }, { once: true });
        candidate.addEventListener("error", () => {
          clearTimeout(timer);
          reject(new Error("connect_pending"));
        }, { once: true });
      });
      return candidate;
    } catch (error) {
      try {
        candidate.close();
      } catch {
        // The socket never opened.
      }
      throw error;
    }
  }, 15_000, "websocket");

  try {
    const response = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("initialize_timeout")), 5_000);
      socket.addEventListener("message", (event) => {
        let message;
        try {
          message = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (message.id !== 110) return;
        clearTimeout(timer);
        resolve(message);
      });
      socket.send(JSON.stringify({
        jsonrpc: "2.0",
        id: 110,
        method: "initialize",
        params: {
          clientInfo: CLIENT_INFO,
          capabilities: { experimentalApi: true },
        },
      }));
    });
    if (!response || response.error || !response.result) {
      fail("initialize_result_missing");
    }
    socket.send(JSON.stringify({
      jsonrpc: "2.0",
      method: "initialized",
      params: null,
    }));
    return { initializeResultPresent: true, initializedSent: true };
  } finally {
    socket.close();
  }
}

async function stopChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
  const exited = await Promise.race([
    new Promise((resolve) => child.once("exit", () => resolve(true))),
    delay(2_000).then(() => false),
  ]);
  if (!exited) {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      child.kill("SIGKILL");
    }
    await new Promise((resolve) => child.once("exit", resolve));
  }
}

const options = parseArgs(process.argv.slice(2));
let stderrBytes = 0;
let child = null;
let report = {
  schema_version: 1,
  task_id: "CB-110",
  endpoint: EXPECTED_ENDPOINT,
  listener_scope: "loopback_only",
  readyz: { passed: false },
  protocol: {
    initialize_result_present: false,
    initialized_sent: false,
    authenticated_turn_started: false,
  },
  credential_content_read: false,
  public_callback_used: false,
  business_runtime_started: false,
  child_cleanup: "pending",
};

try {
  child = spawn(
    options.codexCommand,
    ["app-server", "--listen", EXPECTED_ENDPOINT],
    {
      detached: true,
      env: { ...process.env },
      stdio: ["ignore", "ignore", "pipe"],
    },
  );
  child.stderr.on("data", (chunk) => {
    stderrBytes += chunk.length;
  });
  child.once("error", (error) => {
    report.spawn_error_class = error?.code || error?.name || "spawn_error";
  });

  const readyz = await probeReadyz(EXPECTED_ENDPOINT);
  const protocol = await initializeProtocol(EXPECTED_ENDPOINT);
  report.readyz = {
    passed: true,
    status: readyz.status,
    body_classification: readyz.body_classification,
  };
  report.protocol.initialize_result_present = protocol.initializeResultPresent;
  report.protocol.initialized_sent = protocol.initializedSent;
  report.server_stderr_persisted = false;
  report.server_stderr_bytes_observed = stderrBytes;

  if (options.readyMarker) {
    writeExclusive(options.readyMarker, {
      ready: true,
      endpoint: EXPECTED_ENDPOINT,
      credential_content_read: false,
    });
    await waitForPredicate(
      async () => fs.existsSync(options.releaseMarker),
      60_000,
      "external_scan_release_marker",
    );
  }
} catch (error) {
  report.failure = error instanceof Error ? error.message : "unknown_failure";
} finally {
  if (child) await stopChild(child);
  report.child_cleanup = "complete";
  report.server_stderr_persisted = false;
  report.server_stderr_bytes_observed = stderrBytes;
}

writeExclusive(options.output, report);
if (report.failure || !report.readyz.passed || !report.protocol.initialize_result_present) {
  console.error(`CODEX_APP_SERVER_PROBE=FAIL reason=${report.failure || "oracle"}`);
  process.exit(1);
}
console.log(
  "CODEX_APP_SERVER_PROBE=PASS endpoint=127.0.0.1:8765 " +
  "readyz=PASS initialize=PASS initialized=sent authenticated_turn=0 " +
  "credential_content_read=0 public_callback=0 cleanup=complete",
);
